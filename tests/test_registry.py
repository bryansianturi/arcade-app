from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pygame
import pytest

import core.registry as registry_module
from core.base_app import AppContext, AppMeta, BaseApp
from core.canvas import Canvas
from core.registry import AppRegistry, RegistrationError

APP_SOURCE = """
from core.base_app import BaseApp
from core.registry import register_app

@register_app
class {cls}(BaseApp):
    def handle_event(self, event): pass
    def update(self, dt): pass
    def draw(self, surface): pass
"""

MANIFEST = """
id = "{id}"
name = "{name}"
description = "d"
category = "game"
accent = "#010203"
version = "1.0.0"
author = "Tester"
min_framework = "{fw}"
"""


def write_app(root: Path, pkg: str, cls: str, app_id: str, name: str, fw: str = "1.0") -> None:
    (root / pkg).mkdir()
    (root / pkg / "__init__.py").write_text(APP_SOURCE.format(cls=cls))
    (root / pkg / "app.toml").write_text(MANIFEST.format(id=app_id, name=name, fw=fw))


@pytest.fixture
def fake_apps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Build a throwaway ``apps``-like package and return its import name."""
    name = f"fakeapps_{uuid.uuid4().hex[:8]}"
    root = tmp_path / name
    root.mkdir()
    (root / "__init__.py").write_text("")
    for pkg, cls, app_id, app_name in [
        ("beta", "Beta", "beta", "Beta"),
        ("alpha", "A", "a", "Alpha"),
        ("_hidden", "H", "hidden", "Hidden"),
    ]:
        write_app(root, pkg, cls, app_id, app_name)
    write_app(root, "broken", "Broken", "broken", "Broken")
    (root / "broken" / "__init__.py").write_text("raise RuntimeError('boom')")
    # Skipped before import: no manifest, an invalid one, and one needing a newer framework.
    (root / "no_manifest").mkdir()
    (root / "no_manifest" / "__init__.py").write_text("raise AssertionError('imported')")
    write_app(root, "invalid", "Invalid", "invalid", "Invalid")
    (root / "invalid" / "app.toml").write_text('id = "Bad Id"\n')
    (root / "invalid" / "__init__.py").write_text("raise AssertionError('imported')")
    write_app(root, "future", "Future", "future", "Future", fw="9.0")
    (root / "future" / "__init__.py").write_text("raise AssertionError('imported')")
    (root / "loose_module.py").write_text("raise AssertionError('modules are not apps')")

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(registry_module, "registry", AppRegistry())
    monkeypatch.delenv(registry_module.SHOW_PRIVATE_ENV, raising=False)
    yield name
    for mod in [m for m in sys.modules if m.startswith(name)]:
        del sys.modules[mod]


def test_discovery_registers_apps_sorted_and_skips_private(fake_apps: str) -> None:
    apps = registry_module.discover_apps(fake_apps)
    assert [a.meta.name for a in apps] == ["Alpha", "Beta"]


def test_discover_steps_reports_progress_one_package_at_a_time(fake_apps: str) -> None:
    reg = registry_module.registry
    steps = []
    for loaded, total in reg.discover_steps(fake_apps):
        steps.append((loaded, total, len(reg)))
    total = steps[0][1]
    assert [s[:2] for s in steps] == [(i, total) for i in range(1, total + 1)]
    assert steps[0][2] <= 1 and len(reg) == 2  # apps register as their step runs
    assert [a.meta.name for a in reg.all()] == ["Alpha", "Beta"]


def test_bad_packages_are_recorded_not_raised(fake_apps: str) -> None:
    registry_module.discover_apps(fake_apps)
    failures = {f.package.rsplit(".", 1)[1]: f.error for f in registry_module.registry.failures}
    assert set(failures) == {"broken", "no_manifest", "invalid", "future"}
    assert "boom" in failures["broken"]
    assert "no app.toml" in failures["no_manifest"]
    assert "'name' must be a non-empty string" in failures["invalid"]
    assert "needs framework 9.0" in failures["future"]


def test_discovered_app_gets_meta_from_manifest(fake_apps: str) -> None:
    registry_module.discover_apps(fake_apps)
    beta = registry_module.registry.get("beta")
    assert beta is not None
    assert beta.meta.author == "Tester" and beta.meta.accent == (1, 2, 3)


def test_discovery_is_idempotent(fake_apps: str) -> None:
    registry_module.discover_apps(fake_apps)
    count = len(registry_module.registry.failures)
    registry_module.discover_apps(fake_apps)
    assert len(registry_module.registry) == 2
    assert len(registry_module.registry.failures) == count  # failures retried, not duplicated


def test_private_packages_can_be_included(fake_apps: str) -> None:
    registry_module.registry.discover(fake_apps, include_private=True)
    assert registry_module.registry.get("hidden") is not None


class _Ok(BaseApp):
    meta = AppMeta(id="ok", name="Ok", description="", category="tool", accent=(0, 0, 0))

    def handle_event(self, event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> None: ...
    def draw(self, surface: Canvas) -> None: ...


def test_duplicate_ids_are_rejected() -> None:
    reg = AppRegistry()
    reg.register(_Ok)
    reg.register(_Ok)  # re-registering the same class is harmless

    class Clash(_Ok):
        pass

    with pytest.raises(RegistrationError, match="ok"):
        reg.register(Clash)


def test_non_apps_are_rejected() -> None:
    reg = AppRegistry()
    with pytest.raises(RegistrationError):
        reg.register(int)  # type: ignore[type-var]

    class NoMeta(BaseApp):
        def handle_event(self, event: pygame.event.Event) -> None: ...
        def update(self, dt: float) -> None: ...
        def draw(self, surface: Canvas) -> None: ...

    with pytest.raises(RegistrationError, match="meta"):
        reg.register(NoMeta)


def test_base_app_helpers(app_context: AppContext) -> None:
    app = _Ok(app_context)
    assert app.submit_score(5) is True
    assert app.submit_score(3) is False
    best = app.best_score()
    assert best is not None and best.score == 5
    app.data["k"] = 1
    app.data.save()
    assert app_context.storage.app_data("ok")["k"] == 1
