#!/usr/bin/env python3
"""LAN multiplayer message protocol for ASCII pet.

Pure-data module: framing, encode/decode, snapshot extraction, hello builder.
Zero pip dependencies (stdlib only).

Wire format
-----------
Each message is framed as::

    +----------------+---------------------------+
    | 4 bytes BE u32 | UTF-8 JSON body           |
    | JSON length N  | (N bytes)                 |
    +----------------+---------------------------+

The JSON body is always an object of the form::

    {"type": <msg_type>, "payload": <payload_dict>}

This module is intentionally side-effect free so it can be unit tested
in isolation without sockets or threads.
"""

import json
import struct
import time

# ─── Message type constants ─────────────────────────────────────────────────

MSG_HELLO = "hello"
MSG_PEER_LIST = "peer_list"
MSG_HEARTBEAT = "heartbeat"
MSG_VISIT_REQ = "visit_req"
MSG_VISIT_ACK = "visit_ack"
MSG_VISIT_DATA = "visit_data"
MSG_VISIT_LEAVE = "visit_leave"
MSG_BYE = "bye"

# Visit-optimization message types (new).
MSG_VISIT_FEED = "visit_feed"
MSG_VISIT_PLAY = "visit_play"
MSG_VISIT_EVENT = "visit_event"
MSG_VISIT_END = "visit_end"
MSG_NAME_CHECK = "name_check"

# ─── Framing ────────────────────────────────────────────────────────────────

_LENGTH_PREFIX = struct.Struct(">I")  # 4-byte big-endian unsigned int


def encode_message(msg_type, payload):
    """Encode a message into framed bytes.

    Layout: 4-byte big-endian length prefix + UTF-8 JSON body.
    The JSON body is ``{"type": msg_type, "payload": payload}``.

    Args:
        msg_type: One of the MSG_* string constants.
        payload:  JSON-serializable dict (may be empty).

    Returns:
        bytes: The framed message.
    """
    body = json.dumps({"type": msg_type, "payload": payload}, ensure_ascii=False)
    body_bytes = body.encode("utf-8")
    return _LENGTH_PREFIX.pack(len(body_bytes)) + body_bytes


def decode_message(data):
    """Decode a framed message from bytes.

    Args:
        data: bytes received from the wire. May be incomplete or corrupted.

    Returns:
        tuple (msg_type, payload) on success, or ``None`` if:
          - fewer than 4 bytes are available,
          - the declared payload length is not yet available (truncated),
          - the JSON body cannot be parsed,
          - the parsed JSON is not the expected ``{"type", "payload"}`` shape.

    Trailing bytes after the first complete frame are ignored; callers
    handling streamed data should slice off the consumed frame themselves.
    """
    if not isinstance(data, (bytes, bytearray)):
        return None
    if len(data) < _LENGTH_PREFIX.size:
        return None
    (declared_len,) = _LENGTH_PREFIX.unpack_from(data, 0)
    end = _LENGTH_PREFIX.size + declared_len
    if len(data) < end:
        return None
    body_bytes = data[_LENGTH_PREFIX.size:end]
    try:
        obj = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    msg_type = obj.get("type")
    payload = obj.get("payload")
    if not isinstance(msg_type, str) or not isinstance(payload, dict):
        return None
    return msg_type, payload


# ─── Pet snapshot ───────────────────────────────────────────────────────────

# Whitelisted read-only fields exposed to other peers on the LAN.
# Deliberately excludes stats, is_dead, critical_since, timestamps, counters,
# achievements, user_id, etc. — anything that could leak internal state or
# be used to cheat.
_SNAPSHOT_FIELDS = (
    "name",
    "species",
    "rarity",
    "level",
    "shiny",
    "eye",
    "hat",
    "mood",
)


def make_pet_snapshot(state, owner):
    """Build a read-only snapshot of a pet for sharing over the LAN.

    Args:
        state: The pet state dict (as produced by ``pet_core.init_state``).
        owner: Username of the pet's owner (string).

    Returns:
        dict with exactly these keys:
        ``name, species, rarity, level, shiny, eye, hat, mood, owner``.
    """
    snap = {field: state[field] for field in _SNAPSHOT_FIELDS}
    snap["owner"] = owner
    return snap


# ─── Hello message builder ──────────────────────────────────────────────────


def make_hello(node_id, username, pet_summary):
    """Build a hello greeting message.

    Args:
        node_id:     Unique peer identifier (string).
        username:    Human-readable owner username (string).
        pet_summary: Read-only pet snapshot dict (from ``make_pet_snapshot``).

    Returns:
        dict with keys ``type, node_id, username, pet_summary, timestamp``.
        ``timestamp`` is ``time.time()`` (float, seconds since epoch).
    """
    return {
        "type": MSG_HELLO,
        "node_id": node_id,
        "username": username,
        "pet_summary": pet_summary,
        "timestamp": time.time(),
    }


# ─── Visit events ───────────────────────────────────────────────────────────


def make_visit_event(event_type, description, stat_effects):
    """Build a visit event dict for transmission during a pet visit.

    Args:
        event_type:   Event category string (e.g. ``"play_together"``).
        description:  Human-readable description of the event (string).
        stat_effects: Dict mapping stat names to integer deltas
                      (e.g. ``{"happy": 15, "energy": -10}``).

    Returns:
        dict with keys ``event_type, description, stat_effects``.
    """
    return {
        "event_type": event_type,
        "description": description,
        "stat_effects": stat_effects,
    }


VISIT_EVENTS = [
    {"event_type": "play_together", "description": "两只宠物一起玩耍，开心地追逐打闹！", "stat_effects": {"happy": 15, "energy": -10}},
    {"event_type": "share_food", "description": "两只宠物分享了食物，都吃得很开心！", "stat_effects": {"hunger": 15, "happy": 5}},
    {"event_type": "race", "description": "两只宠物进行了一场赛跑比赛，都消耗了体力！", "stat_effects": {"energy": -15, "happy": 10}},
    {"event_type": "chat", "description": "两只宠物聊得很投机，心情都变好了！", "stat_effects": {"happy": 10, "wisdom": 5}},
    {"event_type": "nap_together", "description": "两只宠物一起睡了个午觉，精力充沛！", "stat_effects": {"energy": 20, "hunger": -5}},
]
