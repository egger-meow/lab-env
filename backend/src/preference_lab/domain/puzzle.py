"""Puzzle Hints domain logic and pure solver according to PREFERENCE_LAB_SPEC.md."""

from __future__ import annotations

import itertools
from typing import Any, Literal
from pydantic import BaseModel, Field


class Clue(BaseModel):
    clue_id: str
    clue_type: Literal["before", "adjacent", "at_position", "not_at_position"]
    item_a: str
    item_b: str | None = None
    position: int | None = None  # 1-indexed
    text_zh: str


class PuzzlePublicStimulus(BaseModel):
    items: list[str]  # 4 to 6 unique items
    item_labels: dict[str, str] = Field(default_factory=dict)
    clues: list[Clue]
    num_positions: int


class PuzzlePrivateData(BaseModel):
    expected_solution: list[str]  # 1-indexed mapping [item_at_1, item_at_2, ...]
    hint_text: str
    source_clue_ids: list[str]


def evaluate_clue(arrangement: tuple[str, ...], clue: Clue) -> bool:
    """Evaluate if an arrangement (0-indexed tuple of items) satisfies a clue.

    Position in clue is 1-indexed (1..n).
    """
    pos_map = {item: i + 1 for i, item in enumerate(arrangement)}
    pos_a = pos_map.get(clue.item_a)
    if pos_a is None:
        return False

    if clue.clue_type == "before":
        if clue.item_b is None:
            return False
        pos_b = pos_map.get(clue.item_b)
        return pos_b is not None and pos_a < pos_b

    elif clue.clue_type == "adjacent":
        if clue.item_b is None:
            return False
        pos_b = pos_map.get(clue.item_b)
        return pos_b is not None and abs(pos_a - pos_b) == 1

    elif clue.clue_type == "at_position":
        if clue.position is None:
            return False
        return pos_a == clue.position

    elif clue.clue_type == "not_at_position":
        if clue.position is None:
            return False
        return pos_a != clue.position

    return False


def solve_puzzle(items: list[str], clues: list[Clue]) -> list[list[str]]:
    """Enumerate all permutations and return all valid solutions."""
    valid_solutions: list[list[str]] = []
    for perm in itertools.permutations(items):
        if all(evaluate_clue(perm, clue) for clue in clues):
            valid_solutions.append(list(perm))
    return valid_solutions


def validate_puzzle_stimulus(
    stimulus: PuzzlePublicStimulus,
    private_data: PuzzlePrivateData,
) -> None:
    """Strictly validate puzzle integrity.

    Must satisfy:
    1. 4 to 6 items, unique.
    2. Expected solution matches items.
    3. Exactly ONE unique solution found by solver.
    4. Unique solution strictly equals expected_solution.
    5. hint_text is non-empty and source_clue_ids exist in clues.
    """
    items = stimulus.items
    n = len(items)
    if not (4 <= n <= 6):
        raise ValueError(f"Puzzle must have 4 to 6 items, got {n}")
    if len(set(items)) != n:
        raise ValueError(f"Items must be unique: {items}")
    if stimulus.num_positions != n:
        raise ValueError(f"num_positions ({stimulus.num_positions}) must equal item count ({n})")

    if len(private_data.expected_solution) != n:
        raise ValueError(
            f"Expected solution length ({len(private_data.expected_solution)}) must equal {n}"
        )
    if sorted(private_data.expected_solution) != sorted(items):
        raise ValueError("Expected solution does not contain the exact set of items")

    all_clue_ids = {c.clue_id for c in stimulus.clues}
    if not private_data.source_clue_ids:
        raise ValueError("source_clue_ids cannot be empty")
    for cid in private_data.source_clue_ids:
        if cid not in all_clue_ids:
            raise ValueError(f"source_clue_id '{cid}' not found in puzzle clues")
    if not private_data.hint_text.strip():
        raise ValueError("hint_text cannot be empty")

    solutions = solve_puzzle(items, stimulus.clues)
    if len(solutions) == 0:
        raise ValueError(f"Puzzle has NO valid solution for items={items}")
    if len(solutions) > 1:
        raise ValueError(f"Puzzle has multiple solutions ({len(solutions)}), expected unique solution")
    if solutions[0] != private_data.expected_solution:
        raise ValueError(
            f"Solver solution {solutions[0]} does not match expected_solution {private_data.expected_solution}"
        )


def check_board(
    items: list[str],
    board: list[str | None],
    clues: list[Clue],
) -> tuple[bool, str]:
    """Check a player's board submission.

    Returns:
    (True, "已完成") if complete and correct.
    (False, "目前尚未符合全部線索") if complete but invalid or incomplete.
    """
    n = len(items)
    if len(board) != n:
        return False, "目前尚未符合全部線索"
    if any(slot is None for slot in board):
        return False, "目前尚未符合全部線索"

    filled_board = tuple(slot for slot in board if slot is not None)
    if len(set(filled_board)) != n or set(filled_board) != set(items):
        return False, "目前尚未符合全部線索"

    is_valid = all(evaluate_clue(filled_board, clue) for clue in clues)
    if is_valid:
        return True, "已完成"
    return False, "目前尚未符合全部線索"


def execute_next_step(
    expected_solution: list[str],
    current_board: list[str | None],
) -> tuple[int, str, list[str | None]]:
    """Execute the 'next_step' action.

    Find the leftmost position (1..n) that is currently empty or incorrect in current_board.
    Reveal the correct item at that position.
    If that item is already placed elsewhere on current_board, remove it from the old slot.

    Returns:
    (revealed_position, revealed_item, updated_board)
    where revealed_position is 1-indexed.
    """
    n = len(expected_solution)
    board = list(current_board)
    if len(board) < n:
        board.extend([None] * (n - len(board)))
    elif len(board) > n:
        board = board[:n]

    target_idx: int | None = None
    for idx in range(n):
        if board[idx] != expected_solution[idx]:
            target_idx = idx
            break

    if target_idx is None:
        raise ValueError("Board is already completely correct; cannot execute next_step")

    revealed_item = expected_solution[target_idx]
    # Remove revealed_item from any other slot
    for idx in range(n):
        if idx != target_idx and board[idx] == revealed_item:
            board[idx] = None

    board[target_idx] = revealed_item
    return target_idx + 1, revealed_item, board
