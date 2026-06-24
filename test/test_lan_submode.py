#!/usr/bin/env python3
"""TDD tests for LAN submode state management.

Covers:
  - handle_key('c') in LAN mode sets lan_submode='challenge', does NOT call initiate_challenge
  - lan_submode='challenge' + handle_key('1') calls initiate_challenge with first peer's node_id
  - lan_submode='challenge' + handle_key('\x1b') or 'q' clears lan_submode
  - handle_key('g') sets lan_submode='gift'
  - lan_submode='gift' + handle_key('1') sets lan_submode='gift_item', stores target
  - lan_submode='gift_item' + handle_key('1') calls gift_item with stored target and first item
  - handle_key('t') sets lan_submode='trade'
  - lan_submode='trade' + handle_key('1') calls initiate_trade with first peer
  - handle_key('h') directly heals, does NOT set lan_submode
  - Submode ignores non-digit/non-cancel keys
  - When no peers, entering submode shows message and doesn't set lan_submode
  - When inventory is empty, gift submode shows message

Run: python -m pytest test/test_lan_submode.py -v
"""

import os
import sys
import time
import queue
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame
from ascii_pet.protocol import MSG_CHALLENGE_REQ, MSG_TRADE_REQ, MSG_GIFT_ITEM


# ─── Test helpers ───────────────────────────────────────────────────────────


def _uid():
    return f'test-submode-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


@pytest.fixture
def game(tmp_path):
    uid = _uid()
    return PetGame(uid, data_dir=tmp_path)


class _FakeLanNode:
    """Fake LanNode with configurable peers list."""

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


def _enable_lan_with_fake(game, username='alice', peers=None):
    """Enable LAN on game using _FakeLanNode. Returns the fake node."""
    fake_node = _FakeLanNode(username, game.state)
    with patch('ascii_pet.lan.LanNode', return_value=fake_node):
        game.enable_lan(username)
    if peers:
        fake_node._peers = peers
    return fake_node


def _make_peers(count=2):
    """Create fake peer list."""
    return [
        {
            'node_id': f'peer-{i}',
            'username': f'player{i}',
            'pet_summary': {'name': f'Pet{i}', 'species': 'cat'},
        }
        for i in range(count)
    ]


# ─── Tests ──────────────────────────────────────────────────────────────────


class TestChallengeSubmode:
    """Test challenge submode: 'c' enters submode, digit selects target."""

    def test_c_key_sets_challenge_submode(self, game):
        """Pressing 'c' in LAN mode sets lan_submode='challenge'."""
        fake_node = _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.handle_key('c')

        assert game.lan_submode == 'challenge'
        # Should NOT have sent a challenge request yet
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_CHALLENGE_REQ]
        assert len(req_calls) == 0

    def test_challenge_digit_selects_peer(self, game):
        """In challenge submode, pressing '1' calls initiate_challenge with first peer."""
        fake_node = _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.handle_key('c')
        assert game.lan_submode == 'challenge'

        game.handle_key('1')

        # Should have sent a challenge request to peer-0
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_CHALLENGE_REQ]
        assert len(req_calls) == 1
        assert req_calls[0][0] == 'peer-0'
        # Submode should be cleared
        assert game.lan_submode is None

    def test_challenge_esc_cancels(self, game):
        """In challenge submode, pressing ESC clears lan_submode."""
        _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.handle_key('c')
        assert game.lan_submode == 'challenge'

        game.handle_key('\x1b')

        assert game.lan_submode is None

    def test_challenge_q_cancels(self, game):
        """In challenge submode, pressing 'q' clears lan_submode."""
        _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.handle_key('c')
        game.handle_key('q')

        assert game.lan_submode is None

    def test_challenge_no_peers_shows_message(self, game):
        """When there are no peers, pressing 'c' shows message and doesn't set submode."""
        _enable_lan_with_fake(game, peers=[])
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.handle_key('c')

        assert game.lan_submode is None
        assert game.message is not None
        assert 'challenge' in game.message.lower() or 'No peers' in game.message


class TestGiftSubmode:
    """Test gift submode: 'g' enters submode, digit selects target, then item."""

    def test_g_key_sets_gift_submode(self, game):
        """Pressing 'g' in LAN mode sets lan_submode='gift'."""
        _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'
        # Add inventory
        game.pets_data['inventory'] = {'apple': 3}
        game.save()

        game.handle_key('g')

        assert game.lan_submode == 'gift'

    def test_gift_digit_selects_target_then_gift_item_submode(self, game):
        """In gift submode, pressing '1' sets lan_submode='gift_item' with target."""
        fake_node = _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'
        game.pets_data['inventory'] = {'apple': 3}
        game.save()

        game.handle_key('g')
        game.handle_key('1')

        assert game.lan_submode == 'gift_item'
        assert game.lan_submode_data is not None
        assert game.lan_submode_data.get('target_node_id') == 'peer-0'

    def test_gift_item_digit_sends_gift(self, game):
        """In gift_item submode, pressing '1' calls gift_item with stored target."""
        fake_node = _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'
        game.pets_data['inventory'] = {'apple': 3}
        game.save()

        game.handle_key('g')
        game.handle_key('1')  # select target
        game.handle_key('1')  # select item

        # Should have sent a gift message
        gift_calls = [c for c in fake_node.send_calls if c[1] == MSG_GIFT_ITEM]
        assert len(gift_calls) == 1
        assert gift_calls[0][0] == 'peer-0'
        # Submode should be cleared
        assert game.lan_submode is None
        assert game.lan_submode_data is None

    def test_gift_no_peers_shows_message(self, game):
        """When there are no peers, pressing 'g' shows message."""
        _enable_lan_with_fake(game, peers=[])
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'
        game.pets_data['inventory'] = {'apple': 3}
        game.save()

        game.handle_key('g')

        assert game.lan_submode is None
        assert game.message is not None

    def test_gift_no_items_shows_message(self, game):
        """When inventory is empty, pressing 'g' shows message."""
        _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'
        # Empty inventory
        game.pets_data['inventory'] = {}
        game.save()

        game.handle_key('g')

        assert game.lan_submode is None
        assert game.message is not None
        assert 'item' in game.message.lower() or '物品' in game.message

    def test_gift_esc_cancels(self, game):
        """In gift submode, pressing ESC clears lan_submode."""
        _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'
        game.pets_data['inventory'] = {'apple': 3}
        game.save()

        game.handle_key('g')
        game.handle_key('\x1b')

        assert game.lan_submode is None


class TestTradeSubmode:
    """Test trade submode: 't' enters submode, digit selects target."""

    def test_t_key_sets_trade_submode(self, game):
        """Pressing 't' in LAN mode sets lan_submode='trade'."""
        _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.handle_key('t')

        assert game.lan_submode == 'trade'

    def test_trade_digit_selects_peer(self, game):
        """In trade submode, pressing '1' calls initiate_trade with first peer."""
        fake_node = _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.handle_key('t')
        game.handle_key('1')

        # Should have sent a trade request to peer-0
        req_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_REQ]
        assert len(req_calls) == 1
        assert req_calls[0][0] == 'peer-0'
        # Submode should be cleared
        assert game.lan_submode is None

    def test_trade_no_peers_shows_message(self, game):
        """When there are no peers, pressing 't' shows message."""
        _enable_lan_with_fake(game, peers=[])
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.handle_key('t')

        assert game.lan_submode is None
        assert game.message is not None

    def test_trade_esc_cancels(self, game):
        """In trade submode, pressing ESC clears lan_submode."""
        _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.handle_key('t')
        game.handle_key('\x1b')

        assert game.lan_submode is None


class TestHealKey:
    """Test that 'h' key directly heals without entering submode."""

    def test_h_key_heals_directly(self, game):
        """Pressing 'h' in LAN mode heals pet directly, does NOT set lan_submode."""
        _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 50
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.handle_key('h')

        assert game.lan_submode is None
        # HP should be restored to 100
        assert game.state['hp'] == 100


class TestSubmodeIgnoresOtherKeys:
    """Test that submode ignores non-digit/non-cancel keys."""

    def test_submode_ignores_random_key(self, game):
        """In challenge submode, pressing a non-digit/non-cancel key returns 'none'."""
        _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.handle_key('c')
        action_type, detail = game.handle_key('x')

        assert action_type == 'none'
        # Submode should still be active
        assert game.lan_submode == 'challenge'

    def test_submode_invalid_digit_shows_message(self, game):
        """In challenge submode, pressing '9' when only 2 peers shows invalid selection."""
        _enable_lan_with_fake(game, peers=_make_peers(2))
        game.state['hp'] = 100
        game.state['is_dead'] = False
        game.mode = 'lan'

        game.handle_key('c')
        game.handle_key('9')

        assert game.lan_submode is None
        assert game.message is not None


class TestSubmodeInitialState:
    """Test that lan_submode and lan_submode_data are None initially."""

    def test_lan_submode_none_initially(self, game):
        assert game.lan_submode is None

    def test_lan_submode_data_none_initially(self, game):
        assert game.lan_submode_data is None
