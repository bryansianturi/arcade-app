"""Crate Keeper: level files, pushing rules, undo and solvability of every level."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.crate_keeper.logic import Game, Level, LevelError, dead_squares, load_levels, solve
from core.base_app import AppContext

LEVELS = load_levels()


def test_bundled_levels_load() -> None:
    assert len(LEVELS) >= 12
    assert len({lvl.name for lvl in LEVELS}) == len(LEVELS)


@pytest.mark.parametrize("level", LEVELS, ids=lambda lvl: lvl.name)
def test_every_level_is_solvable(level: Level) -> None:
    assert solve(level) is not None


def test_levels_get_harder() -> None:
    pushes = [solve(lvl) or 0 for lvl in LEVELS]
    assert pushes[0] <= 2 and max(pushes[-3:]) >= 10


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (["#####", "#@$ #", "#####"], "1 crates but 0 targets"),
        (["#####", "# $.#", "#####"], "no keeper"),
        (["#####", "#@$.@", "#####"], "more than one keeper"),
        (["#####", "#@$.X", "#####"], "unknown character"),
        (["#####", "#@$. ", "#####"], "walk off the map"),
    ],
)
def test_invalid_levels(rows: list[str], message: str) -> None:
    with pytest.raises(LevelError, match=message):
        Level.parse("bad", rows)


def test_load_levels_from_a_folder(tmp_path: Path) -> None:
    (tmp_path / "02.json").write_text(json.dumps({"name": "B", "map": ["####", "#@*#", "####"]}))
    (tmp_path / "01.json").write_text(json.dumps({"name": "A", "map": ["#####", "#@$.#", "#####"]}))
    assert [lvl.name for lvl in load_levels(tmp_path)] == ["A", "B"]
    (tmp_path / "03.json").write_text("{nope")
    with pytest.raises(LevelError):
        load_levels(tmp_path)


def test_walls_and_double_crates_block() -> None:
    g = Game(Level.parse("t", ["#######", "#@$$. #", "#  .  #", "#######"]))
    assert g.move("up") == "blocked"  # a wall
    assert g.move("right") == "blocked"  # two crates in a row can't be pushed
    assert g.moves == 0 and not g.can_undo


def test_walking_and_pushing() -> None:
    g = Game(Level.parse("t", ["#######", "#     #", "# @$ .#", "#######"]))
    assert g.move("up") == "move" and g.move("down") == "move"
    assert g.move("right") == "push"
    assert g.player == (2, 3) and g.boxes == {(2, 4)} and g.pushes == 1 and g.moves == 3
    assert not g.solved
    assert g.move("right") == "push" and g.solved


def test_push_onto_target_solves() -> None:
    g = Game(Level.parse("t", ["#####", "#@$.#", "#####"]))
    assert g.move("right") == "push"
    assert g.solved and g.moves == 1 and g.pushes == 1 and g.boxes_home == 1
    assert g.move("left") == "blocked"  # nothing moves after solving


def test_undo_and_restart() -> None:
    g = Game(Level.parse("t", ["#######", "#@ $ .#", "#######"]))
    g.move("right")
    g.move("right")
    assert g.boxes == {(1, 4)}
    assert g.undo() and g.boxes == {(1, 3)} and g.player == (1, 2)
    g.restart()
    assert g.player == (1, 1) and not g.can_undo and g.moves == 0


def test_dead_squares_are_corners_away_from_targets() -> None:
    level = Level.parse("t", ["######", "#@   #", "# $ .#", "#    #", "######"])
    dead = dead_squares(level)
    assert (1, 1) in dead and (3, 1) in dead and (2, 4) not in dead


def test_app_plays_a_level(app_context: AppContext) -> None:
    import pygame

    from apps.crate_keeper.app import CrateKeeperApp
    from tests.conftest import tap

    app = CrateKeeperApp(app_context)
    app.on_enter()
    assert app.screen == "levels" and app.unlocked(0) and not app.unlocked(1)
    tap(app, pygame.K_SPACE)  # first key shows the cursor
    tap(app, pygame.K_SPACE)
    assert app.screen == "play" and app.index == 0
    tap(app, pygame.K_RIGHT)
    assert app.game.solved and app.menu is not None
    assert app.unlocked(1) and app.best["0"] == [1, 1]
