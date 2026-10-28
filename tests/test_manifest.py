"""app.toml parsing, validation and framework compatibility."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from core.manifest import (
    FRAMEWORK_VERSION,
    IncompatibleAppError,
    ManifestError,
    is_compatible,
    load_manifest,
    parse_manifest,
    parse_version,
    to_hex_color,
)

VALID = """
id = "demo"
name = "Demo"
description = "A demo app."
category = "game"
accent = "#2ecc71"
version = "1.2.3"
author = "Someone"
min_framework = "1.0"

[scores]
order = "lower"
format = "time"
variants = ["easy", "hard"]

[[achievements]]
id = "first_win"
name = "First win"
description = "Win once."

[[achievements]]
id = "secret"
name = "Secret"
description = "Find it."
hidden = true
"""


def data(text: str = VALID) -> dict[str, Any]:
    return tomllib.loads(text)


def problems_for(d: dict[str, Any]) -> list[str]:
    with pytest.raises(ManifestError) as info:
        parse_manifest(d)
    return info.value.problems


def test_valid_manifest() -> None:
    meta = parse_manifest(data())
    assert (meta.id, meta.name, meta.category, meta.accent) == (
        "demo",
        "Demo",
        "game",
        (46, 204, 113),
    )
    assert (meta.version, meta.author, meta.min_framework) == ("1.2.3", "Someone", "1.0")
    assert meta.tracks_scores and meta.score_order == "lower" and meta.score_format == "time"
    assert meta.variants == ("easy", "hard")
    assert [a.id for a in meta.achievements] == ["first_win", "secret"]
    assert meta.achievements[1].hidden


def test_scores_and_achievements_are_optional() -> None:
    d = data()
    del d["scores"], d["achievements"]
    meta = parse_manifest(d)
    assert not meta.tracks_scores and meta.achievements == ()


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"id": "Has Space"}, "'id' may only contain"),
        ({"name": ""}, "'name' must be a non-empty string"),
        ({"category": "toy"}, "'category' must be"),
        ({"accent": "green"}, "'accent' must be a hex color"),
        ({"version": "one"}, "'version' must look like"),
        ({"min_framework": 1}, "'min_framework' must be a non-empty string"),
        ({"colour": "#000000"}, "unknown key 'colour'"),
        ({"scores": {"order": "up"}}, "'scores.order' must be"),
        ({"scores": {"format": "ms"}}, "'scores.format' must be"),
        ({"scores": {"variants": ["a", "a"]}}, "contains duplicates"),
        ({"scores": {"variants": "easy"}}, "must be a list"),
        ({"scores": {"best": 1}}, "unknown key 'scores.best'"),
        ({"achievements": {"id": "x"}}, "must be an array of tables"),
        ({"achievements": [{"id": "x", "name": "X"}]}, "'achievements[0].description'"),
        (
            {"achievements": [{"id": "x", "name": "X", "description": "d", "hidden": "no"}]},
            "hidden",
        ),
    ],
)
def test_invalid_fields_are_reported(change: dict[str, Any], expected: str) -> None:
    d = data()
    d.update(change)
    assert any(expected in p for p in problems_for(d))


def test_duplicate_achievement_ids() -> None:
    d = data()
    d["achievements"][1]["id"] = "first_win"
    assert any("duplicate achievement id" in p for p in problems_for(d))


def test_all_problems_are_collected() -> None:
    assert len(problems_for({"id": "x"})) >= 6


def test_versions() -> None:
    assert parse_version("1") == (1, 0, 0) and parse_version("2.3.4") == (2, 3, 4)
    with pytest.raises(ValueError):
        parse_version("1.x")
    assert is_compatible("1.0", "1.0") and is_compatible("1.0", "1.4")
    assert not is_compatible("1.5", "1.4")
    assert not is_compatible("1.0", "2.0")  # a new major version breaks old apps
    assert is_compatible("1.0", FRAMEWORK_VERSION)


def test_load_manifest_errors(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match=r"no app\.toml"):
        load_manifest(tmp_path / "app.toml")
    bad = tmp_path / "app.toml"
    bad.write_text("id = ")
    with pytest.raises(ManifestError, match="cannot read"):
        load_manifest(bad)
    bad.write_text(VALID.replace('min_framework = "1.0"', 'min_framework = "1.9"'))
    with pytest.raises(IncompatibleAppError):
        load_manifest(bad, framework="1.0")
    assert load_manifest(bad, framework="1.9").id == "demo"


def test_hex_round_trip() -> None:
    assert to_hex_color((46, 204, 113)) == "#2ECC71"


def test_bundled_manifests_are_valid() -> None:
    folders = [p for p in Path("apps").iterdir() if (p / "__init__.py").is_file()]
    assert len(folders) >= 17
    for folder in folders:
        meta = load_manifest(folder / "app.toml")
        assert meta.author and meta.version
