#!/usr/bin/env python3
"""TDD tests for visit end keeping current UI state.

Redesign-visit-lifecycle spec:
- end_visit() does NOT transition state machine
- MSG_VISIT_END handler does NOT transition to LanState
- _tick_visit_timeout does NOT transition to LanState
- After visit ends, user stays in CompactState/ExpandedState
- Visitor pet is removed from visitor_pets
- End message is displayed
"""
import os
import sys
import time
import queue
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame
from ascii_pet.protocol import (
    MSG_VISIT_REQ, MSG_VISIT_END, make_pet_snapshot,
)
from ascii_pet.states import ExpandedState, CompactState, LanState


def _uid():
    return f'test-visit-keep-state-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


def _make_snapshot(name='VisitorPet', owner='visitor-owner', species='cat'):
    return {
        'name': name,
        'species': species,
        'rarity': 'common',
        'level': 1,
        'shiny': False,
        'eye': '·',
        'hat': 'none',
        'mood': 'normal',
        'owner': owner,
    }


class _FakeLanNode:
    """Fake LanNode for testing without real network."""

    def __init__(self, username, pet_state):
        self.username = username
        self.pet_state = pet_state
        self.node_id = f'fake-node-{username}'
        self.ui_queue = queue.Queue()
        self.net_queue = queue.Queue()
        self._status = {
            'enabled': False,
            'is_master': False,
            'peer_count': 0,
            'error': None,
            'node_id': self.node_id,
        }
        self._peers = []
        self.send_calls = []

    def start(self):
        self._status['enabled'] = True
        self._status['is_master'] = True
        return True

    def stop(self):
        self._status['enabled'] = False

    def get_status(self):
        return dict(self._status)

    def get_peers(self):
        return list(self._peers)

    def send_to_peer(self, peer_node_id, msg_type, payload):
        self.send_calls.append((peer_node_id, msg_type, payload))
        return True

    def send_broadcast(self, msg_type, payload):
        return True


@pytest.fixture
def game(tmp_path):
    """Provide a fresh PetGame with isolated temp dir and LAN enabled."""
    uid = _uid()
    g = PetGame(uid, data_dir=tmp_path)
    fake_node = _FakeLanNode('alice', g.state)
    with patch('ascii_pet.lan.LanNode', return_value=fake_node):
        g.enable_lan('alice')
    return g


def _set_active_visit(game, target='peer-bob'):
    game.active_visit = {
        'target': target,
        'start_time': time.time(),
        'pet_snapshot': _make_snapshot(name='AlicePet'),
        'last_heartbeat': time.time(),
    }
    game.visitor_pets[target] = _make_snapshot(name='BobPet', owner=target)


def _set_being_visited(game, from_id='fake-node-bob'):
    snap = _make_snapshot(name='BobPet', owner=from_id)
    game.being_visited = {
        'from': from_id,
        'start_time': time.time(),
        'pet_snapshot': snap,
        'last_heartbeat': time.time(),
    }
    game.visitor_pets[from_id] = snap


# ─── Initiator presses 'e' to end visit ───


class TestEndVisitKeepsState:
    """Ending a visit keeps the user in their current UI state."""

    def test_initiator_end_visit_keeps_expanded_state(self, game):
        """Initiator pressing 'e' in ExpandedState stays in ExpandedState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game, target='peer-bob')

        game.handle_key('e')

        current = game._inner_state()
        assert isinstance(current, ExpandedState), (
            f"Should stay in ExpandedState after ending visit, got {type(current).__name__}"
        )
        assert game.active_visit is None, "active_visit should be cleared"

    def test_initiator_end_visit_keeps_compact_state(self, game):
        """Initiator pressing 'e' in CompactState stays in CompactState."""
        # CompactState is the initial state
        _set_active_visit(game, target='peer-bob')

        game.handle_key('e')

        current = game._inner_state()
        assert isinstance(current, CompactState), (
            f"Should stay in CompactState after ending visit, got {type(current).__name__}"
        )

    def test_initiator_end_visit_does_not_go_to_lan(self, game):
        """Ending visit must NOT transition to LanState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game, target='peer-bob')

        game.handle_key('e')

        current = game._inner_state()
        assert not isinstance(current, LanState), (
            "Must NOT transition to LanState when ending visit"
        )

    def test_initiator_end_visit_shows_message(self, game):
        """Ending visit shows 'Visit ended' message."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game, target='peer-bob')

        game.handle_key('e')

        assert 'visit ended' in game.message.lower(), (
            f"Expected 'Visit ended' message, got: {game.message!r}"
        )

    def test_initiator_end_visit_removes_visitor_pet(self, game):
        """Ending visit removes the visitor pet from visitor_pets."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game, target='peer-bob')
        assert 'peer-bob' in game.visitor_pets

        game.handle_key('e')

        assert 'peer-bob' not in game.visitor_pets, (
            "visitor_pets entry should be removed after ending visit"
        )


# ─── Receiver gets MSG_VISIT_END ───


class TestReceiveVisitEndKeepsState:
    """Receiver of MSG_VISIT_END stays in current state."""

    def test_receiver_keeps_expanded_state(self, game):
        """Receiver in ExpandedState stays in ExpandedState on MSG_VISIT_END."""
        game.sm.transition_to(game, ExpandedState())
        _set_being_visited(game, from_id='fake-node-bob')

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual', 'from': 'fake-node-bob'},
        })
        game.process_lan_queues()

        current = game._inner_state()
        assert isinstance(current, ExpandedState), (
            f"Should stay in ExpandedState, got {type(current).__name__}"
        )
        assert game.being_visited is None

    def test_receiver_keeps_compact_state(self, game):
        """Receiver in CompactState stays in CompactState on MSG_VISIT_END."""
        _set_being_visited(game, from_id='fake-node-bob')

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual', 'from': 'fake-node-bob'},
        })
        game.process_lan_queues()

        current = game._inner_state()
        assert isinstance(current, CompactState), (
            f"Should stay in CompactState, got {type(current).__name__}"
        )

    def test_receiver_does_not_go_to_lan(self, game):
        """Receiver must NOT transition to LanState on MSG_VISIT_END."""
        game.sm.transition_to(game, ExpandedState())
        _set_being_visited(game, from_id='fake-node-bob')

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual', 'from': 'fake-node-bob'},
        })
        game.process_lan_queues()

        current = game._inner_state()
        assert not isinstance(current, LanState), (
            "Must NOT transition to LanState on MSG_VISIT_END"
        )

    def test_receiver_removes_visitor_pet(self, game):
        """Receiver removes visitor pet from visitor_pets on MSG_VISIT_END."""
        _set_being_visited(game, from_id='fake-node-bob')
        assert 'fake-node-bob' in game.visitor_pets

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual', 'from': 'fake-node-bob'},
        })
        game.process_lan_queues()

        assert 'fake-node-bob' not in game.visitor_pets


# ─── Visit timeout keeps state ───


class TestVisitTimeoutKeepsState:
    """_tick_visit_timeout does NOT transition state."""

    def test_timeout_keeps_expanded_state(self, game):
        """Visit timeout in ExpandedState stays in ExpandedState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game, target='peer-bob')
        # Set start_time to 11 minutes ago -> timeout
        game.active_visit['start_time'] = time.time() - 660

        game._tick_visit_timeout()

        current = game._inner_state()
        assert isinstance(current, ExpandedState), (
            f"Should stay in ExpandedState after timeout, got {type(current).__name__}"
        )
        assert game.active_visit is None

    def test_timeout_does_not_go_to_lan(self, game):
        """Visit timeout must NOT transition to LanState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game, target='peer-bob')
        game.active_visit['start_time'] = time.time() - 660

        game._tick_visit_timeout()

        current = game._inner_state()
        assert not isinstance(current, LanState), (
            "Must NOT transition to LanState on visit timeout"
        )

    def test_timeout_shows_auto_ended_message(self, game):
        """Visit timeout shows 'Visit timed out, auto-ended' message."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game, target='peer-bob')
        game.active_visit['start_time'] = time.time() - 660

        game._tick_visit_timeout()

        assert 'auto-ended' in game.message.lower() or 'timed out' in game.message.lower(), (
            f"Expected timeout message, got: {game.message!r}"
        )
