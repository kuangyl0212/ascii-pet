#!/usr/bin/env python3
"""TDD tests for visit heartbeat (keep-alive) mechanism.

Redesign-visit-lifecycle spec:
- Both active_visit and being_visited sides send MSG_VISIT_HEARTBEAT every 5s
- Heartbeat payload: {"from": node_id, "ts": timestamp}
- On receive: update active_visit['last_heartbeat'] / being_visited['last_heartbeat']
- Timeout: 15s without receiving heartbeat -> auto end_visit() with
  "Visit ended (connection lost)" message, keep current UI state
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
    MSG_VISIT_REQ, MSG_VISIT_END, MSG_VISIT_HEARTBEAT,
    make_pet_snapshot,
)
from ascii_pet.states import ExpandedState, CompactState, LanState


def _uid():
    return f'test-visit-heartbeat-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


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


def _set_active_visit(game, target='peer-bob', age=0.0):
    """Set up an active_visit with optional age in seconds."""
    now = time.time()
    game.active_visit = {
        'target': target,
        'start_time': now - age,
        'pet_snapshot': _make_snapshot(name='AlicePet'),
        'last_heartbeat': now - age,
    }


def _set_being_visited(game, from_id='fake-node-bob', age=0.0):
    """Set up being_visited with optional age in seconds."""
    now = time.time()
    snap = _make_snapshot(name='BobPet', owner=from_id)
    game.being_visited = {
        'from': from_id,
        'start_time': now - age,
        'pet_snapshot': snap,
        'last_heartbeat': now - age,
    }
    game.visitor_pets[from_id] = snap


# ─── Heartbeat sending ───


class TestHeartbeatSending:
    """Both sides send MSG_VISIT_HEARTBEAT every 5 seconds."""

    def test_active_visit_sends_heartbeat_after_5_seconds(self, game):
        """active_visit side sends MSG_VISIT_HEARTBEAT to target after 5s."""
        _set_active_visit(game, target='peer-bob', age=0.0)
        # Set last send to 6 seconds ago -> should send now
        game._last_heartbeat_send = time.time() - 6

        game._tick_visit_heartbeat()

        hb_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_HEARTBEAT]
        assert len(hb_calls) >= 1, "active_visit side should send heartbeat after 5s"
        peer_id, msg_type, payload = hb_calls[-1]
        assert peer_id == 'peer-bob'

    def test_being_visited_sends_heartbeat_after_5_seconds(self, game):
        """being_visited side sends MSG_VISIT_HEARTBEAT to visitor after 5s."""
        _set_being_visited(game, from_id='fake-node-bob', age=0.0)
        game._last_heartbeat_send = time.time() - 6

        game._tick_visit_heartbeat()

        hb_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_HEARTBEAT]
        assert len(hb_calls) >= 1, "being_visited side should send heartbeat after 5s"
        peer_id, msg_type, payload = hb_calls[-1]
        assert peer_id == 'fake-node-bob'

    def test_heartbeat_not_sent_within_5_seconds(self, game):
        """No heartbeat sent if less than 5 seconds since last send."""
        _set_active_visit(game, target='peer-bob', age=0.0)
        game._last_heartbeat_send = time.time() - 2  # only 2s ago

        game._tick_visit_heartbeat()

        hb_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_HEARTBEAT]
        assert len(hb_calls) == 0, "should not send heartbeat within 5s of last send"

    def test_heartbeat_payload_includes_from_and_ts(self, game):
        """Heartbeat payload must include 'from' (node_id) and 'ts' (timestamp)."""
        _set_active_visit(game, target='peer-bob', age=0.0)
        game._last_heartbeat_send = time.time() - 6

        game._tick_visit_heartbeat()

        hb_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_HEARTBEAT]
        assert len(hb_calls) >= 1
        peer_id, msg_type, payload = hb_calls[-1]
        assert 'from' in payload, "payload must include 'from' node_id"
        assert payload['from'] == game.lan_node.node_id
        assert 'ts' in payload, "payload must include 'ts' timestamp"
        assert isinstance(payload['ts'], (int, float))

    def test_no_heartbeat_sent_when_no_visit(self, game):
        """No heartbeat sent when neither active_visit nor being_visited."""
        game._last_heartbeat_send = 0  # never sent

        game._tick_visit_heartbeat()

        hb_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_HEARTBEAT]
        assert len(hb_calls) == 0


# ─── Heartbeat receiving ───


class TestHeartbeatReceiving:
    """Receiving MSG_VISIT_HEARTBEAT updates last_heartbeat timestamp."""

    def test_receive_heartbeat_updates_active_visit(self, game):
        """When active_visit side receives heartbeat, update last_heartbeat."""
        _set_active_visit(game, target='peer-bob', age=10.0)
        old_hb = game.active_visit['last_heartbeat']

        # Simulate receiving heartbeat from the visited peer
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_HEARTBEAT,
            'payload': {'from': 'peer-bob', 'ts': time.time()},
        })
        game.process_lan_queues()

        assert game.active_visit is not None, "visit should still be active"
        assert game.active_visit['last_heartbeat'] > old_hb, (
            "last_heartbeat should be updated when heartbeat received"
        )

    def test_receive_heartbeat_updates_being_visited(self, game):
        """When being_visited side receives heartbeat, update last_heartbeat."""
        _set_being_visited(game, from_id='fake-node-bob', age=10.0)
        old_hb = game.being_visited['last_heartbeat']

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_HEARTBEAT,
            'payload': {'from': 'fake-node-bob', 'ts': time.time()},
        })
        game.process_lan_queues()

        assert game.being_visited is not None, "visit should still be active"
        assert game.being_visited['last_heartbeat'] > old_hb, (
            "last_heartbeat should be updated when heartbeat received"
        )


# ─── Heartbeat timeout ───


class TestHeartbeatTimeout:
    """If no heartbeat received for 15 seconds, auto-end visit."""

    def test_timeout_active_visit_ends_visit(self, game):
        """active_visit with stale heartbeat (>15s) is auto-ended."""
        _set_active_visit(game, target='peer-bob', age=20.0)
        # last_heartbeat is 20s ago -> timeout
        game.active_visit['last_heartbeat'] = time.time() - 20
        game._last_heartbeat_send = time.time()  # don't send this tick

        game._tick_visit_heartbeat()

        assert game.active_visit is None, (
            "active_visit should be cleared after heartbeat timeout"
        )

    def test_timeout_being_visited_ends_visit(self, game):
        """being_visited with stale heartbeat (>15s) is auto-ended."""
        _set_being_visited(game, from_id='fake-node-bob', age=20.0)
        game.being_visited['last_heartbeat'] = time.time() - 20
        game._last_heartbeat_send = time.time()

        game._tick_visit_heartbeat()

        assert game.being_visited is None, (
            "being_visited should be cleared after heartbeat timeout"
        )

    def test_timeout_shows_connection_lost_message(self, game):
        """Heartbeat timeout shows 'Visit ended (connection lost)' message."""
        _set_active_visit(game, target='peer-bob', age=20.0)
        game.active_visit['last_heartbeat'] = time.time() - 20
        game._last_heartbeat_send = time.time()

        game._tick_visit_heartbeat()

        assert 'connection lost' in game.message.lower(), (
            f"Expected 'connection lost' in message, got: {game.message!r}"
        )

    def test_timeout_keeps_current_state(self, game):
        """Heartbeat timeout does NOT transition to LanState."""
        # Start in ExpandedState (not LanState)
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game, target='peer-bob', age=20.0)
        game.active_visit['last_heartbeat'] = time.time() - 20
        game._last_heartbeat_send = time.time()

        game._tick_visit_heartbeat()

        current = game._inner_state()
        assert isinstance(current, ExpandedState), (
            f"Should stay in ExpandedState after timeout, got {type(current).__name__}"
        )
        assert not isinstance(current, LanState), (
            "Should NOT transition to LanState on heartbeat timeout"
        )

    def test_no_timeout_when_heartbeat_recent(self, game):
        """Visit not ended if heartbeat received recently."""
        _set_active_visit(game, target='peer-bob', age=20.0)
        # last_heartbeat is recent -> no timeout
        game.active_visit['last_heartbeat'] = time.time() - 3
        game._last_heartbeat_send = time.time()

        game._tick_visit_heartbeat()

        assert game.active_visit is not None, (
            "active_visit should NOT be cleared when heartbeat is recent"
        )

    def test_timeout_clears_visitor_pets(self, game):
        """Heartbeat timeout removes visitor pet from visitor_pets."""
        _set_active_visit(game, target='peer-bob', age=20.0)
        game.visitor_pets['peer-bob'] = _make_snapshot(name='BobPet')
        game.active_visit['last_heartbeat'] = time.time() - 20
        game._last_heartbeat_send = time.time()

        game._tick_visit_heartbeat()

        assert 'peer-bob' not in game.visitor_pets, (
            "visitor_pets entry should be removed on heartbeat timeout"
        )
