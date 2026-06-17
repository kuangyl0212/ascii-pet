#!/usr/bin/env python3
"""Pytest tests for pet_core.py action functions (SubTasks 5.1-5.14).

Covers: feed_pet, play_pet, sleep_pet, check_level_up, check_achievements.
Uses pytest native style with fixtures and parametrize. No network access.
"""

import sys
import os
from datetime import datetime

import pytest

# Allow importing pet_core from the same directory as this test file.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pet_core
from pet_core import (
    feed_pet, play_pet, sleep_pet,
    check_level_up, check_achievements,
    STAT_NAMES, EYES, EVOLUTION_CHAIN, ACHIEVEMENTS,
)


@pytest.fixture
def make_state():
    """Return a factory that creates a fresh state dict for testing.

    Mirrors init_state's structure. Default stats are 50 across the board;
    defaults satisfy no achievements other than the ones a test explicitly
    opts into via overrides.
    """
    def _make(**overrides):
        now = datetime.now().isoformat()
        state = {
            'user_id': 'test_user',
            'name': 'TestPet',
            'species': 'blob',
            'rarity': 'common',
            'eye': '·',
            'hat': 'none',
            'shiny': False,
            'stats': {
                'HUNGER': 50, 'HAPPY': 50, 'ENERGY': 50,
                'WISDOM': 50, 'CHAOS': 50,
            },
            'mood': 'normal',
            'created_at': now,
            'last_fed': now,
            'last_played': now,
            'last_slept': now,
            'level': 1,
            'xp': 0,
            'total_interactions': 0,
            'feed_count': 0,
            'play_count': 0,
            'sleep_count': 0,
            'achievements': [],
            'critical_since': None,
            'is_dead': False,
            'last_feed': None,
            'last_play': None,
            'last_sleep': None,
            'pet_count_hour': 0,
            'pet_hour_start': None,
            # check_level_up sets these directly; pre-seed for clean assertions.
            'evolved': False,
            'eye_upgraded': False,
        }
        state.update(overrides)
        return state
    return _make


# ─── feed_pet (SubTasks 5.1-5.2) ──────────────────────────────────────────────

def test_feed_full_rejected(make_state):
    """5.1 Given HUNGER=100, When feed_pet, Then reject and state unchanged."""
    stats = {'HUNGER': 100, 'HAPPY': 50, 'ENERGY': 50, 'WISDOM': 50, 'CHAOS': 50}
    state = make_state(stats=dict(stats))
    before = {k: (dict(v) if isinstance(v, dict) else v) for k, v in state.items()}

    msg, anim = feed_pet(state)

    assert msg == 'Already full!'
    assert anim is None
    # State must be completely unchanged.
    assert state['stats'] == stats
    assert state['total_interactions'] == before['total_interactions']
    assert state['feed_count'] == before['feed_count']
    assert state['xp'] == before['xp']
    assert state['last_fed'] == before['last_fed']


def test_feed_normal(make_state):
    """5.2 Given HUNGER=50, When feed_pet, Then HUNGER+25, HAPPY+5, xp+10, counts+1."""
    state = make_state(stats={'HUNGER': 50, 'HAPPY': 50, 'ENERGY': 50,
                              'WISDOM': 50, 'CHAOS': 50})
    old_last_fed = state['last_fed']

    msg, anim = feed_pet(state)

    assert msg == '+25 Hunger, +5 Happy'
    assert anim == 'feed'
    assert state['stats']['HUNGER'] == 75
    assert state['stats']['HAPPY'] == 55
    assert state['xp'] == 10
    assert state['feed_count'] == 1
    assert state['total_interactions'] == 1
    assert state['last_fed'] != old_last_fed


# ─── play_pet (SubTasks 5.3-5.4) ──────────────────────────────────────────────

def test_play_tired(make_state):
    """5.3 Given ENERGY<10, When play_pet, Then reject with 'Too tired!'."""
    state = make_state(stats={'HUNGER': 50, 'HAPPY': 50, 'ENERGY': 5,
                              'WISDOM': 50, 'CHAOS': 50})
    old_xp = state['xp']
    old_play_count = state['play_count']

    msg, anim = play_pet(state)

    assert msg == 'Too tired!'
    assert anim is None
    # No state changes on rejection.
    assert state['xp'] == old_xp
    assert state['play_count'] == old_play_count


def test_play_normal(make_state):
    """5.4 Given normal stats, When play_pet, Then HAPPY+30, ENERGY-15, HUNGER-10, xp+15."""
    state = make_state(stats={'HUNGER': 50, 'HAPPY': 50, 'ENERGY': 50,
                              'WISDOM': 50, 'CHAOS': 50})

    msg, anim = play_pet(state)

    assert msg == '+30 Happy, -15 Energy'
    assert anim == 'play'
    assert state['stats']['HAPPY'] == 80
    assert state['stats']['ENERGY'] == 35
    assert state['stats']['HUNGER'] == 40
    assert state['xp'] == 15
    assert state['play_count'] == 1
    assert state['total_interactions'] == 1


# ─── sleep_pet (SubTasks 5.5-5.6) ─────────────────────────────────────────────

def test_sleep_full_energy(make_state):
    """5.5 Given ENERGY>=100, When sleep_pet, Then reject with 'Not sleepy!'."""
    state = make_state(stats={'HUNGER': 50, 'HAPPY': 50, 'ENERGY': 100,
                              'WISDOM': 50, 'CHAOS': 50})
    old_xp = state['xp']
    old_sleep_count = state['sleep_count']

    msg, anim = sleep_pet(state)

    assert msg == 'Not sleepy!'
    assert anim is None
    assert state['xp'] == old_xp
    assert state['sleep_count'] == old_sleep_count


def test_sleep_normal(make_state):
    """5.6 Given normal stats, When sleep_pet, Then ENERGY+40, HUNGER-5, xp+5."""
    state = make_state(stats={'HUNGER': 50, 'HAPPY': 50, 'ENERGY': 50,
                              'WISDOM': 50, 'CHAOS': 50})

    msg, anim = sleep_pet(state)

    assert msg == '+40 Energy'
    assert anim == 'sleep'
    assert state['stats']['ENERGY'] == 90
    assert state['stats']['HUNGER'] == 45
    assert state['xp'] == 5
    assert state['sleep_count'] == 1
    assert state['total_interactions'] == 1


# ─── check_level_up (SubTasks 5.7-5.11) ───────────────────────────────────────
# Note: xp_need = level * 100, so level N -> N+1 requires N*100 XP.
# Level 1->2 needs 100, 2->3 needs 200, 3->4 needs 300, etc.

def test_single_level_up(make_state):
    """5.7 Given level=1, xp=100, Then level=2, xp=0, WISDOM+5."""
    state = make_state(level=1, xp=100, species='octopus')

    result = check_level_up(state)

    assert result is None
    assert state['level'] == 2
    assert state['xp'] == 0
    assert state['stats']['WISDOM'] == 55  # 50 + 5


def test_continuous_level_up(make_state):
    """5.8 Given enough XP for two level-ups, Then level=3, xp=50, WISDOM+10.

    Level 1->2 needs 100, 2->3 needs 200 (total 300). Starting with
    xp=350 yields level=3 with 50 XP left. (The task description's
    250-100-100=50 assumed both tiers cost 100, but the code uses
    level*100, so 2->3 costs 200.)
    """
    state = make_state(level=1, xp=350, species='octopus')

    result = check_level_up(state)

    assert result is None
    assert state['level'] == 3
    assert state['xp'] == 50
    assert state['stats']['WISDOM'] == 60  # 50 + 5 + 5


def test_eye_upgrade_at_level_5(make_state):
    """5.9 Given level=4, xp=500 (reaches level 5), Then eye upgrades.

    Uses species='octopus' (not in EVOLUTION_CHAIN) so no evolution
    message intercepts the return value.
    """
    state = make_state(level=4, xp=500, eye='·', species='octopus')

    result = check_level_up(state)

    assert result is None
    assert state['level'] == 5
    assert state['xp'] == 100  # 500 - 4*100
    assert state['stats']['WISDOM'] == 55  # one level-up
    # Eye should advance from EYES[0] to EYES[1].
    assert state['eye'] != '·'
    assert state['eye'] == EYES[1]
    assert state['eye_upgraded'] is True


def test_evolved_flag_at_level_10(make_state):
    """5.10 Given level=9 reaching level 10, Then evolved=True.

    Uses species='octopus' (not in EVOLUTION_CHAIN) so check_level_up
    returns None instead of an evolution message.
    """
    state = make_state(level=9, xp=900, species='octopus')

    result = check_level_up(state)

    assert result is None
    assert state['level'] == 10
    assert state['evolved'] is True


@pytest.mark.parametrize(
    'species, start_level, xp, expected_species, expected_message',
    [
        ('blob',   4, 400, 'slime',   'Evolved into slime!'),
        ('duck',   4, 400, 'goose',   'Evolved into goose!'),
        ('cat',    4, 400, 'tiger',   'Evolved into tiger!'),
        ('dragon', 9, 900, 'wyvern',  'Evolved into wyvern!'),
        ('owl',    9, 900, 'phoenix', 'Evolved into phoenix!'),
    ],
    ids=['blob_to_slime', 'duck_to_goose', 'cat_to_tiger',
         'dragon_to_wyvern', 'owl_to_phoenix'],
)
def test_evolution(make_state, species, start_level, xp,
                   expected_species, expected_message):
    """5.11 Given a species reaching its evolution level, Then it evolves."""
    state = make_state(level=start_level, xp=xp, species=species)

    result = check_level_up(state)

    assert result == expected_message
    assert state['species'] == expected_species


def test_evolution_chain_first_match_wins(make_state):
    """5.11 The chain is scanned in order; the first applicable evolution
    wins and returns immediately. A blob that skips past level 5 and
    lands at level 15 still evolves into slime (not elemental), because
    'slime' is checked before 'elemental' and 'blob' != 'slime'.

    A second-stage evolution (slime -> elemental) is not reachable via
    check_level_up alone, since EVOLUTION_CHAIN has no 'slime' key.
    """
    state = make_state(level=14, xp=1400, species='blob')

    result = check_level_up(state)

    # First chain entry (slime, 5) matches; returns before elemental.
    assert result == 'Evolved into slime!'
    assert state['species'] == 'slime'
    # Confirm 'slime' is not itself an EVOLUTION_CHAIN key, so a second
    # evolution from slime cannot trigger via check_level_up.
    assert 'slime' not in EVOLUTION_CHAIN


# ─── check_achievements (SubTasks 5.12-5.14) ──────────────────────────────────

def test_first_feed_unlock(make_state):
    """5.12 Given feed_count=1, achievements=[], Then unlock 'First Meal'."""
    state = make_state(feed_count=1, achievements=[])
    pets_data = {'pets': [state]}

    unlocked = check_achievements(state, pets_data)

    assert unlocked == ['First Meal']
    assert 'first_feed' in state['achievements']


def test_no_duplicate_unlock(make_state):
    """5.13 Given 'first_feed' already unlocked, Then no duplicate."""
    state = make_state(feed_count=1, achievements=['first_feed'])
    pets_data = {'pets': [state]}

    unlocked = check_achievements(state, pets_data)

    assert unlocked == []
    # Still only one entry.
    assert state['achievements'].count('first_feed') == 1


def test_level_5_achievement(make_state):
    """5.14 Given level>=5, Then unlock 'Rising Star' (level_5)."""
    state = make_state(level=5, achievements=[])
    pets_data = {'pets': [state]}

    unlocked = check_achievements(state, pets_data)

    assert 'Rising Star' in unlocked
    assert 'level_5' in state['achievements']


def test_legendary_achievement(make_state):
    """5.14 Given rarity='legendary', Then unlock 'Lucky Find'."""
    state = make_state(rarity='legendary', achievements=[])
    pets_data = {'pets': [state]}

    unlocked = check_achievements(state, pets_data)

    assert 'Lucky Find' in unlocked
    assert 'legendary' in state['achievements']


def test_shiny_achievement(make_state):
    """5.14 Given shiny=True, Then unlock 'Shiny Hunter'."""
    state = make_state(shiny=True, achievements=[])
    pets_data = {'pets': [state]}

    unlocked = check_achievements(state, pets_data)

    assert 'Shiny Hunter' in unlocked
    assert 'shiny' in state['achievements']


def test_collector_5_achievement(make_state):
    """5.14 Given len(pets)>=5, Then unlock 'Pet Collector'."""
    state = make_state(achievements=[])
    # Five pets (the same object referenced 5 times is fine for the
    # len() check used by the collector_5 achievement).
    pets_data = {'pets': [state, state, state, state, state]}

    unlocked = check_achievements(state, pets_data)

    assert 'Pet Collector' in unlocked
    assert 'collector_5' in state['achievements']
