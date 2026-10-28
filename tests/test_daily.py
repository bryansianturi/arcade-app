"""Daily challenges: stable date seeds, per-day results and streaks."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from core.base_app import AppContext
from core.daily import DATA_KEY, KEEP_DAYS, DailyChallenge, daily_seed

DAY = date(2026, 1, 1)
GOLDEN = 5054896057884489009


def test_seed_is_stable_and_specific() -> None:
    # A golden value: changing the derivation would change everyone's puzzles.
    assert daily_seed("sudoku", DAY) == GOLDEN
    assert daily_seed("sudoku", DAY) == daily_seed("sudoku", date(2026, 1, 1))
    assert daily_seed("sudoku", DAY) != daily_seed("sudoku", DAY + timedelta(days=1))
    assert daily_seed("sudoku", DAY) != daily_seed("minesweeper", DAY)


def test_rng_repeats_for_the_same_day() -> None:
    a = DailyChallenge("x", {}, lambda: DAY)
    b = DailyChallenge("x", {}, lambda: DAY)
    assert [a.rng().random() for _ in range(3)] == [b.rng().random() for _ in range(3)]
    assert a.rng().random() != a.rng(DAY + timedelta(days=1)).random()


def test_results_keep_the_best_and_count_streaks() -> None:
    today = [DAY]
    data: dict[str, Any] = {}
    daily = DailyChallenge("x", data, lambda: today[0])
    assert not daily.completed() and daily.streak() == 0
    assert daily.record(90, "lower")
    assert not daily.record(120, "lower") and daily.result() == 90
    assert daily.record(60, "lower") and daily.result() == 60
    today[0] = DAY + timedelta(days=1)
    assert daily.streak() == 1  # today not done yet: yesterday still counts
    daily.record(10)
    assert daily.streak() == 2
    today[0] = DAY + timedelta(days=3)
    assert daily.streak() == 0
    assert daily.record(5, "higher") and not daily.record(4, "higher")


def test_old_results_are_pruned_and_bad_data_ignored() -> None:
    data: dict[str, Any] = {DATA_KEY: {"2000-01-01": 5, "bad": "x"}}
    daily = DailyChallenge("x", data, lambda: DAY)
    assert daily.result(date(2000, 1, 1)) == 5
    daily.record(1)
    assert "2000-01-01" not in data[DATA_KEY] and KEEP_DAYS > 300
    data[DATA_KEY] = "corrupt"
    assert daily.result() is None


def test_sudoku_daily_is_the_same_puzzle_and_records_once(
    app_context: AppContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    import core.daily
    from apps.sudoku.app import SudokuApp

    class FixedDate(date):
        @classmethod
        def today(cls) -> FixedDate:
            return cls(2026, 3, 14)

    monkeypatch.setattr(core.daily, "date", FixedDate)
    app_context.achievements.define("sudoku", SudokuApp.meta.achievements)
    first = SudokuApp(app_context)
    first.on_enter()
    first._start_daily()
    second = SudokuApp(app_context)
    second.on_enter()
    second._start_daily()
    assert first.game is not None and second.game is not None
    assert first.game.puzzle == second.game.puzzle and first.daily_date == "2026-03-14"

    game = first.game
    for i in range(81):
        if game.values[i] == 0:
            game.selected = i
            first._enter(game.solution[i])
    assert first.mode == "solved"
    assert first.daily.result() is not None
    assert app_context.achievements.is_unlocked("sudoku", "daily")
    assert first.best_score("medium") is None  # daily times don't count as bests
    first.on_exit()
    later = SudokuApp(app_context)  # reopening the app: the chooser shows today is done
    later.on_enter()
    assert later.dialog is not None
    labels = [b.text for b in later.dialog.buttons]
    assert any(label.startswith("Daily · solved") for label in labels)
