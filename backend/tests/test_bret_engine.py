"""Tests for BRET Discrete-Static mechanics and mathematical correctness."""

import pytest
from preference_lab.domain.bret import (
    get_bret_action_stats,
    compute_bret_payoff,
    sample_bomb_index,
    verify_bret_mechanics_enumeration,
    validate_bret_params,
)


def test_bret_teaching_round_values():
    """Verify teaching round from Section 6.3 of spec:

    N=100, r=1, k=[0, 20, 40, 60].
    """
    N = 100
    r = 1

    stats_0 = get_bret_action_stats(N, r, 0)
    assert stats_0.hit_probability == 0.0
    assert stats_0.payoff_if_safe == 0
    assert stats_0.payoff_if_hit == 0
    assert stats_0.expected_payoff == 0.0

    stats_20 = get_bret_action_stats(N, r, 20)
    assert stats_20.hit_probability == 0.2
    assert stats_20.payoff_if_safe == 20
    assert stats_20.payoff_if_hit == 0
    assert abs(stats_20.expected_payoff - 16.0) < 1e-9

    stats_40 = get_bret_action_stats(N, r, 40)
    assert stats_40.hit_probability == 0.4
    assert stats_40.payoff_if_safe == 40
    assert stats_40.payoff_if_hit == 0
    assert abs(stats_40.expected_payoff - 24.0) < 1e-9

    stats_60 = get_bret_action_stats(N, r, 60)
    assert stats_60.hit_probability == 0.6
    assert stats_60.payoff_if_safe == 60
    assert stats_60.payoff_if_hit == 0
    assert abs(stats_60.expected_payoff - 24.0) < 1e-9


def test_bret_exhaustive_enumeration_matches_expectation():
    """Test verification theorem: b=1..N enumeration produces exactly k hits and matches expectation."""
    test_cases = [
        (10, 1, 0),
        (10, 1, 3),
        (10, 1, 10),
        (100, 1, 0),
        (100, 1, 20),
        (100, 1, 40),
        (100, 1, 60),
        (100, 1, 100),
        (100, 2, 20),
        (100, 2, 50),
    ]
    for N, r, k in test_cases:
        hits, emp_p, emp_ev = verify_bret_mechanics_enumeration(N, r, k)
        assert hits == k
        assert abs(emp_p - (k / N)) < 1e-9
        expected = r * k * (1.0 - k / N)
        assert abs(emp_ev - expected) < 1e-9


def test_bret_payoff_function_boundary():
    # k=0: no matter where bomb is, payoff is 0, never hit
    payoff, is_hit = compute_bret_payoff(bomb_index=50, k=0, reward_per_box=1)
    assert payoff == 0
    assert not is_hit

    # k=100 with N=100: bomb is at 50 <= 100 -> hit! payoff=0
    payoff, is_hit = compute_bret_payoff(bomb_index=50, k=100, reward_per_box=1)
    assert payoff == 0
    assert is_hit

    # b=21, k=20 -> safe! payoff = 20 * 2 = 40
    payoff, is_hit = compute_bret_payoff(bomb_index=21, k=20, reward_per_box=2)
    assert payoff == 40
    assert not is_hit

    # b=20, k=20 -> hit! payoff = 0
    payoff, is_hit = compute_bret_payoff(bomb_index=20, k=20, reward_per_box=2)
    assert payoff == 0
    assert is_hit


def test_bret_validation_errors():
    with pytest.raises(ValueError, match="reward_per_box must be >= 1"):
        validate_bret_params(100, 0, 20)

    with pytest.raises(ValueError, match="reward_per_box must be >= 1"):
        validate_bret_params(100, -1, 20)

    with pytest.raises(ValueError, match="k must be >= 0"):
        validate_bret_params(100, 1, -5)

    with pytest.raises(ValueError, match="k must be <= 100"):
        validate_bret_params(100, 1, 101)

    with pytest.raises(ValueError, match="num_boxes must be >= 1"):
        validate_bret_params(0, 1, 0)

    # Counterexamples from Review: Reject floats
    with pytest.raises(TypeError, match="must be a strict integer"):
        validate_bret_params(100, 1.5, 20)

    with pytest.raises(TypeError, match="must be a strict integer"):
        validate_bret_params(100, 1, 20.5)

    # Counterexamples from Review: Reject booleans
    with pytest.raises(TypeError, match="must be a strict integer"):
        validate_bret_params(100, True, 20)

    with pytest.raises(TypeError, match="must be a strict integer"):
        validate_bret_params(True, 1, 20)

    with pytest.raises(TypeError, match="must be a strict integer"):
        validate_bret_params(100, 1, False)

    # compute_bret_payoff rejects invalid/negative reward or bomb_index
    with pytest.raises(ValueError, match="reward_per_box must be >= 1"):
        compute_bret_payoff(bomb_index=21, k=20, reward_per_box=-1)

    with pytest.raises(ValueError, match="bomb_index must be >= 1"):
        compute_bret_payoff(bomb_index=0, k=20, reward_per_box=1)

    with pytest.raises(ValueError, match="bomb_index must be <= 100"):
        compute_bret_payoff(bomb_index=101, k=20, reward_per_box=1, num_boxes=100)


def test_bret_bomb_sampling_determinism():
    N = 100
    b1 = sample_bomb_index(N, seed=42)
    b2 = sample_bomb_index(N, seed=42)
    assert b1 == b2
    assert 1 <= b1 <= N

    # Multiple draws stay in 1..N
    for seed in range(50):
        b = sample_bomb_index(N, seed=seed)
        assert 1 <= b <= N
