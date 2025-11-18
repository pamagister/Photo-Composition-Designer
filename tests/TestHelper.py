from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """
    Creates a /temp directory at project root.
    """
    project_root = Path(__file__).resolve().parents[1]
    temp_dir = project_root / "temp"
    temp_dir.mkdir(exist_ok=True)
    return temp_dir
