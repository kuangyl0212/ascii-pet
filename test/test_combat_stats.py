#!/usr/bin/env python3
"""TDD tests for combat stats system.

Covers:
  Task 1: RARITY_COMBAT_MULTIPLIER, SPECIES_COMBAT_PROFILE, SKILLS,
          SPECIES_SKILLS, calculate_combat_stats(), get_pet_skills()
  Task 2: hp field in pet state
  Task 3: medicine item

Run: python -m pytest test/test_combat_stats.py -v
"""

import sys
import os
from pathlib import Path
import tempfile
import time
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pytest
from ascii_pet import core as pet_core
from ascii_pet.core import PetGame


# ─── Task 1: Combat stats constants ──────────────────────────────────────────

BASE_SPECIES = ['duck', 'goose', 'blob', 'cat', 'dragon', 'octopus', 'owl',
                'penguin', 'turtle', 'snail', 'ghost', 'axolotl', 'capybara',
                'cactus', 'robot', 'rabbit', 'mushroom', 'chonk']

EVOLVED_SPECIES = ['slime', 'elemental', 'swan', 'tiger', 'lion', 'wyvern',
                   'dragonlord', 'phoenix', 'sage', 'hare', 'jackalope',
                   'shell', 'turbo', 'wraith', 'specter']

ALL_SPECIES = BASE_SPECIES + EVOLVED_SPECIES


class TestRarityCombatMultiplier:
    """Tests for RARITY_COMBAT_MULTIPLIER dict."""

    def test_exists(self):
        assert hasattr(pet_core, 'RARITY_COMBAT_MULTIPLIER')

    def test_values(self):
        mult = pet_core.RARITY_COMBAT_MULTIPLIER
        assert mult['common'] == 1.0
        assert mult['uncommon'] == 1.2
        assert mult['rare'] == 1.5
        assert mult['epic'] == 1.8
        assert mult['legendary'] == 2.5


class TestSpeciesCombatProfile:
    """Tests for SPECIES_COMBAT_PROFILE dict."""

    def test_exists(self):
        assert hasattr(pet_core, 'SPECIES_COMBAT_PROFILE')

    def test_has_all_base_species(self):
        profile = pet_core.SPECIES_COMBAT_PROFILE
        for species in BASE_SPECIES:
            assert species in profile, f'Missing base species: {species}'

    def test_has_all_evolved_species(self):
        profile = pet_core.SPECIES_COMBAT_PROFILE
        for species in EVOLVED_SPECIES:
            assert species in profile, f'Missing evolved species: {species}'

    def test_entries_have_attack_defense_speed(self):
        profile = pet_core.SPECIES_COMBAT_PROFILE
        for species, entry in profile.items():
            assert 'attack' in entry, f'{species} missing attack'
            assert 'defense' in entry, f'{species} missing defense'
            assert 'speed' in entry, f'{species} missing speed'
            # Multipliers should be positive numbers
            assert entry['attack'] > 0, f'{species} attack must be positive'
            assert entry['defense'] > 0, f'{species} defense must be positive'
            assert entry['speed'] > 0, f'{species} speed must be positive'


class TestSkillsDict:
    """Tests for SKILLS dict."""

    REQUIRED_SKILLS = ['peck', 'scratch', 'bite', 'tackle', 'fire_breath',
                       'water_gun', 'vine_whip', 'thunder', 'shadow_ball',
                       'rock_throw', 'tail_whip', 'roar', 'heal_light']

    def test_exists(self):
        assert hasattr(pet_core, 'SKILLS')

    def test_has_at_least_20_skills(self):
        assert len(pet_core.SKILLS) >= 20

    def test_has_required_skills(self):
        for skill_id in self.REQUIRED_SKILLS:
            assert skill_id in pet_core.SKILLS, f'Missing skill: {skill_id}'

    def test_skills_have_name_power_accuracy(self):
        for skill_id, skill in pet_core.SKILLS.items():
            assert 'name' in skill, f'{skill_id} missing name'
            assert 'power' in skill, f'{skill_id} missing power'
            assert 'accuracy' in skill, f'{skill_id} missing accuracy'
            assert isinstance(skill['power'], (int, float))
            assert 0 <= skill['accuracy'] <= 100


class TestSpeciesSkills:
    """Tests for SPECIES_SKILLS dict."""

    def test_exists(self):
        assert hasattr(pet_core, 'SPECIES_SKILLS')

    def test_has_all_species(self):
        species_skills = pet_core.SPECIES_SKILLS
        for species in ALL_SPECIES:
            assert species in species_skills, f'Missing species: {species}'

    def test_each_species_has_2_to_3_skills(self):
        for species, skills in pet_core.SPECIES_SKILLS.items():
            assert 2 <= len(skills) <= 3, \
                f'{species} has {len(skills)} skills, expected 2-3'

    def test_skill_ids_exist_in_skills_dict(self):
        for species, skill_ids in pet_core.SPECIES_SKILLS.items():
            for sid in skill_ids:
                assert sid in pet_core.SKILLS, \
                    f'{species} references unknown skill: {sid}'

    def test_dragon_has_fire_breath_and_tail_whip(self):
        assert pet_core.SPECIES_SKILLS['dragon'] == ['fire_breath', 'tail_whip']

    def test_dragonlord_has_fire_breath_tail_whip_roar(self):
        assert pet_core.SPECIES_SKILLS['dragonlord'] == ['fire_breath', 'tail_whip', 'roar']


class TestGetPetSkills:
    """Tests for get_pet_skills() function."""

    def test_exists(self):
        assert hasattr(pet_core, 'get_pet_skills')

    def test_returns_list_for_dragon(self):
        skills = pet_core.get_pet_skills('dragon')
        assert isinstance(skills, list)
        assert skills == ['fire_breath', 'tail_whip']

    def test_returns_list_for_dragonlord(self):
        skills = pet_core.get_pet_skills('dragonlord')
        assert isinstance(skills, list)
        assert skills == ['fire_breath', 'tail_whip', 'roar']

    def test_returns_list_for_all_species(self):
        for species in ALL_SPECIES:
            skills = pet_core.get_pet_skills(species)
            assert isinstance(skills, list)
            assert len(skills) >= 2


class TestCalculateCombatStats:
    """Tests for calculate_combat_stats() function."""

    def _make_state(self, species='cat', rarity='common', level=1, hp=100):
        return {
            'species': species,
            'rarity': rarity,
            'level': level,
            'hp': hp,
        }

    def test_exists(self):
        assert hasattr(pet_core, 'calculate_combat_stats')

    def test_returns_dict_with_required_keys(self):
        state = self._make_state()
        stats = pet_core.calculate_combat_stats(state)
        assert isinstance(stats, dict)
        for key in ('hp', 'attack', 'defense', 'speed', 'skills'):
            assert key in stats, f'Missing key: {key}'

    def test_hp_defaults_to_100_when_missing(self):
        state = self._make_state()
        del state['hp']
        stats = pet_core.calculate_combat_stats(state)
        assert stats['hp'] == 100

    def test_hp_uses_state_value(self):
        state = self._make_state(hp=75)
        stats = pet_core.calculate_combat_stats(state)
        assert stats['hp'] == 75

    def test_attack_calculation(self):
        # base = 10 + level * 2; level 5 -> base = 20
        # common rarity_mult = 1.0; cat attack mult = ?
        state = self._make_state(species='cat', rarity='common', level=5)
        stats = pet_core.calculate_combat_stats(state)
        base = 10 + 5 * 2  # 20
        expected_attack = int(base * 1.0 * pet_core.SPECIES_COMBAT_PROFILE['cat']['attack'])
        assert stats['attack'] == expected_attack

    def test_defense_calculation(self):
        state = self._make_state(species='cat', rarity='common', level=5)
        stats = pet_core.calculate_combat_stats(state)
        base = 10 + 5 * 2
        expected_defense = int(base * 1.0 * pet_core.SPECIES_COMBAT_PROFILE['cat']['defense'])
        assert stats['defense'] == expected_defense

    def test_speed_calculation(self):
        state = self._make_state(species='cat', rarity='common', level=5)
        stats = pet_core.calculate_combat_stats(state)
        base = 10 + 5 * 2
        expected_speed = int(base * 1.0 * pet_core.SPECIES_COMBAT_PROFILE['cat']['speed'])
        assert stats['speed'] == expected_speed

    def test_skills_returned(self):
        state = self._make_state(species='dragon', rarity='common', level=5)
        stats = pet_core.calculate_combat_stats(state)
        assert stats['skills'] == ['fire_breath', 'tail_whip']

    def test_higher_level_gives_higher_stats(self):
        state_low = self._make_state(species='cat', rarity='common', level=5)
        state_high = self._make_state(species='cat', rarity='common', level=10)
        stats_low = pet_core.calculate_combat_stats(state_low)
        stats_high = pet_core.calculate_combat_stats(state_high)
        assert stats_high['attack'] > stats_low['attack']
        assert stats_high['defense'] > stats_low['defense']
        assert stats_high['speed'] > stats_low['speed']

    def test_higher_rarity_gives_higher_stats(self):
        state_common = self._make_state(species='cat', rarity='common', level=5)
        state_legendary = self._make_state(species='cat', rarity='legendary', level=5)
        stats_common = pet_core.calculate_combat_stats(state_common)
        stats_legendary = pet_core.calculate_combat_stats(state_legendary)
        assert stats_legendary['attack'] > stats_common['attack']
        assert stats_legendary['defense'] > stats_common['defense']
        assert stats_legendary['speed'] > stats_common['speed']


# ─── Task 2: hp field in pet state ───────────────────────────────────────────

class TestHpField:
    """Tests for hp field in pet state."""

    def test_init_state_has_hp_100(self):
        bones = {
            'species': 'cat', 'eye': '@', 'hat': 'none',
            'shiny': False, 'rarity': 'common',
            'stats': {'HUNGER': 80, 'HAPPY': 80, 'ENERGY': 80, 'WISDOM': 50, 'CHAOS': 50},
        }
        state = pet_core.init_state('test-uid', bones, 'TestPet')
        assert 'hp' in state
        assert state['hp'] == 100

    def test_setdefault_hp_for_backward_compat(self):
        """Loading a state dict without 'hp' should default to 100."""
        bones = {
            'species': 'cat', 'eye': '@', 'hat': 'none',
            'shiny': False, 'rarity': 'common',
            'stats': {'HUNGER': 80, 'HAPPY': 80, 'ENERGY': 80, 'WISDOM': 50, 'CHAOS': 50},
        }
        state = pet_core.init_state('test-uid', bones, 'TestPet')
        # Simulate loading an old save without hp
        del state['hp']
        state.setdefault('hp', 100)
        assert state['hp'] == 100


# ─── Task 3: medicine item ───────────────────────────────────────────────────

@pytest.fixture
def game():
    """Create a PetGame instance for testing."""
    tmpdir = Path(tempfile.mkdtemp())
    uid = f'test-combat-{int(time.time() * 1000000)}'
    g = PetGame(uid, data_dir=tmpdir)
    yield g
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestMedicineItem:
    """Tests for medicine item."""

    def test_medicine_in_items_dict(self):
        assert 'medicine' in pet_core.ITEMS
        item = pet_core.ITEMS['medicine']
        assert item['effect'] == {'hp': 50}

    def test_use_medicine_restores_hp(self, game):
        game.state['hp'] = 30
        game.pets_data.setdefault('inventory', {})['medicine'] = 1
        result = game.use_item('medicine')
        assert game.state['hp'] == 80  # 30 + 50
        assert game.pets_data.get('inventory', {}).get('medicine', 0) == 0
        assert 'Used' in result or 'Medicine' in result

    def test_use_medicine_capped_at_100(self, game):
        game.state['hp'] = 80
        game.pets_data.setdefault('inventory', {})['medicine'] = 1
        game.use_item('medicine')
        assert game.state['hp'] == 100  # capped, not 130

    def test_use_medicine_when_hp_full_does_not_consume(self, game):
        game.state['hp'] = 100
        game.pets_data.setdefault('inventory', {})['medicine'] = 1
        result = game.use_item('medicine')
        assert game.state['hp'] == 100
        assert game.pets_data.get('inventory', {}).get('medicine', 0) == 1
        assert 'full' in result.lower()

    def test_use_medicine_when_dead_does_not_consume(self, game):
        game.state['is_dead'] = True
        game.state['hp'] = 0
        game.pets_data.setdefault('inventory', {})['medicine'] = 1
        result = game.use_item('medicine')
        assert game.state['is_dead'] is True
        assert game.pets_data.get('inventory', {}).get('medicine', 0) == 1
        assert 'Potion' in result or 'dead' in result.lower()
