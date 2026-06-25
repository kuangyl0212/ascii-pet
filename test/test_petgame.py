#!/usr/bin/env python3
"""Pytest tests for PetGame class in pet_core.py.

Covers SubTask 9.1-9.66: all public methods of PetGame.
Uses temp directories for isolation; no network.
"""

import os
import sys
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet import core as pet_core
from ascii_pet.core import (
    PetGame, MAX_PETS, MAX_DAILY_ADOPTIONS, MAX_INVENTORY,
    ITEMS, STAT_NAMES, RANDOM_EVENTS, PET_INTERACTIONS,
    init_state, generate_companion, generate_name,
)


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-game-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


@pytest.fixture
def game(tmp_path):
    """Provide a fresh PetGame with isolated temp dir."""
    uid = _uid()
    return PetGame(uid, data_dir=tmp_path)


def _add_second_pet(game):
    """Helper: add a second pet to the game for multi-pet tests."""
    game.pets_data['pets'][game.pet_idx] = game.state
    bones = generate_companion(game.uid + '-2')
    new_state = init_state(game.uid + '-2', bones, 'SecondPet')
    game.pets_data['pets'].append(new_state)
    game.save()


# ─── TestPetGameInit (9.1-9.3) ───────────────────────────────────────────────


class TestPetGameInit:
    """SubTask 9.1-9.3: __init__ behavior."""

    def test_init_new_user_generates_pet(self, tmp_path):
        """9.1: New user auto-generates a pet."""
        uid = _uid()
        game = PetGame(uid, data_dir=tmp_path)
        assert game.state is not None
        assert len(game.pets_data['pets']) == 1
        assert game.pet_idx == 0
        assert 'name' in game.state
        assert 'stats' in game.state

    def test_init_loads_existing_state(self, tmp_path):
        """9.2: Loading existing save."""
        uid = _uid()
        game1 = PetGame(uid, data_dir=tmp_path)
        game1.state['name'] = 'ModifiedName'
        game1.save()
        # Create new game with same uid - should load modified state
        game2 = PetGame(uid, data_dir=tmp_path)
        assert game2.state['name'] == 'ModifiedName'

    def test_init_daily_login_bonus(self, tmp_path):
        """9.3: Daily login bonus adds an item on first login."""
        uid = _uid()
        game = PetGame(uid, data_dir=tmp_path)
        today = datetime.now().date().isoformat()
        assert game.pets_data.get('last_login') == today
        # Daily bonus should have added exactly 1 item type to inventory
        inv = game.pets_data.get('inventory', {})
        assert sum(inv.values()) == 1
        assert game.message is not None
        assert 'Daily bonus' in game.message


# ─── TestSaveAndCount (9.4-9.6) ──────────────────────────────────────────────


class TestSaveAndCount:
    """SubTask 9.4-9.6: save and count_today_adoptions."""

    def test_save_persists_state(self, game):
        """9.4: save() persists state changes."""
        game.state['name'] = 'SavedName'
        game.save()
        # Reload via new instance
        game2 = PetGame(game.uid, data_dir=game.data_dir)
        assert game2.state['name'] == 'SavedName'

    def test_count_today_adoptions_only_today(self, game):
        """9.5: count_today_adoptions counts only today's adoptions."""
        today = datetime.now().isoformat()
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        game.pets_data['adoption_log'] = [today, today, yesterday]
        assert game.count_today_adoptions() == 2

    def test_count_today_adoptions_ignores_invalid(self, game):
        """9.6: Invalid timestamps are ignored without error."""
        game.pets_data['adoption_log'] = ['invalid', 'not-a-date', '', datetime.now().isoformat()]
        assert game.count_today_adoptions() == 1


# ─── TestTick (9.7-9.18) ─────────────────────────────────────────────────────


class TestTick:
    """SubTask 9.7-9.18: tick() behavior."""

    def test_tick_dead_state_returns_none(self, game):
        """9.7: Dead pets return (None, 0)."""
        game.state['is_dead'] = True
        msg, t = game.tick()
        assert msg is None
        assert t == 0

    def test_tick_decay_accumulation(self, game):
        """9.8: Decay accumulates over multiple ticks."""
        # Set last_fed to 4 hours ago (past 3h threshold)
        game.state['last_fed'] = (datetime.now() - timedelta(hours=4)).isoformat()
        game.state['stats']['HUNGER'] = 80
        initial_hunger = game.state['stats']['HUNGER']
        # Force a large delta by setting last_tick_time to the past
        game.last_tick_time = time.time() - 3600  # 1 hour ago
        game.tick()
        assert game.state['stats']['HUNGER'] < initial_hunger

    def test_tick_mood_calculation(self, game):
        """9.9: tick() updates mood based on stats."""
        game.state['stats']['HUNGER'] = 10
        game.state['stats']['ENERGY'] = 50
        game.state['stats']['HAPPY'] = 50
        game.tick()
        assert game.state['mood'] == 'hungry'

    def test_tick_single_stat_zero_critical(self, game):
        """9.10: Single stat at zero triggers critical warning (no death countdown)."""
        game.state['stats']['HUNGER'] = 0
        game.state['stats']['ENERGY'] = 50
        game.state['stats']['HAPPY'] = 50
        game.state['critical_since'] = None
        game.last_event_time = time.time()  # prevent random event override
        msg, t = game.tick()
        assert game.state.get('critical_since') is None  # countdown only starts when all zero
        assert game.warning_active
        assert 'CRITICAL' in msg

    def test_tick_all_stats_zero_critical(self, game):
        """9.11: All stats at zero triggers all-zero critical warning."""
        game.state['stats']['HUNGER'] = 0
        game.state['stats']['ENERGY'] = 0
        game.state['stats']['HAPPY'] = 0
        game.state['critical_since'] = None
        game.last_event_time = time.time()  # prevent random event override
        msg, t = game.tick()
        assert 'All stats at zero' in msg

    def test_tick_single_stat_zero_15min_not_dead(self, game):
        """9.12: Single stat zero no longer causes death (only all-zero kills)."""
        game.state['stats']['HUNGER'] = 0
        game.state['stats']['ENERGY'] = 50
        game.state['stats']['HAPPY'] = 50
        game.state['critical_since'] = (datetime.now() - timedelta(seconds=901)).isoformat()
        msg, t = game.tick()
        assert not game.state['is_dead']

    def test_tick_single_stat_zero_long_time_not_dead(self, game):
        """Single stat zero for 24h does not cause death; only all-zero kills."""
        game.state['stats']['HUNGER'] = 0
        game.state['stats']['ENERGY'] = 50
        game.state['stats']['HAPPY'] = 50
        game.state['critical_since'] = (datetime.now() - timedelta(hours=24)).isoformat()
        msg, t = game.tick()
        assert not game.state['is_dead']

    def test_tick_all_stats_zero_under_1hour_not_dead(self, game):
        """All stats zero for 3599s does not cause death (1h rescue window)."""
        game.state['stats']['HUNGER'] = 0
        game.state['stats']['ENERGY'] = 0
        game.state['stats']['HAPPY'] = 0
        game.state['critical_since'] = (datetime.now() - timedelta(seconds=3599)).isoformat()
        msg, t = game.tick()
        assert not game.state['is_dead']

    def test_tick_all_stats_zero_1hour_death(self, game):
        """All stats zero for 3600s causes death (1h rescue window expired)."""
        game.state['stats']['HUNGER'] = 0
        game.state['stats']['ENERGY'] = 0
        game.state['stats']['HAPPY'] = 0
        game.state['critical_since'] = (datetime.now() - timedelta(seconds=3600)).isoformat()
        msg, t = game.tick()
        assert game.state['is_dead']
        assert msg == 'Your pet has died...'

    def test_tick_critical_resolved_clears_critical_since(self, game):
        """9.14: When stats recover, critical_since is cleared."""
        game.state['critical_since'] = datetime.now().isoformat()
        game.state['stats']['HUNGER'] = 50
        game.state['stats']['ENERGY'] = 50
        game.state['stats']['HAPPY'] = 50
        game.tick()
        assert game.state.get('critical_since') is None

    def test_tick_random_event_triggers(self, game):
        """9.15: Random event triggers when mock returns low value."""
        game.last_event_time = 0  # bypass cooldown
        game.last_tick_time = time.time()
        game.state['stats']['HAPPY'] = 50  # ensure room for +5
        mood_boost = next(e for e in RANDOM_EVENTS if e.event_id == 'mood_boost')
        with patch('random.random', return_value=0.001), \
             patch('random.choice', return_value=mood_boost):
            game.tick()
            assert game.last_event_time > 0
            assert game.state['stats']['HAPPY'] == 55

    def test_tick_random_event_stat_gate(self, game):
        """9.16: Positive events blocked when stat >= 80."""
        game.last_event_time = 0
        game.last_tick_time = time.time()
        game.state['stats']['HUNGER'] = 95
        found_food = next(e for e in RANDOM_EVENTS if e.event_id == 'found_food')
        with patch('random.random', return_value=0.001), \
             patch('random.choice', return_value=found_food):
            game.tick()
            assert game.state['stats']['HUNGER'] == 95

    def test_tick_random_event_find_item(self, game):
        """9.17: find_item event adds an item to inventory."""
        game.last_event_time = 0
        game.last_tick_time = time.time()
        find_item_evt = next(e for e in RANDOM_EVENTS if e.event_id == 'find_item')
        initial_inv_total = sum(game.pets_data.get('inventory', {}).values())
        with patch('random.random', return_value=0.001), \
             patch('random.choice', side_effect=[find_item_evt, 'apple']):
            game.tick()
        new_inv_total = sum(game.pets_data.get('inventory', {}).values())
        assert new_inv_total > initial_inv_total

    def test_tick_random_event_xp_gain(self, game):
        """9.18: find_coin event grants xp."""
        game.last_event_time = 0
        game.last_tick_time = time.time()
        find_coin = next(e for e in RANDOM_EVENTS if e.event_id == 'find_coin')
        initial_xp = game.state['xp']
        with patch('random.random', return_value=0.001), \
             patch('random.choice', return_value=find_coin):
            game.tick()
        assert game.state['xp'] > initial_xp


# ─── TestHandleAction (9.19-9.25) ────────────────────────────────────────────


class TestHandleAction:
    """SubTask 9.19-9.25: handle_action behavior."""

    def test_handle_action_revive_when_dead(self, game):
        """9.19: Dead pet cannot be revived by feed/play/sleep; must use Potion."""
        game.state['is_dead'] = True
        msg, anim = game.handle_action('feed')
        assert msg == 'Your pet is dead... Use a Potion to revive!'
        assert anim is None
        assert game.state['is_dead']

    def test_handle_action_dead_rejects_unknown_action(self, game):
        """9.20: Dead pet rejects non-feed/play/sleep actions."""
        game.state['is_dead'] = True
        msg, anim = game.handle_action('unknown')
        assert msg == 'Your pet is dead...'
        assert anim is None

    def test_handle_action_cooldown_limit(self, game):
        """9.21: Same-minute action limited to 1 when stat > 10."""
        game.state['stats']['HUNGER'] = 50
        msg1, _ = game.handle_action('feed')
        assert 'Wait' not in msg1
        msg2, _ = game.handle_action('feed')
        assert 'Wait a moment' in msg2

    def test_handle_action_no_cooldown_when_critical(self, game):
        """9.22: Critical state (stat at zero) bypasses cooldown."""
        game.state['stats']['HUNGER'] = 0  # critical: stat at zero bypasses cooldown
        msg1, _ = game.handle_action('feed')
        msg2, _ = game.handle_action('feed')
        # Both should succeed (not cooldown message)
        assert 'Wait' not in msg1
        assert 'Wait' not in msg2

    def test_handle_action_low_stat_allows_3_per_minute(self, game):
        """9.23: When stat <= 10, limit is 3 per minute.

        Use 'play' with HAPPY<=10 and ENERGY<10 (but >0) so play_pet fails
        ('Too tired') but the cooldown count still increments, allowing 3
        attempts before cooldown. ENERGY must be >0 to avoid critical bypass.
        """
        game.state['stats']['HAPPY'] = 5  # <= 10, limit=3
        game.state['stats']['ENERGY'] = 5  # <10 so play_pet fails, >0 so not critical
        # First 3 should pass cooldown check (even though play_pet fails)
        for i in range(3):
            msg, _ = game.handle_action('play')
            assert 'Wait' not in msg, f'Action {i+1} should not be cooldown'
        # 4th should be cooldown
        msg, _ = game.handle_action('play')
        assert 'Wait' in msg

    def test_handle_action_unknown_returns_none(self, game):
        """9.24: Unknown action returns (None, None)."""
        msg, anim = game.handle_action('unknown')
        assert msg is None
        assert anim is None

    def test_handle_action_achievement_unlock_message(self, game):
        """9.25: First feed unlocks achievement."""
        game.state['feed_count'] = 0
        game.state['achievements'] = []
        msg, _ = game.handle_action('feed')
        assert 'Achievement: First Meal' in msg


# ─── TestHandlePet (9.26-9.29) ───────────────────────────────────────────────


class TestHandlePet:
    """SubTask 9.26-9.29: handle_pet behavior."""

    def test_handle_pet_dead_returns_none(self, game):
        """9.26: Dead pet returns None."""
        game.state['is_dead'] = True
        result = game.handle_pet()
        assert result is None

    def test_handle_pet_cooldown_3_per_hour(self, game):
        """9.27: After 3 pets in an hour, returns None and HAPPY unchanged."""
        game.state['pet_count_hour'] = 3
        game.state['pet_hour_start'] = datetime.now().isoformat()
        game.state['stats']['HAPPY'] = 50
        result = game.handle_pet()
        assert result is None
        assert game.state['stats']['HAPPY'] == 50

    def test_handle_pet_hour_window_reset(self, game):
        """9.28: After 1 hour, window resets and petting works again."""
        game.state['pet_count_hour'] = 3
        game.state['pet_hour_start'] = (datetime.now() - timedelta(hours=2)).isoformat()
        game.state['stats']['HAPPY'] = 50
        game.handle_pet()
        assert game.state['pet_count_hour'] == 1
        assert game.state['stats']['HAPPY'] == 52

    def test_handle_pet_critical_no_cooldown(self, game):
        """9.29: Critical state (stat at zero) bypasses pet cooldown but still adds HAPPY."""
        game.state['stats']['HUNGER'] = 0  # critical: stat at zero bypasses cooldown
        game.state['pet_count_hour'] = 3
        game.state['pet_hour_start'] = datetime.now().isoformat()
        game.state['stats']['HAPPY'] = 50
        game.handle_pet()
        assert game.state['stats']['HAPPY'] == 52


# ─── TestSwitchPet (9.30-9.32) ───────────────────────────────────────────────


class TestSwitchPet:
    """SubTask 9.30-9.32: switch_pet behavior."""

    def test_switch_pet_forward_and_backward(self, game):
        """9.30: Switch forward and backward among multiple pets."""
        _add_second_pet(game)
        original_idx = game.pet_idx
        game.switch_pet(1)
        assert game.pet_idx != original_idx
        game.switch_pet(-1)
        assert game.pet_idx == original_idx

    def test_switch_pet_single_pet_wraps_to_self(self, game):
        """9.31: Single pet switching wraps to self."""
        assert len(game.pets_data['pets']) == 1
        game.switch_pet(1)
        assert game.pet_idx == 0

    def test_switch_pet_triggers_interaction_message(self, game):
        """9.32: Switching may trigger interaction message."""
        _add_second_pet(game)
        # Mock to force interaction trigger (random.random() <= 0.3)
        with patch('random.random', return_value=0.1), \
             patch('random.choice', return_value=PET_INTERACTIONS[0]):
            msg = game.switch_pet(1)
            assert 'played together' in msg


# ─── TestTriggerInteraction (9.33-9.36) ──────────────────────────────────────


class TestTriggerInteraction:
    """SubTask 9.33-9.36: trigger_interaction behavior."""

    def test_trigger_interaction_single_pet_returns_none(self, game):
        """9.33: Single pet returns None."""
        assert len(game.pets_data['pets']) == 1
        assert game.trigger_interaction() is None

    def test_trigger_interaction_30_percent_trigger(self, game):
        """9.34: Triggered when random <= 0.3, not when > 0.3."""
        _add_second_pet(game)
        # random.random() = 0.2 (< 0.3) triggers
        with patch('random.random', return_value=0.2), \
             patch('random.choice', return_value=PET_INTERACTIONS[0]):
            result = game.trigger_interaction()
            assert result is not None
        # random.random() = 0.5 (> 0.3) does not trigger
        with patch('random.random', return_value=0.5):
            result = game.trigger_interaction()
            assert result is None

    def test_trigger_interaction_both_target(self, game):
        """9.35: 'both' target affects all pets."""
        _add_second_pet(game)
        play_together = next(i for i in PET_INTERACTIONS if i.event_id == 'play_together')
        for pet in game.pets_data['pets']:
            pet['stats']['HAPPY'] = 50
        with patch('random.random', return_value=0.1), \
             patch('random.choice', return_value=play_together):
            game.trigger_interaction()
        for pet in game.pets_data['pets']:
            assert pet['stats']['HAPPY'] == 55

    def test_trigger_interaction_current_target(self, game):
        """9.36: 'current' target affects only current pet."""
        _add_second_pet(game)
        share_food = next(i for i in PET_INTERACTIONS if i.event_id == 'share_food')
        for pet in game.pets_data['pets']:
            pet['stats']['HUNGER'] = 50
        other_idx = 1 if game.pet_idx == 0 else 0
        with patch('random.random', return_value=0.1), \
             patch('random.choice', return_value=share_food):
            game.trigger_interaction()
        assert game.state['stats']['HUNGER'] == 60
        assert game.pets_data['pets'][other_idx]['stats']['HUNGER'] == 50


# ─── TestAdoptPet (9.37-9.39) ────────────────────────────────────────────────


class TestAdoptPet:
    """SubTask 9.37-9.39: adopt_pet behavior."""

    def test_adopt_pet_max_pets_enters_release_mode(self, game):
        """9.37: At MAX_PETS, enters release mode and returns None."""
        # Fill up to MAX_PETS
        while len(game.pets_data['pets']) < MAX_PETS:
            bones = generate_companion(game.uid + f'-{len(game.pets_data["pets"])}')
            game.pets_data['pets'].append(init_state(_uid(), bones, f'Pet{len(game.pets_data["pets"])}'))
        game.save()
        result = game.adopt_pet()
        assert result is None
        # Mode change happens via handle_key('w'), not adopt_pet() directly
        action_type, detail = game.handle_key('w')
        assert game.mode == 'release'

    def test_adopt_pet_max_pets_from_expanded_enters_release_mode(self, game):
        """Regression: At MAX_PETS, pressing 'w' in expanded mode must enter release mode.

        Previously the state transition `expanded -> release` was not registered,
        so pressing 'w' in expanded mode at MAX_PETS raised InvalidTransition
        inside ExpandedState.handle_key and the adoption/release flow silently
        broke (only compact mode worked).
        """
        # Switch to expanded mode first (initial state is compact)
        game.mode = 'expanded'
        assert game.mode == 'expanded'
        # Fill up to MAX_PETS
        while len(game.pets_data['pets']) < MAX_PETS:
            bones = generate_companion(game.uid + f'-{len(game.pets_data["pets"])}')
            game.pets_data['pets'].append(init_state(_uid(), bones, f'Pet{len(game.pets_data["pets"])}'))
        game.save()
        action_type, detail = game.handle_key('w')
        assert game.mode == 'release'
        assert action_type == 'mode_change'

    def test_adopt_pet_daily_limit_rejected(self, game):
        """9.38: Daily adoption limit returns rejection message."""
        game.pets_data['adoption_log'] = [datetime.now().isoformat() for _ in range(MAX_DAILY_ADOPTIONS)]
        result = game.adopt_pet()
        assert 'Daily limit reached' in result

    def test_adopt_pet_normal(self, game):
        """9.39: Normal adoption adds a pet and switches to it."""
        initial_count = len(game.pets_data['pets'])
        result = game.adopt_pet()
        assert result is not None
        assert len(game.pets_data['pets']) == initial_count + 1
        assert game.pet_idx == len(game.pets_data['pets']) - 1


# ─── TestReleasePet (9.40-9.42) ──────────────────────────────────────────────


class TestReleasePet:
    """SubTask 9.40-9.42: release_pet behavior."""

    @pytest.mark.parametrize('index', [-1, 99])
    def test_release_pet_invalid_index(self, game, index):
        """9.40: Invalid index returns 'Invalid pet!'."""
        assert game.release_pet(index) == 'Invalid pet!'

    def test_release_pet_last_pet_rejected(self, game):
        """9.41: Cannot release the last pet."""
        assert len(game.pets_data['pets']) == 1
        assert game.release_pet(0) == 'Cannot release your last pet!'

    def test_release_pet_normal_and_index_adjustment(self, game):
        """9.42: Normal release reduces count and adjusts pet_idx."""
        _add_second_pet(game)
        initial_count = len(game.pets_data['pets'])
        # Release the first pet
        result = game.release_pet(0)
        assert 'Released' in result
        assert len(game.pets_data['pets']) == initial_count - 1
        # pet_idx should be valid
        assert game.pet_idx < len(game.pets_data['pets'])


# ─── TestGetReleaseList (9.43) ───────────────────────────────────────────────


class TestGetReleaseList:
    """SubTask 9.43: get_release_list format."""

    def test_get_release_list_format(self, game):
        """9.43: Returns list of (index, name, species, rarity) tuples, 1-based."""
        _add_second_pet(game)
        result = game.get_release_list()
        assert len(result) == 2
        for entry in result:
            assert len(entry) == 4
            assert isinstance(entry[0], int)
            assert isinstance(entry[1], str)
            assert isinstance(entry[2], str)
            assert isinstance(entry[3], str)
        assert result[0][0] == 1
        assert result[1][0] == 2


# ─── TestAddItem (9.44-9.45) ─────────────────────────────────────────────────


class TestAddItem:
    """SubTask 9.44-9.45: add_item behavior."""

    def test_add_item_full_inventory_rejected(self, game):
        """9.44: Full inventory returns False."""
        game.pets_data['inventory'] = {'apple': MAX_INVENTORY}
        assert not game.add_item('toy')

    def test_add_item_normal(self, game):
        """9.45: Normal add returns True and increments count."""
        game.pets_data['inventory'] = {}
        assert game.add_item('apple')
        assert game.pets_data['inventory']['apple'] == 1
        assert game.add_item('apple')
        assert game.pets_data['inventory']['apple'] == 2


# ─── TestUseItem (9.46-9.52) ─────────────────────────────────────────────────


class TestUseItem:
    """SubTask 9.46-9.52: use_item behavior."""

    def test_use_item_missing_item(self, game):
        """9.46: Missing item returns 'No such item!'."""
        game.pets_data['inventory'] = {}
        assert game.use_item('apple') == 'No such item!'

    def test_use_item_unknown_item(self, game):
        """9.47: Unknown item id returns 'Unknown item!'."""
        # Inject an invalid item id with positive count
        game.pets_data['inventory'] = {'unknown_item': 1}
        assert game.use_item('unknown_item') == 'Unknown item!'

    def test_use_item_potion_revive_success(self, game):
        """9.48: Potion revives a dead pet."""
        game.state['is_dead'] = True
        game.pets_data['inventory'] = {'potion': 1}
        result = game.use_item('potion')
        assert result == 'Used Potion!'
        assert not game.state['is_dead']
        assert game.state['stats']['HUNGER'] == 25
        assert game.state['stats']['ENERGY'] == 25
        assert game.state['stats']['HAPPY'] == 25

    def test_use_item_potion_not_dead(self, game):
        """9.49: Potion on living pet returns 'Pet is not dead!'."""
        game.state['is_dead'] = False
        game.pets_data['inventory'] = {'potion': 1}
        result = game.use_item('potion')
        assert result == 'Pet is not dead!'

    def test_use_item_hat_equip(self, game):
        """9.50: Crown item equips hat."""
        game.pets_data['inventory'] = {'crown': 1}
        result = game.use_item('crown')
        assert result == 'Used Crown!'
        assert game.state['hat'] == 'crown'
        assert game.bones['hat'] == 'crown'

    def test_use_item_stat_item_capped(self, game):
        """9.51: Apple restores HUNGER capped at 100."""
        game.state['stats']['HUNGER'] = 80
        game.pets_data['inventory'] = {'apple': 1}
        game.use_item('apple')
        assert game.state['stats']['HUNGER'] == 100

    def test_use_item_consumed_when_zero(self, game):
        """9.52: Item with count 1 is removed from inventory after use."""
        game.state['stats']['HUNGER'] = 50
        game.pets_data['inventory'] = {'apple': 1}
        game.use_item('apple')
        assert 'apple' not in game.pets_data['inventory']


# ─── TestGetInventoryList (9.53) ─────────────────────────────────────────────


class TestGetInventoryList:
    """SubTask 9.53: get_inventory_list format."""

    def test_get_inventory_list_format_and_filter(self, game):
        """9.53: Returns tuples (item_id, name, icon, count, desc), filters count>0."""
        game.pets_data['inventory'] = {'apple': 2, 'toy': 1}
        result = game.get_inventory_list()
        assert len(result) == 2
        for entry in result:
            assert len(entry) == 5
            item_id, name, icon, count, desc = entry
            assert item_id in ITEMS
            assert isinstance(name, str)
            assert isinstance(icon, str)
            assert count > 0
            assert isinstance(desc, str)


# ─── TestHandleKey (9.54-9.66) ───────────────────────────────────────────────


class TestHandleKey:
    """SubTask 9.54-9.66: handle_key behavior."""

    def test_handle_key_quit(self, game):
        """9.54: 'q' returns ('quit', None)."""
        assert game.handle_key('q') == ('quit', None)

    def test_handle_key_dead_revive_via_action(self, game):
        """9.55: Dead pet, action key returns Potion hint instead of reviving."""
        game.state['is_dead'] = True
        action_type, msg = game.handle_key('f')
        assert action_type == 'action'
        assert 'Potion' in msg
        assert game.state['is_dead']

    def test_handle_key_enter_mode_toggle(self, game):
        """9.56: Enter toggles compact <-> expanded."""
        assert game.mode == 'compact'
        action_type, mode = game.handle_key('\r')
        assert action_type == 'mode_change'
        assert mode == 'expanded'
        action_type, mode = game.handle_key('\r')
        assert mode == 'compact'

    def test_handle_key_h_help_toggle(self, game):
        """9.57: 'h' toggles help; from compact goes to expanded+help."""
        game.mode = 'compact'
        action_type, mode = game.handle_key('h')
        assert mode == 'expanded'
        assert game.show_help
        # Toggle help off
        game.handle_key('h')
        assert not game.show_help

    def test_handle_key_c_compact_mode(self, game):
        """9.58: 'c' from non-compact switches to compact."""
        game.mode = 'expanded'
        action_type, mode = game.handle_key('c')
        assert action_type == 'mode_change'
        assert mode == 'compact'
        assert not game.show_help

    def test_handle_key_b_n_pet_switch(self, game):
        """9.59: 'b'/'n' switch pets."""
        _add_second_pet(game)
        action_type, msg = game.handle_key('n')
        assert action_type == 'pet_switch'
        assert msg is not None
        action_type, msg = game.handle_key('b')
        assert action_type == 'pet_switch'

    def test_handle_key_w_adopt(self, game):
        """9.60: 'w' adopts a pet or enters release mode."""
        action_type, msg = game.handle_key('w')
        assert action_type in ('action', 'mode_change')
        if action_type == 'action':
            assert msg is not None

    def test_handle_key_t_a_u_mode_switches(self, game):
        """9.61: 't'/'a'/'u' switch modes."""
        # 't' from compact -> stats
        action_type, mode = game.handle_key('t')
        assert mode == 'stats'
        # 't' from stats -> expanded
        action_type, mode = game.handle_key('t')
        assert mode == 'expanded'
        # 'a' from expanded -> achievements
        action_type, mode = game.handle_key('a')
        assert mode == 'achievements'
        # 'u' from achievements -> items
        action_type, mode = game.handle_key('u')
        assert mode == 'items'

    def test_handle_key_e_export_non_compact(self, game):
        """9.62: 'e' exports when not in compact mode."""
        game.mode = 'expanded'
        action_type, detail = game.handle_key('e')
        assert action_type == 'export'
        assert detail is None
        # In compact mode, 'e' should not export
        game.mode = 'compact'
        action_type, _ = game.handle_key('e')
        assert action_type != 'export'

    def test_handle_key_f_p_s_actions(self, game):
        """9.63: 'f'/'p'/'s' trigger actions and set animation."""
        game.state['stats']['HUNGER'] = 50
        game.state['stats']['ENERGY'] = 50
        game.state['stats']['HAPPY'] = 50
        action_type, msg = game.handle_key('f')
        assert action_type == 'action'
        assert msg is not None
        # Animation should be set (anim_end > now)
        assert game.anim_end > time.time()

    def test_handle_key_release_mode_numbers(self, game):
        """9.64: In release mode, number keys release pets."""
        _add_second_pet(game)
        game.mode = 'release'
        initial_count = len(game.pets_data['pets'])
        action_type, msg = game.handle_key('1')
        assert action_type == 'action'
        assert 'Released' in msg
        assert len(game.pets_data['pets']) == initial_count - 1

    def test_handle_key_items_mode_numbers(self, game):
        """9.65: In items mode, number keys use items."""
        game.pets_data['inventory'] = {'apple': 1}
        game.mode = 'items'
        action_type, msg = game.handle_key('1')
        assert action_type == 'action'
        assert 'Used' in msg

    def test_handle_key_unknown_returns_none(self, game):
        """9.66: Unknown key returns ('none', None)."""
        action_type, detail = game.handle_key('z')
        assert action_type == 'none'
        assert detail is None
