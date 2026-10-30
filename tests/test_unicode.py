"""Fix 3: non-ASCII names survive redirected output without -X utf8."""
import os
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the CLI with stdout/stderr as pipes, the way `> file` or `|` does."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env.pop("SENTRY_DSN", None)
    return subprocess.run(
        [sys.executable, "-m", "lastwords.cli", *args],
        cwd=PROJECT, env=env, capture_output=True,
    )


def test_redirected_stdout_keeps_non_ascii_names(make_repo):
    repo = make_repo()
    repo.commit({"a.py": "a\n"}, "translate the docs", author="张酉夫 <z@example.com>")
    repo.commit({"b.py": "b\n"}, "Привет", author="Роман Донченко <r@example.com>")
    repo.commit({"c.py": "c\n"}, "café fix", author="Çağatay Tengiz <c@example.com>")

    result = run_cli("summon", str(repo.path), "--inactive-days", "30")

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    out = result.stdout.decode("utf-8")  # strict: fails on mojibake or '?' bytes
    for name in ["张酉夫", "Роман Донченко", "Çağatay Tengiz"]:
        assert name in out
    assert "Привет" in out and "café fix" in out


def test_redirected_stderr_keeps_non_ascii_paths(tmp_path):
    missing = tmp_path / "幽霊の倉庫"
    result = run_cli("summon", str(missing))
    assert result.returncode == 1
    err = result.stderr.decode("utf-8")
    assert "幽霊の倉庫" in err and "no such folder" in err
    assert "Traceback" not in err


def test_explicit_pythonioencoding_is_respected(make_repo):
    repo = make_repo()
    repo.commit({"a.py": "a\n"}, "x", author="Zoë <z@example.com>")
    env = {**os.environ, "PYTHONIOENCODING": "utf-16"}
    env.pop("SENTRY_DSN", None)
    result = subprocess.run(
        [sys.executable, "-m", "lastwords.cli", "summon", str(repo.path), "--inactive-days", "30"],
        cwd=PROJECT, env=env, capture_output=True,
    )
    assert result.returncode == 0
    assert "Zoë" in result.stdout.decode("utf-16")
