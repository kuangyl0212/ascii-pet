"""Battle simulation engine for ASCII pet. Pure functions, zero dependencies."""
import random
from ascii_pet.core import SKILLS
from ascii_pet.i18n import _

from ascii_pet.log import logger

# Battle XP rewards (Task 1 of add-battle-xp-rewards spec)
WIN_XP = 40
LOSE_XP = 10

# CHAOS combat mechanics (Task 6)
CRIT_BASE_CHANCE = 0.05
CRIT_CHAOS_FACTOR = 0.003
CRIT_CAP = 0.35
CRIT_DAMAGE_MULTIPLIER = 1.5
DODGE_CHAOS_FACTOR = 0.002
DODGE_CAP = 0.20


def calc_crit_chance(attacker_chaos):
    """Calculate crit chance from attacker's CHAOS. Returns float in [0.05, 0.35]."""
    return min(CRIT_CAP, CRIT_BASE_CHANCE + attacker_chaos * CRIT_CHAOS_FACTOR)


def calc_dodge_chance(defender_chaos):
    """Calculate dodge chance from defender's CHAOS. Returns float in [0.0, 0.20]."""
    return min(DODGE_CAP, defender_chaos * DODGE_CHAOS_FACTOR)


def simulate_battle(attacker, defender, seed):
    """Simulate a battle between two pets.

    Args:
        attacker: dict with keys: name, level, hp, attack, defense, speed, skills
        defender: dict with same keys
        seed: int for deterministic randomness

    Returns:
        dict with keys: winner, loser, log, hp_loss_winner, hp_loss_loser
    """
    logger.info(f"Battle started: {attacker.get('name','?')} (lv{attacker.get('level',1)}) vs {defender.get('name','?')} (lv{defender.get('level',1)})")
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

    max_rounds = 200
    rounds = 0
    while rounds < max_rounds:
        _do_attack(first, second, rng, log)
        if second['battle_bp'] <= 0:
            winner, loser = first, second
            break

        _do_attack(second, first, rng, log)
        if first['battle_bp'] <= 0:
            winner, loser = second, first
            break
        rounds += 1
    else:
        # Max rounds reached without a KO (e.g. both pets keep dodging):
        # higher BP wins, ties go to attacker (first).
        if first['battle_bp'] >= second['battle_bp']:
            winner, loser = first, second
        else:
            winner, loser = second, first

    hp_loss_loser = 25
    hp_loss_winner = int((100 - winner['battle_bp']) / 100 * 25)
    if hp_loss_winner > 25:
        hp_loss_winner = 25

    logger.info(f"Battle ended: winner={winner['name']}, rounds={len(log)}")
    return {
        'winner': winner['name'],
        'loser': loser['name'],
        'log': log,
        'hp_loss_winner': hp_loss_winner,
        'hp_loss_loser': hp_loss_loser,
        'xp_winner': WIN_XP,
        'xp_loser': LOSE_XP,
    }


def _do_attack(attacker, defender, rng, log):
    """Perform one attack action and append a log entry.

    Judgment order (preserves backward-compatible RNG sequence for
    combatants without 'chaos' field):
      1. Dodge check (only consumes rng.random() when defender_chaos > 0)
         → if dodged, damage = 0, log "Dodged!"
      2. Accuracy check (FIRST rng.random() when defender has no chaos)
         → if missed, log "Missed!"
      3. If hit: multiplier roll, damage calculation
      4. Crit check (only consumes rng.random() when attacker_chaos > 0)
         → if crit, damage × 1.5, log "Crit!"
    Missing 'chaos' field is treated as 0; when both chaos are 0, RNG
    sequence is identical to the pre-CHAOS implementation.
    """
    skill_id = rng.choice(attacker['skills'])
    skill = SKILLS[skill_id]

    attacker_chaos = attacker.get('chaos', 0)
    defender_chaos = defender.get('chaos', 0)

    # 1. Dodge check (only consumes rng.random() when defender has chaos)
    if defender_chaos > 0:
        dodge_chance = calc_dodge_chance(defender_chaos)
        if rng.random() < dodge_chance:
            log.append(
                _("{name} used {skill}! Dodged! {target} BP: {bp}").format(
                    name=attacker['name'], skill=skill['name'],
                    target=defender['name'],
                    bp=f"{defender['battle_bp']:.1f}")
            )
            return

    # 2. Accuracy check (first rng.random() when defender has no chaos)
    if rng.random() * 100 < skill['accuracy']:
        multiplier = 0.8 + rng.random() * 0.4
        damage = skill['power'] * (
            attacker['attack'] / (attacker['attack'] + defender['defense'])
        ) * multiplier

        # 3. Crit check (only consumes rng.random() when attacker has chaos)
        is_crit = False
        if attacker_chaos > 0:
            crit_chance = calc_crit_chance(attacker_chaos)
            if rng.random() < crit_chance:
                is_crit = True
                damage *= CRIT_DAMAGE_MULTIPLIER

        defender['battle_bp'] -= damage
        if is_crit:
            log.append(
                _("{name} used {skill}! Crit! Damage: {damage}. {target} BP: {bp}").format(
                    name=attacker['name'], skill=skill['name'],
                    damage=f"{damage:.1f}", target=defender['name'],
                    bp=f"{defender['battle_bp']:.1f}")
            )
        else:
            log.append(
                _("{name} used {skill}! Damage: {damage}. {target} BP: {bp}").format(
                    name=attacker['name'], skill=skill['name'],
                    damage=f"{damage:.1f}", target=defender['name'],
                    bp=f"{defender['battle_bp']:.1f}")
            )
    else:
        log.append(
            _("{name} used {skill}! Missed! {target} BP: {bp}").format(
                name=attacker['name'], skill=skill['name'],
                target=defender['name'],
                bp=f"{defender['battle_bp']:.1f}")
        )


def calc_escape_chance(defender_level, attacker_level):
    """Calculate escape chance for defender. Returns float in [0.1, 0.7]."""
    chance = 0.3 + (defender_level - attacker_level) * 0.03
    return max(0.1, min(0.7, chance))
