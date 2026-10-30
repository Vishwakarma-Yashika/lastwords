"""Fix 2: transactions and spans reach Sentry, and private text never does."""
import socket

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from lastwords import tracing
from lastwords.cli import main

QUESTION = "SECRET-QUESTION why is this here?"
COMMIT_MESSAGE = "SECRET-COMMIT-MESSAGE add the thing"
FILE_CONTENT = "SECRET_FILE_CONTENT = 42"


class Capture(Transport):
    def __init__(self):
        super().__init__()
        self.envelopes = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)

    def items(self):
        return [item for env in self.envelopes for item in env.items]

    def raw(self) -> bytes:
        return b"".join(env.serialize() for env in self.envelopes)


@pytest.fixture
def sentry(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    capture = Capture()
    real_init = tracing.init

    def init_with_capture():
        enabled = real_init()
        sentry_sdk.get_client().transport = capture
        return enabled

    monkeypatch.setattr(tracing, "init", init_with_capture)
    yield capture
    sentry_sdk.init()  # back to a disabled client
    tracing.ENABLED = False


def test_tracing_off_without_dsn():
    assert tracing.init() is False
    with tracing.command("ask") as tx, tracing.span("x", "y") as sp:
        assert tx is None and sp is None


def test_invalid_dsn_warns_and_continues(monkeypatch, capsys):
    monkeypatch.setenv("SENTRY_DSN", "not a dsn")
    assert tracing.init() is False
    assert "tracing is off" in capsys.readouterr().err


def test_ask_sends_transaction_with_child_spans(make_repo, fake_ollama, sentry):
    repo = make_repo()
    repo.commit({"app.py": FILE_CONTENT + "\n"}, COMMIT_MESSAGE)
    fake_ollama.state["reply"] = "I remember."

    assert main(["ask", str(repo.path), QUESTION, "--file", "app.py", "--line", "1", "--model", "m"]) == 0
    sentry_sdk.flush()

    transactions = [i.payload.json for i in sentry.items() if i.type == "transaction"]
    assert len(transactions) == 1
    tx = transactions[0]
    assert tx["transaction"] == "lastwords ask"
    ops = {s["op"] for s in tx["spans"]}
    assert {"lastwords.blame", "lastwords.history"} <= ops

    # sentry-sdk 2.66 sends gen_ai.* spans as separate v2 span items in the same trace
    span_items = [s for i in sentry.items() if i.type == "span" for s in i.payload.json["items"]]
    by_op = {s["attributes"]["sentry.op"]["value"]: s for s in span_items}
    agent, tool, chat = by_op["gen_ai.invoke_agent"], by_op["gen_ai.execute_tool"], by_op["gen_ai.chat"]
    root = tx["contexts"]["trace"]
    assert {agent["trace_id"], tool["trace_id"], chat["trace_id"]} == {root["trace_id"]}
    assert agent["parent_span_id"] == root["span_id"]
    assert tool["parent_span_id"] == chat["parent_span_id"] == agent["span_id"]

    def attr(span, key):
        return span["attributes"][key]["value"]

    # the names and attributes Sentry's AI agent views expect
    assert agent["name"] == "invoke_agent LastWords"
    assert attr(agent, "gen_ai.operation.name") == "invoke_agent"
    assert attr(agent, "gen_ai.agent.name") == "LastWords"
    assert tool["name"] == "execute_tool retrieve_memories"
    assert attr(tool, "gen_ai.tool.name") == "retrieve_memories"
    assert attr(tool, "memories.blamed_included") is True
    assert chat["name"] == "chat m"
    assert attr(chat, "gen_ai.operation.name") == "chat"
    assert attr(chat, "gen_ai.provider.name") == "ollama"
    assert attr(chat, "gen_ai.request.model") == "m"
    assert attr(chat, "gen_ai.response.model") == "m"
    assert attr(chat, "gen_ai.usage.input_tokens") == 11
    assert attr(chat, "gen_ai.usage.output_tokens") == 7


def test_private_text_never_leaves(make_repo, fake_ollama, sentry):
    repo = make_repo()
    repo.commit({"app.py": FILE_CONTENT + "\n"}, COMMIT_MESSAGE)
    fake_ollama.state["reply"] = "SECRET-ANSWER from the ghost"

    main(["ask", str(repo.path), QUESTION, "--file", "app.py", "--line", "1", "--model", "m"])
    sentry_sdk.flush()

    raw = sentry.raw()
    assert raw, "expected at least one envelope"
    hostname = socket.gethostname().encode()
    # path segments, not the whole path: JSON escapes Windows backslashes
    folder = repo.path.parent.name.encode()
    for secret in [b"SECRET-QUESTION", b"SECRET-COMMIT-MESSAGE", b"SECRET_FILE_CONTENT",
                   b"SECRET-ANSWER", b"Ada Ghost", b"ada@example.com", b"sys.argv",
                   b"app.py", folder, hostname]:
        assert secret not in raw, secret


def test_failed_command_still_sends_its_transaction(make_repo, sentry, capsys):
    repo = make_repo()
    repo.commit({"app.py": "a\n"}, "init")
    assert main(["ask", str(repo.path), "q", "--file", "app.py", "--line", "9"]) == 1
    sentry_sdk.flush()
    transactions = [i.payload.json for i in sentry.items() if i.type == "transaction"]
    assert [t["transaction"] for t in transactions] == ["lastwords ask"]
    assert "Traceback" not in capsys.readouterr().err
