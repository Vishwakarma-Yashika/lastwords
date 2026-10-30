"""Build a static ofrenda (remembrance altar) site for a repo's ghosts."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .channel import DEFAULT_MODEL, generate
from .errors import LastWordsError
from .history import Author

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

# Marks pages LastWords wrote, so a rebuild can remove its own stale pages
# without touching anything else in --out.
GENERATOR_MARK = '<meta name="generator" content="LastWords">'

# Names that would clash with the index page or that Windows reserves.
RESERVED = {"index", "con", "prn", "aux", "nul"} | {f"{d}{i}" for d in ("com", "lpt") for i in range(1, 10)}


def slugify(name: str) -> str:
    """ASCII words from a name: 'Michael Käufl' -> 'michael-kaufl'. May be empty."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:60].strip("-")


def page_names(ghosts: list[Author]) -> list[str]:
    """A unique, filesystem-safe page name per ghost, without emails.

    The readable slug is used alone when it is unambiguous. A name with no ASCII
    letters, a reserved name, or a slug shared by two people gets a suffix from
    that person's first commit hash, which is stable and public already.
    """
    bases = [slugify(g.name) for g in ghosts]
    counts = Counter(bases)
    for length in (8, 12, 40):
        names = [
            f"{base or 'ghost'}-{g.first_commit.sha[:length]}"
            if not base or base in RESERVED or counts[base] > 1 else base
            for g, base in zip(ghosts, bases)
        ]
        if len(set(names)) == len(names):
            return names
    raise LastWordsError("two ghosts share a first commit; cannot name their pages")


TRIVIAL = re.compile(r"^(merge|sync|wip|typo|update|fix)\b|^\S+$", re.I)


def signature_commit(author: Author) -> str:
    """The commit message most worth quoting: not a merge, not a one-word chore."""
    subjects = [c.message.splitlines()[0].strip() for c in author.commits]
    meaningful = [s for s in subjects if not TRIVIAL.match(s)] or subjects
    return max(meaningful, key=len)


def _lines(n: int) -> str:
    return f"{n:,} line" if n == 1 else f"{n:,} lines"


def line_facts(author: Author, repo_name: str) -> str:
    """The line-count sentence, written by code so the numbers are exact."""
    source, resource = author.surviving_lines, author.resource_lines
    run = "runs" if source == 1 else "run"
    if source and resource:
        return (
            f"{_lines(source)} of their source code still {run} in {repo_name} today, "
            f"along with {_lines(resource)} in translation and generated files."
        )
    if source:
        return f"{_lines(source)} of their source code still {run} in {repo_name} today."
    if resource:
        ship = "ships" if resource == 1 else "ship"
        return (
            f"{_lines(resource)} of their work in translation and generated files "
            f"still {ship} with {repo_name} today."
        )
    return f"Their commits remain part of {repo_name}'s history."


def thanks(author: Author, quote: str) -> str:
    """'Thank you, Name, for “quote”.' without doubling the quote's own end mark."""
    end = "" if quote.endswith((".", "!", "?", "…")) else "."
    return f"Thank you, {author.name}, for “{quote}”{end}"


def note(author: Author, repo_name: str) -> str:
    """The default note: real name, exact commit subject, exact counts. No model."""
    return f"{thanks(author, signature_commit(author))} {line_facts(author, repo_name)}"


def remembrance(author: Author, repo_name: str, model: str = DEFAULT_MODEL) -> str:
    """Experimental (--ai-notes): the model writes the thank-you sentence.

    The code picks the commit and writes the line count, so the model has nothing
    to choose or miscount. If its sentence drops the name or the exact quote, the
    template sentence is used instead.
    """
    quote = signature_commit(author)
    prompt = (
        f"Write ONE warm sentence that starts with \"Thank you, {author.name},\" and "
        f"contains this commit message word for word inside double quotes: \"{quote}\"\n"
        f"Output only that sentence. Do not add any other facts, numbers, years or "
        f"claims. Do not say they died, left, or are gone."
    )
    text = generate(model, prompt)
    text = text.splitlines()[0].strip() if text else ""
    if quote.lower() not in text.lower() or author.name.lower() not in text.lower():
        text = thanks(author, quote)
    return f"{text} {line_facts(author, repo_name)}"


def prepare_output_dir(out_dir: str) -> Path:
    """Create --out and prove it is writable before any slow work starts."""
    out = Path(out_dir)
    if out.exists() and not out.is_dir():
        raise LastWordsError(f"--out {out_dir} is a file, not a folder")
    try:
        out.mkdir(parents=True, exist_ok=True)
        probe = out / ".lastwords-write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        raise LastWordsError(f"cannot write to --out {out_dir}: {e.strerror or e}") from None
    return out


def build_site(
    ghosts: list[Author],
    repo_name: str,
    out_dir: str,
    model: str = DEFAULT_MODEL,
    ai_notes: bool = False,
) -> Path:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,  # no blank, space-only lines where block tags were
        lstrip_blocks=True,
    )
    out = prepare_output_dir(out_dir)
    root = out.resolve()
    pages = {}
    cards = []
    for g, slug in zip(ghosts, page_names(ghosts)):
        entry = {
            "name": g.name,
            "slug": slug,
            "first": g.first_commit,
            "last": g.last_commit,
            "lines": g.surviving_lines,
            "resource_lines": g.resource_lines,
            "commits": len(g.commits),
            "files": g.top_files(),
            "text": remembrance(g, repo_name, model) if ai_notes else note(g, repo_name),
            "repo": repo_name,
        }
        pages[f"{slug}.html"] = env.get_template("ghost.html").render(g=entry, ai_notes=ai_notes)
        cards.append(entry)
    pages["index.html"] = env.get_template("index.html").render(
        cards=cards, repo=repo_name, ai_notes=ai_notes
    )

    # pages from an earlier build that this build no longer produces
    stale = [
        p for p in out.glob("*.html")
        if p.name not in pages and GENERATOR_MARK in p.read_text(encoding="utf-8", errors="ignore")
    ]
    try:
        for name, html in pages.items():
            target = (out / name).resolve()
            if target.parent != root:  # page_names only yields [a-z0-9-]; belt and braces
                raise LastWordsError(f"refusing to write outside --out: {name}")
            target.write_text(html, encoding="utf-8", newline="\n")
        for p in stale:
            p.unlink()
    except OSError as e:
        raise LastWordsError(f"cannot write to --out {out_dir}: {e.strerror or e}") from None
    return out
