"""Optional Sentry tracing. Does nothing unless SENTRY_DSN is set.

When enabled, telemetry leaves this machine for the Sentry server in the DSN.
Only command names, timings, counts, model names and short commit hashes are
recorded. Questions, commit messages, file contents, source code, command-line
arguments and local variables are never attached.
"""
from __future__ import annotations

import contextlib
import os
import sys

import sentry_sdk
from sentry_sdk.integrations.argv import ArgvIntegration
from sentry_sdk.integrations.stdlib import StdlibIntegration
from sentry_sdk.utils import BadDsn

ENABLED = False


def init() -> bool:
    """Start Sentry if a DSN is configured. Nothing leaves the machine otherwise."""
    global ENABLED
    ENABLED = False
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    try:
        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=1.0,
            send_default_pii=False,
            include_local_variables=False,  # frames would hold prompts and questions
            include_source_context=False,
            server_name="lastwords-cli",  # instead of this computer's hostname
            disabled_integrations=[
                ArgvIntegration(),  # argv contains the question
                StdlibIntegration(),  # subprocess spans hold git command lines with repo paths
            ],
        )
    except BadDsn:
        print("lastwords: warning: SENTRY_DSN is not a valid DSN; tracing is off", file=sys.stderr)
        return False
    ENABLED = True
    return True


@contextlib.contextmanager
def command(name: str):
    """Run one CLI command inside a Sentry transaction so its spans are sent."""
    if not ENABLED:
        yield None
        return
    with sentry_sdk.start_transaction(op="cli.command", name=f"lastwords {name}") as tx:
        yield tx


@contextlib.contextmanager
def span(op: str, description: str, **data):
    """Wrap a step (retrieve, generate) in a span; a no-op when tracing is off."""
    if not ENABLED:
        yield None
        return
    with sentry_sdk.start_span(op=op, name=description) as s:
        for k, v in data.items():
            s.set_data(k, v)
        yield s
