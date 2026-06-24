#!/usr/bin/env python3
"""TDD tests for LAN pet trading feature.

Covers:
  Task 11: PetGame trading methods (initiate_trade, accept_trade,
           execute_trade, check_trade_timeout)
  Task 12: LanNode trade message handling (MSG_TRADE_REQ,
           MSG_TRADE_ACK, MSG_TRADE_CONFIRM)

Run: python -m pytest test/test_lan_trade.py -v

All PetGame tests mock LanNode — no real network is started.
All LanNode tests call _handle_decoded_message directly — no sockets bound.

For a full pet trade, the FULL pet state dict is sent in the ``pet_snapshot``
field (not just the read-only snapshot), so ALL pet attributes (stats, level,
xp, hp, species, rarity, etc.) migrate to the new owner.
"""

import os
import sys
import time
import queue
from datetime import datetime
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame
from ascii_pet.protocol import (
    MSG_TRADE_REQ,
    MSG_TRADE_ACK,
    MSG_TRADE_CONFIRM,
)
from ascii_pet import lan


# ─── Test helpers ───────────────────────────────────────────────────────────


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-trade-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


@pytest.fixture
def game(tmp_path):
    """Provide a fresh PetGame with isolated temp dir."""
    uid = _uid()
    return PetGame(uid, data_dir=tmp_path)


class _FakeLanNode:
    """Fake LanNode that simulates network behavior without real sockets.

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
        self._status['enabled'] = True
        self._status['is_master'] = True
        return True

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


def _enable_lan_with_fake(game, username='alice'):
    """Enable LAN on game using _FakeLanNode. Returns the fake node."""
    fake_node = _FakeLanNode(username, game.state)
    with patch('ascii_pet.lan.LanNode', return_value=fake_node):
        game.enable_lan(username)
    return fake_node


def _minimal_pet_state():
    """Minimal pet state dict for LanNode testing."""
    return {
        'name': 'TestPet',
        'species': 'cat',
        'rarity': 'common',
        'level': 1,
        'shiny': False,
        'eye': '·',
        'hat': 'none',
        'mood': 'happy',
        'hp': 100,
    }


def _make_full_pet_state(name='TradedPet', species='cat', rarity='rare',
                         level=10, stats=None, xp=500, hp=80,
                         shiny=True, eye='✦', hat='crown'):
    """Build a full pet state dict for trade testing.

    This mirrors the structure produced by ``init_state`` so that all
    gameplay attributes (stats, level, xp, hp, etc.) can be verified to
    migrate across a trade.
    """
    now = datetime.now().isoformat()
    return {
        'user_id': 'original-owner',
        'name': name,
        'species': species,
        'rarity': rarity,
        'eye': eye,
        'hat': hat,
        'shiny': shiny,
        'stats': stats or {'HUNGER': 75, 'HAPPY': 60, 'ENERGY': 90,
                           'WISDOM': 10, 'CHAOS': 5},
        'mood': 'happy',
        'created_at': now,
        'last_fed': now,
        'last_played': now,
        'last_slept': now,
        'level': level,
        'xp': xp,
        'total_interactions': 42,
        'feed_count': 10,
        'play_count': 8,
        'sleep_count': 5,
        'achievements': ['first_pet'],
        'critical_since': None,
        'is_dead': False,
        'last_feed': None,
        'last_play': None,
        'last_sleep': None,
        'pet_count_hour': 0,
        'pet_hour_start': None,
        'hp': hp,
    }


def _make_trade_req(from_id='peer-1', from_username='bob',
                    pet_state=None, pet_index=0):
    """Build a trade_req dict as received over the network."""
    return {
        'from': from_id,
        'from_username': from_username,
        'pet_snapshot': pet_state or _make_full_pet_state(),
        'pet_index': pet_index,
    }


def _make_trade_ack(from_id='peer-1', accepted=True,
                    pet_state=None, pet_index=0):
    """Build a trade_ack dict as received over the network."""
    return {
        'from': from_id,
        'accepted': accepted,
        'pet_snapshot': pet_state or _make_full_pet_state(),
        'pet_index': pet_index,
    }


# ─── Task 11: PetGame.initiate_trade ────────────────────────────────────────


class TestInitiateTrade:
    """PetGame.initiate_trade: send pet trade request to a peer."""

    def test_initiate_trade_sends_trade_req_and_sets_active_trade(self, game):
        """When lan_enabled and valid pet_index: sends MSG_TRADE_REQ with
        payload {from, from_username, pet_snapshot, pet_index}, sets
        active_trade with target/pet_index/start_time, returns True.

        The pet_snapshot must be a FULL pet state (with stats, level, xp, hp,
        etc.) so all attributes migrate to the new owner."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        pet_index = 0

        before = time.time()
        result = game.initiate_trade('peer-node-id', pet_index)
        after = time.time()

        assert result is True
        # Verify MSG_TRADE_REQ was sent via lan_node.send_to_peer
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_REQ]
        assert len(req_calls) == 1
        peer_id, msg_type, payload = req_calls[0]
        assert peer_id == 'peer-node-id'
        assert payload['from'] == fake_node.node_id
        assert payload['from_username'] == 'alice'
        assert 'pet_snapshot' in payload
        assert payload['pet_index'] == pet_index
        # pet_snapshot should be a FULL pet state (with stats, level, xp, etc.)
        snap = payload['pet_snapshot']
        assert 'stats' in snap
        assert 'level' in snap
        assert 'xp' in snap
        assert 'hp' in snap
        assert 'species' in snap
        assert 'rarity' in snap
        # active_trade should be set with target/pet_index/start_time
        assert game.active_trade is not None
        assert game.active_trade['target'] == 'peer-node-id'
        assert game.active_trade['pet_index'] == pet_index
        assert before <= game.active_trade['start_time'] <= after

    def test_initiate_trade_invalid_pet_index_returns_false(self, game):
        """When pet_index is out of range: returns False, no message sent."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        # Only 1 pet by default, so index 5 is invalid
        result = game.initiate_trade('peer-node-id', 5)

        assert result is False
        assert game.active_trade is None
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_REQ]
        assert len(req_calls) == 0

    def test_initiate_trade_lan_disabled_returns_false(self, game):
        """When lan_enabled is False: returns False."""
        # Disable LAN if auto-enabled
        if game.lan_enabled:
            game.disable_lan()

        result = game.initiate_trade('peer-node-id', 0)

        assert result is False
        assert game.active_trade is None

    def test_initiate_trade_already_trading_returns_false_with_message(self, game):
        """When active_trade already set: returns False, message 'Already trading'."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        # Simulate an ongoing trade
        game.active_trade = {
            'target': 'other-peer',
            'pet_index': 0,
            'start_time': time.time(),
            'role': 'initiator',
        }

        result = game.initiate_trade('peer-node-id', 0)

        assert result is False
        assert game.message is not None
        assert 'Already trading' in game.message
        # Should not have sent a new trade request
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_REQ]
        assert len(req_calls) == 0


# ─── Task 11: PetGame.accept_trade ──────────────────────────────────────────


class TestAcceptTrade:
    """PetGame.accept_trade: accept or reject a trade request."""

    def test_accept_trade_accept_sends_ack_with_snapshot_and_sets_active_trade(self, game):
        """When accepting: sends MSG_TRADE_ACK with {from, accepted: True,
        pet_snapshot, pet_index}, sets active_trade, returns True."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        trade_req = _make_trade_req()
        pet_index = 0

        before = time.time()
        result = game.accept_trade(trade_req, pet_index, accepted=True)
        after = time.time()

        assert result is True
        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_ACK]
        assert len(ack_calls) == 1
        peer_id, msg_type, payload = ack_calls[0]
        assert peer_id == 'peer-1'  # trade_req['from']
        assert payload['from'] == fake_node.node_id
        assert payload['accepted'] is True
        assert 'pet_snapshot' in payload
        assert payload['pet_index'] == pet_index
        # pet_snapshot should be a FULL pet state
        snap = payload['pet_snapshot']
        assert 'stats' in snap
        assert 'level' in snap
        # active_trade should be set
        assert game.active_trade is not None
        assert game.active_trade['target'] == 'peer-1'
        assert game.active_trade['pet_index'] == pet_index
        assert before <= game.active_trade['start_time'] <= after

    def test_accept_trade_reject_sends_ack_without_snapshot(self, game):
        """When rejecting: sends MSG_TRADE_ACK with {from, accepted: False},
        returns True, does NOT set active_trade."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        trade_req = _make_trade_req()

        result = game.accept_trade(trade_req, None, accepted=False)

        assert result is True
        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_ACK]
        assert len(ack_calls) == 1
        peer_id, msg_type, payload = ack_calls[0]
        assert payload['from'] == fake_node.node_id
        assert payload['accepted'] is False
        assert 'pet_snapshot' not in payload
        # active_trade should NOT be set when rejecting
        assert game.active_trade is None

    def test_accept_trade_invalid_pet_index_when_accepting_returns_false(self, game):
        """When accepting with invalid pet_index: returns False, no message sent."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        trade_req = _make_trade_req()

        result = game.accept_trade(trade_req, 99, accepted=True)

        assert result is False
        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_ACK]
        assert len(ack_calls) == 0

    def test_accept_trade_lan_disabled_returns_false(self, game):
        """When lan_enabled is False: returns False."""
        if game.lan_enabled:
            game.disable_lan()
        trade_req = _make_trade_req()

        result = game.accept_trade(trade_req, 0, accepted=True)

        assert result is False


# ─── Task 11: PetGame.execute_trade ─────────────────────────────────────────


class TestExecuteTrade:
    """PetGame.execute_trade: replace pet with received pet."""

    def test_execute_trade_as_initiator_replaces_pet_with_received(self, game):
        """As initiator: replaces pets_data['pets'][pet_index] with received
        pet_snapshot, saves, returns True. ALL attributes migrate."""
        _enable_lan_with_fake(game, 'alice')
        pet_index = 0
        game.active_trade = {
            'target': 'peer-1',
            'pet_index': pet_index,
            'start_time': time.time(),
            'role': 'initiator',
        }
        original_pet_count = len(game.pets_data['pets'])
        received_pet = _make_full_pet_state(
            name='NewPet', species='dragon', rarity='epic', level=15,
            stats={'HUNGER': 80, 'HAPPY': 70, 'ENERGY': 60,
                   'WISDOM': 20, 'CHAOS': 10},
            xp=750, hp=90, shiny=True, eye='◉', hat='crown',
        )
        trade_ack = _make_trade_ack(pet_state=received_pet, pet_index=pet_index)

        result = game.execute_trade(trade_ack)

        assert result is True
        # Pet count should stay the same
        assert len(game.pets_data['pets']) == original_pet_count
        # The pet at pet_index should be the received pet with all attributes
        new_pet = game.pets_data['pets'][pet_index]
        assert new_pet['name'] == 'NewPet'
        assert new_pet['species'] == 'dragon'
        assert new_pet['rarity'] == 'epic'
        assert new_pet['level'] == 15
        assert new_pet['xp'] == 750
        assert new_pet['hp'] == 90
        assert new_pet['shiny'] is True
        assert new_pet['eye'] == '◉'
        assert new_pet['hat'] == 'crown'
        assert new_pet['stats']['HUNGER'] == 80
        assert new_pet['stats']['HAPPY'] == 70
        assert new_pet['stats']['ENERGY'] == 60
        assert new_pet['stats']['WISDOM'] == 20
        assert new_pet['stats']['CHAOS'] == 10
        # active_trade should be cleared
        assert game.active_trade is None

    def test_execute_trade_as_receiver_replaces_pet_with_received(self, game):
        """As receiver: same replacement logic as initiator."""
        _enable_lan_with_fake(game, 'alice')
        pet_index = 0
        game.active_trade = {
            'target': 'peer-1',
            'pet_index': pet_index,
            'start_time': time.time(),
            'role': 'receiver',
        }
        received_pet = _make_full_pet_state(name='ReceivedPet', species='octopus')
        trade_ack = _make_trade_ack(pet_state=received_pet, pet_index=pet_index)

        result = game.execute_trade(trade_ack)

        assert result is True
        new_pet = game.pets_data['pets'][pet_index]
        assert new_pet['name'] == 'ReceivedPet'
        assert new_pet['species'] == 'octopus'

    def test_execute_trade_pet_count_stays_same(self, game):
        """After trade, pet count stays the same (no duplicate, no loss)."""
        _enable_lan_with_fake(game, 'alice')
        # Add a second pet so we have 2 pets
        game.pets_data['pets'].append(_make_full_pet_state(name='SecondPet'))
        game.save()
        pet_index = 1
        game.active_trade = {
            'target': 'peer-1',
            'pet_index': pet_index,
            'start_time': time.time(),
            'role': 'initiator',
        }
        original_count = len(game.pets_data['pets'])
        trade_ack = _make_trade_ack(pet_state=_make_full_pet_state(name='Traded'))

        result = game.execute_trade(trade_ack)

        assert result is True
        assert len(game.pets_data['pets']) == original_count

    def test_execute_trade_current_pet_switches_to_new_pet(self, game):
        """If traded pet was the current pet (pet_idx == traded index),
        state and bones switch to the new pet."""
        _enable_lan_with_fake(game, 'alice')
        pet_index = game.pet_idx  # current pet
        game.active_trade = {
            'target': 'peer-1',
            'pet_index': pet_index,
            'start_time': time.time(),
            'role': 'initiator',
        }
        received_pet = _make_full_pet_state(
            name='NewCurrent', species='dragon', rarity='legendary',
            eye='@', hat='crown', shiny=True,
        )
        trade_ack = _make_trade_ack(pet_state=received_pet, pet_index=pet_index)

        result = game.execute_trade(trade_ack)

        assert result is True
        # state should be the new pet
        assert game.state['name'] == 'NewCurrent'
        assert game.state['species'] == 'dragon'
        # bones should be updated to match new pet
        assert game.bones['species'] == 'dragon'
        assert game.bones['rarity'] == 'legendary'
        assert game.bones['eye'] == '@'
        assert game.bones['hat'] == 'crown'
        assert game.bones['shiny'] is True

    def test_execute_trade_no_active_trade_returns_false(self, game):
        """When no active_trade: returns False."""
        _enable_lan_with_fake(game, 'alice')
        assert game.active_trade is None
        trade_ack = _make_trade_ack()

        result = game.execute_trade(trade_ack)

        assert result is False


# ─── Task 11: PetGame.check_trade_timeout ───────────────────────────────────


class TestCheckTradeTimeout:
    """PetGame.check_trade_timeout: clear stale active_trade after 30 seconds."""

    def test_check_trade_timeout_clears_active_trade_after_30_seconds(self, game):
        """When active_trade start_time is more than 30 seconds ago: clears
        active_trade, returns True, sets message."""
        _enable_lan_with_fake(game, 'alice')
        game.active_trade = {
            'target': 'peer-node-id',
            'pet_index': 0,
            'start_time': time.time() - 31,
            'role': 'initiator',
        }

        result = game.check_trade_timeout()

        assert result is True
        assert game.active_trade is None
        assert game.message is not None

    def test_check_trade_timeout_does_not_clear_within_30_seconds(self, game):
        """When active_trade start_time is less than 30 seconds ago: does not
        clear, returns False."""
        _enable_lan_with_fake(game, 'alice')
        game.active_trade = {
            'target': 'peer-node-id',
            'pet_index': 0,
            'start_time': time.time() - 10,
            'role': 'initiator',
        }

        result = game.check_trade_timeout()

        assert result is False
        assert game.active_trade is not None

    def test_check_trade_timeout_no_active_trade_returns_false(self, game):
        """When no active_trade: returns False."""
        _enable_lan_with_fake(game, 'alice')
        assert game.active_trade is None

        result = game.check_trade_timeout()

        assert result is False


# ─── Task 12: LanNode trade message handling ────────────────────────────────


class TestLanNodeTradeMessages:
    """LanNode._handle_decoded_message enqueues trade messages to ui_queue."""

    def test_trade_req_enqueued_to_ui_queue(self):
        """MSG_TRADE_REQ message is put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        payload = {
            'from': 'peer-1',
            'from_username': 'bob',
            'pet_snapshot': {'name': 'BobPet', 'level': 5},
            'pet_index': 0,
        }
        node._handle_decoded_message(MSG_TRADE_REQ, payload)
        msg = node.ui_queue.get_nowait()
        assert msg['type'] == MSG_TRADE_REQ
        assert msg['payload']['from'] == 'peer-1'
        assert msg['payload']['from_username'] == 'bob'
        assert msg['payload']['pet_index'] == 0

    def test_trade_ack_enqueued_to_ui_queue(self):
        """MSG_TRADE_ACK message is put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        payload = {
            'from': 'peer-1',
            'accepted': True,
            'pet_snapshot': {'name': 'BobPet', 'level': 5},
            'pet_index': 0,
        }
        node._handle_decoded_message(MSG_TRADE_ACK, payload)
        msg = node.ui_queue.get_nowait()
        assert msg['type'] == MSG_TRADE_ACK
        assert msg['payload']['accepted'] is True
        assert msg['payload']['pet_index'] == 0

    def test_trade_confirm_enqueued_to_ui_queue(self):
        """MSG_TRADE_CONFIRM message is put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        payload = {
            'from': 'peer-1',
            'confirmed': True,
        }
        node._handle_decoded_message(MSG_TRADE_CONFIRM, payload)
        msg = node.ui_queue.get_nowait()
        assert msg['type'] == MSG_TRADE_CONFIRM
        assert msg['payload']['from'] == 'peer-1'
        assert msg['payload']['confirmed'] is True
