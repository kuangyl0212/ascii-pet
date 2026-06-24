#!/usr/bin/env python3
"""TDD tests for Community Plaza fixes.

Covers:
  - Issue 2&4: Defender's battle_result contains winner/loser as pet names
  - Issue 2&4: Defender's battle_result contains `loser` key
  - Issue 2&4: Defender's HP is updated after receiving CHALLENGE_RESULT
  - Issue 3: battle_result can be dismissed in expanded mode (not just LAN)
  - Issue 2&4: Battle logs are in defender's language when defender re-simulates

Run: python -m pytest test/test_community_plaza_fix.py -v -m "not slow"
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
    MSG_CHALLENGE_ACK,
    MSG_CHALLENGE_RESULT,
)
from ascii_pet.i18n import set_language, _


# ─── Test helpers ───────────────────────────────────────────────────────────


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-cplaza-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


@pytest.fixture
def game(tmp_path):
    """Provide a fresh PetGame with isolated temp dir."""
    uid = _uid()
    return PetGame(uid, data_dir=tmp_path)


class _FakeLanNode:
    """Fake LanNode that simulates network behavior without real sockets."""

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
        self.send_calls = []

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


# ─── Issue 2&4: Defender battle_result contains pet names ──────────────────


class TestDefenderBattleResultPetNames:
    """Defender's battle_result should contain winner/loser as pet names,
    not 'attacker'/'defender' strings."""

    def test_defender_battle_result_has_loser_key(self, game):
        """Defender's battle_result must contain a 'loser' key with a pet name."""
        fake_node = _enable_lan_with_fake(game, 'bob')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        # Set up active_challenge as defender
        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'BobPet',
                'species': 'dog',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 18,
                'defense': 12,
                'speed': 8,
                'skills': ['tackle', 'scratch'],
            },
            'role': 'defender',
        }

        # Simulate receiving MSG_CHALLENGE_RESULT with snapshots and seed
        # (the fixed version sends attacker_snapshot, defender_snapshot, seed)
        result_payload = {
            'from': 'peer-1',
            'winner': 'attacker',
            'log': ['AlicePet used Tackle! Damage: 10.0. BobPet BP: 90.0'],
            'hp_loss_winner': 8,
            'hp_loss_loser': 25,
            'attacker_snapshot': {
                'name': 'AlicePet',
                'species': 'cat',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 20,
                'defense': 15,
                'speed': 10,
                'skills': ['tackle', 'scratch'],
            },
            'defender_snapshot': {
                'name': 'BobPet',
                'species': 'dog',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 18,
                'defense': 12,
                'speed': 8,
                'skills': ['tackle', 'scratch'],
            },
            'seed': 12345,
        }

        game._handle_lan_message({'type': MSG_CHALLENGE_RESULT, 'payload': result_payload})

        assert game.battle_result is not None
        assert 'loser' in game.battle_result, "Defender's battle_result must have 'loser' key"
        assert game.battle_result['loser'] != '?', "Loser should be a pet name, not '?'"

    def test_defender_battle_result_winner_is_pet_name(self, game):
        """Defender's battle_result winner should be a pet name, not 'attacker'/'defender'."""
        fake_node = _enable_lan_with_fake(game, 'bob')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'BobPet',
                'species': 'dog',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 18,
                'defense': 12,
                'speed': 8,
                'skills': ['tackle', 'scratch'],
            },
            'role': 'defender',
        }

        result_payload = {
            'from': 'peer-1',
            'winner': 'attacker',
            'log': ['AlicePet used Tackle! Damage: 10.0. BobPet BP: 90.0'],
            'hp_loss_winner': 8,
            'hp_loss_loser': 25,
            'attacker_snapshot': {
                'name': 'AlicePet',
                'species': 'cat',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 20,
                'defense': 15,
                'speed': 10,
                'skills': ['tackle', 'scratch'],
            },
            'defender_snapshot': {
                'name': 'BobPet',
                'species': 'dog',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 18,
                'defense': 12,
                'speed': 8,
                'skills': ['tackle', 'scratch'],
            },
            'seed': 12345,
        }

        game._handle_lan_message({'type': MSG_CHALLENGE_RESULT, 'payload': result_payload})

        assert game.battle_result is not None
        winner = game.battle_result['winner']
        assert winner not in ('attacker', 'defender'), \
            f"Winner should be a pet name, got '{winner}'"

    def test_defender_hp_updated_after_challenge_result(self, game):
        """Defender's HP should be updated after receiving CHALLENGE_RESULT."""
        fake_node = _enable_lan_with_fake(game, 'bob')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'BobPet',
                'species': 'dog',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 18,
                'defense': 12,
                'speed': 8,
                'skills': ['tackle', 'scratch'],
            },
            'role': 'defender',
        }

        result_payload = {
            'from': 'peer-1',
            'winner': 'attacker',
            'log': [],
            'hp_loss_winner': 8,
            'hp_loss_loser': 25,
            'attacker_snapshot': {
                'name': 'AlicePet',
                'species': 'cat',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 20,
                'defense': 15,
                'speed': 10,
                'skills': ['tackle', 'scratch'],
            },
            'defender_snapshot': {
                'name': 'BobPet',
                'species': 'dog',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 18,
                'defense': 12,
                'speed': 8,
                'skills': ['tackle', 'scratch'],
            },
            'seed': 12345,
        }

        game._handle_lan_message({'type': MSG_CHALLENGE_RESULT, 'payload': result_payload})

        # Defender lost (winner=attacker), so defender takes hp_loss_loser=25
        assert game.state['hp'] == 75, f"Expected HP=75, got {game.state['hp']}"


# ─── Issue 3: Battle result dismissible in expanded mode ────────────────────


class TestBattleResultDismissInExpandedMode:
    """battle_result should be dismissible in expanded mode, not just LAN mode."""

    def test_battle_result_dismissed_in_expanded_mode(self, game):
        """Pressing any key in expanded mode when battle_result is set should clear it."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'expanded'

        # Set battle_result manually
        game.battle_result = {
            'winner': 'AlicePet',
            'loser': 'BobPet',
            'log': ['Some log entry'],
            'hp_loss_winner': 5,
            'hp_loss_loser': 25,
        }

        # Press any key
        action_type, detail = game.handle_key('x')

        assert game.battle_result is None
        assert action_type == 'action'
        assert detail == 'dismiss'

    def test_battle_result_not_dismissed_when_none(self, game):
        """When battle_result is None, key handling should proceed normally in expanded mode."""
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'expanded'
        game.battle_result = None

        # Press a key that doesn't do anything special
        action_type, detail = game.handle_key('z')

        # Should not crash, battle_result should still be None
        assert game.battle_result is None


# ─── Issue 2&4: Attacker sends snapshots and seed in CHALLENGE_RESULT ──────


class TestAttackerSendsSnapshotsAndSeed:
    """When attacker processes MSG_CHALLENGE_ACK, the CHALLENGE_RESULT
    sent to defender should include attacker_snapshot, defender_snapshot,
    and seed for the defender to re-simulate locally."""

    def test_attacker_sends_snapshots_and_seed(self, game):
        """After attacker processes CHALLENGE_ACK, the sent CHALLENGE_RESULT
        should include attacker_snapshot, defender_snapshot, and seed."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        attacker_snapshot = {
            'name': 'AlicePet',
            'species': 'cat',
            'rarity': 'common',
            'level': 5,
            'shiny': False,
            'hp': 100,
            'attack': 20,
            'defense': 15,
            'speed': 10,
            'skills': ['tackle', 'scratch'],
        }

        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': attacker_snapshot,
            'role': 'attacker',
        }

        defender_snapshot = {
            'name': 'BobPet',
            'species': 'dog',
            'rarity': 'common',
            'level': 5,
            'shiny': False,
            'hp': 100,
            'attack': 18,
            'defense': 12,
            'speed': 8,
            'skills': ['tackle', 'scratch'],
        }

        ack_payload = {
            'from': 'peer-1',
            'escaped': False,
            'defender_snapshot': defender_snapshot,
        }

        game._handle_lan_message({'type': MSG_CHALLENGE_ACK, 'payload': ack_payload})

        # Check that a CHALLENGE_RESULT was sent
        challenge_results = [
            (peer, msg_type, payload)
            for peer, msg_type, payload in fake_node.send_calls
            if msg_type == MSG_CHALLENGE_RESULT
        ]
        assert len(challenge_results) >= 1, "Should have sent CHALLENGE_RESULT"
        _, _, sent_payload = challenge_results[0]

        # The sent payload should include snapshots and seed
        assert 'attacker_snapshot' in sent_payload, "CHALLENGE_RESULT should include attacker_snapshot"
        assert 'defender_snapshot' in sent_payload, "CHALLENGE_RESULT should include defender_snapshot"
        assert 'seed' in sent_payload, "CHALLENGE_RESULT should include seed"
        assert sent_payload['attacker_snapshot']['name'] == 'AlicePet'
        assert sent_payload['defender_snapshot']['name'] == 'BobPet'


# ─── Issue 2&4: Defender re-simulates battle locally ────────────────────────


class TestDefenderReSimulatesLocally:
    """When defender receives CHALLENGE_RESULT with snapshots and seed,
    they should re-simulate the battle locally to get logs in their language."""

    def test_defender_battle_result_has_full_data(self, game):
        """Defender's battle_result after re-simulation should have
        winner, loser, log, hp_loss_winner, hp_loss_loser."""
        fake_node = _enable_lan_with_fake(game, 'bob')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'BobPet',
                'species': 'dog',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 18,
                'defense': 12,
                'speed': 8,
                'skills': ['tackle', 'scratch'],
            },
            'role': 'defender',
        }

        result_payload = {
            'from': 'peer-1',
            'winner': 'attacker',
            'log': [],
            'hp_loss_winner': 8,
            'hp_loss_loser': 25,
            'attacker_snapshot': {
                'name': 'AlicePet',
                'species': 'cat',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 20,
                'defense': 15,
                'speed': 10,
                'skills': ['tackle', 'scratch'],
            },
            'defender_snapshot': {
                'name': 'BobPet',
                'species': 'dog',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 18,
                'defense': 12,
                'speed': 8,
                'skills': ['tackle', 'scratch'],
            },
            'seed': 12345,
        }

        game._handle_lan_message({'type': MSG_CHALLENGE_RESULT, 'payload': result_payload})

        assert game.battle_result is not None
        assert 'winner' in game.battle_result
        assert 'loser' in game.battle_result
        assert 'log' in game.battle_result
        assert 'hp_loss_winner' in game.battle_result
        assert 'hp_loss_loser' in game.battle_result

    def test_defender_battle_result_deterministic(self, game):
        """Defender re-simulating with same seed should get same winner/loser."""
        fake_node = _enable_lan_with_fake(game, 'bob')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'BobPet',
                'species': 'dog',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 18,
                'defense': 12,
                'speed': 8,
                'skills': ['tackle', 'scratch'],
            },
            'role': 'defender',
        }

        seed = 99999
        result_payload = {
            'from': 'peer-1',
            'winner': 'attacker',
            'log': [],
            'hp_loss_winner': 8,
            'hp_loss_loser': 25,
            'attacker_snapshot': {
                'name': 'AlicePet',
                'species': 'cat',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 20,
                'defense': 15,
                'speed': 10,
                'skills': ['tackle', 'scratch'],
            },
            'defender_snapshot': {
                'name': 'BobPet',
                'species': 'dog',
                'rarity': 'common',
                'level': 5,
                'shiny': False,
                'hp': 100,
                'attack': 18,
                'defense': 12,
                'speed': 8,
                'skills': ['tackle', 'scratch'],
            },
            'seed': seed,
        }

        game._handle_lan_message({'type': MSG_CHALLENGE_RESULT, 'payload': result_payload})

        # Also simulate the battle ourselves with the same seed to verify
        from ascii_pet.battle import simulate_battle
        attacker_snap = result_payload['attacker_snapshot']
        defender_snap = result_payload['defender_snapshot']
        expected = simulate_battle(attacker_snap, defender_snap, seed=seed)

        assert game.battle_result['winner'] == expected['winner']
        assert game.battle_result['loser'] == expected['loser']
