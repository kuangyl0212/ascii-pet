"""Unified game event system.

Provides:
  - Event: frozen dataclass representing a single game event.
  - EventRegistry: in-memory registry of events keyed by event_id.
  - REGISTRY: module-level singleton EventRegistry (empty in Task 1;
    events are registered in Task 4).

Zero pip dependencies — stdlib only (dataclasses, random).

This module is intentionally side-effect free beyond constructing the
empty REGISTRY singleton. No events are registered here.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(frozen=True)
class Event:
    """A single game event.

    Fields:
        event_id:    Unique identifier (e.g. 'mood_boost', 'play_together').
        description: i18n key or literal description text.
        effects:     Stat deltas; keys are normalized to UPPERCASE STAT names
                     (HUNGER/HAPPY/ENERGY/WISDOM/CHAOS) in __post_init__.
        target:      'self' | 'both' | 'other' (LAN peer). Default 'self'.
        category:    'solo' | 'interaction' | 'visit' | 'weather'. Default 'solo'.
        metadata:    Optional special-effect hints, e.g.
                     {'item_drop': True}, {'xp': 3}, {'revive': True}.
    """

    event_id: str
    description: str
    effects: dict
    target: str = 'self'
    category: str = 'solo'
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Frozen dataclasses cannot assign attributes normally; use object.__setattr__.
        upper = {k.upper(): v for k, v in self.effects.items()}
        object.__setattr__(self, 'effects', upper)


class EventRegistry:
    """In-memory registry of Event objects, keyed by event_id."""

    def __init__(self) -> None:
        self._events: dict[str, Event] = {}

    def register(self, event: Event) -> None:
        """Register an Event. Raises ValueError on duplicate event_id."""
        if event.event_id in self._events:
            raise ValueError(f"Event already registered: {event.event_id!r}")
        self._events[event.event_id] = event

    def get(self, event_id: str) -> Optional[Event]:
        """Return the Event with the given id, or None if not found."""
        return self._events.get(event_id)

    def by_category(self, category: str) -> list[Event]:
        """Return all events whose category matches."""
        return [e for e in self._events.values() if e.category == category]

    def all(self) -> list[Event]:
        """Return all registered events as a list."""
        return list(self._events.values())

    def random(self, category: Optional[str] = None) -> Event:
        """Return a random event, optionally filtered by category.

        Raises IndexError if no events match.
        """
        pool = self.by_category(category) if category is not None else self.all()
        if not pool:
            raise IndexError(
                f"No events available"
                + (f" for category={category!r}" if category is not None else "")
            )
        return random.choice(pool)


# Module-level singleton. Task 1 leaves it empty; Task 4 registers events.
REGISTRY = EventRegistry()


# ---------------------------------------------------------------------------
# Builtin event registration (Task 4)
# ---------------------------------------------------------------------------
# All builtin events (RANDOM_EVENTS, PET_INTERACTIONS, VISIT_EVENTS) are
# registered into REGISTRY at import time. The original tuple/dict constants
# in core.py and protocol.py are then re-exposed as Event lists sourced from
# REGISTRY, so callers can keep using the same names but get Event objects.

# Stat keys that are allowed in Event.effects (everything else is metadata).
_STAT_KEYS = ('HUNGER', 'HAPPY', 'ENERGY', 'WISDOM', 'CHAOS')


def _register_builtin_events() -> None:
    """Build and register all builtin events into REGISTRY.

    Called once at import time. Idempotent in spirit: if events are already
    registered (e.g. re-import), this is a no-op for those ids.
    """
    # --- RANDOM_EVENTS (solo) ---
    # Original tuples: (id, msg, effects_dict) where effects_dict may contain
    # stat keys (UPPERCASE) plus special keys 'xp' (int) and 'item' (True).
    _random_event_specs = [
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
    for event_id, desc, raw_effects in _random_event_specs:
        effects = {k: v for k, v in raw_effects.items() if k in _STAT_KEYS}
        metadata: dict = {}
        if raw_effects.get('item'):
            metadata['item_drop'] = True
        if 'xp' in raw_effects:
            metadata['xp'] = raw_effects['xp']
        evt = Event(
            event_id=event_id,
            description=desc,
            effects=effects,
            target='self',
            category='solo',
            metadata=metadata,
        )
        if REGISTRY.get(event_id) is None:
            REGISTRY.register(evt)

    # --- PET_INTERACTIONS (interaction) ---
    # Original tuples: (id, msg, effects_dict, target) where target is
    # 'both' or 'current'. 'current' is migrated to 'self'.
    _interaction_specs = [
        ('play_together', ' played together!',  {'HAPPY': 5},  'both'),
        ('share_food',    ' shared a snack!',   {'HUNGER': 10}, 'current'),
        ('chat',          ' had a nice chat!',  {'WISDOM': 5},  'both'),
        ('race',          ' had a race!',       {'ENERGY': 10}, 'current'),
    ]
    for event_id, desc, effects, target in _interaction_specs:
        evt = Event(
            event_id=event_id,
            description=desc,
            effects=effects,
            target='both' if target == 'both' else 'self',
            category='interaction',
        )
        if REGISTRY.get(event_id) is None:
            REGISTRY.register(evt)

    # --- VISIT_EVENTS (visit) ---
    # Original dicts: {event_type, description, stat_effects} where
    # stat_effects uses LOWERCASE keys (Event constructor uppercases them).
    # event_ids that collide with interaction ids are prefixed with 'visit_'.
    _interaction_ids = {spec[0] for spec in _interaction_specs}
    _visit_event_specs = [
        ("play_together", "两只宠物一起玩耍，开心地追逐打闹！", {"happy": 15, "energy": -10}),
        ("share_food", "两只宠物分享了食物，都吃得很开心！", {"hunger": 15, "happy": 5}),
        ("race", "两只宠物进行了一场赛跑比赛，都消耗了体力！", {"energy": -15, "happy": 10}),
        ("chat", "两只宠物聊得很投机，心情都变好了！", {"happy": 10, "wisdom": 5}),
        ("nap_together", "两只宠物一起睡了个午觉，精力充沛！", {"energy": 20, "hunger": -5}),
    ]
    for event_type, desc, stat_effects in _visit_event_specs:
        # Prefix event_id to avoid collision with interaction event_ids.
        if event_type in _interaction_ids:
            event_id = f'visit_{event_type}'
        else:
            event_id = event_type
        evt = Event(
            event_id=event_id,
            description=desc,
            effects=stat_effects,  # Event.__post_init__ uppercases keys
            target='self',
            category='visit',
            metadata={'original_event_type': event_type},
        )
        if REGISTRY.get(event_id) is None:
            REGISTRY.register(evt)


# Register all builtin events at import time.
_register_builtin_events()


# ---------------------------------------------------------------------------
# apply_event: unified effect applicator (Task 2)
# ---------------------------------------------------------------------------

def apply_event(
    state: dict,
    event: Event,
    *,
    pets_data: dict | None = None,
    inventory_adder: Callable | None = None,
    rng: random.Random | None = None,
    stat_gate: bool = True,
    chaos_bump: bool = True,
) -> dict:
    """Apply an Event's effects to pet state(s) using unified rules.

    Args:
        state:            Current pet state dict. Must contain 'stats' and 'xp'.
        event:            The Event to apply.
        pets_data:        Multi-pet container {'pets': [...]} for target='both'/'other'.
        inventory_adder:  Zero-arg callable returning an item_id str or None.
        rng:              Injectable random source (reserved for future use;
                          item randomness is delegated to inventory_adder).
        stat_gate:        When True, positive effects are skipped if the stat
                          is already >= 80.
        chaos_bump:       When True, any negative effect bumps CHAOS by +3
                          (once per event, per pet).

    Returns:
        {'message': None, 'item_dropped': str|None, 'xp_gained': int}
        - message is always None (callers handle messaging).
        - item_dropped reflects the inventory_adder's return value.
        - xp_gained is the XP added to the *current* state only.
    """
    result: dict = {'message': None, 'item_dropped': None, 'xp_gained': 0}

    # 1. Resolve which pets receive stat effects based on target.
    target_pets = _resolve_target_pets(state, event.target, pets_data)

    # 2. Apply stat effects (stat-gate + chaos_bump) to each target pet.
    for pet in target_pets:
        _apply_stat_effects(pet, event, stat_gate=stat_gate, chaos_bump=chaos_bump)

    # 3. item_drop: only on current state, never duplicated per-pet.
    if event.metadata.get('item_drop') and inventory_adder is not None:
        result['item_dropped'] = inventory_adder()

    # 4. xp: only on current state, never duplicated per-pet.
    if 'xp' in event.metadata:
        xp_gain = event.metadata['xp']
        if isinstance(xp_gain, int):
            state['xp'] = state.get('xp', 0) + xp_gain
            result['xp_gained'] = xp_gain

    return result


def _resolve_target_pets(state: dict, target: str, pets_data: dict | None) -> list:
    """Return the list of pet states that should receive stat effects."""
    if target == 'both':
        if pets_data is None:
            return [state]
        pets = list(pets_data.get('pets', []))
        # Ensure the current state is included (it normally is).
        if state not in pets:
            pets.append(state)
        return pets
    if target == 'other':
        if pets_data is None:
            return []
        return [p for p in pets_data.get('pets', []) if p is not state]
    # Default: 'self' (also covers unknown target values).
    return [state]


def _apply_stat_effects(
    pet_state: dict, event: Event, *, stat_gate: bool, chaos_bump: bool
) -> None:
    """Apply stat deltas to a single pet state.

    Honors stat-gate (skip positive effects when stat >= 80) and chaos_bump
    (CHAOS +3 once when any negative effect exists). All values clamp to [0, 100].
    """
    stats = pet_state['stats']
    effects = event.effects

    # chaos_bump: if any effect on an existing stat is negative, bump CHAOS +3.
    # Applied before stat deltas so it matches the original core.py ordering.
    has_negative = any(v < 0 for k, v in effects.items() if k in stats)
    if chaos_bump and has_negative:
        stats['CHAOS'] = min(100, stats.get('CHAOS', 0) + 3)

    # Apply each stat delta with stat-gate and clamping.
    for stat, delta in effects.items():
        if stat not in stats:
            continue
        if stat_gate and delta > 0 and stats[stat] >= 80:
            continue
        stats[stat] = max(0, min(100, stats[stat] + delta))


# ---------------------------------------------------------------------------
# serialize_event / deserialize_event (Task 3)
# ---------------------------------------------------------------------------

def serialize_event(event: Event) -> dict:
    """Convert an Event to a JSON-serializable dict for LAN transit and saves.

    Returns a plain dict with all six Event fields. The effects and metadata
    dicts are copied so the serialized form is independent of the source Event
    (callers may freely mutate the returned dict or run it through json.dumps).
    """
    return {
        'event_id': event.event_id,
        'description': event.description,
        'effects': dict(event.effects),
        'target': event.target,
        'category': event.category,
        'metadata': dict(event.metadata),
    }


def deserialize_event(data: dict) -> Event:
    """Rebuild an Event from a dict produced by serialize_event (or json.loads).

    The Event constructor re-uppercases effects keys via __post_init__, so
    data arriving from external sources (e.g. lowercase keys from a peer
    running an older version) is normalized to the canonical UPPERCASE form.
    """
    return Event(
        event_id=data['event_id'],
        description=data['description'],
        effects=dict(data.get('effects', {})),
        target=data.get('target', 'self'),
        category=data.get('category', 'solo'),
        metadata=dict(data.get('metadata', {})),
    )
