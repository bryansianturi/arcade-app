# Arcade

An all-in-one desktop arcade of small games and tools, built with Python and [pygame-ce](https://pyga.me/).
One window, one main loop, a launcher to pick from, and a plugin system that makes adding a new app
as simple as dropping a folder into `apps/`.

![CI](https://github.com/OWNER/arcade-app/actions/workflows/ci.yml/badge.svg)

## Features

- **Plugin architecture**: apps are discovered automatically at startup. Adding one never touches the launcher.
- **Launcher**: card grid with category tabs (All / Games / Tools), search-as-you-type and full keyboard navigation.
- **Framework-level pause menu** (Esc → Resume / Restart / Back to menu). Games also pause automatically when the window loses focus.
- **Crash isolation**: if an app throws, the error is logged and a friendly dialog brings you back to the launcher.
- **Global High Scores** screen, generated from every app that tracks scores (including per-difficulty bests).
- **Settings**: dark/light theme, window size presets, fullscreen (F11), FPS counter, animations.
- **Modern look**: flat design, rounded corners, soft shadows, hover/press states and screen transitions; all graphics are drawn in code.
- **Quality**: type hints throughout, `mypy --strict`, `ruff`, ~140 pytest tests, GitHub Actions CI.

### Apps

| App            | Type | Highlights |
|----------------|------|------------|
| **Sudoku**     | Game | Generator with Easy/Medium/Hard and a guaranteed unique solution, pencil notes, conflict highlighting, check, undo, timer, best time per difficulty, resume an unfinished game |
| **Calculator** | Tool | Hand-written recursive-descent parser (no `eval`), correct precedence, parentheses, powers, exact decimal arithmetic, history |
| **Snake**      | Game | Queued turns for responsive controls, speeds up as you eat, walls or wrap-around, smooth interpolated movement, high score per mode |
| **Minesweeper** | Game | 3 board sizes, first click always safe (and opens an area), flags, chording, keyboard play, best time per difficulty |
| **2048**       | Game | Animated slides, merges and spawns, keyboard or mouse swipe, resume an unfinished game, best score |
| **Tic-tac-toe** | Game | Minimax with alpha-beta (exhaustively tested to never lose) or a beatable easy mode, animated marks, win/draw/loss record |
| **Four in a Row** | Game | Original take on the drop-four genre: negamax with alpha-beta (up to 7 moves deep) on a background thread, 3 levels, falling-disc animation |
| **Stackfall**  | Game | Original falling-block puzzle: 7-bag randomizer, wall kicks, lock delay, ghost piece, hold, 5-piece preview, custom key repeat |
| **Brick Blitz** | Game | Original brick breaker: 4 hand-made layouts, multi-hit and steel bricks, paddle-angle control, keyboard or mouse, sub-stepped collisions |
| **Paddle Duel** | Game | Original paddle game: 2 players on one keyboard or vs a CPU that predicts bounces (3 levels, simulation-tested), spin, longest-rally record |
| **Skyhop**     | Game | Original one-button flyer: neon gates, parallax night skyline, capped difficulty ramp (speed up, gaps shrink) |
| **Five Letters** | Game | Word-guessing with 800 hand-picked answers, 8.5k valid guesses, correct duplicate-letter scoring, hard mode, flip animations, stats and best streak |
| **Star Siege** | Game | Original fixed-screen shooter: formations that speed up as they thin out, eroding shields, lives, waves, extra lives |

## Screenshots

> _Screenshots and GIFs coming soon._

| Launcher | Sudoku | Star Siege |
|----------|--------|------------|
| ![Launcher](docs/screenshots/launcher.png) | ![Sudoku](docs/screenshots/sudoku.png) | ![Star Siege](docs/screenshots/star_siege.png) |

## Getting started

Requires **Python 3.11+**.

```bash
git clone https://github.com/OWNER/arcade-app.git
cd arcade-app
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Controls

| Where      | Keys |
|------------|------|
| Everywhere | **Esc** pause menu / back · **F11** fullscreen |
| Launcher   | **Arrows** select · **Enter** open · **Tab** switch category · just start typing to search |
| Sudoku     | **Arrows/WASD** move · **1–9** place · **0/Backspace** erase · **P** notes · **U** or **Ctrl+Z** undo · **C** check · **N** new |
| Calculator | Type the expression · **Enter** evaluate · **Backspace** delete · **Del** clear · **^** power |
| Snake      | **Arrows/WASD** steer · **P** pause |
| Minesweeper | **Left click** reveal · **Right click** flag · click a number to chord · **Arrows** + **Space** / **F** · **N** new |
| 2048       | **Arrows/WASD** or drag with the mouse · **N** new |
| Tic-tac-toe | Click or **1–9** · **Arrows** + **Enter** · **N** new round |
| Four in a Row | Click a column or **1–7** · **←/→** + **Enter** · **N** new round |
| Stackfall  | **←/→** move · **↓** soft drop · **↑/X** rotate · **Z** rotate back · **Space** hard drop · **C** hold · **P** pause |
| Brick Blitz | **←/→** or mouse to move · **Space** / click to launch |
| Paddle Duel | Left **W/S** · right **↑/↓** (vs CPU: either set) |
| Skyhop     | **Space**, **↑** or click to hop |
| Five Letters | Type letters · **Enter** submit · **Backspace** delete (or use the on-screen keyboard) |
| Star Siege | **←/→** or **A/D** move · **Space** fire (hold to auto-fire) |

### Development

```bash
pip install -r requirements-dev.txt
ruff check .            # lint
ruff format .           # format
mypy                    # type check (strict)
pytest                  # tests run headless (SDL dummy video driver)
```

Saves, settings and the log file live in a per-user folder:
`~/Library/Application Support/Arcade` (macOS), `%APPDATA%\Arcade` (Windows) or `~/.local/share/arcade` (Linux).
Set `ARCADE_DATA_DIR` to use a different folder.

## Architecture

```mermaid
flowchart TD
    main[main.py<br/>main loop] --> SM[SceneManager<br/>scene stack + transitions]
    main -->|startup| REG[registry.discover_apps]
    REG -->|imports every package in| APPS[(apps/*)]
    APPS -->|"@register_app"| REG

    SM --> L[LauncherScreen]
    SM --> S[SettingsScreen]
    SM --> H[HighScoresScreen]
    SM --> HOST[AppHost]
    HOST -->|pause menu, crash guard| APP[BaseApp subclass]

    subgraph Shared services
        T[Theme] 
        ST[Storage<br/>JSON in user data dir]
        W[Widgets]
        SET[Settings]
    end
    APP -. AppContext .-> T & ST & SET
    APP -. imports .-> W
    L & S & H -. Services .-> T & ST & SET
```

**How the plugin system works**

1. Every app is a package in `apps/` whose `__init__.py` imports a class decorated with `@register_app`.
2. At startup `discover_apps()` walks `apps/` with `pkgutil` and imports each package. The decorator adds the class to the registry. Packages starting with `_` (such as `_template`) are skipped. A package that fails to import is logged and skipped, and the launcher shows a warning instead of crashing.
3. The launcher builds its cards from each class's `AppMeta` (name, description, category, accent color, score settings) and its `draw_icon()`.
4. Opening an app pushes an `AppHost` scene that owns the framework behaviour: the Esc pause menu, auto-pause on focus loss, restart, return to launcher, and catching any exception from the app.
5. Apps only talk to the framework through `AppContext` (theme, storage, settings, `request_exit`, `request_pause`) and the helpers on `BaseApp` (`submit_score`, `best_score`, `data`), so they never import launcher or screen code.

**Other design decisions**

- **Fixed logical canvas.** Everything renders onto a 1280×720 surface, and `pygame.SCALED` lets SDL scale it to the window on the GPU with letterboxing and automatic mouse mapping. Game code never deals with window sizes.
- **Logic is separate from drawing.** Each app has a `logic.py` with no pygame import, which holds the rules and is unit-tested directly. `app.py` only translates input and draws.
- **Storage** is plain JSON with atomic writes (temp file + rename). Corrupt files are logged and treated as empty, never fatal.
- **Theme tokens** (`theme.palette.surface`, `theme.space.md`, `theme.radius.lg`...) instead of hard-coded colors, so the light theme works everywhere.

### Project structure

```
main.py                 entry point and main loop
core/
  base_app.py           BaseApp, AppMeta, AppContext: the app contract
  registry.py           @register_app and auto-discovery
  app_host.py           runs an app: pause menu, restart, crash isolation
  scene_manager.py      scene stack with fade/slide transitions
  display.py            window, scaling, fullscreen
  theme.py, draw.py     design tokens and drawing helpers (shadows, rounded rects, text)
  storage.py            JSON saves: high scores, settings, per-app data
  settings.py           typed user settings
  widgets/              Button, Card, Label, Grid, Toggle, TextInput, SegmentedControl, ButtonMenu
screens/                launcher, settings, high scores
apps/
  _template/            minimal app to copy
  calculator/  snake/  star_siege/  sudoku/
assets/fonts/           Inter (SIL Open Font License)
tests/                  pytest suite (headless)
```

## How to add a new app

The `apps/_template` package is a complete, working app (a click counter with a saved high score).
To create your own:

1. **Copy the template.** Use a folder name without a leading underscore, or it will be hidden:
   ```bash
   cp -r apps/_template apps/my_game
   ```
2. **Fix the imports** in `apps/my_game/__init__.py` and `app.py` (`apps._template` → `apps.my_game`), and rename `TemplateApp`.
3. **Describe your app** by editing `meta`:
   ```python
   meta = AppMeta(
       id="my_game",  # unique and stable; it's the save-file key
       name="My Game",
       description="One line for the launcher card.",
       category="game",  # or "tool"
       accent=(255, 120, 80),
       tracks_scores=True,  # show on the High Scores screen
       score_order="higher",  # "lower" for times
       score_format="points",  # or "time"
       variants=(),  # e.g. ("easy", "hard") for per-difficulty bests
   )
   ```
4. **Write the rules** in `logic.py` without importing pygame, so you can test them.
5. **Implement the hooks** in `app.py`:
   - `on_enter()`: build or reset state (also called on Restart)
   - `handle_event(event)`, `update(dt)`, `draw(surface)`
   - optional: `on_exit()`, `on_pause()`, `on_resume()`, `captures_escape()`, `draw_icon()`
6. **Use the shared pieces**: `self.theme` for colors and fonts, `core.widgets` for UI, `self.submit_score(score, variant)` for high scores, and `self.data` (call `self.data.save()`) for anything else you want to persist.
7. **Run it.** `python main.py` shows your app in the launcher. No other file needs to change.
8. **Test it.** `tests/test_apps_smoke.py` automatically runs every discovered app headless with random input. Add a `tests/test_my_game.py` for your logic.

Tip: run `ARCADE_SHOW_TEMPLATE=1 python main.py` to see the template itself in the launcher.

## License

[MIT](LICENSE). The bundled [Inter](https://rsms.me/inter/) font is licensed under the
[SIL Open Font License 1.1](assets/fonts/OFL.txt). Five Letters' guess list comes from Webster's Second
International Dictionary (1934, public domain), as distributed with BSD systems.
