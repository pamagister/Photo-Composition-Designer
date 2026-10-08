from logging import Logger
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image

from Photo_Composition_Designer.core.composition_io import CompositionIO


def make_composition_io(tmp_path: Path) -> CompositionIO:
    return CompositionIO(
        config=SimpleNamespace(size=SimpleNamespace(jpgQuality=SimpleNamespace(value=80))),
        photo_dir=tmp_path,
        output_dir=tmp_path,
        locations={},
        logger=Mock(spec=Logger),
        dpi=300,
    )


def test_get_description_reads_first_sorted_text_file(tmp_path: Path) -> None:
    (tmp_path / "02-notes.txt").write_text("Title: Second\n", encoding="utf-8")
    (tmp_path / "01-notes.txt").write_text("Title: First\nDetails: More\n", encoding="utf-8")

    assert CompositionIO.get_description(tmp_path) == ["First", "More"]


def test_file_service_saves_compositions_and_generates_pdf(tmp_path: Path) -> None:
    composition_io = make_composition_io(tmp_path)
    first_image = Image.new("RGB", (20, 20), "red")
    second_image = Image.new("RGB", (20, 20), "blue")

    assert composition_io.save(first_image, "first") == tmp_path / "first.jpg"
    second_image.save(tmp_path / "second.jpg")

    pdf_path = composition_io.generate_pdf(tmp_path)

    assert pdf_path == tmp_path / "output.pdf"
    assert pdf_path is not None
    assert pdf_path.is_file()
