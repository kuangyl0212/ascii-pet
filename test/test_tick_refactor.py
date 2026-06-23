#!/usr/bin/env python3
"""TDD tests for Task 5: refactor PetGame.tick() to use apply_event().

Two test strategies are used:
  1. Characterization tests (TestTickCharacterization): verify the observable
     behavior of tick()'s random-event branch is unchanged by the refactor.
     These PASS against the current inline implementation AND after the
     refactor to apply_event().
  2. Strict RED-GREEN test (TestTickUsesApplyEvent): asserts tick() calls
     apply_event() for the random-event branch. This FAILS against the current
     inline implementation (which does not call apply_event) and PASSES only
     after the refactor.

Ownership boundary: only PetGame.tick() random-event branch is in scope.
trigger_interaction(), _tick_visit_events(), _apply_visit_event_effects(), and
protocol.py are owned by other tasks and are NOT tested here.
"""
import os
import sys
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame, RANDOM_EVENTS, ITEMS
from ascii_pet.events import Event, apply_event


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-tick-refactor-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


def _find_event(event_id):
    """Find an event in RANDOM_EVENTS by id. Returns the Event or None."""
    for evt in RANDOM_EVENTS:
        if evt.event_id == event_id:
            return evt
    return None


@pytest.fixture
def game(tmp_path):
    """Provide a fresh PetGame with isolated temp dir and reset event timing."""
    uid = _uid()
    g = PetGame(uid, data_dir=tmp_path)
    # Bypass the 60s event cooldown so random events can fire immediately.
    g.last_event_time = 0
    # Reset last_tick_time to current time to avoid huge delta_hours decay.
    g.last_tick_time = time.time()
    return g


# ─── Characterization tests (pass before AND after refactor) ─────────────────


class TestTickCharacterization:
    """Verify tick() random-event behavior is unchanged by the refactor.

    These tests must pass against the current inline implementation AND
    against the refactored implementation that calls apply_event().
    """

    def test_tick_random_event_applies_stat_effect(self, game):
        """found_food event with HUNGER=60 should raise HUNGER to 65."""
        game.state['stats']['HUNGER'] = 60
        found_food = _find_event('found_food')
        assert found_food is not None, "found_food event must exist"
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=found_food):
            game.tick()
        assert game.state['stats']['HUNGER'] == 65, (
            "found_food should add 5 HUNGER (60 -> 65)"
        )
        assert game.last_event_time > 0, "event should have fired"

    def test_tick_stat_gate_blocks_positive_when_stat_above_80(self, game):
        """found_food with HUNGER=95 should NOT increase HUNGER (stat-gate)."""
        game.state['stats']['HUNGER'] = 95
        found_food = _find_event('found_food')
        assert found_food is not None
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=found_food):
            game.tick()
        assert game.state['stats']['HUNGER'] == 95, (
            "stat-gate should block positive effect when stat >= 80"
        )

    def test_tick_negative_event_increases_chaos(self, game):
        """stomach_ache (negative event) should bump CHAOS by +3."""
        game.state['stats']['CHAOS'] = 50
        game.state['stats']['HUNGER'] = 50
        stomach_ache = _find_event('stomach_ache')
        assert stomach_ache is not None
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=stomach_ache):
            game.tick()
        assert game.state['stats']['CHAOS'] == 53, (
            "negative event should bump CHAOS by 3 (50 -> 53)"
        )

    def test_tick_positive_event_does_not_increase_chaos(self, game):
        """mood_boost (positive event) should NOT bump CHAOS."""
        game.state['stats']['CHAOS'] = 50
        game.state['stats']['HAPPY'] = 50
        mood_boost = _find_event('mood_boost')
        assert mood_boost is not None
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=mood_boost):
            game.tick()
        assert game.state['stats']['CHAOS'] == 50, (
            "positive event should NOT bump CHAOS"
        )

    def test_tick_find_item_adds_to_inventory(self, game):
        """find_item event should add a random item to the inventory."""
        find_item_evt = _find_event('find_item')
        assert find_item_evt is not None
        initial_inv_total = sum(game.pets_data.get('inventory', {}).values())
        # random.choice is called twice: once for the event, once for the item.
        with patch('random.random', return_value=0.001), \
                patch('random.choice', side_effect=[find_item_evt, 'apple']):
            game.tick()
        new_inv_total = sum(game.pets_data.get('inventory', {}).values())
        assert new_inv_total > initial_inv_total, (
            "find_item event should grow the inventory"
        )

    def test_tick_find_coin_grants_xp(self, game):
        """find_coin event should grant xp (metadata.xp = 3)."""
        find_coin = _find_event('find_coin')
        assert find_coin is not None
        initial_xp = game.state['xp']
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=find_coin):
            game.tick()
        assert game.state['xp'] == initial_xp + 3, (
            "find_coin should grant 3 xp"
        )

    def test_tick_find_coin_checks_level_up(self, game):
        """find_coin xp gain should trigger level-up check.

        Set xp close to the level threshold so the xp gain causes a level up.
        Level 1 needs 100 xp to reach level 2.
        """
        find_coin = _find_event('find_coin')
        assert find_coin is not None
        game.state['level'] = 1
        game.state['xp'] = 98  # 98 + 3 = 101 >= 100 -> level up to 2, xp=1
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=find_coin):
            game.tick()
        assert game.state['level'] == 2, (
            "find_coin xp gain should trigger check_level_up (level 1 -> 2)"
        )
        assert game.state['xp'] == 1, (
            "after level up, xp should be 101 - 100 = 1"
        )

    def test_tick_chaos_capped_at_100_after_negative_event(self, game):
        """CHAOS should cap at 100 even when negative event bumps past it."""
        game.state['stats']['CHAOS'] = 99
        game.state['stats']['HUNGER'] = 50
        stomach_ache = _find_event('stomach_ache')
        assert stomach_ache is not None
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=stomach_ache):
            game.tick()
        assert game.state['stats']['CHAOS'] == 100, (
            "CHAOS should cap at 100 (99 + 3 = 102 -> 100)"
        )

    def test_tick_event_message_set_to_description(self, game):
        """tick() should return the event description as the message."""
        mood_boost = _find_event('mood_boost')
        assert mood_boost is not None
        game.state['stats']['HAPPY'] = 50
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=mood_boost):
            msg, msg_time = game.tick()
        assert msg is not None, "tick should return the event description"
        assert msg_time > 0

    def test_tick_find_item_message_shows_item_name(self, game):
        """find_item event should produce a 'Found a ...!' message."""
        find_item_evt = _find_event('find_item')
        assert find_item_evt is not None
        with patch('random.random', return_value=0.001), \
                patch('random.choice', side_effect=[find_item_evt, 'apple']):
            msg, msg_time = game.tick()
        assert msg is not None
        assert 'Found a' in msg, (
            f"find_item message should mention 'Found a', got: {msg!r}"
        )


# ─── Strict RED-GREEN test (fails before refactor, passes after) ─────────────


class TestTickUsesApplyEvent:
    """Verify tick() delegates to apply_event() for the random-event branch.

    These tests FAIL against the current inline implementation (RED) and
    PASS only after the refactor (GREEN).
    """

    def test_tick_calls_apply_event_for_random_event(self, game):
        """tick() should call apply_event() when a random event fires."""
        mood_boost = _find_event('mood_boost')
        assert mood_boost is not None
        # create=True allows patching an attribute that may not yet exist
        # in ascii_pet.core (before the refactor imports apply_event).
        # Configure return_value so the post-apply_event code doesn't crash.
        empty_result = {'message': None, 'item_dropped': None, 'xp_gained': 0}
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=mood_boost), \
                patch('ascii_pet.core.apply_event', create=True,
                      return_value=empty_result) as mock_apply:
            game.tick()
        assert mock_apply.called, (
            "tick() should call apply_event() for the random-event branch"
        )

    def test_tick_passes_event_to_apply_event(self, game):
        """tick() should pass the chosen Event to apply_event()."""
        mood_boost = _find_event('mood_boost')
        assert mood_boost is not None
        empty_result = {'message': None, 'item_dropped': None, 'xp_gained': 0}
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=mood_boost), \
                patch('ascii_pet.core.apply_event', create=True,
                      return_value=empty_result) as mock_apply:
            game.tick()
        assert mock_apply.called
        # The second positional arg (after self.state) should be the Event.
        call_args = mock_apply.call_args
        args, kwargs = call_args
        # apply_event(state, event, ...) — event is the 2nd positional arg.
        assert len(args) >= 2, (
            "apply_event should be called with at least (state, event)"
        )
        passed_event = args[1]
        assert isinstance(passed_event, Event), (
            "second arg to apply_event should be an Event instance"
        )
        assert passed_event.event_id == 'mood_boost', (
            "passed event should be the mood_boost event"
        )

    def test_tick_passes_inventory_adder_to_apply_event(self, game):
        """tick() should pass an inventory_adder callable to apply_event()."""
        find_item_evt = _find_event('find_item')
        assert find_item_evt is not None
        # Use side_effect so the pre-refactor code (which calls random.choice
        # twice: once for the event, once for the item) doesn't crash with a
        # TypeError. After the refactor, random.choice is called only once
        # (for the event); the inventory_adder is passed to apply_event.
        empty_result = {'message': None, 'item_dropped': None, 'xp_gained': 0}
        with patch('random.random', return_value=0.001), \
                patch('random.choice', side_effect=[find_item_evt, 'apple']), \
                patch('ascii_pet.core.apply_event', create=True,
                      return_value=empty_result) as mock_apply:
            game.tick()
        assert mock_apply.called
        _, kwargs = mock_apply.call_args
        assert 'inventory_adder' in kwargs, (
            "apply_event should be called with an inventory_adder kwarg"
        )
        adder = kwargs['inventory_adder']
        assert callable(adder), (
            "inventory_adder should be a callable"
        )
