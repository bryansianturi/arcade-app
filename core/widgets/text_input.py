"""Single-line text field."""

from __future__ import annotations

from collections.abc import Callable

import pygame

from core import draw
from core.theme import Theme, lerp_color
from core.widgets.base import Widget


class TextInput(Widget):
    """A text box. Click to focus; type to edit; Esc or clicking elsewhere unfocuses."""

    def __init__(
        self,
        theme: Theme,
        rect: pygame.Rect | tuple[int, int, int, int],
        placeholder: str = "",
        on_change: Callable[[str], None] | None = None,
        max_length: int = 64,
        icon: draw.Icon | None = None,
    ) -> None:
        super().__init__(theme, rect)
        self.text = ""
        self.placeholder = placeholder
        self.on_change = on_change
        self.max_length = max_length
        self.icon = icon
        self._blink = 0.0

    def set_text(self, value: str) -> None:
        value = value[: self.max_length]
        if value != self.text:
            self.text = value
            if self.on_change is not None:
                self.on_change(value)

    def focus(self) -> None:
        self.focused = True
        self._blink = 0.0

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            inside = self.rect.collidepoint(event.pos)
            if inside:
                self.focus()
            else:
                self.focused = False
            return inside
        if not self.focused:
            return False
        if event.type == pygame.TEXTINPUT:
            self.set_text(self.text + event.text)
            self._blink = 0.0
            return True
        if event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            if event.key == pygame.K_BACKSPACE:
                word_delete = mods & (pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META)
                self.set_text("" if word_delete else self.text[:-1])
                self._blink = 0.0
                return True
            if event.key == pygame.K_ESCAPE:
                self.focused = False
                return True
            # Swallow printable keys so they don't trigger shortcuts while typing.
            return bool(event.unicode and event.unicode.isprintable())
        return False

    def update(self, dt: float) -> None:
        super().update(dt)
        self._blink = (self._blink + dt) % 1.0

    def draw(self, surface: pygame.Surface) -> None:
        t = self.theme
        p = t.palette
        bg = lerp_color(p.surface_alt, p.surface_hover, self._hover_t * 0.6)
        draw.rounded_rect(surface, self.rect, bg, t.radius.md)
        border = p.primary if self.focused else p.border
        draw.rounded_rect(surface, self.rect, border, t.radius.md, 2 if self.focused else 1)

        font = t.font(t.size.body)
        x = self.rect.x + t.space.md
        if self.icon is not None:
            x = draw.draw_icon(surface, self.icon, font, p.text_muted, (x, self.rect.centery))
            x += t.space.sm
        shown = self.text or self.placeholder
        color = p.text if self.text else p.text_muted
        max_w = self.rect.right - t.space.md - x
        # Show the tail of long input so the caret stays visible.
        while self.text and font.size(shown)[0] > max_w:
            shown = shown[1:]
        drawn = draw.text(surface, shown, font, color, (x, self.rect.centery), "midleft")
        if self.focused and self._blink < 0.55:
            cx = drawn.right + 1 if self.text else x
            h = font.get_height() - 4
            pygame.draw.line(
                surface,
                p.text,
                (cx, self.rect.centery - h // 2),
                (cx, self.rect.centery + h // 2),
                2,
            )
