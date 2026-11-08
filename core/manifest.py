"""App manifests: the ``app.toml`` file every app package ships.

The manifest is the single source of an app's metadata. Discovery reads and
validates it *before* importing the package, so an app with a broken manifest
(or one that needs a newer framework) is skipped without running its code.

Example::

    id = "snake"
    name = "Snake"
    description = "Eat, grow and go faster."
    category = "game"            # or "tool"
    accent = "#2ECC71"
    version = "1.0.0"
    author = "Arcade contributors"
    min_framework = "1.0"

    [scores]                     # optional: appear on the High Scores screen
    order = "higher"             # or "lower" (times)
    format = "points"            # or "time"
    variants = ["wrap", "walls"] # optional per-variant bests

    [[achievements]]             # optional, repeatable
    id = "length_25"
    name = "Noodle"
    description = "Grow to a length of 25."
    hidden = false               # optional
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, cast

from core.achievements import Achievement
from core.base_app import AppMeta, Category, ScoreFormat
from core.storage import ScoreOrder

#: Version of the app-facing API (BaseApp, AppContext, services, manifest schema).
#: Bump the minor version for additions and the major version for breaking changes.
FRAMEWORK_VERSION = "1.2"

MANIFEST_NAME = "app.toml"

_ID = re.compile(r"^[a-z0-9][a-z0-9_]*$")
_VERSION = re.compile(r"^\d+(\.\d+){0,2}$")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

_TOP_KEYS = {
    "id",
    "name",
    "description",
    "category",
    "accent",
    "version",
    "author",
    "min_framework",
    "scores",
    "achievements",
}
_SCORE_KEYS = {"order", "format", "variants"}
_ACHIEVEMENT_KEYS = {"id", "name", "description", "hidden"}


class ManifestError(Exception):
    """The manifest is missing, unreadable or invalid. ``problems`` lists every issue."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        super().__init__(f"{path}: " + "; ".join(problems))
        self.path = path
        self.problems = problems


class IncompatibleAppError(ManifestError):
    """The app needs a newer framework than this one."""


def parse_version(text: str) -> tuple[int, int, int]:
    """``"1.2"`` → ``(1, 2, 0)``. Raises ``ValueError`` for anything else."""
    if not _VERSION.match(text):
        raise ValueError(f"not a version: {text!r}")
    parts = [int(p) for p in text.split(".")]
    parts += [0] * (3 - len(parts))
    return parts[0], parts[1], parts[2]


def is_compatible(min_framework: str, framework: str = FRAMEWORK_VERSION) -> bool:
    """Whether an app requiring ``min_framework`` runs on ``framework``.

    Same major version, and at least the required minor/patch.
    """
    need, have = parse_version(min_framework), parse_version(framework)
    return need[0] == have[0] and need <= have


def parse_hex_color(text: str) -> tuple[int, int, int]:
    return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)


def to_hex_color(color: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*color)


def load_manifest(path: Path, framework: str = FRAMEWORK_VERSION) -> AppMeta:
    """Read and validate a manifest file. Raises :class:`ManifestError`."""
    if not path.is_file():
        raise ManifestError(path, [f"no {MANIFEST_NAME} found"])
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ManifestError(path, [f"cannot read: {exc}"]) from exc
    meta = parse_manifest(data, path)
    if not is_compatible(meta.min_framework, framework):
        raise IncompatibleAppError(
            path, [f"needs framework {meta.min_framework}, this is {framework}"]
        )
    return meta


def parse_manifest(data: dict[str, Any], path: Path = Path(MANIFEST_NAME)) -> AppMeta:
    """Validate already-parsed TOML. Collects *all* problems before raising."""
    problems: list[str] = []

    def string(table: dict[str, Any], name: str, where: str = "") -> str:
        value = table.get(name)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"'{where}{name}' must be a non-empty string")
            return ""
        return value

    for unknown in sorted(set(data) - _TOP_KEYS):
        problems.append(f"unknown key {unknown!r}")

    app_id = string(data, "id")
    if app_id and not _ID.match(app_id):
        problems.append("'id' may only contain lowercase letters, digits and underscores")
    name = string(data, "name")
    description = string(data, "description")
    category = data.get("category")
    if category not in ("game", "tool"):
        problems.append('\'category\' must be "game" or "tool"')
    accent_text = string(data, "accent")
    if accent_text and not _HEX.match(accent_text):
        problems.append("'accent' must be a hex color like \"#2ECC71\"")
    version = string(data, "version")
    if version and not _VERSION.match(version):
        problems.append("'version' must look like 1.0.0")
    author = string(data, "author")
    min_framework = string(data, "min_framework")
    if min_framework and not _VERSION.match(min_framework):
        problems.append("'min_framework' must look like 1.0")

    scores = data.get("scores")
    order: ScoreOrder = "higher"
    fmt: ScoreFormat = "points"
    variants: tuple[str, ...] = ()
    if scores is not None:
        if not isinstance(scores, dict):
            problems.append("[scores] must be a table")
            scores = {}
        for unknown in sorted(set(scores) - _SCORE_KEYS):
            problems.append(f"unknown key 'scores.{unknown}'")
        order = scores.get("order", "higher")
        if order not in ("higher", "lower"):
            problems.append('\'scores.order\' must be "higher" or "lower"')
        fmt = scores.get("format", "points")
        if fmt not in ("points", "time", "ms"):
            problems.append('\'scores.format\' must be "points", "time" or "ms"')
        raw_variants = scores.get("variants", [])
        if not (
            isinstance(raw_variants, list)
            and all(isinstance(v, str) and _ID.match(v) for v in raw_variants)
        ):
            problems.append("'scores.variants' must be a list of lowercase ids")
        elif len(set(raw_variants)) != len(raw_variants):
            problems.append("'scores.variants' contains duplicates")
        else:
            variants = tuple(raw_variants)

    achievements: list[Achievement] = []
    raw_achievements = data.get("achievements", [])
    if not isinstance(raw_achievements, list):
        problems.append("'achievements' must be an array of tables ([[achievements]])")
        raw_achievements = []
    seen: set[str] = set()
    for i, entry in enumerate(raw_achievements):
        where = f"achievements[{i}]."
        if not isinstance(entry, dict):
            problems.append(f"achievements[{i}] must be a table")
            continue
        for unknown in sorted(set(entry) - _ACHIEVEMENT_KEYS):
            problems.append(f"unknown key '{where}{unknown}'")
        a_id = string(entry, "id", where)
        if a_id and not _ID.match(a_id):
            problems.append(f"'{where}id' may only contain lowercase letters, digits and _")
        if a_id in seen:
            problems.append(f"duplicate achievement id {a_id!r}")
        seen.add(a_id)
        hidden = entry.get("hidden", False)
        if not isinstance(hidden, bool):
            problems.append(f"'{where}hidden' must be true or false")
            hidden = False
        achievements.append(
            Achievement(
                a_id, string(entry, "name", where), string(entry, "description", where), hidden
            )
        )

    if problems:
        raise ManifestError(path, problems)
    return AppMeta(
        id=app_id,
        name=name,
        description=description,
        category=cast(Category, category),
        accent=parse_hex_color(accent_text),
        tracks_scores=scores is not None,
        score_order=order,
        score_format=fmt,
        variants=variants,
        version=version,
        author=author,
        min_framework=min_framework,
        achievements=tuple(achievements),
    )
