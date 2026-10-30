# LastWords: audit and resolution log

This file has two parts:

1. **Resolution log** (below): what has changed since the audit, with evidence.
   Last updated 2026-10-30, after Phase 2.1.
2. **Original Phase 0 audit**: kept exactly as written, as historical record.
   Its findings describe the code *before* Phases 1–2.1. Where it disagrees with
   the resolution log, the resolution log is current.

---

## Resolution log

### Status of the original findings

| ID | Finding (Phase 0) | Status | What changed | Evidence |
|---|---|---|---|---|
| C1 | `ask` missed the line's own commit (6/45) | **Resolved** | `retrieve(..., blamed_sha=)` always puts the blamed commit first; the rest ranked by relevance, no duplicates | Same 45-line Bottle sample: **45/45**. `tests/test_retrieval.py` (9 tests) |
| C2 | Sentry sent nothing | **Resolved** | Each command runs in a transaction (`tracing.command`) with child spans | Capturing transport receives the transaction and spans. `tests/test_tracing.py` (5 tests). Not yet checked against a real Sentry project |
| — | *(new, found in Phase 1)* Sentry's default integrations would send git command lines (repo path, file names), `sys.argv` (the question) and the hostname | **Resolved** | `StdlibIntegration` and `ArgvIntegration` disabled; `server_name`, local variables and source context turned off | `test_private_text_never_leaves` fails if the fix is removed |
| C3 | Identities split / merged by name | **Partly resolved** | git `.mailmap` honoured (`%aN/%aE`); original identity kept per commit (`author_name`, `author_email`, `Author.aliases`) | `tests/test_history.py`. Bottle has no `.mailmap`, so "Thiago Avelino" / "Avelino" are still two ghosts. A mapping file merges them (shown on Bottle with a throwaway mailmap: 30 commits, 2014–2022) |
| C4 | Windows crash on redirected non-ASCII output | **Resolved** | `cli.utf8_output()` switches stdout/stderr to UTF-8 unless `PYTHONIOENCODING` is set | `tests/test_unicode.py` (3 tests, real subprocess pipes). Verified with PowerShell `>`, cmd.exe `>` and Git Bash pipes. A console on an OEM codepage was not available to test |
| C5 | Raw tracebacks for user errors | **Resolved** | `LastWordsError` → one line on stderr, exit 1; `ask` validates file and line before loading history; `--out` checked before slow work | `tests/test_errors.py` (20 tests) |
| C6 | Page-name collisions (`ghost.html`) | **Resolved** | `page_names()`: ASCII slug, suffix from first commit hash when empty, reserved (`index`, `con`…) or shared; never emails; no writes outside `--out` | `tests/test_ofrenda.py` (5 naming tests) |
| C7 | Line counts dominated by generated files | **Resolved** | Source and translation/generated lines counted separately; ghosts ranked by source lines | Independent `git blame --line-porcelain` recount matches for all 240 Bottle authors. Bottle: 13,894 source, 68,782 translation lines |
| C8 | `count_surviving_lines` not idempotent | **Resolved** | Counts reset before counting | `test_counts_are_the_same_when_computed_twice` |
| C9 | Substring matching in retrieval | **Resolved** | Whole-word matching (trailing plural `s` dropped) | `test_whole_word_matching_ignores_substrings` |
| C10 | `TRIVIAL` filter rejects `fix:` commits | **Open, by decision** | Unchanged, so the quoted commits in verified notes stay stable | — |
| C11 | Answers embellished | **Partly resolved** | Cited hashes not among the memories are removed and the user is told; other wording is not checked | `test_check_citations_*`, `test_ask_ghost_strips_invented_citation` |
| C12 | Hard limits | **Partly resolved** | Blamed commits older than the 5,000-commit window are loaded on their own (no `KeyError`); history load 51 s → 0.7 s on Bottle (one `git log --numstat`) | Loader output identical to the old one on all 1,999 Bottle commits. Templates still resolve outside the package; `ask` still allows active contributors |
| C13 | Prompt injection through commit messages | **Open** | Unchanged; output only reaches the user's terminal or escaped HTML | — |

### Other changes since the audit

- **Ofrenda notes are deterministic by default.** They're built from the real name,
  the exact commit subject and the blame counts, with no model call. The old
  model-written sentence is kept behind `--ai-notes` (experimental, validated,
  falls back to the template). The page footer says which mode produced the notes.
- **Repeatable builds.** Same repo and options give byte-identical HTML. A rebuild
  removes only pages carrying LastWords' `generator` meta tag.
- **`site/` regenerated** from Bottle. New top 6 by source lines: Oz N Tiram,
  Eric Wieser, Iuri de Silvio, Alex Collins, sma, Michael Käufl. The previous 7
  files are kept in `backups/site-phase1-2026-10-30/` (git-ignored, SHA-256 verified).
- **Release files:** `.gitignore`, `requirements.txt`, `requirements-dev.txt`,
  `LICENSE` (MIT), README rewritten, local git repository initialised (no commits,
  no remote).
- **Dependency security:** Jinja2 3.1.4 → 3.1.6, fixing CVE-2024-56201,
  CVE-2024-56326 and CVE-2025-27516. These weren't exploitable as LastWords used
  Jinja (fixed templates, autoescaped data), but they were in a release pin.
  `pip-audit -r requirements-dev.txt` reports no known vulnerabilities.

### Corrections to statements in the original audit

- Section A: there are now `requirements.txt`, `requirements-dev.txt`, `LICENSE`,
  `.gitignore`, a git repository and 68 tests. Jinja2 is 3.1.6.
- Section B: "Sentry when enabled: does not work" is no longer true (C2).
  `load_authors` takes about 0.7 s, not 43 s.
- Section E: Sentry payload contents are now restricted as described above.
  The `OLLAMA_HOST` risk is documented in the README but there is no runtime warning.
- Section J: the error commands now print one line and exit 1. `ofrenda` rebuilds
  `site/` deterministically, so running it no longer rewrites verified notes.
- Blockers 1–4 are resolved; blocker 5 (identity and line-count decisions) was
  settled by using git's `.mailmap` and counting generated lines separately.

### Test evidence (Phase 2.1)

- `python -m pytest -v` in `.venv` (Python 3.10.11, Jinja2 3.1.6): **68 passed**.
- `python -m compileall -q lastwords tests`: exit 0.
- CLI help lists `summon`, `ask`, `ofrenda`; each subcommand's help exits 0.
- Default `ofrenda` with Ollama unreachable (`OLLAMA_HOST=127.0.0.1:9`): exit 0,
  output byte-identical to `site/` (7 files).
- `ask` with Ollama unreachable: one-line error, exit 1.

### Remaining limitations

- Answers come from `gemma2:2b` on CPU; vague answers and embellishment still occur.
  The installed Ollama (0.24) cannot pull newer Gemma releases.
- Retrieval is keyword-based over commit subject lines; diffs aren't given to the model.
- Without a `.mailmap`, one person under two display names is two ghosts.
- Ghost selection depends on the current date.
- Developed and tested on Windows 11 only.
- Sentry hasn't been verified against a real project or its AI dashboard.

### Architectural constraints

- **Local inference only.** Generation goes to Ollama at `OLLAMA_HOST`; there is
  no cloud model path, by design.
- **Git is the source of truth.** History comes from one `git log --numstat`
  (newest 5,000 commits); line credit comes from `git blame` of every text file
  at HEAD, which is one git call per file (about 6 s on Bottle's 220 files).
- **Identity = mailmapped display name.** Email-only matches are not merged.
- **Not packaged.** There's no `pyproject.toml` or console entry point;
  `templates/` is found relative to the source tree, so the project runs from a
  checkout, not from an installed wheel.
- **sentry-sdk 2.66 sends `gen_ai.*` spans as separate span items** in the same
  trace, not inside the transaction; the tests check for that shape.

---

# Original Phase 0 audit (kept as written)

Date: 2026-10-30. Scope: inspection and read-only probes. No application code was changed.
Demo repo: Bottle (`demo-repos/bottle`, HEAD `aba0c1a`, 1,999 commits, 220 tracked files).

All numbers below come from commands that were actually run. The probe scripts live
outside the repo (session scratchpad) and only read from git and Ollama.

---

## A. Existing architecture

```
lastwords/                      (folder is NOT a git repository yet)
├── README.md
├── AUDIT.md                    (this report)
├── lastwords/
│   ├── __init__.py             empty
│   ├── cli.py                  argparse: summon | ask | ofrenda; calls tracing.init()
│   ├── history.py              GitPython: authors, commits, surviving lines, ghosts
│   ├── channel.py              blame a line, keyword retrieval, prompt, ollama.generate
│   ├── ofrenda.py              signature commit, remembrance note, Jinja2 site build
│   └── tracing.py              optional Sentry; no-op unless SENTRY_DSN is set
├── templates/                  base.html, index.html, ghost.html (inline CSS, no CDNs)
├── site/                       generated output: index + 6 ghost pages
└── tests/                      empty
```

Data flow:

```
git log ──► load_authors() ──► Author{commits}
git blame (every file at HEAD) ──► count_surviving_lines() ──► Author.surviving_lines
                                   find_ghosts(inactive_days) ──► ghosts
summon : ghosts ──► stdout
ask    : blame_line(file, line) ──► author ──► retrieve(question) ──► build_prompt ──► Gemma (Ollama) ──► stdout
ofrenda: ghosts ──► signature_commit + Gemma sentence (validated, else template) ──► Jinja2 ──► site/*.html
```

Environment observed:

| Component | Version |
|---|---|
| Python | 3.10.11 (Windows) |
| GitPython | 3.2.1 |
| Jinja2 | 3.1.4 |
| ollama (Python client) | 0.6.1 |
| sentry-sdk | 2.66.1 |
| pytest | 9.1.1 (installed, no tests) |
| Ollama server | 0.24.0 (too old for `gemma3`) |
| Model | `gemma2:2b` (1.6 GB) |

There is no `requirements.txt`, `pyproject.toml`, `LICENSE` or `.gitignore`, and no git metadata.

---

## B. Existing working features (verified)

| Feature | Result | Evidence |
|---|---|---|
| Contributor discovery (`summon`) | Works | 240 author keys, 224 ghosts at 3 years |
| Commit history extraction | Works, slow | `load_authors` takes **43.3 s** on 1,999 commits |
| Author grouping by name | Works as designed, with identity errors (see C3) | |
| Surviving-line calculation | Correct totals | credited 82,676 vs 82,664 lines at HEAD (0.01% gap); takes 6.4 s |
| Git blame for a line | Works | relative, backslash (`test\test_router.py`) and absolute paths all resolve |
| Commit retrieval | Works, but weak (see C1, C9) | |
| Ollama generation | Works locally | `gemma2:2b` on CPU |
| Commit citations in `ask` | Valid in 3 of 3 sampled answers | every cited hash was in the retrieved memories |
| "I don't remember" path | Works | off-topic question on an untouched file returns no memories and the model is not called |
| Ofrenda generation | Works | 6 pages + index; quotes verified verbatim; no emails or external URLs in output |
| HTML escaping | Safe | Jinja2 autoescape is on for `.html` templates |
| Sentry off by default | Works | `tracing.init()` returns False without `SENTRY_DSN` |
| Sentry when enabled | **Does not work** | see C2 |
| Code compiles | Yes | `python -m compileall lastwords` |

---

## C. Bugs and technical risks

Severity: **High** = breaks a headline feature or a prize category. **Medium** = wrong
output or a crash on realistic input. **Low** = robustness or polish.

**C1. High: `ask` usually does not remember the commit that wrote the line.**
Of 45 random lines blamed in `bottle.py`, `test/test_router.py` and `docs/tutorial.rst`,
the blamed commit was among the retrieved memories only **6 times out of 45**. Retrieval
ranks by keyword overlap and recency, and never forces in the commit that `blame_line`
already found. This is the core promise of `ask`. (`channel.py: retrieve`, `ask_ghost`)

**C2. High: Sentry tracing sends nothing as the CLI runs it.**
`tracing.span()` calls `sentry_sdk.start_span()`, but the CLI never opens a root
transaction. With a capturing transport, a bare span produced **0 envelopes**. Wrapping
the same span in `sentry_sdk.start_transaction()` produced 1 `transaction` envelope. As
built, the Sentry prize category has nothing to show. (`cli.py: main`, `tracing.py`)

**C3. Medium: contributor identities are split and wrongly merged.**
- **Split:** 9 emails appear under more than one name. For example "Thiago Avelino" (28
  commits, 2014–2017) and "Avelino" (4 commits, 2015–2022) are the same email but two
  ghosts. Thiago's ofrenda page shows a last-seen date in 2017 when they were active
  until 2022. Other splits: `花浅葱` / `Hanaasagi`, `Frédéric` / `Frederic Junod`,
  `user` / `Dime Mikhalchenko`, and `Eric L Frederich` / `Eric L. Frederich`.
- **Merge:** 9 names merge more than one email, which is mostly correct (Marcel Hellkamp
  has 5). Merging by name alone means two different people who share a name become
  one ghost.
- The standard fix is to honour `.mailmap`. Per the constraints, this needs your
  approval before any identity changes.

**C4. Medium: the CLI crashes on non-ASCII names when output is redirected or piped on Windows.**
`summon --top 250 > file` exits with `UnicodeEncodeError: 'charmap' codec`, because
Python writes cp1252 to pipes. It works under `python -X utf8`. Bottle has many
non-ASCII ghosts (`张酉夫`, `Роман Донченко`, `Çağatay Tengiz`…). An interactive
PowerShell console was not tested. (`cli.py`)

**C5. Medium: no error handling. Every failure is a raw traceback.**

| Input | Result |
|---|---|
| Path that is not a repo | `InvalidGitRepositoryError` traceback |
| `--file nope.py` | `GitCommandError ... exit code(128)` |
| `--line 0`, `-5`, `999999` | `ValueError: bottle.py has no line N` traceback |
| Missing model (`--model nope:1b`) | `ResponseError ... 404` |
| Ollama not running | `ConnectionError: Failed to connect to Ollama` |

`ask` also loads the whole history (43 s) **before** checking the file and line, so a
typo costs 43 s before the error appears.

**C6. Medium: ofrenda slug collisions overwrite pages silently.**
`slugify` strips non-Latin characters. Across all 224 ghosts, four names
(`张酉夫`, `花浅葱`, `Роман Донченко`, `Виталий`) all become `ghost.html`, and
`Eric L Frederich` / `Eric L. Frederich` collide too. With `--top` above 6, pages
would overwrite each other while the index still links to all of them. The current 6
pages are unaffected. (`ofrenda.py: slugify`)

**C7. Medium: "lines still alive" is dominated by generated files.**
Thiago Avelino's 28,941 lines, about 35% of the repo, come from `.po` translation
files under `docs/_locale/`, not hand-written code. The count is accurate as blame
output, but it reads as "they wrote 29k lines". Changing how lines are counted would
change the numbers in the six verified notes, so it needs a decision first.

**C8. Medium: `count_surviving_lines` is not idempotent.**
A second call doubles every count (Oz N Tiram: 100 → 200). No current command calls it
twice, but any future refactor that does will silently corrupt numbers.

**C9. Low: retrieval uses substring matching.**
The word "out" matches "R**out**e". Words are checked with `w in text`, not as whole
words, so short words create false matches. The stopword list is also very small.

**C10. Low: `signature_commit` rejects 571 meaningful commits.**
The `TRIVIAL` pattern drops every subject that starts with `fix` or `update`, including
conventional commits like `fix: etag handling in static_file()`. This only affects
which commit an ofrenda quotes. Changing it could change the six notes, so it's left
as is.

**C11. Low: answers are cited but slightly embellished.**
Citations were valid in 3 of 3 samples, but the model added colour not found in the
commits: Oz "remember[s] it being a challenge at first", and Eric mentions a
"user-friendly traceback". Nothing in `ask` checks the answer against its memories.
Three samples is too few to estimate a rate.

**C12. Low: hard limits and assumptions.**
- `load_authors(max_commits=5000)`: on larger repos, older authors are never loaded,
  and `cmd_ask` would raise `KeyError` at `authors[key]` when blame finds one of them.
  This doesn't happen on Bottle (1,999 commits).
- `TEMPLATES` resolves to `../templates` relative to the package. It works from source
  but would break if installed as a package.
- `ask` will happily channel an active contributor. For example, line 100 of
  `bottle.py` belongs to Marcel Hellkamp, active in September 2026. That's arguably fine,
  but it contradicts the "ghost" framing.

**C13. Low: commit messages are fed straight into the prompt.**
Commit text is untrusted input. A crafted commit message could steer the ghost's
answer (prompt injection). The impact is limited because output only goes to the
user's own terminal or static HTML (escaped).

**Known issues in the six verified notes (reported only, not changed):**
- `iuri-de-silvio.html` has broken punctuation from the model: `Iuri de Silvio," "Stressing…`
- `thiago-avelino.html`: the 28,941 figure is mostly translation files (C7), and the
  dates reflect only one of their two identities (C3).

---

## D. Missing features (against the agreed plan)

- Git repository, `LICENSE` (needed to call it open source), `.gitignore` (`site/`, `__pycache__/`)
- `requirements.txt` with pinned versions, or a `pyproject.toml` with a `lastwords` entry point
- Tests (the `tests/` folder is empty)
- Friendly error messages (C5)
- A working Sentry trace (C2)
- Render deploy of `site/` and the `.tech` domain
- Demo GIF or screenshots
- DEV post
- Optional: `.mailmap` support, excluding generated files from line counts, a newer Gemma after updating Ollama

---

## E. Security and privacy

| Area | Finding |
|---|---|
| Source code leaving the machine | Only to Ollama at `OLLAMA_HOST`. Default is `127.0.0.1:11434`, and the server is bound to loopback (confirmed by the bind error). **The client honours `OLLAMA_HOST`** (confirmed: setting it redirected the call). If someone points it at a remote host, commit text leaves the machine with no warning. |
| Cloud AI APIs | None. The only network-capable imports are `ollama` and `sentry_sdk`. |
| Sentry | Off unless `SENTRY_DSN` is set. `send_default_pii=False`. When fixed (C2), spans would carry the ghost's **name**, commit short hashes and the model name. No prompts, source code or emails. Names are personal data, so the README should say so. |
| Generated site | No email addresses, no external URLs, fonts or scripts. It does publish names and commit messages. That's fine for a public repo like Bottle, but **running `ofrenda` on a private repo and deploying it would leak internal history**. The README should warn about this. |
| XSS | Commit messages are autoescaped by Jinja2. |
| Framing of real people | The footer explains that "ghost" means inactive, not deceased, and the notes avoid death language. Splitting and misdating Thiago Avelino (C3) is the main accuracy risk to a real person. |

---

## F. Recommended improvements, ranked

| # | Priority | Change | Fixes | Changes the six notes? |
|---|---|---|---|---|
| 1 | P0 | Always put the blamed commit first in `ask`'s memories | C1 | No |
| 2 | P0 | Wrap each CLI command in a Sentry transaction; use `gen_ai.*` span attributes | C2 | No |
| 3 | P0 | Force UTF-8 stdout in `cli.main()` (`sys.stdout.reconfigure(encoding="utf-8")`) | C4 | No |
| 4 | P0 | Catch repo, path, line and Ollama errors with one-line messages and a non-zero exit; validate the file and line **before** loading history | C5 | No |
| 5 | P1 | Unique slugs (transliterate, or fall back to a hash of the author key) | C6 | No (current 6 slugs are unchanged) |
| 6 | P1 | Add `requirements.txt`, `LICENSE`, `.gitignore`, `git init` | D | No |
| 7 | P1 | Minimum test suite (see below) | D | No |
| 8 | P1 | Speed up `load_authors` with a single `git log --numstat` instead of `commit.stats` per commit | 43 s load | No |
| 9 | P2 | Honour `.mailmap` (**needs approval**) | C3 | Yes (Thiago's dates and counts) |
| 10 | P2 | Exclude generated files (`*.po`, lockfiles) from line counts (**needs approval**) | C7 | Yes (Thiago's count) |
| 11 | P2 | Make `count_surviving_lines` reset before counting | C8 | No |
| 12 | P2 | Whole-word matching in retrieval | C9 | No |
| 13 | P3 | Warn when `OLLAMA_HOST` is not loopback; privacy notes in README | E | No |
| 14 | P3 | Check that `ask` cites only retrieved hashes | C11 | No |

**Minimum tests needed** (none exist; all can run offline against a tiny temp repo built
in a fixture, with Ollama mocked):
1. `find_ghosts` respects the inactivity cutoff.
2. `author_key` merges the same name across emails.
3. `count_surviving_lines` totals equal the line count at HEAD.
4. `blame_line` returns the right author; raises on line 0 and past the end.
5. `retrieve` returns nothing for an off-topic question on an untouched file.
6. `remembrance` falls back to the template when the model drops the quote or the name.
7. `slugify` produces unique slugs for non-Latin names (fails today; documents C6).
8. `tracing.init()` is a no-op without `SENTRY_DSN`.
9. Ofrenda HTML escapes `<script>` in a commit message.

---

## G. Proposed roadmap

1. **Phase 1, correctness (P0):** items 1–4. Small, local edits to `channel.py`,
   `cli.py` and `tracing.py`. Re-run `ask` on the same 45 lines and expect 45/45.
2. **Phase 2, project hygiene (P1):** items 5–8 plus the test suite; `git init`; first
   commit.
3. **Phase 3, decisions (P2):** decide on `.mailmap` and generated-file exclusion. If
   approved, regenerate only Thiago's page, or all six with your sign-off.
4. **Phase 4, ship:** Render static deploy of `site/`, `.tech` domain, verify Sentry in the
   dashboard, demo GIF, DEV post.

---

## H. Files that need modification

| File | Change | Item |
|---|---|---|
| `lastwords/channel.py` | Include the blamed commit in memories; whole-word matching; optional citation check | 1, 12, 14 |
| `lastwords/cli.py` | UTF-8 stdout, error handling, validate before loading, root transaction per command | 2, 3, 4 |
| `lastwords/tracing.py` | Helper to start a transaction; `gen_ai` attributes | 2 |
| `lastwords/ofrenda.py` | Unique slugs | 5 |
| `lastwords/history.py` | Single-pass `git log --numstat`; reset counts; `.mailmap` and exclusions only if approved | 8, 9, 10, 11 |
| `README.md` | Privacy notes, Windows note, install from `requirements.txt` | 6, 13 |
| new: `requirements.txt`, `LICENSE`, `.gitignore`, `tests/test_*.py` | | 6, 7 |

You asked that `history.py`, `channel.py` and `cli.py` be treated as working.
Items 1–4 still need small additive edits in `channel.py` and `cli.py`. I'd make them
only with your go-ahead.

## I. Files that should not be changed

- `site/*.html`: the six verified notes and the index. Regenerate only with explicit approval.
- `templates/*.html`: working and safe; no changes needed for Phases 1–2.
- `lastwords/__init__.py`.
- The identity logic in `history.py` (`author_key`), until item 9 is approved.
- `demo-repos/bottle`: third-party clone, read-only.

---

## J. Commands to reproduce current behaviour

Run from `New folder/lastwords`. Ollama must be running with `gemma2:2b`.

```powershell
# environment
python --version; ollama --version; ollama list
pip show gitpython jinja2 ollama sentry-sdk

# working paths
python -m lastwords.cli summon ..\demo-repos\bottle --top 5
python -m lastwords.cli ask ..\demo-repos\bottle "why does this handle unprintable errors?" --file bottle.py --line 937
python -m lastwords.cli ofrenda ..\demo-repos\bottle --top 6 --out site   # overwrites site/, so don't run it if you want to keep the six notes

# C4: encoding crash when redirected (and the workaround)
python -m lastwords.cli summon ..\demo-repos\bottle --top 250 > out.txt
python -X utf8 -m lastwords.cli summon ..\demo-repos\bottle --top 250 > out.txt

# C5: raw tracebacks
python -m lastwords.cli summon C:\Windows
python -m lastwords.cli ask ..\demo-repos\bottle "x" --file nope.py --line 1
python -m lastwords.cli ask ..\demo-repos\bottle "x" --file bottle.py --line 0
python -m lastwords.cli ask ..\demo-repos\bottle "x" --file bottle.py --line 937 --model nope:1b

# tests
python -m pytest tests -q        # "no tests ran"
python -m compileall -q lastwords
```

---

## Blockers for the next phase

1. **Not a git repository and no LICENSE.** You can't publish it as open source yet.
2. **Sentry sends nothing (C2).** This blocks the Sentry prize category until fixed.
3. **`ask` misses the line's own commit 39 times out of 45 (C1).** This is the headline demo.
4. **Windows encoding crash when redirecting output (C4).** It will bite while recording logs or the demo.
5. **Two decisions only you can make:** `.mailmap` identity merging (C3) and how to count
   generated files (C7). Both would change Thiago Avelino's verified note.
