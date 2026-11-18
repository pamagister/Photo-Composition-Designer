"""Tests for the typed per-project output profile."""

from __future__ import annotations

from datetime import datetime

import pytest

from photo_composition_designer.core.output_profile import (
    OutputProfile,
    OutputProfileError,
    SizeProfile,
)
from photo_composition_designer.core.settings import Settings
from tests.project_test_helpers import make_database, make_service


def test_default_profile_round_trips():
    profile = OutputProfile.default()

    restored = OutputProfile.from_dict(profile.to_dict())

    assert restored == profile


def test_profile_hash_is_stable_and_sensitive():
    profile = OutputProfile.default()

    assert profile.profile_hash() == OutputProfile.from_dict(profile.to_dict()).profile_hash()

    changed = OutputProfile(
        size=SizeProfile(dpi=150),
        calendar=profile.calendar,
        style=profile.style,
        geo=profile.geo,
        layout=profile.layout,
    )
    assert changed.profile_hash() != profile.profile_hash()


def test_profile_settings_round_trip():
    settings = Settings()
    settings.size.dpi.value = 150
    settings.calendar.language.value = "en_US"
    settings.style.backgroundColor.value = settings.style.backgroundColor.value

    profile = OutputProfile.from_settings(settings)
    restored = profile.to_settings()

    assert restored.size.dpi.value == 150
    assert restored.calendar.language.value == "en_US"


def test_from_dict_fills_missing_values_with_defaults():
    profile = OutputProfile.from_dict({"size": {"dpi": 150}})

    assert profile.size.dpi == 150
    assert profile.size.width == SizeProfile().width
    assert profile.calendar.language == OutputProfile.default().calendar.language


def test_from_dict_rejects_invalid_values():
    with pytest.raises(OutputProfileError):
        OutputProfile.from_dict({"size": {"dpi": 0}})

    with pytest.raises(OutputProfileError):
        OutputProfile.from_dict({"style": {"background_color": "red"}})


def test_profiles_are_independent():
    first = OutputProfile.default()
    second = OutputProfile.default()

    assert first == second
    assert first.profile_hash() == second.profile_hash()


def test_create_project_snapshots_defaults(tmp_path):
    database = make_database(tmp_path)
    service = make_service(database)
    try:
        project = service.create_project(
            name="Snapshot",
            page_count=1,
            start_date=datetime(2027, 1, 4),
        )

        profile = OutputProfile.from_dict(project.output_profile)
        assert profile == OutputProfile.default()
    finally:
        database.close()


def test_existing_empty_profile_reads_default_without_rewrite(tmp_path):
    database = make_database(tmp_path)
    service = make_service(database)
    try:
        # Simulate a legacy project with an empty snapshot.
        project = service.create_project(
            name="Legacy",
            page_count=1,
            start_date=datetime(2027, 1, 4),
        )
        from photo_composition_designer.project.repositories import ProjectRepository

        with database.transaction() as connection:
            ProjectRepository(connection).update(
                project.id,
                output_profile={},
                updated_at=project.updated_at,
            )

        reopened = service.get_project(project.id)
        assert reopened.output_profile == {}
        profile = OutputProfile.from_dict(reopened.output_profile)
        assert profile == OutputProfile.default()
    finally:
        database.close()
