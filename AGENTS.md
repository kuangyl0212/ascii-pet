# AGENTS.md

ASCII desktop pet: shared core logic + platform-specific rendering, no external runtime deps.

## Files

| File | Platform | Notes |
|------|----------|-------|
| `pet_core.py` | — | Shared: constants, PRNG, pet generation, actions, persistence, `PetGame` class |
| `ascii-pet` | Linux | ANSI terminal rendering, xdotool window control, imports `pet_core` |
| `ascii-pet-win.py` | Windows | Win32 GDI rendering via ctypes, system tray icon, imports `pet_core` |
| `ascii-pet-launcher` | Linux (i3) | Bash — kills old instance, launches alacritty with `config/pet.toml` |
| `build.py` | — | PyInstaller → `dist/ascii-pet-win.exe` |
| `reinstall.sh` | Linux | Copies files to `~/.local/bin/`, fixes launcher path, runs |
| `config/pet.toml` | — | Alacritty config: transparent bg, monospace font, green-on-black |

## Architecture

```
pet_core.py          ← platform-independent game logic
├── Constants: SPECIES, BODIES, ACHIEVEMENTS, STAT_NAMES, etc.
├── PRNG: mulberry32, hash_string (FNV-1a)
├── Generation: generate_companion, generate_name, roll_rarity, roll_stats
├── Rendering data: render_sprite, render_face, render_frame (returns plain strings)
├── Actions: feed_pet, play_pet, sleep_pet, check_level_up, check_achievements
├── Persistence: load_state, save_state (auto-detects Linux/Windows data dir)
├── Export: export_text (plain text for clipboard)
├── Pet limit: MAX_PETS=3, release_pet(index), get_release_list()
└── PetGame class: state machine wrapping all logic, handles key input

ascii-pet            ← Linux wrapper
├── ANSI color constants (RARITY_COLORS, MOOD_COLORS)
├── Terminal I/O (get_key, clear_screen, etc.)
├── xdotool window control (set_window_geometry, get_screen_size)
├── ANSI rendering (build_compact, build_expanded, build_stats, build_achievements, build_release)
└── main(): event loop calling PetGame

ascii-pet-win.py     ← Windows wrapper
├── Win32 RGB colors (RARITY_RGB, MOOD_RGB, COLOR_*)
├── Win32 API structs and function signatures
├── GDI rendering (render_compact_lines, render_expanded_lines, render_release_lines, etc.)
├── PetWindow class (WndProc, on_paint, on_timer, on_char)
├── System tray icon with context menu (right-click)
└── main(): creates PetGame + PetWindow, runs message loop
```

## Run

```
./ascii-pet                  # Linux direct
./ascii-pet --all            # List all species with sprites
./ascii-pet [username]       # Specific profile
./ascii-pet-launcher         # i3 + alacritty (kills existing instance)
./reinstall.sh               # Install to ~/.local/bin/ and launch
python ascii-pet-win.py      # Windows (or dist/ascii-pet-win.exe)
python build.py              # Build Windows exe (auto-installs PyInstaller if missing)
```

## Conventions

- **Core logic in `pet_core.py`** — all game state, constants, and pure functions live here. Platform files only handle rendering and I/O.
- **Zero pip dependencies** at runtime (stdlib only). PyInstaller is build-time only.
- **PetGame is the interface** — platform files call `game.tick()`, `game.handle_key()`, `game.handle_action()`. Never duplicate game logic in platform files.
- **Rendering differs by design**: Linux returns ANSI strings, Windows returns `(text, (R,G,B))` tuples. Both call the same `pet_core` data functions.
- **State path**: Linux → `~/.local/share/ascii-pet/`, Windows → `%APPDATA%\ascii-pet\`.
- **Deterministic generation**: Custom FNV-1a hash (`hash_string()`) of uid+SALT (`'ascii-pet-2026'`) feeds a mulberry32 PRNG. Same uid = same pet.

## Gameplay mechanics

- **Pet limit**: `MAX_PETS=3`. Pressing `n` at the last pet enters release mode. Keys 1/2/3 select pet to release. Cannot release your last pet.
- **Daily limit**: `MAX_DAILY_ADOPTIONS=3`. User can adopt max 3 pets per day. Shows warning when exceeded.
- **Action cooldowns**: feed/play = 1h, sleep = 3h. No cooldown when a stat is critical (zero).
- **Hover petting**: Mouse hover gives +2 HAPPY, capped at 3 times per hour.
- **Stat decay**: HUNGER decays after 4h offline, HAPPY after 2h, ENERGY after 6h.
- **Death**: Pet dies if any stat hits zero for 15min, or all stats zero for 5min. Revivable by feeding/playing/sleeping.
- **Leveling**: XP from actions. Level up at `level * 100` XP. Eye upgrades at level 5, evolves at level 10.

## Linux runtime deps

Not pip — system packages: `xdotool`, `xprop`, `xterm`. `picom` optional for transparency.

## What to skip

- No test suite, no CI, no linter, no typechecker.
- `.trae/` contains historical design specs; not needed for current work.
- `build/` and `dist/` are gitignored PyInstaller artifacts.
