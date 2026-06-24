"""Battle simulation engine for ASCII pet. Pure functions, zero dependencies."""
import random
from ascii_pet.core import SKILLS


def simulate_battle(attacker, defender, seed):
    """Simulate a battle between two pets.

    Args:
        attacker: dict with keys: name, level, hp, attack, defense, speed, skills
        defender: dict with same keys
        seed: int for deterministic randomness

    Returns:
        dict with keys: winner, loser, log, hp_loss_winner, hp_loss_loser
    """
    rng = random.Random(seed)

    # Copy combatants and initialise internal battle BP (separate from real hp)
    a = dict(attacker)
    b = dict(defender)
    a['battle_bp'] = 100
    b['battle_bp'] = 100

    log = []

    # Determine turn order: faster pet attacks first; attacker wins speed ties
    if a['speed'] >= b['speed']:
        first, second = a, b
    else:
        first, second = b, a

    while True:
        _do_attack(first, second, rng, log)
        if second['battle_bp'] <= 0:
            winner, loser = first, second
            break

        _do_attack(second, first, rng, log)
        if first['battle_bp'] <= 0:
            winner, loser = second, first
            break

    hp_loss_loser = 25
    hp_loss_winner = int((100 - winner['battle_bp']) / 100 * 25)
    if hp_loss_winner > 25:
        hp_loss_winner = 25

    return {
        'winner': winner['name'],
        'loser': loser['name'],
        'log': log,
        'hp_loss_winner': hp_loss_winner,
        'hp_loss_loser': hp_loss_loser,
    }


def _do_attack(attacker, defender, rng, log):
    """Perform one attack action and append a log entry."""
    skill_id = rng.choice(attacker['skills'])
    skill = SKILLS[skill_id]

    if rng.random() * 100 < skill['accuracy']:
        multiplier = 0.8 + rng.random() * 0.4
        damage = skill['power'] * (
            attacker['attack'] / (attacker['attack'] + defender['defense'])
        ) * multiplier
        defender['battle_bp'] -= damage
        log.append(
            f"{attacker['name']} used {skill['name']}! Damage: {damage:.1f}. "
            f"{defender['name']} BP: {defender['battle_bp']:.1f}"
        )
    else:
        log.append(
            f"{attacker['name']} used {skill['name']}! Missed! "
            f"{defender['name']} BP: {defender['battle_bp']:.1f}"
        )


def calc_escape_chance(defender_level, attacker_level):
    """Calculate escape chance for defender. Returns float in [0.1, 0.7]."""
    chance = 0.3 + (defender_level - attacker_level) * 0.03
    return max(0.1, min(0.7, chance))
