#!/usr/bin/env python3
"""LAN P2P network core for ASCII pet.

Provides LanNode for peer-to-peer networking over UDP broadcast (discovery)
and TCP (reliable messaging). Designed to degrade gracefully: all socket
operations are wrapped in try/except, and network thread exceptions never
propagate to the main thread.

Zero pip dependencies (stdlib only).
"""

import queue
import socket
import struct
import threading
import time

from ascii_pet import protocol as lan_protocol
from ascii_pet.protocol import (
    MSG_HELLO, MSG_PEER_LIST, MSG_HEARTBEAT,
    MSG_VISIT_REQ, MSG_VISIT_ACK, MSG_VISIT_DATA,
    MSG_VISIT_LEAVE, MSG_BYE,
    encode_message, decode_message,
    make_pet_snapshot, make_hello, make_hello_lite,
)

# ─── Constants ─────────────────────────────────────────────────────────────

DEFAULT_UDP_PORT = 50007
DEFAULT_TCP_PORT = 50008
BROADCAST_ADDR = "255.255.255.255"
HELLO_INTERVAL = 5.0       # seconds between HELLO broadcasts
HEARTBEAT_INTERVAL = 15.0  # seconds between heartbeats
PEER_TIMEOUT = 30.0        # seconds before a peer is considered expired
SOCKET_TIMEOUT = 1.0       # recv timeout so worker threads can poll _running
THREAD_JOIN_TIMEOUT = 2.0  # seconds to wait for thread shutdown in stop()
HEARTBEAT_LOOP_SLEEP = 0.5  # seconds between heartbeat-loop iterations


# ─── Pure functions ────────────────────────────────────────────────────────


def elect_master(node_ids):
    """Deterministic master election.

    Returns the lexicographically smallest node_id so every node independently
    arrives at the same master without coordination.

    Args:
        node_ids: List of node ID strings.

    Returns:
        The smallest node_id by string comparison, or None if the list is empty.
    """
    if not node_ids:
        return None
    return min(node_ids)


def generate_node_id(local_ip, tcp_port, username):
    """Generate a deterministic node ID.

    Format: ``f"{local_ip}:{tcp_port}:{username}"``

    The same (ip, port, username) triple always produces the same node_id,
    which makes a node's identity stable across restarts on the same machine.
    """
    return f"{local_ip}:{tcp_port}:{username}"


def is_peer_expired(last_seen, now, timeout=PEER_TIMEOUT):
    """Check if a peer has expired (not seen within timeout).

    Args:
        last_seen: Timestamp when the peer was last seen (seconds since epoch).
        now:       Current timestamp (seconds since epoch).
        timeout:   Expiry threshold in seconds (default 30.0).

    Returns:
        True if ``(now - last_seen) >= timeout``, False otherwise.
    """
    return (now - last_seen) >= timeout


def check_name_conflict(username, peers):
    """Check if a username conflicts with any peer's username.

    Args:
        username: The username to check.
        peers:    List of peer dicts (as returned by ``LanNode.get_peers``).
                  Each dict may contain a ``"username"`` key.

    Returns:
        True if any peer has the same username (conflict), False otherwise.
    """
    for peer in peers:
        if peer.get('username') == username:
            return True
    return False


def _get_local_ip():
    """Detect the local IP address by opening a UDP socket to a public address.

    No packets are actually sent; the kernel picks the source IP it would use
    to reach the target. Returns ``"127.0.0.1"`` if detection fails.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return "127.0.0.1"


def _compute_broadcast_addr(local_ip):
    """Compute the subnet-directed broadcast address for the given local IP.

    Uses a /24 mask (255.255.255.0) which covers the common home/LAN case.
    Falls back to 255.255.255.255 (limited broadcast) for loopback or
    unparseable addresses so tests and single-machine scenarios still work.

    Args:
        local_ip: IPv4 address string (e.g. "192.168.1.100").

    Returns:
        Subnet broadcast address (e.g. "192.168.1.255"), or
        "255.255.255.255" if local_ip is loopback or invalid.
    """
    try:
        parts = local_ip.split(".")
        if len(parts) != 4:
            return BROADCAST_ADDR
        if parts[0] == "127":
            return BROADCAST_ADDR
        # /24 subnet: zero the host portion, set it to 255
        return ".".join(parts[:3]) + ".255"
    except Exception:
        return BROADCAST_ADDR


# ─── LanNode ───────────────────────────────────────────────────────────────


class LanNode:
    """P2P network node for LAN multiplayer.

    Lifecycle::

        node = LanNode("alice", pet_state)
        node.start()    # bind sockets, spawn worker threads
        node.get_peers()
        node.stop()     # send BYE, close sockets, join threads

    Thread safety:
        - ``self._peers`` is protected by ``self._peers_lock``.
        - ``self._client_sockets`` is protected by ``self._client_sockets_lock``.
        - All public methods are safe to call from any thread.
    """

    def __init__(self, username, pet_state, udp_port=DEFAULT_UDP_PORT, tcp_port=DEFAULT_TCP_PORT):
        self.username = username
        self.pet_state = pet_state
        self.udp_port = udp_port
        self.tcp_port = tcp_port

        self.local_ip = _get_local_ip()
        self._broadcast_addr = _compute_broadcast_addr(self.local_ip)
        self.node_id = generate_node_id(self.local_ip, tcp_port, username)

        self.enabled = False
        self.is_master = False
        self.error_msg = None

        # Star topology: master election state
        self._master_id = self.node_id  # initially self is master
        self._master_sock = None        # slave's TCP connection to master
        self._hello_sent = False        # first HELLO carries full snapshot

        # node_id -> peer info dict
        self._peers = {}
        self._peers_lock = threading.Lock()

        self._running = False
        self._threads = []
        self._udp_socket = None
        self._tcp_socket = None       # master listen socket
        self._client_sockets = {}     # node_id -> accepted TCP client socket
        self._client_sockets_lock = threading.Lock()

        # Cross-thread queues (UI events in, network actions out)
        self.ui_queue = queue.Queue()
        self.net_queue = queue.Queue()

    # ─── Lifecycle ─────────────────────────────────────────────────────────

    def start(self):
        """Start the network layer.

        Creates UDP and TCP sockets, spawns worker threads.

        Returns:
            True on success, False on failure (never raises).
        """
        try:
            # UDP socket for broadcast discovery
            self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._udp_socket.bind(("", self.udp_port))
            self._udp_socket.settimeout(SOCKET_TIMEOUT)

            # TCP socket for reliable messaging
            self._tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._tcp_socket.bind(("", self.tcp_port))
            self._tcp_socket.listen(5)
            self._tcp_socket.settimeout(SOCKET_TIMEOUT)

            self.enabled = True
            self.is_master = True  # initially master; slaves adjust via election
            self.error_msg = None
            self._running = True

            self._threads = [
                threading.Thread(target=self._udp_loop, name="lan-udp", daemon=True),
                threading.Thread(target=self._tcp_accept_loop, name="lan-tcp", daemon=True),
                threading.Thread(target=self._heartbeat_loop, name="lan-hb", daemon=True),
            ]
            for t in self._threads:
                t.start()

            return True
        except socket.error as e:
            self.error_msg = str(e)
            self.enabled = False
            self._cleanup_sockets()
            return False
        except Exception as e:
            self.error_msg = str(e)
            self.enabled = False
            self._cleanup_sockets()
            return False

    def stop(self):
        """Stop the network layer: send BYE, close sockets, join threads.

        Safe to call even if start() was never called or failed.
        """
        self._running = False
        self.enabled = False
        self.is_master = False

        # Best-effort BYE broadcast
        if self._udp_socket is not None:
            try:
                self._send_broadcast_raw(MSG_BYE, {"node_id": self.node_id})
            except Exception:
                pass

        self._cleanup_sockets()

        for t in self._threads:
            if t.is_alive():
                t.join(timeout=THREAD_JOIN_TIMEOUT)
        self._threads = []

        # Reset master state
        self._master_id = self.node_id
        self._master_sock = None

    def _cleanup_sockets(self):
        """Close all sockets, ignoring errors."""
        for sock in (self._udp_socket, self._tcp_socket):
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
        with self._client_sockets_lock:
            for sock in self._client_sockets.values():
                try:
                    sock.close()
                except Exception:
                    pass
            self._client_sockets = {}
            if self._master_sock is not None:
                try:
                    self._master_sock.close()
                except Exception:
                    pass
                self._master_sock = None
        self._udp_socket = None
        self._tcp_socket = None

    # ─── Status ────────────────────────────────────────────────────────────

    def get_status(self):
        """Return a status dict.

        Keys: ``enabled``, ``is_master``, ``peer_count``, ``error``, ``node_id``.
        """
        with self._peers_lock:
            peer_count = len(self._peers)
        return {
            "enabled": self.enabled,
            "is_master": self.is_master,
            "peer_count": peer_count,
            "error": self.error_msg,
            "node_id": self.node_id,
        }

    def get_peers(self):
        """Return a list of known peers (thread-safe copy).

        Each entry: ``{"node_id", "username", "pet_summary"}``.
        """
        with self._peers_lock:
            return [
                {
                    "node_id": p["node_id"],
                    "username": p["username"],
                    "pet_summary": p["pet_summary"],
                }
                for p in self._peers.values()
            ]

    # ─── Sending ───────────────────────────────────────────────────────────

    def send_broadcast(self, msg_type, payload):
        """Broadcast a message to all peers via UDP.

        Returns:
            True on success, False if not started or send failed.
        """
        if not self.enabled or self._udp_socket is None:
            return False
        try:
            self._send_broadcast_raw(msg_type, payload)
            return True
        except Exception:
            return False

    def _send_broadcast_raw(self, msg_type, payload):
        """Send a UDP broadcast (internal, may raise)."""
        data = encode_message(msg_type, payload)
        self._udp_socket.sendto(data, (self._broadcast_addr, self.udp_port))

    def send_to_peer(self, peer_node_id, msg_type, payload):
        """Send a message to a specific peer via TCP.

        If this node is the master, the message is forwarded directly to the
        target peer's TCP connection. If this node is a slave and the target
        is the master, the message is sent directly via ``_master_sock``.
        If this node is a slave and the target is another slave, the message
        is wrapped as a relay and sent to the master for forwarding.

        Returns:
            True on success, False if not started, peer unknown, or send failed.
        """
        if not self.enabled:
            return False
        try:
            data = encode_message(msg_type, payload)
            if self.is_master:
                # Master: send directly to target client socket
                with self._client_sockets_lock:
                    sock = self._client_sockets.get(peer_node_id)
                    if sock is None:
                        return False
                    sock.sendall(data)
                    return True
            else:
                # Slave
                if peer_node_id == self._master_id:
                    # Send to master directly via _master_sock, no relay
                    with self._client_sockets_lock:
                        if self._master_sock is None:
                            return False
                        self._master_sock.sendall(data)
                        return True
                else:
                    # Send to another slave: relay through master
                    relay_payload = {
                        "target": peer_node_id,
                        "msg_type": msg_type,
                        "payload": payload,
                    }
                    relay_data = encode_message("relay", relay_payload)
                    with self._client_sockets_lock:
                        if self._master_sock is None:
                            return False
                        self._master_sock.sendall(relay_data)
                        return True
        except Exception:
            return False

    # ─── Worker threads ────────────────────────────────────────────────────

    def _udp_loop(self):
        """UDP thread: receive HELLO/BYE/HEARTBEAT and periodically broadcast HELLO."""
        last_hello = 0.0
        while self._running:
            try:
                data, addr = self._udp_socket.recvfrom(4096)
                self._handle_udp_message(data, addr)
            except socket.timeout:
                pass
            except socket.error:
                break  # socket closed
            except Exception as e:
                self.ui_queue.put({"type": "error", "payload": {"msg": f"网络线程异常: {e}"}})
                break  # unexpected error, exit gracefully

            now = time.time()
            if now - last_hello >= HELLO_INTERVAL:
                last_hello = now
                try:
                    self._broadcast_hello()
                except Exception:
                    pass

    def _tcp_accept_loop(self):
        """TCP thread: accept connections from other nodes (master mode)."""
        while self._running:
            try:
                client_sock, addr = self._tcp_socket.accept()
                client_sock.settimeout(SOCKET_TIMEOUT)
                t = threading.Thread(
                    target=self._tcp_client_loop,
                    args=(client_sock,),
                    name=f"lan-tcp-client-{addr}",
                    daemon=True,
                )
                t.start()
            except socket.timeout:
                continue
            except socket.error:
                break  # socket closed
            except Exception as e:
                self.ui_queue.put({"type": "error", "payload": {"msg": f"网络线程异常: {e}"}})
                break  # unexpected error, exit gracefully

    def _tcp_client_loop(self, sock):
        """Handle a single TCP client connection (master side)."""
        registered_id = None
        while self._running:
            try:
                data = sock.recv(4096)
                if not data:
                    break  # connection closed by peer
                for msg_type, payload in self._decode_all_messages(data):
                    new_id = self._handle_decoded_message(msg_type, payload, sock)
                    if new_id:
                        registered_id = new_id
            except socket.timeout:
                continue
            except socket.error:
                break
            except Exception as e:
                self.ui_queue.put({"type": "error", "payload": {"msg": f"网络线程异常: {e}"}})
                break  # unexpected error, exit gracefully
        # Clean up registered socket on disconnect
        if registered_id:
            with self._client_sockets_lock:
                self._client_sockets.pop(registered_id, None)
        try:
            sock.close()
        except Exception:
            pass

    def _heartbeat_loop(self):
        """Heartbeat thread: send heartbeats and prune expired peers."""
        last_beat = 0.0
        while self._running:
            now = time.time()
            if now - last_beat >= HEARTBEAT_INTERVAL:
                last_beat = now
                try:
                    self._send_broadcast_raw(
                        MSG_HEARTBEAT, {"node_id": self.node_id, "ts": now}
                    )
                except Exception:
                    pass
            self._prune_expired_peers(now)
            time.sleep(HEARTBEAT_LOOP_SLEEP)

    # ─── Message handlers ──────────────────────────────────────────────────

    def _handle_udp_message(self, data, addr):
        """Process a received UDP message."""
        result = decode_message(data)
        if result is None:
            return
        msg_type, payload = result
        if msg_type == MSG_HELLO:
            self._on_peer_hello(payload, addr)
        elif msg_type == MSG_HEARTBEAT:
            self._on_peer_heartbeat(payload, addr)
        elif msg_type == MSG_BYE:
            self._on_peer_bye(payload)

    def _decode_all_messages(self, data):
        """Extract all complete framed messages from a single recv buffer.

        Handles TCP sticky-packet: one recv may contain multiple messages
        concatenated together. Each frame is 4-byte BE length prefix + JSON body.

        Args:
            data: Raw bytes from a single ``sock.recv()`` call.

        Returns:
            list of (msg_type, payload) tuples for each complete frame found.
        """
        messages = []
        offset = 0
        while offset < len(data):
            result = decode_message(data[offset:])
            if result is None:
                break  # incomplete frame or corrupted data, stop
            msg_type, payload = result
            messages.append((msg_type, payload))
            # Calculate consumed bytes: 4-byte length prefix + declared body length
            if offset + 4 > len(data):
                break
            declared_len = struct.unpack_from(">I", data, offset)[0]
            offset += 4 + declared_len
        return messages

    def _handle_decoded_message(self, msg_type, payload, sender_sock=None):
        """Process a decoded TCP message.

        Returns the registered node_id if the message was a HELLO that
        registered a client socket, otherwise None.
        """
        if msg_type == MSG_HELLO:
            node_id = payload.get("node_id")
            if node_id and sender_sock is not None:
                with self._client_sockets_lock:
                    self._client_sockets[node_id] = sender_sock
                return node_id
            return None
        elif msg_type == MSG_VISIT_REQ:
            self.ui_queue.put({"type": msg_type, "payload": payload})
        elif msg_type == MSG_VISIT_ACK:
            self.ui_queue.put({"type": msg_type, "payload": payload})
        elif msg_type == MSG_VISIT_DATA:
            self.ui_queue.put({"type": msg_type, "payload": payload})
        elif msg_type == MSG_VISIT_LEAVE:
            self.ui_queue.put({"type": msg_type, "payload": payload})
        elif msg_type == MSG_HEARTBEAT:
            pass  # heartbeat, no ui_queue action needed
        elif msg_type == MSG_PEER_LIST:
            self._update_peers_from_list(payload.get("peers", []))
        elif msg_type == "relay":
            self._handle_relay(payload)
        return None

    def _handle_tcp_message(self, data, sender_sock=None):
        """Process a received TCP message (compatibility entry point).

        Decodes the first frame from raw bytes and delegates to
        ``_handle_decoded_message``. For new code, prefer calling
        ``_decode_all_messages`` + ``_handle_decoded_message`` directly
        to handle TCP sticky-packet correctly.
        """
        result = decode_message(data)
        if result is None:
            return None
        msg_type, payload = result
        return self._handle_decoded_message(msg_type, payload, sender_sock)

    def _handle_relay(self, payload):
        """Master forwards a relay message to the target slave."""
        target = payload.get("target")
        inner_msg_type = payload.get("msg_type")
        inner_payload = payload.get("payload")
        if not target or not inner_msg_type:
            return
        try:
            inner_data = encode_message(inner_msg_type, inner_payload)
            with self._client_sockets_lock:
                sock = self._client_sockets.get(target)
                if sock is not None:
                    try:
                        sock.sendall(inner_data)
                    except Exception:
                        pass
        except Exception:
            pass

    def _update_peers_from_list(self, peers):
        """Update peers from a list received from the master."""
        now = time.time()
        with self._peers_lock:
            for p in peers:
                node_id = p.get("node_id")
                if not node_id or node_id == self.node_id:
                    continue
                existing = self._peers.get(node_id)
                if existing is not None:
                    existing["last_seen"] = now
                else:
                    self._peers[node_id] = {
                        "node_id": node_id,
                        "username": p.get("username", ""),
                        "pet_summary": p.get("pet_summary", {}),
                        "last_seen": now,
                        "addr": None,
                        "ip": p.get("ip"),
                    }

    def _on_peer_hello(self, payload, addr):
        """Register or update a peer from a HELLO message, then re-elect master."""
        node_id = payload.get("node_id")
        if not node_id or node_id == self.node_id:
            return  # ignore self
        # 判断是否为新 peer
        is_new_peer = False
        with self._peers_lock:
            existing = self._peers.get(node_id)
            if existing is not None:
                # 已知 peer：仅更新 last_seen 和地址，保留旧 pet_summary
                existing["last_seen"] = time.time()
                existing["addr"] = addr
                existing["ip"] = addr[0] if addr else None
                # 若 payload 带了新快照（非 None），更新快照
                new_snapshot = payload.get("pet_summary")
                if new_snapshot is not None:
                    existing["pet_summary"] = new_snapshot
                existing["username"] = payload.get("username", existing.get("username", ""))
            else:
                # 新 peer：插入
                self._peers[node_id] = {
                    "node_id": node_id,
                    "username": payload.get("username", ""),
                    "pet_summary": payload.get("pet_summary") or {},
                    "last_seen": time.time(),
                    "addr": addr,
                    "ip": addr[0] if addr else None,
                }
                is_new_peer = True
        # 仅新 peer 触发重选
        if is_new_peer:
            changed = self._reelect_master()
            if changed:
                old_master, new_master = changed
                self._on_master_change(old_master, new_master)

    def _reelect_master(self):
        """Re-compute the master from the current peer set.

        Returns (old_master, new_master) if the master changed, else None.
        """
        with self._peers_lock:
            all_ids = [self.node_id] + list(self._peers.keys())
            old_master = self._master_id
            new_master = elect_master(all_ids)
            self._master_id = new_master
            self.is_master = (new_master == self.node_id)
        if new_master != old_master:
            return (old_master, new_master)
        return None

    def _on_master_change(self, old_master, new_master):
        """Handle a master change: connect to new master if slave."""
        try:
            # Close old master connection if any
            with self._client_sockets_lock:
                if self._master_sock is not None:
                    try:
                        self._master_sock.close()
                    except Exception:
                        pass
                    self._master_sock = None
            if self.is_master:
                # Became master: ensure TCP listener is running
                if self._tcp_socket is None:
                    self._start_tcp_listener()
            else:
                # Became slave: close TCP listener, connect to master
                self._close_tcp_listener()
                self._connect_to_master()
        except Exception:
            pass  # gradual degradation

    def _start_tcp_listener(self):
        """Start the TCP listener socket (master role)."""
        try:
            self._tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._tcp_socket.bind(("", self.tcp_port))
            self._tcp_socket.listen(5)
            self._tcp_socket.settimeout(SOCKET_TIMEOUT)
            t = threading.Thread(target=self._tcp_accept_loop, name="lan-tcp", daemon=True)
            t.start()
        except Exception:
            pass  # gradual degradation

    def _close_tcp_listener(self):
        """Close the TCP listener (slaves don't need it)."""
        if self._tcp_socket is not None:
            try:
                self._tcp_socket.close()
            except Exception:
                pass
            self._tcp_socket = None

    def _connect_to_master(self):
        """Slave connects to the master's TCP port."""
        if self.is_master:
            return  # master does not connect to itself
        with self._peers_lock:
            master_peer = self._peers.get(self._master_id)
        if not master_peer:
            return
        master_ip = master_peer.get("ip")
        if not master_ip:
            return
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect((master_ip, self.tcp_port))
            sock.settimeout(SOCKET_TIMEOUT)
            # Send HELLO to register with master
            snapshot = make_pet_snapshot(self.pet_state, self.username)
            hello = make_hello(self.node_id, self.username, snapshot)
            hello_payload = {k: v for k, v in hello.items() if k != "type"}
            sock.sendall(encode_message(MSG_HELLO, hello_payload))
            with self._client_sockets_lock:
                self._master_sock = sock
            # Start receive thread
            t = threading.Thread(target=self._recv_master_loop, daemon=True, name="lan-master-recv")
            t.start()
        except Exception:
            pass  # gradual degradation

    def _recv_master_loop(self):
        """Slave receive thread: read messages from the master."""
        try:
            while self._running:
                try:
                    data = self._master_sock.recv(4096)
                    if not data:
                        break  # connection closed
                    for msg_type, payload in self._decode_all_messages(data):
                        self._handle_decoded_message(msg_type, payload)
                except socket.timeout:
                    continue
                except Exception:
                    break
        except Exception:
            pass
        finally:
            # Only trigger failover if we were running (not during shutdown)
            if self._running:
                self._on_master_disconnect()

    def _on_master_disconnect(self):
        """Master disconnected — re-elect and reconnect."""
        try:
            with self._client_sockets_lock:
                if self._master_sock is not None:
                    try:
                        self._master_sock.close()
                    except Exception:
                        pass
                    self._master_sock = None
            # Remove old master from peers
            with self._peers_lock:
                if self._master_id and self._master_id in self._peers:
                    del self._peers[self._master_id]
            # Re-elect
            changed = self._reelect_master()
            new_master = self._master_id
            # Connect to new master if slave
            if not self.is_master:
                self._connect_to_master()
            # Notify UI
            self.ui_queue.put({
                "type": "master_change",
                "payload": {"new_master": new_master},
            })
        except Exception:
            pass  # gradual degradation

    def _on_peer_heartbeat(self, payload, addr):
        """Update peer's last_seen from a heartbeat."""
        node_id = payload.get("node_id")
        if not node_id:
            return
        with self._peers_lock:
            peer = self._peers.get(node_id)
            if peer is not None:
                peer["last_seen"] = time.time()

    def _on_peer_bye(self, payload):
        """Remove a peer that sent BYE."""
        node_id = payload.get("node_id")
        if not node_id:
            return
        with self._peers_lock:
            self._peers.pop(node_id, None)

    def _prune_expired_peers(self, now):
        """Remove peers not seen within PEER_TIMEOUT."""
        with self._peers_lock:
            expired = [
                nid for nid, p in self._peers.items()
                if is_peer_expired(p["last_seen"], now)
            ]
            for nid in expired:
                del self._peers[nid]

    def _broadcast_hello(self):
        """Send a HELLO broadcast.

        First call sends a full HELLO with pet_snapshot; subsequent calls
        send a lightweight HELLO (pet_summary=None) to save bandwidth.
        Receivers retain the previously cached snapshot.
        """
        if not self._hello_sent:
            snapshot = make_pet_snapshot(self.pet_state, self.username)
            hello = make_hello(self.node_id, self.username, snapshot)
            self._hello_sent = True
        else:
            hello = make_hello_lite(self.node_id, self.username)
        payload = {k: v for k, v in hello.items() if k != "type"}
        self._send_broadcast_raw(MSG_HELLO, payload)
