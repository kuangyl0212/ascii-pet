"""TDD tests for the unified event system (Task 1: skeleton + Task 2: apply_event).

Covers:
  - Event dataclass (frozen, effects key uppercasing, defaults)
  - EventRegistry (register, get, by_category, all, random, duplicate guard)
  - Global REGISTRY singleton
  - apply_event() (Task 2): stat-gate, chaos_bump, item_drop, xp, target, clamp

These tests are written BEFORE the implementation per strict TDD.
The implementation lives in src/ascii_pet/events.py.
"""
import dataclasses
import sys
import os

# Ensure src/ is importable when run directly
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pytest

from ascii_pet.events import Event, EventRegistry, REGISTRY


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

class TestEventFrozen:
    """Event must be a frozen dataclass."""

    def test_event_is_frozen_dataclass(self):
        """Event should be decorated with @dataclass(frozen=True)."""
        fields = dataclasses.fields(Event)
        # Sanity: it is a dataclass at all
        assert dataclasses.is_dataclass(Event)
        # Frozen check: attempting to set a field raises FrozenInstanceError
        event = Event('test', 'desc', {'happy': 5})
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.event_id = 'mutated'  # type: ignore[misc]

    def test_event_id_immutable(self):
        """Modifying event_id must raise FrozenInstanceError."""
        event = Event('test', 'desc', {'happy': 5})
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.event_id = 'other'  # type: ignore[misc]


class TestEventEffectsUppercase:
    """Event constructor must uppercase effects keys."""

    def test_lowercase_keys_become_uppercase(self):
        event = Event('test', 'desc', {'happy': 5})
        assert event.effects == {'HAPPY': 5}

    def test_mixed_case_keys_become_uppercase(self):
        event = Event('test', 'desc', {'Happy': 5, 'HUNGER': 3})
        assert event.effects == {'HAPPY': 5, 'HUNGER': 3}

    def test_already_uppercase_keys_unchanged(self):
        event = Event('test', 'desc', {'HAPPY': 5})
        assert event.effects == {'HAPPY': 5}

    def test_empty_effects_dict(self):
        event = Event('test', 'desc', {})
        assert event.effects == {}


class TestEventDefaults:
    """Event must provide sensible defaults for target, category, metadata."""

    def test_default_target_is_self(self):
        event = Event('test', 'desc', {'happy': 5})
        assert event.target == 'self'

    def test_default_category_is_solo(self):
        event = Event('test', 'desc', {'happy': 5})
        assert event.category == 'solo'

    def test_default_metadata_is_empty_dict(self):
        event = Event('test', 'desc', {'happy': 5})
        assert event.metadata == {}

    def test_default_metadata_not_shared_between_instances(self):
        """Each instance must get its own metadata dict (no shared mutable default)."""
        a = Event('a', 'desc', {'happy': 1})
        b = Event('b', 'desc', {'happy': 2})
        a.metadata['x'] = 1
        assert b.metadata == {}, 'metadata dicts must not be shared between instances'

    def test_explicit_fields_respected(self):
        event = Event(
            'test', 'desc', {'happy': 5},
            target='both', category='visit', metadata={'xp': 3},
        )
        assert event.target == 'both'
        assert event.category == 'visit'
        assert event.metadata == {'xp': 3}


# ---------------------------------------------------------------------------
# EventRegistry
# ---------------------------------------------------------------------------

class TestEventRegistryRegister:
    """EventRegistry.register adds events and rejects duplicates."""

    def test_register_then_get_returns_event(self):
        reg = EventRegistry()
        ev = Event('mood_boost', 'desc', {'happy': 5})
        reg.register(ev)
        assert reg.get('mood_boost') is ev

    def test_register_unknown_returns_none(self):
        reg = EventRegistry()
        assert reg.get('does_not_exist') is None

    def test_register_duplicate_raises_value_error(self):
        reg = EventRegistry()
        reg.register(Event('mood_boost', 'desc', {'happy': 5}))
        with pytest.raises(ValueError):
            reg.register(Event('mood_boost', 'other desc', {'happy': 7}))


class TestEventRegistryByCategory:
    """EventRegistry.by_category returns matching events."""

    def test_by_category_returns_only_matching(self):
        reg = EventRegistry()
        solo = Event('a', 'd', {'happy': 1}, category='solo')
        visit = Event('b', 'd', {'happy': 1}, category='visit')
        interaction = Event('c', 'd', {'happy': 1}, category='interaction')
        for e in (solo, visit, interaction):
            reg.register(e)
        result = reg.by_category('visit')
        assert result == [visit]

    def test_by_category_empty_when_no_match(self):
        reg = EventRegistry()
        reg.register(Event('a', 'd', {'happy': 1}, category='solo'))
        assert reg.by_category('visit') == []

    def test_by_category_returns_multiple(self):
        reg = EventRegistry()
        v1 = Event('v1', 'd', {'happy': 1}, category='visit')
        v2 = Event('v2', 'd', {'happy': 1}, category='visit')
        reg.register(v1)
        reg.register(v2)
        result = reg.by_category('visit')
        # Event contains dict fields (unhashable), so compare as sorted list
        assert sorted(result, key=lambda e: e.event_id) == sorted([v1, v2], key=lambda e: e.event_id)


class TestEventRegistryAll:
    """EventRegistry.all returns every registered event."""

    def test_all_empty_when_nothing_registered(self):
        reg = EventRegistry()
        assert reg.all() == []

    def test_all_returns_every_registered_event(self):
        reg = EventRegistry()
        e1 = Event('a', 'd', {'happy': 1})
        e2 = Event('b', 'd', {'happy': 1}, category='visit')
        reg.register(e1)
        reg.register(e2)
        result = reg.all()
        # Event contains dict fields (unhashable), so compare as sorted list
        assert sorted(result, key=lambda e: e.event_id) == sorted([e1, e2], key=lambda e: e.event_id)

    def test_all_returns_a_list(self):
        reg = EventRegistry()
        reg.register(Event('a', 'd', {'happy': 1}))
        result = reg.all()
        assert isinstance(result, list)


class TestEventRegistryRandom:
    """EventRegistry.random returns a random event, optionally filtered."""

    def test_random_returns_registered_event(self):
        reg = EventRegistry()
        e1 = Event('a', 'd', {'happy': 1})
        e2 = Event('b', 'd', {'happy': 1})
        reg.register(e1)
        reg.register(e2)
        result = reg.random()
        assert result in (e1, e2)

    def test_random_with_category_filter(self):
        reg = EventRegistry()
        solo = Event('a', 'd', {'happy': 1}, category='solo')
        visit = Event('b', 'd', {'happy': 1}, category='visit')
        reg.register(solo)
        reg.register(visit)
        result = reg.random(category='visit')
        assert result is visit

    def test_random_default_category_none_considers_all(self):
        reg = EventRegistry()
        e1 = Event('a', 'd', {'happy': 1}, category='solo')
        e2 = Event('b', 'd', {'happy': 1}, category='visit')
        reg.register(e1)
        reg.register(e2)
        # Should be able to return either over many draws (statistical sanity)
        # Event contains dict fields (unhashable), so track by event_id
        seen = {reg.random().event_id for _ in range(50)}
        assert seen <= {'a', 'b'}
        assert seen  # not empty

    def test_random_on_empty_registry_raises(self):
        """Calling random() on an empty registry should raise IndexError."""
        reg = EventRegistry()
        with pytest.raises(IndexError):
            reg.random()

    def test_random_with_category_no_matches_raises(self):
        reg = EventRegistry()
        reg.register(Event('a', 'd', {'happy': 1}, category='solo'))
        with pytest.raises(IndexError):
            reg.random(category='visit')


# ---------------------------------------------------------------------------
# Global REGISTRY singleton
# ---------------------------------------------------------------------------

class TestGlobalRegistry:
    """A module-level REGISTRY singleton must exist as an EventRegistry."""

    def test_registry_is_event_registry_instance(self):
        assert isinstance(REGISTRY, EventRegistry)

    def test_registry_populated_with_builtins(self):
        """Task 4 registers builtin events (solo/interaction/visit) into REGISTRY."""
        # REGISTRY should no longer be empty after Task 4 migration.
        assert len(REGISTRY.all()) > 0

    def test_registry_is_singleton(self):
        """Importing REGISTRY twice yields the same object."""
        from ascii_pet.events import REGISTRY as r2
        assert r2 is REGISTRY


# ---------------------------------------------------------------------------
# apply_event (Task 2)
# ---------------------------------------------------------------------------
# Tests below are written BEFORE apply_event() exists. Per strict TDD they
# must FAIL first (AttributeError on import / call), then PASS once the
# function is implemented in src/ascii_pet/events.py.

from ascii_pet.events import apply_event  # noqa: E402


def _make_state(hunger=50, happy=50, energy=50, wisdom=50, chaos=0, xp=0):
    """Build a minimal pet state dict matching core.py's structure."""
    return {
        'stats': {
            'HUNGER': hunger,
            'HAPPY': happy,
            'ENERGY': energy,
            'WISDOM': wisdom,
            'CHAOS': chaos,
        },
        'xp': xp,
    }


class TestApplyEventStatGate:
    """stat-gate: positive effects skipped when stat >= 80."""

    def test_stat_gate_blocks_heal_when_stat_above_80(self):
        """HUNGER=95, +5 with stat_gate=True → stays 95."""
        state = _make_state(hunger=95)
        event = Event('feed', 'desc', {'HUNGER': 5})
        apply_event(state, event, stat_gate=True)
        assert state['stats']['HUNGER'] == 95

    def test_stat_gate_off_forces_heal(self):
        """HUNGER=95, +5 with stat_gate=False → becomes 100."""
        state = _make_state(hunger=95)
        event = Event('feed', 'desc', {'HUNGER': 5})
        apply_event(state, event, stat_gate=False)
        assert state['stats']['HUNGER'] == 100

    def test_stat_gate_does_not_block_negative_effects(self):
        """Negative effects apply even when stat >= 80 (stat-gate only blocks heals)."""
        state = _make_state(happy=90)
        event = Event('spook', 'desc', {'HAPPY': -5})
        apply_event(state, event, stat_gate=True)
        assert state['stats']['HAPPY'] == 85

    def test_stat_gate_does_not_block_when_stat_below_80(self):
        """Positive effect applies normally when stat < 80."""
        state = _make_state(hunger=70)
        event = Event('feed', 'desc', {'HUNGER': 5})
        apply_event(state, event, stat_gate=True)
        assert state['stats']['HUNGER'] == 75

    def test_stat_gate_default_is_true(self):
        """When stat_gate is omitted, default behavior is gate ON."""
        state = _make_state(hunger=95)
        event = Event('feed', 'desc', {'HUNGER': 5})
        apply_event(state, event)
        assert state['stats']['HUNGER'] == 95


class TestApplyEventChaosBump:
    """chaos_bump: any negative effect bumps CHAOS by 3 (once per event)."""

    def test_negative_event_bumps_chaos(self):
        """CHAOS=50, event with HAPPY=-5 → CHAOS becomes 53."""
        state = _make_state(chaos=50)
        event = Event('spook', 'desc', {'HAPPY': -5})
        apply_event(state, event, chaos_bump=True)
        assert state['stats']['CHAOS'] == 53

    def test_chaos_caps_at_100(self):
        """CHAOS=99, negative event → CHAOS caps at 100 (not 102)."""
        state = _make_state(chaos=99)
        event = Event('spook', 'desc', {'HAPPY': -5})
        apply_event(state, event, chaos_bump=True)
        assert state['stats']['CHAOS'] == 100

    def test_chaos_bump_false_skips(self):
        """chaos_bump=False → CHAOS unchanged even with negative effect."""
        state = _make_state(chaos=50)
        event = Event('spook', 'desc', {'HAPPY': -5})
        apply_event(state, event, chaos_bump=False)
        assert state['stats']['CHAOS'] == 50

    def test_positive_event_does_not_bump_chaos(self):
        """All-positive event → CHAOS unchanged."""
        state = _make_state(chaos=50)
        event = Event('mood_boost', 'desc', {'HAPPY': 5})
        apply_event(state, event, chaos_bump=True)
        assert state['stats']['CHAOS'] == 50

    def test_bump_happens_once_per_event_with_multiple_negatives(self):
        """Multiple negative stats in one event → CHAOS bumps only +3, not +6."""
        state = _make_state(chaos=50, hunger=50, happy=50)
        event = Event('bad_day', 'desc', {'HUNGER': -5, 'HAPPY': -5})
        apply_event(state, event, chaos_bump=True)
        assert state['stats']['CHAOS'] == 53

    def test_chaos_bump_default_is_true(self):
        """When chaos_bump is omitted, default behavior is bump ON."""
        state = _make_state(chaos=50)
        event = Event('spook', 'desc', {'HAPPY': -5})
        apply_event(state, event)
        assert state['stats']['CHAOS'] == 53


class TestApplyEventItemDrop:
    """item_drop: metadata['item_drop'] triggers inventory_adder callback."""

    def test_item_drop_calls_adder_and_stores_returned_id(self):
        """metadata={'item_drop':True} + adder → adder called, item_dropped set."""
        state = _make_state()
        event = Event('find_item', 'desc', {}, metadata={'item_drop': True})
        called = []

        def adder():
            called.append(True)
            return 'apple'

        result = apply_event(state, event, inventory_adder=adder)
        assert called == [True]
        assert result['item_dropped'] == 'apple'

    def test_item_drop_no_adder_returns_none(self):
        """metadata has item_drop but no adder provided → item_dropped is None."""
        state = _make_state()
        event = Event('find_item', 'desc', {}, metadata={'item_drop': True})
        result = apply_event(state, event, inventory_adder=None)
        assert result['item_dropped'] is None

    def test_no_item_drop_metadata_returns_none(self):
        """No item_drop in metadata → item_dropped is None, adder not called."""
        state = _make_state()
        event = Event('mood_boost', 'desc', {'HAPPY': 5})
        called = []

        def adder():
            called.append(True)
            return 'apple'

        result = apply_event(state, event, inventory_adder=adder)
        assert result['item_dropped'] is None
        assert called == []

    def test_item_drop_adder_returns_none(self):
        """If adder returns None (e.g. inventory full), item_dropped is None."""
        state = _make_state()
        event = Event('find_item', 'desc', {}, metadata={'item_drop': True})

        def adder():
            return None

        result = apply_event(state, event, inventory_adder=adder)
        assert result['item_dropped'] is None


class TestApplyEventXp:
    """xp: metadata['xp'] adds to state['xp'] and reports xp_gained."""

    def test_xp_metadata_adds_to_state_xp(self):
        """state['xp']=10, metadata={'xp':3} → state['xp']=13, xp_gained=3."""
        state = _make_state(xp=10)
        event = Event('learn', 'desc', {}, metadata={'xp': 3})
        result = apply_event(state, event)
        assert state['xp'] == 13
        assert result['xp_gained'] == 3

    def test_no_xp_metadata_returns_zero(self):
        """No xp in metadata → xp_gained=0, state['xp'] unchanged."""
        state = _make_state(xp=10)
        event = Event('mood_boost', 'desc', {'HAPPY': 5})
        result = apply_event(state, event)
        assert state['xp'] == 10
        assert result['xp_gained'] == 0

    def test_xp_zero_in_metadata(self):
        """metadata={'xp':0} → xp_gained=0, state['xp'] unchanged."""
        state = _make_state(xp=10)
        event = Event('learn', 'desc', {}, metadata={'xp': 0})
        result = apply_event(state, event)
        assert state['xp'] == 10
        assert result['xp_gained'] == 0


class TestApplyEventTarget:
    """target: 'self' / 'both' / 'other' select which pets receive effects."""

    def test_target_self_only_affects_current_state(self):
        """target='self' → only the passed state is modified."""
        state = _make_state(happy=30)
        other = _make_state(happy=30)
        pets_data = {'pets': [state, other]}
        event = Event('mood_boost', 'desc', {'HAPPY': 5}, target='self')
        apply_event(state, event, pets_data=pets_data)
        assert state['stats']['HAPPY'] == 35
        assert other['stats']['HAPPY'] == 30

    def test_target_both_affects_all_pets(self):
        """target='both' → all pets in pets_data['pets'] get the effect."""
        pet1 = _make_state(happy=30)
        pet2 = _make_state(happy=40)
        pets_data = {'pets': [pet1, pet2]}
        event = Event('play_together', 'desc', {'HAPPY': 5}, target='both')
        apply_event(pet1, event, pets_data=pets_data)
        assert pet1['stats']['HAPPY'] == 35
        assert pet2['stats']['HAPPY'] == 45

    def test_target_other_affects_all_except_current(self):
        """target='other' → only non-current pets get the effect."""
        pet1 = _make_state(happy=30)
        pet2 = _make_state(happy=40)
        pet3 = _make_state(happy=50)
        pets_data = {'pets': [pet1, pet2, pet3]}
        event = Event('gift', 'desc', {'HAPPY': 5}, target='other')
        apply_event(pet1, event, pets_data=pets_data)
        assert pet1['stats']['HAPPY'] == 30  # current unchanged
        assert pet2['stats']['HAPPY'] == 45
        assert pet3['stats']['HAPPY'] == 55

    def test_target_both_item_drop_only_on_current_state(self):
        """target='both' → item_drop applies only to current pet (not duplicated)."""
        pet1 = _make_state()
        pet2 = _make_state()
        pets_data = {'pets': [pet1, pet2]}
        event = Event('group_find', 'desc', {'HAPPY': 5},
                      target='both', metadata={'item_drop': True})
        calls = []

        def adder():
            calls.append(True)
            return 'apple'

        result = apply_event(pet1, event, pets_data=pets_data, inventory_adder=adder)
        assert len(calls) == 1  # not called per-pet
        assert result['item_dropped'] == 'apple'

    def test_target_both_xp_only_on_current_state(self):
        """target='both' → xp applies only to current pet (not duplicated)."""
        pet1 = _make_state(xp=10)
        pet2 = _make_state(xp=10)
        pets_data = {'pets': [pet1, pet2]}
        event = Event('group_learn', 'desc', {'HAPPY': 5},
                      target='both', metadata={'xp': 3})
        result = apply_event(pet1, event, pets_data=pets_data)
        assert pet1['xp'] == 13
        assert pet2['xp'] == 10  # other pet does NOT get xp
        assert result['xp_gained'] == 3

    def test_target_both_stat_gate_applies_per_pet(self):
        """target='both' → stat-gate is evaluated per-pet, not globally."""
        pet1 = _make_state(happy=90)   # gated, no change
        pet2 = _make_state(happy=30)   # not gated, +5
        pets_data = {'pets': [pet1, pet2]}
        event = Event('play_together', 'desc', {'HAPPY': 5}, target='both')
        apply_event(pet1, event, pets_data=pets_data, stat_gate=True)
        assert pet1['stats']['HAPPY'] == 90
        assert pet2['stats']['HAPPY'] == 35

    def test_target_both_chaos_bump_applies_per_pet(self):
        """target='both' → chaos_bump is applied per-pet (each pet's CHAOS bumps)."""
        pet1 = _make_state(chaos=50, happy=50)
        pet2 = _make_state(chaos=10, happy=50)
        pets_data = {'pets': [pet1, pet2]}
        event = Event('group_spook', 'desc', {'HAPPY': -5}, target='both')
        apply_event(pet1, event, pets_data=pets_data, chaos_bump=True)
        assert pet1['stats']['CHAOS'] == 53
        assert pet2['stats']['CHAOS'] == 13


class TestApplyEventClamp:
    """All stat changes clamp to [0, 100]."""

    def test_stat_clamps_to_zero(self):
        """HUNGER=3, -10 → 0 (not -7)."""
        state = _make_state(hunger=3)
        event = Event('starve', 'desc', {'HUNGER': -10})
        apply_event(state, event, stat_gate=False)
        assert state['stats']['HUNGER'] == 0

    def test_stat_clamps_to_hundred(self):
        """HUNGER=98, +5 → 100 (not 103)."""
        state = _make_state(hunger=98)
        event = Event('feast', 'desc', {'HUNGER': 5})
        apply_event(state, event, stat_gate=False)
        assert state['stats']['HUNGER'] == 100

    def test_negative_clamp_does_not_underflow(self):
        """CHAOS=0, negative event with chaos_bump → CHAOS bumps to 3 (not negative)."""
        state = _make_state(chaos=0, happy=50)
        event = Event('spook', 'desc', {'HAPPY': -5})
        apply_event(state, event, chaos_bump=True)
        # CHAOS bumps +3 from 0 → 3 (the bump itself is a positive effect on CHAOS)
        assert state['stats']['CHAOS'] == 3


class TestApplyEventReturn:
    """apply_event returns a dict with the three documented keys."""

    def test_returns_dict_with_required_keys(self):
        """Result must be a dict containing message, item_dropped, xp_gained."""
        state = _make_state()
        event = Event('mood_boost', 'desc', {'HAPPY': 5})
        result = apply_event(state, event)
        assert isinstance(result, dict)
        assert set(result.keys()) == {'message', 'item_dropped', 'xp_gained'}

    def test_default_return_values(self):
        """Plain event with no metadata → message=None, item_dropped=None, xp_gained=0."""
        state = _make_state()
        event = Event('mood_boost', 'desc', {'HAPPY': 5})
        result = apply_event(state, event)
        assert result['message'] is None
        assert result['item_dropped'] is None
        assert result['xp_gained'] == 0

    def test_does_not_mutate_event(self):
        """apply_event must not mutate the Event object (it's frozen anyway)."""
        state = _make_state()
        event = Event('mood_boost', 'desc', {'HAPPY': 5}, metadata={'xp': 3})
        original_effects = dict(event.effects)
        original_metadata = dict(event.metadata)
        apply_event(state, event)
        assert event.effects == original_effects
        assert event.metadata == original_metadata


# ---------------------------------------------------------------------------
# serialize_event / deserialize_event (Task 3)
# ---------------------------------------------------------------------------
# Tests below are written BEFORE serialize_event()/deserialize_event() exist.
# Per strict TDD they must FAIL first (ImportError on import), then PASS once
# the functions are implemented in src/ascii_pet/events.py.

import json  # noqa: E402

from ascii_pet.events import serialize_event, deserialize_event  # noqa: E402


class TestSerializeEvent:
    """serialize_event returns a JSON-serializable dict with all Event fields."""

    def test_returns_dict(self):
        """serialize_event must return a dict, not an Event or other type."""
        event = Event('mood_boost', 'desc', {'HAPPY': 5})
        result = serialize_event(event)
        assert isinstance(result, dict)

    def test_has_all_six_keys(self):
        """Result must contain all 6 Event fields: event_id, description,
        effects, target, category, metadata."""
        event = Event('mood_boost', 'desc', {'HAPPY': 5},
                      target='both', category='interaction', metadata={'xp': 3})
        result = serialize_event(event)
        assert set(result.keys()) == {
            'event_id', 'description', 'effects', 'target', 'category', 'metadata'
        }

    def test_result_is_json_serializable(self):
        """json.dumps on the result must not raise."""
        event = Event('mood_boost', 'desc', {'HAPPY': 5},
                      metadata={'item_drop': True, 'xp': 3})
        result = serialize_event(event)
        # Must not raise
        serialized = json.dumps(result)
        # And must round-trip through json.loads back to an equivalent dict
        assert json.loads(serialized) == result

    def test_effects_keys_preserved_as_uppercase(self):
        """serialize_event must preserve the uppercase effects keys."""
        event = Event('mood_boost', 'desc', {'happy': 5, 'HUNGER': 3})
        result = serialize_event(event)
        # Event.__post_init__ uppercases keys; serialize must preserve them.
        assert result['effects'] == {'HAPPY': 5, 'HUNGER': 3}

    def test_metadata_preserved(self):
        """metadata dict must be preserved verbatim in the serialized output."""
        meta = {'item_drop': True, 'xp': 3}
        event = Event('find', 'desc', {}, metadata=meta)
        result = serialize_event(event)
        assert result['metadata'] == meta

    def test_all_fields_preserved(self):
        """Every field must be carried over with the correct value."""
        event = Event('play_together', 'Play together!', {'HAPPY': 5, 'ENERGY': -5},
                      target='both', category='interaction', metadata={'xp': 2})
        result = serialize_event(event)
        assert result['event_id'] == 'play_together'
        assert result['description'] == 'Play together!'
        assert result['effects'] == {'HAPPY': 5, 'ENERGY': -5}
        assert result['target'] == 'both'
        assert result['category'] == 'interaction'
        assert result['metadata'] == {'xp': 2}

    def test_empty_effects_and_metadata_serializable(self):
        """Empty effects and metadata must serialize cleanly."""
        event = Event('noop', 'desc', {})
        result = serialize_event(event)
        assert result['effects'] == {}
        assert result['metadata'] == {}
        # JSON round-trip must work
        json.loads(json.dumps(result))


class TestDeserializeEvent:
    """deserialize_event rebuilds an Event from a dict."""

    def test_returns_event_instance(self):
        """deserialize_event must return an Event instance."""
        data = {
            'event_id': 'mood_boost',
            'description': 'desc',
            'effects': {'HAPPY': 5},
            'target': 'self',
            'category': 'solo',
            'metadata': {},
        }
        result = deserialize_event(data)
        assert isinstance(result, Event)

    def test_round_trip_equals_original_all_fields(self):
        """deserialize_event(serialize_event(e)) must equal e field-by-field."""
        original = Event('play_together', 'Play together!',
                         {'HAPPY': 5, 'ENERGY': -5},
                         target='both', category='interaction',
                         metadata={'xp': 2, 'item_drop': True})
        restored = deserialize_event(serialize_event(original))
        assert restored.event_id == original.event_id
        assert restored.description == original.description
        assert restored.effects == original.effects
        assert restored.target == original.target
        assert restored.category == original.category
        assert restored.metadata == original.metadata

    def test_round_trip_dataclass_equality(self):
        """Frozen dataclass equality must hold after a round-trip."""
        original = Event('find', 'desc', {'HAPPY': 5}, metadata={'xp': 3})
        restored = deserialize_event(serialize_event(original))
        # Frozen dataclasses compare by field values
        assert restored == original

    def test_handles_empty_effects(self):
        """An Event with empty effects must round-trip cleanly."""
        original = Event('noop', 'desc', {})
        restored = deserialize_event(serialize_event(original))
        assert restored.effects == {}
        assert restored == original

    def test_handles_empty_metadata(self):
        """An Event with empty metadata must round-trip cleanly."""
        original = Event('noop', 'desc', {'HAPPY': 5})
        restored = deserialize_event(serialize_event(original))
        assert restored.metadata == {}
        assert restored == original

    def test_handles_nested_metadata_item_drop(self):
        """metadata={'item_drop': True} must round-trip with the bool preserved."""
        original = Event('find_item', 'desc', {}, metadata={'item_drop': True})
        restored = deserialize_event(serialize_event(original))
        assert restored.metadata == {'item_drop': True}
        # Bool must remain a bool, not become 1
        assert restored.metadata['item_drop'] is True
        assert restored == original

    def test_handles_nested_metadata_xp(self):
        """metadata={'xp': 3} must round-trip with the int preserved."""
        original = Event('learn', 'desc', {}, metadata={'xp': 3})
        restored = deserialize_event(serialize_event(original))
        assert restored.metadata == {'xp': 3}
        assert isinstance(restored.metadata['xp'], int)
        assert restored == original

    def test_deserialize_uppercases_effects_keys(self):
        """deserialize_event must produce an Event that uppercases effect keys,
        matching Event's __post_init__ behavior."""
        data = {
            'event_id': 'mood_boost',
            'description': 'desc',
            'effects': {'happy': 5},  # lowercase, as if from external source
            'target': 'self',
            'category': 'solo',
            'metadata': {},
        }
        result = deserialize_event(data)
        # Event constructor uppercases keys
        assert result.effects == {'HAPPY': 5}


class TestSerializeRoundTrip:
    """Round-trip tests covering complex events, defaults, and JSON transit."""

    def test_complex_event_round_trips(self):
        """An Event with all fields populated must round-trip correctly."""
        original = Event(
            'group_find',
            'A group adventure!',
            {'HAPPY': 5, 'HUNGER': -3, 'ENERGY': -5, 'WISDOM': 1, 'CHAOS': 0},
            target='both',
            category='interaction',
            metadata={'item_drop': True, 'xp': 4},
        )
        restored = deserialize_event(serialize_event(original))
        assert restored == original
        # Spot-check a few fields explicitly
        assert restored.target == 'both'
        assert restored.category == 'interaction'
        assert restored.effects['HAPPY'] == 5
        assert restored.effects['CHAOS'] == 0
        assert restored.metadata['item_drop'] is True
        assert restored.metadata['xp'] == 4

    def test_default_event_round_trips(self):
        """An Event using all defaults (target='self', category='solo',
        metadata={}) must round-trip correctly."""
        original = Event('mood_boost', 'desc', {'HAPPY': 5})
        restored = deserialize_event(serialize_event(original))
        assert restored == original
        assert restored.target == 'self'
        assert restored.category == 'solo'
        assert restored.metadata == {}

    def test_round_trip_through_json_dumps_loads(self):
        """The serialized dict must survive json.dumps + json.loads and still
        deserialize to an equal Event (simulates LAN transit)."""
        original = Event('play_together', 'Play together!',
                         {'HAPPY': 5, 'ENERGY': -5},
                         target='both', category='interaction',
                         metadata={'xp': 2, 'item_drop': True})
        serialized = serialize_event(original)
        # Simulate network transit: dumps → loads
        wire = json.loads(json.dumps(serialized))
        restored = deserialize_event(wire)
        assert restored == original
        # Bool preserved through JSON (json turns True → true → True)
        assert restored.metadata['item_drop'] is True
        assert restored.metadata['xp'] == 2

    def test_round_trip_preserves_negative_effects(self):
        """Negative effect values must survive the round-trip unchanged."""
        original = Event('spook', 'desc', {'HAPPY': -5, 'ENERGY': -10})
        restored = deserialize_event(serialize_event(original))
        assert restored.effects == {'HAPPY': -5, 'ENERGY': -10}
        assert restored == original

    def test_round_trip_preserves_all_target_values(self):
        """Each legal target value must round-trip."""
        for target in ('self', 'both', 'other'):
            original = Event('e', 'd', {'HAPPY': 1}, target=target)
            restored = deserialize_event(serialize_event(original))
            assert restored.target == target
            assert restored == original

    def test_round_trip_preserves_all_category_values(self):
        """Each legal category value must round-trip."""
        for category in ('solo', 'interaction', 'visit', 'weather'):
            original = Event('e', 'd', {'HAPPY': 1}, category=category)
            restored = deserialize_event(serialize_event(original))
            assert restored.category == category
            assert restored == original


# ---------------------------------------------------------------------------
# Task 4: Migration of RANDOM_EVENTS / PET_INTERACTIONS / VISIT_EVENTS
# ---------------------------------------------------------------------------
# These tests verify that the existing event constants in core.py and
# protocol.py have been migrated to source from the unified REGISTRY in
# events.py. Per strict TDD they must FAIL first (events are still tuples
# / dicts), then PASS once the migration is implemented.

from ascii_pet.core import RANDOM_EVENTS, PET_INTERACTIONS  # noqa: E402
from ascii_pet.protocol import VISIT_EVENTS  # noqa: E402


class TestRandomEventsMigration:
    """RANDOM_EVENTS (core.py) must be a list of Event objects sourced from REGISTRY."""

    def test_each_element_is_event(self):
        """Every entry in RANDOM_EVENTS must be an Event instance."""
        for evt in RANDOM_EVENTS:
            assert isinstance(evt, Event), f"RANDOM_EVENTS entry is not Event: {evt!r}"

    def test_all_have_category_solo(self):
        """Every random event must have category=='solo'."""
        for evt in RANDOM_EVENTS:
            assert evt.category == 'solo', (
                f"event {evt.event_id!r} category={evt.category!r}, expected 'solo'"
            )

    def test_all_have_target_self(self):
        """Solo random events target only the current pet."""
        for evt in RANDOM_EVENTS:
            assert evt.target == 'self'

    def test_event_ids_match_original_ids(self):
        """event_id must match the original tuple[0] for each event."""
        original_ids = {
            'sneeze', 'find_item', 'mood_boost', 'sparkle', 'yawn',
            'find_coin', 'dance', 'nap', 'sing', 'tripped',
            'found_food', 'stomach_ache', 'nightmare', 'boredom',
        }
        actual_ids = {evt.event_id for evt in RANDOM_EVENTS}
        assert original_ids.issubset(actual_ids), (
            f"missing event ids: {original_ids - actual_ids}"
        )

    def test_all_fourteen_events_present(self):
        """All 14 original random events must be present."""
        assert len(RANDOM_EVENTS) == 14, (
            f"expected 14 random events, got {len(RANDOM_EVENTS)}"
        )

    def test_find_item_has_item_drop_metadata(self):
        """find_item event must carry metadata={'item_drop': True}."""
        evt = next((e for e in RANDOM_EVENTS if e.event_id == 'find_item'), None)
        assert evt is not None, "find_item event missing"
        assert evt.metadata.get('item_drop') is True, (
            f"find_item metadata={evt.metadata!r}, expected item_drop=True"
        )

    def test_find_coin_has_xp_metadata(self):
        """find_coin event must carry metadata={'xp': 3}."""
        evt = next((e for e in RANDOM_EVENTS if e.event_id == 'find_coin'), None)
        assert evt is not None, "find_coin event missing"
        assert evt.metadata.get('xp') == 3, (
            f"find_coin metadata={evt.metadata!r}, expected xp=3"
        )

    def test_mood_boost_effects(self):
        """mood_boost must have effects={'HAPPY': 5}."""
        evt = next((e for e in RANDOM_EVENTS if e.event_id == 'mood_boost'), None)
        assert evt is not None, "mood_boost event missing"
        assert evt.effects == {'HAPPY': 5}, (
            f"mood_boost effects={evt.effects!r}, expected {{'HAPPY': 5}}"
        )

    def test_sneeze_has_empty_effects(self):
        """sneeze has no stat effects."""
        evt = next((e for e in RANDOM_EVENTS if e.event_id == 'sneeze'), None)
        assert evt is not None
        assert evt.effects == {}

    def test_no_special_keys_in_effects(self):
        """Effects must NOT contain 'xp' or 'item' keys (those moved to metadata)."""
        for evt in RANDOM_EVENTS:
            assert 'xp' not in evt.effects, (
                f"event {evt.event_id!r} has 'xp' in effects (should be in metadata)"
            )
            assert 'item' not in evt.effects, (
                f"event {evt.event_id!r} has 'item' in effects (should be in metadata)"
            )


class TestPetInteractionsMigration:
    """PET_INTERACTIONS (core.py) must be a list of Event objects sourced from REGISTRY."""

    def test_each_element_is_event(self):
        """Every entry in PET_INTERACTIONS must be an Event instance."""
        for evt in PET_INTERACTIONS:
            assert isinstance(evt, Event), f"PET_INTERACTIONS entry is not Event: {evt!r}"

    def test_all_have_category_interaction(self):
        """Every interaction must have category=='interaction'."""
        for evt in PET_INTERACTIONS:
            assert evt.category == 'interaction', (
                f"event {evt.event_id!r} category={evt.category!r}, expected 'interaction'"
            )

    def test_target_is_both_or_self(self):
        """target must be 'both' or 'self' (NOT 'current')."""
        for evt in PET_INTERACTIONS:
            assert evt.target in ('both', 'self'), (
                f"event {evt.event_id!r} target={evt.target!r}, expected 'both' or 'self'"
            )

    def test_all_four_interactions_present(self):
        """All 4 original interactions must be present."""
        assert len(PET_INTERACTIONS) == 4, (
            f"expected 4 interactions, got {len(PET_INTERACTIONS)}"
        )

    def test_play_together_target_both(self):
        """play_together must have target='both'."""
        evt = next((e for e in PET_INTERACTIONS if e.event_id == 'play_together'), None)
        assert evt is not None, "play_together interaction missing"
        assert evt.target == 'both', (
            f"play_together target={evt.target!r}, expected 'both'"
        )

    def test_share_food_target_self(self):
        """share_food must have target='self' (migrated from 'current')."""
        evt = next((e for e in PET_INTERACTIONS if e.event_id == 'share_food'), None)
        assert evt is not None, "share_food interaction missing"
        assert evt.target == 'self', (
            f"share_food target={evt.target!r}, expected 'self'"
        )

    def test_chat_target_both(self):
        """chat must have target='both'."""
        evt = next((e for e in PET_INTERACTIONS if e.event_id == 'chat'), None)
        assert evt is not None
        assert evt.target == 'both'

    def test_race_target_self(self):
        """race must have target='self' (migrated from 'current')."""
        evt = next((e for e in PET_INTERACTIONS if e.event_id == 'race'), None)
        assert evt is not None
        assert evt.target == 'self'

    def test_play_together_effects(self):
        """play_together must have effects={'HAPPY': 5}."""
        evt = next((e for e in PET_INTERACTIONS if e.event_id == 'play_together'), None)
        assert evt is not None
        assert evt.effects == {'HAPPY': 5}


class TestVisitEventsMigration:
    """VISIT_EVENTS (protocol.py) must be a list of Event objects sourced from REGISTRY."""

    def test_each_element_is_event(self):
        """Every entry in VISIT_EVENTS must be an Event instance."""
        for evt in VISIT_EVENTS:
            assert isinstance(evt, Event), f"VISIT_EVENTS entry is not Event: {evt!r}"

    def test_all_have_category_visit(self):
        """Every visit event must have category=='visit'."""
        for evt in VISIT_EVENTS:
            assert evt.category == 'visit', (
                f"event {evt.event_id!r} category={evt.category!r}, expected 'visit'"
            )

    def test_all_have_target_self(self):
        """Visit events target the local pet."""
        for evt in VISIT_EVENTS:
            assert evt.target == 'self'

    def test_effects_keys_are_uppercase(self):
        """All effects keys must be UPPERCASE stat names."""
        for evt in VISIT_EVENTS:
            for key in evt.effects:
                assert key == key.upper(), (
                    f"event {evt.event_id!r} has lowercase effects key {key!r}"
                )
                assert key in ('HUNGER', 'HAPPY', 'ENERGY', 'WISDOM', 'CHAOS'), (
                    f"event {evt.event_id!r} has unknown stat key {key!r}"
                )

    def test_all_five_visit_events_present(self):
        """All 5 original visit events must be present."""
        assert len(VISIT_EVENTS) == 5, (
            f"expected 5 visit events, got {len(VISIT_EVENTS)}"
        )

    def test_play_together_visit_event_id_prefixed(self):
        """The visit play_together event must have event_id='visit_play_together'."""
        evt = next((e for e in VISIT_EVENTS if e.event_id == 'visit_play_together'), None)
        assert evt is not None, "visit_play_together event missing"

    def test_play_together_preserves_original_event_type(self):
        """visit_play_together must carry metadata['original_event_type']='play_together'."""
        evt = next((e for e in VISIT_EVENTS if e.event_id == 'visit_play_together'), None)
        assert evt is not None
        assert evt.metadata.get('original_event_type') == 'play_together', (
            f"metadata={evt.metadata!r}, expected original_event_type='play_together'"
        )

    def test_all_visit_event_ids_prefixed(self):
        """All visit event_ids that collide with interaction ids must be prefixed."""
        # The 4 colliding ids: play_together, share_food, chat, race
        # nap_together does not collide so it stays as-is.
        interaction_ids = {e.event_id for e in PET_INTERACTIONS}
        for evt in VISIT_EVENTS:
            if evt.metadata.get('original_event_type') in interaction_ids:
                assert evt.event_id.startswith('visit_'), (
                    f"event {evt.event_id!r} should be prefixed with 'visit_'"
                )

    def test_nap_together_not_prefixed(self):
        """nap_together does not collide, so its event_id stays 'nap_together'."""
        evt = next((e for e in VISIT_EVENTS if e.event_id == 'nap_together'), None)
        assert evt is not None, "nap_together visit event missing"


class TestRegistryPopulation:
    """REGISTRY must be populated with all builtin events at import time."""

    def test_solo_category_has_14_events(self):
        """REGISTRY.by_category('solo') must return 14 events."""
        assert len(REGISTRY.by_category('solo')) == 14

    def test_interaction_category_has_4_events(self):
        """REGISTRY.by_category('interaction') must return 4 events."""
        assert len(REGISTRY.by_category('interaction')) == 4

    def test_visit_category_has_5_events(self):
        """REGISTRY.by_category('visit') must return 5 events."""
        assert len(REGISTRY.by_category('visit')) == 5

    def test_get_mood_boost_returns_solo_event(self):
        """REGISTRY.get('mood_boost') must return the solo event."""
        evt = REGISTRY.get('mood_boost')
        assert evt is not None
        assert evt.category == 'solo'
        assert evt.effects == {'HAPPY': 5}

    def test_get_visit_play_together_returns_visit_event(self):
        """REGISTRY.get('visit_play_together') must return the visit event."""
        evt = REGISTRY.get('visit_play_together')
        assert evt is not None
        assert evt.category == 'visit'
        assert evt.metadata.get('original_event_type') == 'play_together'

    def test_get_play_together_returns_interaction_event(self):
        """REGISTRY.get('play_together') must return the interaction event."""
        evt = REGISTRY.get('play_together')
        assert evt is not None
        assert evt.category == 'interaction'
        assert evt.target == 'both'

    def test_total_event_count(self):
        """Total events in REGISTRY must be 14 + 4 + 5 = 23."""
        assert len(REGISTRY.all()) == 23
