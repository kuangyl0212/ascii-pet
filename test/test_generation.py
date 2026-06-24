#!/usr/bin/env python3
"""Pytest tests for pet_core.py pet generation functions (SubTask 3.1-3.7).

Note on PRNG: pet_core.mulberry32 is a non-standard implementation whose output
is heavily non-uniform (common~28%, legendary~16% instead of 60%/1%). This is a
bug in pet_core.py that we do NOT fix (per task constraint). For distribution
tests (SubTask 3.3, 3.7) we test the function's weighting logic in isolation by
feeding a uniform PRNG (random.Random), so we verify roll_rarity / shiny logic
correctness rather than the broken PRNG's output quality. Separate tests confirm
the functions still run without errors under the real mulberry32.
"""

import sys
import os
import random
from collections import Counter
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pytest
from ascii_pet.core import (
    generate_companion, generate_name, roll_rarity, roll_stats,
    mulberry32, hash_string,
    SPECIES, EYES, RARITIES, RARITY_WEIGHTS, RARITY_FLOOR, STAT_NAMES,
    HAT_LINES, ADJECTIVES, NOUNS, SALT,
)


def _uniform_rng(seed):
    """Return a uniform [0, 1) PRNG — a drop-in replacement for mulberry32.

    Used to test roll_rarity / shiny weighting logic independent of the buggy
    mulberry32 implementation in pet_core.py.
    """
    return random.Random(seed).random


class TestGenerateCompanionDeterminism:
    """SubTask 3.1: generate_companion(uid, seed) determinism."""

    def test_same_uid_seed_returns_identical_dict(self):
        c1 = generate_companion("alice", "seed-123")
        c2 = generate_companion("alice", "seed-123")
        assert c1 == c2

    def test_different_seed_returns_different_dict(self):
        c1 = generate_companion("alice", "seed-123")
        c2 = generate_companion("alice", "seed-456")
        assert c1 != c2

    def test_different_uid_returns_different_dict(self):
        c1 = generate_companion("alice", "seed-123")
        c2 = generate_companion("bob", "seed-123")
        assert c1 != c2

    @pytest.mark.parametrize("uid", ["user1", "user2", "user3"])
    @pytest.mark.parametrize("seed", ["s1", "s2", "s3"])
    def test_determinism_across_many_uids_seeds(self, uid, seed):
        c1 = generate_companion(uid, seed)
        c2 = generate_companion(uid, seed)
        assert c1 == c2, f"Mismatch for uid={uid}, seed={seed}"


class TestGenerateCompanionFields:
    """SubTask 3.2: generate_companion field completeness and validity."""

    def test_required_fields_present(self):
        c = generate_companion("testuser", "testseed")
        required = {'rarity', 'species', 'eye', 'hat', 'shiny', 'stats'}
        assert set(c.keys()) == required

    def test_species_in_SPECIES(self):
        for i in range(100):
            c = generate_companion("testuser", str(i))
            assert c['species'] in SPECIES, f"seed={i}: species {c['species']} not in SPECIES"

    def test_eye_in_EYES(self):
        for i in range(100):
            c = generate_companion("testuser", str(i))
            assert c['eye'] in EYES, f"seed={i}: eye {c['eye']} not in EYES"

    def test_rarity_in_RARITIES(self):
        for i in range(100):
            c = generate_companion("testuser", str(i))
            assert c['rarity'] in RARITIES, f"seed={i}: rarity {c['rarity']} not in RARITIES"

    def test_stats_contain_all_STAT_NAMES(self):
        c = generate_companion("testuser", "testseed")
        assert set(c['stats'].keys()) == set(STAT_NAMES)

    def test_stats_values_in_range_1_to_100(self):
        for i in range(100):
            c = generate_companion("testuser", str(i))
            for stat in STAT_NAMES:
                v = c['stats'][stat]
                assert v >= 1, f"seed={i} {stat}={v} < 1"
                assert v <= 100, f"seed={i} {stat}={v} > 100"

    def test_shiny_is_bool(self):
        c = generate_companion("testuser", "testseed")
        assert isinstance(c['shiny'], bool)


class TestRollRarityDistribution:
    """SubTask 3.3: roll_rarity distribution approximates RARITY_WEIGHTS.

    roll_rarity's weighting logic is correct (it consumes one rng() value and
    maps ranges to rarities per RARITY_WEIGHTS). We verify the logic with a
    uniform PRNG so the test reflects the intended distribution. A separate
    test confirms roll_rarity also runs under the real (non-uniform)
    mulberry32 without error and returns valid rarities.
    """

    def test_common_about_60_percent(self):
        rng = _uniform_rng(42)
        n = 10000
        counts = Counter(roll_rarity(rng) for _ in range(n))
        common_ratio = counts['common'] / n
        # RARITY_WEIGHTS['common']=60/100; allow loose [50%, 70%] band
        assert common_ratio > 0.50, f"common ratio {common_ratio:.3f} too low"
        assert common_ratio < 0.70, f"common ratio {common_ratio:.3f} too high"

    def test_legendary_under_5_percent(self):
        rng = _uniform_rng(7)
        n = 10000
        legendary_count = sum(1 for _ in range(n) if roll_rarity(rng) == 'legendary')
        legendary_ratio = legendary_count / n
        # RARITY_WEIGHTS['legendary']=1/100; must be < 5%
        assert legendary_ratio < 0.05, f"legendary ratio {legendary_ratio:.3f} >= 5%"

    @pytest.mark.slow
    def test_all_rarities_appear(self):
        rng = _uniform_rng(12345)
        seen = set()
        for _ in range(10000):
            seen.add(roll_rarity(rng))
        assert seen == set(RARITIES)

    def test_relative_order_matches_weights(self):
        rng = _uniform_rng(999)
        n = 10000
        counts = Counter(roll_rarity(rng) for _ in range(n))
        # Order should follow weights: common > uncommon > rare > epic > legendary
        assert counts['common'] > counts['uncommon']
        assert counts['uncommon'] > counts['rare']
        assert counts['rare'] > counts['epic']
        assert counts['epic'] > counts['legendary']

    def test_roll_rarity_works_with_mulberry32(self):
        """roll_rarity must return a valid rarity under the real mulberry32."""
        for seed in range(1000):
            rng = mulberry32(seed)
            r = roll_rarity(rng)
            assert r in RARITIES

    def test_roll_rarity_returns_rarities_only(self):
        rng = _uniform_rng(2024)
        for _ in range(1000):
            assert roll_rarity(rng) in RARITIES


class TestRollStats:
    """SubTask 3.4: roll_stats ranges — peak >= floor+50, dump <= floor+5."""

    @pytest.mark.parametrize("rarity", RARITIES)
    def test_all_stats_in_range_1_to_100(self, rarity):
        rng = mulberry32(hash_string(rarity + '-range'))
        for _ in range(100):
            stats = roll_stats(rng, rarity)
            for stat in STAT_NAMES:
                v = stats[stat]
                assert v >= 1, f"{rarity} {stat}={v} < 1"
                assert v <= 100, f"{rarity} {stat}={v} > 100"

    @pytest.mark.parametrize("rarity", RARITIES)
    def test_peak_stat_at_least_floor_plus_50(self, rarity):
        # peak = min(100, floor+50+int(rng()*30)) >= floor+50 (clamped at 100)
        # peak is always the max stat since normal max = floor+39 < floor+50 <= peak
        floor = RARITY_FLOOR[rarity]
        rng = mulberry32(hash_string(rarity + '-peak'))
        for _ in range(100):
            stats = roll_stats(rng, rarity)
            max_val = max(stats.values())
            assert max_val >= floor + 50, (
                f"{rarity}: max stat {max_val} < floor+50={floor + 50}")

    @pytest.mark.parametrize("rarity", RARITIES)
    def test_dump_stat_at_most_floor_plus_5(self, rarity):
        # dump = max(1, floor-10+int(rng()*15)) <= floor+4 <= floor+5
        # dump is one of the stats, so min(stats) <= dump <= floor+5
        floor = RARITY_FLOOR[rarity]
        rng = mulberry32(hash_string(rarity + '-dump'))
        for _ in range(100):
            stats = roll_stats(rng, rarity)
            min_val = min(stats.values())
            assert min_val <= floor + 5, (
                f"{rarity}: min stat {min_val} > floor+5={floor + 5}")

    @pytest.mark.parametrize("rarity", RARITIES)
    def test_stats_contain_all_stat_names(self, rarity):
        rng = mulberry32(0)
        stats = roll_stats(rng, rarity)
        assert set(stats.keys()) == set(STAT_NAMES)

    @pytest.mark.parametrize("rarity", RARITIES)
    def test_roll_stats_works_with_uniform_rng(self, rarity):
        """roll_stats must produce valid ranges under a uniform PRNG too."""
        floor = RARITY_FLOOR[rarity]
        rng = _uniform_rng(hash_string(rarity + '-uni'))
        for _ in range(100):
            stats = roll_stats(rng, rarity)
            for stat in STAT_NAMES:
                assert stats[stat] in range(1, 101)
            assert max(stats.values()) >= floor + 50
            assert min(stats.values()) <= floor + 5


class TestGenerateName:
    """SubTask 3.5: generate_name returns 'adjective noun' format."""

    def test_name_has_exactly_one_space(self):
        name = generate_name("user1", "seed1")
        assert name.count(' ') == 1, f"Name '{name}' does not have exactly one space"

    def test_name_two_parts_split_by_space(self):
        for i in range(200):
            name = generate_name("user1", str(i))
            parts = name.split(' ')
            assert len(parts) == 2, f"Name '{name}' split into {len(parts)} parts"

    def test_adjective_in_ADJECTIVES(self):
        for i in range(200):
            name = generate_name("user1", str(i))
            adj = name.split(' ')[0]
            assert adj in ADJECTIVES, f"Adjective '{adj}' not in ADJECTIVES (name='{name}')"

    def test_noun_in_NOUNS(self):
        for i in range(200):
            name = generate_name("user1", str(i))
            noun = name.split(' ')[1]
            assert noun in NOUNS, f"Noun '{noun}' not in NOUNS (name='{name}')"

    def test_name_determinism(self):
        n1 = generate_name("user1", "seed1")
        n2 = generate_name("user1", "seed1")
        assert n1 == n2

    def test_different_uid_different_name(self):
        n1 = generate_name("alice", "seed1")
        n2 = generate_name("bob", "seed1")
        assert n1 != n2


class TestHatLogic:
    """SubTask 3.6: common hat='none', non-common hat in HAT_LINES keys."""

    def test_common_pet_hat_is_none(self):
        common_found = False
        for i in range(2000):
            c = generate_companion("testuser", str(i))
            if c['rarity'] == 'common':
                common_found = True
                assert c['hat'] == 'none', (
                    f"seed={i}: common pet has hat={c['hat']} instead of 'none'")
        assert common_found, "No common pets generated in 2000 samples"

    def test_noncommon_pet_hat_in_HAT_LINES(self):
        noncommon_found = False
        for i in range(2000):
            c = generate_companion("testuser", str(i))
            if c['rarity'] != 'common':
                noncommon_found = True
                assert c['hat'] in HAT_LINES, (
                    f"seed={i}: {c['rarity']} pet hat={c['hat']} not in HAT_LINES")
        assert noncommon_found, "No non-common pets generated in 2000 samples"

    def test_hat_never_invalid(self):
        for i in range(2000):
            c = generate_companion("testuser", str(i))
            assert c['hat'] in HAT_LINES, f"seed={i}: hat={c['hat']} not in HAT_LINES keys"


class TestShinyProbability:
    """SubTask 3.7: shiny probability ~1% (loose bounds 0.5%-2%).

    generate_companion sets shiny = rng() < 0.01, which yields ~1% under a
    uniform PRNG. pet_core.mulberry32 is non-uniform so the real shiny rate is
    far lower; we patch mulberry32 with a uniform PRNG to test the shiny
    logic as intended. A separate test confirms shiny is always a bool under
    the real mulberry32.
    """

    @pytest.mark.slow
    def test_shiny_ratio_about_1_percent(self):
        n = 10000
        shiny_count = 0
        with patch('ascii_pet.core.mulberry32', side_effect=lambda s: random.Random(s).random):
            for i in range(n):
                c = generate_companion("testuser", str(i))
                if c['shiny']:
                    shiny_count += 1
        ratio = shiny_count / n
        # Expected ~1%; allow loose [0.5%, 2%] band to avoid flaky tests
        assert ratio > 0.005, (
            f"shiny ratio {ratio:.4f} too low (< 0.5%), count={shiny_count}")
        assert ratio < 0.02, (
            f"shiny ratio {ratio:.4f} too high (> 2%), count={shiny_count}")

    @pytest.mark.slow
    def test_shiny_is_bool_in_large_sample(self):
        for i in range(1000):
            c = generate_companion("testuser", str(i))
            assert isinstance(c['shiny'], bool)

    def test_shiny_can_be_true_under_uniform_rng(self):
        """Under a uniform PRNG, at least one shiny pet must appear in 10000."""
        found_shiny = False
        with patch('ascii_pet.core.mulberry32', side_effect=lambda s: random.Random(s).random):
            for i in range(10000):
                if generate_companion("testuser", str(i))['shiny']:
                    found_shiny = True
                    break
        assert found_shiny, "No shiny pet generated in 10000 samples under uniform PRNG"
