# AGENTS.md

## Project

Terminal ASCII desktop pet for i3. Two files: `ascii-pet` (Python 3, ~490 lines) and `ascii-pet-launcher` (Bash, 8 lines). No build system, no tests, no dependencies beyond stdlib.

## Run

```bash
./ascii-pet                  # Direct launch
./ascii-pet-launcher         # Via i3 + alacritty (kills existing instance first)
```

Requires: `alacritty`, `i3`, `picom` (transparency), `python3`.

## Architecture

- `ascii-pet` — single-file Python script. All logic (species, rendering, state, input) in one file. Uses `termios`/`tty` for raw input, `subprocess` for xprop/xdotool.
- `ascii-pet-launcher` — kills existing window, launches via alacritty with `config/pet.toml`.
- `config/pet.toml` — alacritty config (transparent bg, green-on-black, no decorations).

## State

Pet state persisted to `~/.local/share/ascii-pet/` as JSON. Multiple pets per user, stored as `{"pets": [...], "current": 0}`. Pet is deterministically generated from a seed (hash of species+name), so regenerating with same params yields same pet.

## Conventions

- Single-file architecture is intentional — keep changes in `ascii-pet` unless launcher needs updating.
- No external dependencies. Do not add pip packages or requirements files.
- Transparent background requires picom + alacritty (not xterm despite README listing it).

## Keybindings

- `Enter`: toggle compact ↔ expanded (also Esc to collapse)
- `← →`: switch between pets (cycles; creates new if only 1)
- `n`: create new pet, `r`: regenerate current pet
- `f`/`p`/`s`: feed/play/sleep (expanded/info modes only)
