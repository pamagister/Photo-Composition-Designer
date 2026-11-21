"""GUI command: launch the local web editor."""

from __future__ import annotations

import socket
import threading
import time
import webbrowser
from dataclasses import replace

BROWSER_TIMEOUT_SECONDS = 30.0


def _wait_for_server(host: str, port: int, timeout: float = BROWSER_TIMEOUT_SECONDS) -> bool:
    """Return True once the local server accepts a TCP connection."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _open_browser_when_ready(
    host: str, port: int, timeout: float = BROWSER_TIMEOUT_SECONDS
) -> None:
    """Open the web UI once the server is ready; browser errors are non-fatal."""
    if not _wait_for_server(host, port, timeout=timeout):
        print(f"Browser launch skipped: server did not start on {host}:{port}.")
        return
    try:
        webbrowser.open(f"http://{host}:{port}/")
    except (webbrowser.Error, OSError) as error:
        print(f"Could not open the browser: {error}")


def run(
    host: str = "127.0.0.1",
    port: int = 8767,
    log_level: str = "info",
    open_browser: bool = False,
) -> int:
    """Start the local FastAPI editor with uvicorn."""
    import uvicorn

    from photo_composition_designer.gui.app import create_app
    from photo_composition_designer.gui.settings import load_gui_settings

    settings = replace(load_gui_settings(), host=host, port=port, log_level=log_level)
    print(f"Starting Photo Composition Designer at http://{host}:{port}/")
    app = create_app(settings)
    config = uvicorn.Config(app, host=host, port=port, log_level=log_level.lower())
    server = uvicorn.Server(config)
    app.state.server = server
    if open_browser:
        threading.Thread(
            target=_open_browser_when_ready,
            args=(host, port),
            name="photo-composition-designer-open-browser",
            daemon=True,
        ).start()
    server.run()
    return 0
