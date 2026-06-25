#!/usr/bin/env python3
"""TDD tests for battle log XP display (add-battle-xp-rewards spec Task 5).

Verifies that render_battle_log_lines shows XP gained, level-up, and evolution
messages when the battle_result dict carries those fields.

Run: python -m pytest test/test_battle_log_xp.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pytest

# bin/ascii-pet-win.py is not a package; load it directly by path.
import importlib.util
_WIN_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'bin', 'ascii-pet-win.py'
)
_spec = importlib.util.spec_from_file_location('ascii_pet_win', _WIN_MODULE_PATH)
win = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(win)
render_battle_log_lines = win.render_battle_log_lines


class TestBattleLogXPDisplay:
    """render_battle_log_lines should show XP / level-up / evolution info."""

    def test_shows_xp_gained(self):
        """When battle_result includes xp_gained=30, the rendered lines include
        a line mentioning 'XP +30'."""
        battle_result = {
            'winner': 'Alice', 'loser': 'Bob',
            'log': ['Alice used Tackle!'],
            'hp_loss_winner': 5, 'hp_loss_loser': 25,
            'xp_gained': 30,
        }
        lines = render_battle_log_lines(battle_result)
        text_lines = [t for t, _ in lines]
        # Find a line containing 'XP' and '30'
        xp_line = [t for t in text_lines if 'XP' in t and '30' in t]
        assert len(xp_line) >= 1, f'Expected XP +30 line, got: {text_lines}'

    def test_shows_level_up_when_leveled_up(self):
        """When battle_result includes leveled_up=True, the rendered lines
        include a line indicating level up."""
        battle_result = {
            'winner': 'Alice', 'loser': 'Bob',
            'log': ['Alice used Tackle!'],
            'hp_loss_winner': 5, 'hp_loss_loser': 25,
            'xp_gained': 30, 'leveled_up': True,
        }
        lines = render_battle_log_lines(battle_result)
        text_lines = [t for t, _ in lines]
        # Look for 'Level Up' (case-insensitive)
        has_level_up = any('level' in t.lower() and 'up' in t.lower() for t in text_lines)
        assert has_level_up, f'Expected Level Up line, got: {text_lines}'

    def test_shows_evolution_when_evolved(self):
        """When battle_result includes evolved='slime', the rendered lines
        include a line mentioning the new species."""
        battle_result = {
            'winner': 'Alice', 'loser': 'Bob',
            'log': ['Alice used Tackle!'],
            'hp_loss_winner': 5, 'hp_loss_loser': 25,
            'xp_gained': 30, 'leveled_up': True, 'evolved': 'slime',
        }
        lines = render_battle_log_lines(battle_result)
        text_lines = [t for t, _ in lines]
        has_evo = any('slime' in t for t in text_lines)
        assert has_evo, f'Expected evolution line mentioning slime, got: {text_lines}'

    def test_no_xp_line_when_xp_gained_zero_or_missing(self):
        """When xp_gained is 0 or missing, no XP line should be added (or it
        should show +0). Either is acceptable — verify the function does not
        crash and produces some lines."""
        battle_result = {
            'winner': 'Alice', 'loser': 'Bob',
            'log': ['Alice used Tackle!'],
            'hp_loss_winner': 5, 'hp_loss_loser': 25,
        }
        lines = render_battle_log_lines(battle_result)
        # Must not crash; should still produce the basic log lines
        assert len(lines) >= 3  # header + log + result summary

    def test_preserves_existing_lines(self):
        """Existing Winner/Loser and HP lines must still be present."""
        battle_result = {
            'winner': 'Alice', 'loser': 'Bob',
            'log': ['Alice used Tackle!'],
            'hp_loss_winner': 5, 'hp_loss_loser': 25,
            'xp_gained': 30, 'leveled_up': True, 'evolved': 'slime',
        }
        lines = render_battle_log_lines(battle_result)
        text_lines = [t for t, _ in lines]
        # Winner/Loser line still present
        assert any('Alice' in t and 'Bob' in t for t in text_lines)
        # HP line still present
        assert any('HP' in t for t in text_lines)
