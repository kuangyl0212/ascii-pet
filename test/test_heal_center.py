#!/usr/bin/env python3
"""TDD tests for LAN healing center feature.

Covers:
  Task 13: PetGame.heal_pet — heal current pet at the LAN healing center.

Run: python -m pytest test/test_heal_center.py -v

All PetGame tests mock LanNode — no real network is started.
The healing center is a LAN-only feature: free of cost, 30-minute cooldown.
"""

import os
import sys
import time
import queue
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame


# ─── Test helpers ───────────────────────────────────────────────────────────


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-heal-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


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


# ─── Task 13: PetGame.heal_pet ──────────────────────────────────────────────


class TestHealPet:
    """PetGame.heal_pet: heal current pet at the LAN healing center."""

    def test_heal_pet_when_lan_enabled_and_hp_below_100_heals_and_returns_true(self, game):
        """When lan_enabled=True and hp<100: adds 20 HP (capped at 100),
        updates last_heal_time, sets message 'Healed +20 HP!', returns True."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 50
        # Ensure no cooldown is in effect
        game.last_heal_time = 0.0

        before = time.time()
        result = game.heal_pet()
        after = time.time()

        assert result is True
        assert game.state['hp'] == 70  # 50 + 20
        assert before <= game.last_heal_time <= after
        assert game.message == 'Healed +20 HP!'
        assert game.message_time > 0

    def test_heal_pet_when_hp_already_full_returns_false_with_message(self, game):
        """When hp is already 100: returns False, message 'HP is full'."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.last_heal_time = 0.0

        result = game.heal_pet()

        assert result is False
        assert game.message == 'HP is full'
        assert game.message_time > 0

    def test_heal_pet_when_lan_disabled_returns_false_with_message(self, game):
        """When lan_enabled=False: returns False, message 'LAN not enabled'."""
        # Make sure LAN is disabled
        if game.lan_enabled:
            game.disable_lan()
        game.state['hp'] = 50

        result = game.heal_pet()

        assert result is False
        assert game.message == 'LAN not enabled'
        assert game.message_time > 0

    def test_heal_pet_cooldown_blocks_second_heal_within_30_minutes(self, game):
        """When heal_pet is called again within 30 minutes of the last heal:
        returns False, message mentions cooldown."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 50
        game.last_heal_time = 0.0

        # First heal succeeds
        first_result = game.heal_pet()
        assert first_result is True
        assert game.state['hp'] == 70  # 50 + 20

        # Damage pet again so hp<100, then try to heal within cooldown
        game.state['hp'] = 30
        second_result = game.heal_pet()

        assert second_result is False
        assert game.message is not None
        # Message should mention cooldown and minutes remaining
        assert 'cooldown' in game.message.lower() or 'wait' in game.message.lower()
        assert game.message_time > 0
        # HP should NOT have been restored by the second attempt
        assert game.state['hp'] == 30

    def test_heal_pet_after_cooldown_expires_heals_successfully(self, game):
        """When last_heal_time is 31 minutes ago: heals successfully, returns True."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 40
        # Set last_heal_time to 31 minutes ago — cooldown (30 min) has expired
        game.last_heal_time = time.time() - (31 * 60)

        result = game.heal_pet()

        assert result is True
        assert game.state['hp'] == 60  # 40 + 20
        assert game.message == 'Healed +20 HP!'
        assert game.message_time > 0
        # last_heal_time should be updated to roughly now
        assert game.last_heal_time > time.time() - 5

    def test_heal_pet_saves_state_after_healing(self, game):
        """heal_pet calls self.save() after a successful heal."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 50
        game.last_heal_time = 0.0

        with patch.object(game, 'save') as mock_save:
            result = game.heal_pet()

        assert result is True
        assert game.state['hp'] == 70  # 50 + 20
        mock_save.assert_called_once()
