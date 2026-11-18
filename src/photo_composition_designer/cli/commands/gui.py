"""GUI command: launch the local web editor.

Phase 1 stub. The FastAPI application is delivered in Phase 2; until then
this prints a clear message and returns a non-zero exit code so the command
is discoverable but does not pretend to succeed.
"""

from __future__ import annotations


def run(host: str = "127.0.0.1", port: int = 8767) -> int:
    """Start the web editor (not yet implemented in this phase)."""
    print(
        "The web editor is not available yet. "
        f"It will start at http://{host}:{port}/ once Phase 2 is complete."
    )
    return 1
