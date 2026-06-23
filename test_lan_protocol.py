#!/usr/bin/env python3
"""Pytest tests for lan_protocol.py — LAN multiplayer message protocol.

Covers:
- Message type constants (8 types)
- encode_message / decode_message round-trip with framing
- make_pet_snapshot (read-only field extraction)
- make_hello (greeting message)

Zero pip dependencies; stdlib only.
"""

import json
import os
import struct
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lan_protocol
from lan_protocol import (
    MSG_HELLO, MSG_PEER_LIST, MSG_HEARTBEAT,
    MSG_VISIT_REQ, MSG_VISIT_ACK, MSG_VISIT_DATA,
    MSG_VISIT_LEAVE, MSG_BYE,
    encode_message, decode_message,
    make_pet_snapshot, make_hello,
)


# ─── Message type constants ─────────────────────────────────────────────────


class TestMessageConstants:
    """Verify the 8 message type constants exist with correct string values."""

    def test_msg_hello(self):
        assert MSG_HELLO == "hello"

    def test_msg_peer_list(self):
        assert MSG_PEER_LIST == "peer_list"

    def test_msg_heartbeat(self):
        assert MSG_HEARTBEAT == "heartbeat"

    def test_msg_visit_req(self):
        assert MSG_VISIT_REQ == "visit_req"

    def test_msg_visit_ack(self):
        assert MSG_VISIT_ACK == "visit_ack"

    def test_msg_visit_data(self):
        assert MSG_VISIT_DATA == "visit_data"

    def test_msg_visit_leave(self):
        assert MSG_VISIT_LEAVE == "visit_leave"

    def test_msg_bye(self):
        assert MSG_BYE == "bye"

    def test_eight_distinct_constants(self):
        """All 8 constants are distinct strings."""
        consts = {
            MSG_HELLO, MSG_PEER_LIST, MSG_HEARTBEAT,
            MSG_VISIT_REQ, MSG_VISIT_ACK, MSG_VISIT_DATA,
            MSG_VISIT_LEAVE, MSG_BYE,
        }
        assert len(consts) == 8


# ─── encode_message / decode_message ────────────────────────────────────────


class TestEncodeDecode:
    """Framed encode/decode: 4-byte big-endian length prefix + UTF-8 JSON."""

    def test_roundtrip_basic(self):
        """Encode then decode returns original msg_type and payload."""
        raw = encode_message(MSG_HELLO, {"node_id": "abc", "username": "alice"})
        assert isinstance(raw, bytes)
        result = decode_message(raw)
        assert result is not None
        msg_type, payload = result
        assert msg_type == MSG_HELLO
        assert payload == {"node_id": "abc", "username": "alice"}

    def test_roundtrip_empty_payload(self):
        """Empty dict payload {} survives round-trip."""
        raw = encode_message(MSG_HEARTBEAT, {})
        result = decode_message(raw)
        assert result is not None
        msg_type, payload = result
        assert msg_type == MSG_HEARTBEAT
        assert payload == {}

    def test_roundtrip_chinese_pet_name(self):
        """Chinese / special characters in payload survive round-trip."""
        raw = encode_message(MSG_VISIT_DATA, {"pet_name": "Mochi喵", "mood": "excited"})
        result = decode_message(raw)
        assert result is not None
        _, payload = result
        assert payload["pet_name"] == "Mochi喵"
        assert payload["mood"] == "excited"

    def test_roundtrip_all_message_types(self):
        """Every message type constant can be encoded and decoded."""
        for msg_type in [
            MSG_HELLO, MSG_PEER_LIST, MSG_HEARTBEAT,
            MSG_VISIT_REQ, MSG_VISIT_ACK, MSG_VISIT_DATA,
            MSG_VISIT_LEAVE, MSG_BYE,
        ]:
            raw = encode_message(msg_type, {"k": "v"})
            result = decode_message(raw)
            assert result is not None
            assert result[0] == msg_type
            assert result[1] == {"k": "v"}

    def test_encode_returns_bytes(self):
        """encode_message always returns bytes."""
        raw = encode_message(MSG_BYE, {})
        assert isinstance(raw, bytes)

    def test_encode_format_length_prefix(self):
        """First 4 bytes are big-endian unsigned int = JSON byte length."""
        raw = encode_message(MSG_HELLO, {"a": 1})
        prefix = raw[:4]
        (declared_len,) = struct.unpack(">I", prefix)
        json_bytes = raw[4:]
        assert declared_len == len(json_bytes)
        # And the JSON portion decodes to expected structure
        obj = json.loads(json_bytes.decode("utf-8"))
        assert obj["type"] == MSG_HELLO
        assert obj["payload"] == {"a": 1}

    def test_decode_insufficient_data_returns_none(self):
        """Truncated buffer (< 4 bytes) returns None, does not crash."""
        assert decode_message(b"") is None
        assert decode_message(b"\x00") is None
        assert decode_message(b"\x00\x01") is None
        assert decode_message(b"\x00\x01\x02") is None

    def test_decode_truncated_payload_returns_none(self):
        """Length prefix declares more bytes than available → None."""
        raw = encode_message(MSG_HELLO, {"x": "y"})
        # Strip a few payload bytes
        truncated = raw[:-2]
        assert decode_message(truncated) is None

    def test_decode_corrupted_json_returns_none(self):
        """Corrupted JSON body returns None instead of raising."""
        # Build a frame whose length prefix is correct but JSON is invalid
        bad_json = b"{not valid json"
        frame = struct.pack(">I", len(bad_json)) + bad_json
        assert decode_message(frame) is None

    def test_decode_extra_trailing_bytes_ignored(self):
        """Decoder consumes exactly one frame; trailing bytes are ignored.

        Returns the first frame's (msg_type, payload).
        """
        raw = encode_message(MSG_HEARTBEAT, {"n": 1})
        # Append arbitrary trailing bytes
        padded = raw + b"\x99\x99\x99"
        result = decode_message(padded)
        assert result is not None
        msg_type, payload = result
        assert msg_type == MSG_HEARTBEAT
        assert payload == {"n": 1}


# ─── make_pet_snapshot ──────────────────────────────────────────────────────


def _full_pet_state():
    """Construct a state dict mirroring pet_core.init_state output shape."""
    return {
        "user_id": "uid-123",
        "name": "Mochi喵",
        "species": "cat",
        "rarity": 2,
        "eye": 1,
        "hat": 0,
        "shiny": True,
        "stats": {"HUNGER": 80, "ENERGY": 70, "HAPPY": 90},
        "mood": "excited",
        "created_at": "2026-01-01T00:00:00",
        "last_fed": "2026-01-01T00:00:00",
        "last_played": "2026-01-01T00:00:00",
        "last_slept": "2026-01-01T00:00:00",
        "level": 7,
        "xp": 350,
        "total_interactions": 42,
        "feed_count": 10,
        "play_count": 8,
        "sleep_count": 3,
        "achievements": ["first_pet"],
        "critical_since": None,
        "is_dead": False,
        "last_feed": None,
        "last_play": None,
        "last_sleep": None,
        "pet_count_hour": 0,
        "pet_hour_start": None,
    }


class TestMakePetSnapshot:
    """make_pet_snapshot extracts only whitelisted read-only fields."""

    def test_returns_dict(self):
        snap = make_pet_snapshot(_full_pet_state(), "alice")
        assert isinstance(snap, dict)

    def test_includes_required_fields(self):
        """Snapshot must include exactly the 9 whitelisted fields."""
        snap = make_pet_snapshot(_full_pet_state(), "alice")
        expected_keys = {
            "name", "species", "rarity", "level",
            "shiny", "eye", "hat", "mood", "owner",
        }
        assert set(snap.keys()) == expected_keys

    def test_field_values_match_state(self):
        """Each whitelisted field's value matches the source state."""
        state = _full_pet_state()
        snap = make_pet_snapshot(state, "alice")
        assert snap["name"] == state["name"]
        assert snap["species"] == state["species"]
        assert snap["rarity"] == state["rarity"]
        assert snap["level"] == state["level"]
        assert snap["shiny"] == state["shiny"]
        assert snap["eye"] == state["eye"]
        assert snap["hat"] == state["hat"]
        assert snap["mood"] == state["mood"]

    def test_owner_field_set_from_argument(self):
        """owner comes from the owner argument, not the state."""
        snap = make_pet_snapshot(_full_pet_state(), "bob")
        assert snap["owner"] == "bob"

    def test_does_not_leak_internal_state(self):
        """Snapshot must NOT contain stats, is_dead, critical_since, etc."""
        snap = make_pet_snapshot(_full_pet_state(), "alice")
        forbidden = {
            "stats", "is_dead", "critical_since",
            "last_fed", "last_played", "last_slept",
            "xp", "total_interactions", "feed_count",
            "play_count", "sleep_count", "achievements",
            "user_id", "created_at",
            "last_feed", "last_play", "last_sleep",
            "pet_count_hour", "pet_hour_start",
        }
        for key in forbidden:
            assert key not in snap, f"snapshot leaks internal field: {key}"

    def test_chinese_name_preserved(self):
        """Chinese characters in pet name are preserved verbatim."""
        snap = make_pet_snapshot(_full_pet_state(), "alice")
        assert snap["name"] == "Mochi喵"

    def test_snapshot_is_json_serializable(self):
        """Snapshot must be JSON-serializable for network transmission."""
        snap = make_pet_snapshot(_full_pet_state(), "alice")
        # Must not raise
        s = json.dumps(snap, ensure_ascii=False)
        # And round-trip
        assert json.loads(s) == snap


# ─── make_hello ─────────────────────────────────────────────────────────────


class TestMakeHello:
    """make_hello builds a hello message with required keys."""

    def test_returns_dict_with_type_hello(self):
        msg = make_hello("node-1", "alice", {"name": "Mochi"})
        assert isinstance(msg, dict)
        assert msg["type"] == "hello"

    def test_contains_required_keys(self):
        msg = make_hello("node-1", "alice", {"name": "Mochi"})
        assert set(msg.keys()) == {"type", "node_id", "username", "pet_summary", "timestamp"}

    def test_node_id_and_username_propagated(self):
        msg = make_hello("node-42", "bob", {"name": "Rex"})
        assert msg["node_id"] == "node-42"
        assert msg["username"] == "bob"

    def test_pet_summary_propagated(self):
        summary = {"name": "Mochi喵", "level": 5}
        msg = make_hello("node-1", "alice", summary)
        assert msg["pet_summary"] == summary
        # Same object reference is fine; values must match
        assert msg["pet_summary"]["name"] == "Mochi喵"

    def test_timestamp_is_float(self):
        msg = make_hello("node-1", "alice", {})
        assert isinstance(msg["timestamp"], float)

    def test_timestamp_close_to_now(self):
        """timestamp should be within a few seconds of time.time()."""
        before = time.time()
        msg = make_hello("node-1", "alice", {})
        after = time.time()
        assert before - 1.0 <= msg["timestamp"] <= after + 1.0

    def test_hello_is_json_serializable(self):
        """Hello message must be JSON-serializable for wire transmission."""
        summary = make_pet_snapshot(_full_pet_state(), "alice")
        msg = make_hello("node-1", "alice", summary)
        s = json.dumps(msg, ensure_ascii=False)
        decoded = json.loads(s)
        assert decoded["type"] == "hello"
        assert decoded["node_id"] == "node-1"
        assert decoded["pet_summary"]["name"] == "Mochi喵"

    def test_hello_can_be_encoded_via_encode_message(self):
        """End-to-end: hello → encode_message → decode_message."""
        summary = make_pet_snapshot(_full_pet_state(), "alice")
        msg = make_hello("node-1", "alice", summary)
        # The protocol's encode_message expects (msg_type, payload);
        # hello's payload is everything except the "type" key.
        payload = {k: v for k, v in msg.items() if k != "type"}
        raw = encode_message(MSG_HELLO, payload)
        result = decode_message(raw)
        assert result is not None
        msg_type, decoded_payload = result
        assert msg_type == MSG_HELLO
        assert decoded_payload["node_id"] == "node-1"
        assert decoded_payload["username"] == "alice"
        assert decoded_payload["pet_summary"]["name"] == "Mochi喵"
        assert isinstance(decoded_payload["timestamp"], float)
