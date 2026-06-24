#!/usr/bin/env python3
"""TDD tests for LAN challenge (battle) feature.

Covers:
  Task 7: PetGame challenge methods (initiate_challenge, accept_challenge,
          apply_battle_result)
  Task 8: LanNode challenge message handling (MSG_CHALLENGE_REQ,
          MSG_CHALLENGE_ACK, MSG_CHALLENGE_RESULT)

Run: python -m pytest test/test_lan_challenge.py -v

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

from ascii_pet.core import PetGame
from ascii_pet.protocol import (
    MSG_CHALLENGE_REQ,
    MSG_CHALLENGE_ACK,
    MSG_CHALLENGE_RESULT,
    make_battle_snapshot,
)
from ascii_pet import lan
from ascii_pet import battle


# ─── Test helpers ───────────────────────────────────────────────────────────


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-challenge-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


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


def _make_challenge_req(from_id='peer-1', from_username='bob', level=5):
    """Build a minimal challenge_req dict as received over the network."""
    return {
        'from': from_id,
        'from_username': from_username,
        'pet_snapshot': {
            'name': 'BobPet',
            'species': 'cat',
            'rarity': 'common',
            'level': level,
            'shiny': False,
            'owner': from_username,
            'hp': 100,
            'attack': 20,
            'defense': 15,
            'speed': 10,
            'skills': ['tackle', 'scratch'],
        },
    }


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


# ─── Task 7: PetGame.initiate_challenge ─────────────────────────────────────


class TestInitiateChallenge:
    """PetGame.initiate_challenge: send battle challenge to a peer."""

    def test_initiate_challenge_sends_challenge_req_and_sets_active_challenge(self, game):
        """When lan_enabled, hp>=25, not dead: sends MSG_CHALLENGE_REQ,
        sets active_challenge with target/start_time/pet_snapshot, returns True."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        # Ensure pet is healthy enough to challenge
        game.state['hp'] = 100
        game.state['is_dead'] = False

        before = time.time()
        result = game.initiate_challenge('peer-node-id')
        after = time.time()

        assert result is True
        # Verify MSG_CHALLENGE_REQ was sent via lan_node.send_to_peer
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_CHALLENGE_REQ]
        assert len(req_calls) == 1
        peer_id, msg_type, payload = req_calls[0]
        assert peer_id == 'peer-node-id'
        assert 'from' in payload
        assert 'from_username' in payload
        assert 'pet_snapshot' in payload
        # active_challenge should be set with target/start_time/pet_snapshot
        assert game.active_challenge is not None
        assert game.active_challenge['target'] == 'peer-node-id'
        assert before <= game.active_challenge['start_time'] <= after
        assert 'pet_snapshot' in game.active_challenge

    def test_initiate_challenge_hp_below_25_returns_false_with_message(self, game):
        """When pet hp < 25: returns False, sets message about low HP."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 24
        game.state['is_dead'] = False

        result = game.initiate_challenge('peer-node-id')

        assert result is False
        assert game.message is not None
        assert 'HP' in game.message or 'low' in game.message.lower()
        # Should not have sent any challenge request
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_CHALLENGE_REQ]
        assert len(req_calls) == 0
        # active_challenge should not be set
        assert game.active_challenge is None

    def test_initiate_challenge_dead_pet_returns_false_with_message(self, game):
        """When pet is_dead: returns False, sets message about dead pet."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.state['is_dead'] = True

        result = game.initiate_challenge('peer-node-id')

        assert result is False
        assert game.message is not None
        assert 'dead' in game.message.lower() or 'Dead' in game.message
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_CHALLENGE_REQ]
        assert len(req_calls) == 0
        assert game.active_challenge is None

    def test_initiate_challenge_lan_disabled_returns_false(self, game):
        """When lan_enabled is False: returns False."""
        # Disable LAN if auto-enabled
        if game.lan_enabled:
            game.disable_lan()
        game.state['hp'] = 100
        game.state['is_dead'] = False

        result = game.initiate_challenge('peer-node-id')

        assert result is False
        assert game.active_challenge is None

    def test_initiate_challenge_already_in_challenge_returns_false(self, game):
        """When active_challenge already set: returns False, message 'Already in a challenge'."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        # Simulate an ongoing challenge
        game.active_challenge = {
            'target': 'other-peer',
            'start_time': time.time(),
            'pet_snapshot': {},
            'role': 'attacker',
        }

        result = game.initiate_challenge('peer-node-id')

        assert result is False
        assert game.message is not None
        assert 'Already' in game.message
        # Should not have sent a new challenge request
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_CHALLENGE_REQ]
        assert len(req_calls) == 0


# ─── Task 7: PetGame.accept_challenge ───────────────────────────────────────


class TestAcceptChallenge:
    """PetGame.accept_challenge: accept or escape from an incoming challenge."""

    def test_accept_challenge_low_hp_returns_escaped_low_hp(self, game):
        """When defender hp < 25: returns {'escaped': True, 'reason': 'low_hp'}."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 24
        game.state['is_dead'] = False
        challenge_req = _make_challenge_req()

        result = game.accept_challenge(challenge_req)

        assert result == {'escaped': True, 'reason': 'low_hp'}

    def test_accept_challenge_dead_pet_returns_escaped_dead(self, game):
        """When defender is_dead: returns {'escaped': True, 'reason': 'dead'}."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.state['is_dead'] = True
        challenge_req = _make_challenge_req()

        result = game.accept_challenge(challenge_req)

        assert result == {'escaped': True, 'reason': 'dead'}

    def test_accept_challenge_escape_succeeds_returns_escaped_true(self, game):
        """When escape chance check succeeds: returns {'escaped': True}."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        challenge_req = _make_challenge_req(level=5)

        # Mock random.random to return 0.0 (always < escape_chance, min 0.1)
        with patch('random.random', return_value=0.0):
            result = game.accept_challenge(challenge_req)

        assert result == {'escaped': True}

    def test_accept_challenge_escape_fails_returns_defender_snapshot(self, game):
        """When escape chance check fails: returns {'escaped': False, 'defender_snapshot': ...}."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        challenge_req = _make_challenge_req(level=5)

        # Mock random.random to return 1.0 (always >= escape_chance, max 0.7)
        with patch('random.random', return_value=1.0):
            result = game.accept_challenge(challenge_req)

        assert result['escaped'] is False
        assert 'defender_snapshot' in result
        # defender_snapshot should be a battle snapshot of the local pet
        snap = result['defender_snapshot']
        assert snap['name'] == game.state['name']
        assert 'attack' in snap
        assert 'defense' in snap
        assert 'speed' in snap
        assert 'skills' in snap


# ─── Task 7: PetGame.apply_battle_result ────────────────────────────────────


class TestApplyBattleResult:
    """PetGame.apply_battle_result: update pet hp after battle, clear challenge."""

    def test_apply_battle_result_pet_wins_reduces_hp_by_hp_loss_winner(self, game):
        """When pet is the winner: hp reduced by result['hp_loss_winner'], state saved."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
            'role': 'attacker',
        }
        result = {
            'winner': 'attacker',
            'hp_loss_winner': 10,
            'hp_loss_loser': 25,
        }

        game.apply_battle_result(result)

        assert game.state['hp'] == 90  # 100 - 10

    def test_apply_battle_result_pet_loses_reduces_hp_by_hp_loss_loser(self, game):
        """When pet is the loser: hp reduced by result['hp_loss_loser'] (25), state saved."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
            'role': 'attacker',
        }
        result = {
            'winner': 'defender',
            'hp_loss_winner': 5,
            'hp_loss_loser': 25,
        }

        game.apply_battle_result(result)

        assert game.state['hp'] == 75  # 100 - 25

    def test_apply_battle_result_hp_does_not_go_below_zero(self, game):
        """HP does not go below 0 after applying battle result."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 10
        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
            'role': 'attacker',
        }
        result = {
            'winner': 'defender',
            'hp_loss_winner': 0,
            'hp_loss_loser': 25,
        }

        game.apply_battle_result(result)

        assert game.state['hp'] == 0  # max(0, 10 - 25) = 0, not -15

    def test_apply_battle_result_clears_active_challenge(self, game):
        """apply_battle_result clears active_challenge after applying result."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
            'role': 'attacker',
        }
        result = {
            'winner': 'attacker',
            'hp_loss_winner': 10,
            'hp_loss_loser': 25,
        }

        game.apply_battle_result(result)

        assert game.active_challenge is None

    def test_apply_battle_result_defender_role_wins(self, game):
        """When pet role is defender and defender wins: hp reduced by hp_loss_winner."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
            'role': 'defender',
        }
        result = {
            'winner': 'defender',
            'hp_loss_winner': 15,
            'hp_loss_loser': 25,
        }

        game.apply_battle_result(result)

        assert game.state['hp'] == 85  # 100 - 15

    def test_apply_battle_result_defender_role_loses(self, game):
        """When pet role is defender and attacker wins: hp reduced by hp_loss_loser."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
            'role': 'defender',
        }
        result = {
            'winner': 'attacker',
            'hp_loss_winner': 5,
            'hp_loss_loser': 25,
        }

        game.apply_battle_result(result)

        assert game.state['hp'] == 75  # 100 - 25


# ─── Task 8: LanNode challenge message handling ─────────────────────────────


class TestLanNodeChallengeMessages:
    """LanNode._handle_decoded_message enqueues challenge messages to ui_queue."""

    def test_challenge_req_enqueued_to_ui_queue(self):
        """MSG_CHALLENGE_REQ message is put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        payload = {
            'from': 'peer-1',
            'from_username': 'bob',
            'pet_snapshot': {'name': 'BobPet', 'level': 5},
        }
        node._handle_decoded_message(MSG_CHALLENGE_REQ, payload)
        msg = node.ui_queue.get_nowait()
        assert msg['type'] == MSG_CHALLENGE_REQ
        assert msg['payload']['from'] == 'peer-1'
        assert msg['payload']['pet_snapshot']['name'] == 'BobPet'

    def test_challenge_ack_enqueued_to_ui_queue(self):
        """MSG_CHALLENGE_ACK message is put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        payload = {
            'from': 'peer-1',
            'escaped': False,
            'defender_snapshot': {'name': 'BobPet', 'level': 5},
        }
        node._handle_decoded_message(MSG_CHALLENGE_ACK, payload)
        msg = node.ui_queue.get_nowait()
        assert msg['type'] == MSG_CHALLENGE_ACK
        assert msg['payload']['escaped'] is False
        assert msg['payload']['defender_snapshot']['name'] == 'BobPet'

    def test_challenge_result_enqueued_to_ui_queue(self):
        """MSG_CHALLENGE_RESULT message is put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        payload = {
            'winner': 'attacker',
            'hp_loss_winner': 10,
            'hp_loss_loser': 25,
            'log': ['Attacker used Tackle!'],
        }
        node._handle_decoded_message(MSG_CHALLENGE_RESULT, payload)
        msg = node.ui_queue.get_nowait()
        assert msg['type'] == MSG_CHALLENGE_RESULT
        assert msg['payload']['winner'] == 'attacker'
        assert msg['payload']['hp_loss_loser'] == 25
