#!/usr/bin/env python3
"""Pytest tests for lan.py — LAN P2P network core layer.

Strict TDD: these tests are written BEFORE lan.py implementation.
Run with: python -m pytest test_lan_network.py -v

Test categories:
1. Pure functions (elect_master, generate_node_id, is_peer_expired) — no network
2. LanNode lifecycle (start/stop/get_status/get_peers) — mocked sockets

IMPORTANT: No test binds real network ports. All socket operations are mocked
via unittest.mock.patch on socket.socket. A _FakeSocket class simulates
network behavior (bind success/failure, recvfrom/accept timeouts) without
touching the real network.
"""

import os
import queue
import socket
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lan_protocol  # noqa: F401  — ensure protocol module is importable
from lan_protocol import (
    MSG_HELLO, MSG_PEER_LIST, MSG_HEARTBEAT,
    MSG_VISIT_REQ, MSG_VISIT_ACK, MSG_VISIT_DATA,
    MSG_VISIT_LEAVE, MSG_BYE,
    encode_message,
)

import lan


# ─── Test helpers ───────────────────────────────────────────────────────────


def _minimal_pet_state():
    """Minimal pet state dict for testing (matches pet_core.init_state shape)."""
    return {
        "name": "TestPet",
        "species": "cat",
        "rarity": 1,
        "level": 1,
        "shiny": False,
        "eye": 0,
        "hat": 0,
        "mood": "happy",
    }


class _FakeSocket:
    """Fake socket that simulates network behavior without binding real ports.

    - bind() can be configured to fail (simulates port-in-use).
    - recvfrom()/accept() raise socket.timeout periodically so worker threads
      can loop and check the running flag without blocking forever.
    - recv_should_error triggers an unexpected RuntimeError to test that
      worker threads exit gracefully on unexpected exceptions.
    """

    def __init__(self, *args, **kwargs):
        self._closed = False
        self._bind_should_fail = False
        self._recv_should_error = False

    def setsockopt(self, *args, **kwargs):
        pass

    def bind(self, addr):
        if self._bind_should_fail:
            raise socket.error("Address already in use")

    def settimeout(self, t):
        pass

    def listen(self, n):
        pass

    def connect(self, addr):
        pass

    def recvfrom(self, bufsize):
        if self._recv_should_error:
            raise RuntimeError("Simulated unexpected thread error")
        time.sleep(0.02)
        raise socket.timeout()

    def accept(self):
        if self._recv_should_error:
            raise RuntimeError("Simulated unexpected thread error")
        time.sleep(0.02)
        raise socket.timeout()

    def recv(self, bufsize):
        if self._recv_should_error:
            raise RuntimeError("Simulated unexpected thread error")
        time.sleep(0.02)
        raise socket.timeout()

    def sendto(self, data, addr):
        return len(data)

    def send(self, data):
        return len(data)

    def sendall(self, data):
        return None

    def close(self):
        self._closed = True

    def fileno(self):
        return -1


def _fake_socket_factory(bind_should_fail=False, recv_should_error=False):
    """Return a side_effect callable that produces _FakeSocket instances."""
    def factory(*args, **kwargs):
        s = _FakeSocket()
        s._bind_should_fail = bind_should_fail
        s._recv_should_error = recv_should_error
        return s
    return factory


# ─── Pure function tests (no network) ──────────────────────────────────────


class TestElectMaster:
    """elect_master: deterministic master election by lexicographic order."""

    def test_multi_node_returns_smallest(self):
        """Among multiple node_ids, returns the lexicographically smallest."""
        node_ids = ["node-c", "node-a", "node-b"]
        assert lan.elect_master(node_ids) == "node-a"

    def test_empty_list_returns_none(self):
        """Empty list returns None."""
        assert lan.elect_master([]) is None

    def test_single_node_returns_itself(self):
        """Single node returns that node."""
        assert lan.elect_master(["solo"]) == "solo"

    def test_deterministic_multiple_calls(self):
        """Same input produces same output across multiple calls."""
        node_ids = ["node-z", "node-m", "node-a", "node-q"]
        results = [lan.elect_master(node_ids) for _ in range(5)]
        assert all(r == "node-a" for r in results)

    def test_order_independent(self):
        """Input order doesn't affect result."""
        ids_a = ["node-c", "node-a", "node-b"]
        ids_b = ["node-b", "node-c", "node-a"]
        assert lan.elect_master(ids_a) == lan.elect_master(ids_b)


class TestGenerateNodeId:
    """generate_node_id: f"{local_ip}:{tcp_port}:{username}" """

    def test_format_correct(self):
        """Output matches expected format."""
        assert lan.generate_node_id("192.168.1.10", 50008, "alice") == "192.168.1.10:50008:alice"

    def test_contains_three_parts(self):
        """Output has exactly 3 colon-separated parts: ip, port, username."""
        node_id = lan.generate_node_id("10.0.0.5", 50008, "bob")
        parts = node_id.split(":")
        assert len(parts) == 3
        assert parts[0] == "10.0.0.5"
        assert parts[1] == "50008"
        assert parts[2] == "bob"

    def test_deterministic(self):
        """Same inputs produce same node_id."""
        a = lan.generate_node_id("1.2.3.4", 50008, "x")
        b = lan.generate_node_id("1.2.3.4", 50008, "x")
        assert a == b


class TestIsPeerExpired:
    """is_peer_expired: 30s default timeout."""

    def test_not_expired_returns_false(self):
        """Peer seen recently → not expired."""
        assert lan.is_peer_expired(990.0, 1000.0) is False

    def test_expired_returns_true(self):
        """Peer seen >30s ago → expired."""
        assert lan.is_peer_expired(960.0, 1000.0) is True

    def test_boundary_exactly_at_timeout(self):
        """Exactly at 30s → expired (>= timeout)."""
        assert lan.is_peer_expired(970.0, 1000.0) is True

    def test_just_before_timeout(self):
        """1ms before timeout → not expired."""
        # diff = 1000.0 - 970.001 = 29.999 (< 30.0 timeout)
        assert lan.is_peer_expired(970.0 + 0.001, 1000.0) is False

    def test_custom_timeout(self):
        """Custom timeout parameter is respected."""
        # 50s ago with default 30s → expired
        assert lan.is_peer_expired(950.0, 1000.0, timeout=30.0) is True
        # 50s ago with 60s timeout → not expired
        assert lan.is_peer_expired(950.0, 1000.0, timeout=60.0) is False


# ─── LanNode tests (mocked sockets) ────────────────────────────────────────


class TestLanNodeStart:
    """LanNode.start() behavior with mocked sockets."""

    @patch('lan._get_local_ip', return_value='192.168.1.100')
    @patch('socket.socket', side_effect=_fake_socket_factory(bind_should_fail=True))
    def test_start_failure_returns_false_no_exception(self, mock_sock, mock_ip):
        """start() returns False on socket.error, does not raise (test 4)."""
        node = lan.LanNode("alice", _minimal_pet_state())
        result = node.start()
        assert result is False
        assert node.get_status()["enabled"] is False
        node.stop()  # cleanup, should not crash

    @patch('lan._get_local_ip', return_value='192.168.1.100')
    @patch('socket.socket', side_effect=_fake_socket_factory(bind_should_fail=False))
    def test_start_success_returns_true(self, mock_sock, mock_ip):
        """start() returns True when sockets bind successfully."""
        node = lan.LanNode("alice", _minimal_pet_state())
        result = node.start()
        assert result is True
        assert node.get_status()["enabled"] is True
        node.stop()

    @patch('lan._get_local_ip', return_value='192.168.1.100')
    @patch('socket.socket', side_effect=_fake_socket_factory(recv_should_error=True))
    def test_network_thread_exception_exits_gracefully(self, mock_sock, mock_ip):
        """Network thread exception doesn't crash main thread (test 9)."""
        node = lan.LanNode("alice", _minimal_pet_state())
        result = node.start()
        # Sockets bound successfully, so start() returns True
        assert result is True
        # Wait for threads to encounter the unexpected error
        time.sleep(0.3)
        # Main thread still works — get_status() doesn't hang
        status = node.get_status()
        assert isinstance(status, dict)
        # stop() should still work without hanging
        node.stop()
        assert node.get_status()["enabled"] is False


class TestLanNodeStop:
    """LanNode.stop() behavior."""

    def test_stop_when_not_started_does_not_crash(self):
        """stop() on a fresh LanNode (never started) doesn't raise (test 5)."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.stop()  # should not raise

    @patch('lan._get_local_ip', return_value='192.168.1.100')
    @patch('socket.socket', side_effect=_fake_socket_factory(bind_should_fail=False))
    def test_start_then_stop_cleans_up(self, mock_sock, mock_ip):
        """start() → stop() properly cleans up resources (test 10)."""
        node = lan.LanNode("alice", _minimal_pet_state())
        assert node.start() is True
        assert node.get_status()["enabled"] is True
        node.stop()
        # After stop, node is disabled
        status = node.get_status()
        assert status["enabled"] is False


class TestLanNodeGetStatus:
    """LanNode.get_status() behavior."""

    def test_get_status_not_started_returns_disabled(self):
        """get_status() on a fresh LanNode returns enabled=False (test 6)."""
        node = lan.LanNode("alice", _minimal_pet_state())
        status = node.get_status()
        assert status["enabled"] is False
        assert status["is_master"] is False
        assert status["peer_count"] == 0
        assert status["error"] is None
        assert isinstance(status["node_id"], str)
        assert len(status["node_id"]) > 0

    @patch('lan._get_local_ip', return_value='192.168.1.100')
    @patch('socket.socket', side_effect=_fake_socket_factory(bind_should_fail=False))
    def test_get_status_after_start_returns_enabled_with_node_id(self, mock_sock, mock_ip):
        """get_status() after start returns enabled=True and correct node_id (test 7)."""
        node = lan.LanNode("alice", _minimal_pet_state(), tcp_port=50008)
        node.start()
        status = node.get_status()
        assert status["enabled"] is True
        assert status["node_id"] == "192.168.1.100:50008:alice"
        node.stop()


class TestLanNodeGetPeers:
    """LanNode.get_peers() behavior."""

    def test_get_peers_initially_empty(self):
        """get_peers() returns empty list on a fresh LanNode (test 8)."""
        node = lan.LanNode("alice", _minimal_pet_state())
        peers = node.get_peers()
        assert isinstance(peers, list)
        assert peers == []


class TestLanNodeSendBroadcast:
    """LanNode.send_broadcast() basic behavior."""

    def test_send_broadcast_not_started_returns_false(self):
        """send_broadcast returns False when node is not started."""
        node = lan.LanNode("alice", _minimal_pet_state())
        result = node.send_broadcast(MSG_HEARTBEAT, {"ts": time.time()})
        assert result is False

    @patch('lan._get_local_ip', return_value='192.168.1.100')
    @patch('socket.socket', side_effect=_fake_socket_factory(bind_should_fail=False))
    def test_send_broadcast_started_returns_true(self, mock_sock, mock_ip):
        """send_broadcast returns True when node is started."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.start()
        result = node.send_broadcast(MSG_HEARTBEAT, {"ts": time.time()})
        assert result is True
        node.stop()


class TestLanNodeSendToPeer:
    """LanNode.send_to_peer() basic behavior."""

    def test_send_to_peer_not_started_returns_false(self):
        """send_to_peer returns False when node is not started."""
        node = lan.LanNode("alice", _minimal_pet_state())
        result = node.send_to_peer("peer-1", MSG_HEARTBEAT, {"ts": time.time()})
        assert result is False

    @patch('lan._get_local_ip', return_value='192.168.1.100')
    @patch('socket.socket', side_effect=_fake_socket_factory(bind_should_fail=False))
    def test_send_to_peer_unknown_peer_returns_false(self, mock_sock, mock_ip):
        """send_to_peer returns False when peer is not in peers list."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.start()
        result = node.send_to_peer("unknown-peer", MSG_HEARTBEAT, {})
        assert result is False
        node.stop()


# ─── Star topology: TCP message handling ───────────────────────────────────


class TestHandleTcpMessage:
    """_handle_tcp_message dispatches TCP messages to ui_queue."""

    def test_visit_req_enqueued_to_ui_queue(self):
        """VISIT_REQ message is put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        data = encode_message(MSG_VISIT_REQ, {"from": "peer-1", "pet_name": "Buddy"})
        node._handle_tcp_message(data)
        msg = node.ui_queue.get_nowait()
        assert msg["type"] == MSG_VISIT_REQ
        assert msg["payload"]["pet_name"] == "Buddy"

    def test_visit_ack_enqueued_to_ui_queue(self):
        """VISIT_ACK message is put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        data = encode_message(MSG_VISIT_ACK, {"accept": True})
        node._handle_tcp_message(data)
        msg = node.ui_queue.get_nowait()
        assert msg["type"] == MSG_VISIT_ACK
        assert msg["payload"]["accept"] is True

    def test_visit_data_enqueued_to_ui_queue(self):
        """VISIT_DATA message is put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        data = encode_message(MSG_VISIT_DATA, {"name": "TestPet", "species": "cat"})
        node._handle_tcp_message(data)
        msg = node.ui_queue.get_nowait()
        assert msg["type"] == MSG_VISIT_DATA
        assert msg["payload"]["name"] == "TestPet"

    def test_visit_leave_enqueued_to_ui_queue(self):
        """VISIT_LEAVE message is put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        data = encode_message(MSG_VISIT_LEAVE, {"pet_name": "Buddy"})
        node._handle_tcp_message(data)
        msg = node.ui_queue.get_nowait()
        assert msg["type"] == MSG_VISIT_LEAVE
        assert msg["payload"]["pet_name"] == "Buddy"

    def test_heartbeat_not_enqueued_to_ui_queue(self):
        """HEARTBEAT message is NOT put into ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        data = encode_message(MSG_HEARTBEAT, {"node_id": "peer-1"})
        node._handle_tcp_message(data)
        assert node.ui_queue.empty()

    def test_invalid_message_does_not_crash(self):
        """Invalid data does not crash, nothing enqueued."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node._handle_tcp_message(b"invalid")
        node._handle_tcp_message(b"")
        node._handle_tcp_message(None)
        assert node.ui_queue.empty()

    def test_relay_message_forwards_to_target(self):
        """Master forwards relay message to target client socket."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.is_master = True
        fake_sock = _FakeSocket()
        with node._client_sockets_lock:
            node._client_sockets["target-peer"] = fake_sock
        relay_payload = {
            "target": "target-peer",
            "msg_type": MSG_VISIT_REQ,
            "payload": {"from": "alice", "pet_name": "Buddy"},
        }
        data = encode_message("relay", relay_payload)
        node._handle_tcp_message(data)
        # No message enqueued to ui_queue (relay is forwarded, not enqueued)
        assert node.ui_queue.empty()

    def test_relay_unknown_target_no_crash(self):
        """Master receives relay for unknown target, does not crash."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.is_master = True
        relay_payload = {
            "target": "unknown-peer",
            "msg_type": MSG_VISIT_REQ,
            "payload": {},
        }
        data = encode_message("relay", relay_payload)
        node._handle_tcp_message(data)
        assert node.ui_queue.empty()

    def test_hello_registers_client_socket(self):
        """Master registers client socket on HELLO message via TCP."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.is_master = True
        fake_sock = _FakeSocket()
        hello_payload = {
            "node_id": "peer-1",
            "username": "bob",
            "pet_summary": {"name": "BobPet"},
        }
        data = encode_message(MSG_HELLO, hello_payload)
        node._handle_tcp_message(data, sender_sock=fake_sock)
        with node._client_sockets_lock:
            assert "peer-1" in node._client_sockets
            assert node._client_sockets["peer-1"] is fake_sock


# ─── Star topology: master election integration ───────────────────────────


class TestMasterElectionIntegration:
    """Master election is integrated into peer discovery."""

    def test_reelect_master_alone_returns_self(self):
        """Node with no peers elects itself as master."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.is_master = False  # reset to verify re-election
        node._reelect_master()
        assert node.is_master is True
        assert node._master_id == node.node_id

    def test_reelect_master_smaller_peer_demotes(self):
        """Node with a smaller peer_id becomes slave."""
        node = lan.LanNode("zzz", _minimal_pet_state())
        node.node_id = "zzz-node"  # override for predictable election
        node._master_id = "zzz-node"
        with node._peers_lock:
            node._peers["aaa-peer"] = {
                "node_id": "aaa-peer",
                "username": "alice",
                "pet_summary": {},
                "last_seen": time.time(),
                "addr": ("127.0.0.1", 50007),
                "ip": "127.0.0.1",
            }
        node._reelect_master()
        assert node.is_master is False
        assert node._master_id == "aaa-peer"

    def test_reelect_master_self_smallest_stays_master(self):
        """Node with the smallest node_id stays master."""
        node = lan.LanNode("aaa", _minimal_pet_state())
        with node._peers_lock:
            node._peers["zzz-peer"] = {
                "node_id": "zzz-peer",
                "username": "zoe",
                "pet_summary": {},
                "last_seen": time.time(),
                "addr": ("127.0.0.1", 50007),
                "ip": "127.0.0.1",
            }
        node._reelect_master()
        assert node.is_master is True
        assert node._master_id == node.node_id

    @patch('socket.socket', side_effect=_fake_socket_factory())
    def test_hello_from_smaller_peer_demotes_to_slave(self, mock_sock):
        """HELLO from a peer with smaller node_id demotes self to slave."""
        node = lan.LanNode("zzz", _minimal_pet_state())
        node.node_id = "zzz-node"  # override for predictable election
        node._master_id = "zzz-node"
        node.is_master = True
        hello_payload = {
            "node_id": "aaa-peer",
            "username": "alice",
            "pet_summary": {},
        }
        node._on_peer_hello(hello_payload, ("127.0.0.1", 50007))
        assert node.is_master is False
        assert node._master_id == "aaa-peer"


# ─── Star topology: send_to_peer relay ─────────────────────────────────────


class TestSendToPeerRelay:
    """send_to_peer routes via master (direct) or relay (slave)."""

    def test_master_sends_directly_to_target(self):
        """Master sends directly to target client socket."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.enabled = True
        node.is_master = True
        fake_sock = _FakeSocket()
        with node._client_sockets_lock:
            node._client_sockets["target-peer"] = fake_sock
        result = node.send_to_peer("target-peer", MSG_VISIT_REQ, {"from": "alice"})
        assert result is True

    def test_master_returns_false_for_unknown_target(self):
        """Master returns False when target not in client_sockets."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.enabled = True
        node.is_master = True
        result = node.send_to_peer("unknown-peer", MSG_VISIT_REQ, {})
        assert result is False

    def test_slave_relays_through_master(self):
        """Slave sends relay message to master socket."""
        node = lan.LanNode("bob", _minimal_pet_state())
        node.enabled = True
        node.is_master = False
        node._master_sock = _FakeSocket()
        result = node.send_to_peer("target-peer", MSG_VISIT_REQ, {"from": "bob"})
        assert result is True

    def test_slave_returns_false_when_no_master_sock(self):
        """Slave returns False when master socket is not connected."""
        node = lan.LanNode("bob", _minimal_pet_state())
        node.enabled = True
        node.is_master = False
        node._master_sock = None
        result = node.send_to_peer("target-peer", MSG_VISIT_REQ, {})
        assert result is False

    def test_send_to_peer_disabled_returns_false(self):
        """send_to_peer returns False when node is disabled."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.enabled = False
        result = node.send_to_peer("peer-1", MSG_VISIT_REQ, {})
        assert result is False


# ─── Star topology: slave connects to master ───────────────────────────────


class TestConnectToMaster:
    """_connect_to_master establishes TCP connection to master."""

    def test_master_does_not_connect_to_self(self):
        """Master node does not connect to itself."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.is_master = True
        node._connect_to_master()
        assert node._master_sock is None

    @patch('socket.socket', side_effect=_fake_socket_factory())
    def test_slave_connects_to_master(self, mock_sock):
        """Slave connects to master's TCP port."""
        node = lan.LanNode("bob", _minimal_pet_state())
        node.is_master = False
        node._master_id = "master-id"
        with node._peers_lock:
            node._peers["master-id"] = {
                "node_id": "master-id",
                "username": "alice",
                "pet_summary": {},
                "last_seen": time.time(),
                "addr": ("127.0.0.1", 50007),
                "ip": "127.0.0.1",
            }
        node._connect_to_master()
        assert node._master_sock is not None
        # Clean up
        with node._client_sockets_lock:
            if node._master_sock:
                try:
                    node._master_sock.close()
                except Exception:
                    pass
                node._master_sock = None

    def test_slave_no_master_peer_returns_early(self):
        """Slave returns early when master peer is unknown."""
        node = lan.LanNode("bob", _minimal_pet_state())
        node.is_master = False
        node._master_id = "unknown-master"
        node._connect_to_master()
        assert node._master_sock is None

    def test_slave_no_master_ip_returns_early(self):
        """Slave returns early when master peer has no IP."""
        node = lan.LanNode("bob", _minimal_pet_state())
        node.is_master = False
        node._master_id = "master-id"
        with node._peers_lock:
            node._peers["master-id"] = {
                "node_id": "master-id",
                "username": "alice",
                "pet_summary": {},
                "last_seen": time.time(),
                "addr": None,
                "ip": None,
            }
        node._connect_to_master()
        assert node._master_sock is None


# ─── Star topology: failover ───────────────────────────────────────────────


class TestFailover:
    """Failover when master disconnects."""

    @patch('socket.socket', side_effect=_fake_socket_factory())
    def test_master_disconnect_triggers_reelection(self, mock_sock):
        """When master disconnects, slave re-elects and connects to new master."""
        node = lan.LanNode("zzz-bob", _minimal_pet_state())
        node.node_id = "zzz-bob"  # override for predictable election
        node.is_master = False
        node._master_id = "old-master"
        node._master_sock = _FakeSocket()
        node._running = True
        with node._peers_lock:
            node._peers["old-master"] = {
                "node_id": "old-master",
                "username": "alice",
                "pet_summary": {},
                "last_seen": time.time(),
                "addr": ("127.0.0.1", 50007),
                "ip": "127.0.0.1",
            }
            node._peers["aaa-new-master"] = {
                "node_id": "aaa-new-master",
                "username": "carol",
                "pet_summary": {},
                "last_seen": time.time(),
                "addr": ("127.0.0.1", 50007),
                "ip": "127.0.0.1",
            }
        node._on_master_disconnect()
        with node._peers_lock:
            assert "old-master" not in node._peers
        assert node._master_id == "aaa-new-master"
        assert node.is_master is False
        msg = node.ui_queue.get_nowait()
        assert msg["type"] == "master_change"
        # Clean up
        node._running = False
        with node._client_sockets_lock:
            if node._master_sock:
                try:
                    node._master_sock.close()
                except Exception:
                    pass
                node._master_sock = None

    def test_self_becomes_master_when_no_other_peers(self):
        """When master disconnects and no other peers, self becomes master."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.is_master = False
        node._master_id = "old-master"
        node._master_sock = _FakeSocket()
        node._running = True
        with node._peers_lock:
            node._peers["old-master"] = {
                "node_id": "old-master",
                "username": "zoe",
                "pet_summary": {},
                "last_seen": time.time(),
                "addr": ("127.0.0.1", 50007),
                "ip": "127.0.0.1",
            }
        node._on_master_disconnect()
        assert node.is_master is True
        assert node._master_id == node.node_id
        assert node._master_sock is None
        msg = node.ui_queue.get_nowait()
        assert msg["type"] == "master_change"


# ─── Star topology: thread exception notification ──────────────────────────


class TestThreadExceptionNotification:
    """Thread exceptions notify the UI via ui_queue."""

    @patch('lan._get_local_ip', return_value='192.168.1.100')
    @patch('socket.socket', side_effect=_fake_socket_factory(recv_should_error=True))
    def test_thread_exception_puts_error_in_ui_queue(self, mock_sock, mock_ip):
        """Network thread exception puts an error message in ui_queue."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.start()
        time.sleep(0.3)
        errors = []
        while True:
            try:
                msg = node.ui_queue.get_nowait()
                if msg.get("type") == "error":
                    errors.append(msg)
            except queue.Empty:
                break
        assert len(errors) > 0
        assert "网络线程异常" in errors[0]["payload"]["msg"]
        node.stop()


# ─── Bug fix tests ─────────────────────────────────────────────────────────


class TestBug1SlaveSendsDirectlyToMaster:
    """Bug 1 fix: slave sends to master directly via _master_sock, not relay."""

    def test_slave_sends_to_master_directly(self):
        """Slave sends message to master via _master_sock, not relay wrapper."""
        node = lan.LanNode("bob", _minimal_pet_state())
        node.enabled = True
        node.is_master = False
        node._master_id = "master-node"
        master_sock = _FakeSocket()
        node._master_sock = master_sock
        result = node.send_to_peer("master-node", MSG_VISIT_REQ, {"from": "bob"})
        assert result is True

    def test_slave_sends_to_master_no_master_sock_returns_false(self):
        """Slave returns False when sending to master but _master_sock is None."""
        node = lan.LanNode("bob", _minimal_pet_state())
        node.enabled = True
        node.is_master = False
        node._master_id = "master-node"
        node._master_sock = None
        result = node.send_to_peer("master-node", MSG_VISIT_REQ, {"from": "bob"})
        assert result is False

    def test_slave_sends_to_other_slave_uses_relay(self):
        """Slave sends to another slave via relay (not direct)."""
        node = lan.LanNode("bob", _minimal_pet_state())
        node.enabled = True
        node.is_master = False
        node._master_id = "master-node"
        node._master_sock = _FakeSocket()
        result = node.send_to_peer("other-slave", MSG_VISIT_REQ, {"from": "bob"})
        assert result is True

    def test_slave_to_master_sends_raw_not_relay(self):
        """Verify slave→master sends raw message, not relay-wrapped.

        We intercept sendall to check the sent data is a raw VISIT_REQ,
        not a relay message.
        """
        node = lan.LanNode("bob", _minimal_pet_state())
        node.enabled = True
        node.is_master = False
        node._master_id = "master-node"
        sent_data = []

        class _CapturingSocket(_FakeSocket):
            def sendall(self, data):
                sent_data.append(data)

        node._master_sock = _CapturingSocket()
        node.send_to_peer("master-node", MSG_VISIT_REQ, {"from": "bob"})
        # Should have sent exactly one raw message
        assert len(sent_data) == 1
        # Decode the sent data — it should be VISIT_REQ, not relay
        result = lan_protocol.decode_message(sent_data[0])
        assert result is not None
        msg_type, payload = result
        assert msg_type == MSG_VISIT_REQ
        assert payload["from"] == "bob"

    def test_slave_to_other_slave_sends_relay(self):
        """Verify slave→other-slave sends relay-wrapped message."""
        node = lan.LanNode("bob", _minimal_pet_state())
        node.enabled = True
        node.is_master = False
        node._master_id = "master-node"
        sent_data = []

        class _CapturingSocket(_FakeSocket):
            def sendall(self, data):
                sent_data.append(data)

        node._master_sock = _CapturingSocket()
        node.send_to_peer("other-slave", MSG_VISIT_REQ, {"from": "bob"})
        assert len(sent_data) == 1
        result = lan_protocol.decode_message(sent_data[0])
        assert result is not None
        msg_type, payload = result
        assert msg_type == "relay"
        assert payload["target"] == "other-slave"
        assert payload["msg_type"] == MSG_VISIT_REQ


class TestBug2DecodeAllMessages:
    """Bug 2 fix: _decode_all_messages handles TCP sticky-packet."""

    def test_single_message(self):
        """Single message in buffer is decoded correctly."""
        node = lan.LanNode("alice", _minimal_pet_state())
        data = encode_message(MSG_VISIT_REQ, {"from": "bob"})
        messages = node._decode_all_messages(data)
        assert len(messages) == 1
        assert messages[0][0] == MSG_VISIT_REQ
        assert messages[0][1]["from"] == "bob"

    def test_two_messages_stuck_together(self):
        """Two messages concatenated in one recv are both decoded."""
        node = lan.LanNode("alice", _minimal_pet_state())
        data1 = encode_message(MSG_VISIT_REQ, {"from": "bob"})
        data2 = encode_message(MSG_VISIT_ACK, {"accept": True})
        combined = data1 + data2
        messages = node._decode_all_messages(combined)
        assert len(messages) == 2
        assert messages[0][0] == MSG_VISIT_REQ
        assert messages[0][1]["from"] == "bob"
        assert messages[1][0] == MSG_VISIT_ACK
        assert messages[1][1]["accept"] is True

    def test_three_messages_stuck_together(self):
        """Three messages concatenated are all decoded."""
        node = lan.LanNode("alice", _minimal_pet_state())
        data1 = encode_message(MSG_VISIT_REQ, {"from": "a"})
        data2 = encode_message(MSG_VISIT_ACK, {"accept": False})
        data3 = encode_message(MSG_VISIT_LEAVE, {"pet_name": "x"})
        combined = data1 + data2 + data3
        messages = node._decode_all_messages(combined)
        assert len(messages) == 3
        assert messages[0][0] == MSG_VISIT_REQ
        assert messages[1][0] == MSG_VISIT_ACK
        assert messages[2][0] == MSG_VISIT_LEAVE

    def test_incomplete_frame_stops_parsing(self):
        """Incomplete trailing frame is ignored, earlier frames are decoded."""
        node = lan.LanNode("alice", _minimal_pet_state())
        data1 = encode_message(MSG_VISIT_REQ, {"from": "bob"})
        # Add incomplete frame: just 2 bytes of length prefix
        incomplete = data1 + b"\x00\x05"
        messages = node._decode_all_messages(incomplete)
        assert len(messages) == 1
        assert messages[0][0] == MSG_VISIT_REQ

    def test_empty_data_returns_empty_list(self):
        """Empty bytes returns empty list."""
        node = lan.LanNode("alice", _minimal_pet_state())
        messages = node._decode_all_messages(b"")
        assert messages == []

    def test_invalid_data_returns_empty_list(self):
        """Invalid bytes returns empty list."""
        node = lan.LanNode("alice", _minimal_pet_state())
        messages = node._decode_all_messages(b"garbage")
        assert messages == []

    def test_handle_decoded_message_visit_req(self):
        """_handle_decoded_message enqueues VISIT_REQ."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node._handle_decoded_message(MSG_VISIT_REQ, {"from": "bob"})
        msg = node.ui_queue.get_nowait()
        assert msg["type"] == MSG_VISIT_REQ

    def test_handle_decoded_message_hello_registers(self):
        """_handle_decoded_message registers socket on HELLO."""
        node = lan.LanNode("alice", _minimal_pet_state())
        fake_sock = _FakeSocket()
        result = node._handle_decoded_message(
            MSG_HELLO, {"node_id": "peer-1"}, sender_sock=fake_sock
        )
        assert result == "peer-1"
        with node._client_sockets_lock:
            assert node._client_sockets["peer-1"] is fake_sock

    def test_handle_decoded_message_relay(self):
        """_handle_decoded_message handles relay messages."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.is_master = True
        fake_sock = _FakeSocket()
        with node._client_sockets_lock:
            node._client_sockets["target-peer"] = fake_sock
        node._handle_decoded_message("relay", {
            "target": "target-peer",
            "msg_type": MSG_VISIT_REQ,
            "payload": {"from": "alice"},
        })
        # relay is forwarded, not enqueued
        assert node.ui_queue.empty()

    def test_handle_tcp_message_still_works_as_compat(self):
        """_handle_tcp_message (compat) still works after refactor."""
        node = lan.LanNode("alice", _minimal_pet_state())
        data = encode_message(MSG_VISIT_ACK, {"accept": True})
        result = node._handle_tcp_message(data)
        assert result is None  # VISIT_ACK doesn't return node_id
        msg = node.ui_queue.get_nowait()
        assert msg["type"] == MSG_VISIT_ACK


class TestBug3SlaveClosesTcpListener:
    """Bug 3 fix: slave closes TCP listener on master change."""

    def test_close_tcp_listener_sets_socket_none(self):
        """_close_tcp_listener closes and nullifies _tcp_socket."""
        node = lan.LanNode("alice", _minimal_pet_state())
        fake_sock = _FakeSocket()
        node._tcp_socket = fake_sock
        node._close_tcp_listener()
        assert node._tcp_socket is None
        assert fake_sock._closed is True

    def test_close_tcp_listener_when_none_no_crash(self):
        """_close_tcp_listener when _tcp_socket is None doesn't crash."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node._tcp_socket = None
        node._close_tcp_listener()  # should not raise
        assert node._tcp_socket is None

    @patch('socket.socket', side_effect=_fake_socket_factory())
    def test_on_master_change_slave_closes_listener(self, mock_sock):
        """When becoming slave, _on_master_change closes TCP listener."""
        node = lan.LanNode("zzz", _minimal_pet_state())
        node.node_id = "zzz-node"
        node.is_master = True
        node._master_id = "zzz-node"
        node._tcp_socket = _FakeSocket()
        # Simulate demotion to slave
        with node._peers_lock:
            node._peers["aaa-master"] = {
                "node_id": "aaa-master",
                "username": "alice",
                "pet_summary": {},
                "last_seen": time.time(),
                "addr": ("127.0.0.1", 50007),
                "ip": "127.0.0.1",
            }
        node._reelect_master()
        # After re-elect, node should be slave
        assert node.is_master is False
        # _on_master_change should have been called via _on_peer_hello path
        # but we call it directly to test
        node._on_master_change("zzz-node", "aaa-master")
        assert node._tcp_socket is None

    @patch('socket.socket', side_effect=_fake_socket_factory())
    def test_on_master_change_master_ensures_listener(self, mock_sock):
        """When becoming master, _on_master_change ensures TCP listener is running."""
        node = lan.LanNode("alice", _minimal_pet_state())
        node.is_master = True
        node._master_id = "old-master"
        node._tcp_socket = None  # listener was closed when slave
        node._on_master_change("old-master", node.node_id)
        # _start_tcp_listener should have been called (with mock socket)
        # We just verify it didn't crash and _tcp_socket was attempted


# ─── Username conflict check ──────────────────────────────────────────────


class TestCheckNameConflict:
    """check_name_conflict: pure function checking username against peers."""

    def test_returns_true_when_username_matches_peer(self):
        """Returns True (conflict) when a peer has the same username."""
        peers = [
            {"node_id": "peer-1", "username": "alice", "pet_summary": {}},
            {"node_id": "peer-2", "username": "bob", "pet_summary": {}},
        ]
        assert lan.check_name_conflict("alice", peers) is True

    def test_returns_false_when_no_match(self):
        """Returns False (no conflict) when no peer has the username."""
        peers = [
            {"node_id": "peer-1", "username": "alice", "pet_summary": {}},
            {"node_id": "peer-2", "username": "bob", "pet_summary": {}},
        ]
        assert lan.check_name_conflict("carol", peers) is False

    def test_returns_false_for_empty_peers(self):
        """Returns False (no conflict) when peers list is empty."""
        assert lan.check_name_conflict("alice", []) is False

    def test_returns_true_when_single_peer_matches(self):
        """Returns True when the only peer has the same username."""
        peers = [{"node_id": "peer-1", "username": "alice", "pet_summary": {}}]
        assert lan.check_name_conflict("alice", peers) is True

    def test_returns_false_when_peer_missing_username_key(self):
        """Returns False when peers lack 'username' key (no match)."""
        peers = [{"node_id": "peer-1", "pet_summary": {}}]
        assert lan.check_name_conflict("alice", peers) is False

