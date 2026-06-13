#!/usr/bin/env python3
"""Platform-independent game logic for ASCII Desktop Pet."""

import os, json, time, random
from pathlib import Path
from datetime import datetime

# ─── Constants ────────────────────────────────────────────────────────────────

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
MAX_PETS = 3
MAX_DAILY_ADOPTIONS = 3

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

# ─── Actions ──────────────────────────────────────────────────────────────────

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

# ─── State management ─────────────────────────────────────────────────────────

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

# ─── Persistence ──────────────────────────────────────────────────────────────

def _default_data_dir():
    if os.name == 'nt':
        return Path(os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))) / 'ascii-pet'
    return Path.home() / '.local' / 'share' / 'ascii-pet'

def get_state_path(uid, data_dir=None):
    if data_dir is None: data_dir = _default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / f'{hash_string(uid) & 0xFFFFFFFF:08x}.json'

def load_pets(uid, data_dir=None):
    p = get_state_path(uid, data_dir)
    if not p.exists(): return None
    data = json.load(open(p, encoding='utf-8'))
    if isinstance(data, list): return {'pets': data, 'current': 0}
    if 'pets' not in data: return {'pets': [data], 'current': 0}
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

# ─── Game class ───────────────────────────────────────────────────────────────

class PetGame:
    """Platform-independent game state and logic."""

    def __init__(self, uid, data_dir=None):
        self.uid = uid
        self.data_dir = data_dir
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

        state, pets_data, pet_idx = load_state(uid, data_dir)
        if state is None:
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
        self.state = update_state_over_time(self.state)
        self.save()
        now = time.time()

        stats = self.state['stats']
        msg, msg_time = None, 0
        if stats['HUNGER'] < 10 and not self.reminder_shown:
            msg = 'Your pet is starving!'; msg_time = now; self.reminder_shown = True
        elif stats['ENERGY'] < 10 and not self.reminder_shown:
            msg = 'Your pet is exhausted!'; msg_time = now; self.reminder_shown = True
        elif stats['HAPPY'] < 10 and not self.reminder_shown:
            msg = 'Your pet is lonely!'; msg_time = now; self.reminder_shown = True
        if stats['HUNGER'] >= 10 and stats['ENERGY'] >= 10 and stats['HAPPY'] >= 10:
            self.reminder_shown = False

        if now - self.last_event_time > 60 and random.random() < 0.01:
            evt = random.choice(RANDOM_EVENTS)
            msg = evt[1]; msg_time = now; self.last_event_time = now
            for k, v in evt[2].items():
                if k == 'xp': self.state['xp'] += v; check_level_up(self.state)
                elif k in self.state['stats']: self.state['stats'][k] = min(100, self.state['stats'][k] + v)

        return msg, msg_time

    def handle_action(self, action):
        """Execute an action. Returns (message, anim_type)."""
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
        if new_ach: msg = f'Achievement: {new_ach[0]}!'
        return msg, anim

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
        msg = f'Switched to {self.state["name"]}'
        if new_ach: msg = f'Achievement: {new_ach[0]}!'
        return msg

    def adopt_pet(self):
        """Adopt a new pet. Returns message or None if entering release mode."""
        if len(self.pets_data['pets']) >= MAX_PETS:
            self.mode = 'release'
            self.pets_data['current'] = self.pet_idx
            save_pets(self.uid, self.pets_data, self.data_dir)
            return None
        if self.count_today_adoptions() >= MAX_DAILY_ADOPTIONS:
            return f'Daily limit reached ({MAX_DAILY_ADOPTIONS}/day). Try again tomorrow!'
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
        msg = f'Adopted {self.state["name"]}!'
        if new_ach: msg = f'Achievement: {new_ach[0]}!'
        return msg

    def release_pet(self, index):
        """Release a pet by index (0-based). Returns message."""
        if index < 0 or index >= len(self.pets_data['pets']):
            return 'Invalid pet!'
        if len(self.pets_data['pets']) <= 1:
            return 'Cannot release your last pet!'
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
        return f'Released {name}!'

    def get_release_list(self):
        """Return list of (index, name, species, rarity) for release mode."""
        result = []
        for i, s in enumerate(self.pets_data['pets']):
            result.append((i+1, s['name'], s['species'], s['rarity']))
        return result

    def handle_key(self, key):
        """Process a keypress. Returns (action_type, detail).

        action_type: 'quit', 'mode_change', 'action', 'pet_switch', 'export', 'none'
        detail: depends on action_type
        """
        now = time.time()
        if key == 'q':
            return 'quit', None

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

        if key == 'e' and self.mode != 'compact':
            return 'export', None

        if key == 'f':
            msg, anim = self.handle_action('feed')
            self.message = msg; self.message_time = now
            if anim: self.anim_end = now + 1.5; self.anim_frames = ANIMATIONS[anim]; self.anim_idx = 0
            return 'action', msg

        if key == 'p':
            msg, anim = self.handle_action('play')
            self.message = msg; self.message_time = now
            if anim: self.anim_end = now + 1.5; self.anim_frames = ANIMATIONS[anim]; self.anim_idx = 0
            return 'action', msg

        if key == 's':
            msg, anim = self.handle_action('sleep')
            self.message = msg; self.message_time = now
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

        return 'none', None
