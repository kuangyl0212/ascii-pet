# AGENTS.md

## Project

Terminal ASCII desktop pet for i3 (18 species, 5 rarities, 5 stats). Single file: `ascii-pet` (Python 3, ~660 lines) + `ascii-pet-launcher` (Bash, 8 lines). No build system, no tests, no dependencies beyond stdlib.

## Run

```bash
./ascii-pet                  # Direct launch
./ascii-pet --all            # Show all species
./ascii-pet [username]       # Specific user profile
./ascii-pet-launcher         # Via i3 + alacritty (kills existing instance first)
```

Requires: `alacritty`, `i3`, `picom` (transparency), `python3`, `xdotool`, `xprop`.

## Architecture

- `ascii-pet` — single-file Python script. All logic (species, rendering, state, input, achievements) in one file. Uses `termios`/`tty` for raw input, `subprocess` for xprop/xdotool (window geometry, opacity, clipboard).
- `ascii-pet-launcher` — kills existing instance via `i3-msg`, launches alacritty with `config/pet.toml`.
- `config/pet.toml` — alacritty config (transparent bg, green-on-black, no decorations, opacity 0.0).

## State

Pet state persisted to `~/.local/share/ascii-pet/<hash>.json`. Multi-pet store: `{"pets": [...], "current": N}`. Pet deterministically generated from seed (FNV-1a hash of species+name+SALT). Regenerating with same params yields same pet.

## Keybindings

- `Enter`: toggle compact ↔ expanded (`c` collapses to compact)
- `b` / `n`: previous / next pet (`n` creates new pet at end of list)
- `h`: toggle help overlay
- `i`: info panel, `t`: stats panel, `a`: achievements panel
- `f` / `p` / `s`: feed / play / sleep (non-compact modes only)
- `r`: regenerate current pet (non-compact only)
- `e`: export pet to clipboard (non-compact only, needs xclip or xsel)
- `q`: quit

## Conventions

- Single-file architecture is intentional — keep changes in `ascii-pet` unless launcher needs updating.
- No external dependencies. Do not add pip packages or requirements files.
- Transparent background requires picom + alacritty (not xterm despite README listing it).
