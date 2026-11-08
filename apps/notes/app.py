"""Notes UI: an input row, filter tabs and a scrolling list of to-do items."""

from __future__ import annotations

import pygame

from apps.notes.logic import FILTERS, MAX_LENGTH, Filter, Item, TodoList
from core import draw, gfx
from core.base_app import BaseApp
from core.canvas import Canvas, mouse_pos
from core.input import is_action
from core.registry import register_app
from core.theme import Color, Theme, lerp_color, readable_on
from core.widgets import Button, SegmentedControl, TextInput

ACCENT: Color = (13, 148, 136)
LEFT, WIDTH = 240, 800
LIST_TOP, ROW_H, VISIBLE_ROWS = 232, 54, 8
DOUBLE_CLICK = 0.4  # seconds
FILTER_NAMES = ("All", "Active", "Done")


@register_app
class NotesApp(BaseApp):
    """A to-do list saved between sessions."""

    @classmethod
    def draw_icon(cls, surface: Canvas, rect: pygame.Rect, theme: Theme) -> None:
        draw.rounded_rect(surface, rect, ACCENT, theme.radius.md)
        u = rect.width / 8
        white = (255, 255, 255)
        for row in range(3):
            y = rect.y + (2.3 + row * 1.7) * u
            box = pygame.Rect(round(rect.x + 1.6 * u), round(y - 0.5 * u), round(u), round(u))
            if row == 0:
                draw.thick_line(surface, white, (box.x, box.centery), (box.centerx, box.bottom), 2)
                draw.thick_line(surface, white, (box.centerx, box.bottom), (box.right, box.y), 2)
            else:
                gfx.rect(surface, white, box, 2)
            draw.thick_line(surface, white, (rect.x + 3.3 * u, y), (rect.x + 6.4 * u, y), 2)

    # ------------------------------------------------------------------ lifecycle
    def on_enter(self) -> None:
        t = self.theme
        self.todo = TodoList.from_dict(self.data.get("todo"))
        saved_filter = self.data.get("filter")
        self.filter: Filter = saved_filter if saved_filter in FILTERS else "all"
        self.new_input = TextInput(
            t, (LEFT, 92, WIDTH - 124, 52), "Add a task and press Enter", max_length=MAX_LENGTH
        )
        self.new_input.focus()
        self.add_btn = Button(
            t, (LEFT + WIDTH - 112, 92, 112, 52), "Add", self._add, "primary", accent=ACCENT
        )
        self.tabs = SegmentedControl(
            t,
            (LEFT, 168, 330, 40),
            FILTER_NAMES,
            FILTERS.index(self.filter),
            self._set_filter,
            accent=ACCENT,
        )
        self.clear_btn = Button(
            t, (LEFT + WIDTH - 160, 168, 160, 40), "Clear done", self._clear_done, "ghost"
        )
        self.selected: int | None = None  # item id with keyboard focus
        self.editing: int | None = None
        self.editor = TextInput(t, (0, 0, 10, 10), max_length=MAX_LENGTH)
        self.scroll = 0
        self.time = 0.0
        self._last_click: tuple[int, float] = (-1, -10.0)

    def on_exit(self) -> None:
        self._commit_edit()
        self._save()

    def restart(self) -> None:
        self._commit_edit()
        self.new_input.set_text("")
        self.new_input.focus()
        self.selected = None

    def _save(self) -> None:
        self.data["todo"] = self.todo.to_dict()
        self.data["filter"] = self.filter
        self.data.save()

    # ------------------------------------------------------------------ actions
    def _add(self) -> None:
        if self.todo.add(self.new_input.text) is not None:
            self.new_input.set_text("")
            if self.filter == "done":  # show where the new item went
                self._set_filter(0)
            self._scroll_to(len(self._visible()) - 1)
            self._save()
        self.new_input.focus()

    def _set_filter(self, index: int) -> None:
        self.tabs.index = index
        self.filter = FILTERS[index]
        self.scroll = 0
        if self.selected is not None and self._row_of(self.selected) is None:
            self.selected = None
        self._save()

    def _clear_done(self) -> None:
        if self.todo.clear_done():
            if self.selected is not None and self.todo.get(self.selected) is None:
                self.selected = None
            self._clamp_scroll()
            self._save()

    def _toggle(self, item_id: int) -> None:
        self.todo.toggle(item_id)
        self._save()

    def _delete(self, item_id: int) -> None:
        row = self._row_of(item_id)
        self.todo.delete(item_id)
        visible = self._visible()
        if self.selected == item_id:
            self.selected = visible[min(row or 0, len(visible) - 1)].id if visible else None
        self._clamp_scroll()
        self._save()

    def _start_edit(self, item_id: int) -> None:
        item = self.todo.get(item_id)
        if item is None:
            return
        self.editing = item_id
        self.selected = item_id
        self.editor.set_text(item.text)
        self.editor.focus()
        self.new_input.focused = False

    def _commit_edit(self) -> None:
        if self.editing is not None:
            self.todo.edit(self.editing, self.editor.text)
            if self.todo.get(self.editing) is None:
                self.selected = None
            self.editing = None
            self._clamp_scroll()
            self._save()

    def _cancel_edit(self) -> None:
        self.editing = None

    # ------------------------------------------------------------------ layout
    def _visible(self) -> list[Item]:
        return self.todo.visible(self.filter)

    def _row_of(self, item_id: int) -> int | None:
        return next((i for i, item in enumerate(self._visible()) if item.id == item_id), None)

    def _row_rect(self, row: int) -> pygame.Rect:
        y = LIST_TOP + (row - self.scroll) * ROW_H
        return pygame.Rect(LEFT, y, WIDTH, ROW_H - 6)

    def _check_rect(self, row: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(row.x + 14, row.centery - 12, 24, 24)

    def _delete_rect(self, row: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(row.right - 46, row.centery - 16, 32, 32)

    def _clamp_scroll(self) -> None:
        self.scroll = max(0, min(self.scroll, len(self._visible()) - VISIBLE_ROWS))

    def _scroll_to(self, row: int) -> None:
        if row < self.scroll:
            self.scroll = row
        elif row >= self.scroll + VISIBLE_ROWS:
            self.scroll = row - VISIBLE_ROWS + 1
        self._clamp_scroll()

    def _rows_on_screen(self) -> list[tuple[Item, pygame.Rect]]:
        visible = self._visible()
        end = min(len(visible), self.scroll + VISIBLE_ROWS)
        return [(visible[i], self._row_rect(i)) for i in range(self.scroll, end)]

    # ------------------------------------------------------------------ input
    def uses_text_input(self) -> bool:
        return self.new_input.focused or self.editing is not None

    def captures_pause(self) -> bool:
        return self.editing is not None

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.editing is not None:
            self._handle_editing(event)
            return
        if self.new_input.focused and self._handle_new_input(event):
            return
        if self.add_btn.handle_event(event) or self.clear_btn.handle_event(event):
            return
        if self.tabs.handle_event(event):
            return
        if self.new_input.handle_event(event):
            self.selected = None
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._click(event.pos)
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll -= event.y
            self._clamp_scroll()
        elif event.type == pygame.KEYDOWN:
            self._shortcut(event)
        else:
            self._navigate(event)

    def _handle_editing(self, event: pygame.event.Event) -> None:
        if is_action(event, "pause", repeat=False):
            self._cancel_edit()
            return
        if event.type == pygame.KEYDOWN and self.input.action_for_key(event.key) == "pause":
            return  # the pause action above cancels; don't let the editor eat the key
        if is_action(event, "action", repeat=False):
            self._commit_edit()
            return
        handled = self.editor.handle_event(event)
        if not self.editor.focused:  # clicked outside the editor
            self._commit_edit()
            if not handled:
                self.handle_event(event)

    def _handle_new_input(self, event: pygame.event.Event) -> bool:
        if is_action(event, "action", repeat=False):
            self._add()
            return True
        if is_action(event, "down") and self._visible():
            self.new_input.focused = False
            self.selected = self._visible()[self.scroll].id
            return True
        return False

    def _click(self, pos: tuple[int, int]) -> None:
        for item, rect in self._rows_on_screen():
            if not rect.collidepoint(pos):
                continue
            if self._check_rect(rect).inflate(12, 12).collidepoint(pos):
                self._toggle(item.id)
            elif self._delete_rect(rect).collidepoint(pos):
                self._delete(item.id)
            else:
                last_id, last_time = self._last_click
                if last_id == item.id and self.time - last_time < DOUBLE_CLICK:
                    self._start_edit(item.id)
                self.selected = item.id
                self._last_click = (item.id, self.time)
            return
        self.selected = None

    def _shortcut(self, event: pygame.event.Event) -> None:
        item_id = self.selected
        if item_id is None:
            return
        mods = pygame.key.get_mods()
        if event.key in (pygame.K_UP, pygame.K_DOWN) and mods & (
            pygame.KMOD_CTRL | pygame.KMOD_META | pygame.KMOD_ALT
        ):
            if self.filter == "all" and self.todo.move(
                item_id, -1 if event.key == pygame.K_UP else 1
            ):
                self._scroll_to(self._row_of(item_id) or 0)
                self._save()
        elif event.key in (pygame.K_e, pygame.K_F2):
            self._start_edit(item_id)
        elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self._delete(item_id)

    def _navigate(self, event: pygame.event.Event) -> None:
        visible = self._visible()
        if self.selected is not None and is_action(event, "action", repeat=False):
            self._toggle(self.selected)
            return
        step = -1 if is_action(event, "up") else 1 if is_action(event, "down") else 0
        if not step:
            return
        row = self._row_of(self.selected) if self.selected is not None else None
        if row is None:
            row = -1 if step > 0 else len(visible)
        row += step
        if row < 0:
            self.selected = None
            self.new_input.focus()
        elif visible:
            row = min(row, len(visible) - 1)
            self.selected = visible[row].id
            self._scroll_to(row)

    def update(self, dt: float) -> None:
        self.time += dt
        for widget in (self.new_input, self.add_btn, self.tabs, self.clear_btn, self.editor):
            widget.update(dt)
        self.clear_btn.enabled = self.todo.counts()["done"] > 0

    # ------------------------------------------------------------------ drawing
    def draw(self, surface: Canvas) -> None:
        t = self.theme
        p = t.palette
        surface.fill(p.bg)
        draw.text(surface, "Notes", t.font(t.size.heading, "bold"), p.text, (LEFT, 30))
        counts = self.todo.counts()
        summary = (
            f"{counts['active']} to do · {counts['done']} done" if counts["all"] else "Nothing yet"
        )
        draw.text(
            surface,
            summary,
            t.font(t.size.label),
            p.text_muted,
            (LEFT + WIDTH, 46),
            "midright",
        )
        self.new_input.draw(surface)
        self.add_btn.draw(surface)
        self.tabs.draw(surface)
        self.clear_btn.draw(surface)
        self._draw_list(surface, t)
        hint = (
            "Enter save · Esc cancel"
            if self.editing is not None
            else "Enter add · ↑/↓ select · Space tick · E or double-click edit · "
            "Del delete · Ctrl+↑/↓ reorder"
        )
        draw.text(surface, hint, t.font(t.size.caption), p.text_muted, (640, 694), "center")

    def _draw_list(self, surface: Canvas, t: Theme) -> None:
        p = t.palette
        visible = self._visible()
        if not visible:
            empty = {
                "all": "No tasks yet. Type one above to get started.",
                "active": "All done. Nice work!",
                "done": "Nothing ticked off yet.",
            }[self.filter]
            draw.text(
                surface, empty, t.font(t.size.body), p.text_muted, (640, LIST_TOP + 80), "center"
            )
            return
        mouse = mouse_pos()
        for item, rect in self._rows_on_screen():
            self._draw_row(surface, t, item, rect, rect.collidepoint(mouse))
        if len(visible) > VISIBLE_ROWS:
            track = pygame.Rect(LEFT + WIDTH + 12, LIST_TOP, 4, VISIBLE_ROWS * ROW_H - 6)
            draw.rounded_rect(surface, track, p.surface_alt, 2)
            h = max(24, track.height * VISIBLE_ROWS // len(visible))
            y = track.y + (track.height - h) * self.scroll // (len(visible) - VISIBLE_ROWS)
            draw.rounded_rect(surface, pygame.Rect(track.x, y, 4, h), p.text_muted, 2)

    def _draw_row(
        self, surface: Canvas, t: Theme, item: Item, rect: pygame.Rect, hovered: bool
    ) -> None:
        p = t.palette
        selected = item.id == self.selected
        bg = p.surface_hover if hovered or selected else p.surface
        draw.rounded_rect(surface, rect, bg, t.radius.md)
        if selected:
            draw.rounded_rect(surface, rect, ACCENT, t.radius.md, 2)
        box = self._check_rect(rect)
        if item.done:
            gfx.circle(surface, ACCENT, box.center, 12)
            white = readable_on(ACCENT)
            draw.thick_line(surface, white, (box.x + 6, box.centery), (box.x + 10, box.y + 16), 2)
            draw.thick_line(surface, white, (box.x + 10, box.y + 16), (box.x + 18, box.y + 7), 2)
        else:
            gfx.circle(surface, p.text_muted, box.center, 12, 2)
        text_x = box.right + 16
        if item.id == self.editing:
            self.editor.rect = pygame.Rect(
                text_x - 8, rect.y + 4, rect.right - text_x, rect.height - 8
            )
            self.editor.draw(surface)
            return
        font = t.font(t.size.body)
        color = p.text_muted if item.done else p.text
        room = rect.right - 64 - text_x
        shown = draw.text(
            surface,
            draw.fit_text(item.text, font, room),
            font,
            color,
            (text_x, rect.centery),
            "midleft",
        )
        if item.done:
            strike = lerp_color(p.text_muted, p.bg, 0.2)
            gfx.line(surface, strike, (shown.x, shown.centery), (shown.right, shown.centery), 2)
        if hovered or selected:
            cross = self._delete_rect(rect)
            over = cross.collidepoint(mouse_pos())
            if over:
                draw.rounded_rect(
                    surface, cross, lerp_color(p.surface, p.danger, 0.18), t.radius.sm
                )
            color = p.danger if over else p.text_muted
            (cx, cy), r = cross.center, 6
            draw.thick_line(surface, color, (cx - r, cy - r), (cx + r, cy + r), 2)
            draw.thick_line(surface, color, (cx - r, cy + r), (cx + r, cy - r), 2)
