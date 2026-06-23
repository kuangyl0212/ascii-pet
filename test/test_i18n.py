"""Tests for i18n.py — translation framework module.

TDD red phase: these tests define the expected behavior of the i18n module
before implementation exists.
"""
import json
import os
import tempfile
from pathlib import Path

import pytest

import i18n


class TestTranslateEnglish:
    """With language 'en', _() returns the original English text."""

    def test_already_full(self):
        i18n.set_language('en')
        assert i18n._('Already full!') == 'Already full!'

    def test_too_tired(self):
        i18n.set_language('en')
        assert i18n._('Too tired!') == 'Too tired!'

    def test_not_sleepy(self):
        i18n.set_language('en')
        assert i18n._('Not sleepy!') == 'Not sleepy!'


class TestTranslateChinese:
    """With language 'zh', _() returns the Chinese translation."""

    def test_already_full(self):
        i18n.set_language('zh')
        assert i18n._('Already full!') == '已经吃饱了！'

    def test_too_tired(self):
        i18n.set_language('zh')
        assert i18n._('Too tired!') == '太累了！'

    def test_not_sleepy(self):
        i18n.set_language('zh')
        assert i18n._('Not sleepy!') == '不想睡！'

    def test_achoo(self):
        i18n.set_language('zh')
        assert i18n._('Achoo!') == '阿嚏！'


class TestSetLanguageSwitches:
    """Setting language switches the active translation."""

    def test_switch_en_to_zh(self):
        i18n.set_language('en')
        assert i18n._('Already full!') == 'Already full!'
        i18n.set_language('zh')
        assert i18n._('Already full!') == '已经吃饱了！'

    def test_switch_zh_to_en(self):
        i18n.set_language('zh')
        assert i18n._('Already full!') == '已经吃饱了！'
        i18n.set_language('en')
        assert i18n._('Already full!') == 'Already full!'


class TestMissingTranslationFallback:
    """Untranslated strings fall back to the original text."""

    def test_untranslated_text_zh(self):
        i18n.set_language('zh')
        assert i18n._('some untranslated text') == 'some untranslated text'

    def test_untranslated_text_en(self):
        i18n.set_language('en')
        assert i18n._('some untranslated text') == 'some untranslated text'


class TestGetLanguage:
    """get_language() returns the current language code."""

    def test_after_set_zh(self):
        i18n.set_language('zh')
        assert i18n.get_language() == 'zh'

    def test_after_set_en(self):
        i18n.set_language('en')
        assert i18n.get_language() == 'en'

    def test_unsupported_language_falls_back(self):
        i18n.set_language('fr')
        assert i18n.get_language() == 'en'


class TestSaveAndLoadSettings:
    """Language preference persists to settings.json."""

    def test_save_and_load(self, tmp_path):
        i18n.set_language('zh')
        i18n.save_settings(data_dir=str(tmp_path))

        loaded = i18n.load_settings(data_dir=str(tmp_path))
        assert loaded == 'zh'

    def test_save_en_and_load(self, tmp_path):
        i18n.set_language('en')
        i18n.save_settings(data_dir=str(tmp_path))

        loaded = i18n.load_settings(data_dir=str(tmp_path))
        assert loaded == 'en'

    def test_settings_file_created(self, tmp_path):
        i18n.set_language('zh')
        i18n.save_settings(data_dir=str(tmp_path))

        settings_file = tmp_path / 'settings.json'
        assert settings_file.exists()
        data = json.loads(settings_file.read_text(encoding='utf-8'))
        assert data['language'] == 'zh'

    def test_load_nonexistent_returns_none(self, tmp_path):
        result = i18n.load_settings(data_dir=str(tmp_path / 'nonexistent'))
        assert result is None

    def test_load_invalid_json_returns_none(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text('not valid json{{{', encoding='utf-8')
        result = i18n.load_settings(data_dir=str(tmp_path))
        assert result is None

    def test_load_unsupported_language_returns_none(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({'language': 'xx'}), encoding='utf-8')
        result = i18n.load_settings(data_dir=str(tmp_path))
        assert result is None


class TestDefaultLanguageDetection:
    """When no settings exist, default language is inferred from system locale."""

    def test_detect_returns_supported_language(self):
        lang = i18n._detect_system_language()
        assert lang in i18n.SUPPORTED_LANGUAGES

    def test_init_language_no_settings(self, tmp_path):
        i18n.init_language(data_dir=str(tmp_path / 'nonexistent'))
        # Should not raise, and language should be valid
        assert i18n.get_language() in i18n.SUPPORTED_LANGUAGES


class TestSupportedLanguages:
    """SUPPORTED_LANGUAGES contains 'en' and 'zh'."""

    def test_contains_en(self):
        assert 'en' in i18n.SUPPORTED_LANGUAGES

    def test_contains_zh(self):
        assert 'zh' in i18n.SUPPORTED_LANGUAGES

    def test_at_least_two(self):
        assert len(i18n.SUPPORTED_LANGUAGES) >= 2
