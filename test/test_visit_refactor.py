#!/usr/bin/env python3
"""TDD tests for Task 7: refactor PetGame._tick_visit_events() to use
apply_event(), delete _apply_visit_event_effects(), and refactor
protocol.make_visit_event() to use serialize_event() internally.

Two test strategies are used:
  1. Strict RED-GREEN tests (TestTickVisitUsesApplyEvent): asserts NEW
     behavior (stat-gate blocks, CHAOS bumps, apply_event called) and that
     _apply_visit_event_effects is deleted. These FAIL against the current
     inline implementation (which uses _apply_visit_event_effects with no
     stat-gate/CHAOS) and PASS only after the refactor.
  2. make_visit_event tests (TestMakeVisitEventRefactor): asserts the
     return structure and values are preserved after the refactor to use
     serialize_event() internally.

Ownership boundary: only PetGame._tick_visit_events(),
_apply_visit_event_effects() deletion, _handle_lan_message MSG_VISIT_EVENT
receiver update, and protocol.make_visit_event() are in scope.
tick() and trigger_interaction() are owned by other tasks and NOT tested here.
"""
import os
import sys
import time
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame
from ascii_pet.events import Event, apply_event
from ascii_pet.protocol import (
    MSG_VISIT_EVENT, make_visit_event, VISIT_EVENTS,
)


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-visit-refactor-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


def _happy_boost_event():
    """A visit event with only a positive HAPPY effect (+15)."""
    return Event(
        event_id='test_visit_happy_boost',
        description='Test happy boost',
        effects={'HAPPY': 15},
        target='self',
        category='visit',
        metadata={'original_event_type': 'test_visit_happy_boost'},
    )


def _negative_event():
    """A visit event with a negative HAPPY effect (-5)."""
    return Event(
        event_id='test_visit_negative',
        description='Test negative',
        effects={'HAPPY': -5},
        target='self',
        category='visit',
        metadata={'original_event_type': 'test_visit_negative'},
    )


@pytest.fixture
def game(tmp_path):
    """Provide a fresh PetGame with isolated temp dir and an active visit."""
    uid = _uid()
    g = PetGame(uid, data_dir=tmp_path)
    g.visit_event_cooldown = 0  # not on cooldown
    g.active_visit = {
        'target': 'peer-1',
        'start_time': time.time(),
        'pet_snapshot': {},
    }
    # Attach a mock lan_node so send_to_peer can be asserted.
    g.lan_enabled = True
    g.lan_node = MagicMock()
    g.lan_node.send_to_peer = MagicMock(return_value=True)
    return g


# ─── Strict RED-GREEN tests for _tick_visit_events ─────────────────────────


class TestTickVisitUsesApplyEvent:
    """Verify _tick_visit_events() delegates to apply_event() and honors
    stat-gate + CHAOS bump (NEW behavior).

    These tests FAIL against the current inline implementation (RED) and
    PASS only after the refactor (GREEN).
    """

    def test_tick_visit_events_uses_apply_event(self, game):
        """_tick_visit_events() should call apply_event() with the Event."""
        evt = _happy_boost_event()
        empty_result = {'message': None, 'item_dropped': None, 'xp_gained': 0}
        with patch('random.random', return_value=0.05), \
                patch('random.choice', return_value=evt), \
                patch('ascii_pet.core.apply_event',
                      return_value=empty_result) as mock_apply:
            game._tick_visit_events()
        assert mock_apply.called, (
            "_tick_visit_events() should call apply_event()"
        )
        # The second positional arg should be the Event.
        args, _ = mock_apply.call_args
        assert len(args) >= 2, (
            "apply_event should be called with at least (state, event)"
        )
        passed_event = args[1]
        assert isinstance(passed_event, Event), (
            "second arg to apply_event should be an Event instance"
        )

    def test_tick_visit_events_applies_stat_effect(self, game):
        """Visit event with HAPPY=30, +15 → HAPPY=45 (stat-gate allows <80)."""
        game.state['stats']['HAPPY'] = 30
        evt = _happy_boost_event()
        with patch('random.random', return_value=0.05), \
                patch('random.choice', return_value=evt):
            game._tick_visit_events()
        assert game.state['stats']['HAPPY'] == 45, (
            "visit event should add 15 HAPPY (30 -> 45) when stat < 80"
        )

    def test_tick_visit_events_stat_gate_blocks(self, game):
        """Visit event with HAPPY=90, +15 → HAPPY stays 90 (NEW stat-gate).

        NEW behavior: stat-gate blocks positive effects when stat >= 80.
        Current inline code does min(100, 90+15)=100, so this fails RED.
        After refactor, apply_event() skips the +15 because 90 >= 80.
        """
        game.state['stats']['HAPPY'] = 90
        evt = _happy_boost_event()
        with patch('random.random', return_value=0.05), \
                patch('random.choice', return_value=evt):
            game._tick_visit_events()
        assert game.state['stats']['HAPPY'] == 90, (
            "stat-gate should block positive effect when stat >= 80"
        )

    def test_tick_visit_events_chaos_bump(self, game):
        """Visit event with negative effect → CHAOS+3 (NEW behavior).

        NEW behavior: any negative effect triggers CHAOS +3.
        Current inline code has no CHAOS bump, so this fails RED.
        """
        game.state['stats']['HAPPY'] = 50
        game.state['stats']['CHAOS'] = 50
        evt = _negative_event()
        with patch('random.random', return_value=0.05), \
                patch('random.choice', return_value=evt):
            game._tick_visit_events()
        assert game.state['stats']['CHAOS'] == 53, (
            "negative visit event should bump CHAOS by 3 (50 -> 53)"
        )

    def test_tick_visit_events_sends_message(self, game):
        """_tick_visit_events() should set message to 'Visit event: ...'."""
        evt = _happy_boost_event()
        with patch('random.random', return_value=0.05), \
                patch('random.choice', return_value=evt):
            game._tick_visit_events()
        assert game.message is not None, (
            "_tick_visit_events should set a message"
        )
        assert 'Visit event' in game.message, (
            f"message should contain 'Visit event', got: {game.message!r}"
        )

    def test_tick_visit_events_sends_to_peer(self, game):
        """_tick_visit_events() should send MSG_VISIT_EVENT to the peer."""
        evt = _happy_boost_event()
        with patch('random.random', return_value=0.05), \
                patch('random.choice', return_value=evt):
            game._tick_visit_events()
        assert game.lan_node.send_to_peer.called, (
            "_tick_visit_events should call lan_node.send_to_peer"
        )
        call_args = game.lan_node.send_to_peer.call_args
        args, _ = call_args
        # send_to_peer(peer_id, msg_type, payload)
        assert args[0] == 'peer-1', (
            "should send to the active visit target 'peer-1'"
        )
        assert args[1] == MSG_VISIT_EVENT, (
            "should send MSG_VISIT_EVENT"
        )
        payload = args[2]
        assert isinstance(payload, dict), (
            "payload should be a dict"
        )
        assert 'event_type' in payload, (
            "payload should contain 'event_type' key"
        )
        assert 'description' in payload, (
            "payload should contain 'description' key"
        )
        assert 'stat_effects' in payload, (
            "payload should contain 'stat_effects' key"
        )


# ─── _apply_visit_event_effects deletion test ──────────────────────────────


class TestApplyVisitEventEffectsDeleted:
    """Verify _apply_visit_event_effects has been deleted from PetGame."""

    def test_apply_visit_event_effects_deleted(self):
        """PetGame should NOT have _apply_visit_event_effects attribute.

        After the refactor, _tick_visit_events uses apply_event() and the
        receiver builds an Event from the payload. The old
        _apply_visit_event_effects helper is no longer needed and must be
        deleted.
        """
        assert not hasattr(PetGame, '_apply_visit_event_effects'), (
            "PetGame should not have _apply_visit_event_effects "
            "(it was deleted in favor of apply_event)"
        )


# ─── make_visit_event refactor tests ────────────────────────────────────────


class TestMakeVisitEventRefactor:
    """Verify make_visit_event() preserves its external contract after the
    refactor to use serialize_event() internally.

    The signature (event_type, description, stat_effects) and the returned
    dict structure ({event_type, description, stat_effects}) must remain
    backward-compatible.
    """

    def test_make_visit_event_returns_old_keys(self):
        """make_visit_event returns dict with the 3 old keys."""
        evt = make_visit_event('play_together', 'desc', {'happy': 15})
        assert isinstance(evt, dict), (
            "make_visit_event should return a dict"
        )
        assert set(evt.keys()) == {'event_type', 'description', 'stat_effects'}, (
            f"expected keys {{event_type, description, stat_effects}}, "
            f"got: {set(evt.keys())}"
        )

    def test_make_visit_event_preserves_values(self):
        """make_visit_event preserves the input values in the returned dict."""
        evt = make_visit_event('play_together', 'desc', {'happy': 15})
        assert evt['event_type'] == 'play_together', (
            f"event_type should be 'play_together', got: {evt['event_type']!r}"
        )
        assert evt['description'] == 'desc', (
            f"description should be 'desc', got: {evt['description']!r}"
        )
        assert evt['stat_effects'] == {'happy': 15}, (
            f"stat_effects should be {{'happy': 15}}, got: {evt['stat_effects']!r}"
        )
