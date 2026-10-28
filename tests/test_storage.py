from __future__ import annotations

import json
from datetime import date

from core.settings import WINDOW_PRESETS, Settings
from core.storage import Storage


def test_record_score_higher_is_better(storage: Storage) -> None:
    assert storage.record_score("snake", 10) is True
    assert storage.record_score("snake", 5) is False
    assert storage.record_score("snake", 10) is False  # ties are not new bests
    assert storage.record_score("snake", 12) is True
    best = storage.best_score("snake")
    assert best is not None and best.score == 12


def test_record_score_lower_is_better_per_variant(storage: Storage) -> None:
    storage.record_score("sudoku", 300, "easy", order="lower")
    assert storage.record_score("sudoku", 320, "easy", order="lower") is False
    assert storage.record_score("sudoku", 250, "easy", order="lower") is True
    storage.record_score("sudoku", 900, "hard", order="lower")
    scores = storage.scores_for("sudoku")
    assert {k: v.score for k, v in scores.items()} == {"easy": 250, "hard": 900}


def test_score_date_is_recorded(storage: Storage) -> None:
    storage.record_score("x", 1, today=date(2026, 1, 2))
    best = storage.best_score("x")
    assert best is not None and best.date == "2026-01-02"


def test_scores_persist_across_instances(storage: Storage) -> None:
    storage.record_score("snake", 42)
    best = Storage(storage.root).best_score("snake")
    assert best is not None and best.score == 42


def test_missing_and_corrupt_files_are_treated_as_empty(storage: Storage) -> None:
    assert storage.best_score("nothing") is None
    storage.root.mkdir(parents=True)
    storage.path_for("scores.json").write_text("{not json", encoding="utf-8")
    assert storage.best_score("snake") is None
    assert storage.record_score("snake", 3) is True  # recovers by overwriting


def test_malformed_entries_are_ignored(storage: Storage) -> None:
    storage.save_json("scores.json", {"snake": {"default": {"score": "lots"}, "ok": {"score": 2}}})
    assert set(storage.scores_for("snake")) == {"ok"}


def test_clear_scores(storage: Storage) -> None:
    storage.record_score("a", 1)
    storage.record_score("b", 1)
    storage.clear_scores("a")
    assert storage.best_score("a") is None and storage.best_score("b") is not None
    storage.clear_scores()
    assert storage.best_score("b") is None


def test_save_is_atomic_and_leaves_no_temp_files(storage: Storage) -> None:
    storage.save_json("x.json", {"a": 1})
    files = [p.name for p in storage.root.iterdir()]
    assert files == ["x.json"]
    assert json.loads(storage.path_for("x.json").read_text()) == {"a": 1}


def test_app_data_roundtrip(storage: Storage) -> None:
    data = storage.app_data("snake")
    data["wrap"] = True
    data.save()
    again = storage.app_data("snake")
    assert again.get("wrap") is True and len(again) == 1
    assert storage.path_for("apps/snake.json").is_file()


def test_settings_roundtrip_and_validation(storage: Storage) -> None:
    s = Settings(theme="light", window_size=WINDOW_PRESETS[0], show_fps=True)
    s.save(storage)
    loaded = Settings.load(storage)
    assert (loaded.theme, loaded.window_size, loaded.show_fps) == ("light", WINDOW_PRESETS[0], True)

    storage.save_json(
        "settings.json", {"theme": "neon", "window_size": [1, 2], "fullscreen": "yes"}
    )
    loaded = Settings.load(storage)
    assert loaded == Settings()  # every invalid value falls back to its default


def test_settings_notify_listeners() -> None:
    s = Settings()
    seen: list[str] = []
    s.subscribe(lambda st: seen.append(st.theme))
    s.theme = "light"
    s.notify()
    assert seen == ["light"]
