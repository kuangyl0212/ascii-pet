#!/usr/bin/env python3
"""TDD tests for community plaza fixes: visit submode, error messages, daily challenge limit.

Covers:
  - Visit uses 'v' key to enter submode, then digit to select player
  - Challenge/gift/trade failure shows specific reason (not generic "Cannot X now")
  - Daily challenge limit (5/day)

Run: python -m pytest test/test_community_plaza_v2.py -v
"""

import os
import sys
import time
import queue
from unittest.mock import patch
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
    MSG_VISIT_REQ,
)


# ─── Test helpers ───────────────────────────────────────────────────────────


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-cpv2-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


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
        self._peers = [
            {
                'node_id': 'peer-1',
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


# ═══════════════════════════════════════════════════════════════════════════
# Test 1: Visit submode (v key)
# ═══════════════════════════════════════════════════════════════════════════


class TestVisitSubmode:
    """Visit should use 'v' key to enter submode, then digit to select player."""

    def test_v_key_enters_visit_submode(self, game):
        """Pressing 'v' in LAN mode sets lan_submode='visit'."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.lan_submode = None

        action_type, detail = game.handle_key('v')

        assert game.lan_submode == 'visit'
        assert action_type == 'action'

    def test_visit_submode_digit_selects_player(self, game):
        """In visit submode, pressing '1' visits the first player."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.lan_submode = 'visit'

        action_type, detail = game.handle_key('1')

        # Should have sent a visit request
        assert game.lan_submode is None  # submode cleared after action
        # Check that send_to_peer was called with MSG_VISIT_REQ
        visit_calls = [c for c in fake_node.send_calls if c[1] == MSG_VISIT_REQ]
        assert len(visit_calls) == 1

    def test_visit_submode_esc_cancels(self, game):
        """In visit submode, pressing ESC cancels back to normal."""
        _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.lan_submode = 'visit'

        game.handle_key('\x1b')

        assert game.lan_submode is None

    def test_digit_key_no_longer_directly_visits(self, game):
        """Pressing '1' in LAN mode (no submode) should NOT directly visit."""
        _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.lan_submode = None

        # Old behavior: '1' directly visits. New behavior: '1' does nothing
        # unless in a submode
        action_type, detail = game.handle_key('1')

        # Should NOT have visited (no submode active)
        assert game.active_visit is None


# ═══════════════════════════════════════════════════════════════════════════
# Test 2: Specific error messages for challenge/gift/trade failures
# ═══════════════════════════════════════════════════════════════════════════


class TestSpecificErrorMessages:
    """When challenge/gift/trade fails, the specific reason should be shown,
    not a generic 'Cannot X now' message."""

    def test_challenge_dead_pet_shows_specific_reason(self, game):
        """When challenging with a dead pet, message should say 'Dead pets cannot challenge',
        not 'Cannot challenge now'."""
        _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.state['is_dead'] = True

        # Enter challenge submode
        game.handle_key('c')
        assert game.lan_submode == 'challenge'

        # Select player
        game.handle_key('1')

        # Message should be specific, not generic
        assert 'dead' in game.message.lower() or '死亡' in game.message or 'Dead' in game.message
        assert 'Cannot challenge now' not in game.message

    def test_challenge_low_hp_shows_specific_reason(self, game):
        """When challenging with low HP, message should say 'Pet HP too low',
        not 'Cannot challenge now'."""
        _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.state['hp'] = 10  # Below 25 threshold
        game.state['is_dead'] = False

        # Enter challenge submode
        game.handle_key('c')
        assert game.lan_submode == 'challenge'

        # Select player
        game.handle_key('1')

        # Message should mention HP
        assert 'hp' in game.message.lower() or 'HP' in game.message
        assert 'Cannot challenge now' not in game.message

    def test_gift_not_enough_items_shows_specific_reason(self, game):
        """When gifting without enough items, message should be specific."""
        _enable_lan_with_fake(game)
        game.mode = 'lan'
        # Clear inventory
        game.pets_data['inventory'] = {}

        # Can't enter gift submode without items - message should say so
        game.handle_key('g')
        # The 'g' key itself should show "No items to gift"
        assert 'item' in game.message.lower() or '物品' in game.message

    def test_trade_failure_shows_specific_reason(self, game):
        """When trade fails, specific reason should be shown."""
        _enable_lan_with_fake(game)
        game.mode = 'lan'

        # Enter trade submode
        game.handle_key('t')
        assert game.lan_submode == 'trade'

        # If initiate_trade returns False, message should be from initiate_trade
        # not generic "Cannot trade now"
        # For now, with a working setup, trade should succeed
        game.handle_key('1')
        # If it failed, the message should not be generic
        if 'Cannot' in game.message:
            # Should have a specific reason
            assert game.message != 'Cannot trade now'


# ═══════════════════════════════════════════════════════════════════════════
# Test 3: Daily challenge limit
# ═══════════════════════════════════════════════════════════════════════════


class TestDailyChallengeLimit:
    """Challenges should be limited to 5 per day."""

    def test_daily_challenge_limit_exists(self, game):
        """PetGame should have a MAX_DAILY_CHALLENGES attribute."""
        assert hasattr(game, 'MAX_DAILY_CHALLENGES')
        assert game.MAX_DAILY_CHALLENGES == 5

    def test_challenge_count_increments(self, game):
        """After initiating a challenge, daily challenge count should increment."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.state['hp'] = 100
        game.state['is_dead'] = False

        # Enter challenge submode and select player
        game.handle_key('c')
        game.handle_key('1')

        # Should have recorded the challenge
        today = datetime.now().date().isoformat()
        challenge_log = game.pets_data.get('challenge_log', {})
        assert challenge_log.get(today, 0) >= 1

    def test_challenge_blocked_after_limit(self, game):
        """After 5 challenges in a day, further challenges should be blocked."""
        fake_node = _enable_lan_with_fake(game)
        game.mode = 'lan'
        game.state['hp'] = 100
        game.state['is_dead'] = False

        # Simulate 5 challenges already done today
        today = datetime.now().date().isoformat()
        game.pets_data.setdefault('challenge_log', {})[today] = 5
        game.save()

        # Try to enter challenge submode
        game.handle_key('c')

        # Should be blocked with a message about daily limit
        assert 'limit' in game.message.lower() or '上限' in game.message or 'daily' in game.message.lower()
