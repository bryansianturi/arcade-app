"""Static text."""

from __future__ import annotations

from typing import Literal

from core import draw
from core.canvas import Canvas
from core.theme import Theme, Weight
from core.widgets.base import Widget

Tone = Literal["text", "text_muted", "primary", "danger", "success"]


class Label(Widget):
    """A single line of text anchored at a point."""

    def __init__(
        self,
        theme: Theme,
        text: str,
        pos: tuple[int, int],
        size: int | None = None,
        weight: Weight = "regular",
        tone: Tone = "text",
        anchor: draw.Anchor = "topleft",
    ) -> None:
        super().__init__(theme, (pos[0], pos[1], 0, 0))
        self.text = text
        self.pos = pos
        self.size = size or theme.size.body
        self.weight: Weight = weight
        self.tone: Tone = tone
        self.anchor: draw.Anchor = anchor

    def draw(self, surface: Canvas) -> None:
        if not self.visible:
            return
        color = getattr(self.theme.palette, self.tone)
        font = self.theme.font(self.size, self.weight)
        self.rect = draw.text(surface, self.text, font, color, self.pos, self.anchor)
