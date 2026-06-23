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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet import core as pet_core
from ascii_pet.core import PetGame
from ascii_pet.protocol import (
    MSG_HELLO, MSG_PEER_LIST, MSG_HEARTBEAT,
    MSG_VISIT_REQ, MSG_VISIT_ACK, MSG_VISIT_DATA,
    MSG_VISIT_LEAVE, MSG_BYE,
    MSG_VISIT_FEED, MSG_VISIT_PLAY, MSG_VISIT_EVENT, MSG_VISIT_END,
    make_pet_snapshot, make_visit_event, VISIT_EVENTS,
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
    """PetGame initializes LAN fields and auto-enables on startup."""

    def test_lan_fields_default_auto_enabled(self, game):
        """After __init__, LAN auto-enables if network available."""
        # LAN should be enabled or disabled depending on network availability
        assert isinstance(game.lan_enabled, bool)
        assert isinstance(game.lan_peers, list)
        assert isinstance(game.visitor_pets, list)

    def test_pending_visit_request_removed(self, game):
        """pending_visit_request field has been removed (replaced by active_visit/being_visited)."""
        assert not hasattr(game, 'pending_visit_request')

    def test_active_visit_default_none(self, game):
        """active_visit starts as None."""
        assert game.active_visit is None

    def test_being_visited_default_none(self, game):
        """being_visited starts as None."""
        assert game.being_visited is None

    def test_visit_event_cooldown_default_zero(self, game):
        """visit_event_cooldown starts at 0."""
        assert game.visit_event_cooldown == 0

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
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            result = game.enable_lan('alice')
        assert result is True
        assert game.lan_enabled is True
        assert game.lan_node is fake_node

    def test_enable_lan_failure_returns_false_no_raise(self, game):
        """enable_lan returns False and does not raise when start() fails."""
        # First disable LAN if auto-enabled
        if game.lan_enabled:
            game.disable_lan()
        fake_node = _FakeLanNode('alice', game.state)
        fake_node._start_should_succeed = False
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
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
        """disable_lan sets lan_enabled=False and clears peers/visitors/visit state."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        # Add some state to verify it gets cleared
        game.lan_peers = [{'node_id': 'peer1'}]
        game.visitor_pets = [_make_snapshot()]
        game.active_visit = {'target': 'peer1', 'start_time': time.time(), 'pet_snapshot': {}}
        game.being_visited = {'from': 'peer2', 'start_time': time.time(), 'pet_snapshot': {}}
        game.visit_event_cooldown = time.time() + 30

        game.disable_lan()

        assert game.lan_enabled is False
        assert game.lan_node is None
        assert game.lan_peers == []
        assert game.visitor_pets == []
        assert game.active_visit is None
        assert game.being_visited is None
        assert game.visit_event_cooldown == 0

    def test_disable_lan_when_not_enabled_no_raise(self, game):
        """disable_lan on a game that never enabled LAN does not raise."""
        game.disable_lan()
        assert game.lan_enabled is False

    def test_disable_lan_calls_stop_on_node(self, game):
        """disable_lan calls stop() on the lan_node."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
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
        """When LAN disabled, returns disabled status with defaults."""
        # Disable LAN if auto-enabled
        if game.lan_enabled:
            game.disable_lan()
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
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
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
        from ascii_pet.core import generate_companion, init_state
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
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
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


# ─── 5. Visit invitations (single-direction) ────────────────────────────────


class TestVisitInvitations:
    """invite_visit single-direction behavior (no ACK confirmation)."""

    def test_invite_visit_when_disabled_returns_false(self, game):
        """invite_visit returns False when LAN not enabled."""
        result = game.invite_visit('peer-1')
        assert result is False

    def test_invite_visit_sends_visit_req_with_snapshot(self, game):
        """invite_visit sends MSG_VISIT_REQ with pet_snapshot directly (no ACK wait)."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        result = game.invite_visit('peer-node-id')

        assert result is True
        # Verify send_to_peer was called with MSG_VISIT_REQ
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_REQ]
        assert len(req_calls) == 1
        peer_id, msg_type, payload = req_calls[0]
        assert peer_id == 'peer-node-id'
        assert 'from' in payload
        assert 'from_username' in payload
        assert 'pet_snapshot' in payload
        # Snapshot should contain pet data
        snap = payload['pet_snapshot']
        assert snap['name'] == game.state['name']
        assert 'species' in snap
        assert 'owner' in snap

    def test_invite_visit_sets_active_visit(self, game):
        """After successful invite_visit, active_visit is set with target/start_time/pet_snapshot."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        before = time.time()
        result = game.invite_visit('peer-node-id')
        after = time.time()

        assert result is True
        assert game.active_visit is not None
        assert game.active_visit['target'] == 'peer-node-id'
        assert before <= game.active_visit['start_time'] <= after
        assert 'pet_snapshot' in game.active_visit

    def test_invite_visit_active_visit_locks_returns_false(self, game):
        """invite_visit returns False when active_visit is already set."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        # Simulate an ongoing visit
        game.active_visit = {'target': 'peer-1', 'start_time': time.time(), 'pet_snapshot': {}}

        result = game.invite_visit('peer-2')

        assert result is False
        # Should not have sent a new VISIT_REQ
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_REQ]
        assert len(req_calls) == 0

    def test_invite_visit_being_visited_locks_returns_false(self, game):
        """invite_visit returns False when being_visited is already set."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        # Simulate being visited
        game.being_visited = {'from': 'peer-1', 'start_time': time.time(), 'pet_snapshot': {}}

        result = game.invite_visit('peer-2')

        assert result is False
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_REQ]
        assert len(req_calls) == 0


# ─── 5b. Receiving visits ──────────────────────────────────────────────────


class TestReceiveVisit:
    """Receiving VISIT_REQ sets being_visited and adds to visitor_pets."""

    def test_visit_req_sets_being_visited(self, game):
        """VISIT_REQ message auto-sets being_visited (no manual confirmation)."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        snapshot = _make_snapshot(name='Buddy', owner='friend-1')
        fake_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-node-id',
                'from_username': 'friend',
                'pet_snapshot': snapshot,
            },
        })

        game.process_lan_queues()

        assert game.being_visited is not None
        assert game.being_visited['from'] == 'peer-node-id'
        assert 'start_time' in game.being_visited
        assert game.being_visited['pet_snapshot']['name'] == 'Buddy'

    def test_visit_req_adds_snapshot_to_visitor_pets(self, game):
        """VISIT_REQ auto-appends the pet snapshot to visitor_pets."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        snapshot = _make_snapshot(name='Buddy', owner='friend-1')
        fake_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-node-id',
                'from_username': 'friend',
                'pet_snapshot': snapshot,
            },
        })

        game.process_lan_queues()

        assert len(game.visitor_pets) == 1
        assert game.visitor_pets[0]['name'] == 'Buddy'

    def test_visit_req_does_not_set_pending_visit_request(self, game):
        """VISIT_REQ must not create pending_visit_request (field removed)."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        snapshot = _make_snapshot(name='Buddy', owner='friend-1')
        fake_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-node-id',
                'from_username': 'friend',
                'pet_snapshot': snapshot,
            },
        })

        game.process_lan_queues()

        assert not hasattr(game, 'pending_visit_request')

    def test_visit_req_sets_message(self, game):
        """VISIT_REQ sets a friendly message about the visitor arriving."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        snapshot = _make_snapshot(name='Buddy', owner='friend-1')
        fake_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-node-id',
                'from_username': 'friend',
                'pet_snapshot': snapshot,
            },
        })

        game.process_lan_queues()

        assert game.message is not None
        assert 'Buddy' in game.message


# ─── 5c. Ending visits ─────────────────────────────────────────────────────


class TestEndVisit:
    """end_visit sends VISIT_END and clears visit state."""

    def test_end_visit_as_initiator_clears_active_visit(self, game):
        """Initiator calling end_visit sends VISIT_END and clears active_visit."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.active_visit = {'target': 'peer-1', 'start_time': time.time(), 'pet_snapshot': {}}

        result = game.end_visit()

        assert result is True
        assert game.active_visit is None
        end_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_END]
        assert len(end_calls) == 1
        peer_id, _, payload = end_calls[0]
        assert peer_id == 'peer-1'

    def test_end_visit_as_receiver_clears_being_visited(self, game):
        """Receiver calling end_visit sends VISIT_END and clears being_visited."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.being_visited = {'from': 'peer-1', 'start_time': time.time(), 'pet_snapshot': _make_snapshot(name='Buddy', owner='peer-1')}
        game.visitor_pets.append(game.being_visited['pet_snapshot'])

        result = game.end_visit()

        assert result is True
        assert game.being_visited is None
        end_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_END]
        assert len(end_calls) == 1
        peer_id, _, payload = end_calls[0]
        assert peer_id == 'peer-1'

    def test_end_visit_no_active_visit_returns_false(self, game):
        """end_visit returns False when there is no active or incoming visit."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        result = game.end_visit()

        assert result is False

    def test_receive_visit_end_clears_active_visit(self, game):
        """Receiving VISIT_END as initiator clears active_visit."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.active_visit = {'target': 'peer-1', 'start_time': time.time(), 'pet_snapshot': {}}

        fake_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual'},
        })

        game.process_lan_queues()

        assert game.active_visit is None

    def test_receive_visit_end_clears_being_visited(self, game):
        """Receiving VISIT_END as receiver clears being_visited and removes visitor."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        snap = _make_snapshot(name='Buddy', owner='peer-1')
        game.being_visited = {'from': 'peer-1', 'start_time': time.time(), 'pet_snapshot': snap}
        game.visitor_pets.append(snap)

        fake_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual'},
        })

        game.process_lan_queues()

        assert game.being_visited is None
        # Visitor should be removed from visitor_pets
        assert len(game.visitor_pets) == 0


# ─── 5d. Remote actions ────────────────────────────────────────────────────


class TestRemoteActions:
    """remote_feed / remote_play send messages to the peer being visited."""

    def test_remote_feed_sends_visit_feed(self, game):
        """remote_feed sends MSG_VISIT_FEED to the visit target."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.active_visit = {'target': 'peer-1', 'start_time': time.time(), 'pet_snapshot': {}}

        result = game.remote_feed()

        assert result is True
        feed_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_FEED]
        assert len(feed_calls) == 1
        peer_id, _, payload = feed_calls[0]
        assert peer_id == 'peer-1'

    def test_remote_play_sends_visit_play(self, game):
        """remote_play sends MSG_VISIT_PLAY to the visit target."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.active_visit = {'target': 'peer-1', 'start_time': time.time(), 'pet_snapshot': {}}

        result = game.remote_play()

        assert result is True
        play_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_PLAY]
        assert len(play_calls) == 1
        peer_id, _, payload = play_calls[0]
        assert peer_id == 'peer-1'

    def test_remote_feed_no_active_visit_returns_false(self, game):
        """remote_feed returns False when there is no active visit."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        result = game.remote_feed()

        assert result is False

    def test_remote_play_no_active_visit_returns_false(self, game):
        """remote_play returns False when there is no active visit."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        result = game.remote_play()

        assert result is False

    def test_receive_visit_feed_executes_local_feed(self, game):
        """Receiving MSG_VISIT_FEED triggers local handle_action('feed')."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        # Ensure feed is not on cooldown and stat is low enough
        game.state['stats']['HUNGER'] = 50
        hunger_before = game.state['stats']['HUNGER']

        fake_node.ui_queue.put({
            'type': MSG_VISIT_FEED,
            'payload': {'from': 'friend'},
        })

        game.process_lan_queues()

        # HUNGER should have increased from local feed
        assert game.state['stats']['HUNGER'] > hunger_before
        assert game.message is not None
        assert 'Remote feed' in game.message or 'fed your pet' in game.message

    def test_receive_visit_play_executes_local_play(self, game):
        """Receiving MSG_VISIT_PLAY triggers local handle_action('play')."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        # Ensure play is not on cooldown and stat is low enough
        game.state['stats']['ENERGY'] = 80
        happy_before = game.state['stats']['HAPPY']

        fake_node.ui_queue.put({
            'type': MSG_VISIT_PLAY,
            'payload': {'from': 'friend'},
        })

        game.process_lan_queues()

        assert game.message is not None
        assert 'Remote play' in game.message or 'played with your pet' in game.message


# ─── 5e. Visit timeout ─────────────────────────────────────────────────────


class TestVisitTimeout:
    """Visits auto-end after 600 seconds (10 minutes)."""

    def test_active_visit_timeout_ends_visit(self, game):
        """active_visit older than 600s is cleared by _tick_visit_timeout."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        # Simulate a visit that started 601 seconds ago
        game.active_visit = {
            'target': 'peer-1',
            'start_time': time.time() - 601,
            'pet_snapshot': {},
        }

        game._tick_visit_timeout()

        assert game.active_visit is None

    def test_being_visited_timeout_ends_visit(self, game):
        """being_visited older than 600s is cleared by _tick_visit_timeout."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.being_visited = {
            'from': 'peer-1',
            'start_time': time.time() - 601,
            'pet_snapshot': {},
        }

        game._tick_visit_timeout()

        assert game.being_visited is None

    def test_active_visit_not_expired_kept(self, game):
        """active_visit younger than 600s is NOT cleared."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.active_visit = {
            'target': 'peer-1',
            'start_time': time.time() - 100,  # only 100s ago
            'pet_snapshot': {},
        }

        game._tick_visit_timeout()

        assert game.active_visit is not None

    def test_tick_calls_visit_timeout_when_lan_enabled(self, game):
        """tick() invokes _tick_visit_timeout when LAN is enabled."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        called = []
        original = game._tick_visit_timeout
        def tracking():
            called.append(True)
            original()
        game._tick_visit_timeout = tracking

        game.state['stats']['HUNGER'] = 50
        game.state['stats']['ENERGY'] = 50
        game.state['stats']['HAPPY'] = 50
        game.last_tick_time = time.time()
        game.tick()

        assert called == [True]


# ─── 5f. Visit random events ───────────────────────────────────────────────


class TestVisitRandomEvents:
    """Random events during visits: 10% chance, 30s cooldown, sends VISIT_EVENT."""

    def test_no_event_without_active_visit(self, game):
        """_tick_visit_events does nothing when no active visit or being_visited."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        with patch('random.random', return_value=0.05):  # would trigger 10%
            game._tick_visit_events()

        # No message set, no send calls
        event_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_EVENT]
        assert len(event_calls) == 0

    def test_event_triggers_with_active_visit(self, game):
        """With active_visit and random<0.10, an event fires and is sent to peer."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.active_visit = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
        }
        game.visit_event_cooldown = 0  # not on cooldown

        with patch('random.random', return_value=0.05), \
             patch('random.choice', return_value=VISIT_EVENTS[0]):
            game._tick_visit_events()

        event_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_EVENT]
        assert len(event_calls) == 1
        peer_id, _, payload = event_calls[0]
        assert peer_id == 'peer-1'
        assert 'description' in payload
        assert 'stat_effects' in payload
        assert game.message is not None
        assert 'Visit event' in game.message

    def test_event_cooldown_blocks_new_event(self, game):
        """When visit_event_cooldown is in the future, no event fires."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.active_visit = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
        }
        # Set cooldown to 30s in the future
        game.visit_event_cooldown = time.time() + 30

        with patch('random.random', return_value=0.05):
            game._tick_visit_events()

        event_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_EVENT]
        assert len(event_calls) == 0

    def test_event_high_random_no_trigger(self, game):
        """With random>=0.10, no event fires."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.active_visit = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
        }
        game.visit_event_cooldown = 0

        with patch('random.random', return_value=0.50):  # >= 0.10
            game._tick_visit_events()

        event_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_EVENT]
        assert len(event_calls) == 0

    def test_event_sets_cooldown(self, game):
        """After an event fires, visit_event_cooldown is set 30s in the future."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.active_visit = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
        }
        game.visit_event_cooldown = 0
        before = time.time()

        with patch('random.random', return_value=0.05), \
             patch('random.choice', return_value=VISIT_EVENTS[0]):
            game._tick_visit_events()

        # Cooldown should be ~30s in the future
        assert game.visit_event_cooldown >= before + 29
        assert game.visit_event_cooldown <= before + 31

    def test_receive_visit_event_applies_effects(self, game):
        """Receiving MSG_VISIT_EVENT applies stat_effects and sets message."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        happy_before = game.state['stats']['HAPPY']

        event = make_visit_event(
            'play_together',
            '两只宠物一起玩耍',
            {'happy': 15, 'energy': -10},
        )
        fake_node.ui_queue.put({
            'type': MSG_VISIT_EVENT,
            'payload': event,
        })

        game.process_lan_queues()

        assert game.state['stats']['HAPPY'] == min(100, happy_before + 15)
        assert game.message is not None
        assert 'Visit event' in game.message
        assert '玩耍' in game.message


# ─── 6. process_lan_queues ──────────────────────────────────────────────────


class TestProcessLanQueues:
    """process_lan_queues polls ui_queue and dispatches messages."""

    def test_process_lan_queues_disabled_returns_early(self, game):
        """process_lan_queues returns immediately when LAN not enabled."""
        # Should not raise even though there's no lan_node
        game.process_lan_queues()

    def test_process_lan_queues_empty_queue_no_error(self, game):
        """Empty ui_queue does not cause errors."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        # Queue is empty
        game.process_lan_queues()
        # No exception, no state change
        assert game.visitor_pets == []

    def test_process_lan_queues_malformed_message_skipped(self, game):
        """A malformed message is skipped without affecting subsequent messages."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        # Put a malformed message (string instead of dict) then a valid one
        fake_node.ui_queue.put('not-a-dict')
        snapshot = _make_snapshot(name='Valid', owner='peer-valid')
        fake_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-valid',
                'from_username': 'valid',
                'pet_snapshot': snapshot,
            },
        })

        game.process_lan_queues()

        # The valid message should still be processed
        assert len(game.visitor_pets) == 1
        assert game.visitor_pets[0]['name'] == 'Valid'

    def test_process_lan_queues_multiple_messages(self, game):
        """Multiple messages in queue are all processed in order."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        fake_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-1',
                'from_username': 'first',
                'pet_snapshot': _make_snapshot(name='First', owner='peer-1'),
            },
        })
        fake_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-2',
                'from_username': 'second',
                'pet_snapshot': _make_snapshot(name='Second', owner='peer-2'),
            },
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
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
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
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.disable_lan()

        # Should be a no-op
        game.process_lan_queues()
        assert game.visitor_pets == []

    def test_tick_unaffected_by_lan_state(self, game):
        """tick() works the same regardless of LAN enabled/disabled."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')

        game.state['stats']['HUNGER'] = 50
        game.state['stats']['ENERGY'] = 50
        game.state['stats']['HAPPY'] = 50
        game.last_tick_time = time.time()

        msg, t = game.tick()
        # tick should still return normally
        assert isinstance(msg, str) or msg is None


# ─── 8. Username management ────────────────────────────────────────────────


class TestGenerateRandomUsername:
    """generate_random_username: module-level function producing Player-XXXX."""

    def test_returns_str(self):
        """Returns a str type."""
        result = pet_core.generate_random_username()
        assert isinstance(result, str)

    def test_format_player_prefix(self):
        """Format is Player-XXXX (Player- prefix + 4 alphanumeric chars)."""
        result = pet_core.generate_random_username()
        assert result.startswith('Player-')
        suffix = result[len('Player-'):]
        assert len(suffix) == 4
        valid_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        assert all(c in valid_chars for c in suffix)

    def test_length_is_11(self):
        """Length is fixed at 11 (Player- 7 chars + 4 chars)."""
        result = pet_core.generate_random_username()
        assert len(result) == 11

    def test_multiple_calls_generate_different_results(self):
        """Multiple calls produce different results (randomness)."""
        results = {pet_core.generate_random_username() for _ in range(20)}
        # With 36^4 possible suffixes, 20 calls should produce >1 unique value
        assert len(results) > 1


class TestEnableLanAutoUsername:
    """enable_lan auto-generates username when None is passed."""

    def test_enable_lan_none_auto_generates_username(self, game):
        """enable_lan(None) auto-generates a random username."""
        fake_node = _FakeLanNode(None, game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            result = game.enable_lan(None)
        assert result is True
        assert game.lan_username is not None
        assert isinstance(game.lan_username, str)
        assert game.lan_username.startswith('Player-')

    def test_enable_lan_none_saves_generated_username(self, game):
        """enable_lan(None) saves the generated username to save data."""
        fake_node = _FakeLanNode(None, game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan(None)
        # Username should be saved in pets_data
        assert game.pets_data.get('username') == game.lan_username

    def test_enable_lan_none_loads_existing_username(self, game):
        """enable_lan(None) loads a previously saved username from save data."""
        game.lan_username = 'saved-user'
        game.pets_data['username'] = 'saved-user'
        fake_node = _FakeLanNode(None, game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan(None)
        assert game.lan_username == 'saved-user'

    def test_enable_lan_with_username_uses_provided(self, game):
        """enable_lan('alice') uses the provided username."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            result = game.enable_lan('alice')
        assert result is True
        assert game.lan_username == 'alice'


class TestChangeLanUsername:
    """change_lan_username: rename with conflict check."""

    def test_change_username_no_conflict_returns_true(self, game):
        """change_lan_username returns True when no peer has the new name."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        # No peers → no conflict
        result = game.change_lan_username('newname')
        assert result is True
        assert game.lan_username == 'newname'

    def test_change_username_conflict_auto_resolves(self, game):
        """change_lan_username auto-resolves conflicts by appending suffix."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        # Simulate a peer with the target name
        fake_node._peers = [{'node_id': 'peer-1', 'username': 'taken', 'pet_summary': {}}]
        result = game.change_lan_username('taken')
        assert result is True
        # Should auto-resolve to taken(2)
        assert game.lan_username == 'taken(2)'

    def test_change_username_updates_lan_node_username(self, game):
        """change_lan_username updates the LanNode's username attribute."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.change_lan_username('newname')
        assert fake_node.username == 'newname'

    def test_change_username_saves_to_pets_data(self, game):
        """change_lan_username persists the new username to save data."""
        fake_node = _FakeLanNode('alice', game.state)
        with patch('ascii_pet.lan.LanNode', return_value=fake_node):
            game.enable_lan('alice')
        game.change_lan_username('newname')
        assert game.pets_data.get('username') == 'newname'

    def test_change_username_when_lan_disabled_returns_false(self, game):
        """change_lan_username returns False when LAN is not enabled."""
        # Disable LAN if auto-enabled
        if game.lan_enabled:
            game.disable_lan()
        result = game.change_lan_username('newname')
        assert result is False
