"""Internationalization module for ASCII Desktop Pet.

Uses Python standard library gettext for translation.
Supports runtime language switching and preference persistence.
"""
import gettext
import json
import locale
import os
import sys
from pathlib import Path

SUPPORTED_LANGUAGES = ['en', 'zh']
_current_translation = gettext.NullTranslations()
_current_language = 'en'


def _get_locales_dir():
    """Return the path to the locales directory.

    When running from PyInstaller bundle (sys._MEIPASS), locales are
    extracted to the temp dir alongside the main script.
    When running as a plain script, locales are next to i18n.py.
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle: locales are in the _MEIPASS temp dir
        return Path(sys._MEIPASS) / 'locales'
    return Path(__file__).parent / 'locales'


def _detect_system_language():
    """Detect system language and return 'zh' or 'en'."""
    import warnings
    # locale.getlocale() is the preferred API (getdefaultlocale deprecated in 3.15+)
    try:
        result = locale.getlocale()
        lang = result[0] if result else None
        if lang and lang.startswith('zh'):
            return 'zh'
    except Exception:
        pass
    # Fallback for environments where getlocale() returns None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            getter = getattr(locale, 'getdefaultlocale', None)
            if getter:
                result = getter()
                lang = result[0] if result else None
                if lang and lang.startswith('zh'):
                    return 'zh'
    except Exception:
        pass
    try:
        lang = os.environ.get('LANG', '')
        if lang.startswith('zh'):
            return 'zh'
    except Exception:
        pass
    return 'en'


def set_language(lang):
    """Set the current language and reload translations."""
    global _current_translation, _current_language
    if lang not in SUPPORTED_LANGUAGES:
        lang = 'en'
    _current_language = lang
    locales_dir = _get_locales_dir()
    try:
        translation = gettext.translation(
            'ascii_pet', localedir=str(locales_dir), languages=[lang]
        )
        _current_translation = translation
    except FileNotFoundError:
        print(f"[i18n] WARNING: Translation file not found for '{lang}' in {locales_dir}", file=sys.stderr)
        _current_translation = gettext.NullTranslations()
    except Exception as e:
        print(f"[i18n] WARNING: Failed to load translation for '{lang}': {e}", file=sys.stderr)
        _current_translation = gettext.NullTranslations()


def get_language():
    """Return the current language code."""
    return _current_language


def _(message):
    """Translate a message string."""
    return _current_translation.gettext(message)


def _get_settings_path(data_dir=None):
    """Return the path to settings.json."""
    if data_dir is None:
        if os.name == 'nt':
            data_dir = Path(os.environ.get(
                'APPDATA', str(Path.home() / 'AppData' / 'Roaming')
            )) / 'ascii-pet'
        else:
            data_dir = Path.home() / '.local' / 'share' / 'ascii-pet'
    return Path(data_dir) / 'settings.json'


def save_settings(data_dir=None):
    """Save current language preference to settings.json."""
    settings_path = _get_settings_path(data_dir)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            settings = {}
    settings['language'] = _current_language
    settings_path.write_text(json.dumps(settings, indent=2), encoding='utf-8')


def load_settings(data_dir=None):
    """Load language preference from settings.json. Returns language code or None."""
    settings_path = _get_settings_path(data_dir)
    if not settings_path.exists():
        return None
    try:
        settings = json.loads(settings_path.read_text(encoding='utf-8'))
        lang = settings.get('language')
        if lang in SUPPORTED_LANGUAGES:
            return lang
    except (json.JSONDecodeError, OSError):
        pass
    return None


def init_language(data_dir=None):
    """Initialize language from settings or system detection."""
    saved = load_settings(data_dir)
    if saved:
        set_language(saved)
    else:
        set_language(_detect_system_language())


# Initialize with English by default (will be overridden by init_language in PetGame)
set_language('en')
