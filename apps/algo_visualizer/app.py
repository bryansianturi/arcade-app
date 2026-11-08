"""Algorithm Visualizer UI: a pathfinding grid you draw on, and sorting bars.

The algorithm buttons are built from the registries in :mod:`.logic`, so new
algorithms in :mod:`.sorting` or :mod:`.pathfinding` show up automatically.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Callable

import pygame

from apps.algo_visualizer import pathfinding as _pathfinding  # noqa: F401 (registers)
from apps.algo_visualizer import sorting as _sorting  # noqa: F401 (registers)
from apps.algo_visualizer.logic import (
    PATHFINDERS,
    SORTS,
    Cell,
    Grid,
    PathRun,
    SortRun,
    Swap,
    Write,
    make_values,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color, readable_on
from core.widgets import Button, SegmentedControl, Slider, draw_panel

ACCENT: Color = (147, 51, 234)
CELL = 24
COLS, ROWS = 37, 24
AREA = pygame.Rect(48, 92, COLS * CELL, ROWS * CELL)
SIDE = pygame.Rect(960, 92, 272, 584)
ORDERS = ("random", "reversed", "nearly")
START_COLOR: Color = (34, 197, 94)
GOAL_COLOR: Color = (239, 68, 68)
FRONTIER_COLOR: Color = (245, 158, 11)
PATH_COLOR: Color = (250, 204, 21)
MUD_COLOR: Color = (146, 104, 62)


def steps_per_second(speed: float) -> float:
    """The speed slider (0–100) on a log scale: 2 to about 630 steps a second."""
    return 2 * 10 ** (speed / 40)


@register_app
class AlgoVisualizerApp(BaseApp):
    """Pathfinding on a grid you draw, and sorting on bars, one step at a time."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        u = rect.width / 8
        for i, h in enumerate((2, 4, 3, 5, 6)):
            bar = pygame.Rect(
                round(rect.x + (1.3 + i * 1.15) * u),
                round(rect.bottom - (1.3 + h) * u),
                round(u * 0.8),
                round(h * u),
            )
            draw.rounded_rect(surface, bar, (255, 255, 255) if i != 2 else PATH_COLOR, 2)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        self.rng = random.Random()
        self.mode = 1 if self.data.get("mode") == 1 else 0
        self.tabs = SegmentedControl(
            t,
            (1232 - 340, 30, 340, 40),
            ["Pathfinding", "Sorting"],
            self.mode,
            self._set_mode,
            accent=ACCENT,
        )
        names = list(PATHFINDERS)
        saved = self.data.get("pathfinder")
        self.pathfinder = saved if saved in PATHFINDERS else ("A*" if "A*" in names else names[0])
        saved = self.data.get("sort")
        self.sort_name = saved if saved in SORTS else next(iter(SORTS))
        speed = self.data.get("speed")
        self.speed = float(speed) if isinstance(speed, int | float) and 0 <= speed <= 100 else 45.0
        size = self.data.get("size")
        self.size = size if isinstance(size, int) and 8 <= size <= 120 else 48
        self.order = "random"

        self.grid = Grid(COLS, ROWS, (5, ROWS // 2), (COLS - 6, ROWS // 2))
        self.path_run: PathRun | None = None
        self.sort_run: SortRun | None = None
        self.values = make_values(self.size, self.order, self.rng)
        self.original = list(self.values)  # what Reset puts back after a sort
        self.running = False
        self.accumulator = 0.0
        self.done_t = 0.0  # seconds since a sort finished (for the green sweep)
        self.paint: str | None = None  # "wall", "mud" or "erase" while dragging
        self.dragging: str | None = None  # "start" or "goal"
        self.last_cell: Cell | None = None
        self.tool = 0  # 0 walls, 1 mud

        x = SIDE.x + 24
        half = 108
        self.path_buttons = [
            Button(
                t,
                (x + (i % 2) * 116, SIDE.y + 40 + (i // 2) * 40, half, 34),
                name,
                self._pathfinder_setter(name),
                font_size=t.size.caption,
            )
            for i, name in enumerate(PATHFINDERS)
        ]
        self.sort_buttons = [
            Button(
                t,
                (x + (i % 2) * 116, SIDE.y + 40 + (i // 2) * 40, half, 34),
                name,
                self._sort_setter(name),
                font_size=t.size.caption,
            )
            for i, name in enumerate(SORTS)
        ]
        rows = max(len(PATHFINDERS), len(SORTS)) + 1
        y = SIDE.y + 40 + (rows // 2) * 40 + 8
        self.run_btn = Button(
            t, (x, y, half, 40), "Run", self._toggle_run, "primary", accent=ACCENT
        )
        self.step_btn = Button(t, (x + 116, y, half, 40), "Step", self._step)
        self.reset_btn = Button(t, (x, y + 48, half, 36), "Reset", self._reset)
        self.finish_btn = Button(t, (x + 116, y + 48, half, 36), "Finish", self._finish)
        self.controls_y = y + 100
        self.speed_slider = Slider(
            t,
            (x - 6, self.controls_y + 18, 236, 28),
            0,
            100,
            self.speed,
            self._set_speed,
            accent=ACCENT,
        )
        y2 = self.controls_y + 66
        self.tool_tabs = SegmentedControl(
            t, (x, y2 + 18, 224, 34), ["Walls", "Mud ×5"], 0, self._set_tool, accent=ACCENT
        )
        self.maze_btn = Button(
            t, (x, y2 + 62, half, 34), "Maze", self._maze, font_size=t.size.caption
        )
        self.random_btn = Button(
            t, (x + 116, y2 + 62, half, 34), "Scatter", self._scatter, font_size=t.size.caption
        )
        self.clear_btn = Button(
            t,
            (x, y2 + 102, 224, 34),
            "Clear grid",
            self._clear_grid,
            "ghost",
            font_size=t.size.caption,
        )
        self.size_slider = Slider(
            t, (x - 6, y2 + 18, 236, 28), 8, 120, self.size, self._set_size, accent=ACCENT
        )
        self.order_tabs = SegmentedControl(
            t,
            (x, y2 + 66, 224, 34),
            ["Random", "Reverse", "Nearly"],
            0,
            self._set_order,
            accent=ACCENT,
        )
        self.shuffle_btn = Button(
            t, (x, y2 + 108, 224, 34), "Shuffle", self._shuffle, font_size=t.size.caption
        )
        self.stats_y = y2 + 160

    def on_exit(self) -> None:
        self.data["mode"] = self.mode
        self.data["pathfinder"] = self.pathfinder
        self.data["sort"] = self.sort_name
        self.data["speed"] = self.speed
        self.data["size"] = self.size
        self.data.save()

    def restart(self) -> None:
        self._reset()

    def _set_mode(self, index: int) -> None:
        self.tabs.index = index
        self.mode = index
        self.running = False

    # ------------------------------------------------------------------ shared controls
    def _widgets(self) -> list[Button | Slider | SegmentedControl]:
        common: list[Button | Slider | SegmentedControl] = [
            self.run_btn,
            self.step_btn,
            self.reset_btn,
            self.finish_btn,
            self.speed_slider,
        ]
        if self.mode == 0:
            return [
                *self.path_buttons,
                *common,
                self.tool_tabs,
                self.maze_btn,
                self.random_btn,
                self.clear_btn,
            ]
        return [*self.sort_buttons, *common, self.size_slider, self.order_tabs, self.shuffle_btn]

    def _ensure_run(self) -> PathRun | SortRun:
        if self.mode == 0:
            if self.path_run is None:
                self.path_run = PathRun(self.grid, PATHFINDERS[self.pathfinder])
            return self.path_run
        if self.sort_run is None:
            self.sort_run = SortRun(self.values, SORTS[self.sort_name])
            self.done_t = 0.0
        return self.sort_run

    def _current_run(self) -> PathRun | SortRun | None:
        return self.path_run if self.mode == 0 else self.sort_run

    def _toggle_run(self) -> None:
        run = self._current_run()
        if run is not None and run.done:
            self._reset()
        self._ensure_run()
        self.running = not self.running
        self.accumulator = 0.0

    def _step(self) -> None:
        self.running = False
        self._ensure_run().advance()

    def _finish(self) -> None:
        self.running = False
        self._ensure_run().finish()

    def _reset(self) -> None:
        """Forget the current run (and, for sorting, put the bars back how they were)."""
        self.running = False
        if self.mode == 0:
            self.path_run = None
        else:
            self.values = list(self.original)
            self.sort_run = None

    def _set_speed(self, value: float) -> None:
        self.speed = value

    # ------------------------------------------------------------------ pathfinding
    def _pathfinder_setter(self, name: str) -> Callable[[], None]:
        def choose() -> None:
            self.pathfinder = name
            self.path_run = None
            self.running = False

        return choose

    def _set_tool(self, index: int) -> None:
        self.tool_tabs.index = index
        self.tool = index

    def _maze(self) -> None:
        self.path_run = None
        self.grid.maze(self.rng)

    def _scatter(self) -> None:
        self.path_run = None
        self.grid.random_walls(self.rng)

    def _clear_grid(self) -> None:
        self.path_run = None
        self.grid.clear()

    def _cell_at(self, pos: tuple[int, int]) -> Cell | None:
        if not AREA.collidepoint(pos):
            return None
        return (pos[0] - AREA.x) // CELL, (pos[1] - AREA.y) // CELL

    def _paint(self, cell: Cell) -> None:
        g = self.grid
        if cell in (g.start, g.goal) or self.paint is None:
            return
        g.walls.discard(cell)
        g.mud.discard(cell)
        if self.paint == "wall":
            g.walls.add(cell)
        elif self.paint == "mud":
            g.mud.add(cell)

    def _press_grid(self, pos: tuple[int, int], button: int) -> None:
        cell = self._cell_at(pos)
        if cell is None:
            return
        self.running = False
        self.path_run = None
        if button == 1 and cell == self.grid.start:
            self.dragging = "start"
        elif button == 1 and cell == self.grid.goal:
            self.dragging = "goal"
        else:
            kind = "wall" if self.tool == 0 else "mud"
            already = cell in (self.grid.walls if kind == "wall" else self.grid.mud)
            self.paint = "erase" if button != 1 or already else kind
            self._paint(cell)
        self.last_cell = cell

    def _drag_grid(self, pos: tuple[int, int]) -> None:
        clamped = (
            min(max(pos[0], AREA.x), AREA.right - 1),
            min(max(pos[1], AREA.y), AREA.bottom - 1),
        )
        cell = self._cell_at(clamped)
        if cell is None or cell == self.last_cell:
            return
        g = self.grid
        if self.dragging is not None:
            other = g.goal if self.dragging == "start" else g.start
            if cell != other:
                g.walls.discard(cell)
                g.mud.discard(cell)
                if self.dragging == "start":
                    g.start = cell
                else:
                    g.goal = cell
        else:
            (x0, y0), (x1, y1) = self.last_cell or cell, cell
            n = max(abs(x1 - x0), abs(y1 - y0), 1)
            for i in range(n + 1):
                self._paint((round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n)))
        self.last_cell = cell

    # ------------------------------------------------------------------ sorting
    def _sort_setter(self, name: str) -> Callable[[], None]:
        def choose() -> None:
            self._reset()
            self.sort_name = name

        return choose

    def _set_size(self, value: float) -> None:
        self.size = int(value)
        self._shuffle()

    def _set_order(self, index: int) -> None:
        self.order_tabs.index = index
        self.order = ORDERS[index]
        self._shuffle()

    def _shuffle(self) -> None:
        self.running = False
        self.sort_run = None
        self.values = make_values(self.size, self.order, self.rng)
        self.original = list(self.values)

    # ------------------------------------------------------------------ input
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.tabs.handle_event(event):
            return
        for widget in self._widgets():
            if widget.handle_event(event):
                return
        if self.mode == 0 and event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            self._press_grid(event.pos, event.button)
        elif event.type == pygame.MOUSEMOTION and (self.paint or self.dragging):
            self._drag_grid(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP:
            self.paint = self.dragging = None
            self.last_cell = None
        elif is_action(event, "action", repeat=False):
            self._toggle_run()
        elif is_action(event, "right"):
            self._step()
        elif is_action(event, "up") or is_action(event, "down"):
            self.speed_slider.set_value(self.speed + (5 if is_action(event, "up") else -5))
        elif event.type == pygame.KEYDOWN:
            self._shortcut(event.key)

    def _shortcut(self, key: int) -> None:
        names = list(PATHFINDERS if self.mode == 0 else SORTS)
        if key == pygame.K_TAB:
            self._set_mode(1 - self.mode)
        elif key == pygame.K_r:
            self._reset()
        elif key == pygame.K_f:
            self._finish()
        elif pygame.K_1 <= key < pygame.K_1 + len(names):
            name = names[key - pygame.K_1]
            (self._pathfinder_setter if self.mode == 0 else self._sort_setter)(name)()
        elif self.mode == 0 and key == pygame.K_m:
            self._maze()
        elif self.mode == 0 and key == pygame.K_c:
            self._clear_grid()
        elif self.mode == 1 and key == pygame.K_s:
            self._shuffle()

    def update(self, dt: float) -> None:
        self.tabs.update(dt)
        for widget in self._widgets():
            widget.update(dt)
        dragging = self.paint is not None or self.dragging is not None
        if dragging and not any(pygame.mouse.get_pressed()):
            self.paint = self.dragging = None
        run = self._current_run()
        if self.running and run is not None:
            self.accumulator += dt * steps_per_second(self.speed)
            budget = min(int(self.accumulator), 2000)
            self.accumulator -= budget
            for _ in range(budget):
                if not run.advance():
                    self.running = False
                    break
        if self.sort_run is not None and self.sort_run.done:
            self.done_t += dt
        finished = run is not None and run.done
        self.run_btn.text = "Pause" if self.running else ("Again" if finished else "Run")
        self.step_btn.enabled = self.finish_btn.enabled = not finished
        for button in self.path_buttons:
            button.variant = "primary" if button.text == self.pathfinder else "secondary"
            button.accent = ACCENT
        for button in self.sort_buttons:
            button.variant = "primary" if button.text == self.sort_name else "secondary"
            button.accent = ACCENT

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(surface, "Algorithm Visualizer", t.font(t.size.heading, "bold"), p.text, (48, 30))
        self.tabs.draw(surface)
        if self.mode == 0:
            self._draw_grid(surface, t)
            hint = (
                "Drag to draw · right-drag to erase · drag the green start or red goal · "
                "Space run · → step · F finish · R reset · M maze · 1–3 algorithm · Tab sorting"
            )
        else:
            self._draw_bars(surface, t)
            hint = (
                "Space run · → step · F finish · R reset · S shuffle · ↑/↓ speed · "
                "1–4 algorithm · Tab pathfinding"
            )
        self._draw_side(surface, t)
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (640, 696), "center")

    def _draw_grid(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        g = self.grid
        run = self.path_run
        draw.shadow(surface, AREA, t.radius.md, p.shadow, (0, 6), 14)
        surface.fill(p.surface, AREA)
        wall = lerp_color(p.text, p.bg, 0.15)
        mud = MUD_COLOR if t.mode == "light" else lerp_color(MUD_COLOR, p.bg, 0.2)
        light_visit = lerp_color(p.surface, ACCENT, 0.25)
        deep_visit = lerp_color(p.surface, ACCENT, 0.7)
        count = max(1, len(run.order)) if run else 1
        for y in range(ROWS):
            for x in range(COLS):
                cell = (x, y)
                color: Color | None = None
                if cell in g.walls:
                    color = wall
                elif run is not None and cell in run.visited:
                    color = lerp_color(deep_visit, light_visit, run.order.get(cell, 0) / count)
                    if cell in g.mud:
                        color = lerp_color(color, mud, 0.55)
                elif run is not None and cell in run.frontier:
                    color = lerp_color(p.surface, FRONTIER_COLOR, 0.6)
                elif cell in g.mud:
                    color = mud
                if color is not None:
                    surface.fill(color, (AREA.x + x * CELL, AREA.y + y * CELL, CELL, CELL))
        line = lerp_color(p.surface, p.text_muted, 0.18)
        for x in range(COLS + 1):
            gfx.line(surface, line, (AREA.x + x * CELL, AREA.y), (AREA.x + x * CELL, AREA.bottom))
        for y in range(ROWS + 1):
            gfx.line(surface, line, (AREA.x, AREA.y + y * CELL), (AREA.right, AREA.y + y * CELL))
        if run is not None and len(run.path) > 1:
            points = [
                (AREA.x + x * CELL + CELL / 2, AREA.y + y * CELL + CELL / 2) for x, y in run.path
            ]
            for a, b in itertools.pairwise(points):
                draw.thick_line(surface, PATH_COLOR, a, b, 6)
            for pt in points:
                gfx.circle(surface, PATH_COLOR, pt, 3)
        if run is not None and run.current is not None:
            cx, cy = run.current
            gfx.rect(surface, ACCENT, (AREA.x + cx * CELL, AREA.y + cy * CELL, CELL, CELL), 2)
        for cell, color, label in ((g.start, START_COLOR, "S"), (g.goal, GOAL_COLOR, "G")):
            center = (AREA.x + cell[0] * CELL + CELL / 2, AREA.y + cell[1] * CELL + CELL / 2)
            gfx.circle(surface, color, center, CELL * 0.42)
            draw.text(surface, label, t.font(13, "bold"), readable_on(color), center, "center")

    def _draw_bars(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw.shadow(surface, AREA, t.radius.md, p.shadow, (0, 6), 14)
        draw.rounded_rect(surface, AREA, p.surface, t.radius.md)
        run = self.sort_run
        n = len(self.values)
        inner = AREA.inflate(-32, -32)
        width = inner.width / n
        gap = 1 if width < 6 else 2
        hot = set(run.highlighted()) if run is not None else set()
        last = run.last if run is not None else None
        hot_color = GOAL_COLOR if isinstance(last, Swap | Write) else FRONTIER_COLOR
        base = lerp_color(p.surface, ACCENT, 0.75)
        sweep = n * min(1.0, self.done_t / 0.8) if run is not None and run.done else -1
        for i, value in enumerate(self.values):
            h = inner.height * value / n
            bar = pygame.FRect(inner.x + i * width, inner.bottom - h, max(1.0, width - gap), h)
            color = base
            if i in hot:
                color = hot_color
            elif i < sweep:
                color = START_COLOR
            surface.fill(color, bar)

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw_panel(surface, SIDE, t)
        x = SIDE.x + 24
        caption = t.font(t.size.caption, "semibold")
        draw.text(surface, "ALGORITHM", caption, p.text_muted, (x, SIDE.y + 22), "midleft")
        for widget in self._widgets():
            widget.draw(surface)
        draw.text(surface, "SPEED", caption, p.text_muted, (x, self.controls_y + 8), "midleft")
        draw.text(
            surface,
            f"{steps_per_second(self.speed):.0f} steps/s",
            t.font(t.size.caption),
            p.text_muted,
            (SIDE.right - 24, self.controls_y + 8),
            "midright",
        )
        y2 = self.controls_y + 66
        if self.mode == 0:
            draw.text(surface, "DRAW", caption, p.text_muted, (x, y2 + 8), "midleft")
            run = self.path_run
            rows: list[tuple[str, str]] = [
                ("Visited", str(len(run.visited)) if run else "—"),
                ("Steps", str(run.steps) if run else "—"),
            ]
            if run is not None and run.done:
                if run.found:
                    rows += [
                        ("Path length", str(len(run.path) - 1)),
                        ("Path cost", str(self.grid.path_cost(list(run.path)))),
                    ]
                else:
                    rows.append(("Result", "No path"))
        else:
            draw.text(surface, "BARS", caption, p.text_muted, (x, y2 + 8), "midleft")
            draw.text(
                surface,
                str(self.size),
                t.font(t.size.caption),
                p.text_muted,
                (SIDE.right - 24, y2 + 8),
                "midright",
            )
            draw.text(surface, "START FROM", caption, p.text_muted, (x, y2 + 56), "midleft")
            sort_run = self.sort_run
            rows = [
                ("Comparisons", f"{sort_run.comparisons:,}" if sort_run else "—"),
                ("Swaps", f"{sort_run.swaps:,}" if sort_run else "—"),
                ("Writes", f"{sort_run.writes:,}" if sort_run else "—"),
            ]
        top = self.stats_y if self.mode == 0 else self.stats_y + 4
        for i, (name, value) in enumerate(rows):
            y = top + i * 24
            draw.text(surface, name, t.font(t.size.label), p.text_muted, (x, y), "midleft")
            draw.text(
                surface,
                value,
                t.font(t.size.label, "bold"),
                p.text,
                (SIDE.right - 24, y),
                "midright",
            )
