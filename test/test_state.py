#!/usr/bin/env python3
"""Pytest tests for pet_core.py state management functions.

Covers SubTasks 6.1-6.7:
  6.1 init_state field completeness
  6.2 init_state initial values
  6.3 update_state_over_time HUNGER decay
  6.4 update_state_over_time no decay below threshold
  6.5 update_state_over_time HAPPY/ENERGY decay
  6.6 update_state_over_time stats never go below 0
  6.7 update_state_over_time mood priority
"""

import sys
import os
from datetime import datetime, timedelta

# Allow importing pet_core.py from this directory
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pytest
from ascii_pet import core as pet_core


@pytest.fixture
def make_bones():
    """Factory returning a bones dict matching generate_companion() shape."""
    def _make():
        return {
            'species': 'cat',
            'eye': '@',
            'hat': 'none',
            'shiny': False,
            'rarity': 'common',
            'stats': {
                'HUNGER': 80,
                'HAPPY': 80,
                'ENERGY': 80,
                'WISDOM': 50,
                'CHAOS': 50,
            },
        }
    return _make


@pytest.fixture
def make_state(make_bones):
    """Factory building a fresh state via init_state, then applying overrides.

    Override keys may be top-level state keys, or 'stats' to merge into stats.
    Time fields should be isoformat strings.
    """
    def _make(**overrides):
        state = pet_core.init_state('test-uid', make_bones(), 'TestPet')
        for key, value in overrides.items():
            if key == 'stats':
                state['stats'].update(value)
            else:
                state[key] = value
        return state
    return _make


@pytest.fixture
def iso_hours_ago():
    """Factory returning an isoformat string for a datetime `hours` ago."""
    def _make(hours):
        return (datetime.now() - timedelta(hours=hours)).isoformat()
    return _make


# ─── SubTask 6.1: init_state field completeness ──────────────────────────────

def test_init_state_has_all_required_fields(make_bones):
    bones = make_bones()
    state = pet_core.init_state('test-uid', bones, 'TestPet')

    required_fields = [
        'user_id', 'name', 'species', 'rarity', 'eye', 'hat', 'shiny',
        'stats', 'mood', 'created_at', 'last_fed', 'last_played', 'last_slept',
        'level', 'xp', 'total_interactions', 'feed_count', 'play_count',
        'sleep_count', 'achievements', 'critical_since', 'is_dead',
        'last_feed', 'last_play', 'last_sleep', 'pet_count_hour', 'pet_hour_start',
    ]
    for field in required_fields:
        assert field in state, f'Missing required field: {field}'


def test_init_state_copies_bones_fields(make_bones):
    bones = make_bones()
    state = pet_core.init_state('my-uid', bones, 'Kitty')
    assert state['user_id'] == 'my-uid'
    assert state['name'] == 'Kitty'
    assert state['species'] == 'cat'
    assert state['rarity'] == 'common'
    assert state['eye'] == '@'
    assert state['hat'] == 'none'
    assert state['shiny'] is False
    assert state['stats'] == bones['stats']


# ─── SubTask 6.2: init_state initial values ──────────────────────────────────

def test_initial_values(make_bones):
    state = pet_core.init_state('test-uid', make_bones(), 'TestPet')
    assert state['level'] == 1
    assert state['xp'] == 0
    assert state['is_dead'] is False
    assert state['critical_since'] is None
    assert state['mood'] == 'normal'
    assert state['total_interactions'] == 0
    assert state['feed_count'] == 0
    assert state['play_count'] == 0
    assert state['sleep_count'] == 0
    assert state['achievements'] == []
    assert state['last_feed'] is None
    assert state['last_play'] is None
    assert state['last_sleep'] is None
    assert state['pet_count_hour'] == 0
    assert state['pet_hour_start'] is None


def test_initial_time_fields_are_isoformat(make_bones):
    state = pet_core.init_state('test-uid', make_bones(), 'TestPet')
    # created_at / last_fed / last_played / last_slept must parse as isoformat
    for key in ('created_at', 'last_fed', 'last_played', 'last_slept'):
        datetime.fromisoformat(state[key])


# ─── SubTask 6.3: HUNGER decay ───────────────────────────────────────────────
# Note: pet_core.update_state_over_time computes decay as int(hours * rate),
# NOT int((hours - threshold) * rate). For 4h elapsed with rate 8/h:
#   decay = int(4 * 8) = 32  ->  HUNGER = 80 - 32 = 48

def test_hunger_decays_after_threshold(make_state, iso_hours_ago):
    state = make_state()
    state['stats']['HUNGER'] = 80
    state['last_fed'] = iso_hours_ago(4)
    pet_core.update_state_over_time(state)
    assert state['stats']['HUNGER'] == 48


# ─── SubTask 6.4: no decay below threshold ───────────────────────────────────

def test_no_decay_below_threshold(make_state, iso_hours_ago):
    state = make_state()
    state['stats']['HUNGER'] = 80
    state['last_fed'] = iso_hours_ago(2)  # 2h < 3h threshold
    pet_core.update_state_over_time(state)
    assert state['stats']['HUNGER'] == 80


# ─── SubTask 6.5: HAPPY/ENERGY decay ─────────────────────────────────────────
# HAPPY:  threshold 1.5h, rate 5/h  ->  int(hours * 5)
# ENERGY: threshold 4h,   rate 6/h  ->  int(hours * 6)

def test_happy_decay(make_state, iso_hours_ago):
    state = make_state()
    state['stats']['HAPPY'] = 80
    state['last_played'] = iso_hours_ago(3)  # 3h > 1.5h
    pet_core.update_state_over_time(state)
    # decay = int(3 * 5) = 15  ->  HAPPY = 80 - 15 = 65
    assert state['stats']['HAPPY'] == 65


def test_energy_decay(make_state, iso_hours_ago):
    state = make_state()
    state['stats']['ENERGY'] = 80
    state['last_slept'] = iso_hours_ago(6)  # 6h > 4h
    pet_core.update_state_over_time(state)
    # decay = int(6 * 6) = 36  ->  ENERGY = 80 - 36 = 44
    assert state['stats']['ENERGY'] == 44


def test_happy_no_decay_below_threshold(make_state, iso_hours_ago):
    state = make_state()
    state['stats']['HAPPY'] = 80
    state['last_played'] = iso_hours_ago(1)  # 1h < 1.5h
    pet_core.update_state_over_time(state)
    assert state['stats']['HAPPY'] == 80


def test_energy_no_decay_below_threshold(make_state, iso_hours_ago):
    state = make_state()
    state['stats']['ENERGY'] = 80
    state['last_slept'] = iso_hours_ago(2)  # 2h < 4h
    pet_core.update_state_over_time(state)
    assert state['stats']['ENERGY'] == 80


# ─── SubTask 6.6: stats never go below 0 ─────────────────────────────────────
# For 10h elapsed: decay = int(10 * 8) = 80  ->  max(0, 5 - 80) = 0

def test_stat_clamped_to_zero(make_state, iso_hours_ago):
    state = make_state()
    state['stats']['HUNGER'] = 5
    state['last_fed'] = iso_hours_ago(10)
    pet_core.update_state_over_time(state)
    assert state['stats']['HUNGER'] == 0
    assert state['stats']['HUNGER'] >= 0


# ─── SubTask 6.7: mood priority ──────────────────────────────────────────────
# hungry (HUNGER<20) > sleepy (ENERGY<20) > excited (HAPPY>80)
# > happy (HAPPY>50) > normal.

@pytest.mark.parametrize('hunger, energy, happy, expected_mood', [
    # HUNGER=10 -> hungry, even though ENERGY is also low and HAPPY high
    (10, 10, 90, 'hungry'),
    # HUNGER=50 (ok), ENERGY=10 -> sleepy (HAPPY high but sleepy > excited)
    (50, 10, 90, 'sleepy'),
    # HUNGER=50, ENERGY=50, HAPPY=90 -> excited
    (50, 50, 90, 'excited'),
    # HUNGER=50, ENERGY=50, HAPPY=60 -> happy
    (50, 50, 60, 'happy'),
    # HUNGER=50, ENERGY=50, HAPPY=40 -> normal
    (50, 50, 40, 'normal'),
])
def test_mood_priority(make_state, hunger, energy, happy, expected_mood):
    # Build a state with given stats and all last_* set to now (no decay).
    state = make_state()
    state['stats']['HUNGER'] = hunger
    state['stats']['ENERGY'] = energy
    state['stats']['HAPPY'] = happy
    now_iso = datetime.now().isoformat()
    state['last_fed'] = now_iso
    state['last_played'] = now_iso
    state['last_slept'] = now_iso
    pet_core.update_state_over_time(state)
    assert state['mood'] == expected_mood
