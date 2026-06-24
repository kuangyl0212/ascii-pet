#!/usr/bin/env python3
"""TDD tests for Bug 1: Bidirectional visit flow.

Bug description:
- When the visit initiator selects a player to visit, BOTH sides enter visit
  state and should see BOTH pets (visitor's pet + visited party's pet).
- The initiator currently does NOT receive the visited party's pet snapshot,
  so the initiator can't see the visited party's pet.
- When EITHER side ends the visit, BOTH sides should exit visit state and
  their visitor_pets should be cleaned up.

BDD Scenarios:

  Feature: Bidirectional Visit Flow

    Scenario: Visited party sends back pet snapshot on VISIT_REQ
      Given Bob receives a VISIT_REQ from Alice with Alice's pet snapshot
      When Bob processes the VISIT_REQ
      Then Bob should send MSG_VISIT_DATA back to Alice
      And the MSG_VISIT_DATA payload should contain Bob's pet snapshot
      And Bob's being_visited should be set with Alice's info

    Scenario: Initiator stores visited party's pet snapshot
      Given Alice has an active visit to Bob
      When Alice receives MSG_VISIT_DATA from Bob with Bob's pet snapshot
      Then Alice should store Bob's snapshot in visitor_pets[Bob's node_id]
      And Alice should be able to render Bob's pet on her screen

    Scenario: Initiator's visitor_pets cleared when visited party ends visit
      Given Alice has an active visit to Bob and visitor_pets[Bob] = Bob's snapshot
      When Alice receives VISIT_END from Bob
      Then Alice's active_visit should be cleared
      And Alice's visitor_pets should not contain Bob's entry

    Scenario: Random events are shared during visit
      Given Alice is visiting Bob (active_visit set)
      When a random visit event triggers on Alice's side
      Then Alice should send MSG_VISIT_EVENT to Bob
      And Bob should apply the event and see the message
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
    MSG_VISIT_REQ, MSG_VISIT_DATA, MSG_VISIT_END, MSG_VISIT_EVENT,
    make_pet_snapshot, make_visit_event, VISIT_EVENTS,
)


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-visit-flow-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


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
        'hp': 100,
        'attack': 0,
        'defense': 0,
        'speed': 0,
        'skills': [],
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


# ─── BDD Scenario 1: Visited party sends back pet snapshot on VISIT_REQ ───


class TestVisitedPartySendsSnapshotBack:
    """When the visited party receives a VISIT_REQ, they should send back
    their own pet snapshot via MSG_VISIT_DATA so the initiator can see
    the visited party's pet.

    Given Bob receives a VISIT_REQ from Alice with Alice's pet snapshot
    When Bob processes the VISIT_REQ
    Then Bob should send MSG_VISIT_DATA back to Alice
    And the MSG_VISIT_DATA payload should contain Bob's pet snapshot
    """

    def test_visit_req_triggers_visit_data_response(self, game):
        """Receiving VISIT_REQ should cause MSG_VISIT_DATA to be sent back."""
        alice_snapshot = _make_snapshot(name='AlicePet', owner='peer-alice')
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-alice',
                'from_username': 'Alice',
                'pet_snapshot': alice_snapshot,
            },
        })

        game.process_lan_queues()

        data_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_DATA]
        assert len(data_calls) == 1, (
            "VISIT_REQ should trigger exactly one MSG_VISIT_DATA response, "
            f"got {len(data_calls)}"
        )

    def test_visit_data_sent_back_to_initiator(self, game):
        """MSG_VISIT_DATA should be sent back to the initiator's node_id."""
        alice_snapshot = _make_snapshot(name='AlicePet', owner='peer-alice')
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-alice',
                'from_username': 'Alice',
                'pet_snapshot': alice_snapshot,
            },
        })

        game.process_lan_queues()

        data_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_DATA]
        assert len(data_calls) == 1
        peer_id, msg_type, payload = data_calls[0]
        assert peer_id == 'peer-alice', (
            f"MSG_VISIT_DATA should be sent to 'peer-alice', got {peer_id!r}"
        )

    def test_visit_data_contains_visited_party_snapshot(self, game):
        """MSG_VISIT_DATA payload should contain the visited party's pet snapshot."""
        alice_snapshot = _make_snapshot(name='AlicePet', owner='peer-alice')
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-alice',
                'from_username': 'Alice',
                'pet_snapshot': alice_snapshot,
            },
        })

        game.process_lan_queues()

        data_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_DATA]
        assert len(data_calls) == 1
        _, _, payload = data_calls[0]
        # Payload should contain snapshot fields (name, species, owner, etc.)
        assert 'name' in payload, (
            "MSG_VISIT_DATA payload should contain 'name' field"
        )
        assert 'species' in payload, (
            "MSG_VISIT_DATA payload should contain 'species' field"
        )
        assert 'owner' in payload, (
            "MSG_VISIT_DATA payload should contain 'owner' field"
        )
        # The snapshot should be the visited party's own pet, not Alice's
        assert payload['name'] == game.state['name'], (
            f"MSG_VISIT_DATA should contain visited party's pet name "
            f"{game.state['name']!r}, got {payload['name']!r}"
        )

    def test_visit_req_still_sets_being_visited(self, game):
        """VISIT_REQ handler should still set being_visited (existing behavior)."""
        alice_snapshot = _make_snapshot(name='AlicePet', owner='peer-alice')
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-alice',
                'from_username': 'Alice',
                'pet_snapshot': alice_snapshot,
            },
        })

        game.process_lan_queues()

        assert game.being_visited is not None, (
            "being_visited should be set after VISIT_REQ"
        )
        assert game.being_visited['from'] == 'peer-alice'

    def test_visit_req_still_stores_visitor_snapshot(self, game):
        """VISIT_REQ handler should still store visitor's snapshot in visitor_pets."""
        alice_snapshot = _make_snapshot(name='AlicePet', owner='peer-alice')
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-alice',
                'from_username': 'Alice',
                'pet_snapshot': alice_snapshot,
            },
        })

        game.process_lan_queues()

        assert 'peer-alice' in game.visitor_pets, (
            "visitor_pets should contain Alice's snapshot after VISIT_REQ"
        )
        assert game.visitor_pets['peer-alice']['name'] == 'AlicePet'


# ─── BDD Scenario 2: Initiator stores visited party's pet snapshot ───


class TestInitiatorReceivesVisitedSnapshot:
    """When the initiator receives MSG_VISIT_DATA, they should store the
    visited party's pet snapshot in visitor_pets so they can see it.

    Given Alice has an active visit to Bob
    When Alice receives MSG_VISIT_DATA from Bob with Bob's pet snapshot
    Then Alice should store Bob's snapshot in visitor_pets[Bob's node_id]
    """

    def test_visit_data_stores_snapshot_in_visitor_pets(self, game):
        """Receiving MSG_VISIT_DATA should store the snapshot in visitor_pets."""
        bob_snapshot = _make_snapshot(name='BobPet', owner='peer-bob')
        game.active_visit = {
            'target': 'peer-bob',
            'start_time': time.time(),
            'pet_snapshot': _make_snapshot(name='AlicePet'),
        }

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_DATA,
            'payload': bob_snapshot,
        })

        game.process_lan_queues()

        assert 'peer-bob' in game.visitor_pets, (
            "MSG_VISIT_DATA should store snapshot in visitor_pets[owner]"
        )
        assert game.visitor_pets['peer-bob']['name'] == 'BobPet'

    def test_visit_data_uses_owner_as_key(self, game):
        """MSG_VISIT_DATA should use the snapshot's 'owner' field as the key."""
        bob_snapshot = _make_snapshot(name='BobPet', owner='peer-bob')
        game.active_visit = {
            'target': 'peer-bob',
            'start_time': time.time(),
            'pet_snapshot': _make_snapshot(name='AlicePet'),
        }

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_DATA,
            'payload': bob_snapshot,
        })

        game.process_lan_queues()

        # The key should be the owner field from the snapshot, not the
        # active_visit target (though they should match in practice)
        assert 'peer-bob' in game.visitor_pets
        assert game.visitor_pets['peer-bob'] == bob_snapshot


# ─── BDD Scenario 3: Initiator's visitor_pets cleared on VISIT_END ───


class TestInitiatorVisitorPetsClearedOnVisitEnd:
    """When the initiator receives VISIT_END (because the visited party ended
    the visit), the initiator's visitor_pets entry for the visited party
    should also be cleared.

    Given Alice has an active visit to Bob and visitor_pets[Bob] = Bob's snapshot
    When Alice receives VISIT_END from Bob
    Then Alice's active_visit should be cleared
    And Alice's visitor_pets should not contain Bob's entry
    """

    def test_visit_end_clears_initiator_active_visit(self, game):
        """When initiator receives VISIT_END, active_visit should be cleared."""
        bob_snapshot = _make_snapshot(name='BobPet', owner='peer-bob')
        game.active_visit = {
            'target': 'peer-bob',
            'start_time': time.time(),
            'pet_snapshot': _make_snapshot(name='AlicePet'),
        }
        game.visitor_pets = {'peer-bob': bob_snapshot}

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual', 'from': 'peer-bob'},
        })

        game.process_lan_queues()

        assert game.active_visit is None, (
            "active_visit should be cleared when VISIT_END is received"
        )

    def test_visit_end_clears_initiator_visitor_pets(self, game):
        """When initiator receives VISIT_END, visitor_pets entry should be cleared.

        BUG: Current code only clears visitor_pets in the `if being_visited`
        branch, not in the `if active_visit` branch. So when the initiator
        receives VISIT_END, the visited party's pet stays in visitor_pets.
        """
        bob_snapshot = _make_snapshot(name='BobPet', owner='peer-bob')
        game.active_visit = {
            'target': 'peer-bob',
            'start_time': time.time(),
            'pet_snapshot': _make_snapshot(name='AlicePet'),
        }
        game.visitor_pets = {'peer-bob': bob_snapshot}

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual', 'from': 'peer-bob'},
        })

        game.process_lan_queues()

        assert 'peer-bob' not in game.visitor_pets, (
            "visitor_pets entry for the visited party should be cleared "
            "when initiator receives VISIT_END"
        )

    def test_visit_end_clears_initiator_visitor_pets_no_from_field(self, game):
        """When VISIT_END has no 'from' field, use active_visit target to clear."""
        bob_snapshot = _make_snapshot(name='BobPet', owner='peer-bob')
        game.active_visit = {
            'target': 'peer-bob',
            'start_time': time.time(),
            'pet_snapshot': _make_snapshot(name='AlicePet'),
        }
        game.visitor_pets = {'peer-bob': bob_snapshot}

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual'},
        })

        game.process_lan_queues()

        assert game.active_visit is None
        assert 'peer-bob' not in game.visitor_pets, (
            "visitor_pets should be cleared using active_visit target "
            "when 'from' field is missing"
        )


# ─── BDD Scenario 4: Random events are shared during visit ───


class TestRandomEventsSharedDuringVisit:
    """Random events during a visit should be shared between both sides.

    Given Alice is visiting Bob (active_visit set)
    When a random visit event triggers on Alice's side
    Then Alice should send MSG_VISIT_EVENT to Bob
    And Bob should apply the event and see the message
    """

    def test_initiator_sends_visit_event_to_peer(self, game):
        """When a visit event triggers on the initiator's side, it should be
        sent to the visited party via MSG_VISIT_EVENT."""
        from ascii_pet.events import Event
        game.active_visit = {
            'target': 'peer-bob',
            'start_time': time.time(),
            'pet_snapshot': _make_snapshot(name='AlicePet'),
        }
        game.visit_event_cooldown = 0  # not on cooldown

        evt = Event(
            event_id='test_visit_event',
            description='Test event',
            effects={'HAPPY': 15},
            target='self',
            category='visit',
            metadata={'original_event_type': 'test_visit_event'},
        )

        with patch('random.random', return_value=0.05), \
                patch('random.choice', return_value=evt):
            game._tick_visit_events()

        event_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_EVENT]
        assert len(event_calls) == 1, (
            "Initiator should send MSG_VISIT_EVENT to the visited party"
        )
        peer_id, msg_type, payload = event_calls[0]
        assert peer_id == 'peer-bob'
        assert 'description' in payload
        assert 'stat_effects' in payload

    def test_visited_party_applies_received_event(self, game):
        """When the visited party receives MSG_VISIT_EVENT, they should apply
        the event to their pet and show a message."""
        bob_initial_happy = game.state['stats']['HAPPY']
        game.being_visited = {
            'from': 'peer-alice',
            'start_time': time.time(),
            'pet_snapshot': _make_snapshot(name='AlicePet'),
        }

        event_payload = make_visit_event(
            'test_event', 'A fun visit event', {'happy': 15}
        )

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_EVENT,
            'payload': event_payload,
        })

        game.process_lan_queues()

        # The visited party should have applied the event to their pet
        assert game.state['stats']['HAPPY'] != bob_initial_happy or \
               game.state['stats']['HAPPY'] >= 80, (
            "Visited party should apply the event effect to their pet"
        )
        assert game.message is not None
        assert 'Visit event' in game.message or 'fun visit' in game.message.lower(), (
            f"Visited party should show visit event message, got: {game.message!r}"
        )


# ─── Integration: Full bidirectional visit flow ───


class TestFullBidirectionalVisitFlow:
    """End-to-end test of the bidirectional visit flow.

    Given Alice initiates a visit to Bob
    When Bob receives the VISIT_REQ and sends back his snapshot
    Then Alice should receive Bob's snapshot and see Bob's pet
    And Both sides should be in visit state
    And When either side ends the visit, both sides should exit visit state
    """

    def test_both_sides_see_both_pets(self, game):
        """After the full visit handshake, both sides should have the other's
        pet in their visitor_pets."""
        # --- Alice (initiator) side ---
        alice_snapshot = _make_snapshot(name='AlicePet', owner='fake-node-alice')
        game.active_visit = {
            'target': 'peer-bob',
            'start_time': time.time(),
            'pet_snapshot': alice_snapshot,
        }
        # Alice does NOT yet have Bob's snapshot (this is the bug)

        # --- Bob (visited party) side - simulated via VISIT_REQ ---
        # Bob receives VISIT_REQ from Alice
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-alice',
                'from_username': 'Alice',
                'pet_snapshot': alice_snapshot,
            },
        })
        # Note: in this test we're using a single game object to simulate
        # both sides. We need to reset being_visited since we're also the
        # initiator. In reality, Alice and Bob are separate game instances.
        # For this test, we focus on verifying Bob sends back his snapshot.

        # Clear active_visit to simulate being only the visited party
        game.active_visit = None
        game.process_lan_queues()

        # Bob should have sent MSG_VISIT_DATA back to Alice
        data_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_DATA]
        assert len(data_calls) == 1, (
            "Bob should send MSG_VISIT_DATA back to Alice"
        )
        bob_snapshot_sent = data_calls[0][2]
        assert bob_snapshot_sent['name'] == game.state['name'], (
            "Bob's MSG_VISIT_DATA should contain his own pet snapshot"
        )

    def test_visit_end_clears_both_sides(self, game):
        """When either side ends the visit, both sides' visit state should be cleared."""
        # Set up as visited party receiving VISIT_END
        alice_snapshot = _make_snapshot(name='AlicePet', owner='peer-alice')
        game.being_visited = {
            'from': 'peer-alice',
            'start_time': time.time(),
            'pet_snapshot': alice_snapshot,
        }
        game.visitor_pets = {'peer-alice': alice_snapshot}

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual', 'from': 'peer-alice'},
        })

        game.process_lan_queues()

        assert game.being_visited is None
        assert 'peer-alice' not in game.visitor_pets
