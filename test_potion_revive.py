#!/usr/bin/env python3
"""TDD RED phase: Tests for potion-only revive.

Dead pets can only be revived by using a Potion item.
feed/play/sleep should NOT revive dead pets anymore.

Run: python -m pytest test_potion_revive.py -v
"""

from pathlib import Path
import tempfile
import time
import shutil

import pytest

from pet_core import PetGame


@pytest.fixture
def game():
    """Create a PetGame instance with a dead pet for testing."""
    tmpdir = Path(tempfile.mkdtemp())
    uid = f'test-revive-{int(time.time() * 1000000)}'
    g = PetGame(uid, data_dir=tmpdir)
    g.state['is_dead'] = True
    g.state['critical_since'] = time.time()
    yield g
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def game_alive():
    """Create a PetGame instance with an alive pet for testing."""
    tmpdir = Path(tempfile.mkdtemp())
    uid = f'test-revive-alive-{int(time.time() * 1000000)}'
    g = PetGame(uid, data_dir=tmpdir)
    g.state['is_dead'] = False
    yield g
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestDeadPetFeedPlaySleep:
    """Tests that feed/play/sleep do NOT revive dead pets."""

    def test_dead_feed_no_revive(self, game):
        msg, _ = game.handle_action('feed')
        assert game.state['is_dead'] is True
        assert msg == 'Your pet is dead... Use a Potion to revive!'

    def test_dead_play_no_revive(self, game):
        msg, _ = game.handle_action('play')
        assert game.state['is_dead'] is True
        assert msg == 'Your pet is dead... Use a Potion to revive!'

    def test_dead_sleep_no_revive(self, game):
        msg, _ = game.handle_action('sleep')
        assert game.state['is_dead'] is True
        assert msg == 'Your pet is dead... Use a Potion to revive!'


class TestDeadPetKeyHandling:
    """Tests that f/p/s keys don't revive dead pets."""

    def test_dead_f_key_no_revive(self, game):
        game.handle_key('f')
        assert game.state['is_dead'] is True
        assert 'Potion' in game.message

    def test_dead_p_key_no_revive(self, game):
        game.handle_key('p')
        assert game.state['is_dead'] is True
        assert 'Potion' in game.message

    def test_dead_s_key_no_revive(self, game):
        game.handle_key('s')
        assert game.state['is_dead'] is True
        assert 'Potion' in game.message


class TestPotionReviveStillWorks:
    """Tests that Potion revive still works (and is rejected when alive)."""

    def test_potion_revives_dead_pet(self, game):
        game.pets_data.setdefault('inventory', {})['potion'] = 1
        result = game.use_item('potion')
        assert game.state['is_dead'] is False
        assert game.state['stats']['HUNGER'] == 25
        assert game.state['stats']['ENERGY'] == 25
        assert game.state['stats']['HAPPY'] == 25
        assert 'Potion' in result or 'Used' in result

    def test_potion_rejected_when_alive(self, game_alive):
        game_alive.pets_data.setdefault('inventory', {})['potion'] = 1
        result = game_alive.use_item('potion')
        assert result == 'Pet is not dead!'
