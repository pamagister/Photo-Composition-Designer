import shutil
import subprocess
from pathlib import Path


def test_cli_generates_collages():
    base_dir = Path(__file__).resolve().parents[1]
    collages_dir = base_dir / "collages"
    images_dir = base_dir / "images"

    # 1. collages/ leeren
    if collages_dir.exists():
        shutil.rmtree(collages_dir)
    collages_dir.mkdir(parents=True, exist_ok=True)

    # 2. CLI ausführen
    cli_cmd = [
        "python3",
        "-m",
        "Photo_Composition_Designer",
        "--dpi",
        "50",
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

    # 3. Exitcode prüfen
    assert result.returncode == 0, "CLI returned non-zero exit code"

    # 4. Dateien prüfen
    assert collages_dir.exists(), "collages/ directory missing"

    # Liste der erzeugten Dateien
    created_files = list(collages_dir.glob("*.jpg"))
    pdf_files = list(collages_dir.glob("*.pdf"))

    # Falls sich die Anzahl später ändert, ist nur wichtig: mindestens 1 jpg!
    assert len(created_files) > 0, "No collage JPG files created"
    assert len(pdf_files) == 1, "PDF output missing"
