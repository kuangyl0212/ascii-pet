#!/usr/bin/env python3
"""TDD tests for pet rename feature.

RED phase: these tests should FAIL until rename_pet and rename mode are implemented.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame, init_state, generate_companion


def _uid():
    return f'test-rename-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


@pytest.fixture
def game(tmp_path):
    uid = _uid()
    return PetGame(uid, data_dir=tmp_path)


# ─── rename_pet method ────────────────────────────────────────────────────────


class TestRenamePet:
    """Test PetGame.rename_pet(new_name) method."""

    def test_rename_pet_success(self, game):
        """Normal rename: name is updated and saved."""
        old_name = game.state['name']
        result = game.rename_pet('Fluffy')
        assert game.state['name'] == 'Fluffy'
        assert 'Fluffy' in result
        # Verify persistence
        game2 = PetGame(game.uid, data_dir=game.data_dir)
        assert game2.state['name'] == 'Fluffy'

    def test_rename_pet_chinese_name(self, game):
        """Chinese name should be accepted."""
        game.rename_pet('小橘')
        assert game.state['name'] == '小橘'

    def test_rename_pet_empty_name_rejected(self, game):
        """Empty name (whitespace only) should be rejected."""
        old_name = game.state['name']
        result = game.rename_pet('   ')
        assert game.state['name'] == old_name
        assert 'empty' in result.lower() or 'cannot' in result.lower()

    def test_rename_pet_too_long_rejected(self, game):
        """Name exceeding 20 chars should be rejected."""
        old_name = game.state['name']
        long_name = 'A' * 21
        result = game.rename_pet(long_name)
        assert game.state['name'] == old_name
        assert 'long' in result.lower() or 'max' in result.lower() or '20' in result

    def test_rename_pet_max_length_accepted(self, game):
        """Name at exactly 20 chars should be accepted."""
        name_20 = 'B' * 20
        game.rename_pet(name_20)
        assert game.state['name'] == name_20

    def test_rename_pet_returns_message(self, game):
        """rename_pet should return a success message containing the new name."""
        result = game.rename_pet('Mittens')
        assert isinstance(result, str)
        assert len(result) > 0


# ─── rename mode via handle_key ────────────────────────────────────────────────


class TestRenameMode:
    """Test rename mode entry, input, confirm, and cancel via handle_key."""

    def test_enter_rename_mode_from_stats(self, game):
        """Press 'r' in stats mode enters rename mode."""
        game.mode = 'stats'
        atype, detail = game.handle_key('r')
        assert game.mode == 'rename'
        assert atype == 'mode_change'

    def test_enter_rename_mode_initializes_input(self, game):
        """Entering rename mode should initialize _rename_input buffer."""
        game.mode = 'stats'
        game.handle_key('r')
        assert hasattr(game, '_rename_input')
        assert game._rename_input == ''

    def test_rename_mode_char_input(self, game):
        """Typing in rename mode appends to input buffer."""
        game.mode = 'stats'
        game.handle_key('r')
        game.handle_key('F')
        game.handle_key('l')
        game.handle_key('u')
        assert game._rename_input == 'Flu'

    def test_rename_mode_backspace(self, game):
        """Backspace removes last character from input buffer."""
        game.mode = 'stats'
        game.handle_key('r')
        game.handle_key('A')
        game.handle_key('B')
        game.handle_key('\x08')  # backspace
        assert game._rename_input == 'A'

    def test_rename_mode_max_length_input(self, game):
        """Input buffer should not exceed 20 characters."""
        game.mode = 'stats'
        game.handle_key('r')
        for ch in 'A' * 25:
            game.handle_key(ch)
        assert len(game._rename_input) == 20

    def test_rename_mode_enter_confirms(self, game):
        """Enter key confirms rename and returns to stats mode."""
        game.mode = 'stats'
        game.handle_key('r')
        game.handle_key('F')
        game.handle_key('l')
        game.handle_key('u')
        atype, detail = game.handle_key('\r')
        assert game.mode == 'stats'
        assert game.state['name'] == 'Flu'
        assert atype == 'mode_change'

    def test_rename_mode_enter_empty_rejected(self, game):
        """Enter with empty input should show error, stay in rename mode."""
        game.mode = 'stats'
        game.handle_key('r')
        atype, detail = game.handle_key('\r')
        assert game.mode == 'rename'
        assert game.message is not None

    def test_rename_mode_esc_cancels(self, game):
        """ESC key cancels rename and returns to stats mode."""
        old_name = game.state['name']
        game.mode = 'stats'
        game.handle_key('r')
        game.handle_key('X')
        atype, detail = game.handle_key('\x1b')
        assert game.mode == 'stats'
        assert game.state['name'] == old_name
        assert atype == 'mode_change'

    def test_rename_mode_only_from_stats(self, game):
        """Press 'r' in non-stats mode should not enter rename mode."""
        game.mode = 'expanded'
        atype, detail = game.handle_key('r')
        # In expanded mode, 'r' should not trigger rename
        assert game.mode != 'rename'

    def test_rename_mode_non_printable_ignored(self, game):
        """Non-printable characters should be ignored in rename mode."""
        game.mode = 'stats'
        game.handle_key('r')
        game.handle_key('\t')
        assert game._rename_input == ''
