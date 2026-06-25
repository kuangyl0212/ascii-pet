"""XP balance integration tests.

Validates that daily battle XP contribution falls within the 30-40% target
range specified in balance-xp-and-combat/spec.md, assuming:
- 4h daily active play
- 60 play actions, 20 feed actions per day
- 5 challenges per day with 50% win rate
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.battle import WIN_XP, LOSE_XP
from ascii_pet.core import MAX_DAILY_CHALLENGES


def test_battle_xp_constants():
    """Verify battle XP constants match spec."""
    assert WIN_XP == 40, f"WIN_XP should be 40, got {WIN_XP}"
    assert LOSE_XP == 10, f"LOSE_XP should be 10, got {LOSE_XP}"


def test_daily_xp_distribution():
    """Daily battle XP should account for 30-40% of total XP.

    Scenario per spec.md:
    - 4h active play
    - 60 play actions × 3 XP = 180 XP
    - 20 feed actions × 2 XP = 40 XP
    - 5 challenges at 50% win rate: 2.5 × 40 + 2.5 × 10 = 125 XP
    - Total: 345 XP, battle share = 125/345 ≈ 36.23%
    """
    # Action XP (per spec.md balance analysis)
    PLAY_XP_PER_ACTION = 3
    FEED_XP_PER_ACTION = 2
    SLEEP_XP_PER_ACTION = 0
    DAILY_PLAYS = 60
    DAILY_FEEDS = 20

    daily_play_xp = DAILY_PLAYS * PLAY_XP_PER_ACTION
    daily_feed_xp = DAILY_FEEDS * FEED_XP_PER_ACTION
    daily_sleep_xp = 0  # sleep grants no XP per spec

    # Battle XP: 5 challenges, 50% win rate
    daily_challenges = MAX_DAILY_CHALLENGES
    win_rate = 0.5
    daily_battle_xp = (daily_challenges * win_rate * WIN_XP
                       + daily_challenges * (1 - win_rate) * LOSE_XP)

    total_daily_xp = daily_play_xp + daily_feed_xp + daily_sleep_xp + daily_battle_xp

    battle_share = daily_battle_xp / total_daily_xp

    # Spec target: 30-40%
    assert 0.30 <= battle_share <= 0.40, (
        f"Battle XP share {battle_share:.2%} out of [30%, 40%] range. "
        f"battle={daily_battle_xp}, total={total_daily_xp}"
    )


def test_extreme_heavy_play_battle_share_floor():
    """Heavy play (8h) reduces battle share but should stay above 15%."""
    # 8h active: 120 plays × 3 = 360 XP
    heavy_play_xp = 120 * 3
    daily_battle_xp = 5 * 0.5 * WIN_XP + 5 * 0.5 * LOSE_XP  # 125
    total = heavy_play_xp + 40 + daily_battle_xp  # 525
    battle_share = daily_battle_xp / total
    assert battle_share >= 0.15, f"Heavy play battle share {battle_share:.2%} below 15% floor"


def test_extreme_light_play_battle_share_ceiling():
    """Light play (1h) raises battle share but should stay below 75%."""
    # 1h active: 15 plays × 3 = 45 XP
    light_play_xp = 15 * 3
    daily_battle_xp = 5 * 0.5 * WIN_XP + 5 * 0.5 * LOSE_XP  # 125
    total = light_play_xp + 40 + daily_battle_xp  # 210
    battle_share = daily_battle_xp / total
    assert battle_share <= 0.75, f"Light play battle share {battle_share:.2%} above 75% ceiling"
