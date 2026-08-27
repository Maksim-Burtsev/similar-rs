"""Rust bindings to the `similar` diffing crate."""

from typing import Sequence

Opcode = tuple[str, int, int, int, int]
"""A single edit op: (tag, i1, i2, j1, j2), tag in equal/delete/insert/replace."""

def unified_diff(
    old: str,
    new: str,
    context_radius: int = 3,
    algorithm: str = "myers",
    header: tuple[str, str] | None = None,
) -> str:
    """Render a unified diff of two texts."""

def opcodes_str(
    kind: str,
    old: str,
    new: str,
    algorithm: str = "myers",
) -> list[Opcode]:
    """Diff two texts at granularity `kind` (lines, words or chars)."""

def opcodes_seq(
    old: Sequence[str],
    new: Sequence[str],
    algorithm: str = "myers",
) -> list[Opcode]:
    """Diff two sequences of strings."""

def get_close_matches(
    word: str,
    possibilities: Sequence[str],
    n: int = 3,
    cutoff: float = 0.6,
) -> list[str]:
    """Return the best `n` of `possibilities` scoring at least `cutoff`."""
