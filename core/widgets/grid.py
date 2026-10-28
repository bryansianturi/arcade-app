"""Grid layout maths, kept free of drawing so it is easy to test and reuse."""

from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass
class Grid:
    """Lays out equally-sized cells in rows inside ``rect``.

    The grid only computes rectangles; callers decide what to draw in them.
    """

    rect: pygame.Rect
    columns: int
    cell_height: int
    gap: int = 16

    @classmethod
    def fit(cls, rect: pygame.Rect, min_cell_width: int, cell_height: int, gap: int = 16) -> Grid:
        """Create a grid with as many columns as fit ``min_cell_width``."""
        columns = max(1, (rect.width + gap) // (min_cell_width + gap))
        return cls(rect, columns, cell_height, gap)

    @property
    def cell_width(self) -> int:
        return (self.rect.width - self.gap * (self.columns - 1)) // self.columns

    def cell(self, index: int, scroll: int = 0) -> pygame.Rect:
        """Rectangle of cell ``index`` (row-major), shifted up by ``scroll`` pixels."""
        row, col = divmod(index, self.columns)
        x = self.rect.x + col * (self.cell_width + self.gap)
        y = self.rect.y + row * (self.cell_height + self.gap) - scroll
        return pygame.Rect(x, y, self.cell_width, self.cell_height)

    def rows(self, count: int) -> int:
        return (count + self.columns - 1) // self.columns

    def content_height(self, count: int) -> int:
        rows = self.rows(count)
        return max(0, rows * self.cell_height + (rows - 1) * self.gap)

    def move(self, index: int, dx: int, dy: int, count: int) -> int:
        """Return the index reached by moving ``(dx, dy)`` cells, clamped to the grid."""
        if count <= 0:
            return 0
        if dx:
            return max(0, min(count - 1, index + dx))
        target = index + dy * self.columns
        if target < 0:
            return index % self.columns if dy < 0 and index < self.columns else 0
        if target >= count:
            # Moving down from a row with no cell directly below: go to the last item,
            # but only if there is a further row.
            return count - 1 if self.rows(count) - 1 > index // self.columns else index
        return target
