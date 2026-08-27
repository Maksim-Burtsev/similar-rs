"""Drop-in replacement for stdlib difflib, accelerated by Rust (the `similar` crate).

SequenceMatcher, unified_diff and get_close_matches run on Rust opcodes.
Everything else is re-exported from the standard library unchanged.
"""

import warnings

# Absolute import from a submodule of `similar`: this is the stdlib difflib.
from difflib import (
    IS_CHARACTER_JUNK,
    IS_LINE_JUNK,
    Differ,
    HtmlDiff,
    Match,
    context_diff,
    diff_bytes,
    ndiff,
    restore,
)

from similar._similar import opcodes_seq, opcodes_str

__all__ = [
    "get_close_matches",
    "ndiff",
    "restore",
    "SequenceMatcher",
    "Differ",
    "IS_CHARACTER_JUNK",
    "IS_LINE_JUNK",
    "context_diff",
    "unified_diff",
    "diff_bytes",
    "HtmlDiff",
    "Match",
]


def _calculate_ratio(matches, length):
    if length:
        return 2.0 * matches / length
    return 1.0


def _check_seq(x):
    if isinstance(x, str) or (
        isinstance(x, (list, tuple)) and all(isinstance(e, str) for e in x)
    ):
        return
    raise TypeError(
        f"similar-rs supports only str or sequences of str, got {type(x).__name__}"
    )


class SequenceMatcher:
    """difflib.SequenceMatcher backed by the Rust `similar` crate.

    Differences from stdlib: `isjunk` is ignored (a RuntimeWarning is raised),
    `autojunk` is ignored silently, sequences must be str or sequences of str,
    and `find_longest_match` raises NotImplementedError.
    """

    def __init__(self, isjunk=None, a="", b="", autojunk=True, *, algorithm="myers"):
        if isjunk is not None:
            warnings.warn(
                "similar-rs ignores isjunk; results match SequenceMatcher(autojunk=False)",
                RuntimeWarning,
                stacklevel=2,
            )
        self._algorithm = algorithm
        self.a = self.b = None
        self.set_seqs(a, b)

    def set_seqs(self, a, b):
        """Set the two sequences to be compared."""
        self.set_seq1(a)
        self.set_seq2(b)

    def set_seq1(self, a):
        """Set the first sequence to be compared."""
        if a is self.a:
            return
        _check_seq(a)
        self.a = a
        self._opcodes = self._matching_blocks = None

    def set_seq2(self, b):
        """Set the second sequence to be compared."""
        if b is self.b:
            return
        _check_seq(b)
        self.b = b
        self._opcodes = self._matching_blocks = None
        self.fullbcount = None

    def find_longest_match(self, alo=0, ahi=None, blo=0, bhi=None):
        raise NotImplementedError(
            "similar-rs does not implement find_longest_match; "
            "use stdlib difflib for this"
        )

    def get_opcodes(self):
        """Return a list of (tag, i1, i2, j1, j2) tuples covering both inputs."""
        if self._opcodes is None:
            a, b = self.a, self.b
            if isinstance(a, str) and isinstance(b, str):
                self._opcodes = opcodes_str("chars", a, b, self._algorithm)
            else:
                self._opcodes = opcodes_seq(list(a), list(b), self._algorithm)
        return self._opcodes

    def get_matching_blocks(self):
        """Return a list of Match(a, b, size) triples, ending with a sentinel."""
        if self._matching_blocks is None:
            self._matching_blocks = [
                Match(i1, j1, i2 - i1)
                for tag, i1, i2, j1, j2 in self.get_opcodes()
                if tag == "equal"
            ]
            self._matching_blocks.append(Match(len(self.a), len(self.b), 0))
        return self._matching_blocks

    def get_grouped_opcodes(self, n=3):
        """Isolate change clusters by eliminating ranges with no changes."""
        # Copy: stdlib mutates its own opcode cache here, we keep ours intact.
        codes = list(self.get_opcodes())
        if not codes:
            codes = [("equal", 0, 1, 0, 1)]
        # Fixup leading and trailing groups if they show no changes.
        if codes[0][0] == "equal":
            tag, i1, i2, j1, j2 = codes[0]
            codes[0] = tag, max(i1, i2 - n), i2, max(j1, j2 - n), j2
        if codes[-1][0] == "equal":
            tag, i1, i2, j1, j2 = codes[-1]
            codes[-1] = tag, i1, min(i2, i1 + n), j1, min(j2, j1 + n)

        nn = n + n
        group = []
        for tag, i1, i2, j1, j2 in codes:
            # End the current group and start a new one whenever
            # there is a large range with no changes.
            if tag == "equal" and i2 - i1 > nn:
                group.append((tag, i1, min(i2, i1 + n), j1, min(j2, j1 + n)))
                yield group
                group = []
                i1, j1 = max(i1, i2 - n), max(j1, j2 - n)
            group.append((tag, i1, i2, j1, j2))
        if group and not (len(group) == 1 and group[0][0] == "equal"):
            yield group

    def ratio(self):
        """Similarity in [0, 1]: twice the matched size over the total size."""
        codes = self.get_opcodes()
        total = sum((i2 - i1) + (j2 - j1) for _, i1, i2, j1, j2 in codes)
        matches = sum(i2 - i1 for tag, i1, i2, _, _ in codes if tag == "equal")
        return _calculate_ratio(matches, total)

    def quick_ratio(self):
        """Return an upper bound on ratio() relatively quickly."""
        if self.fullbcount is None:
            self.fullbcount = fullbcount = {}
            for elt in self.b:
                fullbcount[elt] = fullbcount.get(elt, 0) + 1
        fullbcount = self.fullbcount
        avail = {}
        availhas, matches = avail.__contains__, 0
        for elt in self.a:
            if availhas(elt):
                numb = avail[elt]
            else:
                numb = fullbcount.get(elt, 0)
            avail[elt] = numb - 1
            if numb > 0:
                matches = matches + 1
        return _calculate_ratio(matches, len(self.a) + len(self.b))

    def real_quick_ratio(self):
        """Return an upper bound on ratio() very quickly."""
        la, lb = len(self.a), len(self.b)
        return _calculate_ratio(min(la, lb), la + lb)


def _check_types(a, b, *args):
    if a and not isinstance(a[0], str):
        raise TypeError(
            "lines to compare must be str, not %s (%r)" % (type(a[0]).__name__, a[0])
        )
    if b and not isinstance(b[0], str):
        raise TypeError(
            "lines to compare must be str, not %s (%r)" % (type(b[0]).__name__, b[0])
        )
    for arg in args:
        if not isinstance(arg, str):
            raise TypeError("all arguments must be str, not: %r" % (arg,))


def _format_range_unified(start, stop):
    'Convert range to the "ed" format'
    beginning = start + 1  # lines start numbering with one
    length = stop - start
    if length == 1:
        return "{}".format(beginning)
    if not length:
        beginning -= 1  # empty ranges begin at line just before the range
    return "{},{}".format(beginning, length)


def unified_diff(
    a,
    b,
    fromfile="",
    tofile="",
    fromfiledate="",
    tofiledate="",
    n=3,
    lineterm="\n",
):
    """Compare two sequences of lines; generate the delta as a unified diff."""
    _check_types(a, b, fromfile, tofile, fromfiledate, tofiledate, lineterm)
    started = False
    for group in SequenceMatcher(None, a, b).get_grouped_opcodes(n):
        if not started:
            started = True
            fromdate = "\t{}".format(fromfiledate) if fromfiledate else ""
            todate = "\t{}".format(tofiledate) if tofiledate else ""
            yield "--- {}{}{}".format(fromfile, fromdate, lineterm)
            yield "+++ {}{}{}".format(tofile, todate, lineterm)

        first, last = group[0], group[-1]
        file1_range = _format_range_unified(first[1], last[2])
        file2_range = _format_range_unified(first[3], last[4])
        yield "@@ -{} +{} @@{}".format(file1_range, file2_range, lineterm)

        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for line in a[i1:i2]:
                    yield " " + line
                continue
            if tag in {"replace", "delete"}:
                for line in a[i1:i2]:
                    yield "-" + line
            if tag in {"replace", "insert"}:
                for line in b[j1:j2]:
                    yield "+" + line
