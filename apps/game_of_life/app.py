"""Game of Life UI: a paintable grid, playback controls, rules and pattern stamps."""

from __future__ import annotations

import random
from collections.abc import Callable

import pygame

from apps.game_of_life.logic import PATTERNS, RULES, Cell, Life, Pattern, rotate
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, mouse_pos
from core.input import is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, Slider, Toggle, draw_panel

ACCENT: Color = (22, 163, 74)
CELL = 10
COLS, ROWS = 88, 58
GRID = pygame.Rect(48, 92, COLS * CELL, ROWS * CELL)
SIDE = pygame.Rect(952, 92, 280, 580)
MAX_SPEED = 30


def line_cells(a: Cell, b: Cell) -> list[Cell]:
    """Cells on the straight line from ``a`` to ``b`` (so fast drags leave no gaps)."""
    (x0, y0), (x1, y1) = a, b
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    return [
        (round(x0 + (x1 - x0) * i / steps), round(y0 + (y1 - y0) * i / steps))
        for i in range(steps + 1)
    ]


@register_app
class GameOfLifeApp(BaseApp):
    """Conway's Game of Life and a few other rules on a wrap-around grid."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        u = rect.width / 6
        for x, y in ((2, 1), (3, 2), (1, 3), (2, 3), (3, 3)):  # a glider
            cell = pygame.Rect(
                round(rect.x + x * u + 1), round(rect.y + y * u + 1), round(u - 2), round(u - 2)
            )
            draw.rounded_rect(surface, cell, (255, 255, 255), 2)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        self.rng = random.Random()
        rule_name = self.data.get("rule")
        rule = next((r for r in RULES if r.name == rule_name), RULES[0])
        self.life = Life(COLS, ROWS, rule, wrap=self.data.get("wrap") is not False)
        saved = self.data.get("cells")
        if isinstance(saved, list):
            for item in saved:
                if (
                    isinstance(item, list)
                    and len(item) == 2
                    and all(isinstance(v, int) for v in item)
                ):
                    self.life.set((item[0], item[1]), True)
        else:
            self._stamp_center(PATTERNS[4])  # start with the glider gun: something to watch
        speed = self.data.get("speed")
        self.speed = speed if isinstance(speed, int) and 1 <= speed <= MAX_SPEED else 10
        self.running = False
        self.accumulator = 0.0
        self.painting: bool | None = None  # the state a drag paints, while dragging
        self.last_cell: Cell | None = None
        self.stamp: tuple[Pattern, frozenset[Cell]] | None = None
        x, half = SIDE.x + 24, 112
        self.play_btn = Button(
            t, (x, SIDE.y + 76, 232, 44), "Play", self._toggle_run, "primary", accent=ACCENT
        )
        self.step_btn = Button(t, (x, SIDE.y + 128, half, 40), "Step", self._step)
        self.random_btn = Button(t, (x + 120, SIDE.y + 128, half, 40), "Random", self._randomize)
        self.clear_btn = Button(t, (x, SIDE.y + 176, half, 40), "Clear", self._clear)
        self.wrap_toggle = Toggle(
            t,
            (SIDE.right - 24 - Toggle.WIDTH, SIDE.y + 182),
            self.life.wrap,
            self._set_wrap,
            accent=ACCENT,
        )
        self.speed_slider = Slider(
            t,
            (x - 6, SIDE.y + 250, 244, 28),
            1,
            MAX_SPEED,
            self.speed,
            self._set_speed,
            accent=ACCENT,
        )
        self.rule_buttons = [
            Button(
                t,
                (x + (i % 2) * 120, SIDE.y + 312 + (i // 2) * 38, half, 32),
                rule.name,
                self._rule_setter(i),
                font_size=t.size.caption,
            )
            for i, rule in enumerate(RULES)
        ]
        self.pattern_buttons = [
            Button(
                t,
                (x + (i % 2) * 120, SIDE.y + 414 + (i // 2) * 38, half, 32),
                p.name,
                self._pattern_picker(p),
                font_size=12,
            )
            for i, p in enumerate(PATTERNS)
        ]
        self._grid_lines: tuple[tuple[float, str], Canvas] | None = None

    def on_exit(self) -> None:
        self.data["cells"] = [list(c) for c in sorted(self.life.cells)]
        self.data["rule"] = self.life.rule.name
        self.data["wrap"] = self.life.wrap
        self.data["speed"] = self.speed
        self.data.save()

    def on_pause(self) -> None:
        self.painting = None

    def restart(self) -> None:
        self._clear()

    def _buttons(self) -> list[Button]:
        return [
            self.play_btn,
            self.step_btn,
            self.random_btn,
            self.clear_btn,
            *self.rule_buttons,
            *self.pattern_buttons,
        ]

    # ------------------------------------------------------------------ actions
    def _toggle_run(self) -> None:
        self.running = not self.running
        self.accumulator = 0.0

    def _step(self) -> None:
        self.running = False
        self.life.step()

    def _randomize(self) -> None:
        self.life.randomize(self.rng, 0.28)

    def _clear(self) -> None:
        self.life.clear()
        self.running = False

    def _set_wrap(self, on: bool) -> None:
        self.life.wrap = on

    def _set_speed(self, value: float) -> None:
        self.speed = int(value)

    def _rule_setter(self, index: int) -> Callable[[], None]:
        def set_rule() -> None:
            self.life.rule = RULES[index]

        return set_rule

    def _pattern_picker(self, pattern: Pattern) -> Callable[[], None]:
        return lambda: self._pick_pattern(pattern)

    def _pick_pattern(self, pattern: Pattern) -> None:
        same = self.stamp is not None and self.stamp[0] == pattern
        self.stamp = None if same else (pattern, pattern.cells)

    def _stamp_center(self, pattern: Pattern) -> None:
        w, h = pattern.size
        self.life.stamp(pattern.cells, ((COLS - w) // 2, (ROWS - h) // 2))

    def _stamp_origin(self, pos: tuple[int, int]) -> Cell | None:
        if self.stamp is None:
            return None
        cell = self._cell_at(pos)
        if cell is None:
            return None
        cells = self.stamp[1]
        w = max(x for x, _ in cells) + 1
        h = max(y for _, y in cells) + 1
        return cell[0] - w // 2, cell[1] - h // 2

    def _cell_at(self, pos: tuple[int, int]) -> Cell | None:
        if not GRID.collidepoint(pos):
            return None
        return (pos[0] - GRID.x) // CELL, (pos[1] - GRID.y) // CELL

    # ------------------------------------------------------------------ input
    def captures_pause(self) -> bool:
        return self.stamp is not None

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.stamp is not None and is_action(event, "pause", repeat=False):
            self.stamp = None
            return
        for widget in (*self._buttons(), self.wrap_toggle, self.speed_slider):
            if widget.handle_event(event):
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            self._press(event.pos, event.button)
        elif event.type == pygame.MOUSEMOTION and self.painting is not None:
            self._drag(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP:
            self.painting = None
            self.last_cell = None
        elif is_action(event, "action", repeat=False):
            self._toggle_run()
        elif is_action(event, "right"):
            self._step()
        elif is_action(event, "up") or is_action(event, "down"):
            self.speed_slider.set_value(self.speed + (1 if is_action(event, "up") else -1))
        elif event.type == pygame.KEYDOWN:
            self._shortcut(event.key)

    def _press(self, pos: tuple[int, int], button: int) -> None:
        cell = self._cell_at(pos)
        if cell is None:
            return
        if self.stamp is not None:
            origin = self._stamp_origin(pos)
            if button == 1 and origin is not None:
                self.life.stamp(self.stamp[1], origin)
            else:
                self.stamp = None
            return
        self.painting = self.life.toggle(cell) if button == 1 else False
        if not self.painting:
            self.life.set(cell, False)
        self.last_cell = cell

    def _drag(self, pos: tuple[int, int]) -> None:
        clamped = (
            min(max(pos[0], GRID.x), GRID.right - 1),
            min(max(pos[1], GRID.y), GRID.bottom - 1),
        )
        cell = self._cell_at(clamped)
        if cell is None or self.painting is None:
            return
        for c in line_cells(self.last_cell or cell, cell):
            self.life.set(c, self.painting)
        self.last_cell = cell

    def _shortcut(self, key: int) -> None:
        if key == pygame.K_c:
            self._clear()
        elif key == pygame.K_r:
            if self.stamp is not None:
                self.stamp = (self.stamp[0], rotate(self.stamp[1]))
            else:
                self._randomize()
        elif key == pygame.K_w:
            self.wrap_toggle.toggle()
        elif pygame.K_1 <= key < pygame.K_1 + len(PATTERNS):
            self._pick_pattern(PATTERNS[key - pygame.K_1])

    def update(self, dt: float) -> None:
        for widget in (*self._buttons(), self.wrap_toggle, self.speed_slider):
            widget.update(dt)
        if self.painting is not None and not any(pygame.mouse.get_pressed()):
            self.painting = None
            self.last_cell = None
        if self.running:
            self.accumulator += dt
            interval = 1 / self.speed
            steps = 0
            while self.accumulator >= interval and steps < 4:  # never spiral on slow frames
                self.life.step()
                self.accumulator -= interval
                steps += 1
            self.accumulator = min(self.accumulator, interval)
        self.play_btn.text = "Pause" if self.running else "Play"
        for button, rule in zip(self.rule_buttons, RULES, strict=True):
            button.variant = "primary" if rule == self.life.rule else "secondary"
            button.accent = ACCENT
        for button, pattern in zip(self.pattern_buttons, PATTERNS, strict=True):
            chosen = self.stamp is not None and self.stamp[0] == pattern
            button.variant = "primary" if chosen else "secondary"
            button.accent = ACCENT

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(surface, "Game of Life", t.font(t.size.heading, "bold"), p.text, (48, 30))
        draw.text(
            surface,
            f"{self.life.rule.name} · {self.life.rule.notation}",
            t.font(t.size.label),
            p.text_muted,
            (GRID.right, 46),
            "midright",
        )
        self._draw_grid(surface, t)
        self._draw_side(surface, t)
        if self.stamp is not None:
            hint = "Click to place · R rotate · right-click or Esc to stop placing"
        else:
            hint = (
                "Click or drag to draw · right-drag to erase · Space play · → step · "
                "↑/↓ speed · R random · C clear · W wrap · 1–8 patterns"
            )
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (640, 696), "center")

    def _cells_image(self, surface: Canvas, t: Theme) -> Canvas:
        """Live cells drawn one pixel each, then scaled up to the grid (fast at any density)."""
        p = t.palette
        small = pygame.Surface((COLS, ROWS))
        small.fill(p.surface)
        alive = ACCENT if t.mode == "light" else (74, 222, 128)
        for cell in self.life.cells:
            small.set_at(cell, alive)
        size = surface.px_rect(GRID).size
        return Canvas(pygame.transform.scale(small, size), surface.scale)

    def _lines(self, surface: Canvas, t: Theme) -> Canvas:
        key = (surface.scale, t.mode)
        if self._grid_lines is None or self._grid_lines[0] != key:
            layer = Canvas.new(GRID.size, alpha=True)
            color = (*t.palette.bg, 255)
            for x in range(COLS + 1):
                gfx.line(layer, color, (x * CELL, 0), (x * CELL, GRID.height), 1)
            for y in range(ROWS + 1):
                gfx.line(layer, color, (0, y * CELL), (GRID.width, y * CELL), 1)
            self._grid_lines = (key, layer)
        return self._grid_lines[1]

    def _draw_grid(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw.shadow(surface, GRID, t.radius.md, p.shadow, (0, 6), 14)
        surface.blit(self._cells_image(surface, t), GRID.topleft)
        surface.blit(self._lines(surface, t), GRID.topleft)
        origin = self._stamp_origin(mouse_pos())
        if self.stamp is not None and origin is not None:
            ghost = lerp_color(p.surface, ACCENT, 0.55)
            for x, y in self.stamp[1]:
                cx, cy = origin[0] + x, origin[1] + y
                if self.life.wrap:
                    cx, cy = cx % COLS, cy % ROWS
                if 0 <= cx < COLS and 0 <= cy < ROWS:
                    gfx.rect(
                        surface,
                        ghost,
                        (GRID.x + cx * CELL + 1, GRID.y + cy * CELL + 1, CELL - 1, CELL - 1),
                    )
        if not self.life.wrap:
            draw.rounded_rect(surface, GRID.inflate(4, 4), p.border, t.radius.sm, 2)

    def _draw_side(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw_panel(surface, SIDE, t)
        x = SIDE.x + 24
        for i, (name, value) in enumerate(
            (("Generation", self.life.generation), ("Population", len(self.life.cells)))
        ):
            y = SIDE.y + 24 + i * 24
            draw.text(surface, name, t.font(t.size.label), p.text_muted, (x, y), "midleft")
            draw.text(
                surface,
                f"{value:,}",
                t.font(t.size.body, "bold"),
                p.text,
                (SIDE.right - 24, y),
                "midright",
            )
        for button in self._buttons():
            if button not in self.rule_buttons and button not in self.pattern_buttons:
                button.draw(surface)
        draw.text(
            surface,
            "Wrap",
            t.font(t.size.label),
            p.text,
            (SIDE.x + 148, self.wrap_toggle.rect.centery),
            "midleft",
        )
        self.wrap_toggle.draw(surface)
        caption = t.font(t.size.caption, "semibold")
        draw.text(surface, "SPEED", caption, p.text_muted, (x, SIDE.y + 236), "midleft")
        draw.text(
            surface,
            f"{self.speed} gen/s",
            t.font(t.size.caption),
            p.text_muted,
            (SIDE.right - 24, SIDE.y + 236),
            "midright",
        )
        self.speed_slider.draw(surface)
        draw.text(surface, "RULE", caption, p.text_muted, (x, SIDE.y + 298), "midleft")
        for button in self.rule_buttons:
            button.draw(surface)
        draw.text(surface, "PATTERNS", caption, p.text_muted, (x, SIDE.y + 400), "midleft")
        for button in self.pattern_buttons:
            button.draw(surface)
