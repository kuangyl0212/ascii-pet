# AGENTS.md

ASCII desktop pet: shared core logic + platform-specific rendering, no external runtime deps.

## Files

| File | Platform | Notes |
|------|----------|-------|
| `pet_core.py` | — | Shared: constants, PRNG, pet generation, actions, persistence, `PetGame` class |
| `ascii-pet` | Linux | ANSI terminal rendering, xdotool window control, imports `pet_core` |
| `ascii-pet-win.py` | Windows | Win32 GDI rendering via ctypes, imports `pet_core` |
| `ascii-pet-launcher` | Linux (i3) | Bash — kills old instance, launches alacritty with `config/pet.toml` |
| `build.py` | — | PyInstaller → `dist/ascii-pet-win.exe` |
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
└── PetGame class: state machine wrapping all logic, handles key input

ascii-pet            ← Linux wrapper
├── ANSI color constants (RARITY_COLORS, MOOD_COLORS)
├── Terminal I/O (get_key, clear_screen, etc.)
├── xdotool window control (set_window_geometry, get_screen_size)
├── ANSI rendering (build_compact, build_expanded, build_stats, build_achievements)
└── main(): event loop calling PetGame

ascii-pet-win.py     ← Windows wrapper
├── Win32 RGB colors (RARITY_RGB, MOOD_RGB, COLOR_*)
├── Win32 API structs and function signatures
├── GDI rendering (render_compact_lines, render_expanded_lines, etc.)
├── PetWindow class (WndProc, on_paint, on_timer, on_char)
└── main(): creates PetGame + PetWindow, runs message loop
```

## Run

```
./ascii-pet                  # Linux direct
./ascii-pet --all            # List all species with sprites
./ascii-pet [username]       # Specific profile
./ascii-pet-launcher         # i3 + alacritty (kills existing instance)
python ascii-pet-win.py      # Windows (or dist/ascii-pet-win.exe)
python build.py              # Build Windows exe (auto-installs PyInstaller if missing)
```

## Conventions

- **Core logic in `pet_core.py`** — all game state, constants, and pure functions live here. Platform files only handle rendering and I/O.
- **Zero pip dependencies** at runtime (stdlib only). PyInstaller is build-time only.
- **PetGame is the interface** — platform files call `game.tick()`, `game.handle_key()`, `game.handle_action()`. Never duplicate game logic in platform files.
- **State path**: Linux → `~/.local/share/ascii-pet/`, Windows → `%APPDATA%\ascii-pet\`.
- **Deterministic generation**: Custom FNV-1a hash (`hash_string()`) of uid+SALT (`'ascii-pet-2026'`) feeds a mulberry32 PRNG. Same uid = same pet.
- **Rendering differs by design**: Linux returns ANSI strings, Windows returns `(text, (R,G,B))` tuples. Both call the same `pet_core` data functions.
- **Linux runtime deps** (not pip): `xdotool`, `xprop`, `xterm`. `picom` optional for transparency.

## What to skip

- No test suite, no CI, no linter, no typechecker.
- `.trae/` contains historical design specs; not needed for current work.
- `build/` and `dist/` are gitignored PyInstaller artifacts.
