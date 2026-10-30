"""Channel a ghost: answer a question using only what they committed."""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path, PurePosixPath

import httpx
import ollama

from . import tracing
from .errors import LastWordsError
from .history import Author, CommitRecord, author_key, git, open_repo

DEFAULT_MODEL = "gemma2:2b"
NO_MEMORY = "The veil is thin... I do not remember this."

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "why", "how", "what", "this", "that",
    "do", "did", "does", "of", "to", "in", "it", "for", "and", "or", "you", "i",
}

# A cited hash: bracketed like [83cfe03], or bare with both a digit and a letter
# so ordinary words ("defaced") and numbers ("1234567") are left alone.
_BRACKETED = re.compile(r"\[([0-9a-f]{7,40})\]")
_BARE = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")


def resolve_file(repo_path: str, file: str) -> str:
    """Turn --file into a repo-relative POSIX path that exists as a file at HEAD."""
    repo = open_repo(repo_path)
    path = Path(file)
    if path.is_absolute():
        root = Path(repo.working_tree_dir or repo_path).resolve()
        try:
            rel = PurePosixPath(path.resolve().relative_to(root).as_posix())
        except ValueError:
            raise LastWordsError(f"{file} is outside the repository {root}") from None
    else:
        rel = PurePosixPath(file.replace("\\", "/"))
    if ".." in rel.parts or not rel.parts:
        raise LastWordsError(f"{file} is not a path inside the repository")
    try:
        kind = git(repo_path, "cat-file", "-t", f"HEAD:{rel.as_posix()}").strip()
    except LastWordsError:
        raise LastWordsError(f"{rel} does not exist in the latest commit (HEAD)") from None
    if kind != "blob":
        raise LastWordsError(f"{rel} is a folder, not a file")
    return rel.as_posix()


def blame_line(repo_path: str, file: str, line: int) -> tuple[str, str]:
    """Return (author key, commit sha) for one line of a file at HEAD."""
    if line < 1:
        raise LastWordsError(f"--line must be 1 or more (got {line})")
    path = resolve_file(repo_path, file)
    seen = 0
    for commit, lines in open_repo(repo_path).blame("HEAD", path):
        if seen < line <= seen + len(lines):
            return author_key(commit.author), commit.hexsha
        seen += len(lines)
    raise LastWordsError(f"{path} has {seen} lines; there is no line {line}")


def _words(text: str) -> set[str]:
    """Whole words, lowercased, with a trailing plural 's' dropped."""
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"[a-z0-9_]+", text.lower())}


def retrieve(
    author: Author,
    question: str,
    file: str | None = None,
    limit: int = 6,
    blamed_sha: str | None = None,
) -> list[CommitRecord]:
    """Pick the commits whose message or files best match the question.

    The commit that blame says wrote the line always comes first, whatever its
    keywords. The rest are ranked by whole-word overlap with the question, with
    a head start for commits that touched the same file. No commit appears twice.
    """
    words = _words(question) - STOPWORDS
    picked: list[CommitRecord] = []
    if blamed_sha:
        blamed = next((c for c in author.commits if c.sha == blamed_sha), None)
        if blamed is None:
            raise ValueError(f"{blamed_sha[:7]} is not one of {author.name}'s commits")
        picked.append(blamed)

    def score(c: CommitRecord) -> int:
        text = _words(c.message + " " + " ".join(c.files))
        return len(words & text) + (1 if file and file in c.files else 0)

    ranked = sorted(author.commits, key=lambda c: (-score(c), -c.when.timestamp()))
    for c in ranked:
        if len(picked) >= limit:
            break
        if score(c) > 0 and c.sha != blamed_sha:
            picked.append(c)
    return picked


def build_prompt(
    author: Author, question: str, memories: list[CommitRecord], blamed_sha: str | None = None
) -> str:
    def note(c: CommitRecord) -> str:
        mark = "  <- this commit wrote the line being asked about" if c.sha == blamed_sha else ""
        return f"- [{c.sha[:7]}] {c.when.date()}: {c.message.splitlines()[0]}{mark}"

    notes = "\n".join(note(c) for c in sorted(memories, key=lambda c: c.when))
    return (
        f"You are the ghost of {author.name}, a developer who once worked on this code "
        f"and last committed on {author.last_commit.when.date()}.\n"
        "Speak in first person, briefly, with a quiet haunted tone.\n"
        "Answer using ONLY the memories below, and cite the commit hash in square "
        "brackets when you use one. If they only partly answer, say what you do "
        "remember and admit what you have forgotten. Never invent details.\n\n"
        f"Memories (oldest first):\n{notes}\n\nQuestion: {question}\n"
    )


def check_citations(text: str, memories: list[CommitRecord]) -> tuple[str, list[str]]:
    """Remove cited hashes that aren't among the memories. Returns (text, removed)."""
    known = [m.sha for m in memories]
    removed: list[str] = []

    def keep(match: re.Match) -> str:
        sha = match.group(1) if match.re is _BRACKETED else match.group(0)
        if any(k.startswith(sha) for k in known):
            return match.group(0)
        removed.append(sha)
        return ""

    text = _BRACKETED.sub(keep, text)
    text = _BARE.sub(keep, text)
    return re.sub(r"[ \t]{2,}", " ", text).strip(), removed


def generate(model: str, prompt: str) -> str:
    """Run the local model, turning Ollama failures into one-line errors.

    The span follows Sentry's AI agent conventions (op gen_ai.chat). It records
    the model and token counts, never the prompt or the reply.
    """
    attrs = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "ollama",
        "gen_ai.request.model": model,
    }
    with tracing.span("gen_ai.chat", f"chat {model}", **attrs) as sp:
        try:
            reply = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        except ollama.ResponseError as e:
            if e.status_code == 404:
                raise LastWordsError(
                    f"model '{model}' is not installed in Ollama. Run: ollama pull {model}"
                ) from None
            raise LastWordsError(f"Ollama could not generate with '{model}': {e.error}") from None
        except (ConnectionError, httpx.HTTPError):
            if shutil.which("ollama") is None:
                raise LastWordsError(
                    "Ollama is not installed. Install it from https://ollama.com/download, "
                    f"then run: ollama pull {model}"
                ) from None
            host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
            raise LastWordsError(
                f"Ollama is installed but not answering at {host}. "
                "Start the Ollama app, or run: ollama serve"
            ) from None
        if sp:
            sp.set_data("gen_ai.response.model", reply.get("model") or model)
            sp.set_data("gen_ai.usage.input_tokens", reply.get("prompt_eval_count"))
            sp.set_data("gen_ai.usage.output_tokens", reply.get("eval_count"))
    return reply["message"]["content"].strip()


def ask_ghost(
    author: Author,
    question: str,
    model: str = DEFAULT_MODEL,
    file: str | None = None,
    blamed_sha: str | None = None,
) -> tuple[str, list[CommitRecord]]:
    agent = {"gen_ai.agent.name": "LastWords"}
    with tracing.span(
        "gen_ai.invoke_agent", "invoke_agent LastWords", **agent,
        **{"gen_ai.operation.name": "invoke_agent"},
    ) as agent_span:
        with tracing.span(
            "gen_ai.execute_tool", "execute_tool retrieve_memories", **agent,
            **{"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "retrieve_memories"},
        ) as sp:
            memories = retrieve(author, question, file, blamed_sha=blamed_sha)
            if sp:
                sp.set_data("memories.count", len(memories))
                sp.set_data("memories.blamed_included", any(m.sha == blamed_sha for m in memories))
        if not memories:
            return NO_MEMORY, []
        answer = generate(model, build_prompt(author, question, memories, blamed_sha))
        answer, removed = check_citations(answer, memories)
        if agent_span:
            agent_span.set_data("citations.removed", len(removed))
    if removed:
        answer += (
            f"\n(LastWords removed {len(removed)} citation(s) to commits that were not "
            "among the retrieved memories.)"
        )
    return answer, memories
