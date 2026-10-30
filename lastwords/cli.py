"""lastwords summon | ask | ofrenda"""
from __future__ import annotations

import argparse
import os
import sys

from git.exc import GitCommandError, GitCommandNotFound

from . import tracing
from .channel import DEFAULT_MODEL, ask_ghost, blame_line, resolve_file
from .errors import LastWordsError
from .history import (
    count_surviving_lines, find_ghosts, load_authors, load_commit, open_repo, owner_of,
)
from .ofrenda import build_site, prepare_output_dir


def utf8_output() -> None:
    """Write UTF-8 even when Windows redirects stdout/stderr to a cp1252 pipe or file.

    An explicit PYTHONIOENCODING wins. Interactive consoles are already UTF-8.
    """
    if os.environ.get("PYTHONIOENCODING"):
        return
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").replace("-", "").lower()
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def lines_label(author) -> str:
    label = f"{author.surviving_lines} lines still alive"
    if author.resource_lines:
        label += f" (+{author.resource_lines} in translation/generated files)"
    return label


def cmd_summon(args: argparse.Namespace) -> None:
    with tracing.span("lastwords.history", "load history"):
        authors = load_authors(args.repo)
    with tracing.span("lastwords.blame", "count surviving lines"):
        count_surviving_lines(args.repo, authors)
    ghosts = find_ghosts(authors, args.inactive_days)
    print(f"{len(ghosts)} ghosts walk this repo (inactive > {args.inactive_days} days)\n")
    for g in ghosts[: args.top]:
        last = g.last_commit
        print(f"* {g.name}  |  {lines_label(g)}  |  last seen {last.when.date()}")
        print(f"    last words: \"{last.message.splitlines()[0][:80]}\"")


def cmd_ask(args: argparse.Namespace) -> None:
    # check the file and line first: blame is quick, loading history is not
    with tracing.span("lastwords.blame", "blame line"):
        path = resolve_file(args.repo, args.file)
        _, sha = blame_line(args.repo, path, args.line)
    with tracing.span("lastwords.history", "load history"):
        authors = load_authors(args.repo)
    ghost = owner_of(authors, sha)
    if ghost is None:  # older than the commits load_authors reads
        key, lone = load_commit(args.repo, sha)
        ghost = authors.setdefault(key, lone)
        if ghost is not lone:
            ghost.commits.append(lone.commits[0])
    print(f"Line {args.line} of {path} was written by {ghost.name} ({sha[:7]}). Summoning...\n")
    answer, memories = ask_ghost(ghost, args.question, args.model, path, blamed_sha=sha)
    print(f"{ghost.name}: {answer}\n")
    for m in sorted(memories, key=lambda m: m.when):
        mark = "  <- wrote this line" if m.sha == sha else ""
        print(f"  [{m.sha[:7]}] {m.when.date()}  {m.message.splitlines()[0][:70]}{mark}")


def cmd_ofrenda(args: argparse.Namespace) -> None:
    open_repo(args.repo)
    prepare_output_dir(args.out)  # fail before the slow part, not after it
    with tracing.span("lastwords.history", "load history"):
        authors = load_authors(args.repo)
    with tracing.span("lastwords.blame", "count surviving lines"):
        count_surviving_lines(args.repo, authors)
    ghosts = find_ghosts(authors, args.inactive_days)[: args.top]
    name = args.repo.rstrip("/\\").replace("\\", "/").split("/")[-1]
    out = build_site(ghosts, name, args.out, args.model, ai_notes=args.ai_notes)
    print(f"Lit {len(ghosts)} candles. Open {out / 'index.html'}")


def main(argv: list[str] | None = None) -> int:
    utf8_output()
    parser = argparse.ArgumentParser(prog="lastwords")
    sub = parser.add_subparsers(required=True)

    s = sub.add_parser("summon", help="list the ghosts of a repo")
    s.add_argument("repo")
    s.add_argument("--inactive-days", type=int, default=365 * 3)
    s.add_argument("--top", type=int, default=10)
    s.set_defaults(func=cmd_summon, command="summon")

    a = sub.add_parser("ask", help="ask the ghost who wrote a line")
    a.add_argument("repo")
    a.add_argument("question")
    a.add_argument("--file", required=True)
    a.add_argument("--line", type=int, required=True)
    a.add_argument("--model", default=DEFAULT_MODEL)
    a.set_defaults(func=cmd_ask, command="ask")

    o = sub.add_parser("ofrenda", help="build a static remembrance site")
    o.add_argument("repo")
    o.add_argument("--out", default="site")
    o.add_argument("--top", type=int, default=6)
    o.add_argument("--inactive-days", type=int, default=365 * 3)
    o.add_argument("--model", default=DEFAULT_MODEL, help="model for --ai-notes")
    o.add_argument(
        "--ai-notes", action="store_true",
        help="experimental: let the local model write each thank-you sentence",
    )
    o.set_defaults(func=cmd_ofrenda, command="ofrenda")

    args = parser.parse_args(argv)
    tracing.init()
    try:
        with tracing.command(args.command):
            args.func(args)
    except LastWordsError as e:
        print(f"lastwords: error: {e}", file=sys.stderr)
        return 1
    except GitCommandNotFound:
        print("lastwords: error: git is not installed or not on PATH", file=sys.stderr)
        return 1
    except GitCommandError as e:
        print(f"lastwords: error: git failed: {(e.stderr or '').strip() or e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
