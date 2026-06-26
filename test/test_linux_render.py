"""TDD tests for Linux version feature parity with Windows version.

Covers:
  - Bug fixes (weather import, animation cursor positioning)
  - Theme system
  - New render functions (build_lan_panel, build_lan_name_edit,
    build_battle_log, build_trade_confirm, build_restore)
  - Overlays (visitor pets, visit hint, battle log, trade confirm)
  - Keyboard shortcuts (B/V/;/'/A)
  - Main loop hooks (process_lan_queues, disable_lan on exit)

Uses importlib because the module filename 'ascii-pet' contains a hyphen.
"""

import os
import sys
import time
import queue
import importlib.util
import importlib.machinery
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame
from ascii_pet import i18n

# Load bin/ascii-pet via importlib (hyphen in filename prevents normal import).
# An explicit SourceFileLoader is required because the file has no .py extension,
# so spec_from_file_location cannot infer the loader from the suffix.
_MOD_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin', 'ascii-pet')
_loader = importlib.machinery.SourceFileLoader('ascii_pet_linux', _MOD_PATH)
_spec = importlib.util.spec_from_file_location('ascii_pet_linux', _MOD_PATH, loader=_loader)
ascii_pet_linux = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ascii_pet_linux)


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-linux-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


@pytest.fixture
def game(tmp_path):
    """Provide a fresh PetGame with isolated temp dir."""
    return PetGame(_uid(), data_dir=tmp_path)


class _FakeLanNode:
    """Fake LanNode that simulates network behavior without real sockets."""

    def __init__(self, username, pet_state):
        self.username = username
        self.pet_state = pet_state
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
        self._peers = [
            {
                'node_id': 'peer-1',
                'username': 'Bob',
                'pet_summary': {'name': 'BobPet', 'species': 'cat', 'level': 3, 'hp': 80},
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


class TestImport:
    """Verify the Linux module loads correctly."""

    def test_module_loads(self):
        assert hasattr(ascii_pet_linux, 'main')
        assert hasattr(ascii_pet_linux, 'build_compact')

    def test_weather_import_fixed(self):
        """The weather import should use ascii_pet.weather, not bare weather."""
        # Read source to verify import statement
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert 'from ascii_pet.weather import' in source
        assert 'from weather import' not in source
