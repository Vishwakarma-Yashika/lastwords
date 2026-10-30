"""Throwaway git repositories for tests. No network, no real Ollama."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class GitRepo:
    def __init__(self, path: Path):
        self.path = path
        self._git("init", "-q", "-b", "main")
        self._git("config", "core.autocrlf", "false")

    def _git(self, *args: str, env: dict | None = None) -> str:
        return subprocess.run(
            ["git", "-C", str(self.path), *args],
            check=True, capture_output=True, encoding="utf-8",
            env={**os.environ, **(env or {})},
        ).stdout

    def commit(self, files: dict[str, str | bytes], message: str,
               author: str = "Ada Ghost <ada@example.com>",
               date: str = "2015-03-01T12:00:00+00:00") -> str:
        for name, content in files.items():
            target = self.path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8", newline="\n")
            self._git("add", "--", name)
        name, email = author[:-1].split(" <")
        env = {
            "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": date,
        }
        self._git("commit", "-q", "-m", message, env=env)
        return self._git("rev-parse", "HEAD").strip()


@pytest.fixture
def make_repo(tmp_path):
    def factory(name: str = "repo") -> GitRepo:
        path = tmp_path / name
        path.mkdir()
        return GitRepo(path)
    return factory


@pytest.fixture(autouse=True)
def no_sentry(monkeypatch):
    """Tests never talk to Sentry unless they install a capturing transport."""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    from lastwords import tracing
    monkeypatch.setattr(tracing, "ENABLED", False)


@pytest.fixture
def fake_ollama(monkeypatch):
    """Replace ollama.generate; records prompts and returns a scripted reply."""
    import ollama

    calls: list[dict] = []
    state = {"reply": "I remember."}

    def generate(model, prompt, **kwargs):
        calls.append({"model": model, "prompt": prompt})
        reply = state["reply"]
        if isinstance(reply, BaseException):
            raise reply
        return {"response": reply(prompt) if callable(reply) else reply,
                "prompt_eval_count": 11, "eval_count": 7}

    monkeypatch.setattr(ollama, "generate", generate)
    return type("FakeOllama", (), {"calls": calls, "state": state})
