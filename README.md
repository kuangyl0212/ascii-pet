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
- **Action cooldowns**: feed/play = 1h, sleep = 3h (bypassed when stat is critical)

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
- **5% chance per tick** (500ms), 30s cooldown
- **Daily login bonus**: free item every day

### Weather System
- OpenWeatherMap integration with 30-minute cache
- IP-based geolocation fallback
- Affects pet mood
- Extreme weather reminders

### Survival
- **Stat decay**: HUNGER (after 4h offline), HAPPY (after 2h), ENERGY (after 6h)
- **Death**: pet dies if any stat hits zero for 15min, or all stats zero for 5min
- **Revival**: feed/play/sleep to revive, or use a potion

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
