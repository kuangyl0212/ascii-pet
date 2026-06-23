#!/usr/bin/env python3
"""Pytest tests for LAN integration in PetGame.

Strict TDD: these tests are written BEFORE PetGame LAN integration.
Run with: python -m pytest test_lan_game.py -v

Test categories:
1. LAN field initialization
2. enable_lan / disable_lan lifecycle
3. get_lan_status
4. Visitor management (receive_visitor, dismiss_visitor)
5. Visit invitations (invite_visit, respond_visit)
6. process_lan_queues (UI queue polling)
7. Graceful degradation (single-player still works when LAN fails)

All tests mock LanNode — no real network is started.
"""

import os
import sys
import time
import queue
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pet_core
from pet_core import PetGame
from lan_protocol import (
    MSG_HELLO, MSG_PEER_LIST, MSG_HEARTBEAT,
    MSG_VISIT_REQ, MSG_VISIT_ACK, MSG_VISIT_DATA,
    MSG_VISIT_LEAVE, MSG_BYE,
    make_pet_snapshot,
)


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-lan-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


@pytest.fixture
def game(tmp_path):
    """Provide a fresh PetGame with isolated temp dir."""
    uid = _uid()
    return PetGame(uid, data_dir=tmp_path)


def _make_snapshot(name='VisitorPet', owner='visitor-owner'):
    """Build a minimal pet snapshot dict matching make_pet_snapshot output."""
    return {
        'name': name,
        'species': 'cat',
        'rarity': 'common',
        'level': 1,
        'shiny': False,
        'eye': '·',
        'hat': 'none',
        'mood': 'normal',
        'owner': owner,
    }


class _FakeLanNode:
    """Fake LanNode that simulates network behavior without real sockets.

    - start() can be configured to succeed or fail via _start_should_succeed
    - ui_queue is a real queue.Queue that tests can populate
    - send_to_peer records all calls in send_calls for verification
    """

    def __init__(self, username, pet_state, udp_port=50007, tcp_port=50008):
        self.username = username
        self.pet_state = pet_state
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.node_id = f'fake-node-{username}'
        self.ui_queue = queue.Queue()
        self.net_queue = queue.Queue()
        self._start_should_succeed = True
        self._status = {
            'enabled': False,
            'is_master': False,
            'peer_count': 0,
            'error': None,
            'node_id': self.node_id,
        }
        self._peers = []
        self.send_calls = []  # records (peer_id, msg_type, payload)

    def start(self):
        if self._start_should_succeed:
            self._status['enabled'] = True
            self._status['is_master'] = True
            return True
        else:
            self._status['error'] = 'mock start failure'
            return False

    def stop(self):
        self._status['enabled'] = False
        self._status['is_master'] = False

    def get_status(self):
        return dict(self._status)

    def get_peers(self):
        return list(self._peers)

    def send_to_peer(self, peer_node_id, msg_type, payload):
        self.send_calls.append((peer_node_id, msg_type, payload))
        return True

    def send_broadcast(self, msg_type, payload):
        return True


# ─── 1. LAN field initialization ────────────────────────────────────────────


class TestLanFieldInit:
    """PetGame initializes LAN fields to disabled/empty state."""

    def test_lan_fields_default_disabled(self, game):
        """After __init__, lan_enabled=False, lan_node=None, lan_peers=[], visitor_pets=[]."""
        assert game.lan_enabled is False
        assert game.lan_node is None
        assert game.lan_peers == []
        assert game.visitor_pets == []

    def test_pending_visit_request_default_none(self, game):
        """pending_visit_request starts as None."""
        assert game.pending_visit_request is None

    def test_single_player_still_works(self, game):
        """Single-player methods work normally without LAN."""
        # feed
        game.state['stats']['HUNGER'] = 50
        msg, anim = game.handle_action('feed')
        assert msg is not None
        # play
        game.state['stats']['ENERGY'] = 50
        msg, anim = game.handle_action('play')
        assert msg is not None
        # sleep
        game.state['stats']['ENERGY'] = 50
        msg, anim = game.handle_action('sleep')
        assert msg is not None


# ─── 2. enable_lan / disable_lan ────────────────────────────────────────────


class TestEnableDisableLan:
    """enable_lan and disable_lan lifecycle."""

    def test_enable_lan_success(self, game):
        """enable_lan returns True and sets lan_enabled when start() succeeds."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            result = game.enable_lan('alice')
        assert result is True
        assert game.lan_enabled is True
        assert game.lan_node is fake_node

    def test_enable_lan_failure_returns_false_no_raise(self, game):
        """enable_lan returns False and does not raise when start() fails."""
        fake_node = _FakeLanNode('alice', game.state)
        fake_node._start_should_succeed = False
        with patch('lan.LanNode', return_value=fake_node):
            result = game.enable_lan('alice')
        assert result is False
        assert game.lan_enabled is False
        assert game.lan_node is None

    def test_enable_lan_import_failure_returns_false(self, game):
        """enable_lan returns False when LanNode import fails (no exception raised)."""
        with patch('builtins.__import__', side_effect=ImportError('no lan module')):
            result = game.enable_lan('alice')
        assert result is False
        assert game.lan_enabled is False
        assert game.lan_node is None

    def test_disable_lan_clears_state(self, game):
        """disable_lan sets lan_enabled=False and clears peers/visitors."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        # Add some state to verify it gets cleared
        game.lan_peers = [{'node_id': 'peer1'}]
        game.visitor_pets = [_make_snapshot()]
        game.pending_visit_request = {'from': 'peer1'}

        game.disable_lan()

        assert game.lan_enabled is False
        assert game.lan_node is None
        assert game.lan_peers == []
        assert game.visitor_pets == []
        assert game.pending_visit_request is None

    def test_disable_lan_when_not_enabled_no_raise(self, game):
        """disable_lan on a game that never enabled LAN does not raise."""
        game.disable_lan()
        assert game.lan_enabled is False

    def test_disable_lan_calls_stop_on_node(self, game):
        """disable_lan calls stop() on the lan_node."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        stop_called = []
        original_stop = fake_node.stop
        def tracking_stop():
            stop_called.append(True)
            original_stop()
        fake_node.stop = tracking_stop

        game.disable_lan()

        assert stop_called == [True]


# ─── 3. get_lan_status ──────────────────────────────────────────────────────


class TestGetLanStatus:
    """get_lan_status returns appropriate status dict."""

    def test_status_when_disabled(self, game):
        """When LAN not enabled, returns disabled status with defaults."""
        status = game.get_lan_status()
        assert status == {
            'enabled': False,
            'is_master': False,
            'peer_count': 0,
            'error': None,
        }

    def test_status_when_enabled_returns_node_status(self, game):
        """When LAN enabled, returns the lan_node's get_status() result."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        # Configure fake status
        fake_node._status = {
            'enabled': True,
            'is_master': True,
            'peer_count': 2,
            'error': None,
            'node_id': 'fake-node-alice',
        }

        status = game.get_lan_status()

        assert status['enabled'] is True
        assert status['is_master'] is True
        assert status['peer_count'] == 2
        assert status['node_id'] == 'fake-node-alice'


# ─── 4. Visitor management ──────────────────────────────────────────────────


class TestVisitorManagement:
    """receive_visitor and dismiss_visitor behavior."""

    def test_receive_visitor_adds_to_list(self, game):
        """receive_visitor appends snapshot to visitor_pets."""
        snap = _make_snapshot(name='Buddy', owner='friend-1')
        game.receive_visitor(snap)
        assert len(game.visitor_pets) == 1
        assert game.visitor_pets[0]['name'] == 'Buddy'

    def test_receive_visitor_multiple(self, game):
        """Multiple visitors can be received."""
        game.receive_visitor(_make_snapshot(name='A'))
        game.receive_visitor(_make_snapshot(name='B'))
        game.receive_visitor(_make_snapshot(name='C'))
        assert len(game.visitor_pets) == 3
        assert [v['name'] for v in game.visitor_pets] == ['A', 'B', 'C']

    def test_dismiss_visitor_valid_index(self, game):
        """dismiss_visitor removes visitor at valid index and returns True."""
        game.receive_visitor(_make_snapshot(name='A'))
        game.receive_visitor(_make_snapshot(name='B'))
        result = game.dismiss_visitor(0)
        assert result is True
        assert len(game.visitor_pets) == 1
        assert game.visitor_pets[0]['name'] == 'B'

    def test_dismiss_visitor_invalid_index_returns_false(self, game):
        """dismiss_visitor returns False for out-of-range index."""
        game.receive_visitor(_make_snapshot(name='A'))
        assert game.dismiss_visitor(5) is False
        assert game.dismiss_visitor(-1) is False
        assert len(game.visitor_pets) == 1  # unchanged

    def test_dismiss_visitor_empty_list_returns_false(self, game):
        """dismiss_visitor on empty list returns False."""
        assert game.dismiss_visitor(0) is False

    def test_visitor_pets_unaffected_by_tick(self, game):
        """tick() does not decay or modify visitor_pets."""
        snap = _make_snapshot(name='Visitor', owner='friend')
        # Add a fake stat that tick might decay (if it touched visitors)
        snap['stats'] = {'HUNGER': 50}
        game.receive_visitor(snap)
        original_hunger = game.visitor_pets[0]['stats']['HUNGER']

        # Make local pet stats low so tick does decay work
        game.state['stats']['HUNGER'] = 0
        game.state['last_fed'] = (datetime.now() - timedelta(hours=5)).isoformat()
        game.last_tick_time = time.time() - 3600
        game.tick()

        # Visitor pet should be untouched
        assert game.visitor_pets[0]['stats']['HUNGER'] == original_hunger
        assert len(game.visitor_pets) == 1

    def test_visitor_pets_unaffected_by_switch_pet(self, game):
        """switch_pet does not affect visitor_pets."""
        # Add a second local pet
        from pet_core import generate_companion, init_state
        game.pets_data['pets'][game.pet_idx] = game.state
        bones = generate_companion(game.uid + '-2')
        new_state = init_state(game.uid + '-2', bones, 'SecondPet')
        game.pets_data['pets'].append(new_state)
        game.save()

        # Add a visitor
        game.receive_visitor(_make_snapshot(name='Visitor'))
        assert len(game.visitor_pets) == 1

        game.switch_pet(1)

        # Visitor should still be there
        assert len(game.visitor_pets) == 1
        assert game.visitor_pets[0]['name'] == 'Visitor'

    def test_dismiss_visitor_sends_visit_leave_when_lan_enabled(self, game):
        """dismiss_visitor sends MSG_VISIT_LEAVE to visitor's owner when LAN enabled."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        snap = _make_snapshot(name='Buddy', owner='friend-node-id')
        game.receive_visitor(snap)

        game.dismiss_visitor(0)

        # Should have sent VISIT_LEAVE to the owner
        leave_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_LEAVE]
        assert len(leave_calls) == 1
        peer_id, msg_type, payload = leave_calls[0]
        assert peer_id == 'friend-node-id'
        assert payload['pet_name'] == 'Buddy'


# ─── 5. Visit invitations ───────────────────────────────────────────────────


class TestVisitInvitations:
    """invite_visit and respond_visit behavior."""

    def test_invite_visit_when_disabled_returns_false(self, game):
        """invite_visit returns False when LAN not enabled."""
        result = game.invite_visit('peer-1')
        assert result is False

    def test_invite_visit_sends_visit_req(self, game):
        """invite_visit sends MSG_VISIT_REQ to the peer via lan_node."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        result = game.invite_visit('peer-node-id')

        assert result is True
        # Verify send_to_peer was called with MSG_VISIT_REQ
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_REQ]
        assert len(req_calls) == 1
        peer_id, msg_type, payload = req_calls[0]
        assert peer_id == 'peer-node-id'
        assert 'from' in payload
        assert 'pet_name' in payload
        assert payload['pet_name'] == game.state['name']

    def test_respond_visit_accept_sends_ack_and_data(self, game):
        """respond_visit(accept=True) sends MSG_VISIT_ACK then MSG_VISIT_DATA."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        result = game.respond_visit('peer-node-id', True)

        assert result is True
        # Should have sent ACK first
        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_ACK]
        assert len(ack_calls) == 1
        _, _, ack_payload = ack_calls[0]
        assert ack_payload['accept'] is True
        # Should have sent DATA after ACK
        data_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_DATA]
        assert len(data_calls) == 1
        peer_id, _, data_payload = data_calls[0]
        assert peer_id == 'peer-node-id'
        # Data payload should be a pet snapshot
        assert 'name' in data_payload
        assert 'species' in data_payload
        assert 'owner' in data_payload

    def test_respond_visit_reject_sends_only_ack(self, game):
        """respond_visit(accept=False) sends only MSG_VISIT_ACK, no DATA."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        result = game.respond_visit('peer-node-id', False)

        assert result is True
        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_ACK]
        assert len(ack_calls) == 1
        _, _, ack_payload = ack_calls[0]
        assert ack_payload['accept'] is False
        # No DATA should be sent
        data_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_DATA]
        assert len(data_calls) == 0

    def test_respond_visit_when_disabled_returns_false(self, game):
        """respond_visit returns False when LAN not enabled."""
        result = game.respond_visit('peer-1', True)
        assert result is False


# ─── 6. process_lan_queues ──────────────────────────────────────────────────


class TestProcessLanQueues:
    """process_lan_queues polls ui_queue and dispatches messages."""

    def test_process_lan_queues_disabled_returns_early(self, game):
        """process_lan_queues returns immediately when LAN not enabled."""
        # Should not raise even though there's no lan_node
        game.process_lan_queues()

    def test_process_lan_queues_visit_req_sets_pending(self, game):
        """VISIT_REQ message creates pending_visit_request for UI confirmation."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        fake_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {'from': 'peer-1', 'pet_name': 'Buddy'},
        })

        game.process_lan_queues()

        assert game.pending_visit_request is not None
        assert game.pending_visit_request['from'] == 'peer-1'
        assert game.pending_visit_request['pet_name'] == 'Buddy'

    def test_process_lan_queues_visit_ack_rejected_sets_message(self, game):
        """VISIT_ACK with accept=False sets a rejection message."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        fake_node.ui_queue.put({
            'type': MSG_VISIT_ACK,
            'payload': {'accept': False},
        })

        game.process_lan_queues()

        assert game.message is not None
        assert '拒绝' in game.message

    def test_process_lan_queues_visit_data_adds_visitor(self, game):
        """VISIT_DATA message adds the snapshot to visitor_pets."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        snapshot = _make_snapshot(name='NewVisitor', owner='friend-1')
        fake_node.ui_queue.put({
            'type': MSG_VISIT_DATA,
            'payload': snapshot,
        })

        game.process_lan_queues()

        assert len(game.visitor_pets) == 1
        assert game.visitor_pets[0]['name'] == 'NewVisitor'
        assert game.message is not None
        assert '拜访' in game.message

    def test_process_lan_queues_visit_leave_removes_visitor(self, game):
        """VISIT_LEAVE message removes the matching visitor by name."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        # Pre-populate visitors
        game.receive_visitor(_make_snapshot(name='Stays'))
        game.receive_visitor(_make_snapshot(name='Leaves'))

        fake_node.ui_queue.put({
            'type': MSG_VISIT_LEAVE,
            'payload': {'pet_name': 'Leaves'},
        })

        game.process_lan_queues()

        assert len(game.visitor_pets) == 1
        assert game.visitor_pets[0]['name'] == 'Stays'

    def test_process_lan_queues_empty_queue_no_error(self, game):
        """Empty ui_queue does not cause errors."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        # Queue is empty
        game.process_lan_queues()
        # No exception, no state change
        assert game.visitor_pets == []

    def test_process_lan_queues_malformed_message_skipped(self, game):
        """A malformed message is skipped without affecting subsequent messages."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        # Put a malformed message (string instead of dict) then a valid one
        fake_node.ui_queue.put('not-a-dict')
        fake_node.ui_queue.put({
            'type': MSG_VISIT_DATA,
            'payload': _make_snapshot(name='Valid'),
        })

        game.process_lan_queues()

        # The valid message should still be processed
        assert len(game.visitor_pets) == 1
        assert game.visitor_pets[0]['name'] == 'Valid'

    def test_process_lan_queues_multiple_messages(self, game):
        """Multiple messages in queue are all processed in order."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        fake_node.ui_queue.put({
            'type': MSG_VISIT_DATA,
            'payload': _make_snapshot(name='First'),
        })
        fake_node.ui_queue.put({
            'type': MSG_VISIT_DATA,
            'payload': _make_snapshot(name='Second'),
        })

        game.process_lan_queues()

        assert len(game.visitor_pets) == 2
        assert game.visitor_pets[0]['name'] == 'First'
        assert game.visitor_pets[1]['name'] == 'Second'


# ─── 7. Graceful degradation ────────────────────────────────────────────────


class TestGracefulDegradation:
    """Single-player methods work even when LAN fails completely."""

    def test_single_player_methods_work_after_lan_failure(self, game):
        """feed/play/sleep/adopt/switch all work after enable_lan fails."""
        fake_node = _FakeLanNode('alice', game.state)
        fake_node._start_should_succeed = False
        with patch('lan.LanNode', return_value=fake_node):
            result = game.enable_lan('alice')
        assert result is False

        # All single-player methods should still work
        game.state['stats']['HUNGER'] = 50
        msg, _ = game.handle_action('feed')
        assert msg is not None

        game.state['stats']['ENERGY'] = 50
        msg, _ = game.handle_action('play')
        assert msg is not None

        game.state['stats']['ENERGY'] = 50
        msg, _ = game.handle_action('sleep')
        assert msg is not None

        # adopt
        msg = game.adopt_pet()
        assert msg is not None

        # switch (now we have 2 pets)
        msg = game.switch_pet(1)
        assert 'Switched' in msg

    def test_process_lan_queues_after_disable_no_error(self, game):
        """process_lan_queues after disable_lan does not raise."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.disable_lan()

        # Should be a no-op
        game.process_lan_queues()
        assert game.visitor_pets == []

    def test_tick_unaffected_by_lan_state(self, game):
        """tick() works the same regardless of LAN enabled/disabled."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        game.state['stats']['HUNGER'] = 50
        game.state['stats']['ENERGY'] = 50
        game.state['stats']['HAPPY'] = 50
        game.last_tick_time = time.time()

        msg, t = game.tick()
        # tick should still return normally
        assert isinstance(msg, str) or msg is None
