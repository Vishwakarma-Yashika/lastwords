"""Read a git repo and work out who the ghosts are."""
from __future__ import annotations

import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from .errors import LastWordsError

# Files whose lines are counted separately from hand-written source code.
GENERATED_SUFFIXES = (".po", ".pot", ".mo", ".min.js", ".min.css", ".map")
GENERATED_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "pipfile.lock", "cargo.lock", "composer.lock", "gemfile.lock", "go.sum",
}

# One git log record: fields split by \x1f, records started by \x1e.
_LOG_FORMAT = "%x1e%H%x1f%aN%x1f%aE%x1f%an%x1f%ae%x1f%ct%x1f%B%x1f"


@dataclass
class CommitRecord:
    sha: str
    message: str
    when: datetime
    files: list[str]
    # identity exactly as recorded in the commit, before .mailmap
    author_name: str = ""
    author_email: str = ""


@dataclass
class Author:
    name: str
    email: str
    commits: list[CommitRecord] = field(default_factory=list)
    surviving_lines: int = 0  # hand-written source lines still at HEAD
    resource_lines: int = 0  # translation, generated and lock-file lines at HEAD

    @property
    def first_commit(self) -> CommitRecord:
        return min(self.commits, key=lambda c: c.when)

    @property
    def last_commit(self) -> CommitRecord:
        return max(self.commits, key=lambda c: c.when)

    @property
    def aliases(self) -> set[tuple[str, str]]:
        """Every (name, email) this person committed under, before .mailmap."""
        return {(c.author_name, c.author_email) for c in self.commits}

    def top_files(self, n: int = 5) -> list[str]:
        counts: dict[str, int] = defaultdict(int)
        for c in self.commits:
            for f in c.files:
                counts[f] += 1
        return [f for f, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:n]]


def git(repo_path: str, *args: str, stdin: str | None = None) -> str:
    """Run git in the repo and return stdout. Paths are printed unquoted as UTF-8.

    Bytes are decoded by hand so \\r\\n inside commit messages survives unchanged.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "-c", "core.quotePath=false", *args],
            input=stdin.encode("utf-8") if stdin is not None else None,
            capture_output=True,
        )
    except FileNotFoundError:
        raise LastWordsError("git is not installed or not on PATH") from None
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise LastWordsError(f"git {args[0]} failed: {stderr}")
    return result.stdout.decode("utf-8", "replace")


def open_repo(repo_path: str) -> Repo:
    """Open a repo or explain, in one line, why it can't be used."""
    path = Path(repo_path)
    if not path.exists():
        raise LastWordsError(f"{repo_path}: no such folder")
    if not path.is_dir():
        raise LastWordsError(f"{repo_path} is a file, not a git repository folder")
    try:
        repo = Repo(path)
    except (InvalidGitRepositoryError, NoSuchPathError):
        raise LastWordsError(
            f"{repo_path} is not a git repository (point it at the folder that contains .git)"
        ) from None
    if not repo.head.is_valid():
        raise LastWordsError(f"{repo_path} has no commits yet")
    return repo


def author_key(person) -> str:
    """People commit under several emails; the display name is the better identity.

    `person` is any object with .name and .email. Git applies .mailmap before
    these reach us, so a mapped name merges here too.
    """
    return identity_key(person.name, person.email)


def identity_key(name: str | None, email: str | None) -> str:
    return (name or email or "unknown").strip().lower()


def _parse_log(repo_path: str, *rev_args: str) -> list[tuple[str, str, CommitRecord]]:
    """(mapped name, mapped email, commit) for each commit, in one git call.

    %aN/%aE apply .mailmap; %an/%ae keep the original identity. Merges are
    diffed against their first parent, without rename detection.
    """
    out = git(
        repo_path, "log", f"--format={_LOG_FORMAT}", "--numstat",
        "--no-renames", "--diff-merges=first-parent", *rev_args,
    )
    records = []
    for chunk in out.split("\x1e")[1:]:
        sha, name, email, raw_name, raw_email, ts, body, stats = chunk.split("\x1f", 7)
        files = [line.split("\t", 2)[2] for line in stats.splitlines() if line.count("\t") >= 2]
        records.append((name, email, CommitRecord(
            sha=sha,
            message=body.strip(),
            when=datetime.fromtimestamp(int(ts), tz=timezone.utc),
            files=files,
            author_name=raw_name,
            author_email=raw_email.lower(),
        )))
    return records


def load_authors(repo_path: str, max_commits: int = 5000) -> dict[str, Author]:
    """Group commits by author, merging the same (mailmapped) name across emails."""
    open_repo(repo_path)
    authors: dict[str, Author] = {}
    for name, email, record in _parse_log(repo_path, f"--max-count={max_commits}", "HEAD"):
        key = identity_key(name, email)
        author = authors.setdefault(key, Author(name or key, email.lower()))
        author.commits.append(record)
    return authors


def load_commit(repo_path: str, sha: str) -> tuple[str, Author]:
    """A single commit wrapped in an Author, for commits older than max_commits."""
    name, email, record = _parse_log(repo_path, "-1", sha)[0]
    return identity_key(name, email), Author(name, email.lower(), [record])


def owner_of(authors: dict[str, Author], sha: str) -> Author | None:
    for author in authors.values():
        if any(c.sha == sha for c in author.commits):
            return author
    return None


def is_generated(path: str, attributes: dict[str, str] | None = None) -> bool:
    """Translation, generated or lock files: counted, but not as source code."""
    if attributes and attributes.get(path) in ("set", "true"):
        return True
    name = PurePosixPath(path).name.lower()
    return name in GENERATED_NAMES or name.endswith(GENERATED_SUFFIXES)


def head_text_files(repo_path: str) -> list[str]:
    """Files at HEAD that git treats as text (binary files have no lines to credit)."""
    empty_tree = git(repo_path, "mktree", stdin="").strip()
    out = git(repo_path, "diff", "--numstat", "--no-renames", empty_tree, "HEAD")
    files = []
    for line in out.splitlines():
        added, _, path = line.split("\t", 2)
        if added != "-":
            files.append(path)
    return files


def linguist_generated(repo_path: str, paths: list[str]) -> dict[str, str]:
    """Honour `linguist-generated` from .gitattributes, the attribute GitHub uses."""
    if not paths:
        return {}
    out = git(repo_path, "check-attr", "-z", "--stdin", "linguist-generated", stdin="\0".join(paths) + "\0")
    parts = out.split("\0")
    return {parts[i]: parts[i + 2] for i in range(0, len(parts) - 2, 3)}


def count_surviving_lines(repo_path: str, authors: dict[str, Author]) -> None:
    """Blame every text file at HEAD and credit each line to its author.

    Counts are recomputed from zero, so calling this twice gives the same result.
    Lines in generated or translation files go to `resource_lines`.
    """
    repo = open_repo(repo_path)
    by_sha = {c.sha: a for a in authors.values() for c in a.commits}
    for author in authors.values():
        author.surviving_lines = 0
        author.resource_lines = 0
    files = head_text_files(repo_path)
    attributes = linguist_generated(repo_path, files)
    for path in files:
        try:
            blame = repo.blame("HEAD", path)
        except GitCommandError:
            continue  # unreadable at HEAD
        generated = is_generated(path, attributes)
        for commit, lines in blame:
            author = by_sha.get(commit.hexsha) or authors.get(author_key(commit.author))
            if author is None:
                continue
            if generated:
                author.resource_lines += len(lines)
            else:
                author.surviving_lines += len(lines)


def find_ghosts(
    authors: dict[str, Author], inactive_days: int = 365, now: datetime | None = None
) -> list[Author]:
    """Authors whose last commit is older than the threshold, most haunting first."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=inactive_days)
    ghosts = [a for a in authors.values() if a.last_commit.when < cutoff]
    return sorted(ghosts, key=lambda a: (-a.surviving_lines, -a.resource_lines))
