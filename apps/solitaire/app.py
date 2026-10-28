"""Solitaire UI: a felt table, vector-drawn cards, drag and drop and keyboard play."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

import pygame

from apps.solitaire.logic import FOUNDATIONS, TABLEAU, Card, Klondike, Suit
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas
from core.input import action_of
from core.registry import register_app
from core.theme import Color, Theme, lerp_color
from core.widgets import Button, ButtonMenu, SegmentedControl, draw_panel

ACCENT: Color = (190, 18, 60)
FELT: Color = (21, 83, 62)
FELT_DARK: Color = (16, 66, 50)
CARD_FACE: Color = (250, 250, 249)
CARD_EDGE: Color = (203, 213, 225)
RED_INK: Color = (220, 38, 38)
BLACK_INK: Color = (30, 41, 59)

CARD_W, CARD_H = 96, 134
GAP = 20
COLUMNS = 7
LEFT = (1280 - (COLUMNS * CARD_W + (COLUMNS - 1) * GAP)) // 2
TOP_Y = 92
TABLEAU_Y = TOP_Y + CARD_H + 28
BOTTOM = 708
DOWN_OFFSET = 12
UP_OFFSET = 30
WASTE_FAN = 22
DOUBLE_CLICK = 0.4
AUTO_STEP = 0.07

TOP_ROW = ("stock", "waste", "", *FOUNDATIONS)  # "" = the gap in column 2
DrawCount = Literal[1, 3]


@dataclass
class Drag:
    source: str
    index: int
    offset: pygame.Vector2
    pos: pygame.Vector2
    start: pygame.Vector2

    @property
    def moved(self) -> bool:
        return (self.pos - self.start).length() > 6


def column_x(col: int) -> int:
    return LEFT + col * (CARD_W + GAP)


@register_app
class SolitaireApp(BaseApp):
    """Klondike solitaire: build the four foundations from ace to king."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, FELT, theme.radius.md)
        w, h = rect.width * 0.42, rect.height * 0.58
        back = pygame.Rect(0, 0, round(w), round(h))
        back.center = (round(rect.x + rect.width * 0.4), round(rect.y + rect.height * 0.48))
        draw_card_back(surface, back, 4)
        face = back.move(round(rect.width * 0.2), round(rect.height * 0.08))
        draw.rounded_rect(surface, face, CARD_FACE, 4)
        draw_suit(surface, "hearts", face.center, face.width * 0.55, RED_INK)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        saved = self.data.get("draw_count", 1)
        self.draw_count: DrawCount = 3 if saved == 3 else 1
        t = self.theme
        right = column_x(COLUMNS - 1) + CARD_W
        self.new_btn = Button(
            t, (right - 110, 26, 110, 40), "New game", self._new_game, "primary", accent=ACCENT
        )
        self.undo_btn = Button(t, (right - 110 - 12 - 90, 26, 90, 40), "Undo", self._undo)
        self.finish_btn = Button(
            t,
            (right - 110 - 24 - 90 - 110, 26, 110, 40),
            "Finish",
            self._finish,
            "primary",
            accent=FELT,
        )
        self.draw_picker = SegmentedControl(
            t,
            (LEFT + 180, 26, 200, 40),
            ["Draw 1", "Draw 3"],
            0 if self.draw_count == 1 else 1,
            self._set_draw,
        )
        self.time = 0.0
        self._new_game()

    def _new_game(self) -> None:
        self.game = Klondike(random.Random(), self.draw_count)
        self.elapsed = 0.0
        self.started = False
        self.drag: Drag | None = None
        self.cursor: tuple[str, int] = ("stock", 0)
        self.held: tuple[str, int] | None = None  # keyboard pick-up
        self.keyboard = False
        self.autoplay = False
        self.auto_timer = 0.0
        self.last_click: tuple[str, int, float] | None = None
        self.won = False
        self.new_best = False
        self.menu: ButtonMenu | None = None
        self.confetti: list[list[float]] = []

    def restart(self) -> None:
        self._new_game()

    def _set_draw(self, index: int) -> None:
        self.draw_count = 1 if index == 0 else 3
        self.data["draw_count"] = self.draw_count
        self.data.save()
        self._new_game()

    @property
    def variant(self) -> str:
        return f"draw{self.draw_count}"

    def captures_pause(self) -> bool:
        return self.held is not None  # Esc drops the card you picked up instead

    # ------------------------------------------------------------------ actions
    def _undo(self) -> None:
        if not self.won and self.game.undo():
            self.autoplay = False

    def _finish(self) -> None:
        if self.game.can_autocomplete:
            self.autoplay = True

    def _changed(self) -> None:
        self.started = True
        if self.game.won and not self.won:
            self._on_won()

    def _on_won(self) -> None:
        self.won = True
        self.autoplay = False
        seconds = max(1, round(self.elapsed))
        self.new_best = self.submit_score(seconds, self.variant)
        self.unlock("win")
        if self.draw_count == 3:
            self.unlock("win_draw3")
        if seconds < 240:
            self.unlock("fast")
        rng = random.Random()
        self.confetti = [
            [
                rng.uniform(0, 1280),
                rng.uniform(-400, 0),
                rng.uniform(-40, 40),
                rng.uniform(80, 220),
                rng.random(),
            ]
            for _ in range(140)
        ]
        self.menu = ButtonMenu(
            self.theme,
            (640, 420),
            [("Deal again", self._new_game), ("Back to menu", self.exit_to_launcher)],
            accent=ACCENT,
        )

    def _draw_from_stock(self) -> None:
        if self.game.draw():
            self._changed()

    def _try_move(self, source: str, index: int, target: str) -> bool:
        if self.game.move(source, index, target):
            self._changed()
            return True
        return False

    def _send_home(self, pile: str) -> bool:
        if self.game.auto_move(pile) is not None:
            self._changed()
            return True
        return False

    # ------------------------------------------------------------------ geometry
    def pile_origin(self, pile: str) -> tuple[int, int]:
        if pile in TABLEAU:
            return column_x(TABLEAU.index(pile)), TABLEAU_Y
        return column_x(TOP_ROW.index(pile)), TOP_Y

    def _up_offset(self, pile: str) -> float:
        cards = self.game.piles[pile]
        down = sum(1 for c in cards if not c.face_up)
        up = len(cards) - down
        room = BOTTOM - TABLEAU_Y - CARD_H - down * DOWN_OFFSET
        return UP_OFFSET if up <= 1 else min(UP_OFFSET, room / (up - 1))

    def card_rect(self, pile: str, index: int) -> pygame.Rect:
        """Where card ``index`` of ``pile`` is drawn."""
        x, y = self.pile_origin(pile)
        cards = self.game.piles[pile]
        if pile in TABLEAU:
            up_offset = self._up_offset(pile)
            for card in cards[:index]:
                y += round(DOWN_OFFSET if not card.face_up else up_offset)
        elif pile == "waste":
            first_fanned = max(0, len(cards) - self.draw_count)
            x += max(0, index - first_fanned) * WASTE_FAN
        return pygame.Rect(x, y, CARD_W, CARD_H)

    def pile_rect(self, pile: str) -> pygame.Rect:
        """The area that accepts a drop onto ``pile``."""
        x, y = self.pile_origin(pile)
        cards = self.game.piles[pile]
        if pile in TABLEAU and cards:
            bottom = self.card_rect(pile, len(cards) - 1).bottom
            return pygame.Rect(x, y, CARD_W, bottom - y)
        return pygame.Rect(x, y, CARD_W, CARD_H)

    def card_at(self, pos: tuple[int, int]) -> tuple[str, int] | None:
        """The topmost card (or empty pile, index -1) under ``pos``."""
        for pile in (*TABLEAU, "waste", "stock", *FOUNDATIONS):
            cards = self.game.piles[pile]
            for i in range(len(cards) - 1, -1, -1):
                if self.card_rect(pile, i).collidepoint(pos):
                    return pile, i
            if not cards and self.pile_rect(pile).collidepoint(pos):
                return pile, -1
        return None

    def _drop_target(self, drag: Drag) -> str | None:
        """The pile the dragged cards overlap most (that would accept them)."""
        moving = pygame.Rect(0, 0, CARD_W, CARD_H)
        moving.topleft = (round(drag.pos.x - drag.offset.x), round(drag.pos.y - drag.offset.y))
        best, best_area = None, 0
        for pile in (*FOUNDATIONS, *TABLEAU):
            overlap = moving.clip(self.pile_rect(pile))
            area = overlap.width * overlap.height
            if area > best_area and self.game.can_move(drag.source, drag.index, pile):
                best, best_area = pile, area
        return best

    # ------------------------------------------------------------------ events
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.menu is not None:
            self.menu.handle_event(event)
            return
        for widget in (self.new_btn, self.undo_btn, self.draw_picker):
            if widget.handle_event(event):
                return
        if self.game.can_autocomplete and not self.autoplay and self.finish_btn.handle_event(event):
            return
        if self.autoplay:
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.keyboard = False
            self._mouse_down(event.pos)
        elif event.type == pygame.MOUSEMOTION and self.drag is not None:
            self.drag.pos = pygame.Vector2(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag is not None:
            self._mouse_up(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            hit = self.card_at(event.pos)
            if hit is not None:
                self._send_home(hit[0])  # right-click: send to a foundation
        else:
            self._handle_key(event)

    def _mouse_down(self, pos: tuple[int, int]) -> None:
        hit = self.card_at(pos)
        if hit is None:
            return
        pile, index = hit
        if pile == "stock":
            self._draw_from_stock()
            return
        cards = self.game.piles[pile]
        if index < 0 or not cards[index].face_up:
            return
        if pile in ("waste", *FOUNDATIONS):
            index = len(cards) - 1  # only the top card can be picked up
        rect = self.card_rect(pile, index)
        p = pygame.Vector2(pos)
        self.drag = Drag(pile, index, p - pygame.Vector2(rect.topleft), p, p)

    def _mouse_up(self, pos: tuple[int, int]) -> None:
        drag = self.drag
        assert drag is not None
        self.drag = None
        drag.pos = pygame.Vector2(pos)
        if drag.moved:
            target = self._drop_target(drag)
            if target is not None:
                self._try_move(drag.source, drag.index, target)
            return
        # A click: two in a row on the same card sends it to a foundation.
        key = (drag.source, drag.index)
        if (
            self.last_click
            and self.last_click[:2] == key
            and self.time - self.last_click[2] < DOUBLE_CLICK
        ):
            self.last_click = None
            if drag.index == len(self.game.piles[drag.source]) - 1:
                self._send_home(drag.source)
        else:
            self.last_click = (*key, self.time)

    def _handle_key(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            mods = event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META)
            if event.key == pygame.K_u or (event.key == pygame.K_z and mods):
                self._undo()
            elif event.key == pygame.K_n:
                self._new_game()
            elif event.key == pygame.K_d:
                self._draw_from_stock()
            elif event.key == pygame.K_f:
                self._send_home(self.cursor[0])
            elif event.key == pygame.K_a:
                self._finish()
            return
        action = action_of(event)
        if action is None:
            return
        if not self.keyboard:
            self.keyboard = True  # the first key press just shows the cursor
            return
        if action == "pause":
            self.held = None
        elif action == "action" and not getattr(event, "repeat", False):
            self._keyboard_select()
        elif action in ("left", "right"):
            self._move_cursor_horizontally(-1 if action == "left" else 1)
        elif action in ("up", "down"):
            self._move_cursor_vertically(-1 if action == "up" else 1)

    def _move_cursor_horizontally(self, step: int) -> None:
        pile, _ = self.cursor
        row = list(TABLEAU) if pile in TABLEAU else [p for p in TOP_ROW if p]
        i = max(0, min(len(row) - 1, row.index(pile) + step))
        self._set_cursor(row[i])

    def _move_cursor_vertically(self, step: int) -> None:
        pile, index = self.cursor
        cards = self.game.piles[pile]
        if pile in TABLEAU:
            first_up = next((i for i, c in enumerate(cards) if c.face_up), len(cards))
            if step < 0 and index > first_up:
                self.cursor = (pile, index - 1)
                return
            if step > 0 and index < len(cards) - 1:
                self.cursor = (pile, index + 1)
                return
            if step < 0:
                col = TABLEAU.index(pile)
                self._set_cursor(TOP_ROW[col] or "waste")
        elif step > 0:
            col = TOP_ROW.index(pile)
            self._set_cursor(TABLEAU[col])

    def _set_cursor(self, pile: str) -> None:
        self.cursor = (pile, max(0, len(self.game.piles[pile]) - 1))

    def _keyboard_select(self) -> None:
        pile, index = self.cursor
        if self.held is None:
            if pile == "stock":
                self._draw_from_stock()
                self._set_cursor("stock")
                return
            cards = self.game.piles[pile]
            if cards and cards[min(index, len(cards) - 1)].face_up:
                self.held = (pile, min(index, len(cards) - 1))
            return
        source, src_index = self.held
        self.held = None
        if pile == source:
            if src_index == len(self.game.piles[source]) - 1:
                self._send_home(source)  # pick up and put down on the same pile: send home
        elif self._try_move(source, src_index, pile):
            self._set_cursor(pile)

    # ------------------------------------------------------------------ frame
    def update(self, dt: float) -> None:
        self.time += dt
        for widget in (self.new_btn, self.undo_btn, self.draw_picker, self.finish_btn):
            widget.update(dt)
        self.undo_btn.enabled = self.game.can_undo and not self.won
        if self.menu is not None:
            self.menu.update(dt)
        for c in self.confetti:
            c[0] += c[2] * dt
            c[1] += c[3] * dt
        if self.started and not self.won:
            self.elapsed += dt
        if self.autoplay:
            self.auto_timer -= dt
            if self.auto_timer <= 0:
                self.auto_timer = AUTO_STEP
                if self.game.autocomplete_step() is None:
                    self.autoplay = False
                self._changed()
        pile, index = self.cursor
        self.cursor = (pile, min(index, max(0, len(self.game.piles[pile]) - 1)))

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        table = pygame.Rect(
            LEFT - 28, TOP_Y - 18, column_x(COLUMNS - 1) + CARD_W - LEFT + 56, BOTTOM - TOP_Y + 26
        )
        draw.rounded_rect(surface, table, FELT, t.radius.lg)
        self._draw_header(surface, t)

        dragging = set()
        if self.drag is not None and self.drag.moved:
            cards = self.game.piles[self.drag.source]
            dragging = {(self.drag.source, i) for i in range(self.drag.index, len(cards))}
        for pile in ("stock", "waste", *FOUNDATIONS, *TABLEAU):
            self._draw_pile(surface, pile, dragging)
        self._draw_cursor(surface)
        if dragging and self.drag is not None:
            d = self.drag
            target = self._drop_target(d)
            if target is not None:
                draw.rounded_rect(
                    surface, self.pile_rect(target).inflate(10, 10), (253, 224, 71), 12, 3
                )
            x, y = d.pos.x - d.offset.x, d.pos.y - d.offset.y
            for i, card in enumerate(self.game.piles[d.source][d.index :]):
                rect = pygame.Rect(round(x), round(y + i * UP_OFFSET), CARD_W, CARD_H)
                draw.shadow(surface, rect, 8, (0, 0, 0, 110), (0, 10), 14)
                draw_card(surface, rect, card, self.theme)

        for x, y, _, _, hue in self.confetti:
            if y < 760:
                color = (ACCENT, (253, 224, 71), (96, 165, 250), (74, 222, 128))[int(hue * 4)]
                gfx.rect(surface, color, (x, y, 7, 11), border_radius=2)
        if self.menu is not None:
            panel = pygame.Rect(0, 0, 380, self.menu.rect.height + 150)
            panel.midbottom = (640, self.menu.rect.bottom + 28)
            draw_panel(surface, panel, t)
            draw.text(
                surface,
                "You won!",
                t.font(t.size.heading, "bold"),
                p.text,
                (640, panel.y + 26),
                "midtop",
            )
            sub = (
                "New best time!"
                if self.new_best
                else f"{_clock(self.elapsed)} · {self.game.moves} moves"
            )
            draw.text(
                surface,
                sub,
                t.font(t.size.label, "semibold"),
                p.success if self.new_best else p.text_muted,
                (640, panel.y + 70),
                "midtop",
            )
            self.menu.draw(surface)

    def _draw_header(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        draw.text(
            surface, "Solitaire", t.font(t.size.heading, "bold"), p.text, (LEFT, 46), "midleft"
        )
        self.draw_picker.draw(surface)
        best = self.best_score(self.variant)
        stats = f"{_clock(self.elapsed)} · {self.game.moves} moves"
        if best:
            stats += f" · best {_clock(best.score)}"
        draw.text(
            surface,
            stats,
            t.font(t.size.label, "medium"),
            p.text_muted,
            (LEFT + 400, 46),
            "midleft",
        )
        if self.game.can_autocomplete and not self.autoplay and not self.won:
            self.finish_btn.draw(surface)
        self.undo_btn.draw(surface)
        self.new_btn.draw(surface)

    def _draw_pile(self, surface: Canvas, pile: str, hidden: set[tuple[str, int]]) -> None:
        cards = self.game.piles[pile]
        x, y = self.pile_origin(pile)
        slot = pygame.Rect(x, y, CARD_W, CARD_H)
        draw.rounded_rect(surface, slot, FELT_DARK, 8)
        draw.rounded_rect(surface, slot, lerp_color(FELT, (255, 255, 255), 0.18), 8, 2)
        if pile in FOUNDATIONS and not cards:
            draw.text(
                surface,
                "A",
                self.theme.font(34, "bold"),
                lerp_color(FELT, (255, 255, 255), 0.25),
                slot.center,
                "center",
            )
        elif pile == "stock" and not cards and self.game.piles["waste"]:
            gfx.circle(
                surface, lerp_color(FELT, (255, 255, 255), 0.3), slot.center, 22, 4
            )  # recycle
        if pile == "stock":
            if cards:
                for i in range(min(3, len(cards))):  # a hint of thickness
                    draw_card_back(surface, slot.move(-i * 2, -i * 2), 8)
            return
        start = 0
        if pile == "waste":
            start = max(0, len(cards) - max(self.draw_count, 1) - 1)
        elif pile in FOUNDATIONS:
            start = max(0, len(cards) - 2)
        for i in range(start, len(cards)):
            if (pile, i) in hidden:
                break
            rect = self.card_rect(pile, i)
            draw.shadow(surface, rect, 8, (0, 0, 0, 60), (0, 2), 4)
            if cards[i].face_up:
                draw_card(surface, rect, cards[i], self.theme)
            else:
                draw_card_back(surface, rect, 8)
        if self.held is not None and self.held[0] == pile:
            for i in range(self.held[1], len(cards)):
                draw.rounded_rect(surface, self.card_rect(pile, i), (253, 224, 71), 8, 3)

    def _draw_cursor(self, surface: Canvas) -> None:
        if not self.keyboard:
            return
        pile, index = self.cursor
        cards = self.game.piles[pile]
        rect = self.card_rect(pile, index) if cards else self.pile_rect(pile)
        if pile in TABLEAU and cards:
            rect = rect.union(self.card_rect(pile, len(cards) - 1))
        draw.rounded_rect(surface, rect.inflate(10, 10), (96, 165, 250), 12, 3)


def _clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


# ---------------------------------------------------------------------- card art
def draw_card(surface: Canvas, rect: pygame.Rect, card: Card, theme: Theme) -> None:
    """A face-up card (card faces stay light in both themes, like real cards)."""
    ink = RED_INK if card.red else BLACK_INK
    draw.rounded_rect(surface, rect, CARD_FACE, 8)
    draw.rounded_rect(surface, rect, CARD_EDGE, 8, 1)
    draw.text(surface, card.label, theme.font(22, "bold"), ink, (rect.x + 9, rect.y + 6))
    draw_suit(surface, card.suit, (rect.x + 18, rect.y + 44), 15, ink)
    draw.text(
        surface,
        card.label,
        theme.font(15, "bold"),
        ink,
        (rect.right - 8, rect.bottom - 6),
        "bottomright",
    )
    if card.rank > 10:
        # Court cards: a framed panel with a large letter.
        inner = pygame.Rect(rect.x + 34, rect.y + 24, rect.width - 46, rect.height - 56)
        draw.rounded_rect(surface, inner, lerp_color(CARD_FACE, ink, 0.1), 6)
        draw.text(surface, card.label, theme.font(30, "bold"), ink, inner.center, "center")
        draw_suit(surface, card.suit, (inner.centerx, inner.bottom - 12), 12, ink)
    else:
        draw_suit(
            surface,
            card.suit,
            (rect.centerx + 8, rect.centery + 10),
            38 if card.rank == 1 else 30,
            ink,
        )


def draw_card_back(surface: Canvas, rect: pygame.Rect, radius: int) -> None:
    draw.rounded_rect(surface, rect, CARD_FACE, radius)
    inner = rect.inflate(-8, -8)
    draw.rounded_rect(surface, inner, ACCENT, max(2, radius - 3))
    clip = surface.get_clip()
    surface.set_clip(inner.clip(clip))
    stripe = lerp_color(ACCENT, (255, 255, 255), 0.18)
    for k in range(-inner.height, inner.width, 9):
        gfx.line(
            surface, stripe, (inner.x + k, inner.y), (inner.x + k + inner.height, inner.bottom), 2
        )
    surface.set_clip(clip)


def draw_suit(
    surface: Canvas, suit: Suit, center: tuple[float, float], size: float, color: Color
) -> None:
    """Vector suit symbols (fonts can't be relied on to include them)."""
    x, y = center
    s = size / 2
    if suit == "diamonds":
        gfx.polygon(surface, color, [(x, y - s), (x + s * 0.72, y), (x, y + s), (x - s * 0.72, y)])
    elif suit == "hearts":
        for dx in (-0.45, 0.45):
            gfx.circle(surface, color, (x + dx * s, y - s * 0.3), s * 0.52)
        gfx.polygon(
            surface,
            color,
            [(x - s * 0.95, y - s * 0.15), (x + s * 0.95, y - s * 0.15), (x, y + s * 0.95)],
        )
    elif suit == "spades":
        for dx in (-0.45, 0.45):
            gfx.circle(surface, color, (x + dx * s, y + s * 0.2), s * 0.5)
        gfx.polygon(
            surface,
            color,
            [(x - s * 0.93, y + s * 0.1), (x + s * 0.93, y + s * 0.1), (x, y - s * 0.98)],
        )
        gfx.polygon(
            surface, color, [(x, y + s * 0.2), (x - s * 0.32, y + s), (x + s * 0.32, y + s)]
        )
    else:  # clubs
        r = s * 0.42
        for dx, dy in ((0, -0.48), (-0.5, 0.12), (0.5, 0.12)):
            gfx.circle(surface, color, (x + dx * s, y + dy * s), r)
        gfx.polygon(surface, color, [(x, y), (x - s * 0.32, y + s), (x + s * 0.32, y + s)])
