#!/usr/bin/env python3
"""Pytest tests for pet_core.export_text function (SubTasks 8.1-8.5)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pytest
from ascii_pet.core import export_text, render_face, RARITY_STARS, STAT_NAMES


@pytest.fixture
def make_state():
    """Factory fixture: build a test state dict with optional stat overrides."""
    def _make(stats=None):
        base_stats = {'HUNGER': 50, 'HAPPY': 50, 'ENERGY': 50, 'WISDOM': 50, 'CHAOS': 50}
        if stats:
            base_stats.update(stats)
        return {
            'name': 'TestPet',
            'species': 'cat',
            'rarity': 'rare',
            'eye': '@',
            'hat': 'none',
            'shiny': False,
            'stats': base_stats,
            'mood': 'normal',
        }
    return _make


@pytest.fixture
def make_bones():
    """Factory fixture: build a test bones dict matching the default state."""
    def _make():
        return {
            'species': 'cat',
            'eye': '@',
            'hat': 'none',
            'shiny': False,
            'rarity': 'rare',
        }
    return _make


@pytest.fixture
def state(make_state):
    """Default test state."""
    return make_state()


@pytest.fixture
def bones(make_bones):
    """Default test bones."""
    return make_bones()


@pytest.fixture
def export_result(state, bones):
    """export_text output for the default state/bones at frame 0."""
    return export_text(state, bones, 0)


# ─── SubTask 8.1: name and rarity stars ───────────────────────────────────────

class TestExportTextNameAndStars:
    """export_text contains name and rarity stars."""

    def test_contains_name(self, export_result):
        assert 'TestPet' in export_result

    def test_contains_rarity_stars(self, export_result):
        assert RARITY_STARS['rare'] in export_result

    def test_contains_three_stars_for_rare(self, export_result):
        assert '★★★' in export_result

    def test_first_line_has_name_and_stars(self, export_result):
        first_line = export_result.split('\n')[0]
        assert first_line == 'TestPet  ★★★'


# ─── SubTask 8.2: species and rarity ──────────────────────────────────────────

class TestExportTextSpeciesAndRarity:
    """export_text contains species and rarity."""

    def test_contains_species(self, export_result):
        assert 'cat' in export_result

    def test_contains_rarity_word(self, export_result):
        assert 'rare' in export_result

    def test_second_line_has_species_and_rarity(self, export_result):
        second_line = export_result.split('\n')[1]
        assert 'cat' in second_line
        assert 'rare' in second_line


# ─── SubTask 8.3: face line ───────────────────────────────────────────────────

class TestExportTextFaceLine:
    """export_text contains the face line."""

    def test_contains_face_prefix(self, export_result):
        assert 'face: ' in export_result

    def test_contains_render_face_output(self, export_result, bones):
        expected_face = render_face(bones)
        assert expected_face in export_result

    def test_face_line_format(self, export_result, bones):
        expected_face_line = f'face: {render_face(bones)}'
        assert expected_face_line in export_result

    def test_cat_face_value(self, export_result):
        # cat with eye '@' -> '=@ω@='
        assert '=@ω@=' in export_result


# ─── SubTask 8.4: stat name prefixes ──────────────────────────────────────────

class TestExportTextStatNames:
    """export_text contains all 5 stat name prefixes."""

    def test_contains_all_stat_prefixes(self, export_result):
        for stat in STAT_NAMES:
            assert stat[:4] in export_result, (
                f'Stat prefix {stat[:4]} not found in export_text output'
            )

    @pytest.mark.parametrize('stat,prefix', [
        ('HUNGER', 'HUNG'),
        ('HAPPY', 'HAPP'),
        ('ENERGY', 'ENER'),
        ('WISDOM', 'WISD'),
        ('CHAOS', 'CHAO'),
    ])
    def test_contains_stat_prefix(self, export_result, stat, prefix):
        assert prefix in export_result

    def test_has_five_stat_lines(self, export_result):
        lines = export_result.split('\n')
        stat_lines = [ln for ln in lines if ln.startswith(('HUNG', 'HAPP', 'ENER', 'WISD', 'CHAO'))]
        assert len(stat_lines) == 5


# ─── SubTask 8.5: stat bar format ─────────────────────────────────────────────

class TestExportTextStatBarFormat:
    """export_text stat bar format with █/░ fill."""

    @pytest.mark.parametrize('value,filled,empty', [
        (0, 0, 20),
        (50, 10, 10),
        (100, 20, 0),
    ])
    def test_hunger_bar_fill_counts(self, make_state, make_bones, value, filled, empty):
        state = make_state({'HUNGER': value})
        bones = make_bones()
        result = export_text(state, bones, 0)
        lines = result.split('\n')
        hunger_line = next(ln for ln in lines if ln.startswith('HUNG'))
        assert hunger_line.count('█') == filled
        assert hunger_line.count('░') == empty
        assert str(value) in hunger_line

    @pytest.mark.parametrize('value', [0, 50, 100])
    @pytest.mark.parametrize('stat', STAT_NAMES)
    def test_all_stats_bar_fill_counts(self, make_state, make_bones, stat, value):
        state = make_state({stat: value})
        bones = make_bones()
        result = export_text(state, bones, 0)
        lines = result.split('\n')
        stat_line = next(ln for ln in lines if ln.startswith(stat[:4]))
        expected_filled = round(value / 5)
        assert stat_line.count('█') == expected_filled, (
            f'Stat {stat} should have {expected_filled} filled blocks at v={value}'
        )
        assert stat_line.count('░') == 20 - expected_filled, (
            f'Stat {stat} should have {20 - expected_filled} empty blocks at v={value}'
        )

    def test_stat_bar_exact_format(self, make_state, make_bones):
        """Verify exact format: '{STAT[:4]}  {█*round(v/5)}{░*(20-round(v/5))} {v}'"""
        state = make_state({'HUNGER': 50})
        bones = make_bones()
        result = export_text(state, bones, 0)
        lines = result.split('\n')
        hunger_line = next(ln for ln in lines if ln.startswith('HUNG'))
        expected = 'HUNG  ' + '█' * 10 + '░' * 10 + ' 50'
        assert hunger_line == expected

    @pytest.mark.parametrize('value', [0, 25, 50, 75, 100])
    def test_stat_bar_total_length_is_constant(self, make_state, make_bones, value):
        """Bar should always be 20 chars wide regardless of value."""
        state = make_state({'HUNGER': value})
        bones = make_bones()
        result = export_text(state, bones, 0)
        lines = result.split('\n')
        hunger_line = next(ln for ln in lines if ln.startswith('HUNG'))
        filled = hunger_line.count('█')
        empty = hunger_line.count('░')
        assert filled + empty == 20, (
            f'Bar width should be 20 for v={value}, got {filled + empty}'
        )
