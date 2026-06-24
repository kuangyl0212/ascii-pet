#!/usr/bin/env python3
"""TDD tests for challenge flow fixes: from field, timeout, mutual lock.

Root cause: CHALLENGE_ACK/GIFT_ACK/TRADE_CONFIRM payloads lack 'from' field,
so the sender can't reply. This causes battle results to never appear.

Also: no challenge timeout, and defender can still initiate challenges.

Run: python -m pytest test/test_challenge_flow_fix.py -v
"""

import os
import sys
import time
import queue
from unittest.mock import patch, MagicMock
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame
from ascii_pet.protocol import (
    MSG_CHALLENGE_REQ,
    MSG_CHALLENGE_ACK,
    MSG_CHALLENGE_RESULT,
    MSG_GIFT_ITEM,
    MSG_GIFT_ACK,
    MSG_TRADE_REQ,
    MSG_TRADE_ACK,
    MSG_TRADE_CONFIRM,
    make_battle_snapshot,
)


def _uid():
    return f'test-cff-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


@pytest.fixture
def game(tmp_path):
    uid = _uid()
    return PetGame(uid, data_dir=tmp_path)


class _FakeLanNode:
    """Fake LanNode that tracks sent messages and simulates incoming messages."""

    def __init__(self, username, pet_state, node_id='fake-node-alice'):
        self.username = username
        self.pet_state = pet_state
        self.node_id = node_id
        self.udp_port = 50007
        self.tcp_port = 50008
        self.ui_queue = queue.Queue()
        self.net_queue = queue.Queue()
        self._status = {
            'enabled': False,
            'is_master': False,
            'peer_count': 0,
            'error': None,
            'node_id': self.node_id,
        }
        self._peers = [
            {
                'node_id': 'peer-bob',
                'username': 'Bob',
                'pet_summary': {'name': 'BobPet', 'species': 'cat'},
            },
        ]
        self.send_calls = []

    def start(self):
        self._status['enabled'] = True
        self._status['is_master'] = True
        self._status['peer_count'] = len(self._peers)
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

    def inject_message(self, msg_type, payload):
        """Simulate receiving a message from the network."""
        self.ui_queue.put({"type": msg_type, "payload": payload})


def _enable_lan_with_fake(game, username='alice', node_id='fake-node-alice'):
    fake_node = _FakeLanNode(username, game.state, node_id)
    with patch('ascii_pet.lan.LanNode', return_value=fake_node):
        game.enable_lan(username)
    return fake_node


def _make_challenge_req(from_id='peer-bob', from_username='Bob', pet_state=None):
    """Create a CHALLENGE_REQ payload as if sent by a peer."""
    if pet_state is None:
        pet_state = {'name': 'BobPet', 'species': 'cat', 'level': 5,
                     'hp': 100, 'attack': 10, 'defense': 10, 'speed': 10,
                     'rarity': 'common'}
    snapshot = make_battle_snapshot(pet_state, from_username)
    return {
        "from": from_id,
        "from_username": from_username,
        "pet_snapshot": snapshot,
    }


def _make_snapshot(name='BobPet', species='cat', level=5, username='Bob'):
    """Create a battle snapshot with all required fields."""
    return make_battle_snapshot(
        {'name': name, 'species': species, 'level': level,
         'hp': 100, 'attack': 10, 'defense': 10, 'speed': 10,
         'rarity': 'common'},
        username
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test 1: CHALLENGE_ACK must include 'from' field
# ═══════════════════════════════════════════════════════════════════════════


class TestChallengeAckFromField:
    """When defender sends CHALLENGE_ACK, it must include 'from' field
    so the attacker can reply with CHALLENGE_RESULT."""

    def test_challenge_ack_includes_from_field(self, game):
        """Defender's CHALLENGE_ACK should include 'from' field with node_id."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'

        # Simulate receiving CHALLENGE_REQ from Bob
        req = _make_challenge_req()
        with patch('ascii_pet.core.random.random', return_value=1.0):
            fake_node.inject_message(MSG_CHALLENGE_REQ, req)
            game.process_lan_queues()

        # Find the CHALLENGE_ACK that was sent
        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_CHALLENGE_ACK]
        assert len(ack_calls) == 1
        target_id, msg_type, payload = ack_calls[0]
        # The ACK should be sent back to the challenger
        assert target_id == 'peer-bob'
        # CRITICAL: payload must include 'from' field
        assert 'from' in payload, "CHALLENGE_ACK payload missing 'from' field!"
        assert payload['from'] == fake_node.node_id

    def test_challenge_escaped_ack_includes_from_field(self, game):
        """Even escaped CHALLENGE_ACK should include 'from' field."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.state['hp'] = 10  # Low HP triggers escape

        req = _make_challenge_req()
        fake_node.inject_message(MSG_CHALLENGE_REQ, req)
        game.process_lan_queues()

        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_CHALLENGE_ACK]
        assert len(ack_calls) == 1
        _, _, payload = ack_calls[0]
        assert 'from' in payload, "Escaped CHALLENGE_ACK also needs 'from' field!"


# ═══════════════════════════════════════════════════════════════════════════
# Test 2: Full challenge flow end-to-end (attacker perspective)
# ═══════════════════════════════════════════════════════════════════════════


class TestChallengeFlowEndToEnd:
    """Test the complete challenge flow from initiation to result display."""

    def test_attacker_sees_battle_result_after_ack(self, game):
        """After attacker receives CHALLENGE_ACK, battle_result should be set."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.state['hp'] = 100

        # Step 1: Attacker initiates challenge
        game.handle_key('c')
        game.handle_key('1')
        assert game.active_challenge is not None
        assert game.active_challenge['role'] == 'attacker'

        # Step 2: Simulate receiving CHALLENGE_ACK from defender
        # The ACK should come with 'from' field (this is what we're fixing)
        ack_payload = {
            "from": "peer-bob",
            "escaped": False,
            "defender_snapshot": _make_snapshot('BobPet', 'cat', 5, 'Bob'),
        }
        fake_node.inject_message(MSG_CHALLENGE_ACK, ack_payload)
        game.process_lan_queues()

        # Step 3: Attacker should now have battle_result
        assert game.battle_result is not None, "Attacker should see battle result!"
        assert 'winner' in game.battle_result
        assert 'loser' in game.battle_result
        assert 'log' in game.battle_result

        # Step 4: CHALLENGE_RESULT should have been sent to defender
        result_calls = [c for c in fake_node.send_calls if c[1] == MSG_CHALLENGE_RESULT]
        assert len(result_calls) == 1, "CHALLENGE_RESULT should be sent to defender!"
        # The target should be 'peer-bob', not empty string
        assert result_calls[0][0] == 'peer-bob', \
            f"CHALLENGE_RESULT target should be 'peer-bob', got '{result_calls[0][0]}'"

    def test_defender_sees_battle_result(self, game):
        """After defender receives CHALLENGE_RESULT, battle_result should be set."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.state['hp'] = 100

        # Step 1: Defender receives CHALLENGE_REQ
        req = _make_challenge_req()
        # Mock random to ensure no escape
        with patch('ascii_pet.core.random.random', return_value=1.0):
            fake_node.inject_message(MSG_CHALLENGE_REQ, req)
            game.process_lan_queues()
        assert game.active_challenge is not None
        assert game.active_challenge['role'] == 'defender'

        # Step 2: Defender receives CHALLENGE_RESULT
        result_payload = {
            "from": "peer-bob",
            "winner": "defender",
            "log": ["BobPet attacks for 10 damage"],
            "hp_loss_winner": 5,
            "hp_loss_loser": 25,
            "attacker_snapshot": _make_snapshot('BobPet', 'cat', 5, 'Bob'),
            "defender_snapshot": _make_snapshot(game.state.get('name', 'Pet'), game.state.get('species', 'cat'), game.state.get('level', 1), 'alice'),
            "seed": 12345,
        }
        fake_node.inject_message(MSG_CHALLENGE_RESULT, result_payload)
        game.process_lan_queues()

        # Step 3: Defender should have battle_result
        assert game.battle_result is not None, "Defender should see battle result!"


# ═══════════════════════════════════════════════════════════════════════════
# Test 3: Challenge timeout
# ═══════════════════════════════════════════════════════════════════════════


class TestChallengeTimeout:
    """Challenges should time out after a reasonable period."""

    def test_challenge_timeout_exists(self, game):
        """PetGame should have a CHALLENGE_TIMEOUT attribute."""
        assert hasattr(game, 'CHALLENGE_TIMEOUT')

    def test_stale_challenge_cleared_on_tick(self, game):
        """A challenge older than CHALLENGE_TIMEOUT should be cleared on tick."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.state['hp'] = 100

        # Initiate a challenge
        game.handle_key('c')
        game.handle_key('1')
        assert game.active_challenge is not None

        # Simulate time passing beyond timeout
        game.active_challenge['start_time'] = time.time() - game.CHALLENGE_TIMEOUT - 1

        # Tick should clear the stale challenge
        game.tick()
        assert game.active_challenge is None
        assert 'timed out' in game.message.lower() or '超时' in game.message


# ═══════════════════════════════════════════════════════════════════════════
# Test 4: Mutual challenge lock
# ═══════════════════════════════════════════════════════════════════════════


class TestMutualChallengeLock:
    """Both attacker and defender should be locked during a challenge."""

    def test_defender_cannot_initiate_challenge(self, game):
        """When defender has active_challenge, pressing 'c' should be blocked."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.state['hp'] = 100

        # Receive a challenge
        req = _make_challenge_req()
        with patch('ascii_pet.core.random.random', return_value=1.0):
            fake_node.inject_message(MSG_CHALLENGE_REQ, req)
            game.process_lan_queues()
        assert game.active_challenge is not None
        assert game.active_challenge['role'] == 'defender'

        # Try to initiate own challenge
        game.handle_key('c')
        assert 'Already' in game.message or '已经在' in game.message or 'already' in game.message.lower()

    def test_defender_cannot_gift_during_challenge(self, game):
        """When defender has active_challenge, pressing 'g' should be blocked."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.state['hp'] = 100

        req = _make_challenge_req()
        with patch('ascii_pet.core.random.random', return_value=1.0):
            fake_node.inject_message(MSG_CHALLENGE_REQ, req)
            game.process_lan_queues()

        game.handle_key('g')
        assert 'challenge' in game.message.lower() or '挑战' in game.message

    def test_defender_cannot_trade_during_challenge(self, game):
        """When defender has active_challenge, pressing 't' should be blocked."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.state['hp'] = 100

        req = _make_challenge_req()
        with patch('ascii_pet.core.random.random', return_value=1.0):
            fake_node.inject_message(MSG_CHALLENGE_REQ, req)
            game.process_lan_queues()

        game.handle_key('t')
        assert 'challenge' in game.message.lower() or '挑战' in game.message


# ═══════════════════════════════════════════════════════════════════════════
# Test 5: GIFT_ACK and TRADE_CONFIRM also need 'from' field
# ═══════════════════════════════════════════════════════════════════════════


class TestGiftAckFromField:
    """GIFT_ACK should include 'from' field."""

    def test_gift_ack_includes_from_field(self, game):
        """When receiver sends GIFT_ACK, it should include 'from' field."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'

        # Simulate receiving GIFT_ITEM
        gift_payload = {
            "from": "peer-bob",
            "from_username": "Bob",
            "item_id": "apple",
            "item_name": "Apple",
            "quantity": 1,
        }
        fake_node.inject_message(MSG_GIFT_ITEM, gift_payload)
        game.process_lan_queues()

        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_GIFT_ACK]
        assert len(ack_calls) == 1
        _, _, payload = ack_calls[0]
        assert 'from' in payload, "GIFT_ACK payload missing 'from' field!"
