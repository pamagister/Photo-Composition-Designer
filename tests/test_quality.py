"""Tests for the image-quality heuristic and best-photo selection scorer."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter

from photo_composition_designer.project.quality import QualityScorer, SelectionScorer


def _write_photo(path: Path, width: int, height: int, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), color).save(path)


def _write_sharp_photo(path: Path) -> None:
    """Write a high-resolution photo with strong edges."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (800, 600), (0, 0, 0))
    for x in range(0, 800, 20):
        for y in range(0, 600, 20):
            for dx in range(10):
                for dy in range(10):
                    image.putpixel((x + dx, y + dy), (255, 255, 255))
    image.save(path)


def _write_blurry_photo(path: Path) -> None:
    """Write a low-resolution, nearly uniform photo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (64, 48), (120, 120, 120))
    image = image.filter(ImageFilter.GaussianBlur(4))
    image.save(path)


def test_sharp_high_resolution_photo_outranks_blurry_low_resolution(tmp_path: Path) -> None:
    sharp = tmp_path / "sharp.jpg"
    blurry = tmp_path / "blurry.jpg"
    _write_sharp_photo(sharp)
    _write_blurry_photo(blurry)

    scores = QualityScorer().score_all({1: sharp, 2: blurry})

    assert scores[1] > scores[2]


def test_unreadable_image_receives_lowest_score(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jpg"
    good = tmp_path / "good.jpg"
    _write_photo(good, 400, 300, (200, 10, 10))

    scores = QualityScorer().score_all({1: missing, 2: good})

    assert scores[1] < scores[2]


def test_scores_are_deterministic_and_normalised(tmp_path: Path) -> None:
    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    _write_photo(first, 400, 300, (200, 10, 10))
    _write_photo(second, 400, 300, (10, 200, 10))

    scorer = QualityScorer()
    first_scores = scorer.score_all({1: first, 2: second})
    second_scores = QualityScorer().score_all({1: first, 2: second})

    assert first_scores == second_scores
    assert all(0.0 < value <= 1.0 for value in first_scores.values())


def test_selection_scorer_multiplies_importance_and_quality() -> None:
    scorer = SelectionScorer({1: 0.8, 2: 0.4})
    assert scorer.score(1, 2.0) == 1.6
    assert scorer.score(2, 2.0) == 0.8


def test_selection_scorer_uses_neutral_quality_when_unknown() -> None:
    scorer = SelectionScorer({})
    assert scorer.score(99, 1.5) == 1.5
