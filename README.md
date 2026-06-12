# ASCII Desktop Pet

A terminal-based ASCII desktop pet for i3 window manager.

## Features

- 18 species (duck, cat, dragon, ghost, etc.)
- 5 rarities (common ~ legendary)
- 5 stats (HUNGER, HAPPY, ENERGY, WISDOM, CHAOS)
- Animated idle loops (blink, fidget)
- Compact mode: pet only, bottom-right corner
- Expanded mode: full stats display
- Info mode: detailed pet info
- State persistence across sessions
- Transparent background (picom compatible)

## Install

```bash
# Copy files
cp ascii-pet ~/.local/bin/
cp ascii-pet-launcher ~/.local/bin/
chmod +x ~/.local/bin/ascii-pet ~/.local/bin/ascii-pet-launcher

# Add to i3 config (~/.config/i3/config)
for_window [class="ascii-pet"] floating enable
for_window [class="ascii-pet"] sticky enable
for_window [class="ascii-pet"] border pixel 0
for_window [class="ascii-pet"] title_format ""
bindsym $mod+p exec --no-startup-id ~/.local/bin/ascii-pet-launcher

# Reload i3
$mod+Shift+r
```

## Usage

```bash
# Launch via i3
$mod+p

# Or directly
ascii-pet-launcher
```

## Controls

| Key | Mode | Action |
|-----|------|--------|
| Enter | Compact | Expand to full view |
| Enter | Expanded | Return to compact |
| Enter | Info | Back to expanded |
| b | Expanded/Info | Previous pet |
| n | Expanded/Info | Next pet (creates new at end) |
| i | Expanded | Toggle info panel |
| i | Info | Back to expanded |
| f | Expanded/Info | Feed pet (+25 Hunger) |
| p | Expanded/Info | Play with pet (+30 Happy) |
| s | Expanded/Info | Put pet to sleep (+40 Energy) |
| r | Expanded/Info | Regenerate current pet |
| q | Any | Quit |

## State

Pet state is saved to `~/.local/share/ascii-pet/` and persists across sessions.

## Dependencies

- Python 3
- xterm
- xdotool
- xprop
- picom (for transparency)

## License

MIT
