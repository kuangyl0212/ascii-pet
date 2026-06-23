#!/usr/bin/env python3
"""pytest tests for persistence functions in pet_core.py.

Covers SubTasks 7.1-7.9:
  7.1 save_pets/load_pets round-trip consistency
  7.2 load_pets legacy list format compatibility
  7.3 load_pets single-pet (bare dict) legacy format
  7.4 load_pets auto-fills missing inventory field
  7.5 load_pets returns None when file does not exist
  7.6 get_state_path determinism and directory auto-creation
  7.7 load_state falls back to index 0 when current is out of range
  7.8 save_state updates the specified index
  7.9 _default_data_dir platform branches (nt vs posix)
"""

import sys
import os
import json
import time
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet import core as pet_core


def _make_state(name='Test', species='cat'):
    """Build a minimal but realistic pet state dict for tests."""
    return {
        'user_id': 'test-uid',
        'name': name,
        'species': species,
        'rarity': 'common',
        'eye': '·',
        'hat': 'none',
        'shiny': False,
        'stats': {
            'HUNGER': 50,
            'HAPPY': 50,
            'ENERGY': 50,
            'WISDOM': 50,
            'CHAOS': 50,
        },
        'mood': 'normal',
        'created_at': '2026-01-01T00:00:00',
        'last_fed': '2026-01-01T00:00:00',
        'last_played': '2026-01-01T00:00:00',
        'last_slept': '2026-01-01T00:00:00',
        'level': 1,
        'xp': 0,
        'total_interactions': 0,
        'feed_count': 0,
        'play_count': 0,
        'sleep_count': 0,
        'achievements': [],
        'critical_since': None,
        'is_dead': False,
    }


def _unique_uid(prefix='test-persist'):
    """Generate a unique uid to avoid state file collisions across tests."""
    return f'{prefix}-{int(time.time() * 1000000)}'


@pytest.fixture
def data_dir(tmp_path):
    """Provide a fresh temp data dir for each test (auto-cleaned by tmp_path)."""
    return tmp_path


@pytest.fixture
def uid():
    """Provide a unique uid for each test."""
    return _unique_uid('persist')


# ─── 7.1: save_pets/load_pets round-trip consistency ─────────────────────────

def test_save_load_round_trip_preserves_data(data_dir, uid):
    state1 = _make_state(name='Alpha', species='cat')
    state2 = _make_state(name='Beta', species='duck')
    pets_data = {
        'pets': [state1, state2],
        'current': 1,
        'inventory': {'apple': 2},
    }
    pet_core.save_pets(uid, pets_data, data_dir)
    loaded = pet_core.load_pets(uid, data_dir)

    assert loaded is not None
    assert loaded['current'] == 1
    assert loaded['inventory'] == {'apple': 2}
    assert len(loaded['pets']) == 2
    assert loaded['pets'][0]['name'] == 'Alpha'
    assert loaded['pets'][1]['name'] == 'Beta'
    assert loaded['pets'][0]['species'] == 'cat'
    assert loaded['pets'][1]['species'] == 'duck'
    assert loaded['pets'][0]['stats']['HUNGER'] == 50
    assert loaded['pets'][1]['stats']['CHAOS'] == 50


# ─── 7.2-7.4: load_pets legacy format handling ───────────────────────────────

@pytest.mark.parametrize(
    "raw_data,expected",
    [
        # 7.2: legacy list format
        (
            [_make_state('Alpha', 'cat'), _make_state('Beta', 'duck')],
            {'count': 2, 'current': 0, 'inventory': {},
             'names': ['Alpha', 'Beta']},
        ),
        # 7.3: single dict (bare pet) legacy format
        (
            _make_state('Solo', 'blob'),
            {'count': 1, 'current': 0, 'inventory': {},
             'names': ['Solo'], 'species': ['blob']},
        ),
        # 7.4: dict without inventory key
        (
            {'pets': [_make_state('NoInv', 'owl')], 'current': 0},
            {'count': 1, 'current': 0, 'inventory': {},
             'names': ['NoInv'], 'check_inventory_key': True},
        ),
    ],
    ids=['legacy_list', 'single_dict', 'no_inventory'],
)
def test_load_pets_legacy_formats(data_dir, uid, raw_data, expected):
    path = pet_core.get_state_path(uid, data_dir)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw_data, f)

    loaded = pet_core.load_pets(uid, data_dir)

    assert loaded is not None
    assert len(loaded['pets']) == expected['count']
    assert loaded['current'] == expected['current']
    assert loaded['inventory'] == expected['inventory']
    for i, name in enumerate(expected['names']):
        assert loaded['pets'][i]['name'] == name
    if 'species' in expected:
        for i, sp in enumerate(expected['species']):
            assert loaded['pets'][i]['species'] == sp
    if expected.get('check_inventory_key'):
        assert 'inventory' in loaded


# ─── 7.5: load_pets returns None when file does not exist ────────────────────

def test_load_returns_none_when_no_file(data_dir, uid):
    loaded = pet_core.load_pets(uid, data_dir)
    assert loaded is None


# ─── 7.6: get_state_path determinism and directory auto-creation ─────────────

def test_path_is_deterministic_for_same_uid(data_dir, uid):
    p1 = pet_core.get_state_path(uid, data_dir)
    p2 = pet_core.get_state_path(uid, data_dir)
    assert p1 == p2


def test_path_filename_is_hash_hex_8(data_dir, uid):
    p = pet_core.get_state_path(uid, data_dir)
    expected_name = f'{pet_core.hash_string(uid) & 0xFFFFFFFF:08x}.json'
    assert p.name == expected_name


def test_path_creates_missing_data_dir(data_dir, uid):
    nested = data_dir / 'nested' / 'deeper'
    assert not nested.exists()
    p = pet_core.get_state_path(uid, nested)
    assert nested.exists()
    assert p.parent.exists()


def test_path_distinct_for_distinct_uids(data_dir):
    uid_a = _unique_uid('persist-path-a')
    uid_b = _unique_uid('persist-path-b')
    pa = pet_core.get_state_path(uid_a, data_dir)
    pb = pet_core.get_state_path(uid_b, data_dir)
    assert pa != pb


# ─── 7.7: load_state falls back to index 0 when current is out of range ──────

def test_load_state_falls_back_to_zero(data_dir, uid):
    s1 = _make_state(name='Only', species='cat')
    data = {'pets': [s1], 'current': 5}
    pet_core.save_pets(uid, data, data_dir)

    state, loaded_data, idx = pet_core.load_state(uid, data_dir)

    assert state is not None
    assert loaded_data is not None
    assert idx == 0
    assert state['name'] == 'Only'
    assert loaded_data['current'] == 5  # original data preserved


# ─── 7.8: save_state updates the specified index ─────────────────────────────

def test_save_state_updates_target_index(data_dir, uid):
    s1 = _make_state(name='Alpha', species='cat')
    s2 = _make_state(name='Beta', species='duck')
    data = {'pets': [s1, s2], 'current': 0}
    pet_core.save_pets(uid, data, data_dir)

    # Modify s1 and save at index 0.
    modified_s1 = dict(s1)
    modified_s1['name'] = 'AlphaPrime'
    modified_s1['stats'] = dict(s1['stats'])
    modified_s1['stats']['HUNGER'] = 99
    pet_core.save_state(uid, modified_s1, data, 0, data_dir)

    # Reload and verify the modification persisted at index 0.
    loaded_state, loaded_data, idx = pet_core.load_state(uid, data_dir)
    assert idx == 0
    assert loaded_state['name'] == 'AlphaPrime'
    assert loaded_state['stats']['HUNGER'] == 99
    # Index 1 should remain untouched.
    assert loaded_data['pets'][1]['name'] == 'Beta'
    assert loaded_data['pets'][1]['stats']['HUNGER'] == 50


# ─── 7.9: _default_data_dir platform branches ────────────────────────────────

def test_windows_branch_returns_appdata_ascii_pet():
    fake_appdata = 'C:\\Users\\TestUser\\AppData\\Roaming'
    with patch('os.name', 'nt'), \
         patch.dict(os.environ, {'APPDATA': fake_appdata}, clear=False):
        result = pet_core._default_data_dir()
        assert result == Path(fake_appdata) / 'ascii-pet'


def test_windows_branch_falls_back_to_home_when_no_appdata():
    fake_home = 'C:\\Users\\NoAppData'
    # Remove APPDATA to exercise the fallback inside the branch.
    env = {k: v for k, v in os.environ.items() if k != 'APPDATA'}
    env['USERPROFILE'] = fake_home
    with patch('os.name', 'nt'), \
         patch.dict(os.environ, env, clear=True), \
         patch.object(Path, 'home', return_value=Path(fake_home)):
        result = pet_core._default_data_dir()
        assert result == Path(fake_home) / 'AppData' / 'Roaming' / 'ascii-pet'


def test_posix_branch_returns_local_share_ascii_pet():
    fake_home = '/home/testuser'
    # Use PureWindowsPath for the mock return value and expected result:
    # PurePath subclasses do not check os.name in __new__, so the /
    # operator works even when os.name is patched to 'posix' on Windows.
    expected = PureWindowsPath(fake_home) / '.local' / 'share' / 'ascii-pet'
    with patch('os.name', 'posix'), \
         patch.object(Path, 'home', return_value=PureWindowsPath(fake_home)):
        result = pet_core._default_data_dir()
        assert result == expected
