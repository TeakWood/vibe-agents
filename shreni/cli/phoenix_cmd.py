"""`shreni phoenix` — manage the Arize Phoenix server that receives traces.

Phoenix runs as a separate process. This subcommand offers convenience
wrappers but does not act as a process supervisor — users are free to run
Phoenix in Docker, systemd, or any other way they like, as long as the
OTLP endpoint at ``$SHRENI_PHOENIX_ENDPOINT`` is reachable.

Subcommands:
    start [--port 6006] [--host 127.0.0.1]   Run `phoenix serve` in the foreground
    status                                    Probe the endpoint and report
    open                                      Open the project page in the browser
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from urllib import error as urllib_error
from urllib import request as urllib_request

from ..context import Context
from ..phoenix import DEFAULT_ENDPOINT, endpoint


def _resolve_endpoint() -> str:
    return endpoint()


def _project_url(ctx: Context) -> str:
    return f"{_resolve_endpoint()}/projects?project={ctx.project_slug}"


def cmd_start(*, port: int, host: str) -> int:
    """Run ``phoenix serve`` in the foreground. Blocks until Ctrl-C."""
    if shutil.which("phoenix") is None:
        print(
            "ERROR: 'phoenix' CLI not found. Install with:\n"
            "  pip install arize-phoenix   # or:  uv pip install arize-phoenix\n"
            "Alternatively run Phoenix in Docker:\n"
            f"  docker run -p {port}:6006 arizephoenix/phoenix:latest",
            file=sys.stderr,
        )
        return 1

    env = os.environ.copy()
    # Phoenix reads PHOENIX_PORT / PHOENIX_HOST for its server binding.
    env.setdefault("PHOENIX_PORT", str(port))
    env.setdefault("PHOENIX_HOST", host)

    print(f"Starting Phoenix at http://{host}:{port} (Ctrl-C to stop)...")
    print(f"Point Shreni at it with:  export SHRENI_PHOENIX_ENDPOINT=http://{host}:{port}")
    return subprocess.call(["phoenix", "serve"], env=env)


def cmd_status(ctx: Context) -> int:
    """Probe the OTLP endpoint and report whether Phoenix is reachable."""
    target = _resolve_endpoint()
    url = f"{target}/healthz"
    try:
        with urllib_request.urlopen(url, timeout=2) as resp:
            code = resp.getcode()
    except urllib_error.HTTPError as e:
        code = e.code
    except Exception as e:
        print(f"Phoenix UNREACHABLE at {target}  ({type(e).__name__}: {e})")
        print(f"  Start with:  shreni phoenix start")
        return 1

    if 200 <= code < 400:
        print(f"Phoenix OK at {target}")
        print(f"  Project URL: {_project_url(ctx)}")
        return 0
    print(f"Phoenix responded with HTTP {code} at {target}")
    return 1


def cmd_open(ctx: Context) -> int:
    """Open the current project's Phoenix UI page in the default browser."""
    url = _project_url(ctx)
    print(f"Opening {url}")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Failed to open browser ({e}). Copy this URL manually.")
        return 1
    return 0
