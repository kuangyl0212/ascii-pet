#!/usr/bin/env python3
"""End-to-end tests for the redesigned visit lifecycle.

Tests the complete visit lifecycle combining heartbeat, keep-state, and
state-switching restrictions using two interconnected PetGame instances.

BDD Scenarios:

  Feature: Visit Lifecycle (Redesigned)

    Scenario: Complete visit lifecycle with heartbeat
      Given Alice and Bob are connected via _MessageBus
      When Alice invites Bob to visit
      And both sides exchange heartbeats via _tick_visit_heartbeat
      Then both sides' last_heartbeat is updated
      When Alice presses 'e' to end visit
      And Bob processes the MSG_VISIT_END
      Then both sides clear visit state
      And both sides keep their current UI state (ExpandedState)

    Scenario: Heartbeat timeout auto-ends visit
      Given a visit is established between Alice and Bob
      When Bob disconnects (messages not delivered)
      And Alice's heartbeat timeout exceeds 15 seconds
      Then Alice's visit auto-ends with "connection lost" message
      And Alice stays in ExpandedState (no LanState transition)

    Scenario: Visit restrictions prevent state switching
      Given a visit is established between Alice and Bob
      When Alice presses 't' during the visit
      Then Alice stays in ExpandedState
      And Alice sees "Please end the visit first" message
      When Alice presses 'c' during the visit
      Then Alice switches to CompactState (allowed)
      When Alice presses 't' from CompactState
      Then Alice stays in CompactState (still blocked)
      When Alice ends the visit
      And Alice presses 't'
      Then Alice switches to StatsState (restriction lifted)
"""
import os
import sys
import time
import queue
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame
from ascii_pet.protocol import (
    MSG_VISIT_REQ, MSG_VISIT_DATA, MSG_VISIT_END, MSG_VISIT_HEARTBEAT,
)
from ascii_pet.states import (
    ExpandedState, CompactState, StatsState, LanState,
)


def _uid(prefix):
    return f'test-visit-lifecycle-{prefix}-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


class _MessageBus:
    """Simulated network message bus connecting two _FakeLanNode instances."""

    def __init__(self):
        self._nodes = {}
        self._deliver_enabled = True  # Can be disabled to simulate disconnect

    def register(self, node):
        self._nodes[node.node_id] = node

    def deliver(self, target_node_id, msg_type, payload):
        if not self._deliver_enabled:
            return False  # Simulate network failure
        target = self._nodes.get(target_node_id)
        if target is None:
            return False
        target.ui_queue.put({'type': msg_type, 'payload': payload})
        return True


class _FakeLanNode:
    """Fake LanNode that routes messages through _MessageBus."""

    def __init__(self, username, pet_state, node_id, bus):
        self.username = username
        self.pet_state = pet_state
        self.node_id = node_id
        self._bus = bus
        self.ui_queue = queue.Queue()
        self.net_queue = queue.Queue()
        self._status = {
            'enabled': False, 'is_master': False, 'peer_count': 0,
            'error': None, 'node_id': self.node_id,
        }
        self._peers = []
        self.send_calls = []
        self._bus.register(self)

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
        return self._bus.deliver(peer_node_id, msg_type, payload)

    def send_broadcast(self, msg_type, payload):
        return True


def _make_game(tmp_path, prefix, username, node_id, bus):
    uid = _uid(prefix)
    data_dir = tmp_path / prefix
    data_dir.mkdir(exist_ok=True)
    g = PetGame(uid, data_dir=data_dir)
    fake_node = _FakeLanNode(username, g.state, node_id, bus)
    with patch('ascii_pet.lan.LanNode', return_value=fake_node):
        g.enable_lan(username)
    return g


@pytest.fixture
def two_games(tmp_path):
    """Create two interconnected PetGame instances (Alice and Bob)."""
    bus = _MessageBus()
    alice = _make_game(tmp_path, 'alice', 'Alice', 'node-alice', bus)
    bob = _make_game(tmp_path, 'bob', 'Bob', 'node-bob', bus)
    return alice, bob, bus


def _establish_visit(alice, bob):
    """Establish a visit: Alice invites Bob, both process messages."""
    assert alice.invite_visit('node-bob') is True
    bob.process_lan_queues()
    alice.process_lan_queues()
    assert alice.active_visit is not None
    assert bob.being_visited is not None


# ─── Scenario 1: Complete visit lifecycle with heartbeat ───


class TestCompleteVisitLifecycleWithHeartbeat:
    """Complete visit lifecycle: establish → heartbeat → end → keep state."""

    def test_heartbeat_exchange_during_visit(self, two_games):
        """Both sides exchange heartbeats and update last_heartbeat."""
        alice, bob, bus = two_games
        _establish_visit(alice, bob)

        # Set _last_heartbeat_send to 6 seconds ago so heartbeats fire
        alice._last_heartbeat_send = time.time() - 6
        bob._last_heartbeat_send = time.time() - 6

        # Both sides tick heartbeat -> both send MSG_VISIT_HEARTBEAT
        alice._tick_visit_heartbeat()
        bob._tick_visit_heartbeat()

        # Both sides process the received heartbeats
        alice.process_lan_queues()
        bob.process_lan_queues()

        # Verify last_heartbeat was updated on both sides
        assert alice.active_visit is not None
        assert bob.being_visited is not None
        assert alice.active_visit['last_heartbeat'] > alice.active_visit['start_time']
        assert bob.being_visited['last_heartbeat'] > bob.being_visited['start_time']

    def test_initiator_ends_visit_both_keep_state(self, two_games):
        """When initiator ends visit, both sides keep their UI state."""
        alice, bob, bus = two_games
        _establish_visit(alice, bob)

        # Both switch to ExpandedState
        alice.sm.transition_to(alice, ExpandedState())
        # Bob is already in ExpandedState (set by MSG_VISIT_REQ handler)

        # Alice ends the visit
        alice.handle_key('e')
        assert alice.active_visit is None

        # Bob processes MSG_VISIT_END
        bob.process_lan_queues()
        assert bob.being_visited is None

        # Both keep their UI state (ExpandedState, NOT LanState)
        assert isinstance(alice._inner_state(), ExpandedState), (
            f"Alice should stay in ExpandedState, got {type(alice._inner_state()).__name__}"
        )
        assert isinstance(bob._inner_state(), ExpandedState), (
            f"Bob should stay in ExpandedState, got {type(bob._inner_state()).__name__}"
        )

    def test_visitor_pets_cleared_on_both_sides(self, two_games):
        """Visitor pets are cleared on both sides when visit ends."""
        alice, bob, bus = two_games
        _establish_visit(alice, bob)
        assert 'node-bob' in alice.visitor_pets
        assert 'node-alice' in bob.visitor_pets

        # Alice switches to ExpandedState and ends the visit
        alice.sm.transition_to(alice, ExpandedState())
        alice.handle_key('e')
        bob.process_lan_queues()

        assert 'node-bob' not in alice.visitor_pets
        assert 'node-alice' not in bob.visitor_pets


# ─── Scenario 2: Heartbeat timeout auto-ends visit ───


class TestHeartbeatTimeoutAutoEnd:
    """Heartbeat timeout auto-ends visit when peer disconnects."""

    def test_timeout_ends_visit_on_initiator_side(self, two_games):
        """When Bob disconnects, Alice's visit auto-ends after 15s."""
        alice, bob, bus = two_games
        _establish_visit(alice, bob)

        # Alice is in ExpandedState
        alice.sm.transition_to(alice, ExpandedState())

        # Simulate Bob disconnecting: disable message delivery
        bus._deliver_enabled = False

        # Simulate 16 seconds passing without receiving heartbeat from Bob
        alice.active_visit['last_heartbeat'] = time.time() - 16
        alice._last_heartbeat_send = time.time()  # don't send this tick

        alice._tick_visit_heartbeat()

        assert alice.active_visit is None, (
            "Alice's visit should auto-end after heartbeat timeout"
        )
        assert 'connection lost' in alice.message.lower(), (
            f"Expected 'connection lost' message, got: {alice.message!r}"
        )

    def test_timeout_keeps_expanded_state(self, two_games):
        """Heartbeat timeout does NOT transition to LanState."""
        alice, bob, bus = two_games
        _establish_visit(alice, bob)
        alice.sm.transition_to(alice, ExpandedState())

        bus._deliver_enabled = False
        alice.active_visit['last_heartbeat'] = time.time() - 16
        alice._last_heartbeat_send = time.time()

        alice._tick_visit_heartbeat()

        current = alice._inner_state()
        assert isinstance(current, ExpandedState), (
            f"Should stay in ExpandedState, got {type(current).__name__}"
        )
        assert not isinstance(current, LanState), (
            "Must NOT transition to LanState on heartbeat timeout"
        )

    def test_timeout_ends_visit_on_receiver_side(self, two_games):
        """When Alice disconnects, Bob's visit auto-ends after 15s."""
        alice, bob, bus = two_games
        _establish_visit(alice, bob)

        # Bob is in ExpandedState (set by MSG_VISIT_REQ handler)
        assert isinstance(bob._inner_state(), ExpandedState)

        # Simulate Alice disconnecting
        bus._deliver_enabled = False

        # Simulate 16 seconds without heartbeat from Alice
        bob.being_visited['last_heartbeat'] = time.time() - 16
        bob._last_heartbeat_send = time.time()

        bob._tick_visit_heartbeat()

        assert bob.being_visited is None, (
            "Bob's visit should auto-end after heartbeat timeout"
        )
        assert 'connection lost' in bob.message.lower()


# ─── Scenario 3: Visit restrictions prevent state switching ───


class TestVisitRestrictionsE2E:
    """Visit state-switching restrictions in end-to-end context."""

    def test_blocked_keys_show_prompt_during_visit(self, two_games):
        """Pressing 't' during visit shows 'end the visit first' prompt."""
        alice, bob, bus = two_games
        _establish_visit(alice, bob)
        alice.sm.transition_to(alice, ExpandedState())

        alice.handle_key('t')

        assert isinstance(alice._inner_state(), ExpandedState), (
            "Alice should stay in ExpandedState"
        )
        assert 'end the visit' in alice.message.lower(), (
            f"Expected 'end the visit first' prompt, got: {alice.message!r}"
        )

    def test_compact_expanded_switch_allowed_during_visit(self, two_games):
        """Compact<->Expanded switching is allowed during visit."""
        alice, bob, bus = two_games
        _establish_visit(alice, bob)
        alice.sm.transition_to(alice, ExpandedState())

        # Switch to CompactState (allowed)
        alice.handle_key('c')
        assert isinstance(alice._inner_state(), CompactState)

        # Try 't' from CompactState (should be blocked)
        alice.handle_key('t')
        assert isinstance(alice._inner_state(), CompactState), (
            "Should stay in CompactState - 't' blocked during visit"
        )
        assert 'end the visit' in alice.message.lower()

    def test_restrictions_lifted_after_visit_ends(self, two_games):
        """State switching works normally after visit ends."""
        alice, bob, bus = two_games
        _establish_visit(alice, bob)
        alice.sm.transition_to(alice, ExpandedState())

        # End the visit
        alice.handle_key('e')
        assert alice.active_visit is None

        # Now 't' should work
        alice.handle_key('t')
        assert isinstance(alice._inner_state(), StatsState), (
            f"'t' should switch to StatsState after visit ends, "
            f"got {type(alice._inner_state()).__name__}"
        )

    def test_both_sides_restricted_during_visit(self, two_games):
        """Both initiator and receiver have state-switching restrictions."""
        alice, bob, bus = two_games
        _establish_visit(alice, bob)

        # Both are in ExpandedState
        assert isinstance(alice._inner_state(), ExpandedState) or isinstance(alice._inner_state(), CompactState)
        assert isinstance(bob._inner_state(), ExpandedState)

        # Alice tries 't' -> blocked
        alice.sm.transition_to(alice, ExpandedState())
        alice.handle_key('t')
        assert isinstance(alice._inner_state(), ExpandedState)

        # Bob tries 'a' -> blocked
        bob.handle_key('a')
        assert isinstance(bob._inner_state(), ExpandedState), (
            f"Bob should stay in ExpandedState, got {type(bob._inner_state()).__name__}"
        )
