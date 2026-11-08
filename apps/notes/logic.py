"""The to-do list model: items, filters, editing and (de)serialisation. No pygame."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Filter = Literal["all", "active", "done"]
FILTERS: tuple[Filter, ...] = ("all", "active", "done")

#: Longest item text, in characters.
MAX_LENGTH = 120


def clean(text: str) -> str:
    """Collapse whitespace and clip to :data:`MAX_LENGTH`."""
    return " ".join(text.split())[:MAX_LENGTH]


@dataclass
class Item:
    """One to-do item. ``id`` is stable across edits and reordering."""

    id: int
    text: str
    done: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "done": self.done}


@dataclass
class TodoList:
    """An ordered list of items. Every method that changes it returns whether it did."""

    items: list[Item] = field(default_factory=list)
    next_id: int = 1

    def add(self, text: str) -> Item | None:
        """Append an item; blank text adds nothing."""
        text = clean(text)
        if not text:
            return None
        item = Item(self.next_id, text)
        self.next_id += 1
        self.items.append(item)
        return item

    def get(self, item_id: int) -> Item | None:
        return next((i for i in self.items if i.id == item_id), None)

    def edit(self, item_id: int, text: str) -> bool:
        """Change an item's text. Editing it to blank deletes it."""
        item = self.get(item_id)
        if item is None:
            return False
        text = clean(text)
        if not text:
            return self.delete(item_id)
        changed = text != item.text
        item.text = text
        return changed

    def toggle(self, item_id: int) -> bool:
        item = self.get(item_id)
        if item is None:
            return False
        item.done = not item.done
        return True

    def delete(self, item_id: int) -> bool:
        before = len(self.items)
        self.items = [i for i in self.items if i.id != item_id]
        return len(self.items) != before

    def move(self, item_id: int, offset: int) -> bool:
        """Move an item ``offset`` places up (negative) or down, clamped to the ends."""
        item = self.get(item_id)
        if item is None:
            return False
        old = self.items.index(item)
        new = max(0, min(len(self.items) - 1, old + offset))
        if new == old:
            return False
        self.items.insert(new, self.items.pop(old))
        return True

    def clear_done(self) -> int:
        """Delete every finished item and return how many were removed."""
        before = len(self.items)
        self.items = [i for i in self.items if not i.done]
        return before - len(self.items)

    def visible(self, which: Filter) -> list[Item]:
        if which == "active":
            return [i for i in self.items if not i.done]
        if which == "done":
            return [i for i in self.items if i.done]
        return list(self.items)

    def counts(self) -> dict[Filter, int]:
        done = sum(i.done for i in self.items)
        return {"all": len(self.items), "active": len(self.items) - done, "done": done}

    # ------------------------------------------------------------------ persistence
    def to_dict(self) -> dict[str, Any]:
        return {"items": [i.to_dict() for i in self.items], "next_id": self.next_id}

    @classmethod
    def from_dict(cls, data: object) -> TodoList:
        """Rebuild a saved list, skipping anything malformed."""
        todo = cls()
        if not isinstance(data, dict):
            return todo
        raw_items = data.get("items")
        seen: set[int] = set()
        for raw in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(raw, dict):
                continue
            item_id, text = raw.get("id"), raw.get("text")
            if not isinstance(item_id, int) or item_id in seen or not isinstance(text, str):
                continue
            text = clean(text)
            if text:
                seen.add(item_id)
                todo.items.append(Item(item_id, text, raw.get("done") is True))
        next_id = data.get("next_id")
        highest = max(seen, default=0) + 1
        todo.next_id = max(next_id, highest) if isinstance(next_id, int) else highest
        return todo
