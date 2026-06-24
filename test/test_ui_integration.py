#!/usr/bin/env python3
"""TDD tests for UI integration of LAN challenge/gift/trade/heal features.

Covers:
  Task 15: _handle_lan_message extensions for challenge/gift/trade messages
           and handle_key 'y'/'n' trade confirmation.
  Task 14: render_lan_lines HP display.

Run: python -m pytest test/test_ui_integration.py -v

All PetGame tests mock LanNode — no real network is started.
"""

import os
import sys
import time
import queue
import importlib.util
from unittest.mock import patch, MagicMock

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
)
from ascii_pet import lan


# ─── Test helpers ───────────────────────────────────────────────────────────


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-ui-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


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


def _make_trade_req(from_id='peer-1', from_username='bob'):
    """Build a minimal trade_req dict as received over the network.

    The pet_snapshot is a FULL pet state dict so all attributes migrate.
    """
    return {
        'from': from_id,
        'from_username': from_username,
        'pet_snapshot': {
            'name': 'BobPet',
            'species': 'cat',
            'rarity': 'common',
            'level': 5,
            'shiny': False,
            'eye': '·',
            'hat': 'none',
            'stats': {'HUNGER': 80, 'HAPPY': 80, 'ENERGY': 80, 'HYGIENE': 80},
            'mood': 'happy',
            'created_at': '2026-01-01T00:00:00',
            'last_fed': '2026-01-01T00:00:00',
            'last_played': '2026-01-01T00:00:00',
            'last_slept': '2026-01-01T00:00:00',
            'level': 5,
            'xp': 0,
            'total_interactions': 0,
            'feed_count': 0,
            'play_count': 0,
            'sleep_count': 0,
            'achievements': [],
            'critical_since': None,
            'is_dead': False,
            'hp': 100,
            'user_id': 'bob',
        },
        'pet_index': 0,
    }


def _load_win_module():
    """Load bin/ascii-pet-win.py as a module via importlib.

    The filename contains hyphens so it cannot be imported normally.
    """
    bin_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'bin', 'ascii-pet-win.py',
    )
    spec = importlib.util.spec_from_file_location('ascii_pet_win', bin_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─── Task 15: _handle_lan_message MSG_CHALLENGE_REQ ─────────────────────────


class TestHandleLanMessageChallengeReq:
    """_handle_lan_message processes MSG_CHALLENGE_REQ on the defender side."""

    def test_challenge_req_low_hp_sends_escaped_ack(self, game):
        """When defender hp < 25: accept_challenge escapes, sends ACK with
        escaped=True."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 24  # low hp → escape
        game.state['is_dead'] = False
        challenge_req = _make_challenge_req()

        fake_node.ui_queue.put({
            'type': MSG_CHALLENGE_REQ,
            'payload': challenge_req,
        })
        game.process_lan_queues()

        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_CHALLENGE_ACK]
        assert len(ack_calls) == 1
        peer_id, msg_type, payload = ack_calls[0]
        assert payload['escaped'] is True

    def test_challenge_req_accepts_and_sends_defender_snapshot(self, game):
        """When defender accepts (escape fails): sends ACK with escaped=False
        and defender_snapshot."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.state['is_dead'] = False
        challenge_req = _make_challenge_req()

        # Mock random.random → 1.0 so escape fails (1.0 >= max escape_chance 0.7)
        with patch('random.random', return_value=1.0):
            fake_node.ui_queue.put({
                'type': MSG_CHALLENGE_REQ,
                'payload': challenge_req,
            })
            game.process_lan_queues()

        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_CHALLENGE_ACK]
        assert len(ack_calls) == 1
        payload = ack_calls[0][2]
        assert payload['escaped'] is False
        assert 'defender_snapshot' in payload


# ─── Task 15: _handle_lan_message MSG_GIFT_ITEM ─────────────────────────────


class TestHandleLanMessageGiftItem:
    """_handle_lan_message processes MSG_GIFT_ITEM on the receiver side."""

    def test_gift_item_calls_receive_gift_and_sends_ack(self, game):
        """When receiving MSG_GIFT_ITEM: calls receive_gift, sends ACK with
        success=True, and adds item to inventory."""
        fake_node = _enable_lan_with_fake(game, 'alice')

        fake_node.ui_queue.put({
            'type': MSG_GIFT_ITEM,
            'payload': {
                'from': 'peer-1',
                'from_username': 'bob',
                'item_id': 'apple',
                'count': 1,
            },
        })
        game.process_lan_queues()

        # Verify ACK sent
        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_GIFT_ACK]
        assert len(ack_calls) == 1
        payload = ack_calls[0][2]
        assert payload['success'] is True
        # Verify item added to inventory
        assert game.pets_data.get('inventory', {}).get('apple', 0) >= 1


# ─── Task 15: _handle_lan_message MSG_TRADE_REQ ─────────────────────────────


class TestHandleLanMessageTradeReq:
    """_handle_lan_message processes MSG_TRADE_REQ on the receiver side."""

    def test_trade_req_sets_pending_trade_req(self, game):
        """When receiving MSG_TRADE_REQ: stores payload in pending_trade_req
        and sets a message prompting [y/n]."""
        fake_node = _enable_lan_with_fake(game, 'alice')

        trade_req = _make_trade_req()
        fake_node.ui_queue.put({
            'type': MSG_TRADE_REQ,
            'payload': trade_req,
        })
        game.process_lan_queues()

        assert game.pending_trade_req is not None
        assert game.pending_trade_req['from'] == 'peer-1'
        assert game.message is not None


# ─── Task 15: _handle_lan_message MSG_TRADE_ACK ─────────────────────────────


class TestHandleLanMessageTradeAck:
    """_handle_lan_message processes MSG_TRADE_ACK on the initiator side."""

    def test_trade_ack_accepted_sends_confirm_and_executes_trade(self, game):
        """When receiving MSG_TRADE_ACK with accepted=True: sends
        MSG_TRADE_CONFIRM and executes the trade (pet replaced)."""
        fake_node = _enable_lan_with_fake(game, 'alice')

        # Set up active_trade as initiator
        original_pet = game.pets_data['pets'][0]
        original_name = original_pet['name']
        game.active_trade = {
            'target': 'peer-1',
            'pet_index': 0,
            'start_time': time.time(),
            'role': 'initiator',
        }

        received_pet = _make_trade_req()['pet_snapshot']
        fake_node.ui_queue.put({
            'type': MSG_TRADE_ACK,
            'payload': {
                'from': 'peer-1',
                'accepted': True,
                'pet_snapshot': received_pet,
                'pet_index': 0,
            },
        })
        game.process_lan_queues()

        # Verify MSG_TRADE_CONFIRM sent
        confirm_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_CONFIRM]
        assert len(confirm_calls) == 1
        # Verify trade executed: pet replaced
        assert game.pets_data['pets'][0]['name'] == 'BobPet'
        # active_trade should be cleared by execute_trade
        assert game.active_trade is None


# ─── Task 15: _handle_lan_message MSG_CHALLENGE_RESULT ──────────────────────


class TestHandleLanMessageChallengeResult:
    """_handle_lan_message processes MSG_CHALLENGE_RESULT on the defender side."""

    def test_challenge_result_calls_apply_battle_result(self, game):
        """When receiving MSG_CHALLENGE_RESULT: calls apply_battle_result,
        stores battle_log, and clears active_challenge."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 100
        game.active_challenge = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
            'role': 'defender',
        }

        result_payload = {
            'winner': 'attacker',
            'hp_loss_winner': 10,
            'hp_loss_loser': 25,
            'log': ['Attacker used Tackle!', 'Defender used Scratch!'],
        }
        fake_node.ui_queue.put({
            'type': MSG_CHALLENGE_RESULT,
            'payload': result_payload,
        })
        game.process_lan_queues()

        # apply_battle_result should have updated hp (defender lost → -25)
        assert game.state['hp'] == 75  # 100 - 25
        # active_challenge cleared
        assert game.active_challenge is None
        # battle_result stored
        assert game.battle_result is not None
        assert len(game.battle_result.get('log', [])) == 2


# ─── Task 15: handle_key 'y'/'n' trade confirmation ─────────────────────────


class TestHandleKeyTradeConfirmation:
    """handle_key processes 'y'/'n' when pending_trade_req exists."""

    def test_handle_key_y_accepts_trade(self, game):
        """When pending_trade_req exists and key == 'y': enters pet selection,
        then pressing '1' accepts trade with pet index 0, sends MSG_TRADE_ACK,
        clears pending_trade_req."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        trade_req = _make_trade_req()
        game.pending_trade_req = trade_req

        # 'y' enters pet selection mode
        game.handle_key('y')
        # pending_trade_req still exists with _accepting flag
        assert game.pending_trade_req is not None
        assert game.pending_trade_req.get('_accepting') is True

        # Press '1' to select pet index 0 and accept
        game.handle_key('1')

        # Verify MSG_TRADE_ACK sent
        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_ACK]
        assert len(ack_calls) == 1
        payload = ack_calls[0][2]
        assert payload['accepted'] is True
        # pending_trade_req cleared
        assert game.pending_trade_req is None

    def test_handle_key_n_rejects_trade(self, game):
        """When pending_trade_req exists and key == 'n': calls accept_trade
        with accepted=False, sends MSG_TRADE_ACK, clears pending_trade_req."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        trade_req = _make_trade_req()
        game.pending_trade_req = trade_req

        game.handle_key('n')

        # Verify MSG_TRADE_ACK sent
        ack_calls = [c for c in fake_node.send_calls if c[1] == MSG_TRADE_ACK]
        assert len(ack_calls) == 1
        payload = ack_calls[0][2]
        assert payload['accepted'] is False
        # pending_trade_req cleared
        assert game.pending_trade_req is None


# ─── Task 14: render_lan_lines HP display ───────────────────────────────────


class TestRenderLanLinesHpDisplay:
    """render_lan_lines shows current pet HP when LAN is enabled."""

    def test_render_lan_lines_includes_hp_display(self, game):
        """When LAN is enabled, render_lan_lines includes a line showing
        'Pet HP: {hp}/100'."""
        _enable_lan_with_fake(game, 'alice')
        game.state['hp'] = 73

        win_mod = _load_win_module()
        lines = win_mod.render_lan_lines(game)

        # At least one line should mention HP
        hp_lines = [l for l in lines if 'HP' in str(l[0])]
        assert len(hp_lines) >= 1
        # The HP value should appear in the text
        assert any('73' in str(l[0]) for l in hp_lines)


# ─── Bug 3: Gift item inventory display + receive message ────────────────────


class TestBug3GiftItemRendering:
    """Bug 3: Verify gift_item submode rendering and receive message display."""

    def test_lan_submode_returns_gift_item_when_in_submode(self, game):
        """Bug 3 Problem 1: game.lan_submode should return 'gift_item' when
        the LanState is in the gift_item submode."""
        from ascii_pet.states import LanState
        _enable_lan_with_fake(game, 'alice')
        # Switch to LAN mode
        game.mode = 'lan'
        # Set the submode to gift_item
        game.lan_submode = 'gift_item'
        # Verify the property returns the correct value
        assert game.lan_submode == 'gift_item'

    def test_render_lan_lines_shows_gift_item_inventory(self, game):
        """Bug 3 Problem 1: render_lan_lines should show inventory items with
        correct counts when in gift_item submode."""
        _enable_lan_with_fake(game, 'alice')
        # Add items to inventory
        game.pets_data['inventory'] = {'apple': 5, 'toy': 2}
        # Switch to LAN mode and gift_item submode
        game.mode = 'lan'
        game.lan_submode = 'gift_item'

        win_mod = _load_win_module()
        lines = win_mod.render_lan_lines(game)

        # Should show "Select item to gift:" or similar
        text_lines = [str(l[0]) for l in lines]
        # Should contain the item count '5' for apple
        assert any('5' in t for t in text_lines), f"Expected count '5' in lines: {text_lines}"
        # Should contain the item count '2' for toy
        assert any('2' in t for t in text_lines), f"Expected count '2' in lines: {text_lines}"

    def test_render_lan_lines_shows_game_message(self, game):
        """Bug 3 Problem 2: render_lan_lines should show game.message so the
        receiver can see 'Received item' messages."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        # Set a message as if a gift was received
        game.message = 'Received 1 Apple from Bob!'
        game.message_time = time.time()

        win_mod = _load_win_module()
        lines = win_mod.render_lan_lines(game)

        # The message should appear in the rendered lines
        text_lines = [str(l[0]) for l in lines]
        assert any('Received 1 Apple from Bob!' in t for t in text_lines), \
            f"Expected 'Received 1 Apple from Bob!' in lines: {text_lines}"

    def test_render_lan_lines_shows_gift_received_message_after_gift(self, game):
        """Bug 3 Problem 2: After receiving a GIFT_ITEM message, the rendered
        LAN panel should show the 'Received' message."""
        fake_node = _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        # Add some initial inventory to avoid "Inventory full!"
        game.pets_data['inventory'] = {}

        # Simulate receiving a gift
        fake_node.ui_queue.put({
            'type': MSG_GIFT_ITEM,
            'payload': {
                'from': 'peer-1',
                'from_username': 'Bob',
                'item_id': 'apple',
                'count': 1,
            },
        })
        game.process_lan_queues()

        # The message should be set
        assert 'Received' in game.message
        assert 'Bob' in game.message

        # Render the LAN panel
        win_mod = _load_win_module()
        lines = win_mod.render_lan_lines(game)

        # The message should appear in the rendered lines
        text_lines = [str(l[0]) for l in lines]
        assert any('Received' in t for t in text_lines), \
            f"Expected 'Received' in lines: {text_lines}"


# ─── Bug 4: Trade pet selection rendering + timeout ──────────────────────────


class TestBug4TradePetSelectionRendering:
    """Bug 4: Verify trade pet selection rendering and pending_trade_req timeout."""

    def test_render_lan_lines_shows_pet_list_when_accepting_trade(self, game):
        """Bug 4 Problem 3: When pending_trade_req has _accepting=True, the
        LAN panel should show the pet list for selection."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        # Set up pending_trade_req in accepting mode
        game.pending_trade_req = {
            'from': 'peer-1',
            'from_username': 'Bob',
            'pet_snapshot': {'name': 'BobPet'},
            '_accepting': True,
        }

        win_mod = _load_win_module()
        lines = win_mod.render_lan_lines(game)

        # Should show "Select pet to trade" or similar
        text_lines = [str(l[0]) for l in lines]
        assert any('Select pet' in t or 'select pet' in t.lower() for t in text_lines), \
            f"Expected 'Select pet' in lines: {text_lines}"
        # Should show pet names from pets_data
        pet_names = [p['name'] for p in game.pets_data['pets']]
        for name in pet_names[:3]:
            assert any(name in t for t in text_lines), \
                f"Expected pet name '{name}' in lines: {text_lines}"

    def test_render_lan_lines_shows_trade_pet_submode(self, game):
        """Bug 4 Problem 3: When in trade_pet submode (initiator side), the
        LAN panel should show the pet list for selection."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        # Set the submode to trade_pet
        game.lan_submode = 'trade_pet'

        win_mod = _load_win_module()
        lines = win_mod.render_lan_lines(game)

        # Should show "Select pet to trade" or similar
        text_lines = [str(l[0]) for l in lines]
        assert any('Select pet' in t or 'select pet' in t.lower() for t in text_lines), \
            f"Expected 'Select pet' in lines: {text_lines}"
        # Should show pet names from pets_data
        pet_names = [p['name'] for p in game.pets_data['pets']]
        for name in pet_names[:3]:
            assert any(name in t for t in text_lines), \
                f"Expected pet name '{name}' in lines: {text_lines}"


class TestBug4TradePendingTimeout:
    """Bug 4 Problem 2: pending_trade_req should timeout after 30 seconds."""

    def test_check_pending_trade_timeout_clears_after_30s(self, game):
        """Bug 4: check_pending_trade_timeout should clear pending_trade_req
        after 30 seconds."""
        _enable_lan_with_fake(game, 'alice')
        game.pending_trade_req = {
            'from': 'peer-1',
            'from_username': 'Bob',
            'pet_snapshot': {'name': 'BobPet'},
            'start_time': time.time() - 31,  # 31 seconds ago
        }
        game.check_pending_trade_timeout()
        assert game.pending_trade_req is None
        assert game.message is not None

    def test_check_pending_trade_timeout_not_triggered_within_30s(self, game):
        """Bug 4: check_pending_trade_timeout should NOT clear pending_trade_req
        within 30 seconds."""
        _enable_lan_with_fake(game, 'alice')
        game.pending_trade_req = {
            'from': 'peer-1',
            'from_username': 'Bob',
            'pet_snapshot': {'name': 'BobPet'},
            'start_time': time.time() - 10,  # 10 seconds ago
        }
        game.check_pending_trade_timeout()
        assert game.pending_trade_req is not None

    def test_tick_calls_check_pending_trade_timeout(self, game):
        """Bug 4: tick() should call check_pending_trade_timeout to clear
        stale pending_trade_req."""
        _enable_lan_with_fake(game, 'alice')
        game.pending_trade_req = {
            'from': 'peer-1',
            'from_username': 'Bob',
            'pet_snapshot': {'name': 'BobPet'},
            'start_time': time.time() - 31,  # 31 seconds ago
        }
        # tick() should clear the pending_trade_req via timeout
        game.tick()
        assert game.pending_trade_req is None
