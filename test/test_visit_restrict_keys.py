#!/usr/bin/env python3
"""TDD tests for visit state-switching restrictions.

Redesign-visit-lifecycle spec:
- During a visit, user can only be in CompactState or ExpandedState
- Pressing 't'/'a'/'u'/'l' during a visit shows a prompt to end visit first
- 'c'/Enter still switches compact<->expanded during visit
- 'e'/'f'/'p' still work during visit
- After visit ends, state switching works normally again
"""
import os
import sys
import time
import queue
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame
from ascii_pet.protocol import MSG_VISIT_END
from ascii_pet.states import (
    ExpandedState, CompactState, StatsState, AchievementsState,
    ItemsState, LanState,
)


def _uid():
    return f'test-visit-restrict-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


def _make_snapshot(name='VisitorPet', owner='visitor-owner', species='cat'):
    return {
        'name': name,
        'species': species,
        'rarity': 'common',
        'level': 1,
        'shiny': False,
        'eye': '·',
        'hat': 'none',
        'mood': 'normal',
        'owner': owner,
    }


class _FakeLanNode:
    """Fake LanNode for testing without real network."""

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
        self._peers = []
        self.send_calls = []

    def start(self):
        self._status['enabled'] = True
        self._status['is_master'] = True
        return True

    def stop(self):
        self._status['enabled'] = False

    def get_status(self):
        return dict(self._status)

    def get_peers(self):
        return list(self._peers)

    def send_to_peer(self, peer_node_id, msg_type, payload):
        self.send_calls.append((peer_node_id, msg_type, payload))
        return True

    def send_broadcast(self, msg_type, payload):
        return True


@pytest.fixture
def game(tmp_path):
    """Provide a fresh PetGame with isolated temp dir and LAN enabled."""
    uid = _uid()
    g = PetGame(uid, data_dir=tmp_path)
    fake_node = _FakeLanNode('alice', g.state)
    with patch('ascii_pet.lan.LanNode', return_value=fake_node):
        g.enable_lan('alice')
    return g


def _set_active_visit(game, target='peer-bob'):
    game.active_visit = {
        'target': target,
        'start_time': time.time(),
        'pet_snapshot': _make_snapshot(name='AlicePet'),
        'last_heartbeat': time.time(),
    }
    game.visitor_pets[target] = _make_snapshot(name='BobPet', owner=target)


def _set_being_visited(game, from_id='fake-node-bob'):
    snap = _make_snapshot(name='BobPet', owner=from_id)
    game.being_visited = {
        'from': from_id,
        'start_time': time.time(),
        'pet_snapshot': snap,
        'last_heartbeat': time.time(),
    }
    game.visitor_pets[from_id] = snap


# ─── ExpandedState: blocked keys during visit ───


class TestExpandedStateBlockedKeys:
    """In ExpandedState during a visit, 't'/'a'/'u'/'l' are blocked."""

    def test_visit_blocks_t_key_in_expanded(self, game):
        """Pressing 't' during visit in ExpandedState does not switch to StatsState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game)

        game.handle_key('t')

        current = game._inner_state()
        assert isinstance(current, ExpandedState), (
            f"Should stay in ExpandedState, got {type(current).__name__}"
        )
        assert not isinstance(current, StatsState)

    def test_visit_blocks_a_key_in_expanded(self, game):
        """Pressing 'a' during visit in ExpandedState does not switch to AchievementsState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game)

        game.handle_key('a')

        current = game._inner_state()
        assert isinstance(current, ExpandedState)
        assert not isinstance(current, AchievementsState)

    def test_visit_blocks_u_key_in_expanded(self, game):
        """Pressing 'u' during visit in ExpandedState does not switch to ItemsState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game)

        game.handle_key('u')

        current = game._inner_state()
        assert isinstance(current, ExpandedState)
        assert not isinstance(current, ItemsState)

    def test_visit_blocks_l_key_in_expanded(self, game):
        """Pressing 'l' during visit in ExpandedState does not switch to LanState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game)

        game.handle_key('l')

        current = game._inner_state()
        assert isinstance(current, ExpandedState)
        assert not isinstance(current, LanState)

    def test_blocked_key_shows_end_visit_prompt(self, game):
        """Pressing a blocked key shows 'Please end the visit first' message."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game)

        game.handle_key('t')

        assert 'end the visit' in game.message.lower(), (
            f"Expected 'Please end the visit first' message, got: {game.message!r}"
        )


# ─── CompactState: blocked keys during visit ───


class TestCompactStateBlockedKeys:
    """In CompactState during a visit, 't'/'a'/'u'/'l' are blocked."""

    def test_visit_blocks_t_key_in_compact(self, game):
        """Pressing 't' during visit in CompactState does not switch to StatsState."""
        _set_active_visit(game)

        game.handle_key('t')

        current = game._inner_state()
        assert isinstance(current, CompactState)
        assert not isinstance(current, StatsState)

    def test_visit_blocks_a_key_in_compact(self, game):
        """Pressing 'a' during visit in CompactState does not switch to AchievementsState."""
        _set_active_visit(game)

        game.handle_key('a')

        current = game._inner_state()
        assert isinstance(current, CompactState)
        assert not isinstance(current, AchievementsState)

    def test_visit_blocks_u_key_in_compact(self, game):
        """Pressing 'u' during visit in CompactState does not switch to ItemsState."""
        _set_active_visit(game)

        game.handle_key('u')

        current = game._inner_state()
        assert isinstance(current, CompactState)
        assert not isinstance(current, ItemsState)

    def test_visit_blocks_l_key_in_compact(self, game):
        """Pressing 'l' during visit in CompactState does not switch to LanState."""
        _set_active_visit(game)

        game.handle_key('l')

        current = game._inner_state()
        assert isinstance(current, CompactState)
        assert not isinstance(current, LanState)

    def test_blocked_key_shows_end_visit_prompt(self, game):
        """Pressing a blocked key shows 'Please end the visit first' message."""
        _set_active_visit(game)

        game.handle_key('t')

        assert 'end the visit' in game.message.lower(), (
            f"Expected 'Please end the visit first' message, got: {game.message!r}"
        )


# ─── Being_visited also blocks ───


class TestBeingVisitedBlocksKeys:
    """being_visited also blocks state-switching keys."""

    def test_being_visited_blocks_t_in_expanded(self, game):
        """Pressing 't' while being_visited does not switch to StatsState."""
        game.sm.transition_to(game, ExpandedState())
        _set_being_visited(game)

        game.handle_key('t')

        current = game._inner_state()
        assert isinstance(current, ExpandedState)


# ─── Allowed keys during visit ───


class TestAllowedKeysDuringVisit:
    """Some keys still work during a visit."""

    def test_c_key_switches_expanded_to_compact_during_visit(self, game):
        """Pressing 'c' during visit switches ExpandedState -> CompactState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game)

        game.handle_key('c')

        current = game._inner_state()
        assert isinstance(current, CompactState), (
            f"'c' should switch to CompactState during visit, got {type(current).__name__}"
        )

    def test_enter_key_switches_expanded_to_compact_during_visit(self, game):
        """Pressing Enter during visit switches ExpandedState -> CompactState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game)

        game.handle_key('\r')

        current = game._inner_state()
        assert isinstance(current, CompactState), (
            f"Enter should switch to CompactState during visit, got {type(current).__name__}"
        )

    def test_e_key_ends_visit_in_expanded(self, game):
        """Pressing 'e' during visit in ExpandedState ends the visit."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game)

        game.handle_key('e')

        assert game.active_visit is None
        current = game._inner_state()
        assert isinstance(current, ExpandedState)


# ─── After visit ends, keys work normally ───


class TestKeysWorkAfterVisitEnds:
    """After a visit ends, state-switching keys work normally."""

    def test_t_works_after_visit_ends(self, game):
        """Pressing 't' after visit ends switches to StatsState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game)
        game.handle_key('e')  # end visit
        assert game.active_visit is None

        game.handle_key('t')

        current = game._inner_state()
        assert isinstance(current, StatsState), (
            f"'t' should switch to StatsState after visit ends, got {type(current).__name__}"
        )

    def test_a_works_after_visit_ends(self, game):
        """Pressing 'a' after visit ends switches to AchievementsState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game)
        game.handle_key('e')

        game.handle_key('a')

        current = game._inner_state()
        assert isinstance(current, AchievementsState)

    def test_u_works_after_visit_ends(self, game):
        """Pressing 'u' after visit ends switches to ItemsState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game)
        game.handle_key('e')

        game.handle_key('u')

        current = game._inner_state()
        assert isinstance(current, ItemsState)

    def test_l_works_after_visit_ends(self, game):
        """Pressing 'l' after visit ends switches to LanState."""
        game.sm.transition_to(game, ExpandedState())
        _set_active_visit(game)
        game.handle_key('e')

        game.handle_key('l')

        current = game._inner_state()
        assert isinstance(current, LanState)
