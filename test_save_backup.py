#!/usr/bin/env python3
"""pytest tests for save backup functions in pet_core.py.

Covers:
  - validate_save_file: normal, corrupt JSON, missing pets field, file not found
  - create_backup: creates backup, filename format, max 10 cleanup
  - list_backups: sorted by mtime desc, empty when no backups
  - restore_from_backup: success, failure on missing backup
  - load_pets_with_fallback: normal load, corrupt fallback, no backup
  - PetGame.__init__: uses load_pets_with_fallback, auto-backup on daily login
"""

import sys
import os
import json
import time
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pet_core


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


def _unique_uid(prefix='test-backup'):
    """Generate a unique uid to avoid state file collisions across tests."""
    return f'{prefix}-{int(time.time() * 1000000)}'


def _make_pets_data(name='Test', species='cat'):
    """Build a minimal pets_data dict for tests."""
    return {
        'pets': [_make_state(name, species)],
        'current': 0,
        'inventory': {},
    }


@pytest.fixture
def data_dir(tmp_path):
    """Provide a fresh temp data dir for each test (auto-cleaned by tmp_path)."""
    return tmp_path


@pytest.fixture
def uid():
    """Provide a unique uid for each test."""
    return _unique_uid('backup')


# ─── validate_save_file ──────────────────────────────────────────────────────

class TestValidateSaveFile:
    def test_valid_file_returns_true(self, data_dir, uid):
        pets_data = _make_pets_data()
        path = pet_core.get_state_path(uid, data_dir)
        pet_core.save_pets(uid, pets_data, data_dir)
        assert pet_core.validate_save_file(path) is True

    def test_corrupt_json_returns_false(self, data_dir, uid):
        path = pet_core.get_state_path(uid, data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{not valid json!!!', encoding='utf-8')
        assert pet_core.validate_save_file(path) is False

    def test_missing_pets_field_returns_false(self, data_dir, uid):
        path = pet_core.get_state_path(uid, data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'current': 0, 'inventory': {}}, f)
        assert pet_core.validate_save_file(path) is False

    def test_nonexistent_file_returns_false(self, data_dir):
        path = data_dir / 'nonexistent.json'
        assert pet_core.validate_save_file(path) is False


# ─── create_backup ───────────────────────────────────────────────────────────

class TestCreateBackup:
    def test_creates_backup_file(self, data_dir, uid):
        pets_data = _make_pets_data()
        pet_core.save_pets(uid, pets_data, data_dir)
        backup_path = pet_core.create_backup(uid, data_dir)
        assert backup_path.exists()
        # Backup content should match original
        with open(backup_path, encoding='utf-8') as f:
            backup_data = json.load(f)
        assert 'pets' in backup_data
        assert backup_data['pets'][0]['name'] == 'Test'

    def test_filename_format(self, data_dir, uid):
        pets_data = _make_pets_data()
        pet_core.save_pets(uid, pets_data, data_dir)
        backup_path = pet_core.create_backup(uid, data_dir)
        h = f'{pet_core.hash_string(uid) & 0xFFFFFFFF:08x}'
        name = backup_path.name
        assert name.startswith(h + '_')
        assert name.endswith('.json')
        # Middle part should be YYYYMMDD_HHMMSS
        ts_part = name[len(h)+1:-5]  # strip hash_ prefix and .json suffix
        assert len(ts_part) == 15  # YYYYMMDD_HHMMSS
        assert ts_part[8] == '_'

    def test_max_10_backups_deletes_oldest(self, data_dir, uid):
        pets_data = _make_pets_data()
        pet_core.save_pets(uid, pets_data, data_dir)
        # Create 11 backups with mocked time to ensure unique filenames
        paths = []
        base_time = datetime(2026, 1, 1, 12, 0, 0)
        for i in range(11):
            fake_now = datetime.fromtimestamp(base_time.timestamp() + i * 60)
            with patch.object(pet_core, 'datetime') as mock_dt:
                mock_dt.now.return_value = fake_now
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                p = pet_core.create_backup(uid, data_dir)
            paths.append(p)
        # Only 10 should remain
        backup_dir = data_dir / 'backups'
        remaining = sorted(backup_dir.glob('*.json'))
        assert len(remaining) == 10
        # The first backup should have been deleted
        assert not paths[0].exists()
        # The second should still exist
        assert paths[1].exists()


# ─── list_backups ────────────────────────────────────────────────────────────

class TestListBackups:
    def test_returns_empty_when_no_backups(self, data_dir, uid):
        result = pet_core.list_backups(uid, data_dir)
        assert result == []

    def test_returns_sorted_by_mtime_desc(self, data_dir, uid):
        pets_data = _make_pets_data()
        pet_core.save_pets(uid, pets_data, data_dir)
        # Create 3 backups with controlled timestamps
        base_time = datetime(2026, 1, 1, 12, 0, 0)
        created_names = []
        for i in range(3):
            fake_now = datetime.fromtimestamp(base_time.timestamp() + i * 60)
            with patch.object(pet_core, 'datetime') as mock_dt:
                mock_dt.now.return_value = fake_now
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                p = pet_core.create_backup(uid, data_dir)
            created_names.append(p.name)

        result = pet_core.list_backups(uid, data_dir)
        assert len(result) == 3
        # Should be sorted by mtime descending (newest first)
        assert result[0][0] == created_names[2]
        assert result[1][0] == created_names[1]
        assert result[2][0] == created_names[0]
        # Each item should be (filename: str, timestamp: datetime)
        for filename, ts in result:
            assert isinstance(filename, str)
            assert isinstance(ts, datetime)


# ─── restore_from_backup ────────────────────────────────────────────────────

class TestRestoreFromBackup:
    def test_restore_success(self, data_dir, uid):
        pets_data = _make_pets_data(name='Original')
        pet_core.save_pets(uid, pets_data, data_dir)
        # Create a backup
        backup_path = pet_core.create_backup(uid, data_dir)
        # Modify the save file
        pets_data['pets'][0]['name'] = 'Modified'
        pet_core.save_pets(uid, pets_data, data_dir)
        # Restore from backup
        result = pet_core.restore_from_backup(uid, backup_path.name, data_dir)
        assert result is True
        # Verify the save file now has the original data
        loaded = pet_core.load_pets(uid, data_dir)
        assert loaded['pets'][0]['name'] == 'Original'

    def test_restore_nonexistent_returns_false(self, data_dir, uid):
        result = pet_core.restore_from_backup(uid, 'nonexistent.json', data_dir)
        assert result is False


# ─── load_pets_with_fallback ────────────────────────────────────────────────

class TestLoadPetsWithFallback:
    def test_normal_load_returns_ok(self, data_dir, uid):
        pets_data = _make_pets_data(name='Normal')
        pet_core.save_pets(uid, pets_data, data_dir)
        data, status = pet_core.load_pets_with_fallback(uid, data_dir)
        assert status == 'ok'
        assert data is not None
        assert data['pets'][0]['name'] == 'Normal'

    def test_no_file_returns_no_file(self, data_dir, uid):
        data, status = pet_core.load_pets_with_fallback(uid, data_dir)
        assert status == 'no_file'
        assert data is None

    def test_corrupt_with_backup_returns_restored(self, data_dir, uid):
        pets_data = _make_pets_data(name='GoodData')
        pet_core.save_pets(uid, pets_data, data_dir)
        # Create a backup of the good data
        pet_core.create_backup(uid, data_dir)
        # Corrupt the save file
        path = pet_core.get_state_path(uid, data_dir)
        path.write_text('{corrupt!!!', encoding='utf-8')
        # Fallback should restore from backup
        data, status = pet_core.load_pets_with_fallback(uid, data_dir)
        assert status == 'restored'
        assert data is not None
        assert data['pets'][0]['name'] == 'GoodData'

    def test_corrupt_no_backup_returns_corrupt_no_backup(self, data_dir, uid):
        # Create a corrupt save file with no backups
        path = pet_core.get_state_path(uid, data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{corrupt!!!', encoding='utf-8')
        data, status = pet_core.load_pets_with_fallback(uid, data_dir)
        assert status == 'corrupt_no_backup'
        assert data is None


# ─── PetGame.__init__ integration ───────────────────────────────────────────

class TestPetGameInitBackup:
    def test_restored_status_sets_message(self, data_dir, uid):
        """When save is corrupt but backup exists, PetGame shows restored message."""
        pets_data = _make_pets_data(name='GoodPet')
        pet_core.save_pets(uid, pets_data, data_dir)
        # Create a backup
        pet_core.create_backup(uid, data_dir)
        # Corrupt the save file
        path = pet_core.get_state_path(uid, data_dir)
        path.write_text('{corrupt!!!', encoding='utf-8')
        game = pet_core.PetGame(uid, data_dir)
        assert game.message == '存档损坏，已从备份恢复'

    def test_corrupt_no_backup_creates_new_save(self, data_dir, uid):
        """When save is corrupt and no backup, PetGame creates new save with message."""
        # Create a corrupt save file with no backups
        path = pet_core.get_state_path(uid, data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{corrupt!!!', encoding='utf-8')
        game = pet_core.PetGame(uid, data_dir)
        assert game.message == '存档损坏且无备份，已创建新存档'
        # Should have a new pet
        assert game.state is not None
        assert game.pets_data is not None
        assert len(game.pets_data['pets']) >= 1

    def test_auto_backup_on_daily_login(self, data_dir, uid):
        """When last_login date changes, create_backup is called before save."""
        pets_data = _make_pets_data(name='DailyPet')
        pets_data['last_login'] = '2026-01-01'  # old date
        pet_core.save_pets(uid, pets_data, data_dir)
        game = pet_core.PetGame(uid, data_dir)
        # A backup should have been created
        backups = pet_core.list_backups(uid, data_dir)
        assert len(backups) >= 1
