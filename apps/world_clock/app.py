"""World Clock UI: local time, city clocks with an add-city picker, and countdowns."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pygame

from apps.world_clock.logic import (
    CITY_BY_NAME,
    DEFAULT_CITIES,
    MAX_CITIES,
    MAX_EVENT_NAME,
    MAX_EVENTS,
    City,
    Event,
    ago_text,
    city_time,
    countdown_text,
    day_text,
    difference_text,
    has_dst_rules,
    is_daytime,
    make_event,
    search_cities,
    utc_offset_text,
)
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, mouse_pos
from core.input import is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color, readable_on
from core.widgets import Button, SegmentedControl, TextInput, draw_panel

ACCENT: Color = (8, 145, 178)
HERO = pygame.Rect(48, 92, 1184, 136)
GRID_TOP, CARD_W, CARD_H, GAP = 252, 378, 200, 25
FORM = pygame.Rect(48, 92, 380, 584)
EVENTS = pygame.Rect(452, 92, 780, 584)
PICKER = pygame.Rect(400, 96, 480, 560)
PICKER_ROW = 44
PICKER_ROWS = 8
DAY_FACE: Color = (248, 250, 252)
NIGHT_FACE: Color = (30, 41, 59)


def clock_text(moment: datetime, twelve_hour: bool, seconds: bool = False) -> str:
    if twelve_hour:
        hour = moment.hour % 12 or 12
        text = f"{hour}:{moment.minute:02d}" + (f":{moment.second:02d}" if seconds else "")
        return f"{text} {'AM' if moment.hour < 12 else 'PM'}"
    return moment.strftime("%H:%M:%S" if seconds else "%H:%M")


def draw_analog(surface: Canvas, center: tuple[float, float], r: float, moment: datetime) -> None:
    """A small clock face: light by day, dark by night, with a second hand."""
    day = is_daytime(moment)
    face = DAY_FACE if day else NIGHT_FACE
    ink = (30, 41, 59) if day else (226, 232, 240)
    gfx.circle(surface, face, center, r)
    gfx.circle(surface, lerp_color(face, ink, 0.25), center, r, 2)
    for i in range(12):
        a = i * math.tau / 12
        inner = r * (0.78 if i % 3 == 0 else 0.86)
        start = (center[0] + math.sin(a) * inner, center[1] - math.cos(a) * inner)
        end = (center[0] + math.sin(a) * r * 0.92, center[1] - math.cos(a) * r * 0.92)
        gfx.line(surface, lerp_color(face, ink, 0.6 if i % 3 == 0 else 0.35), start, end, 2)
    seconds = moment.second + moment.microsecond / 1e6
    minutes = moment.minute + seconds / 60
    hours = moment.hour % 12 + minutes / 60
    for turn, length, width, color in (
        (hours / 12, 0.5, 5, ink),
        (minutes / 60, 0.74, 3, ink),
        (seconds / 60, 0.8, 1.5, ACCENT),
    ):
        a = turn * math.tau
        end = (center[0] + math.sin(a) * r * length, center[1] - math.cos(a) * r * length)
        draw.thick_line(surface, color, center, end, width)
    gfx.circle(surface, ACCENT, center, 4)


@register_app
class WorldClockApp(BaseApp):
    """Clocks for up to six cities, and countdowns to named events."""

    #: Injectable clock (tests replace it); must return a timezone-aware datetime.
    now: Callable[[], datetime] = staticmethod(lambda: datetime.now(UTC))

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        r = rect.width * 0.32
        white = (255, 255, 255)
        c = rect.center
        gfx.circle(surface, white, c, r, 3)
        gfx.ellipse(surface, white, pygame.Rect(c[0] - r * 0.45, c[1] - r, r * 0.9, r * 2), 2)
        gfx.line(surface, white, (c[0] - r, c[1]), (c[0] + r, c[1]), 2)
        gfx.line(surface, white, (c[0], c[1] - r), (c[0], c[1] + r), 2)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        saved = self.data.get("cities")
        names = saved if isinstance(saved, list) else list(DEFAULT_CITIES)
        self.cities: list[City] = []
        for name in names:
            if name in CITY_BY_NAME and CITY_BY_NAME[name] not in self.cities:
                self.cities.append(CITY_BY_NAME[name])
        self.cities = self.cities[:MAX_CITIES]
        raw_events = self.data.get("events")
        loaded = [Event.from_dict(e) for e in raw_events] if isinstance(raw_events, list) else []
        self.events: list[Event] = [e for e in loaded if e is not None][:MAX_EVENTS]
        self.twelve_hour = self.data.get("twelve_hour") is True
        self.tab = 1 if self.data.get("tab") == 1 else 0
        self.tabs = SegmentedControl(
            t,
            (1232 - 300, 30, 300, 40),
            ["Clocks", "Countdowns"],
            self.tab,
            self._set_tab,
            accent=ACCENT,
        )
        self.format_btn = Button(
            t, (HERO.right - 24 - 120, HERO.y + 24, 120, 40), "", self._toggle_format
        )
        # Countdown form.
        x, w = FORM.x + 24, FORM.width - 48
        self.name_input = TextInput(
            t, (x, FORM.y + 96, w, 48), "Birthday, trip, launch…", max_length=MAX_EVENT_NAME
        )
        self.date_input = TextInput(t, (x, FORM.y + 186, w, 48), "YYYY-MM-DD", max_length=10)
        self.time_input = TextInput(t, (x, FORM.y + 276, w, 48), "HH:MM (optional)", max_length=5)
        self.inputs = [self.name_input, self.date_input, self.time_input]
        self.add_btn = Button(
            t, (x, FORM.y + 352, w, 52), "Add countdown", self._add_event, "primary", accent=ACCENT
        )
        self.new_year_btn = Button(
            t, (x, FORM.bottom - 72, (w - 12) // 2, 44), "New Year", self._preset_new_year, "ghost"
        )
        self.tomorrow_btn = Button(
            t,
            (x + (w + 12) // 2, FORM.bottom - 72, (w - 12) // 2, 44),
            "Tomorrow 9:00",
            self._preset_tomorrow,
            "ghost",
        )
        self.form_error = ""
        # Add-city picker.
        self.picking = False
        self.search = TextInput(
            t, (PICKER.x + 24, PICKER.y + 72, PICKER.width - 48, 44), "Search cities", max_length=24
        )
        self.picker_scroll = 0
        self.picker_index = 0

    def on_exit(self) -> None:
        self._save()

    def restart(self) -> None:
        self.picking = False

    def _save(self) -> None:
        self.data["cities"] = [c.name for c in self.cities]
        self.data["events"] = [e.to_dict() for e in self.events]
        self.data["twelve_hour"] = self.twelve_hour
        self.data["tab"] = self.tab
        self.data.save()

    def _set_tab(self, index: int) -> None:
        self.tabs.index = index
        self.tab = index
        self.picking = False
        for box in self.inputs:
            box.focused = False
        if index == 1 and not self.events and not self.name_input.text:
            self.name_input.focus()

    def _toggle_format(self) -> None:
        self.twelve_hour = not self.twelve_hour
        self._save()

    # ------------------------------------------------------------------ clocks
    def _card_rects(self) -> list[pygame.Rect]:
        return [
            pygame.Rect(
                HERO.x + (i % 3) * (CARD_W + GAP),
                GRID_TOP + (i // 3) * (CARD_H + GAP),
                CARD_W,
                CARD_H,
            )
            for i in range(MAX_CITIES)
        ]

    def _remove_rect(self, card: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(card.right - 44, card.y + 12, 32, 32)

    def _open_picker(self) -> None:
        self.picking = True
        self.search.set_text("")
        self.search.focus()
        self.picker_scroll = 0
        self.picker_index = 0

    def _choices(self) -> list[City]:
        return search_cities(self.search.text, tuple(self.cities))

    def _choice_rects(self) -> list[tuple[City, pygame.Rect]]:
        choices = self._choices()[self.picker_scroll : self.picker_scroll + PICKER_ROWS]
        return [
            (
                c,
                pygame.Rect(
                    PICKER.x + 16,
                    PICKER.y + 132 + i * PICKER_ROW,
                    PICKER.width - 32,
                    PICKER_ROW - 4,
                ),
            )
            for i, c in enumerate(choices)
        ]

    def _add_city(self, city: City) -> None:
        if len(self.cities) < MAX_CITIES and city not in self.cities:
            self.cities.append(city)
            self._save()
        self.picking = False

    # ------------------------------------------------------------------ countdowns
    def _local_zone(self) -> datetime:
        return self.now().astimezone()

    def _add_event(self) -> None:
        if len(self.events) >= MAX_EVENTS:
            self.form_error = f"Up to {MAX_EVENTS} countdowns; remove one first."
            return
        local = self._local_zone()
        result = make_event(
            self.name_input.text, self.date_input.text, self.time_input.text, local.tzinfo or UTC
        )
        if isinstance(result, str):
            self.form_error = result
            return
        self.form_error = ""
        self.events.append(result)
        self.events.sort(key=lambda e: e.at)
        for box in self.inputs:
            box.set_text("")
            box.focused = False
        self._save()

    def _preset_new_year(self) -> None:
        year = self._local_zone().year + 1
        self.name_input.set_text(f"New Year {year}")
        self.date_input.set_text(f"{year}-01-01")
        self.time_input.set_text("00:00")

    def _preset_tomorrow(self) -> None:
        tomorrow = (self._local_zone() + timedelta(days=1)).date()
        if not self.name_input.text:
            self.name_input.set_text("Tomorrow morning")
        self.date_input.set_text(tomorrow.isoformat())
        self.time_input.set_text("09:00")

    def _event_rects(self) -> list[pygame.Rect]:
        return [
            pygame.Rect(EVENTS.x + 16, EVENTS.y + 72 + i * 62, EVENTS.width - 32, 56)
            for i in range(len(self.events))
        ]

    # ------------------------------------------------------------------ input
    def uses_text_input(self) -> bool:
        if self.picking:
            return True
        return self.tab == 1 and any(box.focused for box in self.inputs)

    def captures_pause(self) -> bool:
        return self.picking

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.picking:
            self._handle_picker(event)
            return
        if self.tabs.handle_event(event):
            return
        if self.tab == 0:
            self._handle_clocks(event)
        else:
            self._handle_countdowns(event)

    def _handle_picker(self, event: pygame.event.Event) -> None:
        choices = self._choices()
        if is_action(event, "pause", repeat=False):
            self.picking = False
        elif is_action(event, "action", repeat=False):
            if choices:
                self._add_city(choices[min(self.picker_index, len(choices) - 1)])
        elif is_action(event, "up") or is_action(event, "down"):
            step = -1 if is_action(event, "up") else 1
            self.picker_index = max(0, min(len(choices) - 1, self.picker_index + step))
            if self.picker_index < self.picker_scroll:
                self.picker_scroll = self.picker_index
            elif self.picker_index >= self.picker_scroll + PICKER_ROWS:
                self.picker_scroll = self.picker_index - PICKER_ROWS + 1
        elif event.type == pygame.MOUSEWHEEL:
            top = max(0, len(choices) - PICKER_ROWS)
            self.picker_scroll = max(0, min(top, self.picker_scroll - event.y))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not PICKER.collidepoint(event.pos):
                self.picking = False
                return
            for city, rect in self._choice_rects():
                if rect.collidepoint(event.pos):
                    self._add_city(city)
                    return
        elif event.type == pygame.KEYDOWN and self.input.action_for_key(event.key) == "pause":
            return  # handled as the pause action
        if self.picking and self.search.handle_event(event):
            self.picker_index = 0
            self.picker_scroll = 0
        self.search.focused = True

    def _handle_clocks(self, event: pygame.event.Event) -> None:
        if self.format_btn.handle_event(event):
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, card in enumerate(self._card_rects()):
                if not card.collidepoint(event.pos):
                    continue
                if i < len(self.cities):
                    if self._remove_rect(card).collidepoint(event.pos):
                        del self.cities[i]
                        self._save()
                elif i == len(self.cities):
                    self._open_picker()
                return
        elif is_action(event, "action", repeat=False) or (
            event.type == pygame.KEYDOWN and event.key == pygame.K_a
        ):
            if len(self.cities) < MAX_CITIES:
                self._open_picker()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_h:
            self._toggle_format()
        elif is_action(event, "right") or is_action(event, "left"):
            self._set_tab(1)

    def _handle_countdowns(self, event: pygame.event.Event) -> None:
        focused = next((i for i, box in enumerate(self.inputs) if box.focused), None)
        if focused is not None:
            if is_action(event, "action", repeat=False):
                self._add_event()
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
                step = -1 if event.mod & pygame.KMOD_SHIFT else 1
                self.inputs[focused].focused = False
                self.inputs[(focused + step) % len(self.inputs)].focus()
                return
        for widget in (*self.inputs, self.add_btn, self.new_year_btn, self.tomorrow_btn):
            if widget.handle_event(event):
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(self._event_rects()):
                if self._remove_rect(rect).collidepoint(event.pos):
                    del self.events[i]
                    self._save()
                    return
        elif focused is None and (is_action(event, "left") or is_action(event, "right")):
            self._set_tab(0)
        elif focused is None and event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            self.name_input.focus()

    def update(self, dt: float) -> None:
        self.tabs.update(dt)
        self.format_btn.text = "24-hour" if self.twelve_hour else "12-hour"
        widgets = (
            [self.search]
            if self.picking
            else [self.format_btn]
            if self.tab == 0
            else [*self.inputs, self.add_btn, self.new_year_btn, self.tomorrow_btn]
        )
        for widget in widgets:
            widget.update(dt)
        self.add_btn.enabled = len(self.events) < MAX_EVENTS

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(surface, "World Clock", t.font(t.size.heading, "bold"), p.text, (48, 30))
        self.tabs.draw(surface)
        now = self.now()
        if self.tab == 0:
            self._draw_clocks(surface, t, now)
            hint = "Click + or press Space to add a city · H 12/24-hour · hover a card to remove it"
        else:
            self._draw_countdowns(surface, t, now)
            hint = "Tab next field · Enter add · times are in your local time zone"
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (640, 700), "center")
        if self.picking:
            self._draw_picker(surface, t, now)

    def _draw_clocks(self, surface: Canvas, t: Theme, now: datetime) -> None:
        p = t.palette
        local = now.astimezone()
        draw_panel(surface, HERO, t)
        draw.text(
            surface,
            "LOCAL TIME",
            t.font(t.size.caption, "semibold"),
            p.text_muted,
            (HERO.x + 28, HERO.y + 22),
        )
        shown = draw.text(
            surface,
            clock_text(local, self.twelve_hour, seconds=True),
            t.font(56, "bold"),
            p.text,
            (HERO.x + 26, HERO.y + 40),
        )
        draw.text(
            surface,
            local.strftime("%A %d %B %Y").replace(" 0", " "),
            t.font(t.size.body),
            p.text,
            (shown.right + 28, HERO.y + 62),
        )
        draw.text(
            surface,
            utc_offset_text(local.utcoffset()),
            t.font(t.size.label),
            p.text_muted,
            (shown.right + 28, HERO.y + 88),
        )
        self.format_btn.draw(surface)

        mouse = mouse_pos()
        cards = self._card_rects()
        for city, card in zip(self.cities, cards, strict=False):
            there = city_time(city, now)
            draw_panel(surface, card, t)
            draw_analog(surface, (card.x + 86, card.centery), 62, there)
            x = card.x + 172
            draw.text(surface, city.name, t.font(t.size.title, "bold"), p.text, (x, card.y + 34))
            draw.text(
                surface,
                clock_text(there, self.twelve_hour),
                t.font(t.size.heading, "bold"),
                p.text,
                (x, card.y + 68),
            )
            draw.text(
                surface,
                f"{day_text(local, there)} · {difference_text(local, there)}",
                t.font(t.size.label),
                p.text_muted,
                (x, card.y + 116),
            )
            note = utc_offset_text(there.utcoffset())
            if not has_dst_rules(city):
                note += " · no DST data"
            draw.text(surface, note, t.font(t.size.caption), p.text_muted, (x, card.y + 142))
            if card.collidepoint(mouse):
                self._draw_remove(surface, t, self._remove_rect(card))
        if len(self.cities) < MAX_CITIES:
            card = cards[len(self.cities)]
            hover = card.collidepoint(mouse)
            draw.rounded_rect(
                surface, card, p.surface_hover if hover else p.surface_alt, t.radius.lg
            )
            draw.rounded_rect(surface, card, p.border, t.radius.lg, 2)
            cx, cy = card.centerx, card.centery - 14
            gfx.circle(surface, ACCENT, (cx, cy), 24)
            draw.thick_line(surface, readable_on(ACCENT), (cx - 10, cy), (cx + 10, cy), 3)
            draw.thick_line(surface, readable_on(ACCENT), (cx, cy - 10), (cx, cy + 10), 3)
            draw.text(
                surface,
                "Add a city",
                t.font(t.size.body, "semibold"),
                p.text,
                (cx, cy + 46),
                "center",
            )

    def _draw_remove(self, surface: Canvas, t: Theme, rect: pygame.Rect) -> None:
        p = t.palette
        over = rect.collidepoint(mouse_pos())
        if over:
            draw.rounded_rect(surface, rect, lerp_color(p.surface, p.danger, 0.18), t.radius.sm)
        color = p.danger if over else p.text_muted
        (cx, cy), r = rect.center, 6
        draw.thick_line(surface, color, (cx - r, cy - r), (cx + r, cy + r), 2)
        draw.thick_line(surface, color, (cx - r, cy + r), (cx + r, cy - r), 2)

    def _draw_picker(self, surface: Canvas, t: Theme, now: datetime) -> None:
        p = t.palette
        draw.overlay(surface, p.overlay)
        draw_panel(surface, PICKER, t)
        draw.text(
            surface,
            "Add a city",
            t.font(t.size.title, "bold"),
            p.text,
            (PICKER.x + 24, PICKER.y + 24),
        )
        draw.text(
            surface,
            f"{len(self.cities)}/{MAX_CITIES}",
            t.font(t.size.label),
            p.text_muted,
            (PICKER.right - 24, PICKER.y + 36),
            "midright",
        )
        self.search.draw(surface)
        rows = self._choice_rects()
        if not rows:
            draw.text(
                surface,
                "No matching cities",
                t.font(t.size.body),
                p.text_muted,
                (PICKER.centerx, PICKER.y + 180),
                "center",
            )
        mouse = mouse_pos()
        for i, (city, rect) in enumerate(rows):
            selected = i + self.picker_scroll == self.picker_index
            if selected or rect.collidepoint(mouse):
                draw.rounded_rect(surface, rect, p.surface_hover, t.radius.sm)
            if selected:
                draw.rounded_rect(surface, rect, ACCENT, t.radius.sm, 2)
            there = city_time(city, now)
            draw.text(
                surface,
                city.name,
                t.font(t.size.body, "medium"),
                p.text,
                (rect.x + 14, rect.centery),
                "midleft",
            )
            draw.text(
                surface,
                f"{clock_text(there, self.twelve_hour)}  {utc_offset_text(there.utcoffset())}",
                t.font(t.size.label),
                p.text_muted,
                (rect.right - 14, rect.centery),
                "midright",
            )
        draw.text(
            surface,
            "↑/↓ choose · Enter add · Esc close",
            t.font(t.size.caption),
            p.text_muted,
            (PICKER.centerx, PICKER.bottom - 24),
            "center",
        )

    def _draw_countdowns(self, surface: Canvas, t: Theme, now: datetime) -> None:
        p = t.palette
        draw_panel(surface, FORM, t)
        x = FORM.x + 24
        draw.text(surface, "New countdown", t.font(t.size.title, "bold"), p.text, (x, FORM.y + 22))
        label = t.font(t.size.caption, "semibold")
        for box, name in zip(self.inputs, ("NAME", "DATE", "TIME"), strict=True):
            draw.text(surface, name, label, p.text_muted, (x, box.rect.y - 22))
            box.draw(surface)
        self.add_btn.draw(surface)
        if self.form_error:
            for i, line in enumerate(
                draw.wrap_text(self.form_error, t.font(t.size.caption), FORM.width - 48)
            ):
                draw.text(
                    surface,
                    line,
                    t.font(t.size.caption),
                    p.danger,
                    (x, self.add_btn.rect.bottom + 14 + i * 18),
                )
        draw.text(surface, "QUICK FILL", label, p.text_muted, (x, self.new_year_btn.rect.y - 22))
        self.new_year_btn.draw(surface)
        self.tomorrow_btn.draw(surface)

        draw_panel(surface, EVENTS, t)
        draw.text(
            surface,
            "Countdowns",
            t.font(t.size.title, "bold"),
            p.text,
            (EVENTS.x + 24, EVENTS.y + 22),
        )
        if not self.events:
            draw.text(
                surface,
                "Add an event on the left to start counting down.",
                t.font(t.size.body),
                p.text_muted,
                (EVENTS.centerx, EVENTS.centery),
                "center",
            )
            return
        mouse = mouse_pos()
        for event, rect in zip(self.events, self._event_rects(), strict=True):
            left = (event.at - now).total_seconds()
            done = left <= 0
            hover = rect.collidepoint(mouse)
            draw.rounded_rect(
                surface, rect, p.surface_hover if hover else p.surface_alt, t.radius.md
            )
            draw.rounded_rect(
                surface,
                pygame.Rect(rect.x, rect.y + 10, 4, rect.height - 20),
                p.text_muted if done else ACCENT,
                2,
            )
            draw.text(
                surface,
                event.name,
                t.font(t.size.body, "semibold"),
                p.text_muted if done else p.text,
                (rect.x + 20, rect.y + 18),
                "midleft",
            )
            local_at = event.at.astimezone()
            when = local_at.strftime("%a %d %b %Y, ") + clock_text(local_at, self.twelve_hour)
            draw.text(
                surface,
                when,
                t.font(t.size.caption),
                p.text_muted,
                (rect.x + 20, rect.y + 40),
                "midleft",
            )
            right = rect.right - (60 if hover else 20)
            if done:
                draw.text(
                    surface,
                    ago_text(-left),
                    t.font(t.size.body),
                    p.text_muted,
                    (right, rect.centery),
                    "midright",
                )
            else:
                draw.text(
                    surface,
                    countdown_text(left),
                    t.font(t.size.title, "bold"),
                    p.text,
                    (right, rect.centery),
                    "midright",
                )
            if hover:
                self._draw_remove(surface, t, self._remove_rect(rect))
