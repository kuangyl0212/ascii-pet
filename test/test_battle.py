#!/usr/bin/env python3
"""TDD tests for battle simulation engine.

Covers:
  Task 4: simulate_battle() - pure-function battle simulation engine
  Task 5: calc_escape_chance() - escape chance calculation

Run: python -m pytest test/test_battle.py -v
"""

import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pytest
from ascii_pet.core import SKILLS, calculate_combat_stats
from ascii_pet import battle


# ─── Test helpers ────────────────────────────────────────────────────────────

def make_combatant(name='TestPet', level=5, hp=100, attack=20, defense=15,
                   speed=10, skills=None):
    """Create a combatant dict for battle testing.

    Matches the structure returned by calculate_combat_stats plus
    the 'name' and 'level' fields required by simulate_battle.
    """
    return {
        'name': name,
        'level': level,
        'hp': hp,
        'attack': attack,
        'defense': defense,
        'speed': speed,
        'skills': skills or ['tackle', 'scratch'],
    }


class FakeRandom:
    """Fake RNG for deterministic testing.

    Returns predetermined values from `random_values` in order, then
    falls back to `default` for any subsequent calls. `choice()` always
    returns the first element of the sequence (use single-skill lists to
    control skill selection).
    """

    def __init__(self, random_values=None, default=0.0):
        self._random_values = list(random_values) if random_values else []
        self._index = 0
        self._default = default

    def random(self):
        if self._index < len(self._random_values):
            val = self._random_values[self._index]
            self._index += 1
            return val
        return self._default

    def choice(self, seq):
        return seq[0]


def patch_battle_rng(fake_rng):
    """Context manager that patches random.Random inside battle module."""
    return patch('ascii_pet.battle.random.Random', return_value=fake_rng)


# ─── Task 4: Battle simulation engine ────────────────────────────────────────

class TestSimulateBattleExists:
    """Test simulate_battle function exists and returns correct structure."""

    def test_function_exists(self):
        assert hasattr(battle, 'simulate_battle')

    def test_returns_dict(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result = battle.simulate_battle(attacker, defender, seed=42)
        assert isinstance(result, dict)

    def test_returns_required_keys(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result = battle.simulate_battle(attacker, defender, seed=42)
        for key in ('winner', 'loser', 'log', 'hp_loss_winner', 'hp_loss_loser'):
            assert key in result, f'Missing key: {key}'

    def test_winner_loser_are_names(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result = battle.simulate_battle(attacker, defender, seed=42)
        assert result['winner'] in ('Attacker', 'Defender')
        assert result['loser'] in ('Attacker', 'Defender')
        assert result['winner'] != result['loser']

    def test_log_is_list_of_strings(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result = battle.simulate_battle(attacker, defender, seed=42)
        assert isinstance(result['log'], list)
        assert len(result['log']) > 0
        for entry in result['log']:
            assert isinstance(entry, str)


class TestBattleDeterminism:
    """Test that same seed + same inputs produce same output."""

    def test_same_seed_same_output(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result1 = battle.simulate_battle(attacker, defender, seed=123)
        result2 = battle.simulate_battle(attacker, defender, seed=123)
        assert result1 == result2

    def test_different_seed_likely_different_output(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result1 = battle.simulate_battle(attacker, defender, seed=1)
        result2 = battle.simulate_battle(attacker, defender, seed=9999)
        # Not guaranteed, but extremely likely to differ
        assert result1 != result2


class TestSpeedDeterminesOrder:
    """Test that the faster pet attacks first."""

    def test_faster_attacker_goes_first(self):
        """When attacker.speed > defender.speed, attacker goes first."""
        attacker = make_combatant(name='FastAttacker', speed=100, skills=['tackle'])
        defender = make_combatant(name='SlowDefender', speed=10, skills=['tackle'])
        result = battle.simulate_battle(attacker, defender, seed=42)
        first_log = result['log'][0]
        # First log entry should mention the faster pet (attacker) as the one attacking
        assert 'FastAttacker' in first_log
        # The first attacker's name should appear before the defender's name
        # in the log entry (attacker used skill, defender BP shown)
        assert first_log.index('FastAttacker') < first_log.index('SlowDefender')

    def test_faster_defender_goes_first(self):
        """When defender.speed > attacker.speed, defender goes first."""
        attacker = make_combatant(name='SlowAttacker', speed=10, skills=['tackle'])
        defender = make_combatant(name='FastDefender', speed=100, skills=['tackle'])
        result = battle.simulate_battle(attacker, defender, seed=42)
        first_log = result['log'][0]
        assert 'FastDefender' in first_log
        assert first_log.index('FastDefender') < first_log.index('SlowAttacker')


class TestSkillAccuracy:
    """Test skill accuracy and miss handling."""

    def test_miss_shows_in_log(self):
        """When accuracy check fails, log shows 'missed' and no damage dealt."""
        # tackle: accuracy=95. To miss: rng.random()*100 >= 95 → rng.random() >= 0.95
        # Defender has only tail_whip (power 0) so it can't damage attacker,
        # ensuring battle eventually ends with attacker winning.
        attacker = make_combatant(name='Attacker', attack=50, defense=50,
                                  speed=100, skills=['tackle'])
        defender = make_combatant(name='Defender', attack=10, defense=10,
                                  speed=10, skills=['tail_whip'])
        # First random() = 0.96 → miss (0.96*100=96 >= 95)
        # Subsequent random() default = 0.0 → hit (0.0*100=0 < 95), multiplier 0.8
        fake_rng = FakeRandom(random_values=[0.96], default=0.0)
        with patch_battle_rng(fake_rng):
            result = battle.simulate_battle(attacker, defender, seed=0)
        first_log = result['log'][0]
        assert 'miss' in first_log.lower()
        # No damage value on a miss
        assert 'Damage' not in first_log

    def test_hit_deals_damage(self):
        """When accuracy check passes, damage is dealt (no 'missed' in log)."""
        attacker = make_combatant(name='Attacker', attack=50, defense=50,
                                  speed=100, skills=['tackle'])
        defender = make_combatant(name='Defender', attack=10, defense=10,
                                  speed=10, skills=['tail_whip'])
        # First random() = 0.0 → hit, second = 0.5 → multiplier 1.0
        fake_rng = FakeRandom(random_values=[0.0, 0.5], default=0.0)
        with patch_battle_rng(fake_rng):
            result = battle.simulate_battle(attacker, defender, seed=0)
        first_log = result['log'][0]
        assert 'miss' not in first_log.lower()
        assert 'damage' in first_log.lower() or 'Damage' in first_log


class TestDamageFormula:
    """Test the damage calculation formula."""

    def test_damage_with_1x_multiplier(self):
        """With RNG returning 0.5 for multiplier (1.0x), damage = power * (atk/(atk+def)) * 1.0."""
        # tackle: power=35, accuracy=95
        # attacker attack=20, defender defense=20
        # damage = 35 * (20/(20+20)) * 1.0 = 35 * 0.5 * 1.0 = 17.5
        attacker = make_combatant(name='Attacker', attack=20, defense=20,
                                  speed=100, skills=['tackle'])
        defender = make_combatant(name='Defender', attack=20, defense=20,
                                  speed=10, skills=['tail_whip'])
        # random_values: [accuracy=0.0 (hit), multiplier=0.5 (1.0x)]
        fake_rng = FakeRandom(random_values=[0.0, 0.5], default=0.0)
        with patch_battle_rng(fake_rng):
            result = battle.simulate_battle(attacker, defender, seed=0)
        first_log = result['log'][0]
        expected_damage = 35 * (20 / (20 + 20)) * 1.0  # 17.5
        # Log should contain the exact damage value
        assert '17.5' in first_log, f'Expected damage 17.5 in log: {first_log}'


class TestHPLossCaps:
    """Test HP loss calculation and caps."""

    def test_loser_hp_loss_is_25(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result = battle.simulate_battle(attacker, defender, seed=42)
        assert result['hp_loss_loser'] == 25

    def test_winner_hp_loss_at_most_25(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result = battle.simulate_battle(attacker, defender, seed=42)
        assert result['hp_loss_winner'] <= 25
        assert result['hp_loss_winner'] >= 0

    def test_winner_hp_loss_zero_when_undamaged(self):
        """If winner never took damage, hp_loss_winner = 0."""
        # Attacker is much stronger and defender only has 0-power skills,
        # so winner (attacker) takes 0 damage.
        attacker = make_combatant(name='Attacker', attack=100, defense=100,
                                  speed=100, skills=['tackle'])
        defender = make_combatant(name='Defender', attack=1, defense=1,
                                  speed=10, skills=['tail_whip'])
        result = battle.simulate_battle(attacker, defender, seed=42)
        assert result['winner'] == 'Attacker'
        assert result['hp_loss_winner'] == 0


class TestUnderdogWinRate:
    """Test that underdog (weak pet) can win against strong pet."""

    @pytest.mark.slow
    def test_weak_pet_wins_at_least_10_percent(self):
        """Level 5 common pet vs level 20 rare pet, weak wins >= 10%."""
        # Use dragon (common lv5) vs mushroom (rare lv20):
        #   - dragon has fire_breath (power 60) for high damage
        #   - mushroom has heal_light (power 0) giving underdog a chance
        weak_state = {'species': 'dragon', 'rarity': 'common', 'level': 5, 'hp': 100}
        strong_state = {'species': 'mushroom', 'rarity': 'rare', 'level': 20, 'hp': 100}

        weak_stats = calculate_combat_stats(weak_state)
        strong_stats = calculate_combat_stats(strong_state)

        weak = {**weak_stats, 'name': 'Weak', 'level': 5}
        strong = {**strong_stats, 'name': 'Strong', 'level': 20}

        weak_wins = 0
        n_simulations = 1000
        for seed in range(n_simulations):
            result = battle.simulate_battle(weak, strong, seed=seed)
            if result['winner'] == 'Weak':
                weak_wins += 1

        win_rate = weak_wins / n_simulations
        assert win_rate >= 0.10, f'Weak pet win rate {win_rate:.2%} < 10%'


class TestBattleLogFormat:
    """Test the battle log format."""

    def test_log_contains_attacker_name(self):
        attacker = make_combatant(name='Alice', speed=100, skills=['tackle'])
        defender = make_combatant(name='Bob', speed=10, skills=['tackle'])
        result = battle.simulate_battle(attacker, defender, seed=42)
        first_log = result['log'][0]
        assert 'Alice' in first_log or 'Bob' in first_log

    def test_log_contains_skill_name(self):
        attacker = make_combatant(name='Alice', speed=100, skills=['tackle'])
        defender = make_combatant(name='Bob', speed=10, skills=['tackle'])
        result = battle.simulate_battle(attacker, defender, seed=42)
        first_log = result['log'][0]
        # SKILLS['tackle']['name'] == 'Tackle'
        assert 'Tackle' in first_log

    def test_log_contains_damage_or_missed(self):
        attacker = make_combatant(name='Alice', speed=100, skills=['tackle'])
        defender = make_combatant(name='Bob', speed=10, skills=['tackle'])
        result = battle.simulate_battle(attacker, defender, seed=42)
        for entry in result['log']:
            assert 'damage' in entry.lower() or 'miss' in entry.lower(), \
                f'Log entry missing damage/missed: {entry}'

    def test_log_contains_remaining_bp(self):
        attacker = make_combatant(name='Alice', speed=100, skills=['tackle'])
        defender = make_combatant(name='Bob', speed=10, skills=['tackle'])
        result = battle.simulate_battle(attacker, defender, seed=42)
        for entry in result['log']:
            # Log should contain "BP" followed by a number (remaining battle hp)
            assert 'BP' in entry or 'bp' in entry.lower(), \
                f'Log entry missing remaining BP: {entry}'


# ─── Task 5: Escape chance calculation ───────────────────────────────────────

class TestCalcEscapeChance:
    """Tests for calc_escape_chance function."""

    def test_function_exists(self):
        assert hasattr(battle, 'calc_escape_chance')

    def test_equal_levels_returns_0_3(self):
        assert battle.calc_escape_chance(10, 10) == 0.3

    def test_basic_formula(self):
        # 0.3 + (defender_level - attacker_level) * 0.03
        assert battle.calc_escape_chance(15, 10) == pytest.approx(0.45)

    def test_clamp_at_max_0_7(self):
        # level diff +15 → 0.3 + 15*0.03 = 0.75, clamped to 0.7
        assert battle.calc_escape_chance(25, 10) == 0.7

    def test_clamp_at_min_0_1(self):
        # level diff -10 → 0.3 + (-10)*0.03 = 0.0, clamped to 0.1
        assert battle.calc_escape_chance(5, 15) == 0.1

    def test_negative_level_diff(self):
        # defender lower than attacker
        assert battle.calc_escape_chance(8, 10) == pytest.approx(0.24)

    def test_returns_float(self):
        result = battle.calc_escape_chance(10, 10)
        assert isinstance(result, float)


# ─── Battle log i18n ─────────────────────────────────────────────────────────


class TestBattleLogI18n:
    """Test that battle log entries use translatable text via _()."""

    def test_hit_log_uses_translatable_format(self):
        """Hit log entries should be produced via _() so they can be translated.
        Verify the format contains expected patterns (name, skill, damage, BP)."""
        attacker = make_combatant(name='Alice', attack=20, defense=20,
                                  speed=100, skills=['tackle'])
        defender = make_combatant(name='Bob', attack=20, defense=20,
                                  speed=10, skills=['tackle'])
        # Force a hit: accuracy check passes, multiplier = 1.0
        fake_rng = FakeRandom(random_values=[0.0, 0.5], default=0.0)
        with patch_battle_rng(fake_rng):
            result = battle.simulate_battle(attacker, defender, seed=0)
        first_log = result['log'][0]
        # Should contain attacker name, skill name, damage value, defender name, BP
        assert 'Alice' in first_log
        assert 'Tackle' in first_log
        assert 'Bob' in first_log
        assert 'BP' in first_log
        # Should NOT contain raw f-string pattern like "used ...! Damage:"
        # (it should use the _() translated format instead)

    def test_miss_log_uses_translatable_format(self):
        """Miss log entries should be produced via _() so they can be translated.
        Verify the format contains expected patterns (name, skill, Missed, BP)."""
        attacker = make_combatant(name='Alice', attack=50, defense=50,
                                  speed=100, skills=['tackle'])
        defender = make_combatant(name='Bob', attack=10, defense=10,
                                  speed=10, skills=['tail_whip'])
        # Force a miss: accuracy check fails
        fake_rng = FakeRandom(random_values=[0.96], default=0.0)
        with patch_battle_rng(fake_rng):
            result = battle.simulate_battle(attacker, defender, seed=0)
        first_log = result['log'][0]
        assert 'Alice' in first_log
        assert 'Tackle' in first_log
        assert 'Bob' in first_log
        assert 'BP' in first_log
        assert 'miss' in first_log.lower()

    def test_chinese_translation_produces_chinese_log(self):
        """When language is set to zh, battle log should contain Chinese characters."""
        from ascii_pet.i18n import set_language
        set_language('zh')
        try:
            attacker = make_combatant(name='Alice', speed=100, skills=['tackle'])
            defender = make_combatant(name='Bob', speed=10, skills=['tackle'])
            result = battle.simulate_battle(attacker, defender, seed=42)
            # At least one log entry should contain Chinese characters
            has_chinese = any(
                any('\u4e00' <= c <= '\u9fff' for c in entry)
                for entry in result['log']
            )
            assert has_chinese, f'Expected Chinese characters in log: {result["log"]}'
        finally:
            set_language('en')


# ─── Task 1 of add-battle-xp-rewards spec: XP return fields ─────────────────
# Tests that simulate_battle exposes xp_winner / xp_loser fields and that
# the module exposes WIN_XP / LOSE_XP constants. See spec tasks.md.


class TestBattleXPRewards:
    """Tests for XP reward fields returned by simulate_battle.

    Implements Task 1 of the add-battle-xp-rewards spec: the battle result
    dict must include `xp_winner` (winner's XP reward) and `xp_loser` (loser's
    XP reward), backed by module-level constants WIN_XP / LOSE_XP.
    """

    def test_returns_xp_winner_field(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result = battle.simulate_battle(attacker, defender, seed=42)
        assert 'xp_winner' in result

    def test_returns_xp_loser_field(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result = battle.simulate_battle(attacker, defender, seed=42)
        assert 'xp_loser' in result

    def test_xp_winner_is_40(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result = battle.simulate_battle(attacker, defender, seed=42)
        assert result['xp_winner'] == 40

    def test_xp_loser_is_10(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result = battle.simulate_battle(attacker, defender, seed=42)
        assert result['xp_loser'] == 10

    def test_xp_fields_are_int(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result = battle.simulate_battle(attacker, defender, seed=42)
        assert isinstance(result['xp_winner'], int)
        assert isinstance(result['xp_loser'], int)

    def test_xp_is_deterministic(self):
        attacker = make_combatant(name='Attacker', speed=20)
        defender = make_combatant(name='Defender', speed=10)
        result1 = battle.simulate_battle(attacker, defender, seed=42)
        result2 = battle.simulate_battle(attacker, defender, seed=42)
        assert result1['xp_winner'] == result2['xp_winner']
        assert result1['xp_loser'] == result2['xp_loser']

    def test_constants_exposed(self):
        from ascii_pet import battle as battle_mod
        assert battle_mod.WIN_XP == 40
        assert battle_mod.LOSE_XP == 10


# ─── Task 5: make_battle_snapshot chaos field ────────────────────────────────


def test_battle_snapshot_includes_chaos():
    """Battle snapshot must include chaos field from pet stats."""
    from ascii_pet.protocol import make_battle_snapshot
    state = {
        'name': 'TestPet',
        'species': 'blob',
        'rarity': 'common',
        'level': 5,
        'shiny': False,
        'hp': 100,
        'stats': {'HUNGER': 80, 'HAPPY': 70, 'ENERGY': 60, 'WISDOM': 50, 'CHAOS': 42},
    }
    snapshot = make_battle_snapshot(state, 'TestOwner')
    assert 'chaos' in snapshot
    assert snapshot['chaos'] == 42


def test_battle_snapshot_chaos_default_0():
    """Battle snapshot should default chaos to 0 when CHAOS key is missing."""
    from ascii_pet.protocol import make_battle_snapshot
    state = {
        'name': 'TestPet',
        'species': 'blob',
        'rarity': 'common',
        'level': 5,
        'shiny': False,
        'hp': 100,
        'stats': {'HUNGER': 80, 'HAPPY': 70, 'ENERGY': 60, 'WISDOM': 50},  # no CHAOS
    }
    snapshot = make_battle_snapshot(state, 'TestOwner')
    assert snapshot['chaos'] == 0


# ─── Task 6: CHAOS crit/dodge mechanics ─────────────────────────────────────


def test_crit_chance_chaos_0_is_5_percent():
    """Crit chance at CHAOS=0 should be 5%."""
    from ascii_pet.battle import calc_crit_chance
    assert calc_crit_chance(0) == pytest.approx(0.05)


def test_crit_chance_chaos_100_is_35_percent():
    """Crit chance at CHAOS=100 should be capped at 35%."""
    from ascii_pet.battle import calc_crit_chance
    assert calc_crit_chance(100) == pytest.approx(0.35)


def test_crit_chance_chaos_50_is_20_percent():
    """Crit chance at CHAOS=50 should be 5% + 50*0.3% = 20%."""
    from ascii_pet.battle import calc_crit_chance
    assert calc_crit_chance(50) == pytest.approx(0.20)


def test_dodge_chance_chaos_0_is_0_percent():
    """Dodge chance at CHAOS=0 should be 0%."""
    from ascii_pet.battle import calc_dodge_chance
    assert calc_dodge_chance(0) == pytest.approx(0.0)


def test_dodge_chance_chaos_100_is_20_percent():
    """Dodge chance at CHAOS=100 should be capped at 20%."""
    from ascii_pet.battle import calc_dodge_chance
    assert calc_dodge_chance(100) == pytest.approx(0.20)


def test_dodge_chance_chaos_50_is_10_percent():
    """Dodge chance at CHAOS=50 should be 50*0.2% = 10%."""
    from ascii_pet.battle import calc_dodge_chance
    assert calc_dodge_chance(50) == pytest.approx(0.10)


def test_missing_chaos_defaults_to_0():
    """Attacker/defender without chaos field should be treated as CHAOS=0."""
    from ascii_pet.battle import simulate_battle
    # No 'chaos' key in attacker or defender
    attacker = {'name': 'A', 'level': 1, 'hp': 100, 'attack': 50, 'defense': 10,
                'speed': 15, 'skills': ['tackle']}
    defender = {'name': 'D', 'level': 1, 'hp': 100, 'attack': 10, 'defense': 10,
                'speed': 10, 'skills': ['tackle']}
    # Should not raise
    result = simulate_battle(attacker, defender, seed=123)
    assert 'winner' in result
    assert 'xp_winner' in result


def test_battle_with_chaos_does_not_crash():
    """Battle with chaos field should complete normally."""
    from ascii_pet.battle import simulate_battle
    attacker = {'name': 'A', 'level': 1, 'hp': 100, 'attack': 50, 'defense': 10,
                'speed': 15, 'skills': ['tackle'], 'chaos': 80}
    defender = {'name': 'D', 'level': 1, 'hp': 100, 'attack': 10, 'defense': 10,
                'speed': 10, 'skills': ['tackle'], 'chaos': 30}
    result = simulate_battle(attacker, defender, seed=456)
    assert 'winner' in result
    # Verify log may contain Crit! or Dodged! when chaos > 0
    log_text = ' '.join(result['log'])
    # Just verify it runs; specific crit/dodge depends on rng
    assert len(result['log']) > 0


def test_crit_deterministic_with_seed():
    """Same seed + input should produce identical battle log."""
    from ascii_pet.battle import simulate_battle
    attacker = {'name': 'A', 'level': 1, 'hp': 100, 'attack': 50, 'defense': 10,
                'speed': 15, 'skills': ['tackle'], 'chaos': 100}
    defender = {'name': 'D', 'level': 1, 'hp': 100, 'attack': 10, 'defense': 10,
                'speed': 10, 'skills': ['tackle'], 'chaos': 100}
    r1 = simulate_battle(dict(attacker), dict(defender), seed=789)
    r2 = simulate_battle(dict(attacker), dict(defender), seed=789)
    assert r1['log'] == r2['log']
    assert r1['winner'] == r2['winner']


# ─── SubTask 6.4 & 6.5: crit×1.5 damage and dodge zero-damage ──────────────


def test_crit_multiplies_damage_by_1_5():
    """When crit triggers, damage should be base_damage × 1.5.

    Uses FakeRandom to force (defender has no chaos → dodge check skipped;
    attacker chaos=100 → crit_chance=0.35, crit check executes):
      1st random() = 0.0  → accuracy check (hit, 0 < 95)
      2nd random() = 0.5  → multiplier (1.0x)
      3rd random() = 0.0  → crit check (0 < 0.35 → crit)
    Base damage = 35 * (20/(20+20)) * 1.0 = 17.5
    Crit damage = 17.5 * 1.5 = 26.25
    """
    attacker = make_combatant(name='Attacker', attack=20, defense=20,
                              speed=100, skills=['tackle'])
    attacker['chaos'] = 100  # crit_chance = 0.35
    defender = make_combatant(name='Defender', attack=20, defense=20,
                              speed=10, skills=['tail_whip'])
    fake_rng = FakeRandom(random_values=[0.0, 0.5, 0.0], default=0.0)
    with patch_battle_rng(fake_rng):
        result = battle.simulate_battle(attacker, defender, seed=0)
    first_log = result['log'][0]
    assert 'Crit' in first_log, f'Expected crit in log: {first_log}'
    # Crit damage = 17.5 * 1.5 = 26.25
    assert '26.2' in first_log, f'Expected crit damage 26.2 in log: {first_log}'


def test_dodge_zero_damage_logs_dodged():
    """When defender dodges, damage is 0 and log contains 'Dodged!'.

    Uses FakeRandom to force (defender chaos=100 → dodge_chance=0.20,
    dodge check executes FIRST and consumes the first rng.random()):
      1st random() = 0.0 → dodge check (0 < 0.20 → dodge)
    After dodge, defender['battle_bp'] should be unchanged at 100.0.
    """
    attacker = make_combatant(name='Attacker', attack=20, defense=20,
                              speed=100, skills=['tackle'])
    defender = make_combatant(name='Defender', attack=20, defense=20,
                              speed=10, skills=['tail_whip'])
    defender['chaos'] = 100  # dodge_chance = 0.20
    fake_rng = FakeRandom(random_values=[0.0], default=0.0)
    with patch_battle_rng(fake_rng):
        result = battle.simulate_battle(attacker, defender, seed=0)
    first_log = result['log'][0]
    assert 'Dodge' in first_log, f'Expected Dodged! in log: {first_log}'
    # BP should be unchanged (100.0) since no damage was dealt
    assert '100.0' in first_log, f'Expected BP 100.0 in log: {first_log}'
