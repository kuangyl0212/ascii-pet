# AGENTS.md

ASCII desktop pet: shared core logic + platform-specific rendering, no external runtime deps.

## Project Structure

```
src/ascii_pet/        ← core package (importable as `ascii_pet`)
    __init__.py
    core.py           ← pet game logic (PetGame, actions, persistence, rendering data)
    i18n.py           ← internationalization (en/zh), gettext-based
    lan.py            ← LAN P2P networking (UDP discovery + TCP messaging)
    protocol.py       ← LAN message protocol (framing, encode/decode, pure-data)
    weather.py        ← OpenWeatherMap API client
bin/                  ← entry point scripts
    ascii-pet         ← Linux: ANSI terminal rendering, xdotool window control
    ascii-pet-win.py  ← Windows: Win32 GDI rendering, system tray icon
    ascii-pet-launcher← Linux (i3): bash launcher for alacritty
scripts/              ← build/maintenance
    build.py          ← PyInstaller → dist/ascii-pet-win.exe (--win7, --all flags)
    compile_locales.py← Compiles .po → .mo for gettext
    reinstall.sh      ← Linux: copies to ~/.local/bin/
config/
    pet.toml          ← Alacritty config
    weather.json      ← OpenWeatherMap API key
locales/
    en/LC_MESSAGES/   ← English translations
    zh/LC_MESSAGES/   ← Chinese translations
test/                 ← pytest tests (conftest.py auto-forces English locale)
```

## Import Convention

```python
from ascii_pet.core import PetGame, SPECIES, render_sprite
from ascii_pet.i18n import _, get_language, set_language
from ascii_pet.lan import LanNode
from ascii_pet.protocol import MSG_VISIT_FEED, encode_message
```

## Run

```
python bin/ascii-pet-win.py      # Windows
python bin/ascii-pet             # Linux
python scripts/build.py          # Build exe (auto-installs PyInstaller)
python scripts/build.py --win7   # Build Win7-compatible exe
python scripts/build.py --all    # Build both versions
```

## Tests

```
pytest                        # Run all tests
pytest -m "not slow"          # Skip slow tests
pytest test/test_prng.py      # Run a single test file
pytest -k test_hash           # Run tests matching a name pattern
pytest --cov=ascii_pet --cov-report=term-missing  # Coverage report
```

- Tests live in `test/` directory.
- `test/conftest.py` auto-forces English locale before every test.
- `pytest.ini` configures `testpaths=test`, `pythonpath=src`, and `--strict-markers`.
- `requirements-dev.txt`: pytest, pytest-cov, pytest-mock, pytest-xdist, coverage.

## Architecture

```
src/ascii_pet/core.py    ← platform-independent game logic
├── Constants: SPECIES, BODIES, ACHIEVEMENTS, STAT_NAMES, etc.
├── PRNG: mulberry32, hash_string (FNV-1a)
├── Generation: generate_companion, generate_name, roll_rarity, roll_stats
├── Rendering data: render_sprite, render_face, render_frame (returns plain strings)
├── Actions: feed_pet, play_pet, sleep_pet, check_level_up, check_achievements
├── Persistence: load_state, save_state (auto-detects Linux/Windows data dir)
├── Export: export_text (plain text for clipboard)
├── Pet limit: MAX_PETS=3, release_pet(index), get_release_list()
├── Items: ITEMS dict, add_item, use_item, get_inventory_list
├── Evolution: EVOLUTION_CHAIN, EVOLVED_BODIES
├── Interactions: PET_INTERACTIONS, trigger_interaction
├── LAN: lan_init, lan_tick, lan_visit_pet, lan_shutdown, lan_start_visit
└── PetGame class: state machine wrapping all logic, handles key input

bin/ascii-pet             ← Linux wrapper
├── ANSI color constants (RARITY_COLORS, MOOD_COLORS)
├── Terminal I/O (get_key, clear_screen, etc.)
├── xdotool window control (set_window_geometry, get_screen_size)
├── ANSI rendering (build_compact, build_expanded, build_stats, etc.)
└── main(): event loop calling PetGame

bin/ascii-pet-win.py     ← Windows wrapper
├── Win32 RGB colors (RARITY_RGB, MOOD_RGB, COLOR_*)
├── Win32 API structs and function signatures
├── GDI rendering (render_compact_lines, render_expanded_lines, etc.)
├── PetWindow class (WndProc, on_paint, on_timer, on_char)
├── System tray icon with context menu (right-click)
└── main(): creates PetGame + PetWindow, runs message loop
```

## Conventions

- **Core logic in `src/ascii_pet/core.py`** — all game state, constants, and pure functions live here. Platform files only handle rendering and I/O.
- **Zero pip dependencies** at runtime (stdlib only). PyInstaller is build-time only.
- **PetGame is the interface** — platform files call `game.tick()`, `game.handle_key()`, `game.handle_action()`. Never duplicate game logic in platform files.
- **Rendering differs by design**: Linux returns ANSI strings, Windows returns `(text, (R,G,B))` tuples. Both call the same `ascii_pet.core` data functions.
- **State path**: Linux → `~/.local/share/ascii-pet/`, Windows → `%APPDATA%\ascii-pet\`.
- **Deterministic generation**: Custom FNV-1a hash (`hash_string()`) of uid+SALT (`'ascii-pet-2026'`) feeds a mulberry32 PRNG. Same uid = same pet.
- **I18n**: All user-facing strings go through `_()` from `ascii_pet.i18n`. Two locales: `en`, `zh`. Translations in `locales/{lang}/LC_MESSAGES/ascii_pet.po`. Run `python scripts/compile_locales.py` after editing `.po` files.
- **LAN protocol**: `ascii_pet.protocol` is side-effect free — no sockets, no threads. `ascii_pet.lan` handles all networking.

## Gameplay mechanics

- **Pet limit**: `MAX_PETS=3`. Pressing `n` at the last pet enters release mode. Keys 1/2/3 select pet to release. Cannot release your last pet.
- **Daily limit**: `MAX_DAILY_ADOPTIONS=3`. User can adopt max 3 pets per day. Shows warning when exceeded.
- **Action cooldowns**: feed/play = 1h, sleep = 3h. No cooldown when a stat is critical (zero).
- **Hover petting**: Mouse hover gives +2 HAPPY, capped at 3 times per hour.
- **Stat decay**: HUNGER decays after 4h offline, HAPPY after 2h, ENERGY after 6h.
- **Death**: Pet dies if any stat hits zero for 15min, or all stats zero for 5min. Revivable by feeding/playing/sleeping.
- **Leveling**: XP from actions. Level up at `level * 100` XP. Eye upgrades at level 5, evolves at level 10.
- **Random events**: 5% chance per tick (500ms), 30s cooldown. 11 event types with stat effects.
- **Pet interactions**: 30% chance when switching pets. Types: play_together, share_food, chat, race.
- **Items/backpack**: 7 item types (apple, toy, bed, book, potion, crown, tophat). Max 20 items. Drops from events + daily bonus. Press 'u' to open inventory.
- **Evolution chains**: 8 species evolve at specific levels (e.g., blob→slime lv5→elemental lv15). Changes species, keeps stats.
- **Weather system**: OpenWeatherMap API (config/weather.json). Affects pet mood. Weather reminders for extreme conditions.
- **LAN multiplayer**: UDP broadcast for peer discovery, TCP for visit requests. Pet snapshots shared during visits.

## Linux runtime deps

Not pip — system packages: `xdotool`, `xprop`, `xterm`. `picom` optional for transparency.

## What to skip

- `.trae/` contains historical design specs; not needed for current work.
- `build/`, `dist/`, `build-win7/`, `dist-win7/` are PyInstaller artifacts.
