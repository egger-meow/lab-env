"""BRET Discrete-Static task domain logic and mechanics according to PREFERENCE_LAB_SPEC.md."""

from __future__ import annotations

import random
from pydantic import BaseModel, Field


class BretActionOption(BaseModel):
    action_id: str
    k: int
    label: str


class BretPublicStimulus(BaseModel):
    num_boxes: int  # N
    reward_per_box: int  # r
    options: list[BretActionOption]  # 4 action options (e.g. collect_0, collect_low, collect_mid, collect_high)


class BretEvaluationResult(BaseModel):
    k: int
    num_boxes: int
    reward_per_box: int
    hit_probability: float
    payoff_if_safe: int
    payoff_if_hit: int
    expected_payoff: float


def validate_bret_params(num_boxes: int, reward_per_box: int, k: int) -> None:
    """Validate BRET parameters strictly.

    N >= 1, r >= 1, 0 <= k <= N.
    """
    if num_boxes < 1:
        raise ValueError(f"num_boxes must be >= 1, got {num_boxes}")
    if reward_per_box < 1:
        raise ValueError(f"reward_per_box must be >= 1 (positive integer), got {reward_per_box}")
    if k < 0 or k > num_boxes:
        raise ValueError(f"k must be in range [0, {num_boxes}], got {k}")


def get_bret_action_stats(
    num_boxes: int,
    reward_per_box: int,
    k: int,
) -> BretEvaluationResult:
    """Compute exact probabilistic stats for collecting k boxes."""
    validate_bret_params(num_boxes, reward_per_box, k)
    hit_prob = k / num_boxes
    payoff_safe = reward_per_box * k
    payoff_hit = 0
    expected = reward_per_box * k * (1.0 - hit_prob)
    return BretEvaluationResult(
        k=k,
        num_boxes=num_boxes,
        reward_per_box=reward_per_box,
        hit_probability=hit_prob,
        payoff_if_safe=payoff_safe,
        payoff_if_hit=payoff_hit,
        expected_payoff=expected,
    )


def compute_bret_payoff(bomb_index: int, k: int, reward_per_box: int) -> tuple[int, bool]:
    """Calculate payoff given bomb index b, collection k, and reward r.

    Rules:
    - b in 1..N
    - If b <= k: hit bomb! Payoff = 0
    - If b > k: safe! Payoff = r * k

    Returns:
    (payoff, is_bomb_hit)
    """
    if k < 0:
        raise ValueError(f"k cannot be negative, got {k}")
    if bomb_index < 1:
        raise ValueError(f"bomb_index must be >= 1, got {bomb_index}")

    if bomb_index <= k:
        return 0, True
    return reward_per_box * k, False


def sample_bomb_index(num_boxes: int, seed: int | None = None) -> int:
    """Sample a bomb index uniformly from 1..N (inclusive)."""
    if num_boxes < 1:
        raise ValueError(f"num_boxes must be >= 1, got {num_boxes}")
    rng = random.Random(seed)
    return rng.randint(1, num_boxes)


def verify_bret_mechanics_enumeration(
    num_boxes: int,
    reward_per_box: int,
    k: int,
) -> tuple[int, float, float]:
    """Exhaustively enumerate all b in 1..N to verify:

    1. Exactly k positions trigger the bomb.
    2. Empirical average payoff matches theoretical expected payoff exactly.

    Returns:
    (hit_count, empirical_hit_prob, empirical_avg_payoff)
    """
    validate_bret_params(num_boxes, reward_per_box, k)
    hits = 0
    total_payoff = 0

    for b in range(1, num_boxes + 1):
        payoff, is_hit = compute_bret_payoff(b, k, reward_per_box)
        if is_hit:
            hits += 1
        total_payoff += payoff

    empirical_hit_prob = hits / num_boxes
    empirical_avg_payoff = total_payoff / num_boxes
    expected_payoff = reward_per_box * k * (1.0 - k / num_boxes)

    # Sanity checks
    assert hits == k, f"Expected {k} hits, got {hits}"
    assert abs(empirical_avg_payoff - expected_payoff) < 1e-9, (
        f"Empirical average {empirical_avg_payoff} != theoretical {expected_payoff}"
    )

    return hits, empirical_hit_prob, empirical_avg_payoff
