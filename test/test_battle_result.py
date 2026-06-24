#!/usr/bin/env python3
"""TDD tests for battle_result storage fix (replace battle_log).

Covers:
  - After _handle_lan_message processes MSG_CHALLENGE_ACK with a battle,
    game.battle_result contains full data (winner, loser, log, hp_loss_*)
  - After _handle_lan_message processes MSG_CHALLENGE_RESULT,
    game.battle_result contains full data
  - Pressing any key in LAN mode when battle_result is not None clears it

Run: python -m pytest test/test_battle_result.py -v
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
    MSG_CHALLENGE_REQ,
    MSG_CHALLENGE_ACK,
    MSG_CHALLENGE_RESULT,
)


# ─── Test helpers ───────────────────────────────────────────────────────────


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-bresult-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


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


# ─── Tests ──────────────────────────────────────────────────────────────────


class TestBattleResultStorage:
    """After _handle_lan_message processes battle messages,
    game.battle_result contains full data (not just log)."""

    def test_msg_challenge_ack_stores_full_battle_result(self, game):
        """When MSG_CHALLENGE_ACK is processed (attacker side),
        game.battle_result contains winner, loser, log, hp_loss_winner,
        hp_loss_loser — not just the log list."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        # Set up active_challenge as attacker
        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {
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
            'role': 'attacker',
        }

        # Simulate receiving MSG_CHALLENGE_ACK (opponent didn't escape)
        ack_payload = {
            'from': 'peer-1',
            'escaped': False,
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
        }

        game._handle_lan_message({'type': MSG_CHALLENGE_ACK, 'payload': ack_payload})

        # battle_result should be a dict with full data
        assert game.battle_result is not None
        assert isinstance(game.battle_result, dict)
        assert 'log' in game.battle_result
        assert 'winner' in game.battle_result
        assert 'loser' in game.battle_result
        assert 'hp_loss_winner' in game.battle_result
        assert 'hp_loss_loser' in game.battle_result
        # winner and loser should be actual names, not '?'
        assert game.battle_result['winner'] != '?'
        assert game.battle_result['loser'] != '?'
        # hp_loss values should be non-zero for loser
        assert game.battle_result['hp_loss_loser'] > 0

    def test_msg_challenge_result_stores_full_battle_result(self, game):
        """When MSG_CHALLENGE_RESULT is processed (defender side),
        game.battle_result contains full data from the payload."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        # Set up active_challenge as defender
        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
            'role': 'defender',
        }

        # Simulate receiving MSG_CHALLENGE_RESULT
        result_payload = {
            'from': 'peer-1',
            'winner': 'defender',
            'log': ['AlicePet used Tackle! Damage: 10.0. BobPet BP: 90.0',
                     'BobPet used Scratch! Damage: 8.0. AlicePet BP: 92.0'],
            'hp_loss_winner': 8,
            'hp_loss_loser': 25,
        }

        game._handle_lan_message({'type': MSG_CHALLENGE_RESULT, 'payload': result_payload})

        # battle_result should contain full data from payload
        assert game.battle_result is not None
        assert isinstance(game.battle_result, dict)
        assert game.battle_result['winner'] == 'defender'
        assert game.battle_result['log'] == result_payload['log']
        assert game.battle_result['hp_loss_winner'] == 8
        assert game.battle_result['hp_loss_loser'] == 25

    def test_any_key_in_lan_mode_clears_battle_result(self, game):
        """When battle_result is not None and user presses any key in LAN mode,
        battle_result is cleared and the key is consumed."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        # Set battle_result manually
        game.battle_result = {
            'winner': 'attacker',
            'loser': 'defender',
            'log': ['Some log entry'],
            'hp_loss_winner': 5,
            'hp_loss_loser': 25,
        }

        # Press any key
        action_type, detail = game.handle_key('x')

        assert game.battle_result is None
        assert action_type == 'action'
        assert detail == 'dismiss'

    def test_battle_result_not_set_initially(self, game):
        """battle_result should be None initially."""
        assert game.battle_result is None

    def test_battle_log_attribute_removed(self, game):
        """After fix, battle_log attribute should not exist on PetGame."""
        assert not hasattr(game, 'battle_log') or game.battle_log is None
