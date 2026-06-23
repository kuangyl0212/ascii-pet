"""Tests for language selection menu and persistence.

TDD RED phase: tests define expected behavior for:
  - Language preference persistence to settings.json
  - Language menu item IDs in ascii-pet-win.py
  - Language switching affects all text output
  - PetGame initializes language from saved settings
  - Language menu command handling
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ascii_pet import i18n


class TestLanguagePersistence:
    """Test language preference persistence to settings.json."""

    def test_save_and_load_settings(self):
        """Language preference is saved and loaded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            i18n.set_language('zh')
            i18n.save_settings(data_dir=tmpdir)
            loaded = i18n.load_settings(data_dir=tmpdir)
            assert loaded == 'zh'

    def test_load_settings_no_file(self):
        """Returns None when no settings file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = i18n.load_settings(data_dir=tmpdir)
            assert result is None

    def test_save_overwrites_previous(self):
        """Saving again overwrites the previous language."""
        with tempfile.TemporaryDirectory() as tmpdir:
            i18n.set_language('zh')
            i18n.save_settings(data_dir=tmpdir)
            i18n.set_language('en')
            i18n.save_settings(data_dir=tmpdir)
            loaded = i18n.load_settings(data_dir=tmpdir)
            assert loaded == 'en'

    def test_settings_file_is_valid_json(self):
        """The settings file contains valid JSON with 'language' key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            i18n.set_language('zh')
            i18n.save_settings(data_dir=tmpdir)
            settings_path = Path(tmpdir) / 'settings.json'
            data = json.loads(settings_path.read_text(encoding='utf-8'))
            assert data['language'] == 'zh'

    def test_init_language_from_settings(self):
        """init_language loads saved language preference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            i18n.set_language('zh')
            i18n.save_settings(data_dir=tmpdir)
            i18n.set_language('en')  # Change to something else
            i18n.init_language(data_dir=tmpdir)
            assert i18n.get_language() == 'zh'


class TestLanguageMenuConstants:
    """Test that language menu constants are defined correctly."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        """Load ascii-pet-win.py via importlib (hyphen in filename)."""
        import importlib.util
        mod_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin', 'ascii-pet-win.py')
        spec = importlib.util.spec_from_file_location('ascii_pet_win', mod_path)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_lang_zh_id_exists(self):
        """ID_LANG_ZH is defined as an integer."""
        assert isinstance(self.mod.ID_LANG_ZH, int)

    def test_lang_en_id_exists(self):
        """ID_LANG_EN is defined as an integer."""
        assert isinstance(self.mod.ID_LANG_EN, int)

    def test_lang_ids_are_distinct(self):
        """ID_LANG_ZH and ID_LANG_EN are different values."""
        assert self.mod.ID_LANG_ZH != self.mod.ID_LANG_EN

    def test_lang_ids_do_not_conflict_with_existing(self):
        """Language IDs don't conflict with existing menu IDs."""
        existing_ids = {
            self.mod.ID_FEED, self.mod.ID_PLAY, self.mod.ID_SLEEP,
            self.mod.ID_ADOPT, self.mod.ID_PREV_PET, self.mod.ID_NEXT_PET,
            self.mod.ID_EXPORT, self.mod.ID_COMPACT, self.mod.ID_EXPANDED,
            self.mod.ID_STATS, self.mod.ID_ACHIEVE, self.mod.ID_ITEMS,
            self.mod.ID_LAN, self.mod.ID_QUIT,
        }
        assert self.mod.ID_LANG_ZH not in existing_ids
        assert self.mod.ID_LANG_EN not in existing_ids

    def test_mf_popup_constant_exists(self):
        """MF_POPUP constant is defined for submenu creation."""
        assert hasattr(self.mod, 'MF_POPUP')
        assert isinstance(self.mod.MF_POPUP, int)


class TestLanguageSwitchIntegration:
    """Test that switching language affects all text output."""

    def test_switch_to_chinese_affects_translation(self):
        i18n.set_language('zh')
        assert i18n._('Already full!') == '已经吃饱了！'

    def test_switch_to_english_affects_translation(self):
        i18n.set_language('en')
        assert i18n._('Already full!') == 'Already full!'

    def test_switch_back_and_forth(self):
        i18n.set_language('en')
        assert i18n._('Already full!') == 'Already full!'
        i18n.set_language('zh')
        assert i18n._('Already full!') == '已经吃饱了！'
        i18n.set_language('en')
        assert i18n._('Already full!') == 'Already full!'


class TestPetGameLanguageInit:
    """Test that PetGame initializes language from settings."""

    def test_petgame_init_loads_language(self, tmp_path):
        """PetGame.__init__ calls init_language to load saved preference."""
        # Save Chinese preference
        i18n.set_language('zh')
        i18n.save_settings(data_dir=str(tmp_path))
        # Reset to English
        i18n.set_language('en')
        # Create PetGame - should load Chinese
        from ascii_pet.core import PetGame
        game = PetGame('test-lang-init', data_dir=tmp_path)
        assert i18n.get_language() == 'zh'


class TestLanguageMenuCommand:
    """Test language menu command handling in execute_menu_command."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        """Load ascii-pet-win.py via importlib."""
        import importlib.util
        mod_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin', 'ascii-pet-win.py')
        spec = importlib.util.spec_from_file_location('ascii_pet_win', mod_path)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.PetWindow = self.mod.PetWindow
        self.ID_LANG_ZH = self.mod.ID_LANG_ZH
        self.ID_LANG_EN = self.mod.ID_LANG_EN

    def _make_pet_window(self):
        """Create a PetWindow with a mocked game."""
        game = MagicMock()
        game.message = None
        game.message_time = 0
        return self.PetWindow(game)

    def test_lang_zh_sets_language(self):
        """ID_LANG_ZH command sets language to Chinese."""
        i18n.set_language('en')
        pw = self._make_pet_window()
        with patch.object(self.mod, 'save_settings') as mock_save, \
             patch.object(self.mod.user32, 'InvalidateRect'):
            pw.execute_menu_command(self.ID_LANG_ZH)
        assert i18n.get_language() == 'zh'
        mock_save.assert_called_once()

    def test_lang_en_sets_language(self):
        """ID_LANG_EN command sets language to English."""
        i18n.set_language('zh')
        pw = self._make_pet_window()
        with patch.object(self.mod, 'save_settings') as mock_save, \
             patch.object(self.mod.user32, 'InvalidateRect'):
            pw.execute_menu_command(self.ID_LANG_EN)
        assert i18n.get_language() == 'en'
        mock_save.assert_called_once()

    def test_lang_zh_sets_message(self):
        """ID_LANG_ZH command sets a confirmation message."""
        i18n.set_language('en')
        pw = self._make_pet_window()
        with patch.object(self.mod, 'save_settings'), \
             patch.object(self.mod.user32, 'InvalidateRect'):
            pw.execute_menu_command(self.ID_LANG_ZH)
        assert pw.game.message is not None

    def test_lang_en_sets_message(self):
        """ID_LANG_EN command sets a confirmation message."""
        i18n.set_language('zh')
        pw = self._make_pet_window()
        with patch.object(self.mod, 'save_settings'), \
             patch.object(self.mod.user32, 'InvalidateRect'):
            pw.execute_menu_command(self.ID_LANG_EN)
        assert pw.game.message is not None


class TestLanguageMenuTranslations:
    """Test that new language menu strings are translatable."""

    def test_language_label_zh(self):
        """'Language' menu label is translated in Chinese."""
        i18n.set_language('zh')
        result = i18n._('Language')
        assert result != 'Language' or result == '语言/Language'

    def test_language_changed_to_chinese_zh(self):
        """'Language changed to Chinese' is translated in Chinese."""
        i18n.set_language('zh')
        result = i18n._('Language changed to Chinese')
        # Should not return the English key unchanged
        assert result == '已切换为中文'

    def test_language_changed_to_english_zh(self):
        """'Language changed to English' is translated in Chinese."""
        i18n.set_language('zh')
        result = i18n._('Language changed to English')
        assert result == '已切换为英文'

    def test_language_changed_to_chinese_en(self):
        """'Language changed to Chinese' in English."""
        i18n.set_language('en')
        assert i18n._('Language changed to Chinese') == 'Language changed to Chinese'

    def test_language_changed_to_english_en(self):
        """'Language changed to English' in English."""
        i18n.set_language('en')
        assert i18n._('Language changed to English') == 'Language changed to English'
