"""Memory Match UI: flipping cards with vector symbols, size picker and stats."""

from __future__ import annotations

import math
import random

import pygame

from apps.memory_match.logic import LAYOUTS, SIZES, MemoryGame, Size
from core import draw
from core.base_app import AppMeta, BaseApp, format_score
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, SegmentedControl

ACCENT: Color = (234, 88, 12)
BOARD_AREA = pygame.Rect(60, 60, 780, 600)
SIDE_X = 900
FLIP_SECONDS = 0.18
MISMATCH_SECONDS = 0.8
GAP = 16

SYMBOL_COLORS: tuple[Color, ...] = (
    (56, 189, 248),
    (251, 113, 133),
    (250, 204, 21),
    (74, 222, 128),
    (167, 139, 250),
    (251, 146, 60),
)
SHAPES = (
    "circle",
    "square",
    "triangle",
    "diamond",
    "star",
    "heart",
    "hexagon",
    "ring",
    "cross",
    "moon",
    "bolt",
    "drop",
)


def draw_symbol(
    surface: pygame.Surface, symbol: int, center: tuple[float, float], r: float, card: Color
) -> None:
    """Draw symbol ``symbol``: a shape (cycles every 12) in a colour (cycles every 6).

    ``card`` is the colour behind the symbol, used to cut the moon's crescent.
    """
    shape = SHAPES[symbol % len(SHAPES)]
    color = SYMBOL_COLORS[(symbol + symbol // len(SHAPES) * 3) % len(SYMBOL_COLORS)]
    cx, cy = center
    v = pygame.Vector2(center)

    def poly(
        n: int, radius: float, start: float = -90, inner: float | None = None
    ) -> list[pygame.Vector2]:
        pts = []
        for i in range(n * (2 if inner else 1)):
            rad = inner if inner and i % 2 else radius
            pts.append(
                v + pygame.Vector2(rad, 0).rotate(start + i * 360 / (n * (2 if inner else 1)))
            )
        return pts

    if shape == "circle":
        pygame.draw.circle(surface, color, center, r * 0.8)
    elif shape == "square":
        pygame.draw.rect(
            surface,
            color,
            (cx - r * 0.7, cy - r * 0.7, r * 1.4, r * 1.4),
            border_radius=round(r * 0.2),
        )
    elif shape == "triangle":
        pygame.draw.polygon(surface, color, poly(3, r * 0.95, -90))
    elif shape == "diamond":
        pygame.draw.polygon(
            surface, color, [(cx, cy - r), (cx + r * 0.7, cy), (cx, cy + r), (cx - r * 0.7, cy)]
        )
    elif shape == "star":
        pygame.draw.polygon(surface, color, poly(5, r, -90, inner=r * 0.42))
    elif shape == "heart":
        k = r * 0.45
        pygame.draw.circle(surface, color, (cx - k, cy - k * 0.5), k * 1.05)
        pygame.draw.circle(surface, color, (cx + k, cy - k * 0.5), k * 1.05)
        pygame.draw.polygon(
            surface,
            color,
            [(cx - r * 0.92, cy - k * 0.2), (cx + r * 0.92, cy - k * 0.2), (cx, cy + r * 0.9)],
        )
    elif shape == "hexagon":
        pygame.draw.polygon(surface, color, poly(6, r * 0.85, 0))
    elif shape == "ring":
        pygame.draw.circle(surface, color, center, r * 0.8, max(3, round(r * 0.28)))
    elif shape == "cross":
        w = r * 0.5
        pygame.draw.rect(surface, color, (cx - w / 2, cy - r * 0.85, w, r * 1.7), border_radius=4)
        pygame.draw.rect(surface, color, (cx - r * 0.85, cy - w / 2, r * 1.7, w), border_radius=4)
    elif shape == "moon":
        pygame.draw.circle(surface, color, center, r * 0.8)
        pygame.draw.circle(surface, card, (cx + r * 0.38, cy - r * 0.25), r * 0.68)
    elif shape == "bolt":
        pts = [(0.2, -1), (-0.55, 0.12), (-0.02, 0.12), (-0.25, 1), (0.55, -0.15), (0.03, -0.15)]
        pygame.draw.polygon(surface, color, [(cx + x * r, cy + y * r) for x, y in pts])
    elif shape == "drop":
        pygame.draw.circle(surface, color, (cx, cy + r * 0.25), r * 0.62)
        pygame.draw.polygon(
            surface,
            color,
            [(cx, cy - r * 0.95), (cx + r * 0.6, cy + r * 0.1), (cx - r * 0.6, cy + r * 0.1)],
        )
    if symbol >= len(
        SHAPES
    ):  # second set: add a dot so same-shaped symbols differ by more than colour
        pygame.draw.circle(surface, (255, 255, 255), center, max(3, r * 0.14))


@register_app
class MemoryMatchApp(BaseApp):
    """Flip two cards at a time and find every pair."""

    meta = AppMeta(
        id="memory_match",
        name="Memory Match",
        description="Flip cards and find every matching pair.",
        category="game",
        accent=ACCENT,
        tracks_scores=True,
        score_order="lower",
        score_format="time",
        variants=SIZES,
    )

    @classmethod
    def draw_icon(cls, surface: pygame.Surface, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        w = rect.width * 0.36
        for i, symbol in enumerate((4, None)):
            card = pygame.Rect(0, 0, w, w * 1.3)
            card.center = (rect.centerx + (i * 2 - 1) * w * 0.55, rect.centery)
            pygame.draw.rect(
                surface,
                (255, 255, 255) if symbol is not None else (124, 45, 18),
                card,
                border_radius=4,
            )
            if symbol is not None:
                draw_symbol(surface, symbol, card.center, w * 0.32, (255, 255, 255))

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        saved = self.data.get("size")
        self.size: Size = saved if saved in SIZES else "medium"
        t = self.theme
        self.picker = SegmentedControl(
            t,
            (SIDE_X, 284, 320, 40),
            ["Easy", "Medium", "Hard"],
            SIZES.index(self.size),
            self._set_size,
            accent=ACCENT,
        )
        self.new_btn = Button(
            t, (SIDE_X, 560, 320, 52), "New game", self._new_game, "primary", accent=ACCENT
        )
        self.time = 0.0
        self._new_game()

    def restart(self) -> None:
        self._new_game()

    def _set_size(self, index: int) -> None:
        self.picker.index = index
        self.size = SIZES[index]
        self.data["size"] = self.size
        self.data.save()
        self._new_game()

    def _new_game(self) -> None:
        self.game = MemoryGame.for_size(self.size, random.Random())
        self.flip_t: dict[int, float] = {}  # card -> time it last changed side
        self.mismatch_at: float | None = None
        self.new_best = False
        self.recorded = False
        self.cursor = 0
        self.keyboard_nav = False
        cols, rows = LAYOUTS[self.size]
        card_w = min(
            (BOARD_AREA.width - GAP * (cols - 1)) // cols,
            round((BOARD_AREA.height - GAP * (rows - 1)) / rows / 1.25),
        )
        card_h = round(card_w * 1.25)
        total_w = cols * card_w + (cols - 1) * GAP
        total_h = rows * card_h + (rows - 1) * GAP
        x0 = BOARD_AREA.centerx - total_w // 2
        y0 = BOARD_AREA.centery - total_h // 2
        self.rects = [
            pygame.Rect(
                x0 + (i % cols) * (card_w + GAP), y0 + (i // cols) * (card_h + GAP), card_w, card_h
            )
            for i in range(cols * rows)
        ]

    # ------------------------------------------------------------------ input
    def _flip(self, index: int) -> None:
        before = set(self.game.open)
        result = self.game.flip(index)
        if result == "ignored":
            return
        for hidden in before - set(self.game.open) - self.game.matched:
            self.flip_t[hidden] = self.time  # auto-hidden mismatch flips back
        self.flip_t[index] = self.time
        self.mismatch_at = self.time if result == "mismatch" else None
        if self.game.won and not self.recorded:
            self.recorded = True
            self.new_best = self.submit_score(max(1, round(self.game.elapsed)), self.size)

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.picker.handle_event(event) or self.new_btn.handle_event(event):
            return
        cols, _ = LAYOUTS[self.size]
        if event.type == pygame.MOUSEMOTION:
            self.keyboard_nav = False
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(self.rects):
                if rect.collidepoint(event.pos):
                    self._flip(i)
        elif event.type == pygame.KEYDOWN:
            moves = {
                pygame.K_LEFT: -1,
                pygame.K_RIGHT: 1,
                pygame.K_UP: -cols,
                pygame.K_DOWN: cols,
                pygame.K_a: -1,
                pygame.K_d: 1,
                pygame.K_w: -cols,
                pygame.K_s: cols,
            }
            if event.key in moves:
                if self.keyboard_nav:
                    target = self.cursor + moves[event.key]
                    if 0 <= target < len(self.rects):
                        self.cursor = target
                self.keyboard_nav = True
            elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self.keyboard_nav = True
                self._flip(self.cursor)
            elif event.key == pygame.K_n:
                self._new_game()

    def update(self, dt: float) -> None:
        self.time += dt
        self.game.tick(dt)
        self.picker.update(dt)
        self.new_btn.update(dt)
        if self.mismatch_at is not None and self.time - self.mismatch_at > MISMATCH_SECONDS:
            for i in self.game.open:
                self.flip_t[i] = self.time
            self.game.hide_mismatch()
            self.mismatch_at = None

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: pygame.Surface) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        mouse = pygame.mouse.get_pos()
        for i, rect in enumerate(self.rects):
            k = min(1.0, (self.time - self.flip_t.get(i, -10.0)) / FLIP_SECONDS)
            # Width shrinks to 0 at the halfway point, where the face swaps.
            showing_face = self.game.face_up(i) if k >= 0.5 else not self.game.face_up(i)
            width = rect.width * abs(math.cos(k * math.pi))
            card = pygame.Rect(0, 0, max(2, round(width)), rect.height)
            card.center = rect.center
            hovered = (
                rect.collidepoint(mouse) and not self.keyboard_nav and not self.game.face_up(i)
            )
            if hovered:
                card = card.move(0, -3)
            draw.shadow(surface, card, t.radius.md, p.shadow, (0, 4), 8)
            if showing_face:
                matched = i in self.game.matched
                face = p.surface if not matched else lerp_color(p.surface, ACCENT, 0.12)
                pygame.draw.rect(surface, face, card, border_radius=t.radius.md)
                if matched:
                    pygame.draw.rect(surface, ACCENT, card, 2, border_radius=t.radius.md)
                if width > rect.width * 0.4:
                    draw_symbol(
                        surface,
                        self.game.cards[i],
                        card.center,
                        min(rect.width, rect.height) * 0.28,
                        face,
                    )
            else:
                back = lerp_color(ACCENT, p.bg, 0.35)
                pygame.draw.rect(surface, back, card, border_radius=t.radius.md)
                inner = card.inflate(-14, -14)
                if inner.width > 4:
                    pygame.draw.rect(
                        surface,
                        lerp_color(back, (255, 255, 255), 0.18),
                        inner,
                        2,
                        border_radius=t.radius.sm,
                    )
                    pygame.draw.circle(
                        surface,
                        lerp_color(back, (255, 255, 255), 0.25),
                        card.center,
                        min(inner.width, 24) / 3,
                    )
            if self.keyboard_nav and i == self.cursor:
                pygame.draw.rect(
                    surface, p.text, rect.inflate(8, 8), 3, border_radius=t.radius.md + 3
                )
        self._draw_side(surface, t)

    def _draw_side(self, surface: pygame.Surface, t: Theme) -> None:
        p = t.palette
        g = self.game
        draw.text(surface, "Memory Match", t.font(t.size.heading, "bold"), p.text, (SIDE_X, 60))
        if g.won:
            status, color = (
                ("New best time!", p.success) if self.new_best else ("All pairs found!", p.success)
            )
        else:
            status, color = f"{g.pairs_left} pairs to go", p.text_muted
        draw.text(surface, status, t.font(t.size.title, "semibold"), color, (SIDE_X, 106))
        best = self.best_score(self.size)
        boxes = (
            ("Time", format_score(g.elapsed, "time")),
            ("Moves", str(g.moves)),
            ("Best", format_score(best.score, "time") if best else "—"),
        )
        for i, (label, value) in enumerate(boxes):
            box = pygame.Rect(SIDE_X + i * 108, 156, 100, 84)
            draw.rounded_rect(surface, box, p.surface_alt, t.radius.md)
            draw.text(
                surface,
                label.upper(),
                t.font(t.size.caption, "semibold"),
                p.text_muted,
                (box.centerx, box.y + 14),
                "midtop",
            )
            draw.text(
                surface,
                value,
                t.font(t.size.title, "bold"),
                p.text,
                (box.centerx, box.y + 38),
                "midtop",
            )
        draw.text(
            surface, "BOARD SIZE", t.font(t.size.caption, "semibold"), p.text_muted, (SIDE_X, 262)
        )
        self.picker.draw(surface)
        self.new_btn.draw(surface)
        draw.text(
            surface,
            "Click cards, or arrows + Space · N new game",
            t.font(t.size.caption),
            p.text_muted,
            (SIDE_X, 626),
        )
