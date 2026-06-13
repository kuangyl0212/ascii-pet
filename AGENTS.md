# AGENTS.md

ASCII desktop pet: one Python file per platform, no external runtime deps, no tests, no lint.

## Files

| File | Lines | Platform | Notes |
|------|-------|----------|-------|
| `ascii-pet` | 653 | Linux (also Win32 via `msvcrt`) | ANSI terminal via `termios`/`tty`, window control via `xdotool`/`xprop` |
| `ascii-pet-win.py` | 1338 | Windows | Win32 GDI via `ctypes` + `windll` |
| `ascii-pet-launcher` | 8 | Linux (i3) | Bash — kills old instance, launches alacritty with `config/pet.toml` |
| `build.py` | 38 | — | PyInstaller → `dist/ascii-pet-win.exe` |
| `config/pet.toml` | 15 | — | Alacritty config: transparent bg, monospace font, green-on-black |

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

- **Single-file is intentional** — keep all logic in the platform file. Do not split or extract modules.
- **Zero pip dependencies** at runtime (stdlib only). PyInstaller is build-time only.
- **Data constants are duplicated** across both `ascii-pet` and `ascii-pet-win.py` (SPECIES, BODIES, ACHIEVEMENTS, etc.). Mirror changes across both files.
- **State path**: Linux → `~/.local/share/ascii-pet/`, Windows → `%APPDATA%\ascii-pet\`.
- **Deterministic generation**: Custom FNV-1a hash (`hash_string()`) of uid+SALT (`'ascii-pet-2026'`) feeds a mulberry32 PRNG. Same uid = same pet.
- **Linux runtime deps** (not pip): `xdotool`, `xprop`, `xterm`. `picom` optional for transparency.

## What to skip

- No test suite, no CI, no linter, no typechecker.
- `.trae/` contains historical design specs; not needed for current work.
- `build/` and `dist/` are gitignored PyInstaller artifacts.
