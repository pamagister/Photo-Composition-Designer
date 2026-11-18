"""GUI command: launch the local web editor."""

from __future__ import annotations

from dataclasses import replace


def run(host: str = "127.0.0.1", port: int = 8767, log_level: str = "info") -> int:
    """Start the local FastAPI editor with uvicorn."""
    import uvicorn

    from photo_composition_designer.gui.app import create_app
    from photo_composition_designer.gui.settings import load_gui_settings

    settings = replace(load_gui_settings(), host=host, port=port, log_level=log_level)
    print(f"Starting Photo Composition Designer at http://{host}:{port}/")
    uvicorn.run(
        create_app(settings),
        host=host,
        port=port,
        log_level=log_level.lower(),
    )
    return 0
