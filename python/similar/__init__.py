from importlib.metadata import version

from similar._similar import opcodes_str, unified_diff

__version__ = version("similar-rs")
__all__ = ["unified_diff", "TextDiff", "__version__"]

_GRANULARITIES = ("lines", "words", "chars")


class TextDiff:
    """A diff between two texts, computed once at construction.

    Text holding lone surrogates raises UnicodeEncodeError: it cannot cross
    into Rust. Use `similar.difflib.SequenceMatcher`, which falls back.
    """

    def __init__(self, old, new, *, algorithm="myers", granularity="lines"):
        if granularity not in _GRANULARITIES:
            raise ValueError(
                f"unknown granularity {granularity!r}; expected one of: "
                + ", ".join(_GRANULARITIES)
            )
        self._ops = opcodes_str(granularity, old, new, algorithm)

    def ops(self):
        """Return [(tag, (i1, i2), (j1, j2)), ...] covering both inputs."""
        return [(tag, (i1, i2), (j1, j2)) for tag, i1, i2, j1, j2 in self._ops]

    def ratio(self):
        """Similarity in [0, 1]: twice the matched size over the total size."""
        total = sum((i2 - i1) + (j2 - j1) for _, i1, i2, j1, j2 in self._ops)
        if total == 0:
            return 1.0
        matches = sum(i2 - i1 for tag, i1, i2, _, _ in self._ops if tag == "equal")
        return 2.0 * matches / total
