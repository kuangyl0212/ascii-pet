#!/usr/bin/env python3
"""TDD RED phase: Tests for numerical balance optimization.

These tests verify the EXPECTED (new) values after balance optimization.
All tests should FAIL until pet_core.py is updated (TDD RED phase).

Coverage:
    1. Random event trigger frequency reduced (2% probability, 60s cooldown)
    2. Healing event values halved
    3. New negative events added (stomach_ache, nightmare, boredom)
    4. Stat-gate blocks positive healing when stat >= 80
    5. New decay rates in tick()
    6. Decay rates in update_state_over_time() consistent with tick()

Run: python test_balance.py
"""

import unittest
import inspect
import os
import sys
import tempfile
import time
import shutil
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

# Add the project directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pet_core
from pet_core import PetGame, RANDOM_EVENTS


def _find_event(name):
    """Find an event in RANDOM_EVENTS by name. Returns the event tuple or None."""
    for evt in RANDOM_EVENTS:
        if evt[0] == name:
            return evt
    return None


def _source_compact(func):
    """Get source code of a function with all whitespace removed.

    This allows assertions to be formatting-agnostic (spaces, newlines, etc).
    """
    return ''.join(inspect.getsource(func).split())


# ─── Test 1: Random event trigger frequency ──────────────────────────────────


class TestRandomEventFrequency(unittest.TestCase):
    """Verify tick() uses reduced event frequency (2% prob, 60s cooldown)."""

    def test_event_probability_is_2_percent(self):
        """tick() should use 2% (0.02) base event probability with CHAOS scaling."""
        source = _source_compact(PetGame.tick)
        self.assertIn(
            '0.02*(1+chaos/100)', source,
            "tick() should use CHAOS-based probability formula 0.02*(1+chaos/100)",
        )
        self.assertNotIn(
            'random()<0.05', source,
            "tick() should not contain old 0.05 (5%) probability",
        )

    def test_event_cooldown_is_60_seconds(self):
        """tick() should use 60s cooldown, not 30s."""
        source = _source_compact(PetGame.tick)
        self.assertIn(
            'last_event_time>60', source,
            "tick() should use 60s cooldown (last_event_time > 60)",
        )
        self.assertNotIn(
            'last_event_time>30', source,
            "tick() should not contain old 30s cooldown (last_event_time > 30)",
        )


# ─── Test 2: Healing event values halved ─────────────────────────────────────


class TestHealingEventValuesHalved(unittest.TestCase):
    """Verify healing event values are halved in RANDOM_EVENTS."""

    def test_mood_boost_happy_is_5(self):
        """mood_boost HAPPY should be 5 (was 10)."""
        evt = _find_event('mood_boost')
        self.assertIsNotNone(evt, "mood_boost event should exist")
        self.assertEqual(
            evt[2].get('HAPPY'), 5,
            f"mood_boost HAPPY should be 5, got {evt[2].get('HAPPY')}",
        )

    def test_found_food_hunger_is_5(self):
        """found_food HUNGER should be 5 (was 10)."""
        evt = _find_event('found_food')
        self.assertIsNotNone(evt, "found_food event should exist")
        self.assertEqual(
            evt[2].get('HUNGER'), 5,
            f"found_food HUNGER should be 5, got {evt[2].get('HUNGER')}",
        )

    def test_nap_energy_is_5(self):
        """nap ENERGY should be 5 (was 10)."""
        evt = _find_event('nap')
        self.assertIsNotNone(evt, "nap event should exist")
        self.assertEqual(
            evt[2].get('ENERGY'), 5,
            f"nap ENERGY should be 5, got {evt[2].get('ENERGY')}",
        )

    def test_dance_happy_is_3(self):
        """dance HAPPY should be 3 (was 5)."""
        evt = _find_event('dance')
        self.assertIsNotNone(evt, "dance event should exist")
        self.assertEqual(
            evt[2].get('HAPPY'), 3,
            f"dance HAPPY should be 3, got {evt[2].get('HAPPY')}",
        )

    def test_sing_wisdom_is_3(self):
        """sing WISDOM should be 3 (was 5)."""
        evt = _find_event('sing')
        self.assertIsNotNone(evt, "sing event should exist")
        self.assertEqual(
            evt[2].get('WISDOM'), 3,
            f"sing WISDOM should be 3, got {evt[2].get('WISDOM')}",
        )

    def test_find_coin_xp_is_3(self):
        """find_coin xp should be 3 (was 5)."""
        evt = _find_event('find_coin')
        self.assertIsNotNone(evt, "find_coin event should exist")
        self.assertEqual(
            evt[2].get('xp'), 3,
            f"find_coin xp should be 3, got {evt[2].get('xp')}",
        )


# ─── Test 3: New negative events added ───────────────────────────────────────


class TestNewNegativeEvents(unittest.TestCase):
    """Verify new negative events are added to RANDOM_EVENTS."""

    def test_stomach_ache_event_exists(self):
        """stomach_ache event with HUNGER: -5 should exist."""
        evt = _find_event('stomach_ache')
        self.assertIsNotNone(evt, "stomach_ache event should exist in RANDOM_EVENTS")
        self.assertEqual(
            evt[2].get('HUNGER'), -5,
            f"stomach_ache should have HUNGER: -5, got {evt[2].get('HUNGER')}",
        )

    def test_nightmare_event_exists(self):
        """nightmare event with ENERGY: -5 should exist."""
        evt = _find_event('nightmare')
        self.assertIsNotNone(evt, "nightmare event should exist in RANDOM_EVENTS")
        self.assertEqual(
            evt[2].get('ENERGY'), -5,
            f"nightmare should have ENERGY: -5, got {evt[2].get('ENERGY')}",
        )

    def test_boredom_event_exists(self):
        """boredom event with HAPPY: -5 should exist."""
        evt = _find_event('boredom')
        self.assertIsNotNone(evt, "boredom event should exist in RANDOM_EVENTS")
        self.assertEqual(
            evt[2].get('HAPPY'), -5,
            f"boredom should have HAPPY: -5, got {evt[2].get('HAPPY')}",
        )


# ─── Test 4: Stat-gate blocks positive healing when stat >= 80 ───────────────


class TestStatGate(unittest.TestCase):
    """Verify stat-gate blocks positive healing events when stat >= 80."""

    def setUp(self):
        """Create a PetGame instance with isolated storage."""
        # PetGame expects data_dir to be a Path object (calls .mkdir() on it)
        self.tmpdir = Path(tempfile.mkdtemp())
        # Unique uid per test run to avoid loading existing state
        self.uid = f'test-balance-{int(time.time() * 1000000)}'
        self.game = PetGame(self.uid, data_dir=self.tmpdir)
        # Set HUNGER to 95 (above the 80 threshold)
        self.game.state['stats']['HUNGER'] = 95
        # Reset last_event_time to 0 to bypass event cooldown
        self.game.last_event_time = 0
        # Reset last_tick_time to current time to avoid huge delta_hours
        self.game.last_tick_time = time.time()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_positive_event_blocked_when_stat_above_80(self):
        """When HUNGER >= 80, found_food event should not increase HUNGER."""
        found_food_evt = _find_event('found_food')
        self.assertIsNotNone(found_food_evt, "found_food event must exist")

        initial_hunger = self.game.state['stats']['HUNGER']
        self.assertEqual(initial_hunger, 95)

        # Mock random to force-trigger the found_food event:
        #   - random.random() returns 0.001 (< 0.02 new probability, < 0.05 old)
        #   - random.choice() returns the found_food event tuple
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=found_food_evt):
            self.game.tick()

        # Verify the event was actually triggered (last_event_time updated from 0)
        self.assertGreater(
            self.game.last_event_time, 0,
            "Event should have been triggered (last_event_time should be updated)",
        )

        # HUNGER should remain 95 because stat-gate blocks positive events
        # when stat >= 80. Without stat-gate, HUNGER would become 100 (capped).
        self.assertEqual(
            self.game.state['stats']['HUNGER'], 95,
            f"HUNGER should remain 95 (stat-gate blocked positive event at >= 80), "
            f"got {self.game.state['stats']['HUNGER']}",
        )


# ─── Test 5: New decay rates in tick() ───────────────────────────────────────


class TestDecayRatesInTick(unittest.TestCase):
    """Verify tick() uses new decay rates in decay_config."""

    def test_hunger_decay_threshold_3h_rate_8(self):
        """HUNGER decay: threshold 3h, rate 8 (was 4h, rate 5)."""
        source = _source_compact(PetGame.tick)
        self.assertIn(
            "'last_fed',3,8", source,
            "tick() decay_config should have HUNGER: threshold=3h, rate=8 "
            "(expected ('last_fed', 3, 8, 'HUNGER'))",
        )

    def test_happy_decay_threshold_1_5h_rate_5(self):
        """HAPPY decay: threshold 1.5h, rate 5 (was 2h, rate 3)."""
        source = _source_compact(PetGame.tick)
        self.assertIn(
            "'last_played',1.5,5", source,
            "tick() decay_config should have HAPPY: threshold=1.5h, rate=5 "
            "(expected ('last_played', 1.5, 5, 'HAPPY'))",
        )

    def test_energy_decay_threshold_4h_rate_6(self):
        """ENERGY decay: threshold 4h, rate 6 (was 6h, rate 4)."""
        source = _source_compact(PetGame.tick)
        self.assertIn(
            "'last_slept',4,6", source,
            "tick() decay_config should have ENERGY: threshold=4h, rate=6 "
            "(expected ('last_slept', 4, 6, 'ENERGY'))",
        )


# ─── Test 6: Decay rates in update_state_over_time() ─────────────────────────


class TestDecayRatesInUpdateStateOverTime(unittest.TestCase):
    """Verify update_state_over_time() decay config matches new rates in tick()."""

    def test_decay_config_matches_new_rates(self):
        """update_state_over_time() should use new decay rates consistent with tick()."""
        source = _source_compact(pet_core.update_state_over_time)
        # HUNGER: threshold 3h, rate 8
        self.assertIn(
            "('last_fed',3,8)", source,
            "update_state_over_time() should have HUNGER: threshold=3h, rate=8 "
            "(expected ('last_fed', 3, 8))",
        )
        # HAPPY: threshold 1.5h, rate 5
        self.assertIn(
            "('last_played',1.5,5)", source,
            "update_state_over_time() should have HAPPY: threshold=1.5h, rate=5 "
            "(expected ('last_played', 1.5, 5))",
        )
        # ENERGY: threshold 4h, rate 6
        self.assertIn(
            "('last_slept',4,6)", source,
            "update_state_over_time() should have ENERGY: threshold=4h, rate=6 "
            "(expected ('last_slept', 4, 6))",
        )


# ─── Test 7: CHAOS stat affects event probability ────────────────────────────


class TestChaosAffectsEventProbability(unittest.TestCase):
    """Verify CHAOS stat affects random event trigger probability."""

    def test_chaos_0_probability_is_2_percent(self):
        """tick() should use CHAOS-based formula: 0.02*(1+chaos/100)."""
        source = _source_compact(PetGame.tick)
        self.assertIn(
            '0.02*(1+chaos/100)', source,
            "tick() should use CHAOS-based probability formula 0.02*(1+chaos/100)",
        )
        self.assertIn(
            'CHAOS', source,
            "tick() event probability should reference CHAOS stat",
        )
        self.assertNotIn(
            'random()<0.02', source,
            "tick() should not use old fixed 0.02 probability (should be CHAOS-based)",
        )

    def test_chaos_50_probability_is_3_percent(self):
        """CHAOS=50 should give 3% event probability (0.02*(1+50/100)=0.03)."""
        tmpdir = Path(tempfile.mkdtemp())
        uid = f'test-chaos-50-{int(time.time() * 1000000)}'
        game = PetGame(uid, data_dir=tmpdir)
        game.state['stats']['CHAOS'] = 50
        game.last_event_time = 0
        game.last_tick_time = time.time()
        neutral_evt = ('test', 'test', {})
        try:
            # random.random()=0.025 is > 2% but < 3%, so should trigger with CHAOS=50
            with patch('random.random', return_value=0.025), \
                    patch('random.choice', return_value=neutral_evt):
                game.tick()
            self.assertGreater(
                game.last_event_time, 0,
                "Event should trigger with CHAOS=50 and random=0.025 (3% probability)",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_chaos_0_probability_blocks_025(self):
        """CHAOS=0 should give exactly 2% probability, blocking random=0.025."""
        tmpdir = Path(tempfile.mkdtemp())
        uid = f'test-chaos-0-block-{int(time.time() * 1000000)}'
        game = PetGame(uid, data_dir=tmpdir)
        game.state['stats']['CHAOS'] = 0
        game.last_event_time = 0
        game.last_tick_time = time.time()
        try:
            # random.random()=0.025 is > 2%, so should NOT trigger with CHAOS=0
            with patch('random.random', return_value=0.025):
                game.tick()
            self.assertEqual(
                game.last_event_time, 0,
                "Event should NOT trigger with CHAOS=0 and random=0.025 (2% probability)",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_chaos_100_probability_is_4_percent(self):
        """CHAOS=100 should give 4% probability; CHAOS=0 should not at same random."""
        tmpdir = Path(tempfile.mkdtemp())
        uid = f'test-chaos-100-{int(time.time() * 1000000)}'
        neutral_evt = ('test', 'test', {})
        try:
            # CHAOS=100: 0.02*(1+100/100)=0.04, random=0.035 is < 4% → triggers
            game = PetGame(uid, data_dir=tmpdir)
            game.state['stats']['CHAOS'] = 100
            game.last_event_time = 0
            game.last_tick_time = time.time()
            with patch('random.random', return_value=0.035), \
                    patch('random.choice', return_value=neutral_evt):
                game.tick()
            self.assertGreater(
                game.last_event_time, 0,
                "Event should trigger with CHAOS=100 and random=0.035 (4% probability)",
            )

            # CHAOS=0: 0.02*(1+0/100)=0.02, random=0.035 is > 2% → does NOT trigger
            game.state['stats']['CHAOS'] = 0
            game.last_event_time = 0
            with patch('random.random', return_value=0.035):
                game.tick()
            self.assertEqual(
                game.last_event_time, 0,
                "Event should NOT trigger with CHAOS=0 and random=0.035 (2% probability)",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ─── Test 8: Negative events increase CHAOS ──────────────────────────────────


class TestNegativeEventsIncreaseChaos(unittest.TestCase):
    """Verify negative events increase CHAOS stat."""

    def setUp(self):
        """Create a PetGame instance with isolated storage."""
        self.tmpdir = Path(tempfile.mkdtemp())
        self.uid = f'test-chaos-neg-{int(time.time() * 1000000)}'
        self.game = PetGame(self.uid, data_dir=self.tmpdir)
        self.game.state['stats']['CHAOS'] = 50
        self.game.last_event_time = 0
        self.game.last_tick_time = time.time()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_stomach_ache_increases_chaos(self):
        """stomach_ache event should increase CHAOS by 3."""
        evt = _find_event('stomach_ache')
        self.assertIsNotNone(evt, "stomach_ache event must exist")
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=evt):
            self.game.tick()
        self.assertEqual(
            self.game.state['stats']['CHAOS'], 53,
            f"stomach_ache should increase CHAOS from 50 to 53, "
            f"got {self.game.state['stats']['CHAOS']}",
        )

    def test_nightmare_increases_chaos(self):
        """nightmare event should increase CHAOS by 3."""
        evt = _find_event('nightmare')
        self.assertIsNotNone(evt, "nightmare event must exist")
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=evt):
            self.game.tick()
        self.assertEqual(
            self.game.state['stats']['CHAOS'], 53,
            f"nightmare should increase CHAOS from 50 to 53, "
            f"got {self.game.state['stats']['CHAOS']}",
        )

    def test_boredom_increases_chaos(self):
        """boredom event should increase CHAOS by 3."""
        evt = _find_event('boredom')
        self.assertIsNotNone(evt, "boredom event must exist")
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=evt):
            self.game.tick()
        self.assertEqual(
            self.game.state['stats']['CHAOS'], 53,
            f"boredom should increase CHAOS from 50 to 53, "
            f"got {self.game.state['stats']['CHAOS']}",
        )

    def test_tripped_increases_chaos(self):
        """tripped event should increase CHAOS by 3."""
        evt = _find_event('tripped')
        self.assertIsNotNone(evt, "tripped event must exist")
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=evt):
            self.game.tick()
        self.assertEqual(
            self.game.state['stats']['CHAOS'], 53,
            f"tripped should increase CHAOS from 50 to 53, "
            f"got {self.game.state['stats']['CHAOS']}",
        )

    def test_positive_event_does_not_increase_chaos(self):
        """Positive events (e.g. mood_boost) should NOT increase CHAOS."""
        evt = _find_event('mood_boost')
        self.assertIsNotNone(evt, "mood_boost event must exist")
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=evt):
            self.game.tick()
        self.assertEqual(
            self.game.state['stats']['CHAOS'], 50,
            f"mood_boost should NOT increase CHAOS, "
            f"got {self.game.state['stats']['CHAOS']}",
        )

    def test_chaos_capped_at_100(self):
        """CHAOS should be capped at 100 even after negative event."""
        self.game.state['stats']['CHAOS'] = 99
        evt = _find_event('stomach_ache')
        self.assertIsNotNone(evt, "stomach_ache event must exist")
        with patch('random.random', return_value=0.001), \
                patch('random.choice', return_value=evt):
            self.game.tick()
        self.assertEqual(
            self.game.state['stats']['CHAOS'], 100,
            f"CHAOS should be capped at 100 (99+3=102→100), "
            f"got {self.game.state['stats']['CHAOS']}",
        )


# ─── Test 9: Chaos Crystal item ──────────────────────────────────────────────


class TestChaosCrystalItem(unittest.TestCase):
    """Verify Chaos Crystal item exists and works correctly."""

    def test_chaos_crystal_exists_in_items(self):
        """ITEMS should contain 'crystal' with effect {'CHAOS': 15}."""
        self.assertIn('crystal', pet_core.ITEMS, "ITEMS should have a 'crystal' key")
        self.assertEqual(
            pet_core.ITEMS['crystal']['effect'], {'CHAOS': 15},
            f"crystal effect should be {{'CHAOS': 15}}, "
            f"got {pet_core.ITEMS['crystal']['effect']}",
        )

    def test_chaos_crystal_usage(self):
        """Using crystal with CHAOS=30 should increase CHAOS to 45."""
        tmpdir = Path(tempfile.mkdtemp())
        uid = f'test-crystal-{int(time.time() * 1000000)}'
        game = PetGame(uid, data_dir=tmpdir)
        game.state['stats']['CHAOS'] = 30
        game.add_item('crystal')
        try:
            game.use_item('crystal')
            self.assertEqual(
                game.state['stats']['CHAOS'], 45,
                f"CHAOS should be 45 after using crystal (30+15), "
                f"got {game.state['stats']['CHAOS']}",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_chaos_crystal_capped_at_100(self):
        """Using crystal with CHAOS=90 should cap at 100, not 105."""
        tmpdir = Path(tempfile.mkdtemp())
        uid = f'test-crystal-cap-{int(time.time() * 1000000)}'
        game = PetGame(uid, data_dir=tmpdir)
        game.state['stats']['CHAOS'] = 90
        game.add_item('crystal')
        try:
            game.use_item('crystal')
            self.assertEqual(
                game.state['stats']['CHAOS'], 100,
                f"CHAOS should be capped at 100 after using crystal (90+15=105→100), "
                f"got {game.state['stats']['CHAOS']}",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
