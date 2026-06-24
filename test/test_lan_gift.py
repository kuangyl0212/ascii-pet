#!/usr/bin/env python3
"""TDD tests for LAN item gifting feature.

Covers:
  Task 9: PetGame gifting methods (gift_item, receive_gift,
          confirm_gift_sent, check_gift_timeout)
  Task 10: LanNode gifting message handling (MSG_GIFT_ITEM,
           MSG_GIFT_ACK)

Run: python -m pytest test/test_lan_gift.py -v

All PetGame tests mock LanNode — no real network is started.
All LanNode tests call _handle_decoded_message directly — no sockets bound.
"""

import os
import sys
import time
import queue
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame, MAX_INVENTORY
from ascii_pet.protocol import (
    MSG_GIFT_ITEM,
    MSG_GIFT_ACK,
)
from ascii_pet import lan


# ─── Test helpers ───────────────────────────────────────────────────────────


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-gift-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


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


def _set_inventory(game, items):
    """Replace the game's inventory with the given dict of items."""
    game.pets_data['inventory'] = dict(items)
    game.save()


# ─── Task 9: PetGame.gift_item ──────────────────────────────────────────────


class TestGiftItem:
    """PetGame.gift_item: send items to another player over LAN."""

    def test_gift_item_sends_message_and_sets_active_gift_when_has_enough(self, game):
        """When lan_enabled and inventory has enough items: sends MSG_GIFT_ITEM
        via lan_node.send_to_peer with payload {from, from_username, item_id,
        count}, sets self.active_gift dict, returns True."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        _set_inventory(game, {'apple': 5})

        before = time.time()
        result = game.gift_item('peer-node-id', 'apple', 2)
        after = time.time()

        assert result is True
        # Verify MSG_GIFT_ITEM was sent via lan_node.send_to_peer
        gift_calls = [c for c in fake_node.send_calls if c[1] == MSG_GIFT_ITEM]
        assert len(gift_calls) == 1
        peer_id, msg_type, payload = gift_calls[0]
        assert peer_id == 'peer-node-id'
        assert payload['from'] == fake_node.node_id
        assert payload['from_username'] == 'alice'
        assert payload['item_id'] == 'apple'
        assert payload['count'] == 2
        # active_gift should be set with target/item_id/count/start_time
        assert game.active_gift is not None
        assert game.active_gift['target'] == 'peer-node-id'
        assert game.active_gift['item_id'] == 'apple'
        assert game.active_gift['count'] == 2
        assert before <= game.active_gift['start_time'] <= after

    def test_gift_item_insufficient_items_returns_false_with_message(self, game):
        """When inventory has 2 items but trying to gift 3: returns False,
        message contains 'Not enough items'."""
        _enable_lan_with_fake(game, 'alice')
        _set_inventory(game, {'apple': 2})

        result = game.gift_item('peer-node-id', 'apple', 3)

        assert result is False
        assert game.message is not None
        assert 'Not enough items' in game.message
        # active_gift should not be set
        assert game.active_gift is None

    def test_gift_item_lan_disabled_returns_false(self, game):
        """When lan_enabled is False: returns False."""
        # Disable LAN if auto-enabled
        if game.lan_enabled:
            game.disable_lan()
        _set_inventory(game, {'apple': 5})

        result = game.gift_item('peer-node-id', 'apple', 2)

        assert result is False
        assert game.active_gift is None

    def test_gift_item_already_gifting_returns_false_with_message(self, game):
        """When active_gift already set: returns False, message 'Already gifting'."""
        _enable_lan_with_fake(game, 'alice')
        _set_inventory(game, {'apple': 5})
        # Simulate an ongoing gift
        game.active_gift = {
            'target': 'other-peer',
            'item_id': 'apple',
            'count': 1,
            'start_time': time.time(),
        }

        result = game.gift_item('peer-node-id', 'apple', 1)

        assert result is False
        assert game.message is not None
        assert 'Already gifting' in game.message


# ─── Task 9: PetGame.receive_gift ───────────────────────────────────────────


class TestReceiveGift:
    """PetGame.receive_gift: accept gifted items from another player."""

    def test_receive_gift_adds_items_when_inventory_has_space(self, game):
        """When inventory has space: adds items to inventory, returns
        {"success": True}."""
        _set_inventory(game, {'apple': 3})

        result = game.receive_gift('apple', 2)

        assert result == {"success": True}
        assert game.pets_data['inventory']['apple'] == 5  # 3 + 2

    def test_receive_gift_returns_false_when_inventory_full(self, game):
        """When inventory is full (sum >= MAX_INVENTORY): returns
        {"success": False}, does NOT add items."""
        # Fill inventory to MAX_INVENTORY
        _set_inventory(game, {'apple': MAX_INVENTORY})

        result = game.receive_gift('toy', 1)

        assert result == {"success": False}
        # Inventory should not have changed - still MAX_INVENTORY apples, no toy
        assert game.pets_data['inventory']['apple'] == MAX_INVENTORY
        assert 'toy' not in game.pets_data['inventory']


# ─── Task 9: PetGame.confirm_gift_sent ──────────────────────────────────────


class TestConfirmGiftSent:
    """PetGame.confirm_gift_sent: finalize gift after receiver response."""

    def test_confirm_gift_sent_success_removes_items_and_clears_active_gift(self, game):
        """When success=True: removes the gifted items from inventory (count),
        clears active_gift, saves."""
        _enable_lan_with_fake(game, 'alice')
        _set_inventory(game, {'apple': 5})
        game.active_gift = {
            'target': 'peer-node-id',
            'item_id': 'apple',
            'count': 2,
            'start_time': time.time(),
        }

        result = game.confirm_gift_sent(success=True)

        assert result is True
        # Items should be removed from inventory
        assert game.pets_data['inventory']['apple'] == 3  # 5 - 2
        # active_gift should be cleared
        assert game.active_gift is None

    def test_confirm_gift_sent_failure_does_not_remove_items(self, game):
        """When success=False: does NOT remove items, clears active_gift,
        sets message 'Gift rejected'."""
        _enable_lan_with_fake(game, 'alice')
        _set_inventory(game, {'apple': 5})
        game.active_gift = {
            'target': 'peer-node-id',
            'item_id': 'apple',
            'count': 2,
            'start_time': time.time(),
        }

        result = game.confirm_gift_sent(success=False)

        assert result is True
        # Items should NOT be removed
        assert game.pets_data['inventory']['apple'] == 5
        # active_gift should be cleared
        assert game.active_gift is None
        # Message should mention rejection
        assert game.message is not None
        assert 'Gift rejected' in game.message

    def test_confirm_gift_sent_no_active_gift_returns_false(self, game):
        """When no active_gift: returns False."""
        _enable_lan_with_fake(game, 'alice')
        _set_inventory(game, {'apple': 5})
        # No active_gift set
        assert game.active_gift is None

        result = game.confirm_gift_sent(success=True)

        assert result is False
        # Inventory should be unchanged
        assert game.pets_data['inventory']['apple'] == 5


# ─── Task 9: PetGame.check_gift_timeout ─────────────────────────────────────


class TestCheckGiftTimeout:
    """PetGame.check_gift_timeout: clear stale active_gift after 10 seconds."""

    def test_check_gift_timeout_clears_active_gift_after_10_seconds(self, game):
        """When active_gift start_time is more than 10 seconds ago: clears
        active_gift, returns True."""
        _enable_lan_with_fake(game, 'alice')
        # Set active_gift with start_time 11 seconds in the past
        game.active_gift = {
            'target': 'peer-node-id',
            'item_id': 'apple',
            'count': 1,
            'start_time': time.time() - 11,
        }

        result = game.check_gift_timeout()

        assert result is True
        assert game.active_gift is None
        assert game.message is not None

    def test_check_gift_timeout_does_not_clear_within_10_seconds(self, game):
        """When active_gift start_time is less than 10 seconds ago: does not
        clear, returns False."""
        _enable_lan_with_fake(game, 'alice')
        # Set active_gift with start_time 5 seconds in the past
        game.active_gift = {
            'target': 'peer-node-id',
            'item_id': 'apple',
            'count': 1,
            'start_time': time.time() - 5,
        }

        result = game.check_gift_timeout()

        assert result is False
        assert game.active_gift is not None

    def test_check_gift_timeout_no_active_gift_returns_false(self, game):
        """When no active_gift: returns False."""
        _enable_lan_with_fake(game, 'alice')
        assert game.active_gift is None

        result = game.check_gift_timeout()

        assert result is False

    def test_gift_item_sets_start_time_on_active_gift(self, game):
        """Verify that active_gift has a start_time after gift_item succeeds."""
        _enable_lan_with_fake(game, 'alice')
        _set_inventory(game, {'apple': 5})

        before = time.time()
        game.gift_item('peer-node-id', 'apple', 1)
        after = time.time()

        assert game.active_gift is not None
        assert 'start_time' in game.active_gift
        assert before <= game.active_gift['start_time'] <= after


# ─── Task 10: LanNode gifting message handling ──────────────────────────────


class TestLanNodeGiftMessages:
    """LanNode._handle_decoded_message enqueues gift messages to ui_queue."""

    def test_gift_item_enqueued_to_ui_queue(self):
        """MSG_GIFT_ITEM message is put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        payload = {
            'from': 'peer-1',
            'from_username': 'bob',
            'item_id': 'apple',
            'count': 2,
        }
        node._handle_decoded_message(MSG_GIFT_ITEM, payload)
        msg = node.ui_queue.get_nowait()
        assert msg['type'] == MSG_GIFT_ITEM
        assert msg['payload']['from'] == 'peer-1'
        assert msg['payload']['from_username'] == 'bob'
        assert msg['payload']['item_id'] == 'apple'
        assert msg['payload']['count'] == 2

    def test_gift_ack_enqueued_to_ui_queue(self):
        """MSG_GIFT_ACK message is put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        payload = {
            'from': 'peer-1',
            'success': True,
        }
        node._handle_decoded_message(MSG_GIFT_ACK, payload)
        msg = node.ui_queue.get_nowait()
        assert msg['type'] == MSG_GIFT_ACK
        assert msg['payload']['from'] == 'peer-1'
        assert msg['payload']['success'] is True
