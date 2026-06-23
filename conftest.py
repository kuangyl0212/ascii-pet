"""Shared pytest fixtures for all test modules.

Ensures the i18n language is set to English before each test,
so that tests asserting English strings work regardless of system locale.
"""
from unittest.mock import patch

import pytest
import i18n


@pytest.fixture(autouse=True)
def _set_english_language():
    """Reset language to English before each test.

    PetGame.__init__ calls init_language(), which may detect a Chinese
    system locale and switch to Chinese. This fixture patches
    _detect_system_language to return 'en' so that init_language()
    without saved settings defaults to English instead of the system locale.
    """
    i18n.set_language('en')
    with patch.object(i18n, '_detect_system_language', return_value='en'):
        yield
