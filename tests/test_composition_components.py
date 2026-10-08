from logging import Logger
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image

from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.core import composition_builder
from Photo_Composition_Designer.core.base import CompositionDesigner
from Photo_Composition_Designer.core.composition_io import CompositionIO
from Photo_Composition_Designer.image.CalendarRenderer import CalendarRenderer
from Photo_Composition_Designer.image.CollageRenderer import CollageRenderer
from Photo_Composition_Designer.image.DescriptionRenderer import DescriptionRenderer
from Photo_Composition_Designer.image.MapRenderer import MapRenderer
from Photo_Composition_Designer.image.ObjectDetector import ObjectDetector


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


def make_builder_config() -> ConfigParameterManager:
    config = ConfigParameterManager(persist_last_used=False)
    config.size.dpi.value = 300
    config.size.width.value = 210
    config.size.height.value = 297
    config.size.calendarHeight.value = 20
    config.general.compositionTitle.value = "Photo year"
    config.layout.marginTop.value = 10
    config.layout.marginBottom.value = 10
    config.layout.marginSides.value = 10
    config.layout.spacing.value = 5
    config.layout.objectRecognition = True
    config.calendar.horizontalOrientation.value = True
    return config


def test_renderer_builder_wires_shared_collaborators(monkeypatch) -> None:
    config = make_builder_config()
    logger = Mock()
    calendar = Mock(spec=CalendarRenderer)
    map_renderer = Mock(spec=MapRenderer)
    description = Mock(spec=DescriptionRenderer)
    description.height = 12
    detector = Mock(spec=ObjectDetector)
    collage = Mock(spec=CollageRenderer)
    page_renderer = Mock()

    monkeypatch.setattr(CalendarRenderer, "from_config", Mock(return_value=calendar))
    monkeypatch.setattr(MapRenderer, "from_config", Mock(return_value=map_renderer))
    monkeypatch.setattr(DescriptionRenderer, "from_config", Mock(return_value=description))
    monkeypatch.setattr(composition_builder, "ObjectDetector", Mock(return_value=detector))
    collage_constructor = Mock(return_value=collage)
    monkeypatch.setattr(composition_builder, "CollageRenderer", collage_constructor)
    page_renderer_constructor = Mock(return_value=page_renderer)
    monkeypatch.setattr(composition_builder, "CompositionPageRenderer", page_renderer_constructor)

    components = composition_builder.CompositionRendererBuilder(config, logger).build()

    assert components.composition_title == "Photo year"
    assert components.width_px == composition_builder.mm_to_px(210, 300)
    assert components.height_px == composition_builder.mm_to_px(297, 300)
    assert components.object_detector is detector
    assert components.collage_renderer is collage
    assert components.page_renderer is page_renderer
    assert collage_constructor.call_args.args[4] is True
    assert collage_constructor.call_args.args[7] is detector
    render_context = page_renderer_constructor.call_args.args[0]
    assert render_context.logger is logger
    assert render_context.calendar_renderer is calendar
    assert render_context.map_renderer is map_renderer
    assert render_context.description_renderer is description
    assert render_context.collage_renderer is collage


def test_designer_accepts_prebuilt_render_components(monkeypatch, tmp_path: Path) -> None:
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    config = make_builder_config()
    config.general.photoDirectory.value = str(photo_dir)
    components = SimpleNamespace(
        dpi=300,
        composition_title="Injected title",
        width_px=120,
        height_px=240,
        use_object_recognition=False,
        margin_top_px=1,
        margin_bottom_px=2,
        margin_sides_px=3,
        spacing_px=4,
        horizontal_orientation=False,
        calendar_primary_dim_px=5,
        calendar_secondary_dim_px=6,
        calendar_renderer=Mock(spec=CalendarRenderer),
        map_renderer=Mock(spec=MapRenderer),
        description_renderer=Mock(spec=DescriptionRenderer),
        object_detector=None,
        layout=Mock(),
        collage_renderer=Mock(spec=CollageRenderer),
        page_renderer=Mock(),
    )
    build = Mock(side_effect=AssertionError("Injected collaborators must be used"))
    monkeypatch.setattr(composition_builder.CompositionRendererBuilder, "build", build)

    designer = CompositionDesigner(config, Mock(), render_components=components)

    build.assert_not_called()
    assert designer.page_renderer is components.page_renderer
    assert designer.layoutManager is components.collage_renderer
    assert designer.width_px == 120
    assert designer.compositionTitle == "Injected title"
