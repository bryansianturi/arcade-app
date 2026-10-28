"""JSON-backed persistence for high scores, settings and per-app data.

Everything lives in one folder (see :func:`core.paths.user_data_dir`)::

    scores.json          {"snake": {"default": {"score": 42, "date": "2026-10-28"}}, ...}
    settings.json        global settings (see core.settings)
    apps/<app_id>.json   free-form data owned by a single app

Writes are atomic (write to a temp file, then rename) so a crash mid-save never
leaves a corrupt file behind. Corrupt or unreadable files are logged and treated
as empty rather than crashing the program. In the browser, :class:`BrowserStorage`
keeps the same documents in ``localStorage`` instead.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger(__name__)

ScoreOrder = Literal["higher", "lower"]
JSONDict = dict[str, Any]

SCORES_FILE = "scores.json"
DEFAULT_VARIANT = "default"


@dataclass(frozen=True)
class ScoreEntry:
    """A single best score for one app variant (e.g. Sudoku on "hard")."""

    score: float
    date: str


class Storage:
    """Reads and writes JSON documents inside a single data directory."""

    def __init__(self, root: Path) -> None:
        self.root = root

    # ------------------------------------------------------------------ raw JSON
    def path_for(self, name: str) -> Path:
        """Return the absolute path of a document such as ``"settings.json"``."""
        return self.root / name

    def load_json(self, name: str) -> JSONDict:
        """Load a JSON object, returning ``{}`` if it is missing or unreadable."""
        try:
            text = self._read_text(name)
            data = json.loads(text) if text is not None else {}
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read %s (%s); starting fresh", name, exc)
            return {}
        if not isinstance(data, dict):
            log.warning("Ignoring %s: expected a JSON object", name)
            return {}
        return data

    def save_json(self, name: str, data: JSONDict) -> None:
        """Write ``data`` as pretty-printed JSON."""
        self._write_text(name, json.dumps(data, indent=2, sort_keys=True))

    # ------------------------------------------------------------------ backend
    def _read_text(self, name: str) -> str | None:
        """A document's text, or ``None`` if it doesn't exist."""
        try:
            return self.path_for(name).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def _write_text(self, name: str, text: str) -> None:
        """Write atomically: to a temp file, then rename over the old one."""
        path = self.path_for(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    # ------------------------------------------------------------------ scores
    def record_score(
        self,
        app_id: str,
        score: float,
        variant: str = DEFAULT_VARIANT,
        order: ScoreOrder = "higher",
        today: date | None = None,
    ) -> bool:
        """Store ``score`` if it beats the current best. Returns ``True`` on a new best.

        ``order`` decides what "better" means: ``"higher"`` for points,
        ``"lower"`` for times.
        """
        scores = self.load_json(SCORES_FILE)
        per_app: JSONDict = scores.setdefault(app_id, {})
        current = _parse_entry(per_app.get(variant))
        if current is not None and not _is_better(score, current.score, order):
            return False
        per_app[variant] = {"score": score, "date": (today or date.today()).isoformat()}
        self.save_json(SCORES_FILE, scores)
        return True

    def best_score(self, app_id: str, variant: str = DEFAULT_VARIANT) -> ScoreEntry | None:
        """Return the best score for one app variant, or ``None`` if never played."""
        return _parse_entry(self.load_json(SCORES_FILE).get(app_id, {}).get(variant))

    def scores_for(self, app_id: str) -> dict[str, ScoreEntry]:
        """Return every variant's best score for an app."""
        raw = self.load_json(SCORES_FILE).get(app_id, {})
        result: dict[str, ScoreEntry] = {}
        if isinstance(raw, dict):
            for variant, value in raw.items():
                entry = _parse_entry(value)
                if entry is not None:
                    result[variant] = entry
        return result

    def clear_scores(self, app_id: str | None = None) -> None:
        """Delete the scores of one app, or of every app when ``app_id`` is ``None``."""
        if app_id is None:
            self.save_json(SCORES_FILE, {})
            return
        scores = self.load_json(SCORES_FILE)
        if scores.pop(app_id, None) is not None:
            self.save_json(SCORES_FILE, scores)

    # ------------------------------------------------------------------ app data
    def app_data(self, app_id: str) -> AppData:
        """Return a dict-like store private to one app (``apps/<app_id>.json``)."""
        return AppData(self, f"apps/{app_id}.json")


class BrowserStorage(Storage):
    """Keeps every document in the browser's ``localStorage``, under ``arcade/<name>``.

    ``local_storage`` is the page's ``window.localStorage`` (see
    :func:`core.web.local_storage`), or anything with ``getItem``/``setItem``.
    ``root`` is only used for files that never need to survive a reload (logs).

    Some browsers block site storage (privacy settings, full quota). Then
    :attr:`persistent` turns ``False`` and saves only last for this visit, rather
    than the arcade failing to start.
    """

    PREFIX = "arcade/"

    def __init__(self, local_storage: Any, root: Path = Path("/tmp/arcade")) -> None:
        super().__init__(root)
        self._local = local_storage
        self._memory: dict[str, str] = {}  # this visit's saves; newest wins
        self.persistent = True

    def _read_text(self, name: str) -> str | None:
        if name in self._memory:
            return self._memory[name]
        if not self.persistent:
            return None
        try:
            value = self._local.getItem(self.PREFIX + name)
        except Exception as exc:  # the browser's SecurityError arrives as a plain Exception
            self._unavailable(exc)
            return None
        return None if value is None else str(value)

    def _write_text(self, name: str, text: str) -> None:
        self._memory[name] = text
        if self.persistent:
            try:
                self._local.setItem(self.PREFIX + name, text)
            except Exception as exc:
                self._unavailable(exc)

    def _unavailable(self, exc: Exception) -> None:
        log.warning("Browser storage is unavailable (%s); saves will last for this visit only", exc)
        self.persistent = False


class AppData(MutableMapping[str, Any]):
    """A small persistent dictionary. Call :meth:`save` after changing it."""

    def __init__(self, storage: Storage, name: str) -> None:
        self._storage = storage
        self._name = name
        self._data = storage.load_json(name)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def save(self) -> None:
        """Persist the current contents to disk."""
        self._storage.save_json(self._name, self._data)


def _is_better(new: float, old: float, order: ScoreOrder) -> bool:
    return new > old if order == "higher" else new < old


def _parse_entry(value: object) -> ScoreEntry | None:
    if not isinstance(value, dict):
        return None
    score = value.get("score")
    if not isinstance(score, int | float) or isinstance(score, bool):
        return None
    return ScoreEntry(score=score, date=str(value.get("date", "")))
