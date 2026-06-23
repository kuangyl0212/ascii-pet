"""Tests for visit message display on the visited side.

When Player A sends remote feed/play to Player B, Player B should see
the visit message displayed (not overwritten by tick warnings).
"""
import os, sys, time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame, generate_companion, init_state


def _uid():
    return f'test-visit-msg-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


@pytest.fixture
def game(tmp_path):
    uid = _uid()
    g = PetGame(uid, data_dir=tmp_path)
    yield g


@pytest.fixture
def game_with_low_stats(tmp_path):
    """Game with low hunger to trigger warning messages from tick()."""
    uid = _uid()
    g = PetGame(uid, data_dir=tmp_path)
    g.state['stats']['HUNGER'] = 5
    yield g


class TestVisitMessageNotOverwritten:
    """Visit messages should not be overwritten by tick() warnings."""

    def _simulate_on_timer(self, game):
        """Simulate what on_timer() does: tick + process_lan_queues."""
        msg, msg_time = game.tick()
        if msg:
            game.message = msg
            game.message_time = msg_time
        game.process_lan_queues()

    def test_visit_feed_message_survives_tick(self, game_with_low_stats):
        """After receiving visit feed, message should persist despite tick warnings."""
        g = game_with_low_stats
        g.lan_enabled = True

        from queue import Queue
        g.lan_node = MagicMock()
        g.lan_node.ui_queue = Queue()
        g.lan_node.ui_queue.put({'type': 'visit_feed', 'payload': {'from': 'friend'}})

        # First timer tick - processes visit message
        self._simulate_on_timer(g)
        assert g.message is not None
        assert 'friend' in g.message
        visit_msg = g.message

        # Second timer tick - tick() returns warning, should NOT overwrite visit message
        self._simulate_on_timer(g)
        assert g.message == visit_msg, (
            f"Visit message '{visit_msg}' was overwritten by tick warning"
        )

    def test_visit_play_message_survives_tick(self, game_with_low_stats):
        """After receiving visit play, message should persist despite tick warnings."""
        g = game_with_low_stats
        g.lan_enabled = True

        from queue import Queue
        g.lan_node = MagicMock()
        g.lan_node.ui_queue = Queue()
        g.lan_node.ui_queue.put({'type': 'visit_play', 'payload': {'from': 'friend'}})

        self._simulate_on_timer(g)
        assert g.message is not None
        assert 'friend' in g.message
        visit_msg = g.message

        self._simulate_on_timer(g)
        assert g.message == visit_msg

    def test_visit_req_message_survives_tick(self, game_with_low_stats):
        """After receiving visit request, message should persist despite tick warnings."""
        g = game_with_low_stats
        g.lan_enabled = True

        from queue import Queue
        g.lan_node = MagicMock()
        g.lan_node.ui_queue = Queue()
        g.lan_node.ui_queue.put({
            'type': 'visit_req',
            'payload': {
                'from': 'peer-id',
                'from_username': 'friend',
                'pet_snapshot': {'name': 'Buddy', 'species': 'cat'},
            }
        })

        self._simulate_on_timer(g)
        assert g.message is not None
        assert 'friend' in g.message
        visit_msg = g.message

        self._simulate_on_timer(g)
        assert g.message == visit_msg
