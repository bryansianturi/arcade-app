"""Build the browser version of the arcade with pygbag.

    pip install -r requirements-web.txt
    python tools/build_web.py            # build: dist/web/ and dist/arcade-web.zip
    python tools/build_web.py --serve    # build and try it at http://localhost:8000

Only what the game needs (``main.py``, ``core``, ``screens``, ``apps``,
``assets``, plus CPython 3.12's pure-Python ``_pydecimal`` from ``tools/web``)
is copied into a staging folder first, so the virtualenv, tests and caches
never end up in the download.
``dist/web/`` is a static site (upload it anywhere); ``dist/arcade-web.zip`` is
the same files zipped for itch.io.

To keep the first load quick, the fonts are cut down to the characters the
arcade uses, and the page (``tools/web/arcade.tmpl``, based on pygbag's default
template) shows a progress card and starts every big download at once instead
of one after another.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGING = ROOT / "build" / "arcade"
DIST = ROOT / "dist"
INCLUDE = ("main.py", "core", "screens", "apps", "assets")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "_template")
#: CPython 3.12's ``Lib/_pydecimal.py`` and its license (vendored unchanged), and
#: the page template.
VENDOR = ROOT / "tools" / "web"


def stage() -> None:
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir(parents=True)
    for name in INCLUDE:
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, STAGING / name, ignore=IGNORE)
        else:
            shutil.copy2(src, STAGING / name)
    make_favicon(STAGING / "favicon.png")
    subset_fonts(STAGING / "assets" / "fonts")
    # The browser's own ``decimal`` is a stub, so bundle the pure-Python one (see
    # core.web). It must match the browser's Python (3.12), not the one building.
    shutil.copy2(VENDOR / "_pydecimal.py", STAGING / "_pydecimal.py")
    shutil.copy2(VENDOR / "PYTHON-LICENSE.txt", STAGING / "PYTHON-LICENSE.txt")


def make_favicon(path: Path) -> None:
    """A small tab icon: the launcher's rounded tile with an "A"."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    pygame.init()
    size = 64
    icon = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(icon, (99, 102, 241), icon.get_rect(), border_radius=14)
    font = pygame.font.Font(ROOT / "assets" / "fonts" / "Inter-Bold.ttf", 44)
    label = font.render("A", True, (255, 255, 255))
    icon.blit(label, label.get_rect(center=(size // 2, size // 2 - 1)))
    pygame.image.save(icon, path)
    pygame.quit()


def used_characters() -> set[str]:
    """Every character the arcade can draw: ASCII and Latin (for typed text), plus
    any other character in the code, manifests and word lists (arrows, ×, ●...)."""
    chars = {chr(c) for c in (*range(0x20, 0x7F), *range(0xA0, 0x180))}
    for path in STAGING.rglob("*"):
        if path.suffix in (".py", ".toml", ".txt") and path.name != "_pydecimal.py":
            chars |= {c for c in path.read_text(encoding="utf-8") if c.isprintable()}
    return chars


def subset_fonts(fonts: Path) -> None:
    """Shrink each bundled font to :func:`used_characters` (about 400 KB → 110 KB each)."""
    from fontTools import subset

    unicodes = sorted(ord(c) for c in used_characters())
    options = subset.Options()
    options.layout_features = ["*"]  # keep kerning and ligatures
    options.name_IDs = ["*"]
    options.notdef_outline = True
    for path in sorted(fonts.glob("*.ttf")):
        before = path.stat().st_size
        font = subset.load_font(str(path), options)
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=unicodes)
        subsetter.subset(font)
        subset.save_font(font, str(path), options)
        print(f"{path.name}: {before // 1024} KB -> {path.stat().st_size // 1024} KB")


def pygbag(*args: str) -> None:
    template = VENDOR / "arcade.tmpl"
    cmd = [
        sys.executable,
        "-m",
        "pygbag",
        "--ume_block",
        "0",
        "--title",
        "Arcade",
        "--template",
        str(template),
        *args,
    ]
    subprocess.run([*cmd, str(STAGING)], check=True, cwd=ROOT)


def collect() -> None:
    built = STAGING / "build"
    web = DIST / "web"
    if web.exists():
        shutil.rmtree(web)
    shutil.copytree(built / "web", web)
    shutil.copy2(built / "web.zip", DIST / "arcade-web.zip")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--serve", action="store_true", help="serve on localhost:8000 after building"
    )
    args = parser.parse_args()
    stage()
    pygbag("--build", "--archive")
    collect()
    print(f"\nBuilt {DIST / 'web'} and {DIST / 'arcade-web.zip'}")
    if args.serve:
        print("Serving on http://localhost:8000 (Ctrl+C to stop)")
        pygbag()


if __name__ == "__main__":
    main()
