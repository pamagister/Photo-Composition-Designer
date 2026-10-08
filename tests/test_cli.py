import subprocess
import sys
from pathlib import Path

from PIL import Image


def test_cli_generates_collages(tmp_path: Path):
    base_dir = Path(__file__).resolve().parents[1]
    collages_dir = tmp_path / "collages"
    images_dir = tmp_path / "photos"
    week_dir = images_dir / "week-1"
    week_dir.mkdir(parents=True)
    Image.new("RGB", (80, 60), "royalblue").save(week_dir / "2024-03-01.jpg")

    cli_cmd = [
        sys.executable,
        "-m",
        "Photo_Composition_Designer",
        "--dpi",
        "30",
        str(images_dir),
    ]

    result = subprocess.run(
        cli_cmd,
        cwd=base_dir,
        capture_output=True,
        text=True,
    )

    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)

    assert result.returncode == 0, "CLI returned non-zero exit code"

    assert collages_dir.exists(), "collages/ directory missing"
    output_file = collages_dir / "week-1.jpg"
    pdf_file = collages_dir / "output.pdf"
    assert output_file.is_file()
    assert pdf_file.read_bytes().startswith(b"%PDF-")
    with Image.open(output_file) as generated:
        assert generated.width > 0
        assert generated.height > 0
