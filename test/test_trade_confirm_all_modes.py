#!/usr/bin/env python3
"""TDD tests for trade confirmation panel visibility across all modes.

Covers spec: fix-trade-confirm-all-modes
- Task 1: Trade confirm panel renders in ALL modes (not just expanded/lan)
- Task 2: Accepting trade (y) in non-lan mode switches to lan mode
- Task 3: Rejecting trade (n) clears pending_trade_req in all modes
- Task 4: End-to-end flow verification

Run: python -m pytest test/test_trade_confirm_all_modes.py -v
"""

import os
import sys
import time
import queue
import importlib.util
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame
from ascii_pet.protocol import (
    MSG_TRADE_REQ,
    MSG_TRADE_ACK,
    MSG_TRADE_CONFIRM,
)
from ascii_pet import lan


# ─── Test helpers ───────────────────────────────────────────────────────────


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-tc-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


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


def _load_win_module():
    """Load bin/ascii-pet-win.py as a module via importlib."""
    bin_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'bin', 'ascii-pet-win.py',
    )
    spec = importlib.util.spec_from_file_location('ascii_pet_win', bin_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_trade_req(from_id='peer-1', from_username='bob',
                    pet_name='BobPet'):
    """Build a trade_req dict as received over the network."""
    return {
        'from': from_id,
        'from_username': from_username,
        'pet_snapshot': {'name': pet_name, 'species': 'cat'},
        'pet_index': 0,
    }


def _set_pending_trade_req(game, **kwargs):
    """Set game.pending_trade_req with default values."""
    game.pending_trade_req = _make_trade_req(**kwargs)


def _get_render_lines_text(win_mod, game):
    """Get render lines from PetWindow and return as list of text strings."""
    win = win_mod.PetWindow(game)
    lines = win.get_render_lines()
    return [line[0] if isinstance(line, tuple) else str(line) for line in lines]


# ─── Task 1: Trade confirm panel renders in ALL modes ─────────────────────


class TestTradeConfirmPanelAllModes:
    """Task 1: Trade confirm panel must render in ALL modes, not just
    expanded/lan."""

    @pytest.mark.parametrize("mode", [
        'compact', 'expanded', 'stats', 'achievements',
        'items', 'rename', 'release', 'lan',
    ])
    def test_trade_confirm_panel_shown_when_pending_trade_req_exists(self, game, mode):
        """WHEN pending_trade_req exists and game.mode is any of the 8 modes
        THEN get_render_lines output contains the trade confirm panel
        (identifiable by 'wants to trade' and '[y]' and '[n]')."""
        _enable_lan_with_fake(game, 'alice')
        _set_pending_trade_req(game, from_username='Bob', pet_name='BobPet')
        game.mode = mode

        win_mod = _load_win_module()
        text_lines = _get_render_lines_text(win_mod, game)
        all_text = ' '.join(text_lines)

        assert 'wants to trade' in all_text or 'wants to trade' in all_text.lower(), \
            f"Mode {mode}: expected 'wants to trade' in render output. Got: {text_lines}"
        assert '[y]' in all_text, \
            f"Mode {mode}: expected '[y]' accept hint in render output. Got: {text_lines}"
        assert '[n]' in all_text, \
            f"Mode {mode}: expected '[n]' reject hint in render output. Got: {text_lines}"

    @pytest.mark.parametrize("mode", [
        'compact', 'expanded', 'stats', 'achievements',
        'items', 'rename', 'release', 'lan',
    ])
    def test_no_trade_confirm_panel_when_pending_trade_req_is_none(self, game, mode):
        """WHEN pending_trade_req is None
        THEN get_render_lines output does NOT contain trade confirm panel."""
        _enable_lan_with_fake(game, 'alice')
        game.pending_trade_req = None
        game.mode = mode

        win_mod = _load_win_module()
        text_lines = _get_render_lines_text(win_mod, game)
        all_text = ' '.join(text_lines)

        assert 'wants to trade' not in all_text.lower(), \
            f"Mode {mode}: should NOT show trade confirm when pending_trade_req is None. Got: {text_lines}"


# ─── Task 2: Accepting trade switches to lan mode ──────────────────────────


class TestAcceptTradeSwitchesToLan:
    """Task 2: Pressing 'y' to accept trade in non-lan mode switches to lan."""

    @pytest.mark.parametrize("mode", ['compact', 'expanded', 'stats', 'achievements', 'items'])
    def test_accept_trade_in_non_lan_mode_switches_to_lan(self, game, mode):
        """WHEN pending_trade_req exists and user presses 'y' in non-lan mode
        THEN _accepting is set to True AND game.mode switches to 'lan'."""
        _enable_lan_with_fake(game, 'alice')
        _set_pending_trade_req(game, from_username='Bob', pet_name='BobPet')
        game.mode = mode

        game.handle_key('y')

        assert game.pending_trade_req is not None
        assert game.pending_trade_req.get('_accepting') is True, \
            f"Mode {mode}: _accepting should be True after pressing 'y'"
        assert game.mode == 'lan', \
            f"Mode {mode}: mode should switch to 'lan' after accepting trade. Got: {game.mode}"

    def test_accept_trade_in_lan_mode_stays_in_lan(self, game):
        """WHEN already in lan mode and user presses 'y'
        THEN _accepting is True and mode stays 'lan' (no side effect)."""
        _enable_lan_with_fake(game, 'alice')
        _set_pending_trade_req(game, from_username='Bob', pet_name='BobPet')
        game.mode = 'lan'

        game.handle_key('y')

        assert game.pending_trade_req.get('_accepting') is True
        assert game.mode == 'lan'

    def test_accept_trade_shows_select_pet_message(self, game):
        """WHEN user presses 'y' to accept trade
        THEN game.message contains 'Select pet' hint."""
        _enable_lan_with_fake(game, 'alice')
        _set_pending_trade_req(game, from_username='Bob', pet_name='BobPet')
        game.mode = 'compact'

        game.handle_key('y')

        assert game.message is not None
        assert 'select pet' in game.message.lower() or 'Select pet' in game.message, \
            f"Expected 'Select pet' message. Got: {game.message}"


# ─── Task 3: Rejecting trade clears pending_trade_req ──────────────────────


class TestRejectTradeClearsNotification:
    """Task 3: Pressing 'n' rejects trade, sends MSG_TRADE_ACK(accepted=False),
    and clears pending_trade_req in ALL modes."""

    @pytest.mark.parametrize("mode", [
        'compact', 'expanded', 'stats', 'achievements',
        'items', 'rename', 'release', 'lan',
    ])
    def test_reject_trade_clears_pending_trade_req(self, game, mode):
        """WHEN pending_trade_req exists and user presses 'n' in any mode
        THEN pending_trade_req becomes None."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        _set_pending_trade_req(game, from_username='Bob', pet_name='BobPet')
        game.mode = mode

        game.handle_key('n')

        assert game.pending_trade_req is None, \
            f"Mode {mode}: pending_trade_req should be None after rejecting"

    @pytest.mark.parametrize("mode", ['compact', 'stats', 'items', 'lan'])
    def test_reject_trade_sends_trade_ack_false(self, game, mode):
        """WHEN user presses 'n' to reject trade in any mode
        THEN MSG_TRADE_ACK with accepted=False is sent to the requester."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        _set_pending_trade_req(game, from_id='peer-bob', from_username='Bob')
        game.mode = mode

        game.handle_key('n')

        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_ACK]
        assert len(ack_calls) == 1, \
            f"Mode {mode}: expected 1 MSG_TRADE_ACK sent. Got {len(ack_calls)}"
        peer_id, msg_type, payload = ack_calls[0]
        assert payload.get('accepted') is False
        assert peer_id == 'peer-bob'

    @pytest.mark.parametrize("mode", ['compact', 'stats', 'lan'])
    def test_reject_trade_shows_rejected_message(self, game, mode):
        """WHEN user presses 'n' to reject trade in any mode
        THEN game.message contains 'rejected' (or its translation)."""
        _enable_lan_with_fake(game, 'alice')
        _set_pending_trade_req(game, from_username='Bob')
        game.mode = mode

        game.handle_key('n')

        assert game.message is not None
        assert 'reject' in game.message.lower() or '拒绝' in game.message, \
            f"Mode {mode}: expected 'rejected' message. Got: {game.message}"

    def test_reject_trade_removes_confirm_panel_from_render(self, game):
        """WHEN user rejects trade (pending_trade_req becomes None)
        THEN render output no longer contains trade confirm panel."""
        _enable_lan_with_fake(game, 'alice')
        _set_pending_trade_req(game, from_username='Bob')
        game.mode = 'compact'

        # Before reject: panel should be visible
        win_mod = _load_win_module()
        text_before = _get_render_lines_text(win_mod, game)
        assert any('wants to trade' in t.lower() for t in text_before)

        # Reject
        game.handle_key('n')

        # After reject: panel should NOT be visible
        text_after = _get_render_lines_text(win_mod, game)
        assert not any('wants to trade' in t.lower() for t in text_after), \
            f"After reject, trade panel should not show. Got: {text_after}"


# ─── Task 4: End-to-end flow verification ──────────────────────────────────


class TestTradeE2EFlow:
    """Task 4: End-to-end flow tests for trade accept and reject paths."""

    def test_e2e_accept_flow_from_compact_mode(self, game):
        """Full accept flow: compact mode → receive req → see panel → press y
        → switch to lan → select pet → send ACK → receive CONFIRM → trade done."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        # Simulate receiving a trade request
        trade_req = _make_trade_req(from_id='peer-bob', from_username='Bob',
                                     pet_name='BobPet')
        fake_node.ui_queue.put({
            'type': MSG_TRADE_REQ,
            'payload': trade_req,
        })
        game.process_lan_queues()

        # Verify pending_trade_req is set
        assert game.pending_trade_req is not None

        # Switch to compact mode and verify panel shows
        game.mode = 'compact'
        win_mod = _load_win_module()
        text_lines = _get_render_lines_text(win_mod, game)
        assert any('wants to trade' in t.lower() for t in text_lines)

        # Press 'y' to accept → should switch to lan mode
        game.handle_key('y')
        assert game.pending_trade_req.get('_accepting') is True
        assert game.mode == 'lan'

        # Select pet 1 → should send ACK with accepted=True
        game.handle_key('1')
        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_ACK]
        assert len(ack_calls) == 1
        assert ack_calls[0][2].get('accepted') is True
        assert game.pending_trade_req is None
        assert game.active_trade is not None
        assert game.active_trade.get('role') == 'receiver'

    def test_e2e_reject_flow_from_stats_mode(self, game):
        """Full reject flow: stats mode → receive req → press n → panel gone
        → ACK(accepted=False) sent."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        # Simulate receiving a trade request
        trade_req = _make_trade_req(from_id='peer-bob', from_username='Bob',
                                     pet_name='BobPet')
        fake_node.ui_queue.put({
            'type': MSG_TRADE_REQ,
            'payload': trade_req,
        })
        game.process_lan_queues()
        assert game.pending_trade_req is not None

        # Switch to stats mode
        game.mode = 'stats'
        win_mod = _load_win_module()

        # Verify panel shows in stats mode
        text_before = _get_render_lines_text(win_mod, game)
        assert any('wants to trade' in t.lower() for t in text_before)

        # Press 'n' to reject
        game.handle_key('n')
        assert game.pending_trade_req is None

        # Verify ACK(accepted=False) was sent
        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_ACK]
        assert len(ack_calls) == 1
        assert ack_calls[0][2].get('accepted') is False

        # Verify panel no longer shows
        text_after = _get_render_lines_text(win_mod, game)
        assert not any('wants to trade' in t.lower() for t in text_after)
