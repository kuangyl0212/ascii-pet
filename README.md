# ASCII Desktop Pet

A cross-platform ASCII desktop pet — runs on Linux (i3/terminal) and Windows (Win32 GDI floating window).

## Features

- 18 species (duck, cat, dragon, ghost, etc.)
- 5 rarities (common ~ legendary)
- 5 stats (HUNGER, HAPPY, ENERGY, WISDOM, CHAOS)
- Animated idle loops (blink, fidget)
- Compact mode: pet only, bottom-right corner
- Expanded mode: full stats display
- Stats mode: detailed pet info and activity history
- Achievements panel: track unlocked achievements
- Items/inventory: collect and use items
- State persistence across sessions
- Transparent background (picom compatible)

## Pet Preview

### Species Showcase

A few of the 18 species you can adopt:

duck:
```text
    __
  <(· )___
   (  ._>
    `--´
```

cat:
```text
   /\_/\
  ( ·   ·)
  (  ω  )
  (")_(")
```

dragon:
```text
  /^\  /^\
 <  ·  ·  >
 (   ~~   )
  `-vvvv-´
```

ghost:
```text
   .----.
  / ·  · \
  |      |
  ~`~``~`~
```

axolotl:
```text
}~(______)~{
}~(· .. ·)~{
  ( .--. )
  (_/  \_)
```

capybara:
```text
  n______n
 ( ·    · )
 (   oo   )
  `------´
```

### Evolution

8 species have evolution chains. Example — blob evolves at level 5 and 15:

```text
blob (lv1):       slime (lv5):      elemental (lv15):

   .----.           .----.             ~    ~
  ( ·  · )         ( ·  · )           /^\  /^\
  (      )         ( ~~~~ )          <  ·  ·  >
   `----´           `----´           (  ****  )
                                     `-vvvv-´
```

### Rarities

| Rarity | Stars | Base Stat Floor | Drop Rate |
|--------|-------|-----------------|-----------|
| Common | ★ | 5 | 60% |
| Uncommon | ★★ | 15 | 25% |
| Rare | ★★★ | 25 | 10% |
| Epic | ★★★★ | 35 | 4% |
| Legendary | ★★★★★ | 50 | 1% |

### Accessories

Non-common pets can wear hats:

```text
  crown              top hat
   \^^^/             [___]
   /\_/\             /\_/\
  ( ·   ·)          ( ·   ·)
  (  ω  )           (  ω  )
  (")_(")           (")_(")
```

## Game Features

### Pet System
- **18 species**: duck, goose, blob, cat, dragon, octopus, owl, penguin, turtle, snail, ghost, axolotl, capybara, cactus, robot, rabbit, mushroom, chonk
- **5 rarities**: common → legendary, with star ratings and stat floors
- **5 stats**: HUNGER, HAPPY, ENERGY, WISDOM, CHAOS
- **Shiny pets**: 1% chance for a special variant
- **Deterministic generation**: same user ID always produces the same pet
- **Pet limit**: max 3 pets per profile
- **Daily adoption limit**: max 3 new pets per day

### Care & Actions
- **Feed** (+25 Hunger, +5 Happy)
- **Play** (+30 Happy, -15 Energy, -10 Hunger)
- **Sleep** (+40 Energy, -5 Hunger)
- **Hover petting**: +2 Happy per hover, capped at 3/hour
- **Action cooldowns**: 1 action per minute per type (3/min when stat is critical ≤10); bypassed entirely when a stat is at zero

### Progression
- **XP & leveling**: gain XP from actions, level up at `level × 100` XP
- **Eye upgrades**: eyes change at level 5
- **Evolution**: 8 species evolve at specific levels (e.g., blob→slime lv5→elemental lv15)
- **12 achievements**: feeding, playing, sleeping, leveling, collecting, shiny hunting

### Social
- **Multiple pets**: keep up to 3 pets, switch between them
- **Pet interactions**: 30% chance when switching — play together, share food, chat, or race
- **Release mode**: release unwanted pets (can't release your last one)

### Items & Inventory
- **7 item types**: apple, toy, bed, book, potion, crown, top hat
- **Max 20 items** in inventory
- **Item sources**: random events, daily login bonus
- **Press `u`** to open inventory

### Events
- **14 random events**: sneeze, find item, mood boost, sparkle, dance, nap, sing, and more
- **2% chance per tick** (500ms), 60s cooldown
- **Daily login bonus**: free item every day

### Weather System (Linux only)
- OpenWeatherMap integration with 30-minute cache
- IP-based geolocation fallback (via ipapi.co)
- Displays a one-line weather summary in expanded mode
- Requires `config/weather.json` with an API key; silently skipped if missing

### Survival
- **Stat decay**: HUNGER (after 3h, rate 8/h), HAPPY (after 1.5h, rate 5/h), ENERGY (after 4h, rate 6/h)
- **Death**: pet dies if any stat hits zero for 15min, or all stats zero for 5min
- **Revival**: feed/play/sleep to revive, or use a potion

## Install

### Linux (i3)

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

### Windows

```powershell
# Run directly with Python
python ascii-pet-win.py

# Or build a standalone exe (auto-installs PyInstaller if missing)
python build.py
# → produces dist/ascii-pet-win.exe
```

## Usage

### Linux

```bash
# Launch via i3
$mod+p

# Or directly
ascii-pet-launcher
```

### Windows

```bash
# Run the built executable
dist\ascii-pet-win.exe

# Or run from source
python ascii-pet-win.py
```

The Windows version runs as a borderless floating window rendered via Win32 GDI
(`ctypes`), with a system tray icon for quick access.

#### Right-click on the pet window

Right-click anywhere on the pet window to open the context menu:

| Menu Item | Shortcut | Notes |
|-----------|----------|-------|
| 喂食 (Feed) | F | +25 Hunger |
| 玩耍 (Play) | P | +30 Happy |
| 睡觉 (Sleep) | S | +40 Energy |
| 领养新宠物 (Adopt) | W | New pet (max 3) |
| 导出到剪贴板 (Export) | E | Copy pet to clipboard; disabled in compact mode |
| 上一个宠物 (Prev) | B | Switch to previous pet |
| 下一个宠物 (Next) | N | Switch to next pet |
| 紧凑模式 (Compact) | — | Checked when active |
| 展开模式 (Expanded) | — | Checked when active |
| 属性面板 (Stats) | T | Checked when active |
| 成就面板 (Achievements) | A | Checked when active |
| 开机自启动 (Autostart) | — | Checked when enabled |
| 退出 (Quit) | Q | Close the app |

#### Right-click on the system tray icon

A simpler menu for quick window control:

| Menu Item | Notes |
|-----------|-------|
| 显示窗口 (Show) | Restore the pet window |
| 隐藏窗口 (Hide) | Minimize to tray |
| 开机自启动 (Autostart) | Toggle boot autostart via `HKCU\...\Run` — no admin rights needed |
| 退出 (Quit) | Close the app |

## Controls

| Key | Mode | Action |
|-----|------|--------|
| Enter | Compact | Expand to full view |
| Enter | Expanded | Return to compact |
| h | Any | Toggle help panel (also enters expanded from compact) |
| c | Any (non-compact) | Return to compact mode |
| f | Any | Feed pet (+25 Hunger, +5 Happy) |
| p | Any | Play with pet (+30 Happy, -15 Energy, -10 Hunger) |
| s | Any | Put pet to sleep (+40 Energy, -5 Hunger) |
| w | Any | Adopt a new pet (max 3; enters release mode if full) |
| b | Any | Previous pet (requires 2+ pets) |
| n | Any | Next pet |
| t | Any | Toggle stats panel |
| a | Any | Toggle achievements panel |
| u | Any | Toggle items/inventory panel |
| e | Non-compact | Export pet to clipboard |
| 1-3 | Release mode | Release pet by index |
| 1-7 | Items mode | Use item by index |
| m | Any (Linux) | Toggle move/drag mode for the window |
| q | Any | Quit |

## State

Pet state is saved to:

- **Linux**: `~/.local/share/ascii-pet/`
- **Windows**: `%APPDATA%\ascii-pet\`

State persists across sessions. On Windows, autostart debug logs are written to
`%APPDATA%\ascii-pet\autostart_debug.log`.

## Dependencies

### Linux

- Python 3
- xterm
- xdotool
- xprop
- picom (for transparency)

### Windows

- Python 3 (or use the built `dist/ascii-pet-win.exe` — no runtime deps)
- PyInstaller (build-time only, for creating the exe)

## License

MIT
