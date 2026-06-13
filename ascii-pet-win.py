#!/usr/bin/env python3
"""ASCII Desktop Pet — Windows 浮动桌面宠物 (Win32 API + ctypes)"""

import os, sys, json, time, random, hashlib, struct, ctypes
from pathlib import Path
from datetime import datetime
from ctypes import windll, c_int, c_uint, c_long, c_wchar_p, byref, sizeof, create_unicode_buffer
from ctypes import wintypes, POINTER, c_void_p, c_char_p, c_size_t, memmove, c_byte

# ═══════════════════════════════════════════════════════════════════════════════
# 数据常量（从原版复制）
# ═══════════════════════════════════════════════════════════════════════════════

SPECIES = ['duck','goose','blob','cat','dragon','octopus','owl','penguin',
           'turtle','snail','ghost','axolotl','capybara','cactus','robot','rabbit','mushroom','chonk']
EYES = ['·','✦','×','◉','@','°']
RARITIES = ['common','uncommon','rare','epic','legendary']
RARITY_WEIGHTS = {'common':60,'uncommon':25,'rare':10,'epic':4,'legendary':1}
RARITY_STARS = {'common':'★','uncommon':'★★','rare':'★★★','epic':'★★★★','legendary':'★★★★★'}
RARITY_FLOOR = {'common':5,'uncommon':15,'rare':25,'epic':35,'legendary':50}
STAT_NAMES = ['HUNGER','HAPPY','ENERGY','WISDOM','CHAOS']
MOODS = {'happy':{'emoji':'♪'},'normal':{'emoji':'~'},
         'sleepy':{'emoji':'z'},'hungry':{'emoji':'!'},
         'excited':{'emoji':'★'}}
SALT = 'ascii-pet-2026'

RANDOM_EVENTS = [
    ('sneeze',    'Achoo!',             {}),
    ('find_item', 'Found a shiny pebble!', {'xp': 5}),
    ('mood_boost','Feeling great!',     {'HAPPY': 10}),
    ('sparkle',   '✨ Sparkle!',         {}),
    ('yawn',      '*yaaawn*',           {}),
]

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
HAT_LINES = {'none':'','crown':'   \\^^^/    ','tophat':'   [___]    ','propeller':'    -+-     ','halo':'   (   )    ','wizard':'    /^\\     ','beanie':'   (___)    ','tinyduck':'    ,>      '}
IDLE_SEQUENCE = [0,0,0,0,1,0,0,0,-1,0,0,2,0,0,0]
MOOD_SEQUENCES = {
    'normal':  [0,0,0,0,1,0,0,0,-1,0,0,2,0,0,0],
    'happy':   [0,1,0,1,0,0,2,0,2,0,-1,0,0,0,0],
    'excited': [0,1,2,1,2,1,0,-1,0,1,2,1,2,0,0],
    'hungry':  [0,0,0,0,0,0,2,2,0,0,0,0,0,0,0],
    'sleepy':  [0,0,0,-1,0,0,0,0,-1,0,0,0,0,0,0],
}
ADJECTIVES = ['Tiny','Fluffy','Brave','Sneaky','Cosmic','Dizzy','Fuzzy','Mighty','Wobbly','Crispy','Sparkly','Grumpy','Sleepy','Zippy','Bouncy','Spooky','Jolly','Rusty','Stormy','Lucky','Peppy','Zany','Quirky','Sassy']
NOUNS = ['Bean','Nugget','Sprout','Biscuit','Noodle','Pebble','Pickle','Muffin','Waffle','Squish','Pudding','Crumble','Tater','Dumpling','Scraps','Widget','Pixel','Nibble','Scooter','Snickers','Wobbles','Patches','Buttons','Pip']

ANIMATIONS = {
    'feed':  ['  ♪nom  ','  ♪nom♪ ','  ~yum~ '],
    'play':  ['  *  *  ',' * ** * ','  *  *  '],
    'sleep': ['  z     ','  z Z   ','  z Z z '],
}

# ═══════════════════════════════════════════════════════════════════════════════
# 纯逻辑函数（从原版复制）
# ═══════════════════════════════════════════════════════════════════════════════

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

def render_sprite(bones, frame=0):
    frames = BODIES[bones['species']]
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
        'mushroom':f'|{e}  {e}|','chonk':f'({e}.{e})'}
    return faces.get(bones['species'], f'({e}{e})')

def render_frame(bones, frame_idx, mood='normal'):
    seq = MOOD_SEQUENCES.get(mood, IDLE_SEQUENCE)
    step = seq[frame_idx % len(seq)]
    if step == -1:
        f = render_sprite(bones, 0)
        return [l.replace(bones['eye'], '-') for l in f]
    return render_sprite(bones, step)

def feed_pet(state):
    if state['stats']['HUNGER'] >= 100: return 'Already full!', None
    state['stats']['HUNGER'] = min(100, state['stats']['HUNGER']+25)
    state['stats']['HAPPY'] = min(100, state['stats']['HAPPY']+5)
    state['last_fed'] = datetime.now().isoformat()
    state['total_interactions'] += 1; state['feed_count'] = state.get('feed_count',0) + 1
    state['xp'] += 10; check_level_up(state)
    return '+25 Hunger, +5 Happy', 'feed'

def play_pet(state):
    if state['stats']['ENERGY'] < 10: return 'Too tired!', None
    state['stats']['HAPPY'] = min(100, state['stats']['HAPPY']+30)
    state['stats']['ENERGY'] = max(0, state['stats']['ENERGY']-15)
    state['stats']['HUNGER'] = max(0, state['stats']['HUNGER']-10)
    state['last_played'] = datetime.now().isoformat()
    state['total_interactions'] += 1; state['play_count'] = state.get('play_count',0) + 1
    state['xp'] += 15; check_level_up(state)
    return '+30 Happy, -15 Energy', 'play'

def sleep_pet(state):
    if state['stats']['ENERGY'] >= 100: return 'Not sleepy!', None
    state['stats']['ENERGY'] = min(100, state['stats']['ENERGY']+40)
    state['stats']['HUNGER'] = max(0, state['stats']['HUNGER']-5)
    state['last_slept'] = datetime.now().isoformat()
    state['total_interactions'] += 1; state['sleep_count'] = state.get('sleep_count',0) + 1
    state['xp'] += 5; check_level_up(state)
    return '+40 Energy', 'sleep'

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

def check_achievements(state, pets_data):
    unlocked = []
    for aid, ach in ACHIEVEMENTS.items():
        if aid not in state.get('achievements', []) and ach['check'](state, pets_data):
            state.setdefault('achievements', []).append(aid)
            unlocked.append(ach['name'])
    return unlocked

def init_state(uid, bones, name):
    now = datetime.now().isoformat()
    return {'user_id':uid,'name':name,'species':bones['species'],'rarity':bones['rarity'],
            'eye':bones['eye'],'hat':bones['hat'],'shiny':bones['shiny'],'stats':bones['stats'],
            'mood':'normal','created_at':now,'last_fed':now,'last_played':now,'last_slept':now,
            'level':1,'xp':0,'total_interactions':0,
            'feed_count':0,'play_count':0,'sleep_count':0,'achievements':[]}

def update_state_over_time(state):
    now = datetime.now()
    for key, decay, rate in [('last_fed',4,5),('last_played',2,3),('last_slept',6,4)]:
        hours = (now - datetime.fromisoformat(state[key])).total_seconds() / 3600
        if hours > decay:
            stat = {'last_fed':'HUNGER','last_played':'HAPPY','last_slept':'ENERGY'}[key]
            state['stats'][stat] = max(0, state['stats'][stat] - int(hours * rate))
    h, e, p = state['stats']['HUNGER'], state['stats']['ENERGY'], state['stats']['HAPPY']
    state['mood'] = 'hungry' if h<20 else 'sleepy' if e<20 else 'excited' if p>80 else 'happy' if p>50 else 'normal'
    return state

# ═══════════════════════════════════════════════════════════════════════════════
# Windows 数据目录与持久化（适配 Windows 路径）
# ═══════════════════════════════════════════════════════════════════════════════

DATA_DIR = Path(os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))) / 'ascii-pet'

def get_state_path(uid):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f'{hash_string(uid) & 0xFFFFFFFF:08x}.json'

def load_pets(uid):
    p = get_state_path(uid)
    if not p.exists(): return None
    data = json.load(open(p, encoding='utf-8'))
    if isinstance(data, list): return {'pets': data, 'current': 0}
    if 'pets' not in data: return {'pets': [data], 'current': 0}
    return data

def save_pets(uid, data):
    json.dump(data, open(get_state_path(uid), 'w', encoding='utf-8'), indent=2)

def load_state(uid):
    data = load_pets(uid)
    if data is None: return None, None, 0
    idx = data.get('current', 0)
    if idx >= len(data['pets']): idx = 0
    return data['pets'][idx], data, idx

def save_state(uid, state, pets_data, idx):
    pets_data['pets'][idx] = state
    save_pets(uid, pets_data)

# ═══════════════════════════════════════════════════════════════════════════════
# Win32 剪贴板导出
# ═══════════════════════════════════════════════════════════════════════════════

def export_to_clipboard(text):
    """使用 Win32 API 将文本复制到剪贴板"""
    CF_UNICODETEXT = 13
    kernel32 = windll.kernel32
    user32 = windll.user32
    if not user32.OpenClipboard(0): return False
    user32.EmptyClipboard()
    data = text.encode('utf-16-le') + b'\x00\x00'
    h = kernel32.GlobalAlloc(0x0042, len(data))  # GMEM_MOVEABLE | GMEM_ZEROINIT
    p = kernel32.GlobalLock(h)
    memmove(p, data, len(data))
    kernel32.GlobalUnlock(h)
    user32.SetClipboardData(CF_UNICODETEXT, h)
    user32.CloseClipboard()
    return True

def export_pet(state, bones, frame_idx):
    """导出宠物信息到剪贴板"""
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
    text = '\n'.join(lines)
    if export_to_clipboard(text):
        return 'Copied to clipboard!'
    return 'Failed to copy'

# ═══════════════════════════════════════════════════════════════════════════════
# 颜色映射（替换 ANSI 转义码为 RGB）
# ═══════════════════════════════════════════════════════════════════════════════

RARITY_RGB = {
    'common':    (128, 128, 128),
    'uncommon':  (0, 200, 0),
    'rare':      (0, 200, 200),
    'epic':      (200, 0, 200),
    'legendary': (255, 215, 0),
}

MOOD_RGB = {
    'happy':   (255, 215, 0),
    'normal':  (200, 200, 200),
    'sleepy':  (128, 128, 128),
    'hungry':  (255, 80, 80),
    'excited': (200, 0, 200),
}

COLOR_DIM   = (128, 128, 128)
COLOR_MSG   = (255, 215, 0)
COLOR_WHITE = (200, 200, 200)
COLOR_BAR_FILL = (0, 200, 0)
COLOR_BAR_EMPTY = (80, 80, 80)
COLOR_HOVER_BG = (15, 15, 45)  # 悬停时的背景色（配合 LWA_ALPHA 半透明）

def rgb_to_colorref(r, g, b):
    """RGB 转 Win32 COLORREF (0x00BBGGRR)"""
    return (b << 16) | (g << 8) | r

# ═══════════════════════════════════════════════════════════════════════════════
# 渲染函数 — 返回 [(text, (R,G,B)), ...] 列表
# ═══════════════════════════════════════════════════════════════════════════════

def stat_bar_text(value, width=15):
    """返回 (filled_text, empty_text, value_str) 用于分段绘制"""
    filled = round((value / 100) * width)
    return '█' * filled, '░' * (width - filled), str(value)

def render_compact_lines(bones, frame_idx, state):
    """紧凑模式渲染"""
    lines = render_frame(bones, frame_idx, state.get('mood','normal'))
    result = []
    for l in lines:
        result.append((l, COLOR_WHITE))
    return result

def render_expanded_lines(state, bones, frame_idx, show_help):
    """展开模式渲染"""
    color = RARITY_RGB[state['rarity']]
    stars = RARITY_STARS[state['rarity']]
    shiny_str = ' SHINY' if state['shiny'] else ''
    mood = MOODS[state['mood']]
    mood_color = MOOD_RGB[state['mood']]
    frame = render_frame(bones, frame_idx, state.get('mood','normal'))

    lines = []
    # 名字和稀有度
    lines.append((f'{state["name"]} {stars}{shiny_str}', color))
    # 物种·稀有度 心情
    lines.append((f'{state["species"]}·{state["rarity"]}', COLOR_DIM))
    lines[-1] = (f'{state["species"]}·{state["rarity"]} [{mood["emoji"]}]', mood_color)
    # 等级
    lines.append((f'Lv.{state["level"]} XP:{state["xp"]}/{state["level"]*100}', COLOR_DIM))
    # 进化标记
    if state.get('evolved'):
        lines.append(('★ Evolved', color))
    # 精灵图
    for row in frame:
        lines.append((f' {row}', COLOR_WHITE))
    # 表情
    lines.append((f'face:{render_face(bones)}', COLOR_DIM))
    # 属性条
    for s in STAT_NAMES:
        v = state['stats'][s]
        filled, empty, val = stat_bar_text(v, 15)
        # 属性名用灰色，填充用绿色，空白用深灰，数值用白色
        lines.append((f'{s[:4]}', COLOR_DIM, filled, COLOR_BAR_FILL, empty, COLOR_BAR_EMPTY, f' {val}', COLOR_WHITE))
    # 帮助
    if show_help:
        lines.append(('[f]feed [p]play [s]sleep [r]reset [b]prev [n]next [t]stats [a]achieve [e]export [Enter]compact [q]quit', COLOR_DIM))
    else:
        lines.append(('[h] [f] [p] [s]', COLOR_DIM))
    return lines

def render_info_lines(state, bones, frame_idx, pet_idx, pet_count):
    """信息面板渲染"""
    color = RARITY_RGB[state['rarity']]
    stars = RARITY_STARS[state['rarity']]
    shiny_str = ' SHINY' if state['shiny'] else ''
    frame = render_frame(bones, frame_idx, state.get('mood','normal'))

    lines = []
    lines.append((f'{state["name"]}{shiny_str} {stars}', color))
    evo = ' ★EVOLVED' if state.get('evolved') else ''
    lines.append((f'{state["species"]}·{state["rarity"]} Eye:{state["eye"]} Hat:{state["hat"]} Lv.{state["level"]}{evo}', COLOR_DIM))
    lines.append((f'Interactions:{state["total_interactions"]} Pet:{pet_idx+1}/{pet_count}', COLOR_DIM))
    for row in frame:
        lines.append((f' {row}', COLOR_WHITE))
    for s in STAT_NAMES:
        v = state['stats'][s]
        filled, empty, val = stat_bar_text(v, 15)
        lines.append((f'{s[:4]}', COLOR_DIM, filled, COLOR_BAR_FILL, empty, COLOR_BAR_EMPTY, f' {val}', COLOR_WHITE))
    lines.append(('[i]back [q]quit', COLOR_DIM))
    return lines

def render_stats_lines(state, bones, frame_idx, pet_idx, pet_count):
    """统计面板渲染"""
    color = RARITY_RGB[state['rarity']]
    frame = render_frame(bones, frame_idx, state.get('mood','normal'))

    created = datetime.fromisoformat(state['created_at'])
    days = (datetime.now() - created).days
    hours = (datetime.now() - created).total_seconds() / 3600

    lines = []
    lines.append((f'Stats for {state["name"]}', color))
    lines.append((f'Species: {state["species"]}  Pet: {pet_idx+1}/{pet_count}', COLOR_DIM))
    lines.append(('', COLOR_DIM))
    for row in frame:
        lines.append((f' {row}', COLOR_WHITE))
    lines.append(('', COLOR_DIM))
    lines.append(('--- Activity ---', COLOR_DIM))
    lines.append((f'  Days adopted:  {days}', COLOR_DIM))
    lines.append((f'  Hours online: {hours:.1f}', COLOR_DIM))
    lines.append((f'  Feed count:   {state.get("feed_count",0)}', COLOR_DIM))
    lines.append((f'  Play count:   {state.get("play_count",0)}', COLOR_DIM))
    lines.append((f'  Sleep count:  {state.get("sleep_count",0)}', COLOR_DIM))
    lines.append((f'  Total acts:   {state["total_interactions"]}', COLOR_DIM))
    lines.append(('', COLOR_DIM))
    lines.append(('--- Growth ---', COLOR_DIM))
    lines.append((f'  Level: {state["level"]}  XP: {state["xp"]}/{state["level"]*100}', COLOR_DIM))
    lines.append((f'  Rarity: {state["rarity"]}  Shiny: {"Yes" if state["shiny"] else "No"}', COLOR_DIM))
    lines.append(('', COLOR_DIM))
    lines.append(('[t]back [q]quit', COLOR_DIM))
    return lines

def render_achievements_lines(state, bones):
    """成就面板渲染"""
    color = RARITY_RGB[state['rarity']]
    unlocked = state.get('achievements', [])

    lines = []
    lines.append((f'Achievements for {state["name"]}', color))
    lines.append((f'{len(unlocked)}/{len(ACHIEVEMENTS)} unlocked', COLOR_DIM))
    lines.append(('', COLOR_DIM))
    for aid, ach in ACHIEVEMENTS.items():
        if aid in unlocked:
            lines.append((f'  {ach["icon"]} {ach["name"]}', color))
        else:
            lines.append(('  ??? Locked', COLOR_DIM))
    lines.append(('', COLOR_DIM))
    lines.append(('[a]back [q]quit', COLOR_DIM))
    return lines

# ═══════════════════════════════════════════════════════════════════════════════
# Win32 常量
# ═══════════════════════════════════════════════════════════════════════════════

WS_POPUP       = 0x80000000
WS_VISIBLE     = 0x10000000
WS_EX_TOPMOST  = 0x00000008
WS_EX_LAYERED  = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW  = 0x00040000
LWA_COLORKEY   = 0x00000001
LWA_ALPHA      = 0x00000002

WM_PAINT       = 0x000F
WM_TIMER       = 0x0113
WM_CHAR        = 0x0102
WM_KEYDOWN     = 0x0100
WM_DESTROY     = 0x0002
WM_NCHITTEST   = 0x0084
WM_ERASEBKGND  = 0x0014
WM_LBUTTONDOWN = 0x0201
WM_NCLBUTTONDOWN = 0x00A1
WM_MOUSEMOVE   = 0x0200
WM_MOUSELEAVE  = 0x02A3
WM_CONTEXTMENU = 0x007B
WM_COMMAND     = 0x0111
WM_RBUTTONDOWN = 0x0204

HTCAPTION      = 2
DT_LEFT        = 0x0000
DT_TOP         = 0x0000
TRANSPARENT    = 1

COLOR_WINDOW   = 5

# 右键菜单命令 ID
ID_FEED        = 1001
ID_PLAY        = 1002
ID_SLEEP       = 1003
ID_REGENERATE  = 1004
ID_PREV_PET    = 1005
ID_NEXT_PET    = 1006
ID_EXPORT      = 1007
ID_COMPACT     = 1008
ID_EXPANDED    = 1009
ID_INFO        = 1010
ID_STATS       = 1011
ID_ACHIEVE     = 1012
ID_QUIT        = 1013

MF_STRING     = 0x00000000
MF_SEPARATOR  = 0x00000800
MF_GRAYED     = 0x00000001
MF_CHECKED    = 0x00000008
TPM_RIGHTBUTTON = 0x0002
TPM_NONOTIFY   = 0x0080
TPM_RETURNCMD  = 0x0100

# ═══════════════════════════════════════════════════════════════════════════════
# Win32 窗口实现
# ═══════════════════════════════════════════════════════════════════════════════

FONT_SIZE = 14
CHAR_W = 9
CHAR_H = 18
PADDING = 8

# 各模式布局尺寸（字符数）
LAYOUT_SIZES = {
    'compact':      (18, 7),
    'expanded':     (38, 22),
    'info':         (44, 16),
    'stats':        (44, 20),
    'achievements': (44, 20),
}

user32 = windll.user32
kernel32 = windll.kernel32
gdi32 = windll.gdi32

# 手动定义 wintypes 中可能缺失的类型
if not hasattr(wintypes, 'LRESULT'):
    wintypes.LRESULT = ctypes.c_ssize_t
if not hasattr(wintypes, 'WPARAM'):
    wintypes.WPARAM = ctypes.c_ssize_t
if not hasattr(wintypes, 'LPARAM'):
    wintypes.LPARAM = ctypes.c_ssize_t
if not hasattr(wintypes, 'COLORREF'):
    wintypes.COLORREF = wintypes.DWORD
if not hasattr(wintypes, 'HGDIOBJ'):
    wintypes.HGDIOBJ = wintypes.HANDLE
if not hasattr(wintypes, 'HBITMAP'):
    wintypes.HBITMAP = wintypes.HANDLE
if not hasattr(wintypes, 'HFONT'):
    wintypes.HFONT = wintypes.HANDLE
if not hasattr(wintypes, 'HBRUSH'):
    wintypes.HBRUSH = wintypes.HANDLE

# ═══════════════════════════════════════════════════════════════════════════════
# Win32 结构体定义（必须在 argtypes 之前）
# ═══════════════════════════════════════════════════════════════════════════════

class RECT(ctypes.Structure):
    _fields_ = [
        ('left', c_long),
        ('top', c_long),
        ('right', c_long),
        ('bottom', c_long),
    ]

class SIZE(ctypes.Structure):
    _fields_ = [('cx', c_long), ('cy', c_long)]

class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ('hdc', wintypes.HDC),
        ('fErase', c_int),
        ('rcPaint_left', c_long),
        ('rcPaint_top', c_long),
        ('rcPaint_right', c_long),
        ('rcPaint_bottom', c_long),
        ('fRestore', c_int),
        ('fIncUpdate', c_int),
        ('rgbReserved', c_byte * 32),
    ]

class MSG(ctypes.Structure):
    _fields_ = [
        ('hwnd', wintypes.HWND),
        ('message', wintypes.UINT),
        ('wParam', wintypes.WPARAM),
        ('lParam', wintypes.LPARAM),
        ('time', wintypes.DWORD),
        ('pt_x', c_long),
        ('pt_y', c_long),
    ]

class LOGFONTW(ctypes.Structure):
    _fields_ = [
        ('lfHeight', c_long),
        ('lfWidth', c_long),
        ('lfEscapement', c_long),
        ('lfOrientation', c_long),
        ('lfWeight', c_long),
        ('lfItalic', c_byte),
        ('lfUnderline', c_byte),
        ('lfStrikeOut', c_byte),
        ('lfCharSet', c_byte),
        ('lfOutPrecision', c_byte),
        ('lfClipPrecision', c_byte),
        ('lfQuality', c_byte),
        ('lfPitchAndFamily', c_byte),
        ('lfFaceName', ctypes.c_wchar * 32),
    ]

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', c_uint),
        ('biWidth', c_long),
        ('biHeight', c_long),
        ('biPlanes', ctypes.c_ushort),
        ('biBitCount', ctypes.c_ushort),
        ('biCompression', c_uint),
        ('biSizeImage', c_uint),
        ('biXPelsPerMeter', c_long),
        ('biYPelsPerMeter', c_long),
        ('biClrUsed', c_uint),
        ('biClrImportant', c_uint),
    ]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ('bmiHeader', BITMAPINFOHEADER),
        ('bmiColors', c_uint * 1),
    ]

class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('hwndTrack', wintypes.HWND),
        ('dwHoverTime', wintypes.DWORD),
    ]

TME_LEAVE = 0x0002

# WNDPROC 回调类型（使用正确的 64 位类型）
WNDPROC = ctypes.CFUNCTYPE(wintypes.LRESULT, wintypes.HWND, wintypes.UINT,
                            wintypes.WPARAM, wintypes.LPARAM)

class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ('style', c_uint),
        ('lpfnWndProc', WNDPROC),
        ('cbClsExtra', c_int),
        ('cbWndExtra', c_int),
        ('hInstance', wintypes.HINSTANCE),
        ('hIcon', wintypes.HICON),
        ('hCursor', wintypes.HANDLE),
        ('hbrBackground', wintypes.HBRUSH),
        ('lpszMenuName', c_wchar_p),
        ('lpszClassName', c_wchar_p),
    ]

# ═══════════════════════════════════════════════════════════════════════════════
# Win32 API 函数签名（64 位兼容）
# ═══════════════════════════════════════════════════════════════════════════════

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_ssize_t, ctypes.c_ssize_t]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_ssize_t, ctypes.c_ssize_t]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]
user32.TrackMouseEvent.restype = wintypes.BOOL
user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), wintypes.HBRUSH]
user32.FillRect.restype = c_int
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.MoveWindow.argtypes = [wintypes.HWND, c_int, c_int, c_int, c_int, wintypes.BOOL]
user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT), wintypes.BOOL]
user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.BeginPaint.restype = wintypes.HDC
user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, c_int, c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
gdi32.SetBkMode.argtypes = [wintypes.HDC, c_int]
gdi32.TextOutW.argtypes = [wintypes.HDC, c_int, c_int, wintypes.LPCWSTR, c_int]
gdi32.TextOutW.restype = wintypes.BOOL
gdi32.GetTextExtentPoint32W.argtypes = [wintypes.HDC, wintypes.LPCWSTR, c_int, ctypes.POINTER(SIZE)]
gdi32.GetTextExtentPoint32W.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [wintypes.HDC, c_int, c_int, c_int, c_int, wintypes.HDC, c_int, c_int, wintypes.DWORD]
gdi32.CreateFontIndirectW.argtypes = [ctypes.POINTER(LOGFONTW)]
gdi32.CreateFontIndirectW.restype = wintypes.HFONT
user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_ssize_t, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.InsertMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT, ctypes.c_ssize_t, wintypes.LPCWSTR]
user32.InsertMenuW.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, c_int, c_int, c_int, wintypes.HWND, ctypes.POINTER(RECT)]
user32.TrackPopupMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL


class PetWindow:
    """Win32 浮动宠物窗口"""

    def __init__(self, uid, state, pets_data, pet_idx, bones):
        self.uid = uid
        self.state = state
        self.pets_data = pets_data
        self.pet_idx = pet_idx
        self.bones = bones

        # 运行时状态
        self.frame_idx = 0
        self.mode = 'compact'
        self.show_help = False
        self.message = None
        self.message_time = 0
        self.reminder_shown = False
        self.last_event_time = 0
        self.anim_end = 0
        self.anim_frames = []
        self.anim_idx = 0
        self.last_tick = time.time()
        self.hover = False  # 鼠标悬停状态
        self.tracking_mouse = False  # 是否已注册鼠标离开追踪

        # 窗口句柄
        self.hwnd = None
        self.hfont = None
        self.wndproc_callback = None  # 防止被 GC 回收

        # 当前窗口尺寸
        self.win_w = 0
        self.win_h = 0

    def calc_window_size(self, mode):
        """根据模式计算窗口像素尺寸"""
        cols, rows = LAYOUT_SIZES.get(mode, (38, 22))
        return cols * CHAR_W + PADDING * 2, rows * CHAR_H + PADDING * 2

    def resize_window(self, mode):
        """调整窗口大小和位置"""
        w, h = self.calc_window_size(mode)
        self.win_w = w
        self.win_h = h
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        x = sw - w - 20
        y = sh - h - 60
        user32.MoveWindow(self.hwnd, x, y, w, h, True)

    def create_window(self):
        """创建 Win32 浮动窗口"""
        hinstance = kernel32.GetModuleHandleW(None)

        # 保存回调引用，防止 GC
        self.wndproc_callback = WNDPROC(self.wnd_proc)

        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self.wndproc_callback
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinstance
        wc.hIcon = 0
        wc.hCursor = user32.LoadCursorW(0, 32512)  # IDC_ARROW
        wc.hbrBackground = (COLOR_WINDOW + 1)
        wc.lpszMenuName = None
        wc.lpszClassName = 'AsciiPetWin'

        if not user32.RegisterClassW(byref(wc)):
            # 类可能已注册，忽略错误
            pass

        # 创建窗口（WS_EX_LAYERED + LWA_COLORKEY 实现透明背景）
        ex_style = WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_APPWINDOW
        style = WS_POPUP | WS_VISIBLE

        w, h = self.calc_window_size(self.mode)
        self.win_w = w
        self.win_h = h
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        x = sw - w - 20
        y = sh - h - 60

        self.hwnd = user32.CreateWindowExW(
            ex_style,          # dwExStyle
            'AsciiPetWin',     # lpClassName
            'ASCII Pet',       # lpWindowName
            style,             # dwStyle
            x, y, w, h,       # x, y, width, height
            0,                 # hWndParent
            0,                 # hMenu
            hinstance,         # hInstance
            None               # lpParam
        )

        if not self.hwnd:
            raise RuntimeError(f'CreateWindowExW 失败: {kernel32.GetLastError()}')

        # 设置透明色键（纯黑 RGB(0,0,0) 为透明）
        user32.SetLayeredWindowAttributes(self.hwnd, rgb_to_colorref(0, 0, 0), 0, LWA_COLORKEY)

        # 创建字体
        lf = LOGFONTW()
        lf.lfHeight = -FONT_SIZE  # 负值表示字符高度
        lf.lfWidth = 0
        lf.lfEscapement = 0
        lf.lfOrientation = 0
        lf.lfWeight = 400  # FW_NORMAL
        lf.lfItalic = 0
        lf.lfUnderline = 0
        lf.lfStrikeOut = 0
        lf.lfCharSet = 1   # DEFAULT_CHARSET
        lf.lfOutPrecision = 0
        lf.lfClipPrecision = 0
        lf.lfQuality = 1   # CLEARTYPE_QUALITY
        lf.lfPitchAndFamily = 0x31  # FIXED_PITCH | FF_MODERN
        lf.lfFaceName = 'Consolas'

        self.hfont = gdi32.CreateFontIndirectW(byref(lf))

        # 设置定时器（500ms）
        user32.SetTimer(self.hwnd, 1, 500, None)

        # 显示窗口并设置焦点
        user32.ShowWindow(self.hwnd, 5)  # SW_SHOW
        user32.SetForegroundWindow(self.hwnd)
        user32.SetFocus(self.hwnd)

    def wnd_proc(self, hwnd, msg, wparam, lparam):
        """窗口过程"""
        if msg == WM_PAINT:
            self.on_paint(hwnd)
            return 0
        elif msg == WM_TIMER:
            self.on_timer()
            return 0
        elif msg == WM_CHAR:
            self.on_char(wparam)
            return 0
        elif msg == WM_NCHITTEST:
            return 1  # HTCLIENT — 允许窗口获得键盘焦点
        elif msg == WM_LBUTTONDOWN:
            # 左键按下时发起拖拽：释放捕获，发送 NC 鼠标按下消息
            user32.ReleaseCapture()
            user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)
            return 0
        elif msg == WM_RBUTTONDOWN:
            self.show_context_menu(lparam)
            return 0
        elif msg == WM_COMMAND:
            self.on_command(wparam)
            return 0
        elif msg == WM_MOUSEMOVE:
            if not self.tracking_mouse:
                # 注册鼠标离开追踪
                tme = TRACKMOUSEEVENT()
                tme.cbSize = sizeof(TRACKMOUSEEVENT)
                tme.dwFlags = TME_LEAVE
                tme.hwndTrack = hwnd
                tme.dwHoverTime = 0
                user32.TrackMouseEvent(byref(tme))
                self.tracking_mouse = True
            if not self.hover:
                self.hover = True
                # 悬停时：色键透明 + 整体半透明，背景可见
                user32.SetLayeredWindowAttributes(hwnd, rgb_to_colorref(0, 0, 0), 180, LWA_COLORKEY | LWA_ALPHA)
                user32.InvalidateRect(hwnd, None, False)
            return 0
        elif msg == WM_MOUSELEAVE:
            self.tracking_mouse = False
            if self.hover:
                self.hover = False
                # 离开时：仅色键透明，背景纯黑=全透明
                user32.SetLayeredWindowAttributes(hwnd, rgb_to_colorref(0, 0, 0), 255, LWA_COLORKEY)
                user32.InvalidateRect(hwnd, None, False)
            return 0
        elif msg == WM_ERASEBKGND:
            # 根据悬停状态选择背景色
            hdc = int(wparam) & 0xFFFFFFFFFFFFFFFF
            rect = RECT()
            user32.GetClientRect(hwnd, byref(rect))
            bg_color = COLOR_HOVER_BG if self.hover else (0, 0, 0)
            brush = gdi32.CreateSolidBrush(rgb_to_colorref(*bg_color))
            user32.FillRect(hdc, byref(rect), brush)
            gdi32.DeleteObject(brush)
            return 1
        elif msg == WM_DESTROY:
            user32.KillTimer(hwnd, 1)
            if self.hfont:
                gdi32.DeleteObject(self.hfont)
            user32.PostQuitMessage(0)
            return 0
        # DefWindowProcW 不设 argtypes，让 ctypes 自动转换
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def on_timer(self):
        """定时器回调：更新动画帧和状态"""
        now = time.time()
        self.frame_idx += 1
        self.state = update_state_over_time(self.state)
        save_state(self.uid, self.state, self.pets_data, self.pet_idx)
        self.last_tick = now

        # 检查低属性提醒
        stats = self.state['stats']
        if stats['HUNGER'] < 10 and not self.reminder_shown:
            self.message = 'Your pet is starving!'; self.message_time = now; self.reminder_shown = True
        elif stats['ENERGY'] < 10 and not self.reminder_shown:
            self.message = 'Your pet is exhausted!'; self.message_time = now; self.reminder_shown = True
        elif stats['HAPPY'] < 10 and not self.reminder_shown:
            self.message = 'Your pet is lonely!'; self.message_time = now; self.reminder_shown = True
        if stats['HUNGER'] >= 10 and stats['ENERGY'] >= 10 and stats['HAPPY'] >= 10:
            self.reminder_shown = False

        # 随机事件
        if now - self.last_event_time > 60 and random.random() < 0.01:
            evt = random.choice(RANDOM_EVENTS)
            self.message = evt[1]; self.message_time = now; self.last_event_time = now
            for k, v in evt[2].items():
                if k == 'xp': self.state['xp'] += v; check_level_up(self.state)
                elif k in self.state['stats']: self.state['stats'][k] = min(100, self.state['stats'][k] + v)

        # 触发重绘
        user32.InvalidateRect(self.hwnd, None, False)

    def show_context_menu(self, lparam):
        """显示右键菜单"""
        # 获取鼠标屏幕坐标
        class POINT(ctypes.Structure):
            _fields_ = [('x', c_long), ('y', c_long)]
        pt = POINT()
        user32.GetCursorPos(byref(pt))
        x, y = pt.x, pt.y

        hmenu = user32.CreatePopupMenu()

        # 动作菜单
        is_compact = self.mode == 'compact'
        user32.AppendMenuW(hmenu, MF_STRING | (MF_GRAYED if is_compact else 0), ID_FEED, '喂食 (F)')
        user32.AppendMenuW(hmenu, MF_STRING | (MF_GRAYED if is_compact else 0), ID_PLAY, '玩耍 (P)')
        user32.AppendMenuW(hmenu, MF_STRING | (MF_GRAYED if is_compact else 0), ID_SLEEP, '睡觉 (S)')
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING | (MF_GRAYED if is_compact else 0), ID_REGENERATE, '重新生成 (R)')
        user32.AppendMenuW(hmenu, MF_STRING | (MF_GRAYED if is_compact else 0), ID_EXPORT, '导出到剪贴板 (E)')
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)

        # 宠物切换
        user32.AppendMenuW(hmenu, MF_STRING, ID_PREV_PET, '上一个宠物 (B)')
        user32.AppendMenuW(hmenu, MF_STRING, ID_NEXT_PET, '下一个宠物 (N)')
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)

        # 视图模式
        user32.AppendMenuW(hmenu, MF_STRING | (MF_CHECKED if self.mode == 'compact' else 0), ID_COMPACT, '紧凑模式')
        user32.AppendMenuW(hmenu, MF_STRING | (MF_CHECKED if self.mode == 'expanded' else 0), ID_EXPANDED, '展开模式')
        user32.AppendMenuW(hmenu, MF_STRING | (MF_CHECKED if self.mode == 'info' else 0), ID_INFO, '信息面板 (I)')
        user32.AppendMenuW(hmenu, MF_STRING | (MF_CHECKED if self.mode == 'stats' else 0), ID_STATS, '属性面板 (T)')
        user32.AppendMenuW(hmenu, MF_STRING | (MF_CHECKED if self.mode == 'achievements' else 0), ID_ACHIEVE, '成就面板 (A)')
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, ID_QUIT, '退出 (Q)')

        # 显示菜单并获取选择
        cmd = user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                                     x, y, 0, self.hwnd, None)
        user32.DestroyMenu(hmenu)

        # 处理菜单选择
        if cmd:
            self.execute_menu_command(cmd)

    def execute_menu_command(self, cmd):
        """执行菜单命令"""
        now = time.time()
        if cmd == ID_FEED and self.mode != 'compact':
            msg, anim_type = feed_pet(self.state)
            self.message = msg; self.message_time = now
            if anim_type: self.anim_end = now + 1.5; self.anim_frames = ANIMATIONS[anim_type]
            new_ach = check_achievements(self.state, self.pets_data)
            if new_ach: self.message = f'Achievement: {new_ach[0]}!'; self.message_time = now
            save_state(self.uid, self.state, self.pets_data, self.pet_idx)
        elif cmd == ID_PLAY and self.mode != 'compact':
            msg, anim_type = play_pet(self.state)
            self.message = msg; self.message_time = now
            if anim_type: self.anim_end = now + 1.5; self.anim_frames = ANIMATIONS[anim_type]
            new_ach = check_achievements(self.state, self.pets_data)
            if new_ach: self.message = f'Achievement: {new_ach[0]}!'; self.message_time = now
            save_state(self.uid, self.state, self.pets_data, self.pet_idx)
        elif cmd == ID_SLEEP and self.mode != 'compact':
            msg, anim_type = sleep_pet(self.state)
            self.message = msg; self.message_time = now
            if anim_type: self.anim_end = now + 1.5; self.anim_frames = ANIMATIONS[anim_type]
            new_ach = check_achievements(self.state, self.pets_data)
            if new_ach: self.message = f'Achievement: {new_ach[0]}!'; self.message_time = now
            save_state(self.uid, self.state, self.pets_data, self.pet_idx)
        elif cmd == ID_REGENERATE and self.mode != 'compact':
            self.bones = generate_companion(self.uid); name = generate_name(self.uid)
            self.state = init_state(self.uid, self.bones, name)
            self.pets_data['pets'][self.pet_idx] = self.state; save_pets(self.uid, self.pets_data)
            self.message = 'Regenerated!'; self.message_time = now
        elif cmd == ID_EXPORT and self.mode != 'compact':
            self.message = export_pet(self.state, self.bones, self.frame_idx)
            self.message_time = now
        elif cmd == ID_PREV_PET:
            if len(self.pets_data['pets']) > 1:
                self.pets_data['pets'][self.pet_idx] = self.state
                self.pet_idx = (self.pet_idx - 1) % len(self.pets_data['pets'])
                self.state = self.pets_data['pets'][self.pet_idx]
                self.bones = {k: self.state[k] for k in ('species','eye','hat','shiny','rarity')}
                self.pets_data['current'] = self.pet_idx; save_pets(self.uid, self.pets_data)
                new_ach = check_achievements(self.state, self.pets_data)
                self.message = f'Switched to {self.state["name"]}'
                if new_ach: self.message = f'Achievement: {new_ach[0]}!'
                self.message_time = now
        elif cmd == ID_NEXT_PET:
            self.pets_data['pets'][self.pet_idx] = self.state
            if self.pet_idx < len(self.pets_data['pets']) - 1:
                self.pet_idx += 1
            else:
                new_state = init_state(self.uid, generate_companion(self.uid), generate_name(self.uid))
                self.pets_data['pets'].append(new_state)
                self.pet_idx = len(self.pets_data['pets']) - 1
            self.state = self.pets_data['pets'][self.pet_idx]
            self.bones = {k: self.state[k] for k in ('species','eye','hat','shiny','rarity')}
            self.pets_data['current'] = self.pet_idx; save_pets(self.uid, self.pets_data)
            new_ach = check_achievements(self.state, self.pets_data)
            self.message = f'Switched to {self.state["name"]}'
            if new_ach: self.message = f'Achievement: {new_ach[0]}!'
            self.message_time = now
        elif cmd == ID_COMPACT:
            self.mode = 'compact'; self.show_help = False; self.resize_window(self.mode)
        elif cmd == ID_EXPANDED:
            self.mode = 'expanded'; self.show_help = False; self.resize_window(self.mode)
        elif cmd == ID_INFO:
            self.mode = 'info'; self.resize_window(self.mode)
        elif cmd == ID_STATS:
            self.mode = 'stats'; self.resize_window(self.mode)
        elif cmd == ID_ACHIEVE:
            self.mode = 'achievements'; self.resize_window(self.mode)
        elif cmd == ID_QUIT:
            user32.DestroyWindow(self.hwnd)
            return
        user32.InvalidateRect(self.hwnd, None, False)

    def on_command(self, wparam):
        """WM_COMMAND 处理"""
        pass

    def on_char(self, wparam):
        """键盘输入处理"""
        ch = chr(wparam)
        now = time.time()

        if ch in ('\r', '\n'):
            # 切换紧凑/展开
            if self.mode == 'compact':
                self.mode = 'expanded'; self.show_help = False
            elif self.mode == 'expanded':
                self.mode = 'compact'; self.show_help = False
            elif self.mode == 'info':
                self.mode = 'expanded'; self.show_help = False
            else:
                self.mode = 'compact'; self.show_help = False
            self.resize_window(self.mode)

        elif ch == 'h':
            if self.mode == 'compact':
                self.mode = 'expanded'; self.show_help = True
            else:
                self.show_help = not self.show_help
            self.resize_window(self.mode)

        elif ch == 'c':
            if self.mode != 'compact':
                self.mode = 'compact'; self.show_help = False
                self.resize_window(self.mode)

        elif ch == 'b':
            # 上一个宠物
            if len(self.pets_data['pets']) > 1:
                self.pets_data['pets'][self.pet_idx] = self.state
                self.pet_idx = (self.pet_idx - 1) % len(self.pets_data['pets'])
                self.state = self.pets_data['pets'][self.pet_idx]
                self.bones = {k: self.state[k] for k in ('species','eye','hat','shiny','rarity')}
                self.pets_data['current'] = self.pet_idx; save_pets(self.uid, self.pets_data)
                new_ach = check_achievements(self.state, self.pets_data)
                self.message = f'Switched to {self.state["name"]}'
                if new_ach: self.message = f'Achievement: {new_ach[0]}!'
                self.message_time = now

        elif ch == 'n':
            # 下一个宠物
            self.pets_data['pets'][self.pet_idx] = self.state
            if self.pet_idx < len(self.pets_data['pets']) - 1:
                self.pet_idx += 1
            else:
                new_state = init_state(self.uid, generate_companion(self.uid), generate_name(self.uid))
                self.pets_data['pets'].append(new_state)
                self.pet_idx = len(self.pets_data['pets']) - 1
            self.state = self.pets_data['pets'][self.pet_idx]
            self.bones = {k: self.state[k] for k in ('species','eye','hat','shiny','rarity')}
            self.pets_data['current'] = self.pet_idx; save_pets(self.uid, self.pets_data)
            new_ach = check_achievements(self.state, self.pets_data)
            self.message = f'Switched to {self.state["name"]}'
            if new_ach: self.message = f'Achievement: {new_ach[0]}!'
            self.message_time = now

        elif ch == 'i':
            if self.mode == 'info':
                self.mode = 'expanded'
            elif self.mode == 'expanded':
                self.mode = 'info'
            else:
                self.mode = 'info'
            self.resize_window(self.mode)

        elif ch == 't':
            if self.mode == 'stats':
                self.mode = 'expanded'
            elif self.mode in ('expanded', 'info'):
                self.mode = 'stats'
            else:
                self.mode = 'stats'
            self.resize_window(self.mode)

        elif ch == 'a':
            if self.mode == 'achievements':
                self.mode = 'expanded'
            elif self.mode in ('expanded', 'info', 'stats'):
                self.mode = 'achievements'
            else:
                self.mode = 'achievements'
            self.resize_window(self.mode)

        elif ch == 'e' and self.mode != 'compact':
            self.message = export_pet(self.state, self.bones, self.frame_idx)
            self.message_time = now

        elif ch == 'f' and self.mode != 'compact':
            msg, anim_type = feed_pet(self.state)
            self.message = msg; self.message_time = now
            if anim_type:
                self.anim_end = now + 1.5; self.anim_frames = ANIMATIONS[anim_type]; self.anim_idx = 0
            new_ach = check_achievements(self.state, self.pets_data)
            if new_ach: self.message = f'Achievement: {new_ach[0]}!'; self.message_time = now
            save_state(self.uid, self.state, self.pets_data, self.pet_idx)

        elif ch == 'p' and self.mode != 'compact':
            msg, anim_type = play_pet(self.state)
            self.message = msg; self.message_time = now
            if anim_type:
                self.anim_end = now + 1.5; self.anim_frames = ANIMATIONS[anim_type]; self.anim_idx = 0
            new_ach = check_achievements(self.state, self.pets_data)
            if new_ach: self.message = f'Achievement: {new_ach[0]}!'; self.message_time = now
            save_state(self.uid, self.state, self.pets_data, self.pet_idx)

        elif ch == 's' and self.mode != 'compact':
            msg, anim_type = sleep_pet(self.state)
            self.message = msg; self.message_time = now
            if anim_type:
                self.anim_end = now + 1.5; self.anim_frames = ANIMATIONS[anim_type]; self.anim_idx = 0
            new_ach = check_achievements(self.state, self.pets_data)
            if new_ach: self.message = f'Achievement: {new_ach[0]}!'; self.message_time = now
            save_state(self.uid, self.state, self.pets_data, self.pet_idx)

        elif ch == 'r' and self.mode != 'compact':
            self.bones = generate_companion(self.uid); name = generate_name(self.uid)
            self.state = init_state(self.uid, self.bones, name)
            self.pets_data['pets'][self.pet_idx] = self.state; save_pets(self.uid, self.pets_data)
            self.message = 'Regenerated!'; self.message_time = now

        elif ch == 'q':
            user32.DestroyWindow(self.hwnd)
            return

        # 触发重绘
        user32.InvalidateRect(self.hwnd, None, False)

    def get_render_lines(self):
        """获取当前模式的渲染行"""
        if self.mode == 'compact':
            lines = render_compact_lines(self.bones, self.frame_idx, self.state)
        elif self.mode == 'expanded':
            lines = render_expanded_lines(self.state, self.bones, self.frame_idx, self.show_help)
        elif self.mode == 'info':
            lines = render_info_lines(self.state, self.bones, self.frame_idx, self.pet_idx, len(self.pets_data['pets']))
        elif self.mode == 'stats':
            lines = render_stats_lines(self.state, self.bones, self.frame_idx, self.pet_idx, len(self.pets_data['pets']))
        elif self.mode == 'achievements':
            lines = render_achievements_lines(self.state, self.bones)
        else:
            lines = render_compact_lines(self.bones, self.frame_idx, self.state)

        # 添加消息行
        if self.message and time.time() - self.message_time < 2:
            lines.append((f'  {self.message}', COLOR_MSG))

        # 添加动画行
        if self.anim_end and time.time() < self.anim_end:
            self.anim_idx = int((time.time() * 6) % len(self.anim_frames))
            lines.append((f'  {self.anim_frames[self.anim_idx]}', COLOR_MSG))
        elif self.anim_end and time.time() >= self.anim_end:
            self.anim_end = 0

        return lines

    def on_paint(self, hwnd):
        """GDI 绘制"""
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, byref(ps))

        # 获取客户区尺寸
        rect = RECT()
        user32.GetClientRect(hwnd, byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top

        # 创建兼容 DC 和位图（双缓冲）
        memdc = gdi32.CreateCompatibleDC(hdc)
        hbitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
        old_bmp = gdi32.SelectObject(memdc, hbitmap)

        # 根据悬停状态选择背景色（纯黑=透明，深灰=半透明效果）
        bg_color = COLOR_HOVER_BG if self.hover else (0, 0, 0)
        bg_brush = gdi32.CreateSolidBrush(rgb_to_colorref(*bg_color))
        user32.FillRect(memdc, byref(rect), bg_brush)
        gdi32.DeleteObject(bg_brush)

        # 选择字体
        old_font = gdi32.SelectObject(memdc, self.hfont)

        # 设置透明背景模式
        gdi32.SetBkMode(memdc, TRANSPARENT)

        # 获取渲染行
        lines = self.get_render_lines()

        # 逐行绘制
        y = PADDING
        for line in lines:
            x = PADDING
            # 检查是否是多段行（属性条格式: text1, color1, text2, color2, ...）
            if len(line) >= 4 and len(line) % 2 == 0:
                # 多段绘制
                parts = []
                i = 0
                while i + 1 < len(line):
                    text = line[i]
                    color = line[i + 1]
                    parts.append((text, color))
                    i += 2
                for text, color in parts:
                    cr = rgb_to_colorref(*color)
                    gdi32.SetTextColor(memdc, cr)
                    # 计算文本宽度
                    sz = SIZE()
                    gdi32.GetTextExtentPoint32W(memdc, text, len(text), byref(sz))
                    gdi32.TextOutW(memdc, x, y, text, len(text))
                    x += sz.cx
            else:
                # 单段绘制
                text = line[0]
                color = line[1]
                cr = rgb_to_colorref(*color)
                gdi32.SetTextColor(memdc, cr)
                gdi32.TextOutW(memdc, x, y, text, len(text))
            y += CHAR_H

        # BitBlt 到屏幕
        gdi32.BitBlt(hdc, 0, 0, width, height, memdc, 0, 0, 0x00CC0020)  # SRCCOPY

        # 清理 GDI 对象
        gdi32.SelectObject(memdc, old_font)
        gdi32.SelectObject(memdc, old_bmp)
        gdi32.DeleteObject(hbitmap)
        gdi32.DeleteDC(memdc)

        user32.EndPaint(hwnd, byref(ps))

    def run(self):
        """运行消息循环"""
        self.create_window()

        # 消息循环
        msg = MSG()
        while user32.GetMessageW(byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))

# ═══════════════════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    uid = os.environ.get('USERNAME', 'anon')
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ('--help', '-h'):
            print('  ascii-pet — Windows 浮动桌面宠物\n\n  Usage:\n'
                  '    ascii-pet-win.py              Start pet\n'
                  '    ascii-pet-win.py [username]   Specific username\n'
                  '    ascii-pet-win.py --all        Show all species\n'
                  '    ascii-pet-win.py --help       Help\n\n'
                  '  Compact mode: just the pet\n'
                  '  Expanded mode: full stats (Enter to toggle)\n'
                  '  Commands: f feed, p play, s sleep, r reset, b prev, n next,\n'
                  '            t stats, a achieve, e export, h help, c compact, q quit')
            sys.exit(0)
        if arg == '--all':
            print('\n  All 18 species:\n')
            for sp in SPECIES:
                fb = {'species':sp,'eye':'·','hat':'none','shiny':False,'stats':{},'rarity':'common'}
                print(f'  {sp}  {render_face(fb)}')
                for row in render_sprite(fb, 0): print(f'  {row}')
                print()
            sys.exit(0)
        uid = arg

    # 加载或创建宠物状态
    state, pets_data, pet_idx = load_state(uid)
    if state is None:
        bones = generate_companion(uid); name = generate_name(uid)
        state = init_state(uid, bones, name)
        pets_data = {'pets': [state], 'current': 0}; pet_idx = 0
        save_pets(uid, pets_data)
    else:
        bones = {k: state[k] for k in ('species','eye','hat','shiny','rarity')}

    state = update_state_over_time(state)
    save_state(uid, state, pets_data, pet_idx)

    # 创建并运行窗口
    pet_win = PetWindow(uid, state, pets_data, pet_idx, bones)
    pet_win.run()


if __name__ == '__main__':
    main()
