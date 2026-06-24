#!/usr/bin/env python3
"""TDD tests for Windows rename rendering.

RED phase: these tests should FAIL until render_rename_lines,
LAYOUT_SIZES['rename'], and get_render_lines rename mode are implemented.
"""

import importlib.util
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame


def _uid():
    return f'test-rename-win-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


@pytest.fixture
def game(tmp_path):
    uid = _uid()
    return PetGame(uid, data_dir=tmp_path)


def _load_win_module():
    """Load bin/ascii-pet-win.py as a module via importlib (skips main execution)."""
    win_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'bin', 'ascii-pet-win.py'
    )
    # Patch ctypes.windll to avoid Win32 API errors on import
    import unittest.mock
    # We need to mock the ctypes windll before importing
    spec = importlib.util.spec_from_file_location('ascii_pet_win', win_path)
    mod = importlib.util.module_from_spec(spec)

    # Pre-set sys.modules entries that the module tries to import
    # Mock windll to prevent actual Win32 calls
    with unittest.mock.patch('ctypes.windll', create=True):
        with unittest.mock.patch('ctypes.POINTER', lambda x: x):
            try:
                spec.loader.exec_module(mod)
            except Exception:
                # If full import fails due to Win32 deps, skip
                pytest.skip("Cannot load win32 module on this platform")
    return mod


# ─── LAYOUT_SIZES ─────────────────────────────────────────────────────────────


class TestLayoutSizesRename:
    """Test that LAYOUT_SIZES has a 'rename' entry."""

    def test_layout_sizes_has_rename_key(self):
        """LAYOUT_SIZES should contain 'rename' key."""
        mod = _load_win_module()
        assert 'rename' in mod.LAYOUT_SIZES

    def test_layout_sizes_rename_value(self):
        """LAYOUT_SIZES['rename'] should be a (width, height) tuple."""
        mod = _load_win_module()
        val = mod.LAYOUT_SIZES['rename']
        assert isinstance(val, tuple)
        assert len(val) == 2
        w, h = val
        assert w >= 30  # reasonable width for rename dialog
        assert h >= 8   # reasonable height for rename dialog


# ─── render_rename_lines ──────────────────────────────────────────────────────


class TestRenderRenameLines:
    """Test render_rename_lines(game) function output structure."""

    def test_render_rename_lines_exists(self):
        """render_rename_lines function should exist in win module."""
        mod = _load_win_module()
        assert hasattr(mod, 'render_rename_lines')
        assert callable(mod.render_rename_lines)

    def test_render_rename_lines_returns_list(self, game):
        """render_rename_lines should return a list."""
        mod = _load_win_module()
        game.mode = 'stats'
        game.handle_key('r')  # enter rename mode
        result = mod.render_rename_lines(game)
        assert isinstance(result, list)

    def test_render_rename_lines_has_title(self, game):
        """First line should contain 'Rename Pet' title."""
        mod = _load_win_module()
        game.mode = 'stats'
        game.handle_key('r')
        lines = mod.render_rename_lines(game)
        # First line text should contain "Rename Pet"
        title_text = lines[0][0]
        assert 'Rename Pet' in title_text

    def test_render_rename_lines_shows_current_name(self, game):
        """Should display the current pet name."""
        mod = _load_win_module()
        current_name = game.state['name']
        game.mode = 'stats'
        game.handle_key('r')
        lines = mod.render_rename_lines(game)
        all_text = ' '.join(line[0] for line in lines)
        assert current_name in all_text

    def test_render_rename_lines_shows_input_with_cursor(self, game):
        """Should display input prompt with cursor '_'."""
        mod = _load_win_module()
        game.mode = 'stats'
        game.handle_key('r')
        game.handle_key('F')  # type something
        lines = mod.render_rename_lines(game)
        all_text = ' '.join(line[0] for line in lines)
        # Should show the typed input followed by cursor
        assert 'F_' in all_text or 'F_' in all_text

    def test_render_rename_lines_shows_empty_cursor(self, game):
        """With empty input, should show '_' cursor."""
        mod = _load_win_module()
        game.mode = 'stats'
        game.handle_key('r')
        lines = mod.render_rename_lines(game)
        all_text = ' '.join(line[0] for line in lines)
        assert '_' in all_text

    def test_render_rename_lines_has_help_text(self, game):
        """Should contain help text for Enter/ESC/Backspace."""
        mod = _load_win_module()
        game.mode = 'stats'
        game.handle_key('r')
        lines = mod.render_rename_lines(game)
        all_text = ' '.join(line[0] for line in lines)
        # Should mention confirm and cancel keys
        assert 'Enter' in all_text or 'confirm' in all_text.lower()
        assert 'ESC' in all_text or 'cancel' in all_text.lower()


# ─── get_render_lines handles rename mode ─────────────────────────────────────


class TestGetRenderLinesRename:
    """Test that PetWindow.get_render_lines handles 'rename' mode."""

    def test_get_render_lines_rename_mode(self, game):
        """When game.mode == 'rename', get_render_lines should return lines."""
        mod = _load_win_module()
        game.mode = 'stats'
        game.handle_key('r')
        assert game.mode == 'rename'

        win = mod.PetWindow(game)
        # Don't call create_window (needs Win32), just test get_render_lines
        lines = win.get_render_lines()
        assert isinstance(lines, list)
        assert len(lines) > 0
        # Should contain rename title
        all_text = ' '.join(
            line[0] if isinstance(line, tuple) else str(line)
            for line in lines
        )
        assert 'Rename Pet' in all_text


# ─── Stats panel help line ────────────────────────────────────────────────────


class TestStatsPanelRenameHelp:
    """Test that stats panel shows [r]rename in help line."""

    def test_stats_lines_contain_rename_hint(self, game):
        """render_stats_lines should include [r]rename hint."""
        mod = _load_win_module()
        lines = mod.render_stats_lines(
            game.state, game.bones, game.frame_idx,
            game.pet_idx, len(game.pets_data['pets'])
        )
        all_text = ' '.join(line[0] for line in lines)
        # Should contain rename hint
        assert 'rename' in all_text.lower() or '[r]' in all_text
