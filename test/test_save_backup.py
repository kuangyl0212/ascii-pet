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
        # New format: {hash}_{type}_YYYYMMDD_HHMMSS.json
        # Middle part after hash_ and before .json should be {type}_YYYYMMDD_HHMMSS
        middle = name[len(h)+1:-5]  # strip hash_ prefix and .json suffix
        parts = middle.split('_', 1)  # split into type and timestamp
        assert len(parts) == 2
        assert parts[0] in ('auto', 'manual')
        ts_part = parts[1]
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
        # Each item should be (filename: str, timestamp: datetime, backup_type: str)
        for filename, ts, backup_type in result:
            assert isinstance(filename, str)
            assert isinstance(ts, datetime)
            assert backup_type in ('auto', 'manual')


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
        assert game.message == 'Save corrupted, restored from backup'

    def test_corrupt_no_backup_creates_new_save(self, data_dir, uid):
        """When save is corrupt and no backup, PetGame creates new save with message."""
        # Create a corrupt save file with no backups
        path = pet_core.get_state_path(uid, data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{corrupt!!!', encoding='utf-8')
        game = pet_core.PetGame(uid, data_dir)
        assert game.message == 'Save corrupted with no backup, created new save'
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


# ─── create_backup backup_type ──────────────────────────────────────────────

class TestCreateBackupType:
    def test_create_backup_auto_type_in_filename(self, data_dir, uid):
        """create_backup with backup_type='auto' includes 'auto' in filename."""
        pets_data = _make_pets_data()
        pet_core.save_pets(uid, pets_data, data_dir)
        backup_path = pet_core.create_backup(uid, data_dir, backup_type='auto')
        h = f'{pet_core.hash_string(uid) & 0xFFFFFFFF:08x}'
        name = backup_path.name
        # Format: {hash}_auto_YYYYMMDD_HHMMSS.json
        middle = name[len(h)+1:-5]
        parts = middle.split('_', 1)
        assert parts[0] == 'auto'

    def test_create_backup_manual_type_in_filename(self, data_dir, uid):
        """create_backup with backup_type='manual' includes 'manual' in filename."""
        pets_data = _make_pets_data()
        pet_core.save_pets(uid, pets_data, data_dir)
        backup_path = pet_core.create_backup(uid, data_dir, backup_type='manual')
        h = f'{pet_core.hash_string(uid) & 0xFFFFFFFF:08x}'
        name = backup_path.name
        # Format: {hash}_manual_YYYYMMDD_HHMMSS.json
        middle = name[len(h)+1:-5]
        parts = middle.split('_', 1)
        assert parts[0] == 'manual'

    def test_create_backup_default_type_is_auto(self, data_dir, uid):
        """create_backup without backup_type defaults to 'auto'."""
        pets_data = _make_pets_data()
        pet_core.save_pets(uid, pets_data, data_dir)
        backup_path = pet_core.create_backup(uid, data_dir)
        h = f'{pet_core.hash_string(uid) & 0xFFFFFFFF:08x}'
        name = backup_path.name
        middle = name[len(h)+1:-5]
        parts = middle.split('_', 1)
        assert parts[0] == 'auto'


# ─── list_backups with backup_type ──────────────────────────────────────────

class TestListBackupsType:
    def test_list_backups_returns_type(self, data_dir, uid):
        """list_backups returns 3-tuples with backup_type as third element."""
        pets_data = _make_pets_data()
        pet_core.save_pets(uid, pets_data, data_dir)
        pet_core.create_backup(uid, data_dir, backup_type='auto')
        result = pet_core.list_backups(uid, data_dir)
        assert len(result) == 1
        filename, ts, backup_type = result[0]
        assert isinstance(filename, str)
        assert isinstance(ts, datetime)
        assert backup_type == 'auto'

    def test_list_backups_distinguishes_auto_and_manual(self, data_dir, uid):
        """list_backups correctly distinguishes auto and manual backups."""
        pets_data = _make_pets_data()
        pet_core.save_pets(uid, pets_data, data_dir)
        base_time = datetime(2026, 1, 1, 12, 0, 0)
        # Create an auto backup
        fake_now = datetime.fromtimestamp(base_time.timestamp())
        with patch.object(pet_core, 'datetime') as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            pet_core.create_backup(uid, data_dir, backup_type='auto')
        # Create a manual backup 1 minute later
        fake_now2 = datetime.fromtimestamp(base_time.timestamp() + 60)
        with patch.object(pet_core, 'datetime') as mock_dt:
            mock_dt.now.return_value = fake_now2
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            pet_core.create_backup(uid, data_dir, backup_type='manual')
        result = pet_core.list_backups(uid, data_dir)
        assert len(result) == 2
        # Newest first (manual), then auto
        assert result[0][2] == 'manual'
        assert result[1][2] == 'auto'

    def test_list_backups_parses_old_format_as_auto(self, data_dir, uid):
        """Old format backups (without type) are parsed as 'auto' for compatibility."""
        pets_data = _make_pets_data()
        pet_core.save_pets(uid, pets_data, data_dir)
        # Manually create an old-format backup file: {hash}_YYYYMMDD_HHMMSS.json
        h = f'{pet_core.hash_string(uid) & 0xFFFFFFFF:08x}'
        backup_dir = data_dir / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        old_backup = backup_dir / f'{h}_20260101_120000.json'
        shutil.copy2(pet_core.get_state_path(uid, data_dir), old_backup)
        result = pet_core.list_backups(uid, data_dir)
        assert len(result) == 1
        assert result[0][2] == 'auto'  # old format defaults to 'auto'


# ─── restore_from_backup pre-restore backup ─────────────────────────────────

class TestRestorePreBackup:
    def test_restore_creates_pre_restore_backup(self, data_dir, uid):
        """restore_from_backup creates a backup of current state before restoring."""
        pets_data = _make_pets_data(name='Original')
        pet_core.save_pets(uid, pets_data, data_dir)
        # Create a backup of the original data
        backup_path = pet_core.create_backup(uid, data_dir, backup_type='manual')
        # Modify the save file
        pets_data['pets'][0]['name'] = 'Modified'
        pet_core.save_pets(uid, pets_data, data_dir)
        # Before restore, there should be 1 backup
        assert len(pet_core.list_backups(uid, data_dir)) == 1
        # Restore from backup
        result = pet_core.restore_from_backup(uid, backup_path.name, data_dir)
        assert result is True
        # After restore, there should be 2 backups (original + pre-restore auto)
        backups = pet_core.list_backups(uid, data_dir)
        assert len(backups) == 2
        # The pre-restore backup should be of type 'auto'
        backup_types = [b[2] for b in backups]
        assert 'auto' in backup_types
