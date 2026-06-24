#!/usr/bin/env python3
"""End-to-end integration tests for LAN challenge/gift/trade features.

Simulates TWO PetGame instances interacting via mocked LanNode. Instead of
real networking, directly call the receiver's ``_handle_lan_message`` with
the message that the sender would have sent.

Covers:
  Test 1: Challenge end-to-end flow (attacker wins)
  Test 2: Challenge escape flow (defender escapes)
  Test 3: Gift end-to-end flow (success)
  Test 4: Gift rejected (inventory full)
  Test 5: Trade end-to-end flow (success, both swap pets)
  Test 6: Trade rejected

Run: python -m pytest test/test_integration.py -v

All tests mock LanNode — no real network is started.
"""

import os
import sys
import time
import queue
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame, MAX_INVENTORY, init_state, generate_companion
from ascii_pet.protocol import (
    MSG_CHALLENGE_REQ,
    MSG_CHALLENGE_ACK,
    MSG_CHALLENGE_RESULT,
    MSG_GIFT_ITEM,
    MSG_GIFT_ACK,
    MSG_TRADE_REQ,
    MSG_TRADE_ACK,
    MSG_TRADE_CONFIRM,
)


# ─── Test helpers ───────────────────────────────────────────────────────────


def _uid(prefix='int'):
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-{prefix}-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


class _FakeLanNode:
    """Fake LanNode that captures sent messages without real sockets.

    - ui_queue is a real queue.Queue (unused in e2e tests)
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


def _make_game(tmp_path, username):
    """Create a PetGame with fake LAN enabled. Returns the game instance."""
    uid = _uid(username)
    data_dir = tmp_path / username
    data_dir.mkdir(parents=True, exist_ok=True)
    game = PetGame(uid, data_dir=data_dir)
    fake_node = _FakeLanNode(username, game.state)
    with patch('ascii_pet.lan.LanNode', return_value=fake_node):
        game.enable_lan(username)
    game.state['hp'] = 100
    game.state['is_dead'] = False
    return game


def _last_payload(fake_node, msg_type):
    """Get the payload of the last sent message of the given type, or None."""
    for peer_id, mtype, payload in reversed(fake_node.send_calls):
        if mtype == msg_type:
            return payload
    return None


def _deliver(sender, receiver, msg_type):
    """Deliver the last message of msg_type from sender to receiver.

    Captures the payload from sender.lan_node.send_calls and calls
    receiver._handle_lan_message directly (no real networking).
    """
    payload = _last_payload(sender.lan_node, msg_type)
    assert payload is not None, f'No {msg_type} message was sent by sender'
    receiver._handle_lan_message({'type': msg_type, 'payload': payload})


def _set_inventory(game, items):
    """Replace the game's inventory with the given dict of items."""
    game.pets_data['inventory'] = dict(items)
    game.save()


def _add_second_pet(game, name='SecondPet'):
    """Add a second pet to the game for trade testing."""
    uid2 = game.uid + '-pet2'
    bones = generate_companion(uid2)
    pet = init_state(uid2, bones, name)
    game.pets_data['pets'].append(pet)
    game.save()


# ─── Test 1: Challenge end-to-end (attacker wins) ──────────────────────────


def test_challenge_e2e_attacker_wins(tmp_path):
    """Simulate full challenge flow: attacker initiates, defender accepts,
    battle runs, both update HP."""
    attacker = _make_game(tmp_path, 'alice')
    defender = _make_game(tmp_path, 'bob')

    attacker_hp_before = attacker.state['hp']
    defender_hp_before = defender.state['hp']

    # 1. Attacker initiates challenge
    assert attacker.initiate_challenge(defender.lan_node.node_id) is True
    assert attacker.active_challenge is not None
    assert attacker.active_challenge['role'] == 'attacker'

    # 2. Defender receives CHALLENGE_REQ -> accept_challenge (escape fails)
    #    -> sends CHALLENGE_ACK with defender_snapshot
    with patch('random.random', return_value=1.0):  # 1.0 >= max escape_chance 0.7 -> escape fails
        _deliver(attacker, defender, MSG_CHALLENGE_REQ)
    assert defender.active_challenge is not None
    assert defender.active_challenge['role'] == 'defender'

    # 3. Attacker receives CHALLENGE_ACK -> runs battle -> sends CHALLENGE_RESULT
    #    -> applies result locally
    def fake_battle(att, defe, seed):
        return {
            'winner': att.get('name', ''),
            'loser': defe.get('name', ''),
            'log': ['Attacker won the battle!'],
            'hp_loss_winner': 10,
            'hp_loss_loser': 25,
        }

    with patch('ascii_pet.battle.simulate_battle', side_effect=fake_battle):
        _deliver(defender, attacker, MSG_CHALLENGE_ACK)

    # 4. Defender receives CHALLENGE_RESULT -> applies result
    _deliver(attacker, defender, MSG_CHALLENGE_RESULT)

    # Verify: both pets' hp decreased
    assert attacker.state['hp'] < attacker_hp_before, 'attacker hp should have decreased'
    assert defender.state['hp'] < defender_hp_before, 'defender hp should have decreased'
    # Verify: active_challenge cleared on both sides
    assert attacker.active_challenge is None
    assert defender.active_challenge is None


# ─── Test 2: Challenge escape flow ──────────────────────────────────────────


def test_challenge_e2e_defender_escapes(tmp_path):
    """Defender escapes the challenge."""
    attacker = _make_game(tmp_path, 'alice')
    defender = _make_game(tmp_path, 'bob')

    attacker_hp_before = attacker.state['hp']
    defender_hp_before = defender.state['hp']

    # 1. Attacker initiates challenge
    assert attacker.initiate_challenge(defender.lan_node.node_id) is True
    assert attacker.active_challenge is not None

    # 2. Defender receives CHALLENGE_REQ -> escapes (random.random < escape_chance)
    #    -> sends CHALLENGE_ACK with escaped=True
    with patch('random.random', return_value=0.0):  # 0.0 < min escape_chance 0.1 -> escape succeeds
        _deliver(attacker, defender, MSG_CHALLENGE_REQ)
    # Defender should NOT have active_challenge (escaped)
    assert defender.active_challenge is None

    # 3. Attacker receives CHALLENGE_ACK(escaped=True) -> clears active_challenge
    _deliver(defender, attacker, MSG_CHALLENGE_ACK)

    # Verify: no HP changes
    assert attacker.state['hp'] == attacker_hp_before
    assert defender.state['hp'] == defender_hp_before
    # Verify: active_challenge cleared on both sides
    assert attacker.active_challenge is None
    assert defender.active_challenge is None


# ─── Test 3: Gift end-to-end success ────────────────────────────────────────


def test_gift_e2e_success(tmp_path):
    """Full gift flow: sender gifts, receiver accepts, sender confirms."""
    sender = _make_game(tmp_path, 'alice')
    receiver = _make_game(tmp_path, 'bob')

    # 1. Sender has apple x2, receiver has empty inventory
    _set_inventory(sender, {'apple': 2})
    _set_inventory(receiver, {})

    # 2. Sender gifts apple x1
    assert sender.gift_item(receiver.lan_node.node_id, 'apple', 1) is True
    assert sender.active_gift is not None

    # 3. Receiver receives GIFT_ITEM -> receive_gift -> sends GIFT_ACK(success=True)
    _deliver(sender, receiver, MSG_GIFT_ITEM)

    # 4. Sender receives GIFT_ACK -> confirm_gift_sent(True) -> removes item
    _deliver(receiver, sender, MSG_GIFT_ACK)

    # Verify: sender has apple x1, receiver has apple x1
    assert sender.pets_data['inventory'].get('apple', 0) == 1
    assert receiver.pets_data['inventory'].get('apple', 0) == 1
    # Verify: active_gift cleared
    assert sender.active_gift is None


# ─── Test 4: Gift rejected (inventory full) ─────────────────────────────────


def test_gift_e2e_inventory_full(tmp_path):
    """Gift fails when receiver inventory is full."""
    sender = _make_game(tmp_path, 'alice')
    receiver = _make_game(tmp_path, 'bob')

    # 1. Receiver inventory is full (MAX_INVENTORY items)
    _set_inventory(sender, {'apple': 1})
    _set_inventory(receiver, {'apple': MAX_INVENTORY})

    # 2. Sender gifts apple
    assert sender.gift_item(receiver.lan_node.node_id, 'apple', 1) is True

    # 3. Receiver receives GIFT_ITEM -> receive_gift fails (inventory full)
    #    -> sends GIFT_ACK(success=False)
    _deliver(sender, receiver, MSG_GIFT_ITEM)

    # 4. Sender receives GIFT_ACK(success=False) -> confirm_gift_sent(False)
    _deliver(receiver, sender, MSG_GIFT_ACK)

    # Verify: sender still has apple, receiver inventory unchanged
    assert sender.pets_data['inventory'].get('apple', 0) == 1
    assert receiver.pets_data['inventory'].get('apple', 0) == MAX_INVENTORY
    # Verify: active_gift cleared
    assert sender.active_gift is None


# ─── Test 5: Trade end-to-end success ───────────────────────────────────────


def test_trade_e2e_success(tmp_path):
    """Full trade flow: initiator trades, receiver accepts, both swap pets."""
    initiator = _make_game(tmp_path, 'alice')
    receiver = _make_game(tmp_path, 'bob')

    # 1. Both have 2 pets with distinct names
    initiator.state['name'] = 'InitiatorPet'
    _add_second_pet(initiator, 'InitiatorSecond')
    receiver.state['name'] = 'ReceiverPet'
    _add_second_pet(receiver, 'ReceiverSecond')

    initiator_count = len(initiator.pets_data['pets'])
    receiver_count = len(receiver.pets_data['pets'])
    assert initiator_count == 2
    assert receiver_count == 2

    # 2. Initiator calls initiate_trade(receiver, 0) — trades pet 0
    assert initiator.initiate_trade(receiver.lan_node.node_id, 0) is True
    assert initiator.active_trade is not None
    assert initiator.active_trade['role'] == 'initiator'

    # 3. Receiver receives TRADE_REQ -> sets pending_trade_req
    _deliver(initiator, receiver, MSG_TRADE_REQ)
    assert receiver.pending_trade_req is not None

    # 4. Receiver calls accept_trade(trade_req, 0, accepted=True) — trades pet 0
    trade_req = receiver.pending_trade_req
    assert receiver.accept_trade(trade_req, 0, accepted=True) is True
    assert receiver.active_trade is not None
    assert receiver.active_trade['role'] == 'receiver'

    # 5. Initiator receives TRADE_ACK(accepted=True) -> sends TRADE_CONFIRM
    #    -> execute_trade (initiator's pet 0 replaced with receiver's pet)
    _deliver(receiver, initiator, MSG_TRADE_ACK)

    # 6. Receiver receives TRADE_CONFIRM -> execute_trade (receiver's pet 0
    #    replaced with initiator's pet)
    _deliver(initiator, receiver, MSG_TRADE_CONFIRM)

    # Verify: both swapped pets (pet 0)
    assert initiator.pets_data['pets'][0]['name'] == 'ReceiverPet'
    assert receiver.pets_data['pets'][0]['name'] == 'InitiatorPet'
    # Verify: pet counts unchanged
    assert len(initiator.pets_data['pets']) == initiator_count
    assert len(receiver.pets_data['pets']) == receiver_count
    # Verify: pet 1 unchanged
    assert initiator.pets_data['pets'][1]['name'] == 'InitiatorSecond'
    assert receiver.pets_data['pets'][1]['name'] == 'ReceiverSecond'
    # Verify: active_trade cleared on both sides
    assert initiator.active_trade is None
    assert receiver.active_trade is None


# ─── Test 6: Trade rejected ─────────────────────────────────────────────────


def test_trade_e2e_rejected(tmp_path):
    """Receiver rejects the trade."""
    initiator = _make_game(tmp_path, 'alice')
    receiver = _make_game(tmp_path, 'bob')

    initiator.state['name'] = 'InitiatorPet'
    receiver.state['name'] = 'ReceiverPet'

    initiator_pet_before = initiator.pets_data['pets'][0]['name']
    receiver_pet_before = receiver.pets_data['pets'][0]['name']

    # 1. Initiator initiates trade
    assert initiator.initiate_trade(receiver.lan_node.node_id, 0) is True
    assert initiator.active_trade is not None

    # 2. Receiver receives TRADE_REQ -> sets pending_trade_req
    _deliver(initiator, receiver, MSG_TRADE_REQ)
    assert receiver.pending_trade_req is not None

    # 3. Receiver rejects trade -> sends TRADE_ACK(accepted=False)
    trade_req = receiver.pending_trade_req
    assert receiver.accept_trade(trade_req, None, accepted=False) is True
    # Receiver should NOT have active_trade (rejected)
    assert receiver.active_trade is None

    # 4. Initiator receives TRADE_ACK(accepted=False) -> clears active_trade
    _deliver(receiver, initiator, MSG_TRADE_ACK)

    # Verify: no pet changes
    assert initiator.pets_data['pets'][0]['name'] == initiator_pet_before
    assert receiver.pets_data['pets'][0]['name'] == receiver_pet_before
    # Verify: active_trade cleared on initiator
    assert initiator.active_trade is None
