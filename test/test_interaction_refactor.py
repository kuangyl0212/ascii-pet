#!/usr/bin/env python3
"""TDD tests for Task 6: refactor PetGame.trigger_interaction() to use apply_event().

Two test strategies are used:
  1. Characterization tests (TestInteractionCharacterization): verify the
     observable behavior of trigger_interaction() is unchanged by the refactor.
     These PASS against the current inline implementation AND after the
     refactor to apply_event().
  2. Strict RED-GREEN tests (TestInteractionUsesApplyEvent): asserts NEW
     behavior (stat-gate blocks, CHAOS bumps) and that trigger_interaction()
     calls apply_event(). These FAIL against the current inline implementation
     (which has no stat-gate/CHAOS in interactions) and PASS only after the
     refactor.

Ownership boundary: only PetGame.trigger_interaction() is in scope.
tick(), _tick_visit_events(), _apply_visit_event_effects(), and protocol.py
are owned by other tasks and are NOT tested here.
"""
import os
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame, PET_INTERACTIONS, generate_companion, init_state
from ascii_pet.events import Event


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-interaction-refactor-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


def _find_interaction(event_id):
    """Find an interaction Event by id. Returns the Event or None."""
    for evt in PET_INTERACTIONS:
        if evt.event_id == event_id:
            return evt
    return None


def _add_second_pet(game):
    """Helper: add a second pet to the game for multi-pet tests."""
    game.pets_data['pets'][game.pet_idx] = game.state
    bones = generate_companion(game.uid + '-2')
    new_state = init_state(game.uid + '-2', bones, 'SecondPet')
    game.pets_data['pets'].append(new_state)
    game.save()


@pytest.fixture
def game(tmp_path):
    """Provide a fresh PetGame with isolated temp dir."""
    uid = _uid()
    return PetGame(uid, data_dir=tmp_path)


# ─── Characterization tests (pass before AND after refactor) ─────────────────


class TestInteractionCharacterization:
    """Verify trigger_interaction() observable behavior is unchanged.

    These tests must pass against the current inline implementation AND
    against the refactored implementation that calls apply_event().
    """

    def test_interaction_applies_stat_effect(self, game):
        """play_together with HAPPY=30/40 should raise both by +5 (35/45).

        effects={'HAPPY': 5}, target='both'. Stats are below the stat-gate
        threshold (80), so the positive effect applies normally.
        """
        _add_second_pet(game)
        play_together = _find_interaction('play_together')
        assert play_together is not None, "play_together interaction must exist"
        game.pets_data['pets'][0]['stats']['HAPPY'] = 30
        game.pets_data['pets'][1]['stats']['HAPPY'] = 40
        with patch('random.random', return_value=0.1), \
                patch('random.choice', return_value=play_together):
            game.trigger_interaction()
        assert game.pets_data['pets'][0]['stats']['HAPPY'] == 35, (
            "play_together should add 5 HAPPY to pet 0 (30 -> 35)"
        )
        assert game.pets_data['pets'][1]['stats']['HAPPY'] == 45, (
            "play_together should add 5 HAPPY to pet 1 (40 -> 45)"
        )

    def test_interaction_target_self_only_affects_current(self, game):
        """share_food (target='self') should only affect the current pet.

        effects={'HUNGER': 10}, target='self'. Only the current pet's HUNGER
        should increase; the other pet is untouched.
        """
        _add_second_pet(game)
        share_food = _find_interaction('share_food')
        assert share_food is not None, "share_food interaction must exist"
        for pet in game.pets_data['pets']:
            pet['stats']['HUNGER'] = 50
        other_idx = 1 if game.pet_idx == 0 else 0
        with patch('random.random', return_value=0.1), \
                patch('random.choice', return_value=share_food):
            game.trigger_interaction()
        assert game.state['stats']['HUNGER'] == 60, (
            "share_food should add 10 HUNGER to current pet (50 -> 60)"
        )
        assert game.pets_data['pets'][other_idx]['stats']['HUNGER'] == 50, (
            "share_food should NOT affect the other pet"
        )

    def test_interaction_message_uses_event_description(self, game):
        """The returned message should contain the event description."""
        _add_second_pet(game)
        play_together = _find_interaction('play_together')
        assert play_together is not None
        with patch('random.random', return_value=0.1), \
                patch('random.choice', return_value=play_together):
            msg = game.trigger_interaction()
        assert msg is not None, "trigger_interaction should return a message"
        assert 'played together' in msg, (
            f"message should contain the event description, got: {msg!r}"
        )


# ─── Strict RED-GREEN tests (fail before refactor, pass after) ───────────────


class TestInteractionUsesApplyEvent:
    """Verify trigger_interaction() delegates to apply_event() and honors
    stat-gate + CHAOS bump (NEW behavior).

    These tests FAIL against the current inline implementation (RED) and
    PASS only after the refactor (GREEN).
    """

    def test_interaction_stat_gate_blocks_when_stat_above_80(self, game):
        """play_together with HAPPY=90 should NOT increase HAPPY (stat-gate).

        NEW behavior: stat-gate blocks positive effects when stat >= 80.
        Current inline code does min(100, 90+5)=95, so this fails RED.
        After refactor, apply_event() skips the +5 because 90 >= 80.
        """
        _add_second_pet(game)
        play_together = _find_interaction('play_together')
        assert play_together is not None
        for pet in game.pets_data['pets']:
            pet['stats']['HAPPY'] = 90
        with patch('random.random', return_value=0.1), \
                patch('random.choice', return_value=play_together):
            game.trigger_interaction()
        for pet in game.pets_data['pets']:
            assert pet['stats']['HAPPY'] == 90, (
                "stat-gate should block positive effect when stat >= 80"
            )

    def test_interaction_negative_effect_increases_chaos(self, game):
        """An interaction with a negative effect should bump CHAOS by +3.

        NEW behavior: any negative effect triggers CHAOS +3 (once per pet).
        Current inline code has no CHAOS bump, so this fails RED.

        Since no builtin PET_INTERACTIONS have negative effects, we construct
        a custom interaction Event with a negative effect and mock random.choice
        to return it.
        """
        _add_second_pet(game)
        negative_interaction = Event(
            event_id='test_negative_interaction',
            description=' had a fight!',
            effects={'HAPPY': -5},
            target='both',
            category='interaction',
        )
        for pet in game.pets_data['pets']:
            pet['stats']['HAPPY'] = 50
            pet['stats']['CHAOS'] = 50
        with patch('random.random', return_value=0.1), \
                patch('random.choice', return_value=negative_interaction):
            game.trigger_interaction()
        for pet in game.pets_data['pets']:
            assert pet['stats']['CHAOS'] == 53, (
                "negative interaction should bump CHAOS by 3 (50 -> 53)"
            )

    def test_interaction_calls_apply_event(self, game):
        """trigger_interaction() should call apply_event() with the Event.

        NEW behavior: trigger_interaction() delegates to apply_event().
        Current inline code does not call apply_event, so this fails RED.
        """
        _add_second_pet(game)
        play_together = _find_interaction('play_together')
        assert play_together is not None
        empty_result = {'message': None, 'item_dropped': None, 'xp_gained': 0}
        with patch('random.random', return_value=0.1), \
                patch('random.choice', return_value=play_together), \
                patch('ascii_pet.core.apply_event',
                      return_value=empty_result) as mock_apply:
            game.trigger_interaction()
        assert mock_apply.called, (
            "trigger_interaction() should call apply_event()"
        )
        # Verify the Event and pets_data are passed through.
        args, kwargs = mock_apply.call_args
        assert len(args) >= 2, (
            "apply_event should be called with at least (state, event)"
        )
        passed_event = args[1]
        assert isinstance(passed_event, Event), (
            "second arg to apply_event should be an Event instance"
        )
        assert passed_event.event_id == 'play_together', (
            "passed event should be the play_together event"
        )
        assert 'pets_data' in kwargs, (
            "apply_event should be called with pets_data kwarg"
        )
        assert kwargs['pets_data'] is game.pets_data, (
            "pets_data kwarg should be the game's pets_data"
        )
