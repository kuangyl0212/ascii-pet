#!/usr/bin/env python3
"""Platform-independent game logic for ASCII Desktop Pet."""

import os, json, time, random, math, queue, string, shutil
from pathlib import Path
from datetime import datetime
from ascii_pet.i18n import _

# ─── Constants ────────────────────────────────────────────────────────────────

SPECIES = ['duck','goose','blob','cat','dragon','octopus','owl','penguin',
           'turtle','snail','ghost','axolotl','capybara','cactus','robot','rabbit','mushroom','chonk']

EVOLUTION_CHAIN = {
    'blob':    [('slime', 5), ('elemental', 15)],
    'duck':    [('goose', 5), ('swan', 15)],
    'cat':     [('tiger', 5), ('lion', 15)],
    'dragon':  [('wyvern', 10), ('dragonlord', 25)],
    'owl':     [('phoenix', 10), ('sage', 20)],
    'rabbit':  [('hare', 5), ('jackalope', 15)],
    'snail':   [('shell', 5), ('turbo', 15)],
    'ghost':   [('wraith', 10), ('specter', 20)],
}

EYES = ['·','✦','×','◉','@','°']
RARITIES = ['common','uncommon','rare','epic','legendary']
RARITY_WEIGHTS = {'common':60,'uncommon':25,'rare':10,'epic':4,'legendary':1}
RARITY_STARS = {'common':'★','uncommon':'★★','rare':'★★★','epic':'★★★★','legendary':'★★★★★'}
RARITY_FLOOR = {'common':5,'uncommon':15,'rare':25,'epic':35,'legendary':50}
STAT_NAMES = ['HUNGER','HAPPY','ENERGY','WISDOM','CHAOS']

THEMES = {
    'green': {
        'name': 'Green',
        'color_dim': (0, 220, 50),
        'color_msg': (255, 215, 0),
        'color_white': (0, 255, 65),
        'color_bar_fill': (0, 200, 0),
        'color_bar_empty': (80, 80, 80),
        'color_hover_bg': (25, 25, 45),
        'ansi_dim': '\033[90m',
        'ansi_white': '\033[32m',
        'ansi_bar_fill': '\033[32m',
    },
    'orange': {
        'name': 'Orange',
        'color_dim': (180, 120, 50),
        'color_msg': (255, 200, 50),
        'color_white': (255, 165, 0),
        'color_bar_fill': (255, 140, 0),
        'color_bar_empty': (80, 80, 80),
        'color_hover_bg': (45, 25, 15),
        'ansi_dim': '\033[33m',
        'ansi_white': '\033[38;2;255;165;0m',
        'ansi_bar_fill': '\033[38;2;255;140;0m',
    },
}

DEFAULT_THEME = 'green'
MOODS = {'happy':{'emoji':'♪'},'normal':{'emoji':'~'},
         'sleepy':{'emoji':'z'},'hungry':{'emoji':'!'},
         'excited':{'emoji':'★'}}
SALT = 'ascii-pet-2026'
MAX_PETS = 3
MAX_DAILY_ADOPTIONS = 3

RANDOM_EVENTS = [
    ('sneeze',       'Achoo!',              {}),
    ('find_item',    'Found something!',     {'item': True}),
    ('mood_boost',   'Feeling great!',      {'HAPPY': 5}),
    ('sparkle',      '✨ Sparkle!',          {}),
    ('yawn',         '*yaaawn*',            {}),
    ('find_coin',    'Found a coin!',       {'xp': 3}),
    ('dance',        '♪ Dancing! ♪',        {'HAPPY': 3}),
    ('nap',          '*zzz* quick nap',     {'ENERGY': 5}),
    ('sing',         '♪ La la la ♪',        {'WISDOM': 3}),
    ('tripped',      'Tripped! Ouch!',      {'HAPPY': -5}),
    ('found_food',   'Found a snack!',      {'HUNGER': 5}),
    ('stomach_ache', 'Stomach ache... ugh', {'HUNGER': -5}),
    ('nightmare',    '*bad dream* nooo',    {'ENERGY': -5}),
    ('boredom',      'so bored...',         {'HAPPY': -5}),
]

PET_INTERACTIONS = [
    ('play_together', ' played together!',  {'HAPPY': 5},  'both'),
    ('share_food',    ' shared a snack!',   {'HUNGER': 10}, 'current'),
    ('chat',          ' had a nice chat!',  {'WISDOM': 5},  'both'),
    ('race',          ' had a race!',       {'ENERGY': 10}, 'current'),
]

ITEMS = {
    'apple':   {'name':'Apple',    'icon':'🍎', 'effect':{'HUNGER':30},  'desc':'Restores 30 hunger'},
    'toy':     {'name':'Toy',      'icon':'🎾', 'effect':{'HAPPY':30},   'desc':'Restores 30 happiness'},
    'bed':     {'name':'Bed',      'icon':'🛏', 'effect':{'ENERGY':30},  'desc':'Restores 30 energy'},
    'book':    {'name':'Book',     'icon':'📖', 'effect':{'WISDOM':10},  'desc':'Grants 10 wisdom'},
    'potion':  {'name':'Potion',   'icon':'🧪', 'effect':{'revive':True}, 'desc':'Revives a dead pet'},
    'crown':   {'name':'Crown',    'icon':'👑', 'effect':{'hat':'crown'}, 'desc':'A fancy crown'},
    'tophat':  {'name':'Top Hat',  'icon':'🎩', 'effect':{'hat':'tophat'},'desc':'A classy top hat'},
    'crystal': {'name':'Chaos Crystal', 'icon':'💎', 'effect':{'CHAOS':15}, 'desc':'Grants 15 chaos'},
}
MAX_INVENTORY = 20

ACHIEVEMENTS = {
    'first_feed':    {'name':'First Meal',    'icon':'🍖', 'check': lambda s,p: s.get('feed_count',0) >= 1},
    'feeder_10':     {'name':'Gourmet',       'icon':'🍽', 'check': lambda s,p: s.get('feed_count',0) >= 10},
    'feeder_100':    {'name':'Master Chef',   'icon':'👨‍🍳', 'check': lambda s,p: s.get('feed_count',0) >= 100},
    'first_play':    {'name':'Playtime',      'icon':'⚽', 'check': lambda s,p: s.get('play_count',0) >= 1},
    'player_10':     {'name':'Best Friend',   'icon':'❤️', 'check': lambda s,p: s.get('play_count',0) >= 10},
    'sleeper_10':    {'name':'Sleepyhead',    'icon':'💤', 'check': lambda s,p: s.get('sleep_count',0) >= 10},
    'level_5':       {'name':'Rising Star',   'icon':'⭐', 'check': lambda s,p: s['level'] >= 5},
    'level_10':      {'name':'Veteran',       'icon':'🌟', 'check': lambda s,p: s['level'] >= 10},
    'level_25':      {'name':'Legend',        'icon':'👑', 'check': lambda s,p: s['level'] >= 25},
    'collector_5':   {'name':'Pet Collector', 'icon':'🐾', 'check': lambda s,p: len(p['pets']) >= 5},
    'legendary':     {'name':'Lucky Find',    'icon':'🌈', 'check': lambda s,p: s['rarity'] == 'legendary'},
    'shiny':         {'name':'Shiny Hunter',  'icon':'✨', 'check': lambda s,p: s['shiny']},
}

BODIES = {
    'duck':[['            ','    __      ','  <({E} )___  ','   (  ._>   ','    `--´    '],['            ','    __      ','  <({E} )___  ','   (  ._>   ','    `--´~   '],['            ','    __      ','  <({E} )___  ','   (  .__>  ','    `--´    ']],
    'goose':[['            ','     ({E}>    ','     ||     ','   _(__)_   ','    ^^^^    '],['            ','    ({E}>     ','     ||     ','   _(__)_   ','    ^^^^    '],['            ','     ({E}>>   ','     ||     ','   _(__)_   ','    ^^^^    ']],
    'blob':[['            ','   .----.   ','  ( {E}  {E} )  ','  (      )  ','   `----´   '],['            ','  .------.  ',' (  {E}  {E}  ) ',' (        ) ','  `------´  '],['            ','    .--.    ','   ({E}  {E})   ','   (    )   ','    `--´    ']],
    'cat':[['            ','   /\\_/\\    ','  ( {E}   {E})  ','  (  ω  )   ','  (")_(")   '],['            ','   /\\_/\\    ','  ( {E}   {E})  ','  (  ω  )   ','  (")_(")~  '],['            ','   /\\-/\\    ','  ( {E}   {E})  ','  (  ω  )   ','  (")_(")   ']],
    'dragon':[['            ','  /^\\  /^\\  ',' <  {E}  {E}  > ',' (   ~~   ) ','  `-vvvv-´  '],['            ','  /^\\  /^\\  ',' <  {E}  {E}  > ',' (        ) ','  `-vvvv-´  '],['   ~    ~   ','  /^\\  /^\\  ',' <  {E}  {E}  > ',' (   ~~   ) ','  `-vvvv-´  ']],
    'octopus':[['            ','   .----.   ','  ( {E}  {E} )  ','  (______)  ','  /\\/\\/\\/\\  '],['            ','   .----.   ','  ( {E}  {E} )  ','  (______)  ','  \\/\\/\\/\\/  '],['     o      ','   .----.   ','  ( {E}  {E} )  ','  (______)  ','  /\\/\\/\\/\\  ']],
    'owl':[['            ','   /\\  /\\   ','  (({E})({E}))  ','  (  ><  )  ','   `----´   '],['            ','   /\\  /\\   ','  (({E})({E}))  ','  (  ><  )  ','   .----.   '],['            ','   /\\  /\\   ','  (({E})(-))  ','  (  ><  )  ','   `----´   ']],
    'penguin':[['            ','   .---.    ','   ({E}>{E})    ','  /(   )\\   ','   `---´    '],['            ','   .---.    ','   ({E}>{E})    ','  |(   )|   ','   `---´    '],['   .---.    ','   ({E}>{E})    ','  /(   )\\   ','   `---´    ','    ~ ~     ']],
    'turtle':[['            ','   _,--._   ','  ( {E}  {E} )  ',' /[______]\\ ','  ``    ``  '],['            ','   _,--._   ','  ( {E}  {E} )  ',' /[______]\\ ','   ``  ``   '],['            ','   _,--._   ','  ( {E}  {E} )  ',' /[======]\\ ','  ``    ``  ']],
    'snail':[['            ',' {E}    .--.  ','  \\  ( @ )  ','   \\_`--´   ','  ~~~~~~~   '],['            ','  {E}   .--.  ','  |  ( @ )  ','   \\_`--´   ','  ~~~~~~~   '],['            ',' {E}    .--.  ','  \\  ( @  ) ','   \\_`--´   ','   ~~~~~~   ']],
    'ghost':[['            ','   .----.   ','  / {E}  {E} \\  ','  |      |  ','  ~`~``~`~  '],['            ','   .----.   ','  / {E}  {E} \\  ','  |      |  ','  `~`~~`~`  '],['    ~  ~    ','   .----.   ','  / {E}  {E} \\  ','  |      |  ','  ~~`~~`~~  ']],
    'axolotl':[['            ','}~(______)~{','}~({E} .. {E})~{','  ( .--. )  ','  (_/  \\_)  '],['            ','~}(______){~','~}({E} .. {E}){~','  ( .--. )  ','  (_/  \\_)  '],['            ','}~(______)~{','}~({E} .. {E})~{','  (  --  )  ','  ~_/  \\_~  ']],
    'capybara':[['            ','  n______n  ',' ( {E}    {E} ) ',' (   oo   ) ','  `------´  '],['            ','  n______n  ',' ( {E}    {E} ) ',' (   Oo   ) ','  `------´  '],['    ~  ~    ','  u______n  ',' ( {E}    {E} ) ',' (   oo   ) ','  `------´  ']],
    'cactus':[['            ',' n  ____  n ',' | |{E}  {E}| | ',' |_|    |_| ','   |    |   '],['            ','    ____    ',' n |{E}  {E}| n ',' |_|    |_| ','   |    |   '],[' n        n ',' |  ____  | ',' | |{E}  {E}| | ',' |_|    |_| ','   |    |   ']],
    'robot':[['            ','   .[||].   ','  [ {E}  {E} ]  ','  [ ==== ]  ','  `------´  '],['            ','   .[||].   ','  [ {E}  {E} ]  ','  [ -==- ]  ','  `------´  '],['     *      ','   .[||].   ','  [ {E}  {E} ]  ','  [ ==== ]  ','  `------´  ']],
    'rabbit':[['            ','   (\\__/)   ','  ( {E}  {E} )  ',' =(  ..  )= ','  (")__(")  '],['            ','   (|__/)   ','  ( {E}  {E} )  ',' =(  ..  )= ','  (")__(")  '],['            ','   (\\__/)   ','  ( {E}  {E} )  ',' =( .  . )= ','  (")__(")  ']],
    'mushroom':[['            ',' .-o-OO-o-. ','(__________)','   |{E}  {E}|   ','   |____|   '],['            ',' .-O-oo-O-. ','(__________)','   |{E}  {E}|   ','   |____|   '],['   . o  .   ',' .-o-OO-o-. ','(__________)','   |{E}  {E}|   ','   |____|   ']],
    'chonk':[['            ','  /\\    /\\  ',' ( {E}    {E} ) ',' (   ..   ) ','  `------´  '],['            ','  /\\    /|  ',' ( {E}    {E} ) ',' (   ..   ) ','  `------´  '],['            ','  /\\    /\\  ',' ( {E}    {E} ) ',' (   ..   ) ','  `------´~ ']],
}

EVOLVED_BODIES = {
    'slime': [
        ['            ', '   .----.   ', '  ( {E}  {E} )  ', '  ( ~~~~ )  ', '   `----´   '],
        ['            ', '  .------.  ', ' (  {E}  {E}  ) ', ' ( ~~~~~~ ) ', '  `------´  '],
        ['            ', '    .--.    ', '   ({E}  {E})   ', '   (~~~~)   ', '    `--´    '],
    ],
    'elemental': [
        ['   ~    ~   ', '  /^\\  /^\\  ', ' <  {E}  {E}  > ', ' (  ****  ) ', '  `-vvvv-´  '],
        ['  ~   ~   ~ ', '  /^\\  /^\\  ', ' <  {E}  {E}  > ', ' (  ****  ) ', '  `-vvvv-´  '],
        ['   ~    ~   ', '  /^\\  /^\\  ', ' <  {E}  {E}  > ', ' (        ) ', '  `-vvvv-´  '],
    ],
    'swan': [
        ['            ', '     ({E}>    ', '    /||\\    ', '   / || \\   ', '    ~~~~    '],
        ['            ', '    ({E}>     ', '    /||\\    ', '   / || \\   ', '    ~~~~    '],
        ['            ', '     ({E}>>   ', '    /||\\    ', '   / || \\   ', '    ~~~~    '],
    ],
    'tiger': [
        ['   /\\_/\\    ', '  ( {E}   {E})  ', '  (  ≈ω≈ )  ', '  (")_(")   ', '   |||||    '],
        ['   /\\_/\\    ', '  ( {E}   {E})  ', '  (  ≈ω≈ )  ', '  (")_(")~  ', '   |||||    '],
        ['   /\\-/\\    ', '  ( {E}   {E})  ', '  (  ≈ω≈ )  ', '  (")_(")   ', '   |||||    '],
    ],
    'lion': [
        ['  /^^^^^\\   ', ' ( {E}   {E} ) ', ' (  ≈ω≈  ) ', ' (")_(")    ', '  |||||||   '],
        ['  /^^^^^\\   ', ' ( {E}   {E} ) ', ' (  ≈ω≈  ) ', ' (")_(")~   ', '  |||||||   '],
        ['  /^^^^^\\   ', ' ( {E}   {E} ) ', ' (  ≈ω≈  ) ', ' (")_(")    ', '  |||||||   '],
    ],
    'wyvern': [
        [' /^\\  /^\\  ', ' <  {E}  {E}  > ', ' (  ~~~~ ) ', '  \\vvvv/   ', '   ^^      '],
        [' /^\\  /^\\  ', ' <  {E}  {E}  > ', ' (        ) ', '  \\vvvv/   ', '   ^^      '],
        [' /^\\  /^\\  ', ' <  {E}  {E}  > ', ' (  ~~~~ ) ', '  \\vvvv/   ', '   ~~      '],
    ],
    'dragonlord': [
        [' /^^\\  /^^\\', ' <  {E}  {E}  > ', ' (  ≈≈≈≈ ) ', '  \\vvvv/   ', '   @@@     '],
        [' /^^\\  /^^\\', ' <  {E}  {E}  > ', ' (        ) ', '  \\vvvv/   ', '   @@@     '],
        [' /^^\\  /^^\\', ' <  {E}  {E}  > ', ' (  ≈≈≈≈ ) ', '  \\vvvv/   ', '   ~~~     '],
    ],
    'phoenix': [
        ['   *  *    ', '  /{E}\\  /{E}\\ ', ' <  ~~   > ', '  (~~~~)   ', '   `--´    '],
        ['  * ** *   ', '  /{E}\\  /{E}\\ ', ' <      > ', '  (~~~~)   ', '   `--´    '],
        ['   *  *    ', '  /{E}\\  /{E}\\ ', ' <  ~~   > ', '  (    )   ', '   `--´    '],
    ],
    'sage': [
        ['   /\\  /\\  ', '  (({E})({E}))  ', '  (  ><  ) ', '   `----´  ', '   |oo|    '],
        ['   /\\  /\\  ', '  (({E})({E}))  ', '  (  ><  ) ', '   .----.  ', '   |oo|    '],
        ['   /\\  /\\  ', '  (({E})(-))  ', '  (  ><  ) ', '   `----´  ', '   |oo|    '],
    ],
    'hare': [
        ['   (\\__/)  ', '  ( {E}  {E} ) ', ' =(  ..  )=', '  (")__(") ', '   /\\ /\\   '],
        ['   (|__/)  ', '  ( {E}  {E} ) ', ' =(  ..  )=', '  (")__(") ', '   /\\ /\\   '],
        ['   (\\__/)  ', '  ( {E}  {E} ) ', ' =( .  . )=', '  (")__(") ', '   /\\ /\\   '],
    ],
    'jackalope': [
        ['   (\\__/)  ', '  ( {E}  {E} ) ', ' =(  ..  )=', '  (")__(") ', '   /\\ /\\   '],
        ['   (|__/)  ', '  ( {E}  {E} ) ', ' =(  ..  )=', '  (")__(") ', '   /\\ /\\   '],
        ['   (\\__/)  ', '  ( {E}  {E} ) ', ' =( .  . )=', '  (")__(") ', '   /\\ /\\   '],
    ],
    'shell': [
        ['  .---.    ', ' / {E} {E} \\  ', ' \\_____)/  ', '  `---´    ', '   ~~~~    '],
        ['  .---.    ', ' / {E} {E} \\  ', ' \\_____)\\  ', '  `---´    ', '   ~~~~    '],
        ['  .---.    ', ' / {E} {E} \\  ', ' \\_____)\\  ', '  `---´    ', '   ~~~~    '],
    ],
    'turbo': [
        ['  .---.    ', ' / {E} {E} \\  ', ' \\=====/   ', '  `---´    ', '  >>>>>    '],
        ['  .---.    ', ' / {E} {E} \\  ', ' \\=====/   ', '  `---´    ', '  >>>>>    '],
        ['  .---.    ', ' / {E} {E} \\  ', ' \\=====/   ', '  `---´    ', '  >>>>>    '],
    ],
    'wraith': [
        ['   .----.  ', '  / {E}  {E} \\ ', '  | ~~~~ | ', '  ~`~``~`~ ', '   .  . .  '],
        ['   .----.  ', '  / {E}  {E} \\ ', '  | ~~~~ | ', '  `~`~~`~` ', '    .  .   '],
        ['   .----.  ', '  / {E}  {E} \\ ', '  | ~~~~ | ', '  ~~`~~`~~ ', '   .  . .  '],
    ],
    'specter': [
        ['   .----.  ', '  / {E}  {E} \\ ', '  | **** | ', '  ~`~``~`~ ', '   *  * *  '],
        ['   .----.  ', '  / {E}  {E} \\ ', '  | **** | ', '  `~`~~`~` ', '    *  *   '],
        ['   .----.  ', '  / {E}  {E} \\ ', '  | **** | ', '  ~~`~~`~~ ', '   *  * *  '],
    ],
}

HAT_LINES = {'none':'','crown':'   \\^^^/    ','tophat':'   [___]    ','propeller':'    -+-     ','halo':'   (   )    ','wizard':'    /^\\     ','beanie':'   (___)    ','tinyduck':'    ,>      '}
IDLE_SEQUENCE = [0,0,0,0,0,0,1,0,0,0,0,0,2,0,0,0,-1,0,0,0,0,1,0,0,0,0,0,2,0,0]
MOOD_SEQUENCES = {
    'normal':  [0,0,0,0,0,0,1,0,0,0,0,0,2,0,0,0,-1,0,0,0,0,1,0,0,0,0,0,2,0,0],
    'happy':   [0,1,0,2,0,1,0,2,0,1,0,2,-1,0,0,0,1,0,2,0,1,0,2,0],
    'excited': [0,1,2,0,1,2,0,1,2,-1,0,1,2,0,1,2,0,1,2,-1,0,1,2,0],
    'hungry':  [0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,-1,0,0,0,0,0,0,0,0],
    'sleepy':  [0,0,0,0,-1,0,0,0,0,0,-1,0,0,0,0,0,-1,0,0,0,0,0,0,0],
}
ADJECTIVES = ['Tiny','Fluffy','Brave','Sneaky','Cosmic','Dizzy','Fuzzy','Mighty','Wobbly','Crispy','Sparkly','Grumpy','Sleepy','Zippy','Bouncy','Spooky','Jolly','Rusty','Stormy','Lucky','Peppy','Zany','Quirky','Sassy']
NOUNS = ['Bean','Nugget','Sprout','Biscuit','Noodle','Pebble','Pickle','Muffin','Waffle','Squish','Pudding','Crumble','Tater','Dumpling','Scraps','Widget','Pixel','Nibble','Scooter','Snickers','Wobbles','Patches','Buttons','Pip']

ANIMATIONS = {
    'feed':  ['  ♪nom  ','  ♪nom♪ ','  ~yum~ '],
    'play':  ['  *  *  ',' * ** * ','  *  *  '],
    'sleep': ['  z     ','  z Z   ','  z Z z '],
}

# ─── PRNG ─────────────────────────────────────────────────────────────────────

def mulberry32(seed):
    a = seed & 0xFFFFFFFF
    def rng():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = a; t = (t ^ (t >> 15)) & 0xFFFFFFFF; t = (t * (1 | t)) & 0xFFFFFFFF
        t = (t ^ (t >> 7)) & 0xFFFFFFFF; t = (t * 61 | t) & 0xFFFFFFFF
        t = (t ^ (t >> 14)) & 0xFFFFFFFF
        return (t & 0xFFFFFFFF) / 0x100000000
    return rng

def hash_string(s):
    h = 2166136261
    for c in s: h ^= ord(c); h = (h * 16777619) & 0xFFFFFFFF
    return h

def pick(rng, arr): return arr[int(rng() * len(arr))]

# ─── Pet generation ───────────────────────────────────────────────────────────

def roll_rarity(rng):
    total = sum(RARITY_WEIGHTS.values()); roll = rng() * total
    for r in RARITIES:
        roll -= RARITY_WEIGHTS[r]
        if roll < 0: return r
    return 'common'

def roll_stats(rng, rarity):
    floor = RARITY_FLOOR[rarity]; peak = pick(rng, STAT_NAMES); dump = pick(rng, STAT_NAMES)
    while dump == peak: dump = pick(rng, STAT_NAMES)
    stats = {}
    for n in STAT_NAMES:
        if n == peak: stats[n] = min(100, floor + 50 + int(rng()*30))
        elif n == dump: stats[n] = max(1, floor - 10 + int(rng()*15))
        else: stats[n] = floor + int(rng()*40)
    return stats

def generate_companion(uid, seed=None):
    if seed is None: seed = str(time.time_ns())
    rng = mulberry32(hash_string(uid + SALT + seed)); rarity = roll_rarity(rng)
    return {'rarity':rarity,'species':pick(rng,SPECIES),'eye':pick(rng,EYES),
            'hat':'none' if rarity=='common' else pick(rng,list(HAT_LINES.keys())),
            'shiny':rng()<0.01,'stats':roll_stats(rng,rarity)}

def generate_name(uid, seed=None):
    if seed is None: seed = str(time.time_ns())
    rng = mulberry32(hash_string(uid + SALT + seed + '-name'))
    return pick(rng, ADJECTIVES) + ' ' + pick(rng, NOUNS)

# ─── Rendering (data only) ───────────────────────────────────────────────────

def render_sprite(bones, frame=0):
    all_bodies = {**BODIES, **EVOLVED_BODIES}
    frames = all_bodies.get(bones['species'], BODIES.get(bones['species'], BODIES['blob']))
    body = [l.replace('{E}', bones['eye']) for l in frames[frame % len(frames)]]
    if bones['hat'] != 'none' and not body[0].strip(): body[0] = HAT_LINES[bones['hat']]
    if not body[0].strip() and all(not f[0].strip() for f in frames): body.pop(0)
    return body

def render_face(bones):
    e = bones['eye']
    faces = {'duck':f'({e}>','goose':f'({e}>','blob':f'({e}{e})','cat':f'={e}ω{e}=',
        'dragon':f'<{e}~{e}>','octopus':f'~({e}{e})~','owl':f'({e})({e})',
        'penguin':f'({e}>)','turtle':f'[{e}_{e}]','snail':f'{e}(@)',
        'ghost':f'/{e}{e}\\','axolotl':f'}}{e}.{e}{{','capybara':f'({e}oo{e})',
        'cactus':f'|{e}  {e}|','robot':f'[{e}{e}]','rabbit':f'({e}..{e})',
        'mushroom':f'|{e}  {e}|','chonk':f'({e}.{e})',
        'slime':f'({e}{e})','elemental':f'<{e}*{e}>',
        'swan':f'({e}>','tiger':f'={e}≈{e}=','lion':f'({e}≈{e})',
        'wyvern':f'<{e}~{e}>','dragonlord':f'<{e}@{e}>',
        'phoenix':f'({e}*{e})','sage':f'({e})({e})',
        'hare':f'({e}..{e})','jackalope':f'({e}..{e})',
        'shell':f'({e}{e})','turbo':f'({e}{e})',
        'wraith':f'/{e}{e}\\','specter':f'/{e}{e}\\'}
    return faces.get(bones['species'], f'({e}{e})')

def render_frame(bones, frame_idx, mood='normal'):
    seq = MOOD_SEQUENCES.get(mood, IDLE_SEQUENCE)
    step = seq[frame_idx % len(seq)]

    if step == -1:
        f = render_sprite(bones, 0)
        body = [l.replace(bones['eye'], '-') for l in f]
    else:
        body = render_sprite(bones, step % 3)

    bob = int(math.sin(frame_idx * 0.4) * 0.8)
    if bob > 0:
        body = ['            '] * bob + body
    elif bob < 0:
        body = body[-bob:]
    return body

# ─── Actions ──────────────────────────────────────────────────────────────────

def feed_pet(state):
    if state['stats']['HUNGER'] >= 100: return _('Already full!'), None
    state['stats']['HUNGER'] = min(100, state['stats']['HUNGER']+25)
    state['stats']['HAPPY'] = min(100, state['stats']['HAPPY']+5)
    state['last_fed'] = datetime.now().isoformat()
    state['total_interactions'] += 1; state['feed_count'] = state.get('feed_count',0) + 1
    state['xp'] += 10; evo = check_level_up(state)
    if evo: return evo, None
    return _('+25 Hunger, +5 Happy'), 'feed'

def play_pet(state):
    if state['stats']['ENERGY'] < 10: return _('Too tired!'), None
    state['stats']['HAPPY'] = min(100, state['stats']['HAPPY']+30)
    state['stats']['ENERGY'] = max(0, state['stats']['ENERGY']-15)
    state['stats']['HUNGER'] = max(0, state['stats']['HUNGER']-10)
    state['last_played'] = datetime.now().isoformat()
    state['total_interactions'] += 1; state['play_count'] = state.get('play_count',0) + 1
    state['xp'] += 15; evo = check_level_up(state)
    if evo: return evo, None
    return _('+30 Happy, -15 Energy'), 'play'

def sleep_pet(state):
    if state['stats']['ENERGY'] >= 100: return _('Not sleepy!'), None
    state['stats']['ENERGY'] = min(100, state['stats']['ENERGY']+40)
    state['stats']['HUNGER'] = max(0, state['stats']['HUNGER']-5)
    state['last_slept'] = datetime.now().isoformat()
    state['total_interactions'] += 1; state['sleep_count'] = state.get('sleep_count',0) + 1
    state['xp'] += 5; evo = check_level_up(state)
    if evo: return evo, None
    return _('+40 Energy'), 'sleep'

def check_level_up(state):
    xp_need = state['level'] * 100
    while state['xp'] >= xp_need:
        state['xp'] -= xp_need; state['level'] += 1
        state['stats']['WISDOM'] = min(100, state['stats']['WISDOM']+5)
        xp_need = state['level'] * 100
    if state['level'] >= 10: state['evolved'] = True
    if state['level'] >= 5 and not state.get('eye_upgraded'):
        idx = EYES.index(state['eye']) if state['eye'] in EYES else 0
        state['eye'] = EYES[(idx + 1) % len(EYES)]
        state['eye_upgraded'] = True
    # Check evolution chain
    chain = EVOLUTION_CHAIN.get(state['species'])
    if chain:
        for evo_species, evo_level in chain:
            if state['level'] >= evo_level and state['species'] != evo_species:
                state['species'] = evo_species
                state['evolved'] = True
                return _('Evolved into {species}!').format(species=evo_species)
    return None

def check_achievements(state, pets_data):
    unlocked = []
    for aid, ach in ACHIEVEMENTS.items():
        if aid not in state.get('achievements', []) and ach['check'](state, pets_data):
            state.setdefault('achievements', []).append(aid)
            unlocked.append(_(ach['name']))
    return unlocked

# ─── State management ─────────────────────────────────────────────────────────

def init_state(uid, bones, name):
    now = datetime.now().isoformat()
    return {'user_id':uid,'name':name,'species':bones['species'],'rarity':bones['rarity'],
            'eye':bones['eye'],'hat':bones['hat'],'shiny':bones['shiny'],'stats':bones['stats'],
            'mood':'normal','created_at':now,'last_fed':now,'last_played':now,'last_slept':now,
            'level':1,'xp':0,'total_interactions':0,
            'feed_count':0,'play_count':0,'sleep_count':0,'achievements':[],
            'critical_since':None,'is_dead':False,
            'last_feed':None,'last_play':None,'last_sleep':None,'pet_count_hour':0,'pet_hour_start':None}

def update_state_over_time(state):
    now = datetime.now()
    for key, decay, rate in [('last_fed',3,8),('last_played',1.5,5),('last_slept',4,6)]:
        hours = (now - datetime.fromisoformat(state[key])).total_seconds() / 3600
        if hours > decay:
            stat = {'last_fed':'HUNGER','last_played':'HAPPY','last_slept':'ENERGY'}[key]
            state['stats'][stat] = max(0, state['stats'][stat] - int(hours * rate))
    h, e, p = state['stats']['HUNGER'], state['stats']['ENERGY'], state['stats']['HAPPY']
    state['mood'] = 'hungry' if h<20 else 'sleepy' if e<20 else 'excited' if p>80 else 'happy' if p>50 else 'normal'
    return state

# ─── Persistence ──────────────────────────────────────────────────────────────

def _default_data_dir():
    if os.name == 'nt':
        return Path(os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))) / 'ascii-pet'
    return Path.home() / '.local' / 'share' / 'ascii-pet'

def get_state_path(uid, data_dir=None):
    if data_dir is None: data_dir = _default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / f'{hash_string(uid) & 0xFFFFFFFF:08x}.json'

def validate_save_file(path):
    """Validate that a save file exists, is readable, valid JSON, and has 'pets' field."""
    if not path.exists():
        return False
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return isinstance(data, dict) and 'pets' in data
    except (json.JSONDecodeError, OSError, ValueError):
        return False

MAX_BACKUPS = 10

def _get_backup_dir(uid, data_dir=None):
    if data_dir is None: data_dir = _default_data_dir()
    backup_dir = data_dir / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir

def create_backup(uid, data_dir=None, backup_type='auto'):
    """Create a backup of the current save file. Returns the backup Path."""
    src = get_state_path(uid, data_dir)
    backup_dir = _get_backup_dir(uid, data_dir)
    h = f'{hash_string(uid) & 0xFFFFFFFF:08x}'
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = backup_dir / f'{h}_{backup_type}_{ts}.json'
    shutil.copy2(src, dst)
    # Cleanup: keep only MAX_BACKUPS newest
    backups = sorted(backup_dir.glob(f'{h}_*.json'), key=lambda p: p.stat().st_mtime)
    while len(backups) > MAX_BACKUPS:
        backups.pop(0).unlink()
    return dst

def list_backups(uid, data_dir=None):
    """List backups for a uid, sorted by mtime descending. Returns [(filename, datetime, backup_type)]."""
    backup_dir = _get_backup_dir(uid, data_dir)
    h = f'{hash_string(uid) & 0xFFFFFFFF:08x}'
    result = []
    for p in backup_dir.glob(f'{h}_*.json'):
        # Parse timestamp and type from filename: {hash}_{type}_YYYYMMDD_HHMMSS.json
        # Also support old format: {hash}_YYYYMMDD_HHMMSS.json (type defaults to 'auto')
        ts_str = p.name[len(h)+1:-5]  # strip hash_ and .json
        parts = ts_str.split('_', 1)
        if len(parts) == 2 and parts[0] in ('auto', 'manual'):
            btype = parts[0]
            ts_part = parts[1]
        else:
            # Old format: no type field, ts_str is YYYYMMDD_HHMMSS
            btype = 'auto'
            ts_part = ts_str
        try:
            ts = datetime.strptime(ts_part, '%Y%m%d_%H%M%S')
        except ValueError:
            continue
        result.append((p.name, ts, btype))
    result.sort(key=lambda x: x[1], reverse=True)
    return result

def restore_from_backup(uid, backup_filename, data_dir=None):
    """Restore save from a backup file. Returns True on success, False if backup not found."""
    backup_dir = _get_backup_dir(uid, data_dir)
    src = backup_dir / backup_filename
    if not src.exists():
        return False
    # Read backup content first to avoid collision if pre-restore backup
    # generates the same filename (same-second timestamp)
    backup_data = src.read_bytes()
    # Create a pre-restore backup of current state
    dst = get_state_path(uid, data_dir)
    if dst.exists():
        create_backup(uid, data_dir, backup_type='auto')
    dst.write_bytes(backup_data)
    return True

def load_pets_with_fallback(uid, data_dir=None):
    """Load pets with backup fallback. Returns (data, status).
    status: 'ok', 'no_file', 'restored', 'corrupt_no_backup'
    """
    save_path = get_state_path(uid, data_dir)
    if not save_path.exists():
        return None, 'no_file'
    try:
        data = load_pets(uid, data_dir)
    except (json.JSONDecodeError, OSError, ValueError):
        data = None
    if data is not None and validate_save_file(save_path):
        return data, 'ok'
    # Corrupt — try to restore from backup
    backups = list_backups(uid, data_dir)
    if backups:
        restore_from_backup(uid, backups[0][0], data_dir)
        data = load_pets(uid, data_dir)
        return data, 'restored'
    return None, 'corrupt_no_backup'

def load_pets(uid, data_dir=None):
    p = get_state_path(uid, data_dir)
    if not p.exists(): return None
    data = json.load(open(p, encoding='utf-8'))
    if isinstance(data, list): data = {'pets': data, 'current': 0}
    if 'pets' not in data: data = {'pets': [data], 'current': 0}
    if 'inventory' not in data: data['inventory'] = {}
    return data

def save_pets(uid, data, data_dir=None):
    json.dump(data, open(get_state_path(uid, data_dir), 'w', encoding='utf-8'), indent=2)

def load_state(uid, data_dir=None):
    data = load_pets(uid, data_dir)
    if data is None: return None, None, 0
    idx = data.get('current', 0)
    if idx >= len(data['pets']): idx = 0
    return data['pets'][idx], data, idx

def save_state(uid, state, pets_data, idx, data_dir=None):
    pets_data['pets'][idx] = state
    save_pets(uid, pets_data, data_dir)

# ─── Export text ──────────────────────────────────────────────────────────────

def export_text(state, bones, frame_idx):
    stars = RARITY_STARS[state['rarity']]
    frame = render_frame(bones, frame_idx, state.get('mood','normal'))
    lines = [f'{state["name"]}  {stars}', f'{state["species"]} · {state["rarity"]}', '']
    for row in frame: lines.append(row)
    lines.append('')
    lines.append(f'face: {render_face(bones)}')
    lines.append('')
    for s in STAT_NAMES:
        v = state['stats'][s]
        lines.append(f'{s[:4]}  {"█"*round(v/5)}{"░"*(20-round(v/5))} {v}')
    return '\n'.join(lines)

# ─── LAN username helpers ─────────────────────────────────────────────────────

def generate_random_username():
    """Generate a random username in the form ``Player-XXXX``.

    The suffix is 4 uppercase alphanumeric characters (A-Z, 0-9).
    """
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=4))
    return f"Player-{suffix}"

def resolve_name_conflict(username, existing_names):
    """Resolve username conflict by auto-appending a numeric suffix.

    If ``username`` is not in ``existing_names``, returns it unchanged.
    Otherwise, finds the smallest available number N >= 2 such that
    ``username(N)`` is not taken, and returns ``username(N)``.
    Gaps are filled (e.g. if Alice and Alice(3) exist, returns Alice(2)).

    Args:
        username: Desired username.
        existing_names: List of already-taken usernames.

    Returns:
        A username that does not conflict with existing_names.
    """
    if username not in existing_names:
        return username
    used_numbers = set()
    prefix = username + "("
    for name in existing_names:
        if name == username:
            used_numbers.add(1)  # original name counts as #1
        elif name.startswith(prefix) and name.endswith(")"):
            num_str = name[len(prefix):-1]
            try:
                num = int(num_str)
                if num >= 2:
                    used_numbers.add(num)
            except ValueError:
                pass
    n = 2
    while n in used_numbers:
        n += 1
    return f"{username}({n})"
# ─── Game class ───────────────────────────────────────────────────────────────

class PetGame:
    """Platform-independent game state and logic."""

    def __init__(self, uid, data_dir=None):
        from ascii_pet.i18n import init_language
        init_language(data_dir)
        self.uid = uid
        self.data_dir = data_dir
        self.frame_idx = 0
        self.mode = 'compact'
        self.show_help = False
        self.message = None
        self.message_time = 0
        self.visit_message_time = 0
        self.action_message_time = 0
        self.last_event_time = 0
        self.anim_end = 0
        self.anim_frames = []
        self.anim_idx = 0
        self.warning_active = False
        self.last_tick_time = time.time()
        self._decay_accum = {stat: 0.0 for stat in STAT_NAMES}

        data, fallback_status = load_pets_with_fallback(uid, data_dir)
        if fallback_status == 'ok':
            idx = data.get('current', 0)
            if idx >= len(data['pets']): idx = 0
            state, pets_data, pet_idx = data['pets'][idx], data, idx
        elif fallback_status == 'restored':
            idx = data.get('current', 0)
            if idx >= len(data['pets']): idx = 0
            state, pets_data, pet_idx = data['pets'][idx], data, idx
            self.message = _('Save corrupted, restored from backup')
            self.message_time = time.time()
        elif fallback_status == 'corrupt_no_backup':
            bones = generate_companion(uid); name = generate_name(uid)
            state = init_state(uid, bones, name)
            pets_data = {'pets': [state], 'current': 0, 'adoption_log': []}; pet_idx = 0
            save_pets(uid, pets_data, data_dir)
            self.message = _('Save corrupted with no backup, created new save')
            self.message_time = time.time()
        else:  # 'no_file'
            bones = generate_companion(uid); name = generate_name(uid)
            state = init_state(uid, bones, name)
            pets_data = {'pets': [state], 'current': 0, 'adoption_log': []}; pet_idx = 0
            save_pets(uid, pets_data, data_dir)
        if 'adoption_log' not in pets_data:
            pets_data['adoption_log'] = []
        self.state = state
        self.pets_data = pets_data
        self.pet_idx = pet_idx
        self.bones = {k: state[k] for k in ('species','eye','hat','shiny','rarity')}

        self.state = update_state_over_time(self.state)
        save_state(uid, self.state, pets_data, pet_idx, data_dir)

        # Daily login bonus
        today = datetime.now().date().isoformat()
        if self.pets_data.get('last_login') != today:
            create_backup(uid, data_dir, backup_type='auto')
            self.pets_data['last_login'] = today
            if sum(self.pets_data.get('inventory', {}).values()) < MAX_INVENTORY:
                item_id = random.choice(list(ITEMS.keys()))
                self.add_item(item_id)
                if self.message is None:
                    self.message = _('Daily bonus: {name}!').format(name=_(ITEMS[item_id]["name"]))
                    self.message_time = time.time()
            self.save()

        # LAN multiplayer state - auto-enable on startup
        self.lan_enabled = False
        self.lan_node = None
        self.lan_peers = []
        self.visitor_pets = []
        self.active_visit = None
        self.being_visited = None
        self.visit_event_cooldown = 0.0
        # Load username from save data
        self.lan_username = self.pets_data.get('username')
        # Migrate old username.txt if no username in save
        if self.lan_username is None and self.data_dir is not None:
            old_file = Path(self.data_dir) / 'username.txt' if not isinstance(self.data_dir, Path) else self.data_dir / 'username.txt'
            if old_file.exists():
                try:
                    self.lan_username = old_file.read_text(encoding='utf-8').strip()
                    self.pets_data['username'] = self.lan_username
                    self.save()
                except Exception:
                    pass
        # Auto-enable LAN (non-blocking, graceful failure)
        try:
            self.enable_lan()
        except Exception:
            pass  # Network unavailable, continue with local play

    def save(self):
        save_state(self.uid, self.state, self.pets_data, self.pet_idx, self.data_dir)

    def count_today_adoptions(self):
        """Count how many pets were adopted today (from log, not current list)."""
        today = datetime.now().date()
        count = 0
        for ts in self.pets_data.get('adoption_log', []):
            try:
                if datetime.fromisoformat(ts).date() == today:
                    count += 1
            except: pass
        return count

    def tick(self):
        """Called every 500ms. Returns (message, message_time) or (None, 0)."""
        self.frame_idx += 1
        now = time.time()
        delta_hours = (now - self.last_tick_time) / 3600
        self.last_tick_time = now

        if self.state.get('is_dead'):
            return None, 0

        stats = self.state['stats']
        decay_config = [('last_fed', 3, 8, 'HUNGER'), ('last_played', 1.5, 5, 'HAPPY'), ('last_slept', 4, 6, 'ENERGY')]
        for key, threshold, rate, stat in decay_config:
            hours_since = (datetime.now() - datetime.fromisoformat(self.state[key])).total_seconds() / 3600
            if hours_since > threshold:
                self._decay_accum[stat] += delta_hours * rate
                decay = int(self._decay_accum[stat])
                if decay > 0:
                    self._decay_accum[stat] -= decay
                    stats[stat] = max(0, stats[stat] - decay)

        self.state['mood'] = 'hungry' if stats['HUNGER']<20 else 'sleepy' if stats['ENERGY']<20 else 'excited' if stats['HAPPY']>80 else 'happy' if stats['HAPPY']>50 else 'normal'
        self.save()

        h, e, p = stats['HUNGER'], stats['ENERGY'], stats['HAPPY']
        msg, msg_time = None, 0
        critical = h == 0 or e == 0 or p == 0
        all_zero = h == 0 and e == 0 and p == 0

        if critical:
            if self.state.get('critical_since') is None:
                self.state['critical_since'] = datetime.now().isoformat()
            critical_secs = (datetime.now() - datetime.fromisoformat(self.state['critical_since'])).total_seconds()
            if all_zero and critical_secs >= 300:
                self.state['is_dead'] = True
                self.save()
                return _('Your pet has died...'), now
            elif critical_secs >= 900:
                self.state['is_dead'] = True
                self.save()
                return _('Your pet has died...'), now
            if all_zero:
                remaining = int((300 - critical_secs) / 60) + 1
                msg = _('CRITICAL! All stats at zero! ({remaining}min left)').format(remaining=remaining); msg_time = now
            else:
                remaining = int((900 - critical_secs) / 60) + 1
                msg = _('CRITICAL! A stat is at zero! ({remaining}min left)').format(remaining=remaining); msg_time = now
            self.warning_active = True
        else:
            if self.state.get('critical_since'):
                self.state['critical_since'] = None
                self.save()
            if h < 10:
                msg = _('Your pet is starving!'); msg_time = now; self.warning_active = True
            elif e < 10:
                msg = _('Your pet is exhausted!'); msg_time = now; self.warning_active = True
            elif p < 10:
                msg = _('Your pet is lonely!'); msg_time = now; self.warning_active = True
            else:
                self.warning_active = False

        chaos = self.state['stats']['CHAOS']
        event_chance = 0.02 * (1 + chaos / 100)
        if now - self.last_event_time > 60 and random.random() < event_chance:
            evt = random.choice(RANDOM_EVENTS)
            msg = _(evt[1]); msg_time = now; self.last_event_time = now
            # Negative events increase CHAOS
            negative_stats = {k: v for k, v in evt[2].items() if k in self.state['stats'] and v < 0}
            if negative_stats:
                self.state['stats']['CHAOS'] = min(100, self.state['stats']['CHAOS'] + 3)
            for k, v in evt[2].items():
                if k == 'xp': self.state['xp'] += v; evo = check_level_up(self.state)
                elif k == 'item':
                    item_id = random.choice(list(ITEMS.keys()))
                    if self.add_item(item_id):
                        msg = _('Found a {name}!').format(name=_(ITEMS[item_id]["name"])); msg_time = now
                elif k in self.state['stats']:
                    if v > 0 and self.state['stats'][k] >= 80:
                        continue
                    self.state['stats'][k] = min(100, max(0, self.state['stats'][k] + v))

        # 拜访相关检查
        if self.lan_enabled:
            try:
                self._tick_visit_timeout()
                self._tick_visit_events()
            except Exception:
                pass

        # Don't let tick warnings overwrite recent visit or action messages (2s grace)
        if msg and now - self.visit_message_time < 5:
            msg = None
        if msg and now - self.action_message_time < 2:
            msg = None

        return msg, msg_time

    def handle_action(self, action):
        """Execute an action. Returns (message, anim_type)."""
        if self.state.get('is_dead'):
            if action in ('feed', 'play', 'sleep'):
                return _('Your pet is dead... Use a Potion to revive!'), None
            return _('Your pet is dead...'), None

        now = datetime.now()
        critical = self.state.get('critical_since') is not None
        if not critical and action in ('feed', 'play', 'sleep'):
            stat_map = {'feed': 'HUNGER', 'play': 'HAPPY', 'sleep': 'ENERGY'}
            stat_val = self.state['stats'][stat_map[action]]
            limit = 3 if stat_val <= 10 else 1
            minute_key = now.strftime('%Y-%m-%d %H:%M')
            state_key = f'{action}_min'
            state_minute = self.state.get(f'{state_key}_time')
            if state_minute != minute_key:
                self.state[f'{state_key}_time'] = minute_key
                self.state[f'{state_key}_count'] = 0
            count = self.state.get(f'{state_key}_count', 0)
            if count >= limit:
                return _('Wait a moment before {action}ing again.').format(action=action), None
            self.state[f'{state_key}_count'] = count + 1

        if action == 'feed':
            msg, anim = feed_pet(self.state)
        elif action == 'play':
            msg, anim = play_pet(self.state)
        elif action == 'sleep':
            msg, anim = sleep_pet(self.state)
        else:
            return None, None

        self.save()
        new_ach = check_achievements(self.state, self.pets_data)
        if new_ach: msg = _('Achievement: {name}!').format(name=new_ach[0])
        return msg, anim

    def handle_pet(self):
        """Handle hover petting with cooldown. Returns message or None."""
        if self.state.get('is_dead'):
            return None
        now = datetime.now()
        critical = self.state.get('critical_since') is not None
        if not critical:
            hour_start = self.state.get('pet_hour_start')
            if hour_start is None or (now - datetime.fromisoformat(hour_start)).total_seconds() >= 3600:
                self.state['pet_hour_start'] = now.isoformat()
                self.state['pet_count_hour'] = 0
            if self.state['pet_count_hour'] >= 3:
                return None
            self.state['pet_count_hour'] = self.state.get('pet_count_hour', 0) + 1
        self.state['stats']['HAPPY'] = min(100, self.state['stats']['HAPPY'] + 2)
        self.save()
        return None

    def switch_pet(self, direction):
        """Switch to prev (-1) or next (+1) pet. Only cycles through existing pets."""
        self.pets_data['pets'][self.pet_idx] = self.state
        if direction < 0:
            self.pet_idx = (self.pet_idx - 1) % len(self.pets_data['pets'])
        else:
            self.pet_idx = (self.pet_idx + 1) % len(self.pets_data['pets'])
        self.state = self.pets_data['pets'][self.pet_idx]
        self.bones = {k: self.state[k] for k in ('species','eye','hat','shiny','rarity')}
        self.pets_data['current'] = self.pet_idx
        save_pets(self.uid, self.pets_data, self.data_dir)
        new_ach = check_achievements(self.state, self.pets_data)
        msg = _('Switched to {name}').format(name=self.state["name"])
        if new_ach: msg = _('Achievement: {name}!').format(name=new_ach[0])
        interaction_msg = self.trigger_interaction()
        if interaction_msg: msg = f'{msg}\n  {interaction_msg}'
        return msg

    def trigger_interaction(self):
        """Random interaction between pets when switching. Returns message or None."""
        if len(self.pets_data['pets']) < 2:
            return None
        if random.random() > 0.3:
            return None
        interaction = random.choice(PET_INTERACTIONS)
        iid, msg, effects, target = interaction
        for stat, val in effects.items():
            if target == 'both':
                for pet in self.pets_data['pets']:
                    pet['stats'][stat] = min(100, pet['stats'][stat] + val)
            else:
                self.state['stats'][stat] = min(100, self.state['stats'][stat] + val)
        self.save()
        other = self.pets_data['pets'][(self.pet_idx - 1) % len(self.pets_data['pets'])]
        return f'{self.state["name"]} and {other["name"]}{_(msg)}'

    def adopt_pet(self):
        """Adopt a new pet. Returns message or None if entering release mode."""
        if len(self.pets_data['pets']) >= MAX_PETS:
            self.mode = 'release'
            self.pets_data['current'] = self.pet_idx
            save_pets(self.uid, self.pets_data, self.data_dir)
            return None
        if self.count_today_adoptions() >= MAX_DAILY_ADOPTIONS:
            return _('Daily limit reached ({max}/day). Try again tomorrow!').format(max=MAX_DAILY_ADOPTIONS)
        self.pets_data['pets'][self.pet_idx] = self.state
        new_state = init_state(self.uid, generate_companion(self.uid), generate_name(self.uid))
        self.pets_data['pets'].append(new_state)
        self.pets_data.setdefault('adoption_log', []).append(datetime.now().isoformat())
        self.pet_idx = len(self.pets_data['pets']) - 1
        self.state = self.pets_data['pets'][self.pet_idx]
        self.bones = {k: self.state[k] for k in ('species','eye','hat','shiny','rarity')}
        self.pets_data['current'] = self.pet_idx
        save_pets(self.uid, self.pets_data, self.data_dir)
        new_ach = check_achievements(self.state, self.pets_data)
        msg = _('Adopted {name}!').format(name=self.state["name"])
        if new_ach: msg = _('Achievement: {name}!').format(name=new_ach[0])
        return msg

    def release_pet(self, index):
        """Release a pet by index (0-based). Returns message."""
        if index < 0 or index >= len(self.pets_data['pets']):
            return _('Invalid pet!')
        if len(self.pets_data['pets']) <= 1:
            return _('Cannot release your last pet!')
        name = self.pets_data['pets'][index]['name']
        self.pets_data['pets'].pop(index)
        if self.pet_idx >= len(self.pets_data['pets']):
            self.pet_idx = len(self.pets_data['pets']) - 1
        elif self.pet_idx > index:
            self.pet_idx -= 1
        self.state = self.pets_data['pets'][self.pet_idx]
        self.bones = {k: self.state[k] for k in ('species','eye','hat','shiny','rarity')}
        self.pets_data['current'] = self.pet_idx
        self.mode = 'expanded'
        save_pets(self.uid, self.pets_data, self.data_dir)
        return _('Released {name}!').format(name=name)

    def get_release_list(self):
        """Return list of (index, name, species, rarity) for release mode."""
        result = []
        for i, s in enumerate(self.pets_data['pets']):
            result.append((i+1, s['name'], s['species'], s['rarity']))
        return result

    def add_item(self, item_id):
        """Add item to inventory. Returns True if added, False if full."""
        if sum(self.pets_data.get('inventory', {}).values()) >= MAX_INVENTORY:
            return False
        inv = self.pets_data.setdefault('inventory', {})
        inv[item_id] = inv.get(item_id, 0) + 1
        self.save()
        return True

    def use_item(self, item_id):
        """Use an item from inventory. Returns message."""
        inv = self.pets_data.get('inventory', {})
        if inv.get(item_id, 0) <= 0:
            return _('No such item!')
        item = ITEMS.get(item_id)
        if not item:
            return _('Unknown item!')
        inv[item_id] -= 1
        if inv[item_id] <= 0:
            del inv[item_id]
        effect = item['effect']
        if effect.get('revive'):
            if not self.state.get('is_dead'):
                return _('Pet is not dead!')
            self.state['is_dead'] = False
            self.state['critical_since'] = None
            self.state['stats']['HUNGER'] = 25
            self.state['stats']['ENERGY'] = 25
            self.state['stats']['HAPPY'] = 25
        elif 'hat' in effect:
            self.state['hat'] = effect['hat']
            self.bones['hat'] = effect['hat']
        else:
            for stat, val in effect.items():
                if stat in self.state['stats']:
                    self.state['stats'][stat] = min(100, self.state['stats'][stat] + val)
        self.save()
        return _('Used {name}!').format(name=_(item["name"]))

    def get_inventory_list(self):
        """Return list of (item_id, name, icon, count, desc) for display."""
        inv = self.pets_data.get('inventory', {})
        result = []
        for iid, count in inv.items():
            item = ITEMS.get(iid)
            if item and count > 0:
                result.append((iid, _(item['name']), item['icon'], count, _(item['desc'])))
        return result

    def handle_key(self, key):
        """Process a keypress. Returns (action_type, detail).

        action_type: 'quit', 'mode_change', 'action', 'pet_switch', 'export', 'none'
        detail: depends on action_type
        """
        now = time.time()
        if key == 'q':
            return 'quit', None

        if self.state.get('is_dead'):
            # f/p/s: still return Potion guidance (no revive)
            if key in ('f', 'p', 's'):
                msg, anim = self.handle_action(key if key != 'f' else 'feed')
                if key == 'p': msg, anim = self.handle_action('play')
                if key == 's': msg, anim = self.handle_action('sleep')
                self.message = msg; self.message_time = now
                return 'action', msg
            # r: direct revive with Potion
            if key == 'r':
                inv = self.pets_data.get('inventory', {})
                if inv.get('potion', 0) > 0:
                    msg = self.use_item('potion')
                    self.message = msg; self.message_time = now
                    return 'action', msg
                else:
                    msg = _('No Potion available!')
                    self.message = msg; self.message_time = now
                    return 'action', msg
            # d: release dead pet
            if key == 'd':
                msg = self.release_pet(self.pet_idx)
                self.message = msg; self.message_time = now
                return 'action', msg
            # b/n: switch pets
            if key == 'b':
                if len(self.pets_data['pets']) > 1:
                    msg = self.switch_pet(-1)
                    self.message = msg; self.message_time = now
                    return 'pet_switch', msg
                return 'none', None
            if key == 'n':
                msg = self.switch_pet(1)
                self.message = msg; self.message_time = now
                return 'pet_switch', msg
            # Allow mode switching keys to fall through
            # u, a, t, c, h, Enter, l, e will be handled by normal key processing below

        if self.mode == 'lan_name_edit':
            if key == '\r' or key == '\n':  # 回车确认
                new_name = self._name_input.strip()
                if new_name:
                    if self.change_lan_username(new_name):
                        self.message = _('Username changed to: {name}').format(name=self.lan_username)
                    else:
                        self.message = _('Username already in use')
                else:
                    self.message = _('Username cannot be empty')
                self.message_time = now
                self.mode = 'lan'
                return 'mode_change', self.mode
            if key == '\x1b':  # ESC 取消
                self.mode = 'lan'
                return 'mode_change', self.mode
            if key == '\x08':  # 退格
                self._name_input = self._name_input[:-1]
                return 'none', None
            if len(key) == 1 and key.isprintable():
                self._name_input += key
                return 'none', None
            return 'none', None

        if key in ('\r', '\n'):
            if self.mode == 'compact':
                self.mode = 'expanded'; self.show_help = False
            elif self.mode == 'expanded':
                self.mode = 'compact'; self.show_help = False
            return 'mode_change', self.mode

        if key == 'h':
            if self.mode == 'compact':
                self.mode = 'expanded'; self.show_help = True
            else:
                self.show_help = not self.show_help
            return 'mode_change', self.mode

        if key == 'c':
            if self.mode != 'compact':
                self.mode = 'compact'; self.show_help = False
                return 'mode_change', self.mode
            return 'none', None

        if key == 'b':
            if len(self.pets_data['pets']) > 1:
                msg = self.switch_pet(-1)
                self.message = msg; self.message_time = now
                return 'pet_switch', msg
            return 'none', None

        if key == 'n':
            msg = self.switch_pet(1)
            self.message = msg; self.message_time = now
            return 'pet_switch', msg

        if key == 'w':
            msg = self.adopt_pet()
            if msg is None:
                return 'mode_change', self.mode
            self.message = msg; self.message_time = now
            return 'action', msg

        if key == 't':
            if self.mode == 'stats': self.mode = 'expanded'
            elif self.mode == 'expanded': self.mode = 'stats'
            else: self.mode = 'stats'
            return 'mode_change', self.mode

        if key == 'a':
            if self.mode == 'achievements': self.mode = 'expanded'
            elif self.mode in ('expanded', 'stats'): self.mode = 'achievements'
            else: self.mode = 'achievements'
            return 'mode_change', self.mode

        if key == 'u' and self.mode != 'lan':
            if self.mode == 'items':
                self.mode = 'expanded'
            elif self.mode in ('expanded', 'stats', 'achievements'):
                self.mode = 'items'
            else:
                self.mode = 'items'
            return 'mode_change', self.mode

        if key == 'e' and self.mode != 'compact':
            return 'export', None

        if key == 'f' and self.mode != 'lan':
            msg, anim = self.handle_action('feed')
            self.message = msg; self.message_time = now; self.action_message_time = now
            if anim: self.anim_end = now + 1.5; self.anim_frames = ANIMATIONS[anim]; self.anim_idx = 0
            return 'action', msg

        if key == 'p' and self.mode != 'lan':
            msg, anim = self.handle_action('play')
            self.message = msg; self.message_time = now; self.action_message_time = now
            if anim: self.anim_end = now + 1.5; self.anim_frames = ANIMATIONS[anim]; self.anim_idx = 0
            return 'action', msg

        if key == 's':
            msg, anim = self.handle_action('sleep')
            self.message = msg; self.message_time = now; self.action_message_time = now
            if anim: self.anim_end = now + 1.5; self.anim_frames = ANIMATIONS[anim]; self.anim_idx = 0
            return 'action', msg

        if self.mode == 'release':
            if key in ('1','2','3'):
                idx = int(key) - 1
                if idx < len(self.pets_data['pets']):
                    msg = self.release_pet(idx)
                    self.message = msg; self.message_time = now
                    return 'action', msg
            if key == 'c':
                self.mode = 'expanded'
                return 'mode_change', self.mode
            return 'none', None

        if self.mode == 'items':
            if key in ('1','2','3','4','5','6','7'):
                idx = int(key) - 1
                inv_list = self.get_inventory_list()
                if idx < len(inv_list):
                    iid = inv_list[idx][0]
                    msg = self.use_item(iid)
                    self.message = msg; self.message_time = now
                    return 'action', msg
            if key == 'c':
                self.mode = 'expanded'
                return 'mode_change', self.mode
            return 'none', None

        if self.mode == 'lan':
            if key in ('1','2','3','4','5','6','7','8','9'):
                idx = int(key) - 1
                peers = self.get_lan_peers() if self.lan_enabled else []
                if idx < len(peers):
                    peer = peers[idx]
                    peer_id = peer.get('node_id', '')
                    if self.invite_visit(peer_id):
                        self.message = _('Visiting {peer}').format(peer=peer.get("username","?"))
                    else:
                        pass  # invite_visit 内部已设置 message
                    self.message_time = now
                    return 'action', self.message
            if key == 'e':
                if self.end_visit():
                    self.message = _('Visit ended')
                else:
                    self.message = _('No active visit')
                self.message_time = now
                return 'action', self.message
            if key == 'f':
                if self.remote_feed():
                    self.message = _('Remote feed sent')
                else:
                    self.message = _('Remote feed failed (not visiting)')
                self.message_time = now
                return 'action', self.message
            if key == 'p':
                if self.remote_play():
                    self.message = _('Remote play sent')
                else:
                    self.message = _('Remote play failed (not visiting)')
                self.message_time = now
                return 'action', self.message

        return 'none', None

    # ─── LAN multiplayer ──────────────────────────────────────────────────

    def enable_lan(self, username=None):
        """启用联机。成功返回True，失败返回False不抛异常。

        若未提供用户名，则尝试从存档加载；加载失败则生成随机用户名。
        启用后自动检测重名并追加后缀。
        """
        try:
            from ascii_pet.lan import LanNode
            # 如果未提供用户名，尝试从存档加载或生成
            if not username:
                username = self.lan_username
            if not username:
                username = generate_random_username()
            self.lan_username = username
            self.pets_data['username'] = username
            self.save()
            self.lan_node = LanNode(username, self.state)
            if self.lan_node.start():
                self.lan_enabled = True
                # 检查重名并自动解决
                peers = self.lan_node.get_peers()
                if peers:
                    existing = [p.get('username', '') for p in peers]
                    resolved = resolve_name_conflict(self.lan_username, existing)
                    if resolved != self.lan_username:
                        self.lan_username = resolved
                        self.pets_data['username'] = resolved
                        self.save()
                        if hasattr(self.lan_node, 'username'):
                            self.lan_node.username = resolved
                return True
            else:
                self.lan_node = None
                return False
        except Exception:
            self.lan_node = None
            self.lan_enabled = False
            return False

    def disable_lan(self):
        """禁用联机，清空状态。"""
        if self.lan_node:
            try: self.lan_node.stop()
            except Exception: pass
        self.lan_node = None
        self.lan_enabled = False
        self.lan_peers = []
        self.visitor_pets = []
        self.active_visit = None
        self.being_visited = None
        self.visit_event_cooldown = 0.0

    def change_lan_username(self, new_name):
        """修改用户名。重名时自动追加后缀，始终返回True。"""
        if not self.lan_enabled or not self.lan_node:
            return False
        peers = self.lan_node.get_peers()
        existing = [p.get('username', '') for p in peers]
        resolved = resolve_name_conflict(new_name, existing)
        self.lan_username = resolved
        self.pets_data['username'] = resolved
        self.save()
        if hasattr(self.lan_node, 'username'):
            self.lan_node.username = resolved
        return True

    def get_lan_status(self):
        """返回网络状态摘要。"""
        if not self.lan_enabled or not self.lan_node:
            return {"enabled": False, "is_master": False, "peer_count": 0, "error": None}
        return self.lan_node.get_status()

    def get_lan_peers(self):
        """返回对等节点列表。"""
        if not self.lan_enabled or not self.lan_node:
            return []
        return self.lan_node.get_peers()

    def invite_visit(self, peer_node_id):
        """单向发起拜访，直接发送宠物快照，无需对方确认。"""
        if not self.lan_enabled or not self.lan_node:
            return False
        # 拜访锁定检查
        if self.active_visit is not None:
            self.message = _("You are visiting, please end current visit first")
            self.message_time = time.time()
            return False
        if self.being_visited is not None:
            self.message = _("You are being visited, cannot initiate visit")
            self.message_time = time.time()
            return False
        from ascii_pet.protocol import MSG_VISIT_REQ, make_pet_snapshot
        snapshot = make_pet_snapshot(self.state, self.lan_username or self.uid)
        ok = self.lan_node.send_to_peer(peer_node_id, MSG_VISIT_REQ, {
            "from": self.lan_node.get_status().get("node_id", ""),
            "from_username": self.lan_username or self.uid,
            "pet_snapshot": snapshot,
        })
        if ok:
            self.active_visit = {
                "target": peer_node_id,
                "start_time": time.time(),
                "pet_snapshot": snapshot,
            }
        return ok

    def end_visit(self):
        """结束拜访。发起方和受访者均可调用。"""
        from ascii_pet.protocol import MSG_VISIT_END
        if self.active_visit:
            target = self.active_visit.get("target", "")
            if target and self.lan_node:
                try:
                    self.lan_node.send_to_peer(target, MSG_VISIT_END, {"reason": "manual"})
                except Exception:
                    pass
            self.active_visit = None
            return True
        if self.being_visited:
            sender = self.being_visited.get("from", "")
            if sender and self.lan_node:
                try:
                    self.lan_node.send_to_peer(sender, MSG_VISIT_END, {"reason": "manual"})
                except Exception:
                    pass
            # 从 visitor_pets 中移除对应访客
            snap = self.being_visited.get("pet_snapshot", {})
            snap_name = snap.get("name", "")
            for i, v in enumerate(self.visitor_pets):
                if v.get("name", "") == snap_name:
                    self.visitor_pets.pop(i)
                    break
            self.being_visited = None
            return True
        return False

    def remote_feed(self):
        """远程喂食对方宠物。"""
        from ascii_pet.protocol import MSG_VISIT_FEED
        if not self.active_visit or not self.lan_node:
            return False
        target = self.active_visit.get("target", "")
        try:
            return self.lan_node.send_to_peer(target, MSG_VISIT_FEED, {"from": self.lan_username})
        except Exception:
            return False

    def remote_play(self):
        """远程玩耍。"""
        from ascii_pet.protocol import MSG_VISIT_PLAY
        if not self.active_visit or not self.lan_node:
            return False
        target = self.active_visit.get("target", "")
        try:
            return self.lan_node.send_to_peer(target, MSG_VISIT_PLAY, {"from": self.lan_username})
        except Exception:
            return False

    def receive_visitor(self, snapshot):
        """接收访客宠物快照。"""
        self.visitor_pets.append(snapshot)

    def dismiss_visitor(self, index):
        """让访客离开。"""
        if 0 <= index < len(self.visitor_pets):
            visitor = self.visitor_pets.pop(index)
            if self.lan_enabled and self.lan_node:
                from ascii_pet.protocol import MSG_VISIT_LEAVE
                owner_id = visitor.get("owner", "")
                if owner_id:
                    self.lan_node.send_to_peer(owner_id, MSG_VISIT_LEAVE, {"pet_name": visitor.get("name","")})
            return True
        return False

    def process_lan_queues(self):
        """UI线程轮询处理网络消息。"""
        if not self.lan_enabled or not self.lan_node:
            return
        while True:
            try:
                msg = self.lan_node.ui_queue.get_nowait()
            except queue.Empty:
                break
            except Exception:
                break
            try:
                self._handle_lan_message(msg)
            except Exception:
                pass  # 单条消息处理失败不影响后续

    def _handle_lan_message(self, msg):
        """处理单条网络消息。"""
        from ascii_pet.protocol import (MSG_VISIT_REQ, MSG_VISIT_DATA, MSG_VISIT_LEAVE,
                                  MSG_VISIT_FEED, MSG_VISIT_PLAY, MSG_VISIT_EVENT, MSG_VISIT_END)
        msg_type = msg.get("type")
        payload = msg.get("payload", {})
        now = time.time()

        if msg_type == MSG_VISIT_REQ:
            # 单向拜访，自动接收
            snapshot = payload.get("pet_snapshot", {})
            from_id = payload.get("from", "")
            from_username = payload.get("from_username", "?")
            self.being_visited = {"from": from_id, "start_time": now, "pet_snapshot": snapshot}
            self.visitor_pets.append(snapshot)
            self.message = _("{username}'s pet {name} came to visit!").format(username=from_username, name=snapshot.get('name','?'))
            self.message_time = now
            self.visit_message_time = now

        elif msg_type == MSG_VISIT_FEED:
            # 收到远程喂食请求，执行本地 feed 并显示数值变化
            stat_key = 'HUNGER'
            before = self.state['stats'].get(stat_key, 0)
            result = self.handle_action('feed')
            after = self.state['stats'].get(stat_key, 0)
            delta = after - before
            from_name = payload.get("from", "?")
            if delta > 0:
                self.message = _("{name} fed your pet! {stat} {before}->{after}(+{delta})").format(name=from_name, stat=stat_key, before=before, after=after, delta=delta)
            else:
                self.message = _("{name} fed your pet! {result}").format(name=from_name, result=result[0])
            self.message_time = now
            self.visit_message_time = now

        elif msg_type == MSG_VISIT_PLAY:
            # 收到远程玩耍请求，执行本地 play 并显示数值变化
            stat_key = 'HAPPY'
            before = self.state['stats'].get(stat_key, 0)
            result = self.handle_action('play')
            after = self.state['stats'].get(stat_key, 0)
            delta = after - before
            from_name = payload.get("from", "?")
            if delta > 0:
                self.message = _("{name} played with your pet! {stat} {before}->{after}(+{delta})").format(name=from_name, stat=stat_key, before=before, after=after, delta=delta)
            else:
                self.message = _("{name} played with your pet! {result}").format(name=from_name, result=result[0])
            self.message_time = now
            self.visit_message_time = now

        elif msg_type == MSG_VISIT_EVENT:
            # 收到随机事件，应用效果
            description = payload.get("description", "")
            stat_effects = payload.get("stat_effects", {})
            self._apply_visit_event_effects(stat_effects)
            self.message = _("Visit event: {desc}").format(desc=description)
            self.message_time = now
            self.visit_message_time = now

        elif msg_type == MSG_VISIT_END:
            # 结束拜访
            if self.active_visit:
                self.active_visit = None
                self.message = _("Visit ended")
                self.message_time = now
            if self.being_visited:
                snap = self.being_visited.get("pet_snapshot", {})
                snap_name = snap.get("name", "")
                for i, v in enumerate(self.visitor_pets):
                    if v.get("name", "") == snap_name:
                        self.visitor_pets.pop(i)
                        break
                self.being_visited = None
                self.message = _("Visit ended")
                self.message_time = now

        elif msg_type == MSG_VISIT_DATA:
            # 兼容旧客户端：直接加入访客列表
            self.receive_visitor(payload)
            self.message = _("{name} came to visit!").format(name=payload.get('name',''))
            self.message_time = now

        elif msg_type == MSG_VISIT_LEAVE:
            # 兼容旧客户端：移除对应访客
            pet_name = payload.get("pet_name", "")
            for i, v in enumerate(self.visitor_pets):
                if v.get("name") == pet_name:
                    self.visitor_pets.pop(i)
                    break

    def _apply_visit_event_effects(self, stat_effects):
        """应用拜访随机事件的属性效果。"""
        stats = self.state.get('stats', {})
        for stat, delta in stat_effects.items():
            stat_upper = stat.upper() if isinstance(stat, str) else stat
            if stat_upper in stats:
                current = stats[stat_upper]
                stats[stat_upper] = max(0, min(100, current + delta))
            elif stat in stats:
                current = stats[stat]
                stats[stat] = max(0, min(100, current + delta))

    def _tick_visit_timeout(self):
        """检查拜访超时（10分钟）。"""
        VISIT_TIMEOUT = 600  # 10分钟
        now = time.time()
        if self.active_visit and now - self.active_visit.get("start_time", 0) > VISIT_TIMEOUT:
            self.end_visit()
            self.message = _("Visit timed out, auto-ended")
            self.message_time = now
        elif self.being_visited and now - self.being_visited.get("start_time", 0) > VISIT_TIMEOUT:
            self.end_visit()
            self.message = _("Visit timed out, auto-ended")
            self.message_time = now

    def _tick_visit_events(self):
        """拜访期间随机触发互动事件。"""
        import random
        from ascii_pet.protocol import VISIT_EVENTS, MSG_VISIT_EVENT, make_visit_event
        now = time.time()
        # 只在活跃拜访时触发
        if not self.active_visit and not self.being_visited:
            return
        # 冷却检查
        if now < self.visit_event_cooldown:
            return
        # 10% 概率触发
        if random.random() > 0.10:
            return
        # 随机选择事件
        event = random.choice(VISIT_EVENTS)
        # 应用本地效果
        self._apply_visit_event_effects(event.get("stat_effects", {}))
        self.message = _("Visit event: {desc}").format(desc=event.get('description',''))
        self.message_time = now
        self.visit_message_time = now
        # 设置冷却
        self.visit_event_cooldown = now + 30  # 30秒冷却
        # 发送给对方
        event_msg = make_visit_event(event["event_type"], event["description"], event["stat_effects"])
        try:
            if self.active_visit and self.lan_node:
                target = self.active_visit.get("target", "")
                if target:
                    self.lan_node.send_to_peer(target, MSG_VISIT_EVENT, event_msg)
            elif self.being_visited and self.lan_node:
                sender = self.being_visited.get("from", "")
                if sender:
                    self.lan_node.send_to_peer(sender, MSG_VISIT_EVENT, event_msg)
        except Exception:
            pass
