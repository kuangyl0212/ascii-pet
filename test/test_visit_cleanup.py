#!/usr/bin/env python3
"""TDD tests for Bug 1: Visit cleanup issues.

Bug 1.1: When the visit initiator ends the visit, the visited party's
being_visited is not cleared properly (VISIT_END not syncing).

Bug 1.2: visitor_pets grows without proper cleanup — name-based matching
is unreliable and duplicates accumulate.

Fix plan:
- Change visitor_pets from list to dict keyed by node_id
- VISIT_END handler uses node_id from payload to remove from visitor_pets
- end_visit() in core.py sends VISIT_END with "from" node_id
- end_visit() clears visitor_pets entry for the target node_id on initiator side
"""
import os
import sys
import time
import queue
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame
from ascii_pet.protocol import (
    MSG_VISIT_REQ, MSG_VISIT_END, MSG_VISIT_LEAVE,
    make_pet_snapshot,
)


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-visit-cleanup-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


def _make_snapshot(name='VisitorPet', owner='visitor-owner', species='cat'):
    """Build a minimal pet snapshot dict matching make_pet_snapshot output."""
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


# ─── Bug 1.1: VISIT_END should clear being_visited on the visited party ───


class TestVisitEndSyncsToVisitedParty:
    """When the initiator ends a visit, the visited party's being_visited
    should be cleared when it receives the VISIT_END message.

    The VISIT_END payload must include the "from" node_id so the visited
    party can use it to clean up visitor_pets by node_id instead of by name.
    """

    def test_visit_end_payload_includes_from_node_id(self, game):
        """VISIT_END sent by initiator should include 'from' node_id in payload."""
        game.active_visit = {
            'target': 'peer-bob',
            'start_time': time.time(),
            'pet_snapshot': _make_snapshot(name='AlicePet'),
        }

        game.end_visit()

        end_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_END]
        assert len(end_calls) == 1
        peer_id, msg_type, payload = end_calls[0]
        assert peer_id == 'peer-bob'
        # BUG: current code sends {"reason": "manual"} without "from" field
        assert 'from' in payload, (
            "VISIT_END payload must include 'from' node_id for reliable cleanup"
        )

    def test_visit_end_clears_being_visited_on_receiver(self, game):
        """When visited party receives VISIT_END with 'from', being_visited is cleared."""
        snap = _make_snapshot(name='AlicePet', owner='fake-node-alice')
        game.being_visited = {
            'from': 'fake-node-alice',
            'start_time': time.time(),
            'pet_snapshot': snap,
        }
        game.visitor_pets = {'fake-node-alice': snap}

        # Simulate receiving VISIT_END from the initiator
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual', 'from': 'fake-node-alice'},
        })

        game.process_lan_queues()

        assert game.being_visited is None, (
            "being_visited should be cleared when VISIT_END is received"
        )

    def test_visit_end_removes_visitor_from_visitor_pets_by_node_id(self, game):
        """When visited party receives VISIT_END, visitor is removed from
        visitor_pets using node_id, not name."""
        snap = _make_snapshot(name='AlicePet', owner='fake-node-alice')
        game.being_visited = {
            'from': 'fake-node-alice',
            'start_time': time.time(),
            'pet_snapshot': snap,
        }
        game.visitor_pets = {'fake-node-alice': snap}

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual', 'from': 'fake-node-alice'},
        })

        game.process_lan_queues()

        assert 'fake-node-alice' not in game.visitor_pets, (
            "visitor_pets entry should be removed by node_id on VISIT_END"
        )


# ─── Bug 1.2: visitor_pets should be a dict keyed by node_id ───


class TestVisitorPetsDict:
    """visitor_pets should be a dict {node_id: snapshot} instead of a list.

    This prevents:
    - Duplicate entries when the same pet visits multiple times
    - Unreliable name-based matching for removal
    """

    def test_visitor_pets_is_dict(self, game):
        """visitor_pets should be a dict, not a list."""
        assert isinstance(game.visitor_pets, dict), (
            "visitor_pets should be a dict {node_id: snapshot}"
        )

    def test_visit_req_stores_by_node_id(self, game):
        """VISIT_REQ should store visitor snapshot keyed by from node_id."""
        snap = _make_snapshot(name='Buddy', owner='peer-bob')
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-bob',
                'from_username': 'Bob',
                'pet_snapshot': snap,
            },
        })

        game.process_lan_queues()

        assert 'peer-bob' in game.visitor_pets, (
            "visitor_pets should be keyed by node_id 'peer-bob'"
        )
        assert game.visitor_pets['peer-bob']['name'] == 'Buddy'

    def test_duplicate_visit_req_overwrites_not_accumulates(self, game):
        """Receiving two VISIT_REQ from the same node_id should overwrite,
        not accumulate duplicates."""
        snap1 = _make_snapshot(name='Buddy', owner='peer-bob', species='cat')
        snap2 = _make_snapshot(name='Buddy', owner='peer-bob', species='dragon')

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-bob',
                'from_username': 'Bob',
                'pet_snapshot': snap1,
            },
        })
        game.process_lan_queues()

        # Second visit from same node
        game.being_visited = None  # Reset for next visit
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-bob',
                'from_username': 'Bob',
                'pet_snapshot': snap2,
            },
        })
        game.process_lan_queues()

        # Should have only ONE entry for peer-bob, not two
        assert len(game.visitor_pets) == 1, (
            f"visitor_pets should have 1 entry for peer-bob, got {len(game.visitor_pets)}"
        )
        assert game.visitor_pets['peer-bob']['species'] == 'dragon', (
            "Second visit should overwrite the first"
        )

    def test_multiple_visitors_stored_separately(self, game):
        """Multiple visitors from different node_ids are stored separately."""
        snap1 = _make_snapshot(name='Buddy', owner='peer-bob')
        snap2 = _make_snapshot(name='Mittens', owner='peer-carol')

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-bob',
                'from_username': 'Bob',
                'pet_snapshot': snap1,
            },
        })
        game.process_lan_queues()

        # Second visit from different node (reset being_visited for next)
        game.being_visited = None
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-carol',
                'from_username': 'Carol',
                'pet_snapshot': snap2,
            },
        })
        game.process_lan_queues()

        assert len(game.visitor_pets) == 2
        assert 'peer-bob' in game.visitor_pets
        assert 'peer-carol' in game.visitor_pets


# ─── Bug 1.1 extended: end_visit() should also clear visitor_pets for initiator ───


class TestEndVisitClearsVisitorPetsForInitiator:
    """When the initiator calls end_visit(), it should also clean up any
    visitor_pets entries from the target node.

    This handles the case where the initiator was previously visited by
    the same peer and the visitor_pets entry was not cleaned up.
    """

    def test_end_visit_as_initiator_clears_visitor_pets_for_target(self, game):
        """When initiator ends visit, visitor_pets entry for the target should be removed."""
        snap = _make_snapshot(name='BobPet', owner='peer-bob')
        game.visitor_pets = {'peer-bob': snap}
        game.active_visit = {
            'target': 'peer-bob',
            'start_time': time.time(),
            'pet_snapshot': _make_snapshot(name='AlicePet'),
        }

        game.end_visit()

        assert 'peer-bob' not in game.visitor_pets, (
            "end_visit() should remove visitor_pets entry for the target node"
        )

    def test_end_visit_as_receiver_clears_visitor_pets_by_node_id(self, game):
        """When receiver ends visit, visitor_pets entry is removed by node_id."""
        snap = _make_snapshot(name='AlicePet', owner='fake-node-alice')
        game.being_visited = {
            'from': 'peer-bob',
            'start_time': time.time(),
            'pet_snapshot': snap,
        }
        game.visitor_pets = {'peer-bob': snap}

        game.end_visit()

        assert 'peer-bob' not in game.visitor_pets, (
            "end_visit() as receiver should remove visitor_pets by node_id"
        )


# ─── VISIT_LEAVE should also use node_id ───


class TestVisitLeaveByNodeId:
    """VISIT_LEAVE (legacy) should also use node_id for removal when available."""

    def test_visit_leave_removes_by_node_id(self, game):
        """VISIT_LEAVE should remove visitor_pets entry by node_id."""
        snap = _make_snapshot(name='Buddy', owner='peer-bob')
        game.visitor_pets = {'peer-bob': snap}

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_LEAVE,
            'payload': {'pet_name': 'Buddy', 'from': 'peer-bob'},
        })

        game.process_lan_queues()

        assert 'peer-bob' not in game.visitor_pets, (
            "VISIT_LEAVE should remove visitor by node_id"
        )


# ─── disable_lan should clear visitor_pets as dict ───


class TestDisableLanClearsVisitorPetsDict:
    """disable_lan should reset visitor_pets to empty dict."""

    def test_disable_lan_clears_visitor_pets_dict(self, game):
        """disable_lan should clear visitor_pets to empty dict."""
        snap = _make_snapshot(name='Buddy', owner='peer-bob')
        game.visitor_pets = {'peer-bob': snap}

        game.disable_lan()

        assert game.visitor_pets == {}, (
            "disable_lan should clear visitor_pets to empty dict"
        )


# ─── receive_visitor should use node_id ───


class TestReceiveVisitorByNodeId:
    """receive_visitor should store by node_id when available."""

    def test_receive_visitor_stores_by_owner(self, game):
        """receive_visitor should use snapshot's 'owner' field as key."""
        snap = _make_snapshot(name='Buddy', owner='peer-bob')
        game.receive_visitor(snap)

        assert 'peer-bob' in game.visitor_pets, (
            "receive_visitor should store by owner (node_id)"
        )

    def test_receive_visitor_overwrites_existing(self, game):
        """receive_visitor with same owner should overwrite, not accumulate."""
        snap1 = _make_snapshot(name='Buddy', owner='peer-bob', species='cat')
        snap2 = _make_snapshot(name='Buddy', owner='peer-bob', species='dragon')

        game.receive_visitor(snap1)
        game.receive_visitor(snap2)

        assert len(game.visitor_pets) == 1
        assert game.visitor_pets['peer-bob']['species'] == 'dragon'


# ─── dismiss_visitor should work with dict ───


class TestDismissVisitorDict:
    """dismiss_visitor should work with dict-based visitor_pets."""

    def test_dismiss_visitor_by_node_id(self, game):
        """dismiss_visitor should remove visitor by node_id."""
        snap = _make_snapshot(name='Buddy', owner='peer-bob')
        game.visitor_pets = {'peer-bob': snap}

        result = game.dismiss_visitor('peer-bob')

        assert result is True
        assert 'peer-bob' not in game.visitor_pets

    def test_dismiss_visitor_invalid_node_id_returns_false(self, game):
        """dismiss_visitor with unknown node_id returns False."""
        game.visitor_pets = {'peer-bob': _make_snapshot(name='Buddy', owner='peer-bob')}

        result = game.dismiss_visitor('peer-unknown')

        assert result is False
        assert len(game.visitor_pets) == 1

    def test_dismiss_visitor_sends_visit_leave(self, game):
        """dismiss_visitor should send VISIT_LEAVE to the visitor's owner."""
        snap = _make_snapshot(name='Buddy', owner='peer-bob')
        game.visitor_pets = {'peer-bob': snap}

        game.dismiss_visitor('peer-bob')

        leave_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_LEAVE]
        assert len(leave_calls) == 1
        peer_id, msg_type, payload = leave_calls[0]
        assert peer_id == 'peer-bob'
        assert payload.get('pet_name') == 'Buddy'
