#!/usr/bin/env python3
"""TDD tests for Task 4: 治愈改为定量 +20 HP 恢复.

Covers:
  SubTask 4.1: test_heal_adds_20_hp      (hp=50 -> 70)
  SubTask 4.2: test_heal_caps_at_100     (hp=90 -> 100)
  SubTask 4.3: test_heal_full_hp_rejected (hp=100 rejected)
  SubTask 4.4: test_heal_cooldown_30min  (30-minute cooldown retained)

Run: python -m pytest test/test_heal.py -v

These tests assert the NEW behaviour: healing adds a fixed +20 HP
(capped at 100) instead of restoring HP to full.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame


def _make_game(hp, last_heal_time=0):
    """Build a minimal PetGame instance bypassing __init__.

    Only the attributes read by heal_pet are populated, so the test
    focuses purely on heal_pet's contract without touching persistence
    or LAN networking.
    """
    game = PetGame.__new__(PetGame)
    game.lan_enabled = True
    game.last_heal_time = last_heal_time
    game.state = {'hp': hp, 'is_dead': False}
    game.pets_data = {}
    game.message = None
    game.message_time = 0
    game.save = lambda: None
    return game


def test_heal_adds_20_hp():
    """Healing should add 20 HP, not full restore."""
    game = _make_game(hp=50, last_heal_time=0)
    result = game.heal_pet()
    assert result is True
    assert game.state['hp'] == 70


def test_heal_caps_at_100():
    """Healing should cap at 100 HP."""
    game = _make_game(hp=90, last_heal_time=0)
    result = game.heal_pet()
    assert result is True
    assert game.state['hp'] == 100


def test_heal_full_hp_rejected():
    """Healing should be rejected when HP is already full."""
    game = _make_game(hp=100, last_heal_time=0)
    result = game.heal_pet()
    assert result is False
    assert game.state['hp'] == 100


def test_heal_cooldown_30min():
    """Healing should respect 30-minute cooldown."""
    # last heal 10 minutes ago (within 30 min cooldown)
    game = _make_game(hp=50, last_heal_time=time.time() - 600)
    result = game.heal_pet()
    assert result is False
    assert game.state['hp'] == 50  # unchanged
