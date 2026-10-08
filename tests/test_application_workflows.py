from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from logging import Logger, getLogger
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from Photo_Composition_Designer.application import CompositionApplicationFactory
from Photo_Composition_Designer.application.composition_workflow import (
    CompositionWorkflow,
)
from Photo_Composition_Designer.application.photo_distribution_workflow import (
    PhotoDistributionWorkflow,
)
from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.core.base import CompositionDesigner
from Photo_Composition_Designer.gui.gui import MainGui


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
        self.width_px = 100
        self.height_px = 200
        self.generate_compositions_from_folders = Mock()
        self.generate_pdf = Mock()


class PreviewDesignerFactory:
    def __init__(
        self,
        preview_image: Image.Image | None = None,
        output_dir: Path = Path("."),
    ) -> None:
        self.preview_image = preview_image
        self.output_dir = output_dir
        self.created_configs: list[ConfigParameterManager | SimpleNamespace] = []

    def create(
        self,
        config: ConfigParameterManager | SimpleNamespace,
        logger: Logger,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> PreviewDesigner:
        self.created_configs.append(config)
        return PreviewDesigner(self.preview_image, self.output_dir)


class PreviewDesigner:
    width_px = 100
    height_px = 200

    def __init__(self, preview_image: Image.Image | None, output_dir: Path) -> None:
        self.preview_image = preview_image
        self.outputDir = output_dir

    def generate_compositions_from_folder(self, folder_name: str) -> Image.Image | None:
        return self.preview_image


def make_real_config(photo_dir: Path) -> ConfigParameterManager:
    config = ConfigParameterManager(persist_last_used=False)
    config.general.photoDirectory.value = photo_dir
    config.layout.objectRecognition = False
    return config


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


def test_create_preview_scales_a_copy_of_the_configuration() -> None:
    config = make_config()
    preview_image = Image.new("RGB", (50, 100))
    factory = PreviewDesignerFactory(preview_image)
    workflow = CompositionWorkflow(
        config,
        Mock(),
        FakeDesigner(),
        designer_factory=factory,
    )

    result = workflow.create_preview("week", target_width=50, target_height=100)

    assert result is preview_image
    assert config.size.dpi.value == 300
    assert len(factory.created_configs) == 1
    assert factory.created_configs[0].size.dpi.value == 150


def test_render_and_save_preview_writes_full_size_image(tmp_path: Path) -> None:
    preview_image = Image.new("RGB", (12, 8), "red")
    factory = PreviewDesignerFactory(preview_image, tmp_path)
    workflow = CompositionWorkflow(
        make_config(),
        Mock(),
        FakeDesigner(),
        designer_factory=factory,
    )

    output_file = workflow.render_and_save_preview("week")

    assert output_file == tmp_path / "week.jpg"
    assert output_file.is_file()
    with Image.open(output_file) as saved_image:
        assert saved_image.size == preview_image.size


def test_application_factory_creates_and_runs_a_real_workflow(tmp_path: Path) -> None:
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    config = make_real_config(photo_dir)
    progress_events: list[tuple[int, int]] = []

    def progress_callback(value: int, total: int) -> None:
        progress_events.append((value, total))

    workflow = CompositionApplicationFactory(Mock()).create_workflow(
        config,
        progress_callback,
    )

    assert isinstance(workflow.designer, CompositionDesigner)
    assert workflow.designer.progress_callback is progress_callback
    assert workflow.photo_directory == photo_dir
    assert workflow.output_directory == tmp_path / "collages"
    assert workflow.clear_object_detector_cache() is False

    workflow.generate("render_only")

    assert progress_events == [(0, 0)]
    assert config.layout.generatePdf.value is True


def test_real_workflow_preview_uses_a_scaled_config_copy(tmp_path: Path) -> None:
    photo_dir = tmp_path / "photos"
    (photo_dir / "empty-week").mkdir(parents=True)
    config = make_real_config(photo_dir)
    workflow = CompositionApplicationFactory(Mock()).create_workflow(config)

    preview = workflow.create_preview("empty-week", target_width=100, target_height=100)

    assert preview is None
    assert config.size.dpi.value == 300


def test_real_workflow_renders_photo_files_and_creates_pdf(tmp_path: Path) -> None:
    photo_dir = tmp_path / "photos"
    week_dir = photo_dir / "week-1"
    week_dir.mkdir(parents=True)
    Image.new("RGB", (80, 60), "royalblue").save(week_dir / "2024-03-01.jpg")

    config = make_real_config(photo_dir)
    config.general.locationsConfig.value = tmp_path / "locations.ini"
    config.general.compositionTitle.value = ""
    config.size.dpi.value = 30
    config.size.width.value = 100
    config.size.height.value = 70
    config.calendar.useCalendar.value = False
    config.geo.usePhotoLocationMaps.value = False
    config.layout.usePhotoDescription.value = False
    config.layout.generatePdf.value = True

    workflow = CompositionApplicationFactory(getLogger("composition-integration")).create_workflow(
        config
    )

    workflow.generate()

    output_file = tmp_path / "collages" / "week-1.jpg"
    pdf_file = tmp_path / "collages" / "output.pdf"
    assert output_file.is_file()
    assert pdf_file.read_bytes().startswith(b"%PDF-")
    with Image.open(output_file) as rendered_image:
        assert rendered_image.size == (118, 83)
        red, green, blue = rendered_image.getpixel((20, 20))
        assert red < 100
        assert green < 140
        assert blue > 180


def test_gui_progress_update_handles_empty_workloads() -> None:
    gui = MainGui.__new__(MainGui)
    gui.root = Mock()
    gui.progress = Mock()

    gui._progress_update(0, 0)

    callback = gui.root.after.call_args.args[1]
    callback()
    gui.progress.configure.assert_called_once_with(value=0)


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
