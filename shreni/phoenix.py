"""Arize Phoenix integration — OpenTelemetry sidechannel.

Shreni's primary observability stream is JSONL on disk (see ``observability.py``).
Phoenix is a *secondary*, opt-in stream: when a Phoenix server is reachable,
the same span tree is also shipped over OTLP-HTTP so it shows up in
Phoenix's web UI grouped by Shreni project.

Design notes
------------
* The JSONL stream remains the source of truth. If Phoenix is down or the
  package is missing, agents do not block and the JSONL stream is unaffected.
* Each Shreni ``project_slug`` becomes a Phoenix project (the picker in the
  Phoenix UI). Cross-project trace bleed is therefore impossible.
* Setup is idempotent — calling ``setup()`` twice returns the same tracer.

Configuration (env vars, all optional)
--------------------------------------
``SHRENI_PHOENIX_ENDPOINT``  base URL of the Phoenix collector
                              (default ``http://localhost:6006``)
``SHRENI_PHOENIX_DISABLED``  set to ``1`` to skip Phoenix entirely even
                              when the package is installed
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from .context import Context
from .shell import log

DEFAULT_ENDPOINT = "http://localhost:6006"
_PROBE_TIMEOUT_S = 0.5


def _reachable(target: str) -> bool:
    """Quick GET on the root URL — confirms a Phoenix server is listening.

    We tolerate any 2xx/3xx/4xx response (the server is up; 404 on / is fine);
    only connection errors or timeouts mean Phoenix is not reachable.
    """
    try:
        with urllib_request.urlopen(target, timeout=_PROBE_TIMEOUT_S) as resp:
            return resp.getcode() < 500
    except urllib_error.HTTPError as e:
        return e.code < 500
    except Exception:
        return False

_tracer: Any | None = None
_setup_attempted = False
_setup_succeeded = False


def is_disabled() -> bool:
    return os.environ.get("SHRENI_PHOENIX_DISABLED", "").lower() in ("1", "true", "yes")


def endpoint() -> str:
    return os.environ.get("SHRENI_PHOENIX_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/")


def setup(ctx: Context) -> Any | None:
    """Initialise the OTel tracer that ships spans to Phoenix.

    Returns the tracer on success, ``None`` otherwise. Safe to call repeatedly;
    on subsequent calls it returns the cached tracer without re-initialising.
    """
    global _tracer, _setup_attempted, _setup_succeeded
    if _setup_attempted:
        return _tracer
    _setup_attempted = True

    if is_disabled():
        log("Phoenix disabled via SHRENI_PHOENIX_DISABLED — JSONL only.")
        return None

    try:
        from phoenix.otel import register  # type: ignore
    except ImportError:
        log(
            "Phoenix SDK not installed (pip install arize-phoenix-otel) — "
            "tracing to JSONL only."
        )
        return None

    target = endpoint()
    if not _reachable(target):
        log(
            f"Phoenix not reachable at {target} — JSONL only. "
            f"Start it with: shreni phoenix start"
        )
        return None

    try:
        # Silence the OTLP exporter's noisy retry logger — when the server
        # goes away mid-run we want to fail quiet, not spam the agent log.
        logging.getLogger("opentelemetry.exporter.otlp.proto.http.trace_exporter").setLevel(
            logging.CRITICAL
        )
        tracer_provider = register(
            project_name=ctx.project_slug,
            endpoint=f"{target}/v1/traces",
            batch=True,
            set_global_tracer_provider=False,
            verbose=False,
        )
        _tracer = tracer_provider.get_tracer("shreni")
        _setup_succeeded = True
        log(
            f"Phoenix tracing enabled → {target} "
            f"(project: '{ctx.project_slug}')"
        )
        return _tracer
    except Exception as e:
        log(
            f"Phoenix setup failed ({type(e).__name__}: {e}) — JSONL only. "
            f"Start Phoenix with: shreni phoenix start"
        )
        return None


def get_tracer() -> Any | None:
    """Return the active tracer if setup succeeded, else None."""
    return _tracer if _setup_succeeded else None


def is_active() -> bool:
    return _setup_succeeded


def shutdown() -> None:
    """Flush any buffered spans to Phoenix. Safe to call when inactive."""
    if not _setup_succeeded:
        return
    try:
        from opentelemetry import trace as otel_trace
        provider = otel_trace.get_tracer_provider()
        flush = getattr(provider, "force_flush", None)
        if callable(flush):
            flush(timeout_millis=2000)
        shutdown_fn = getattr(provider, "shutdown", None)
        if callable(shutdown_fn):
            shutdown_fn()
    except Exception:
        pass
