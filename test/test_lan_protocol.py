#!/usr/bin/env python3
"""Pytest tests for lan_protocol.py — LAN multiplayer message protocol.

Covers:
- Message type constants (8 base + 5 visit-optimization types)
- encode_message / decode_message round-trip with framing
- make_pet_snapshot (read-only field extraction)
- make_hello (greeting message)
- make_visit_event (visit event builder)
- VISIT_EVENTS (preset visit event catalog)

Zero pip dependencies; stdlib only.
"""

import json
import os
import struct
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet import protocol as lan_protocol
from ascii_pet.protocol import (
    MSG_HELLO, MSG_PEER_LIST, MSG_HEARTBEAT,
    MSG_VISIT_REQ, MSG_VISIT_ACK, MSG_VISIT_DATA,
    MSG_VISIT_LEAVE, MSG_BYE,
    MSG_VISIT_FEED, MSG_VISIT_PLAY, MSG_VISIT_EVENT,
    MSG_VISIT_END, MSG_NAME_CHECK,
    encode_message, decode_message,
    make_pet_snapshot, make_hello,
    make_visit_event, VISIT_EVENTS,
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


# ─── Visit-optimization message type constants ──────────────────────────────


class TestVisitOptimizationConstants:
    """Verify the 5 new visit-optimization message type constants."""

    def test_msg_visit_feed(self):
        assert MSG_VISIT_FEED == "visit_feed"

    def test_msg_visit_play(self):
        assert MSG_VISIT_PLAY == "visit_play"

    def test_msg_visit_event(self):
        assert MSG_VISIT_EVENT == "visit_event"

    def test_msg_visit_end(self):
        assert MSG_VISIT_END == "visit_end"

    def test_msg_name_check(self):
        assert MSG_NAME_CHECK == "name_check"

    def test_five_new_constants_distinct(self):
        """All 5 new constants are distinct strings."""
        consts = {
            MSG_VISIT_FEED, MSG_VISIT_PLAY, MSG_VISIT_EVENT,
            MSG_VISIT_END, MSG_NAME_CHECK,
        }
        assert len(consts) == 5

    def test_new_constants_distinct_from_base(self):
        """New constants must not collide with the 8 base constants."""
        base = {
            MSG_HELLO, MSG_PEER_LIST, MSG_HEARTBEAT,
            MSG_VISIT_REQ, MSG_VISIT_ACK, MSG_VISIT_DATA,
            MSG_VISIT_LEAVE, MSG_BYE,
        }
        new = {
            MSG_VISIT_FEED, MSG_VISIT_PLAY, MSG_VISIT_EVENT,
            MSG_VISIT_END, MSG_NAME_CHECK,
        }
        assert base.isdisjoint(new)


# ─── make_visit_event ───────────────────────────────────────────────────────


class TestMakeVisitEvent:
    """make_visit_event builds a visit event dict with required structure."""

    def test_returns_dict(self):
        evt = make_visit_event("play_together", "desc", {"happy": 10})
        assert isinstance(evt, dict)

    def test_has_required_keys(self):
        evt = make_visit_event("play_together", "desc", {"happy": 10})
        assert set(evt.keys()) == {"event_type", "description", "stat_effects"}

    def test_event_type_propagated(self):
        evt = make_visit_event("race", "fast race", {"energy": -5})
        assert evt["event_type"] == "race"

    def test_description_propagated(self):
        evt = make_visit_event("chat", "聊得很开心", {"happy": 5})
        assert evt["description"] == "聊得很开心"

    def test_stat_effects_propagated(self):
        effects = {"hunger": 10, "happy": 5, "energy": -3}
        evt = make_visit_event("share_food", "shared food", effects)
        assert evt["stat_effects"] == effects

    def test_empty_stat_effects_allowed(self):
        evt = make_visit_event("chat", "no effect", {})
        assert evt["stat_effects"] == {}

    def test_is_json_serializable(self):
        """Visit event must be JSON-serializable for wire transmission."""
        evt = make_visit_event("play_together", "两只宠物一起玩耍", {"happy": 15, "energy": -10})
        s = json.dumps(evt, ensure_ascii=False)
        decoded = json.loads(s)
        assert decoded == evt
        assert decoded["description"] == "两只宠物一起玩耍"

    def test_chinese_description_preserved_through_json(self):
        """Chinese characters in description survive JSON round-trip."""
        evt = make_visit_event("nap_together", "午觉", {"energy": 20})
        s = json.dumps(evt, ensure_ascii=False)
        decoded = json.loads(s)
        assert decoded["description"] == "午觉"

    def test_stat_effects_values_can_be_negative(self):
        """stat_effects may contain negative values (e.g. energy drain)."""
        evt = make_visit_event("race", "tiring race", {"energy": -15, "happy": 10})
        assert evt["stat_effects"]["energy"] == -15
        assert evt["stat_effects"]["happy"] == 10


# ─── VISIT_EVENTS catalog ───────────────────────────────────────────────────


class TestVisitEventsCatalog:
    """VISIT_EVENTS is a preset catalog of visit event templates (Event objects)."""

    def test_is_list(self):
        assert isinstance(VISIT_EVENTS, list)

    def test_has_at_least_five_events(self):
        assert len(VISIT_EVENTS) >= 5

    def test_each_event_is_event(self):
        """Each entry in VISIT_EVENTS must be an Event instance."""
        from ascii_pet.events import Event
        for evt in VISIT_EVENTS:
            assert isinstance(evt, Event), f"event is not an Event: {evt!r}"

    def test_each_event_has_required_fields(self):
        """Each Event must expose event_id, description, effects, target, category, metadata."""
        for evt in VISIT_EVENTS:
            assert hasattr(evt, 'event_id')
            assert hasattr(evt, 'description')
            assert hasattr(evt, 'effects')
            assert hasattr(evt, 'target')
            assert hasattr(evt, 'category')
            assert hasattr(evt, 'metadata')

    def test_each_event_effects_is_dict(self):
        for evt in VISIT_EVENTS:
            assert isinstance(evt.effects, dict), \
                f"effects is not a dict: {evt!r}"

    def test_includes_required_event_types(self):
        """Catalog must include the 5 required original event types."""
        required = {"play_together", "share_food", "race", "chat", "nap_together"}
        actual = {evt.metadata.get('original_event_type', evt.event_id) for evt in VISIT_EVENTS}
        assert required.issubset(actual), \
            f"missing event types: {required - actual}"

    def test_event_types_unique(self):
        """Each original_event_type should be unique within the catalog."""
        types = [evt.metadata.get('original_event_type', evt.event_id) for evt in VISIT_EVENTS]
        assert len(types) == len(set(types)), \
            f"duplicate event types: {types}"

    def test_stat_effects_values_in_reasonable_range(self):
        """All stat effect values should be in [-20, +20]."""
        for evt in VISIT_EVENTS:
            for stat, value in evt.effects.items():
                assert -20 <= value <= 20, \
                    f"{evt.event_id}.{stat}={value} out of [-20, 20]"

    def test_each_event_json_serializable(self):
        """Every event in the catalog must be JSON-serializable via serialize_event."""
        from ascii_pet.events import serialize_event
        for evt in VISIT_EVENTS:
            serialized = serialize_event(evt)
            s = json.dumps(serialized, ensure_ascii=False)
            assert json.loads(s) == serialized

    def test_descriptions_are_non_empty_strings(self):
        for evt in VISIT_EVENTS:
            assert isinstance(evt.description, str)
            assert len(evt.description) > 0


# ─── encode/decode round-trip for new message types ─────────────────────────


class TestEncodeDecodeNewVisitMessages:
    """The 5 new message types must survive encode → decode round-trip."""

    def test_roundtrip_visit_feed(self):
        payload = {"target": "node-2", "food": "apple", "amount": 1}
        raw = encode_message(MSG_VISIT_FEED, payload)
        result = decode_message(raw)
        assert result is not None
        msg_type, decoded = result
        assert msg_type == MSG_VISIT_FEED
        assert decoded == payload

    def test_roundtrip_visit_play(self):
        payload = {"target": "node-2", "game": "catch"}
        raw = encode_message(MSG_VISIT_PLAY, payload)
        result = decode_message(raw)
        assert result is not None
        msg_type, decoded = result
        assert msg_type == MSG_VISIT_PLAY
        assert decoded == payload

    def test_roundtrip_visit_event(self):
        """visit_event payload carries a make_visit_event dict."""
        evt = make_visit_event("play_together", "一起玩耍", {"happy": 15, "energy": -10})
        raw = encode_message(MSG_VISIT_EVENT, evt)
        result = decode_message(raw)
        assert result is not None
        msg_type, decoded = result
        assert msg_type == MSG_VISIT_EVENT
        assert decoded == evt
        assert decoded["event_type"] == "play_together"
        assert decoded["description"] == "一起玩耍"

    def test_roundtrip_visit_end(self):
        payload = {"reason": "user_left", "duration": 120}
        raw = encode_message(MSG_VISIT_END, payload)
        result = decode_message(raw)
        assert result is not None
        msg_type, decoded = result
        assert msg_type == MSG_VISIT_END
        assert decoded == payload

    def test_roundtrip_name_check(self):
        payload = {"name": "Mochi喵", "node_id": "node-1"}
        raw = encode_message(MSG_NAME_CHECK, payload)
        result = decode_message(raw)
        assert result is not None
        msg_type, decoded = result
        assert msg_type == MSG_NAME_CHECK
        assert decoded == payload

    def test_roundtrip_all_new_types_iterate(self):
        """All 5 new types round-trip in a loop with non-trivial payloads."""
        samples = {
            MSG_VISIT_FEED: {"food": "apple"},
            MSG_VISIT_PLAY: {"game": "tag"},
            MSG_VISIT_EVENT: {"event_type": "chat", "description": "d", "stat_effects": {}},
            MSG_VISIT_END: {"reason": "done"},
            MSG_NAME_CHECK: {"name": "Mochi"},
        }
        for msg_type, payload in samples.items():
            raw = encode_message(msg_type, payload)
            result = decode_message(raw)
            assert result is not None, f"decode failed for {msg_type}"
            assert result[0] == msg_type
            assert result[1] == payload

    def test_visit_event_from_catalog_roundtrips(self):
        """Each VISIT_EVENTS entry can be sent as a visit_event payload."""
        for evt in VISIT_EVENTS:
            # Build the wire-format dict via make_visit_event (as production does)
            event_type = evt.metadata.get('original_event_type', evt.event_id)
            payload = make_visit_event(event_type, evt.description, evt.effects)
            raw = encode_message(MSG_VISIT_EVENT, payload)
            result = decode_message(raw)
            assert result is not None
            msg_type, decoded = result
            assert msg_type == MSG_VISIT_EVENT
            assert decoded == payload


# ─── make_hello_lite ────────────────────────────────────────────────────────


class TestMakeHelloLite:
    """make_hello_lite: 构造不含 pet_summary 的轻量 HELLO。"""

    def test_returns_dict_with_required_fields(self):
        from ascii_pet.protocol import make_hello_lite
        result = make_hello_lite("node-1", "alice")
        assert isinstance(result, dict)
        for key in ("type", "node_id", "username", "timestamp", "pet_summary"):
            assert key in result, f"缺少键: {key}"

    def test_type_is_hello(self):
        from ascii_pet.protocol import make_hello_lite, MSG_HELLO
        result = make_hello_lite("node-1", "alice")
        assert result["type"] == MSG_HELLO

    def test_node_id_and_username_correct(self):
        from ascii_pet.protocol import make_hello_lite
        result = make_hello_lite("node-1", "alice")
        assert result["node_id"] == "node-1"
        assert result["username"] == "alice"

    def test_pet_summary_is_none(self):
        from ascii_pet.protocol import make_hello_lite
        result = make_hello_lite("node-1", "alice")
        assert result["pet_summary"] is None

    def test_timestamp_is_float(self):
        from ascii_pet.protocol import make_hello_lite
        result = make_hello_lite("node-1", "alice")
        assert isinstance(result["timestamp"], float)

    def test_encode_decode_roundtrip(self):
        from ascii_pet.protocol import make_hello_lite, encode_message, decode_message, MSG_HELLO
        result = make_hello_lite("node-1", "alice")
        payload = {k: v for k, v in result.items() if k != "type"}
        data = encode_message(MSG_HELLO, payload)
        msg_type, decoded_payload = decode_message(data)
        assert msg_type == MSG_HELLO
        assert decoded_payload["node_id"] == "node-1"
        assert decoded_payload["pet_summary"] is None
