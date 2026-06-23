"""Tests for i18n message translation in pet_core.py

Verifies that user-visible strings in pet_core.py are properly wrapped
with _() so they translate when the language changes.
"""
import os, sys, tempfile
from datetime import datetime
from pathlib import Path
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.i18n import set_language, get_language, _, save_settings
from ascii_pet.core import (
    feed_pet, play_pet, sleep_pet, init_state, generate_companion,
    generate_name, PetGame, ITEMS, ACHIEVEMENTS, RANDOM_EVENTS,
    PET_INTERACTIONS, MAX_DAILY_ADOPTIONS,
)


@pytest.fixture(autouse=True)
def reset_language():
    """Reset language to English after every test."""
    yield
    set_language('en')


def _make_state(**overrides):
    """Create a minimal pet state for testing."""
    bones = generate_companion('test-uid')
    state = init_state('test-uid', bones, 'TestPet')
    state.update(overrides)
    return state


# ─── Action messages ──────────────────────────────────────────────────────────

class TestActionMessagesI18n:
    """Action functions (feed_pet, play_pet, sleep_pet) return translated messages."""

    def test_feed_already_full_chinese(self):
        set_language('zh')
        state = _make_state()
        state['stats']['HUNGER'] = 100
        msg, _ = feed_pet(state)
        assert msg == '已经吃饱了！'

    def test_feed_already_full_english(self):
        set_language('en')
        state = _make_state()
        state['stats']['HUNGER'] = 100
        msg, _ = feed_pet(state)
        assert msg == 'Already full!'

    def test_feed_success_chinese(self):
        set_language('zh')
        state = _make_state()
        state['stats']['HUNGER'] = 50
        msg, _ = feed_pet(state)
        assert msg == '+25 饱食, +5 快乐'

    def test_play_too_tired_chinese(self):
        set_language('zh')
        state = _make_state()
        state['stats']['ENERGY'] = 5
        msg, _ = play_pet(state)
        assert msg == '太累了！'

    def test_play_success_chinese(self):
        set_language('zh')
        state = _make_state()
        state['stats']['ENERGY'] = 50
        msg, _ = play_pet(state)
        assert msg == '+30 快乐, -15 精力'

    def test_sleep_not_sleepy_chinese(self):
        set_language('zh')
        state = _make_state()
        state['stats']['ENERGY'] = 100
        msg, _ = sleep_pet(state)
        assert msg == '不想睡！'

    def test_sleep_success_chinese(self):
        set_language('zh')
        state = _make_state()
        state['stats']['ENERGY'] = 50
        msg, _ = sleep_pet(state)
        assert msg == '+40 精力'


# ─── Item names / descriptions ────────────────────────────────────────────────

class TestItemTranslationsI18n:
    """Item names and descriptions are translatable via _()."""

    def test_item_name_chinese(self):
        set_language('zh')
        assert _('Apple') == '苹果'
        assert _('Toy') == '玩具'
        assert _('Potion') == '药水'
        assert _('Bed') == '床铺'
        assert _('Book') == '书本'
        assert _('Crown') == '皇冠'
        assert _('Top Hat') == '礼帽'
        assert _('Chaos Crystal') == '混沌水晶'

    def test_item_name_english(self):
        set_language('en')
        assert _('Apple') == 'Apple'
        assert _('Potion') == 'Potion'

    def test_item_desc_chinese(self):
        set_language('zh')
        assert _('Restores 30 hunger') == '恢复30饱食'
        assert _('Revives a dead pet') == '复活死亡宠物'
        assert _('Grants 15 chaos') == '增加15混沌'


# ─── Achievement names ────────────────────────────────────────────────────────

class TestAchievementTranslationsI18n:
    """Achievement names are translatable via _()."""

    def test_achievement_name_chinese(self):
        set_language('zh')
        assert _('First Meal') == '第一餐'
        assert _('Lucky Find') == '幸运发现'
        assert _('Rising Star') == '新星'
        assert _('Shiny Hunter') == '闪光猎人'

    def test_achievement_name_english(self):
        set_language('en')
        assert _('First Meal') == 'First Meal'
        assert _('Lucky Find') == 'Lucky Find'


# ─── Random events ────────────────────────────────────────────────────────────

class TestRandomEventTranslationsI18n:
    """Random event descriptions are translatable via _()."""

    def test_event_description_chinese(self):
        set_language('zh')
        assert _('Achoo!') == '阿嚏！'
        assert _('Found something!') == '发现了东西！'
        assert _('Feeling great!') == '感觉棒极了！'
        assert _('Tripped! Ouch!') == '绊倒了！好痛！'

    def test_event_description_english(self):
        set_language('en')
        assert _('Achoo!') == 'Achoo!'
        assert _('Found something!') == 'Found something!'


# ─── Pet interactions ─────────────────────────────────────────────────────────

class TestPetInteractionTranslationsI18n:
    """Pet interaction suffixes are translatable via _()."""

    def test_interaction_chinese(self):
        set_language('zh')
        assert _(' played together!') == ' 一起玩耍了！'
        assert _(' shared a snack!') == ' 分享了零食！'
        assert _(' had a nice chat!') == ' 聊得很开心！'
        assert _(' had a race!') == ' 进行了赛跑！'


# ─── Warning / status messages ────────────────────────────────────────────────

class TestWarningMessagesI18n:
    """Warning and status messages are translatable."""

    def test_starving_chinese(self):
        set_language('zh')
        assert _('Your pet is starving!') == '你的宠物快饿死了！'

    def test_exhausted_chinese(self):
        set_language('zh')
        assert _('Your pet is exhausted!') == '你的宠物精疲力尽！'

    def test_lonely_chinese(self):
        set_language('zh')
        assert _('Your pet is lonely!') == '你的宠物很孤独！'

    def test_died_chinese(self):
        set_language('zh')
        assert _('Your pet has died...') == '你的宠物死了...'

    def test_critical_format_chinese(self):
        set_language('zh')
        msg = _('CRITICAL! All stats at zero! ({remaining}min left)').format(remaining=5)
        assert '危险' in msg
        assert '5' in msg

    def test_dead_revive_chinese(self):
        set_language('zh')
        assert _('Your pet is dead... Use a Potion to revive!') == '你的宠物死了...用药水复活！'


# ─── PetGame integration ──────────────────────────────────────────────────────

class TestPetGameI18n:
    """PetGame methods return translated messages."""

    def test_use_potion_revive_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-potion-i18n', data_dir=Path(tmpdir))
            game.state['is_dead'] = True
            game.pets_data.setdefault('inventory', {})['potion'] = 1
            msg = game.use_item('potion')
            assert '药水' in msg

    def test_adopt_pet_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-adopt-i18n', data_dir=Path(tmpdir))
            msg = game.adopt_pet()
            # May be "领养了..." or an achievement message
            assert '领养' in msg or '成就' in msg

    def test_release_pet_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-release-i18n', data_dir=Path(tmpdir))
            game.adopt_pet()  # Need 2 pets to release one
            msg = game.release_pet(0)
            assert '释放' in msg

    def test_switch_pet_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-switch-i18n', data_dir=Path(tmpdir))
            game.adopt_pet()  # Need 2 pets to switch
            msg = game.switch_pet(1)
            assert '切换' in msg or '成就' in msg

    def test_feed_dead_pet_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-dead-i18n', data_dir=Path(tmpdir))
            game.state['is_dead'] = True
            msg, _ = game.handle_action('feed')
            assert '死了' in msg

    def test_invalid_pet_release_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-invalid-i18n', data_dir=Path(tmpdir))
            msg = game.release_pet(99)
            assert '无效' in msg

    def test_cannot_release_last_pet_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-lastpet-i18n', data_dir=Path(tmpdir))
            msg = game.release_pet(0)
            assert '最后' in msg

    def test_no_such_item_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-nosuchitem-i18n', data_dir=Path(tmpdir))
            msg = game.use_item('nonexistent')
            assert '没有' in msg

    def test_pet_not_dead_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-notdead-i18n', data_dir=Path(tmpdir))
            game.pets_data.setdefault('inventory', {})['potion'] = 1
            msg = game.use_item('potion')
            assert '没有死亡' in msg

    def test_daily_limit_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-dailylimit-i18n', data_dir=Path(tmpdir))
            for _ in range(MAX_DAILY_ADOPTIONS):
                game.pets_data.setdefault('adoption_log', []).append(
                    datetime.now().isoformat())
            msg = game.adopt_pet()
            assert '上限' in msg

    def test_use_item_translated_name_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-useitem-i18n', data_dir=Path(tmpdir))
            game.pets_data.setdefault('inventory', {})['apple'] = 1
            msg = game.use_item('apple')
            assert '苹果' in msg

    def test_inventory_list_translated_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-invlist-i18n', data_dir=Path(tmpdir))
            game.pets_data.setdefault('inventory', {})['apple'] = 1
            inv_list = game.get_inventory_list()
            apple_entries = [e for e in inv_list if e[0] == 'apple']
            assert len(apple_entries) == 1
            assert apple_entries[0][1] == '苹果'   # name
            assert apple_entries[0][4] == '恢复30饱食'  # desc

    def test_cooldown_chinese(self):
        set_language('zh')
        with tempfile.TemporaryDirectory() as tmpdir:
            save_settings(data_dir=tmpdir)
            game = PetGame('test-cooldown-i18n', data_dir=Path(tmpdir))
            minute_key = datetime.now().strftime('%Y-%m-%d %H:%M')
            game.state['feed_min_time'] = minute_key
            game.state['feed_min_count'] = 99
            msg, _ = game.handle_action('feed')
            assert '稍后再' in msg

    def test_evolution_chinese(self):
        set_language('zh')
        state = _make_state(species='blob', level=4, xp=400)
        from ascii_pet.core import check_level_up
        result = check_level_up(state)
        assert '进化为' in result
        assert 'slime' in result
