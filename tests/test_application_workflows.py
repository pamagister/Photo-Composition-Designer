from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from Photo_Composition_Designer.application import composition_workflow
from Photo_Composition_Designer.application.composition_workflow import (
    CompositionWorkflow,
)
from Photo_Composition_Designer.application.photo_distribution_workflow import (
    PhotoDistributionWorkflow,
)


def make_config() -> SimpleNamespace:
    return SimpleNamespace(
        layout=SimpleNamespace(generatePdf=SimpleNamespace(value=True)),
        size=SimpleNamespace(dpi=SimpleNamespace(value=300)),
        calendar=SimpleNamespace(
            collagesToGenerate=SimpleNamespace(value=2),
            startDate=SimpleNamespace(value=datetime(2024, 1, 1)),
        ),
    )


class FakeDesigner:
    def __init__(self, output_dir: Path | None = None) -> None:
        self.outputDir = output_dir or Path(".")
        self.generate_compositions_from_folders = Mock()
        self.generate_pdf = Mock()


def test_generate_render_only_restores_pdf_setting() -> None:
    config = make_config()
    designer = FakeDesigner()
    workflow = CompositionWorkflow(config, Mock(), designer)

    workflow.generate("render_only")

    assert config.layout.generatePdf.value is True
    designer.generate_compositions_from_folders.assert_called_once_with()


def test_generate_render_only_restores_pdf_setting_after_error() -> None:
    config = make_config()
    designer = FakeDesigner()
    designer.generate_compositions_from_folders.side_effect = RuntimeError("render failed")
    workflow = CompositionWorkflow(config, Mock(), designer)

    with pytest.raises(RuntimeError, match="render failed"):
        workflow.generate("render_only")

    assert config.layout.generatePdf.value is True


@pytest.mark.parametrize(
    ("mode", "expected_method"),
    [
        ("render_and_pdf", "generate_compositions_from_folders"),
        ("pdf_only", "generate_pdf"),
    ],
)
def test_generate_delegates_to_designer(mode: str, expected_method: str) -> None:
    designer = FakeDesigner()
    workflow = CompositionWorkflow(make_config(), Mock(), designer)

    workflow.generate(mode)

    getattr(designer, expected_method).assert_called_once()


def test_create_preview_scales_a_copy_of_the_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config()
    preview_image = Image.new("RGB", (50, 100))
    created_configs = []

    class PreviewDesigner:
        width_px = 100
        height_px = 200

        def __init__(self, received_config, logger) -> None:
            created_configs.append(received_config)

        def generate_compositions_from_folder(self, folder_name):
            return preview_image

    monkeypatch.setattr(composition_workflow, "CompositionDesigner", PreviewDesigner)
    workflow = CompositionWorkflow(config, Mock(), FakeDesigner())

    result = workflow.create_preview("week", target_width=50, target_height=100)

    assert result is preview_image
    assert config.size.dpi.value == 300
    assert created_configs[1].size.dpi.value == 150


def test_render_and_save_preview_writes_full_size_image(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preview_image = Mock()

    class PreviewDesigner:
        outputDir = tmp_path

        def __init__(self, config, logger) -> None:
            pass

        def generate_compositions_from_folder(self, folder_name):
            return preview_image

    monkeypatch.setattr(composition_workflow, "CompositionDesigner", PreviewDesigner)
    workflow = CompositionWorkflow(make_config(), Mock(), FakeDesigner())

    output_file = workflow.render_and_save_preview("week")

    assert output_file == tmp_path / "week.jpg"
    preview_image.save.assert_called_once_with(output_file, quality=95)


def test_distribute_copies_grouped_photos_into_week_folders(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_file = tmp_path / "photo.jpg"
    source_file.write_bytes(b"photo")
    photo = SimpleNamespace(file_path=source_file)
    monkeypatch.setattr(
        "Photo_Composition_Designer.application.photo_distribution_workflow.get_photos_from_dir",
        lambda directory: [photo],
    )

    class FakeDistributor:
        def __init__(self, photos, distribution_count) -> None:
            pass

        def distribute_equally(self):
            return [[photo], []]

    monkeypatch.setattr(
        "Photo_Composition_Designer.application.photo_distribution_workflow.ImageDistributor",
        FakeDistributor,
    )
    config = make_config()
    workflow = PhotoDistributionWorkflow(config, Mock())

    completed = workflow.distribute(tmp_path, "distribute_equally")

    assert completed is True
    assert (tmp_path / "00_Jan-01" / "photo.jpg").read_bytes() == b"photo"
    assert (tmp_path / "01_Jan-08").is_dir()
