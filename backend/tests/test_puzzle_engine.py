"""Tests for Puzzle solver, clue evaluation, and actions."""

import pytest
from preference_lab.domain.puzzle import (
    Clue,
    PuzzlePublicStimulus,
    PuzzlePrivateData,
    solve_puzzle,
    validate_puzzle_stimulus,
    check_board,
    execute_next_step,
)


def get_teaching_puzzle():
    items = ["moon", "key", "star", "leaf"]
    clues = [
        Clue(
            clue_id="c1",
            clue_type="before",
            item_a="key",
            item_b="star",
            text_zh="鑰匙在星星左邊。",
        ),
        Clue(
            clue_id="c2",
            clue_type="adjacent",
            item_a="moon",
            item_b="key",
            text_zh="月亮與鑰匙相鄰。",
        ),
        Clue(
            clue_id="c3",
            clue_type="at_position",
            item_a="leaf",
            position=4,
            text_zh="葉子在第 4 格。",
        ),
        Clue(
            clue_id="c4",
            clue_type="not_at_position",
            item_a="key",
            position=1,
            text_zh="鑰匙不在第 1 格。",
        ),
    ]
    expected = ["moon", "key", "star", "leaf"]
    return items, clues, expected


def test_puzzle_teaching_example_unique_solution():
    items, clues, expected = get_teaching_puzzle()
    solutions = solve_puzzle(items, clues)
    assert len(solutions) == 1
    assert solutions[0] == expected


def test_puzzle_validation_success():
    items, clues, expected = get_teaching_puzzle()
    stimulus = PuzzlePublicStimulus(
        items=items,
        clues=clues,
        num_positions=4,
        item_labels={
            "moon": "月亮",
            "key": "鑰匙",
            "star": "星星",
            "leaf": "葉子",
        },
    )
    private_data = PuzzlePrivateData(
        expected_solution=expected,
        hint_text="注意葉子與鑰匙的限制，先推導出第 1 格只能放月亮。",
        source_clue_ids=["c3", "c4", "c2"],
    )
    # Should not raise
    validate_puzzle_stimulus(stimulus, private_data)


def test_puzzle_validation_detects_multiple_solutions():
    items = ["moon", "key", "star", "leaf"]
    # Only 1 clue: leaves multiple solutions
    clues = [
        Clue(
            clue_id="c1",
            clue_type="at_position",
            item_a="leaf",
            position=4,
            text_zh="葉子在第 4 格。",
        )
    ]
    stimulus = PuzzlePublicStimulus(items=items, clues=clues, num_positions=4)
    private_data = PuzzlePrivateData(
        expected_solution=["moon", "key", "star", "leaf"],
        hint_text="提示",
        source_clue_ids=["c1"],
    )
    with pytest.raises(ValueError, match="multiple solutions"):
        validate_puzzle_stimulus(stimulus, private_data)


def test_puzzle_validation_detects_no_solution():
    items = ["moon", "key", "star", "leaf"]
    # Contradicting clues
    clues = [
        Clue(clue_id="c1", clue_type="at_position", item_a="moon", position=1, text_zh="月亮在第1格"),
        Clue(clue_id="c2", clue_type="at_position", item_a="moon", position=2, text_zh="月亮在第2格"),
    ]
    stimulus = PuzzlePublicStimulus(items=items, clues=clues, num_positions=4)
    private_data = PuzzlePrivateData(
        expected_solution=["moon", "key", "star", "leaf"],
        hint_text="提示",
        source_clue_ids=["c1", "c2"],
    )
    with pytest.raises(ValueError, match="NO valid solution"):
        validate_puzzle_stimulus(stimulus, private_data)


def test_check_board_scenarios():
    items, clues, expected = get_teaching_puzzle()

    # Incomplete board
    is_solved, msg = check_board(items, [None, "key", "star", "leaf"], clues)
    assert not is_solved
    assert msg == "目前尚未符合全部線索"

    # Complete but incorrect
    is_solved, msg = check_board(items, ["star", "key", "moon", "leaf"], clues)
    assert not is_solved
    assert msg == "目前尚未符合全部線索"

    # Correct
    is_solved, msg = check_board(items, expected, clues)
    assert is_solved
    assert msg == "已完成"


def test_execute_next_step():
    expected = ["moon", "key", "star", "leaf"]

    # 1. Start with completely empty board
    board: list[str | None] = [None, None, None, None]
    pos, item, updated = execute_next_step(expected, board)
    assert pos == 1
    assert item == "moon"
    assert updated == ["moon", None, None, None]

    # 2. Board where slot 1 is moon, but slot 2 is empty and key is misplaced in slot 3
    board = ["moon", None, "key", None]
    pos, item, updated = execute_next_step(expected, board)
    assert pos == 2
    assert item == "key"
    # key should move to slot 2 (1-indexed), leaving slot 3 empty
    assert updated == ["moon", "key", None, None]

    # 3. Next step on this board
    pos, item, updated2 = execute_next_step(expected, updated)
    assert pos == 3
    assert item == "star"
    assert updated2 == ["moon", "key", "star", None]

    # 4. Final step
    pos, item, updated3 = execute_next_step(expected, updated2)
    assert pos == 4
    assert item == "leaf"
    assert updated3 == expected

    # 5. When fully correct, raises ValueError
    with pytest.raises(ValueError, match="already completely correct"):
        execute_next_step(expected, expected)
