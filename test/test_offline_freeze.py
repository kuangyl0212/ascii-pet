#!/usr/bin/env python3
"""TDD tests for "offline freeze" feature.

目标行为：程序不运行期间，宠物数值不衰减、死亡倒计时不推进。
实现方式：
  1. save_pets() 写入顶层 last_active 时间戳
  2. PetGame.__init__ 加载存档时，把离线时长补偿回每个 pet 的
     last_fed / last_played / last_slept / critical_since 字段，
     使 update_state_over_time 看到的相对时间差只反映程序运行期间。

测试模拟离线的方式：
  保存后调用 _shift_save_timestamps() 把存档里所有时间戳往前推 N 小时，
  模拟"这个存档是 N 小时前保存的"。这样加载时 now 与存档时间戳的差
  才真正反映 N 小时 + 程序运行时长，能区分补偿生效与未生效。
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet import core as pet_core
from ascii_pet.core import PetGame, init_state, generate_companion, generate_name


def _uid():
    return f'test-freeze-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


def _make_full_state(uid='test-uid', name='Test', species='cat'):
    """构造一个完整可用的 pet state（含所有时间戳字段）。"""
    now_iso = datetime.now().isoformat()
    return {
        'user_id': uid,
        'name': name,
        'species': species,
        'rarity': 'common',
        'eye': '·',
        'hat': 'none',
        'shiny': False,
        'stats': {
            'HUNGER': 80,
            'HAPPY': 80,
            'ENERGY': 80,
            'WISDOM': 50,
            'CHAOS': 50,
        },
        'mood': 'normal',
        'created_at': now_iso,
        'last_fed': now_iso,
        'last_played': now_iso,
        'last_slept': now_iso,
        'level': 1,
        'xp': 0,
        'total_interactions': 0,
        'feed_count': 0,
        'play_count': 0,
        'sleep_count': 0,
        'achievements': [],
        'critical_since': None,
        'is_dead': False,
        'hp': 100,
    }


_PET_TIMESTAMP_KEYS = ('last_fed', 'last_played', 'last_slept', 'created_at', 'critical_since')


def _shift_save_timestamps(path, delta):
    """把存档里所有 ISO 时间戳字段往前/往后推 delta（模拟存档是 delta 之前保存的）。

    delta 为负 timedelta 表示往过去推（模拟离线一段时间）。
    会同时移动 pets[].{last_fed,last_played,last_slept,created_at,critical_since}
    和顶层 last_active。
    """
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    for pet in raw.get('pets', []):
        for key in _PET_TIMESTAMP_KEYS:
            val = pet.get(key)
            if not val:
                continue
            try:
                old = datetime.fromisoformat(val)
                pet[key] = (old + delta).isoformat()
            except (ValueError, TypeError):
                pass
    if raw.get('last_active'):
        try:
            old = datetime.fromisoformat(raw['last_active'])
            raw['last_active'] = (old + delta).isoformat()
        except (ValueError, TypeError):
            pass
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw, f)


# ─── 1. save_pets 写入 last_active ──────────────────────────────────────────

class TestSaveWritesLastActive:
    """save_pets() 应当在 pets_data 顶层写入 last_active ISO 时间戳。"""

    def test_save_pets_writes_last_active_field(self, tmp_path):
        uid = _uid()
        state = _make_full_state(uid)
        data = {'pets': [state], 'current': 0}
        pet_core.save_pets(uid, data, tmp_path)

        path = pet_core.get_state_path(uid, tmp_path)
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)

        assert 'last_active' in raw
        # 应为合法 ISO 时间
        datetime.fromisoformat(raw['last_active'])

    def test_save_pets_updates_last_active_on_each_save(self, tmp_path):
        uid = _uid()
        state = _make_full_state(uid)
        data = {'pets': [state], 'current': 0, 'last_active': '2020-01-01T00:00:00'}
        pet_core.save_pets(uid, data, tmp_path)

        path = pet_core.get_state_path(uid, tmp_path)
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)

        # 不应仍是旧时间
        assert raw['last_active'] != '2020-01-01T00:00:00'
        parsed = datetime.fromisoformat(raw['last_active'])
        # 应为近期时间（5 秒内）
        assert abs((datetime.now() - parsed).total_seconds()) < 5

    def test_save_state_via_petgame_persists_last_active(self, tmp_path):
        uid = _uid()
        game = PetGame(uid, data_dir=tmp_path)
        game.save()

        path = pet_core.get_state_path(uid, tmp_path)
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
        assert 'last_active' in raw


# ─── 2. 离线期间数值不衰减 ───────────────────────────────────────────────────

class TestOfflineStatsFreeze:
    """离线一段时间后重新加载，pet 数值应保持不变。"""

    def test_offline_24h_stats_unchanged(self, tmp_path):
        """离线 24 小时后加载，三项数值应与保存时一致。

        设计：保存时 last_fed 设为 5 分钟前（模拟程序已运行 5 分钟未喂食，
        但仍在 3h 衰减阈值内）。然后用 _shift_save_timestamps 把整个存档
        往前推 24h，模拟"存档是 24h 前保存的"。
        - 补偿生效：last_fed 被推后 24h ≈ now-5min，未超阈值，不衰减
        - 未补偿：last_fed 相对 now 是 24h+5min 前，远超阈值，数值会掉
        """
        uid = _uid()
        game = PetGame(uid, data_dir=tmp_path)
        game.state['stats']['HUNGER'] = 70
        game.state['stats']['HAPPY'] = 70
        game.state['stats']['ENERGY'] = 70
        # last_fed 设为 5 分钟前（程序运行期间，未超衰减阈值）
        five_min_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
        game.state['last_fed'] = five_min_ago
        game.state['last_played'] = five_min_ago
        game.state['last_slept'] = five_min_ago
        game.save()

        # 模拟存档是 24h 前保存的（所有时间戳往前推 24h）
        path = pet_core.get_state_path(uid, tmp_path)
        _shift_save_timestamps(path, -timedelta(hours=24))

        game2 = PetGame(uid, data_dir=tmp_path)

        assert game2.state['stats']['HUNGER'] == 70, f'HUNGER 衰减了：{game2.state["stats"]["HUNGER"]}'
        assert game2.state['stats']['HAPPY'] == 70, f'HAPPY 衰减了：{game2.state["stats"]["HAPPY"]}'
        assert game2.state['stats']['ENERGY'] == 70, f'ENERGY 衰减了：{game2.state["stats"]["ENERGY"]}'

    def test_offline_period_compensates_timestamps(self, tmp_path):
        """离线 24h，保存时 last_fed 为 5 分钟前，加载后 last_fed 应 ≈ now-5min。

        - 补偿生效：last_fed = (save_time-5min) + 24h ≈ now-5min
        - 未补偿：last_fed = save_time-5min-24h ≈ now-24h-5min
        """
        uid = _uid()
        game = PetGame(uid, data_dir=tmp_path)
        five_min_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
        game.state['last_fed'] = five_min_ago
        game.save()

        path = pet_core.get_state_path(uid, tmp_path)
        _shift_save_timestamps(path, -timedelta(hours=24))

        game2 = PetGame(uid, data_dir=tmp_path)
        loaded_last_fed = datetime.fromisoformat(game2.state['last_fed'])
        # 补偿后 last_fed 应在 now-5min 附近（允许 1 分钟误差）
        expected = datetime.now() - timedelta(minutes=5)
        delta = abs((loaded_last_fed - expected).total_seconds())
        assert delta < 60, f'last_fed 偏离预期(now-5min) {delta}s，补偿未生效'

    def test_offline_with_multiple_pets_all_compensated(self, tmp_path):
        """多宠物场景：所有 pet 的时间戳都应被补偿。"""
        uid = _uid()
        game = PetGame(uid, data_dir=tmp_path)
        five_min_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
        game.state['last_fed'] = five_min_ago
        # 加第二只宠物
        bones = generate_companion(uid + '-2')
        new_state = init_state(uid + '-2', bones, 'SecondPet')
        new_state['last_fed'] = five_min_ago
        game.pets_data['pets'].append(new_state)
        game.save()

        path = pet_core.get_state_path(uid, tmp_path)
        _shift_save_timestamps(path, -timedelta(hours=12))

        game2 = PetGame(uid, data_dir=tmp_path)
        expected = datetime.now() - timedelta(minutes=5)
        for i, pet in enumerate(game2.pets_data['pets']):
            fed = datetime.fromisoformat(pet['last_fed'])
            delta = abs((fed - expected).total_seconds())
            assert delta < 60, f'pet[{i}] last_fed 偏离预期(now-5min) {delta}s，未补偿'


# ─── 3. 离线期间死亡倒计时不推进 ─────────────────────────────────────────────

class TestOfflineCriticalSinceFreeze:
    """critical_since（死亡倒计时）在离线期间不应推进。"""

    def test_offline_critical_since_compensated(self, tmp_path):
        """进入 critical 状态后离线 2 小时，加载后倒计时只推进"运行时长"（接近 0）。

        设计：critical_since 设为 30 分钟前，然后用 _shift_save_timestamps
        把存档往前推 2h，模拟"存档是 2h 前保存的"。
        - 补偿生效：critical_since 被推后 2h ≈ now-30min，倒计时只推进 30min
        - 未补偿：critical_since 相对 now 是 2h30min 前，超过 1h 会死亡
        """
        uid = _uid()
        game = PetGame(uid, data_dir=tmp_path)
        # 制造 critical 状态：三项归零
        game.state['stats']['HUNGER'] = 0
        game.state['stats']['HAPPY'] = 0
        game.state['stats']['ENERGY'] = 0
        critical_start = datetime.now() - timedelta(minutes=30)
        game.state['critical_since'] = critical_start.isoformat()
        game.save()

        # 模拟存档是 2h 前保存的
        path = pet_core.get_state_path(uid, tmp_path)
        _shift_save_timestamps(path, -timedelta(hours=2))

        game2 = PetGame(uid, data_dir=tmp_path)
        # 不应死亡（补偿后 critical_since ≈ now-30min，未超 1h）
        assert game2.state.get('is_dead') is False
        # critical_since 应被补偿到接近 now-30min
        cs = datetime.fromisoformat(game2.state['critical_since'])
        expected = datetime.now() - timedelta(minutes=30)
        delta = abs((cs - expected).total_seconds())
        assert delta < 60, f'critical_since 偏离预期(now-30min) {delta}s，未补偿'


# ─── 4. 向后兼容：旧存档无 last_active ──────────────────────────────────────

class TestBackwardCompat:
    """旧存档没有 last_active 字段时应优雅降级，不报错。"""

    def test_old_save_without_last_active_loads_fine(self, tmp_path):
        uid = _uid()
        game = PetGame(uid, data_dir=tmp_path)
        game.save()

        # 删除 last_active 字段模拟旧存档
        path = pet_core.get_state_path(uid, tmp_path)
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
        raw.pop('last_active', None)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(raw, f)

        # 应正常加载，不抛异常
        game2 = PetGame(uid, data_dir=tmp_path)
        assert game2.state is not None

    def test_legacy_save_no_last_active_no_crash(self, tmp_path):
        """直接构造一个完全没有 last_active 的存档（模拟从未启用此特性的存档）。"""
        uid = _uid()
        state = _make_full_state(uid)
        # last_fed 设为 48h 前，无 last_active 时应走旧逻辑（会衰减）
        old_ts = (datetime.now() - timedelta(hours=48)).isoformat()
        state['last_fed'] = old_ts
        state['last_played'] = old_ts
        state['last_slept'] = old_ts
        data = {'pets': [state], 'current': 0}
        path = pet_core.get_state_path(uid, tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        # 不抛异常即可
        game = PetGame(uid, data_dir=tmp_path)
        assert game.state is not None


# ─── 5. 损坏的 last_active 优雅降级 ────────────────────────────────────────

class TestCorruptLastActive:
    """last_active 字段损坏（非法 ISO 字符串）时应优雅降级，不抛异常。"""

    def test_corrupt_last_active_does_not_crash(self, tmp_path):
        uid = _uid()
        game = PetGame(uid, data_dir=tmp_path)
        game.save()

        path = pet_core.get_state_path(uid, tmp_path)
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
        raw['last_active'] = 'not-a-date'
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(raw, f)

        # 不应抛异常，应回退到"不补偿"逻辑
        game2 = PetGame(uid, data_dir=tmp_path)
        assert game2.state is not None

    def test_future_last_active_no_crash(self, tmp_path):
        """last_active 在未来（系统时钟异常）时不应导致负时长崩溃。"""
        uid = _uid()
        game = PetGame(uid, data_dir=tmp_path)
        game.save()

        path = pet_core.get_state_path(uid, tmp_path)
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
        raw['last_active'] = (datetime.now() + timedelta(days=10)).isoformat()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(raw, f)

        game2 = PetGame(uid, data_dir=tmp_path)
        assert game2.state is not None
