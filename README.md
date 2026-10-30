# LastWords

Talk to the people who left your codebase.

LastWords reads a git repository's history and finds its "ghosts": contributors
who haven't committed in a long time. Point it at a line of code and it summons
the person who wrote it. A local open-weight model (Gemma, running in Ollama)
answers in their voice, using only their real commits, and cites the commit
hashes. The answer is labelled for what it is: a model's reading of their
commits, not their words. LastWords can also build a Día de los Muertos ofrenda:
a small static website that thanks each person for the work that still runs.

A "ghost" only means someone who hasn't committed in a long time. LastWords
knows nothing else about them, and the ofrenda never describes anyone as dead.

The model runs on your machine. Your code and history are not sent to a cloud AI
service. Optional Sentry tracing, if you turn it on, sends timings and token
counts only (see [Privacy](#privacy)).

## Features

- **`summon`** lists a repo's ghosts: how many of their lines are still alive at
  HEAD (source code and translation/generated files counted separately), when
  they were last seen, and their last commit message.
- **`ask`** blames one line, finds who wrote it, and lets them answer a question.
  The commit that wrote the line is always among the ghost's memories. Any cited
  hash that isn't one of those memories is removed from the answer, and you're told.
- **`ofrenda`** builds a static site with one page per ghost. Each note quotes a
  real commit message word for word, and the line counts come straight from
  `git blame`. Builds are deterministic: same repo and options, identical HTML.
  The site credits the tradition it borrows from and tells anyone listed how to
  ask to be removed.
- Clear one-line errors (bad path, missing line, Ollama not running, model not
  pulled), with exit code 1.
- Optional, privacy-limited Sentry tracing.

## How it works

```
git log --numstat (mailmap applied) ─► authors and their commits
git blame at HEAD, every text file   ─► lines still alive per author
                                         (source vs translation/generated)
inactive longer than --inactive-days ─► ghosts, ranked by source lines

ask:     blame the line ─► that commit + the ghost's most relevant commits
                        ─► prompt ─► Gemma in Ollama (local) ─► citation check
ofrenda: ghost data ─► template note ─► Jinja2 (autoescaped) ─► site/*.html
```

| Module | Job |
|---|---|
| `lastwords/history.py` | Read history, apply `.mailmap`, count surviving lines, find ghosts |
| `lastwords/channel.py` | Validate file and line, blame, retrieve memories, call Ollama, check citations |
| `lastwords/ofrenda.py` | Notes, page names, site build |
| `lastwords/tracing.py` | Optional Sentry tracing |
| `lastwords/cli.py` | The three commands and error reporting |
| `templates/` | Jinja2 templates for the site |

## Prerequisites

- Python 3.10 or newer (tested on 3.10.11)
- Git 2.31 or newer, for `git log --diff-merges` (tested on 2.47)
- [Ollama](https://ollama.com/download), only for `ask` and for `ofrenda --ai-notes`

`summon` and the default `ofrenda` don't need the Ollama app to be installed or running.

## Installation

### Windows (PowerShell)

```powershell
git clone <this repository> lastwords
cd lastwords
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then run commands with `.venv\Scripts\python.exe -m lastwords.cli ...`. To type
plain `python`, activate the environment with `.venv\Scripts\Activate.ps1`.
If PowerShell refuses ("running scripts is disabled"), run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or keep using the
full `.venv\Scripts\python.exe` path.

### Linux / macOS

```bash
git clone <this repository> lastwords
cd lastwords
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Ollama and Gemma

Ollama is a separate application, not a Python package, so `pip` doesn't install it.

1. Install Ollama from https://ollama.com/download and start it. If the server
   isn't running, `ollama serve` starts it.
2. Pull the model LastWords uses by default:

   ```
   ollama pull gemma2:2b
   ```

   It's about 1.6 GB and runs on a CPU. `gemma2:2b` is the only model LastWords
   has been tested with. Pass `--model` to try another one.

Gemma 2 is an open-weight model, not an open-source one. Google distributes its
weights under the [Gemma Terms of Use](https://ai.google.dev/gemma/terms) and the
[Gemma Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy).
LastWords doesn't include or redistribute them; you download them yourself with
`ollama pull`, and using the model means accepting those terms.

Ollama can also run cloud-hosted models. LastWords only ever asks for the local
`gemma2:2b` tag (or whatever you pass to `--model`). To make sure nothing can
reach Ollama's cloud, start Ollama with `OLLAMA_NO_CLOUD=1` set.

## Usage

```
python -m lastwords.cli summon  path/to/repo [--inactive-days 1095] [--top 10]
python -m lastwords.cli ask     path/to/repo "why is this like this?" --file app.py --line 120 [--model gemma2:2b]
python -m lastwords.cli ofrenda path/to/repo [--top 6] [--out site] [--inactive-days 1095] [--opt-out-url URL] [--ai-notes [--model gemma2:2b]]
```

`python -m lastwords.cli --help` and `python -m lastwords.cli <command> --help`
list every option.

`--file` is relative to the repository root. Windows-style (`pkg\mod.py`) and
absolute paths inside the repo also work.

Example, using the [Bottle](https://github.com/bottlepy/bottle) web framework
(the model's wording differs between runs):

```
$ python -m lastwords.cli ask ../bottle "why does this handle unprintable errors?" --file bottle.py --line 937
Line 937 of bottle.py was written by Eric Wieser (06f97c7). Summoning...

Eric Wieser, as gemma2:2b reads their commits: I remember...the headaches of unreconciled lines, that were hard to understand. The "unprintable error" thing...that felt like a solution. A kind of safeguard against those cryptic messages.

  [8a5bfe2] 2014-12-27  Prevent syntax errors when line-wrapping comprehensions
  [5732506] 2014-12-30  Remove repeated slicing when finding python markers
  [d0bae1d] 2014-12-30  Use the `pos` argument of re.search.
  [f65e34b] 2016-09-21  Fix tracebacks that would contain <string> to contain the template pat
  [06f97c7] 2016-09-21  Provide a name to default_error_handler  <- wrote this line
  [83cfe03] 2016-09-21  Handle unprintable errors

This is a local model's reading of Eric Wieser's commits, not their own words.
```

That run took about 14 seconds on a CPU-only Windows laptop (Intel Iris Xe, no GPU).

### The ofrenda website

```
python -m lastwords.cli ofrenda path/to/repo --top 6 --out site
```

This writes `site/index.html` and one page per ghost. Each note looks like:

> Thank you, Eric Wieser, for “Prevent syntax errors when line-wrapping
> comprehensions”. 74 lines of their source code still run in bottle today.

Page names are ASCII and unique: `michael-kaufl.html`. Names with no Latin letters,
reserved names (`index`, `con`…), and two people whose names produce the same page
name get a suffix from their first commit hash, for example `ghost-1a2b3c4d.html`.
Email addresses are never used.

The index page ends with a short note on what an ofrenda is: Día de los Muertos
is an Indigenous Mexican tradition, recognised by UNESCO in 2008, and the page
borrows only its gratitude. It mourns no one and is not a Halloween project. The
note also tells anyone listed how to ask to be removed. Pass `--opt-out-url` (an
`https://` or `mailto:` link) to give them a direct link; without it the page
asks them to contact whoever published it. If someone asks, remove them.

Rebuilding into the same folder removes pages that LastWords itself wrote earlier
and no longer needs. Other files in the folder are left alone.

`--ai-notes` (experimental) lets the local model write each thank-you sentence.
If the model's sentence drops the person's name or the exact commit message, the
template sentence is used instead. The line counts are always written by code.

The `site/` folder in this repository was generated from Bottle's public history
(MIT License, © Marcel Hellkamp) with
`--opt-out-url https://github.com/Vishwakarma-Yashika/lastwords/issues`. The names
and commit messages on it belong to Bottle's contributors. Without a `.mailmap`,
Bottle has 240 author identities, and 224 of them have not committed in over
three years. Those are identities, not people: one person can have two.

## Who counts as whom

Identities follow git's standard `.mailmap`. Add one to the repository, or point
`git config mailmap.file` at one, to merge a person's old names and emails. Without
a mapping, commits are grouped by display name, so one name under several emails
is one ghost.

## Lines still alive

`git blame` at HEAD credits every line to its author. Lines in translation,
generated and lock files (`*.po`, `*.pot`, `*.mo`, `*.min.js`, `*.min.css`, `*.map`,
common lock files, and anything marked `linguist-generated` in `.gitattributes`)
are counted separately and shown next to the source count. Ghosts are ranked by
source lines. Binary files have no lines and aren't counted.

In Bottle, for example, 68,782 of the 82,676 lines still at HEAD are translation files.

## Privacy

- The model runs in Ollama. LastWords sends prompts (commit messages and your
  question) to whatever `OLLAMA_HOST` points at, by default `127.0.0.1:11434` on
  this machine. If you point it at another computer, your history goes there.
- The ofrenda site contains contributor names and commit messages. Don't publish
  one built from a private repository.
- Nothing else leaves your machine unless you turn on Sentry.
- The people `ask` speaks for never agreed to it. Their commits are public (or
  your company's), but the answer is a guess about what they meant, so LastWords
  labels every answer as a model's reading of their commits, not their words.
  Don't quote it as something they said.

## Sentry tracing (opt-in)

Tracing is off unless the `SENTRY_DSN` environment variable is set. **When it is
set, telemetry is sent over the internet to the Sentry server in that DSN.**

Each command becomes one transaction with spans for blame and history loading.
`ask` follows Sentry's
[AI agent conventions](https://docs.sentry.io/platforms/python/agent-tracing/manual-instrumentation/),
so it shows up in Sentry's AI agent views:

```
lastwords ask                              (transaction)
├─ blame line / load history
└─ invoke_agent LastWords                  gen_ai.invoke_agent
   ├─ execute_tool retrieve_memories       gen_ai.execute_tool  memories found, blamed commit included
   └─ chat gemma2:2b                       gen_ai.chat          provider ollama, model, input/output tokens
```

The data is command names, timings, counts, the model name and token counts.
Because the model runs locally, the metered cost of each call is $0.

It never includes your questions, the ghost's answers, commit messages, file
contents, source code, file or folder paths, command-line arguments, local
variables, contributor names or emails, or this computer's hostname. The test
suite captures everything the Sentry client would send for an `ask` run and
checks that none of these appear in it.

An invalid DSN prints a warning and LastWords runs without tracing.

## Windows notes

Output is written as UTF-8, so names like 张酉夫 survive `>` and `|` without
`python -X utf8`. Set `PYTHONIOENCODING` if you need a different encoding.

## Known limitations

- Retrieval is whole-word keyword matching, not semantic search.
- A 2B model sometimes answers vaguely or adds colour that isn't in the commits.
  Citations are checked; the rest of the wording is not.
- Without a `.mailmap`, one person under two display names is two ghosts. In
  Bottle, "Thiago Avelino" and "Avelino" are an example.
- Only the newest 5,000 commits are read for history. Blame still finds older
  authors, but their other commits aren't remembered.
- Page names for people without Latin letters are hash-based, not transliterated.
- Who counts as a ghost depends on today's date, so a rebuild on a later day can
  select different people.
- Developed and tested on Windows 11 only. The Linux/macOS steps above are the
  standard ones but haven't been run.

## Related work

LastWords builds on well-known ideas, and these tools do parts of it well:

- [git-fame](https://github.com/casperdcl/git-fame) ranks authors by surviving
  `git blame` lines and honours `.mailmap`.
- [git-of-theseus](https://github.com/erikbern/git-of-theseus) plots how much of
  each author's and each year's code survives over time.
- [CodeScene](https://codescene.com/)'s offboarding simulator shows the code
  owned by developers who have left a team.
- [git-why](https://pypi.org/project/git-why/) explains blamed lines with an LLM,
  including through Ollama.

What LastWords adds is the combination: answers limited to the blamed author's
own commits with the writing commit always included, invented commit hashes
removed, inactive contributors found automatically, translation lines counted
apart from source, and a thank-you site written by code rather than a model.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest tests
```

The tests build throwaway git repositories and mock Ollama and Sentry. They need
git but no network and no Ollama.

## License

LastWords' code, templates and tests are released under the [MIT License](LICENSE).

Dependencies are installed from PyPI, not bundled, and keep their own licenses:
GitPython, Jinja2 and httpx are BSD-3-Clause; ollama (Python client) and
sentry-sdk are MIT.

The example site in `site/` is generated from the public history of
[Bottle](https://github.com/bottlepy/bottle), Copyright (c) 2009-2025 Marcel
Hellkamp, MIT License. Contributor names and quoted commit messages come from
that history. Gemma model weights are not part of this project (see
[Gemma Terms of Use](https://ai.google.dev/gemma/terms)).
