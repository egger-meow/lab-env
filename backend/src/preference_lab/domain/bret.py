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


def _validate_strict_int(
    val: Any,
    name: str,
    min_val: int | None = None,
    max_val: int | None = None,
) -> None:
    """Validate that val is strictly an int (not bool, not float) and within bounds."""
    if isinstance(val, bool) or not isinstance(val, int):
        raise TypeError(f"{name} must be a strict integer, got {type(val).__name__} ({val})")
    if min_val is not None and val < min_val:
        raise ValueError(f"{name} must be >= {min_val}, got {val}")
    if max_val is not None and val > max_val:
        raise ValueError(f"{name} must be <= {max_val}, got {val}")


def validate_bret_params(num_boxes: int, reward_per_box: int, k: int) -> None:
    """Validate BRET parameters strictly.

    N >= 1 (strict int), r >= 1 (strict int), 0 <= k <= N (strict int).
    Note: k=0 and k=N are valid boundary values.
    """
    _validate_strict_int(num_boxes, "num_boxes", min_val=1)
    _validate_strict_int(reward_per_box, "reward_per_box", min_val=1)
    _validate_strict_int(k, "k", min_val=0, max_val=num_boxes)


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


def compute_bret_payoff(
    bomb_index: int,
    k: int,
    reward_per_box: int,
    num_boxes: int | None = None,
) -> tuple[int, bool]:
    """Calculate payoff given bomb index b, collection k, reward r, and optional N.

    Rules:
    - b in 1..N (strictly integer, >= 1, <= N if num_boxes provided)
    - 0 <= k <= N (strictly integer)
    - r >= 1 (strictly integer)
    - If b <= k: hit bomb! Payoff = 0
    - If b > k: safe! Payoff = r * k

    Returns:
    (payoff, is_bomb_hit)
    """
    _validate_strict_int(reward_per_box, "reward_per_box", min_val=1)
    _validate_strict_int(k, "k", min_val=0, max_val=num_boxes if num_boxes is not None else None)
    _validate_strict_int(
        bomb_index,
        "bomb_index",
        min_val=1,
        max_val=num_boxes if num_boxes is not None else None,
    )

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
