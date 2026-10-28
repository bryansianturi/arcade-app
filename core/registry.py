"""App registration and auto-discovery.

Each app package ships an ``app.toml`` manifest (see :mod:`core.manifest`) and
calls :func:`register_app` (usually as a class decorator) when it is imported.
:func:`discover_apps` validates every sub-package's manifest, then imports it,
so registration happens without the launcher knowing any app by name. The
registered class gets its ``meta`` from the manifest.

A package is skipped, with a logged warning, when its manifest is missing or
invalid, when it needs a newer framework, or when importing it fails.

Packages whose name starts with an underscore (such as ``apps/_template``) are
skipped unless the ``ARCADE_SHOW_TEMPLATE`` environment variable is set.
"""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from core.base_app import BaseApp
from core.manifest import MANIFEST_NAME, ManifestError, load_manifest

log = logging.getLogger(__name__)

AppT = TypeVar("AppT", bound=type[BaseApp])

SHOW_PRIVATE_ENV = "ARCADE_SHOW_TEMPLATE"


class RegistrationError(Exception):
    """Raised when an app class is invalid or its id is already taken."""


@dataclass
class DiscoveryFailure:
    """An app package that was skipped (bad manifest or import error)."""

    package: str
    error: str


@dataclass
class AppRegistry:
    """Holds the registered app classes, keyed by ``meta.id``."""

    _apps: dict[str, type[BaseApp]] = field(default_factory=dict)
    failures: list[DiscoveryFailure] = field(default_factory=list)
    #: package name -> app id, for packages already discovered.
    _packages: dict[str, str] = field(default_factory=dict)

    def register(self, cls: AppT) -> AppT:
        """Register an app class. Returns the class so it works as a decorator.

        A class without its own ``meta`` gets it from the ``app.toml`` next to its
        module; classes registered directly (e.g. in tests) may define ``meta`` in code.
        """
        if not (isinstance(cls, type) and issubclass(cls, BaseApp)):
            raise RegistrationError(f"{cls!r} is not a BaseApp subclass")
        if "meta" not in vars(cls):
            manifest = _manifest_beside(cls)
            if manifest is not None:
                try:
                    cls.meta = load_manifest(manifest)
                except ManifestError as exc:
                    raise RegistrationError(str(exc)) from exc
        meta = getattr(cls, "meta", None)
        if meta is None:
            raise RegistrationError(f"{cls.__name__} must define a 'meta' AppMeta")
        existing = self._apps.get(meta.id)
        if existing is not None and existing is not cls:
            raise RegistrationError(
                f"App id {meta.id!r} is used by both {existing.__qualname__} and {cls.__qualname__}"
            )
        self._apps[meta.id] = cls
        return cls

    def discover(self, package: str = "apps", include_private: bool | None = None) -> None:
        """Validate and import every sub-package of ``package``.

        Problems are logged and recorded in :attr:`failures`; they never stop the
        other apps (or the launcher) from loading.
        """
        if include_private is None:
            include_private = bool(os.environ.get(SHOW_PRIVATE_ENV))
        root = importlib.import_module(package)
        # Failed packages are retried, so forget their earlier failures.
        self.failures = [f for f in self.failures if not f.package.startswith(package + ".")]
        for info in sorted(pkgutil.iter_modules(root.__path__), key=lambda m: m.name):
            if not info.ispkg or (info.name.startswith("_") and not include_private):
                continue
            name = f"{package}.{info.name}"
            if name in self._packages:
                continue
            folder = Path(getattr(info.module_finder, "path", "")) / info.name
            self._load_package(name, folder / MANIFEST_NAME)

    def _load_package(self, name: str, manifest_path: Path) -> type[BaseApp] | None:
        try:
            meta = load_manifest(manifest_path)
        except ManifestError as exc:
            log.warning("Skipping app package %s: %s", name, "; ".join(exc.problems))
            self.failures.append(DiscoveryFailure(name, "; ".join(exc.problems)))
            return None
        try:
            importlib.import_module(name)
        except Exception as exc:
            log.exception("Failed to load app package %s", name)
            self.failures.append(DiscoveryFailure(name, f"{type(exc).__name__}: {exc}"))
            return None
        found = [
            c
            for c in self._apps.values()
            if c.__module__ == name or c.__module__.startswith(name + ".")
        ]
        if len(found) != 1 or found[0].meta.id != meta.id:
            problem = "registered no app" if not found else "registered an unexpected app"
            log.warning("Skipping app package %s: it %s", name, problem)
            self.failures.append(DiscoveryFailure(name, problem))
            for cls in found:
                del self._apps[cls.meta.id]
            return None
        self._packages[name] = meta.id
        return found[0]

    def get(self, app_id: str) -> type[BaseApp] | None:
        return self._apps.get(app_id)

    def all(self) -> list[type[BaseApp]]:
        """Registered apps sorted by display name."""
        return sorted(self._apps.values(), key=lambda cls: cls.meta.name.lower())

    def __len__(self) -> int:
        return len(self._apps)


def _manifest_beside(cls: type) -> Path | None:
    """The ``app.toml`` in the folder of the module that defines ``cls``, if any."""
    module = sys.modules.get(cls.__module__)
    file = getattr(module, "__file__", None)
    if file is None:
        return None
    path = Path(file).parent / MANIFEST_NAME
    return path if path.is_file() else None


#: The process-wide registry used by the real application.
registry = AppRegistry()


def register_app(cls: AppT) -> AppT:
    """Class decorator that adds an app to the global registry."""
    return registry.register(cls)


def discover_apps(package: str = "apps") -> list[type[BaseApp]]:
    """Discover apps in ``package`` and return every registered app, sorted by name."""
    registry.discover(package)
    return registry.all()
