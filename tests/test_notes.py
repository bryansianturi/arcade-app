from __future__ import annotations

import pygame

from apps.notes.logic import MAX_LENGTH, TodoList, clean
from core.base_app import AppContext
from tests.conftest import click, feed, tap


def make(*texts: str) -> TodoList:
    todo = TodoList()
    for text in texts:
        todo.add(text)
    return todo


def test_add_cleans_text_and_ignores_blank() -> None:
    todo = TodoList()
    assert todo.add("   ") is None
    item = todo.add("  buy   milk ")
    assert item is not None and item.text == "buy milk" and item.id == 1
    assert len(clean("x" * 500)) == MAX_LENGTH


def test_edit_toggle_delete() -> None:
    todo = make("a", "b")
    assert todo.edit(1, "apples")
    assert not todo.edit(1, "apples")  # unchanged
    assert todo.toggle(2) and todo.items[1].done
    assert todo.edit(2, "   ")  # editing to blank deletes
    assert [i.text for i in todo.items] == ["apples"]
    assert not todo.delete(99) and not todo.toggle(99) and not todo.edit(99, "x")


def test_ids_stay_unique_after_deletes() -> None:
    todo = make("a", "b")
    todo.delete(2)
    assert todo.add("c") is not None
    assert [i.id for i in todo.items] == [1, 3]


def test_filters_counts_and_clear_done() -> None:
    todo = make("a", "b", "c")
    todo.toggle(1)
    todo.toggle(3)
    assert [i.text for i in todo.visible("active")] == ["b"]
    assert [i.text for i in todo.visible("done")] == ["a", "c"]
    assert todo.counts() == {"all": 3, "active": 1, "done": 2}
    assert todo.clear_done() == 2
    assert [i.text for i in todo.items] == ["b"]


def test_move_clamps_to_ends() -> None:
    todo = make("a", "b", "c")
    assert todo.move(3, -1)
    assert [i.text for i in todo.items] == ["a", "c", "b"]
    assert not todo.move(1, -1)
    assert todo.move(1, 10)
    assert [i.text for i in todo.items] == ["c", "b", "a"]


def test_round_trip_and_bad_data() -> None:
    todo = make("a", "b")
    todo.toggle(2)
    again = TodoList.from_dict(todo.to_dict())
    assert again == todo
    messy = {
        "items": [
            {"id": 4, "text": "ok", "done": True},
            {"id": 4, "text": "duplicate id"},
            {"id": "x", "text": "bad id"},
            {"id": 5, "text": "  "},
            "junk",
        ],
        "next_id": 2,
    }
    loaded = TodoList.from_dict(messy)
    assert [(i.id, i.text, i.done) for i in loaded.items] == [(4, "ok", True)]
    assert loaded.next_id == 5  # never reuses a saved id
    assert TodoList.from_dict(None) == TodoList()


def type_text(app: object, text: str) -> None:
    for ch in text:
        feed(app, pygame.event.Event(pygame.TEXTINPUT, text=ch))  # type: ignore[arg-type]


def test_app_adds_ticks_edits_and_saves(app_context: AppContext) -> None:
    from apps.notes.app import NotesApp

    app = NotesApp(app_context)
    app.on_enter()
    type_text(app, "water plants")
    tap(app, pygame.K_RETURN)
    type_text(app, "call mum")
    tap(app, pygame.K_RETURN)
    assert [i.text for i in app.todo.items] == ["water plants", "call mum"]

    tap(app, pygame.K_DOWN)  # leave the input for the list
    assert app.selected == 1
    tap(app, pygame.K_SPACE)
    assert app.todo.items[0].done

    tap(app, pygame.K_e)
    assert app.editing == 1 and app.uses_text_input()
    type_text(app, "!")
    tap(app, pygame.K_RETURN)
    assert app.editing is None and app.todo.items[0].text == "water plants!"

    tap(app, pygame.K_e)
    type_text(app, "zzz")
    tap(app, pygame.K_ESCAPE)  # cancels the edit instead of pausing
    assert app.todo.items[0].text == "water plants!"

    again = NotesApp(app_context)
    again.on_enter()
    assert again.todo == app.todo


def test_app_mouse_tick_and_delete(app_context: AppContext) -> None:
    from apps.notes.app import NotesApp

    app = NotesApp(app_context)
    app.on_enter()
    app.todo.add("one")
    app.todo.add("two")
    row = app._row_rect(0)
    feed(app, *click(app._check_rect(row).center))
    assert app.todo.items[0].done
    feed(app, *click(app._delete_rect(row).center))
    assert [i.text for i in app.todo.items] == ["two"]
