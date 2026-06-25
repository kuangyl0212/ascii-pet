#!/usr/bin/env python3
"""LAN multiplayer message protocol for ASCII pet.

Pure-data module: framing, encode/decode, snapshot extraction, hello builder.
Runtime dependency: loguru (transitive).

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

from ascii_pet.events import REGISTRY

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

# Battle / gift / trade message types (Task 6).
MSG_CHALLENGE_REQ = "challenge_req"
MSG_CHALLENGE_ACK = "challenge_ack"
MSG_CHALLENGE_RESULT = "challenge_result"
MSG_GIFT_ITEM = "gift_item"
MSG_GIFT_ACK = "gift_ack"
MSG_TRADE_REQ = "trade_req"
MSG_TRADE_ACK = "trade_ack"
MSG_TRADE_CONFIRM = "trade_confirm"
MSG_TRADE_COMPLETE = "trade_complete"

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

# Combat fields added to snapshots in Task 6. These may not exist in older
# pet states, so make_pet_snapshot uses .get() with defaults for backward
# compatibility. make_battle_snapshot computes them via calculate_combat_stats.
_COMBAT_SNAPSHOT_DEFAULTS = {
    "hp": 100,
    "attack": 0,
    "defense": 0,
    "speed": 0,
    "skills": list,
}


def make_pet_snapshot(state, owner):
    """Build a read-only snapshot of a pet for sharing over the LAN.

    Args:
        state: The pet state dict (as produced by ``pet_core.init_state``).
        owner: Username of the pet's owner (string).

    Returns:
        dict with these keys:
        ``name, species, rarity, level, shiny, eye, hat, mood, owner`` plus
        combat fields ``hp, attack, defense, speed, skills``. The combat
        fields use ``state.get(field, default)`` so older states without
        combat data still produce a valid snapshot.
    """
    snap = {field: state[field] for field in _SNAPSHOT_FIELDS}
    for field, default in _COMBAT_SNAPSHOT_DEFAULTS.items():
        value = state.get(field)
        if value is None:
            snap[field] = default() if callable(default) else default
        else:
            snap[field] = list(value) if field == "skills" else value
    snap["owner"] = owner
    return snap


def make_battle_snapshot(state, owner):
    """Build a battle-ready snapshot including calculated combat stats.

    Unlike ``make_pet_snapshot`` (which reads combat fields verbatim from
    state with defaults), this function calls ``calculate_combat_stats`` to
    derive hp/attack/defense/speed/skills from the pet's level, rarity, and
    species. Use this when sending a pet into a LAN battle.

    Args:
        state: The pet state dict (as produced by ``pet_core.init_state``).
        owner: Username of the pet's owner (string).

    Returns:
        dict with keys:
        ``name, species, rarity, level, shiny, owner, hp, attack, defense,
        speed, skills``.
    """
    from ascii_pet.core import calculate_combat_stats
    combat = calculate_combat_stats(state)
    return {
        "name": state["name"],
        "species": state["species"],
        "rarity": state["rarity"],
        "level": state["level"],
        "shiny": state.get("shiny", False),
        "owner": owner,
        "hp": combat["hp"],
        "attack": combat["attack"],
        "defense": combat["defense"],
        "speed": combat["speed"],
        "skills": combat["skills"],
    }


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


def make_hello_lite(node_id, username):
    """Build a lightweight HELLO message without pet_snapshot.

    Used for subsequent HELLO broadcasts after the first one. Receivers
    retain the previously cached pet_summary.

    Args:
        node_id:  Unique peer identifier (string).
        username: Human-readable owner username (string).

    Returns:
        dict with keys ``type, node_id, username, timestamp, pet_summary``.
        ``pet_summary`` is ``None`` to signal "no snapshot, keep cached".
    """
    return {
        "type": MSG_HELLO,
        "node_id": node_id,
        "username": username,
        "timestamp": time.time(),
        "pet_summary": None,
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
        dict with keys ``event_type, description, stat_effects``. The
        ``stat_effects`` keys are normalized to lowercase to preserve the
        pre-migration wire format that receivers expect.
    """
    from ascii_pet.events import Event, serialize_event
    event = Event(
        event_id=event_type,
        description=description,
        effects=stat_effects,
        target='self',
        category='visit',
    )
    serialized = serialize_event(event)
    # Event normalizes effects keys to UPPERCASE; convert back to lowercase
    # for wire compatibility with the pre-migration visit-event format.
    lowercase_effects = {k.lower(): v for k, v in serialized['effects'].items()}
    return {
        "event_type": serialized['event_id'],
        "description": serialized['description'],
        "stat_effects": lowercase_effects,
    }


# VISIT_EVENTS is sourced from the unified REGISTRY in ascii_pet.events.
# Each entry is an Event object (not a dict). Migration (Task 4): original
# dict constants are now Event lists. Visit event_ids that would collide
# with PET_INTERACTIONS ids are prefixed with 'visit_'; the original
# event_type is preserved in metadata['original_event_type'].
VISIT_EVENTS = REGISTRY.by_category('visit')
