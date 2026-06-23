#!/usr/bin/env python3
"""TDD RED phase: Tests for death UI interaction fix.

Dead pets should allow menu switching, pet switching, direct revive (r),
and direct release (d). The death screen should show updated commands.

Run: python -m pytest test_death_ui.py -v
"""

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import shutil

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pet_core import PetGame, generate_companion, init_state


def _uid():
    return f'test-death-ui-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


@pytest.fixture
def game(tmp_path):
    """PetGame with a dead pet."""
    uid = _uid()
    g = PetGame(uid, data_dir=tmp_path)
    g.state['is_dead'] = True
    g.state['critical_since'] = datetime.now().isoformat()
    yield g


@pytest.fixture
def game_multi(tmp_path):
    """PetGame with a dead pet and a second alive pet."""
    uid = _uid()
    g = PetGame(uid, data_dir=tmp_path)
    g.state['is_dead'] = True
    g.state['critical_since'] = datetime.now().isoformat()
    # Add second pet
    g.pets_data['pets'][g.pet_idx] = g.state
    bones = generate_companion(g.uid + '-2')
    new_state = init_state(g.uid + '-2', bones, 'SecondPet')
    g.pets_data['pets'].append(new_state)
    g.save()
    yield g


# ─── 死亡后菜单切换 ──────────────────────────────────────────────────────────


class TestDeadMenuSwitch:
    """Dead pet should allow switching to other menu modes."""

    def test_dead_u_key_opens_items(self, game):
        """死亡后按 u 键可切换到物品栏模式。"""
        atype, detail = game.handle_key('u')
        assert atype == 'mode_change'
        assert detail == 'items'

    def test_dead_a_key_opens_achievements(self, game):
        """死亡后按 a 键可切换到成就模式。"""
        atype, detail = game.handle_key('a')
        assert atype == 'mode_change'
        assert detail == 'achievements'

    def test_dead_t_key_opens_stats(self, game):
        """死亡后按 t 键可切换到统计模式。"""
        atype, detail = game.handle_key('t')
        assert atype == 'mode_change'
        assert detail == 'stats'

    def test_dead_enter_key_toggles_mode(self, game):
        """死亡后按 Enter 键可切换模式。"""
        game.mode = 'compact'
        atype, detail = game.handle_key('\r')
        assert atype == 'mode_change'
        assert detail == 'expanded'

    def test_dead_c_key_goes_compact(self, game):
        """死亡后按 c 键可切换到紧凑模式。"""
        game.mode = 'expanded'
        atype, detail = game.handle_key('c')
        assert atype == 'mode_change'
        assert detail == 'compact'

    def test_dead_items_mode_use_potion_revives(self, game):
        """死亡后在物品栏使用 Potion 可复活宠物。"""
        game.pets_data.setdefault('inventory', {})['potion'] = 1
        # Switch to items mode
        game.handle_key('u')
        assert game.mode == 'items'
        # Use potion (find its index in inventory)
        inv_list = game.get_inventory_list()
        potion_idx = None
        for i, (iid, name, icon, count, desc) in enumerate(inv_list):
            if iid == 'potion':
                potion_idx = i
                break
        assert potion_idx is not None, "Potion should be in inventory"
        atype, msg = game.handle_key(str(potion_idx + 1))
        assert atype == 'action'
        assert game.state['is_dead'] is False
        assert game.state['stats']['HUNGER'] == 25


# ─── 死亡后 r 键直接复活 ─────────────────────────────────────────────────────


class TestDeadReviveKey:
    """Dead pet: 'r' key uses Potion to revive directly."""

    def test_dead_r_key_revive_with_potion(self, game):
        """有 Potion 时按 r 键复活宠物。"""
        game.pets_data.setdefault('inventory', {})['potion'] = 1
        atype, msg = game.handle_key('r')
        assert atype == 'action'
        assert game.state['is_dead'] is False
        assert game.state['stats']['HUNGER'] == 25
        assert game.state['stats']['ENERGY'] == 25
        assert game.state['stats']['HAPPY'] == 25
        assert game.pets_data['inventory'].get('potion', 0) == 0

    def test_dead_r_key_no_potion(self, game):
        """无 Potion 时按 r 键返回提示。"""
        game.pets_data.setdefault('inventory', {})
        atype, msg = game.handle_key('r')
        assert atype == 'action'
        assert 'No Potion' in msg or 'No potion' in msg
        assert game.state['is_dead'] is True

    def test_dead_r_key_multiple_potions(self, game):
        """有多个 Potion 时按 r 键复活，消耗一个。"""
        game.pets_data.setdefault('inventory', {})['potion'] = 3
        atype, msg = game.handle_key('r')
        assert atype == 'action'
        assert game.state['is_dead'] is False
        assert game.pets_data['inventory']['potion'] == 2


# ─── 死亡后 d 键遗弃宠物 ─────────────────────────────────────────────────────


class TestDeadReleaseKey:
    """Dead pet: 'd' key releases the dead pet."""

    def test_dead_d_key_release_multi_pets(self, game_multi):
        """多只宠物时按 d 键遗弃死亡宠物。"""
        dead_name = game_multi.state['name']
        atype, msg = game_multi.handle_key('d')
        assert atype == 'action'
        assert 'Released' in msg or dead_name in msg
        # Should switch to the remaining pet
        assert game_multi.state['is_dead'] is False
        assert game_multi.mode == 'expanded'

    def test_dead_d_key_single_pet_rejected(self, game):
        """仅剩一只宠物时按 d 键返回提示。"""
        assert len(game.pets_data['pets']) == 1
        atype, msg = game.handle_key('d')
        assert atype == 'action'
        assert 'Cannot release' in msg or 'last pet' in msg
        assert game.state['is_dead'] is True


# ─── 死亡后宠物切换 ──────────────────────────────────────────────────────────


class TestDeadPetSwitch:
    """Dead pet should allow switching to other pets."""

    def test_dead_n_key_switch_pet(self, game_multi):
        """死亡后按 n 键切换到下一只宠物。"""
        atype, msg = game_multi.handle_key('n')
        assert atype == 'pet_switch'
        # Should have switched to the other (alive) pet
        assert game_multi.state['is_dead'] is False

    def test_dead_b_key_switch_pet(self, game_multi):
        """死亡后按 b 键切换到上一只宠物。"""
        atype, msg = game_multi.handle_key('b')
        assert atype == 'pet_switch'
        assert game_multi.state['is_dead'] is False


# ─── 死亡后 f/p/s 键仍返回引导提示 ──────────────────────────────────────────


class TestDeadFPSKeys:
    """Dead pet: f/p/s keys should still return Potion guidance (existing behavior)."""

    def test_dead_f_key_hint(self, game):
        """死亡后按 f 键仍返回引导提示。"""
        atype, msg = game.handle_key('f')
        assert atype == 'action'
        assert 'Potion' in msg
        assert game.state['is_dead'] is True

    def test_dead_p_key_hint(self, game):
        """死亡后按 p 键仍返回引导提示。"""
        atype, msg = game.handle_key('p')
        assert atype == 'action'
        assert 'Potion' in msg
        assert game.state['is_dead'] is True

    def test_dead_s_key_hint(self, game):
        """死亡后按 s 键仍返回引导提示。"""
        atype, msg = game.handle_key('s')
        assert atype == 'action'
        assert 'Potion' in msg
        assert game.state['is_dead'] is True
