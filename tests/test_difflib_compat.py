"""Compatibility of `similar.difflib` with stdlib difflib."""

import difflib as stdlib
import heapq
import re
from collections import Counter, UserList

import pytest
from hypothesis import given
from hypothesis import strategies as st

from similar import difflib as ours

# --- strategies -----------------------------------------------------------

texts = st.text(alphabet="ab\n", max_size=40)
unicode_texts = st.text(max_size=20)
words = st.text(alphabet="abcd", min_size=2, max_size=4)
seqs = st.lists(words, max_size=30)
line_seqs = st.lists(words.map(lambda s: s + "\n"), max_size=30)


def check_opcodes(a, b, codes):
    """Coverage, contiguity and content invariants of a difflib opcode list."""
    if not codes:
        assert len(a) == len(b) == 0
        return
    assert codes[0][1] == 0 and codes[0][3] == 0
    assert codes[-1][2] == len(a) and codes[-1][4] == len(b)
    for (_, _, pi2, _, pj2), (_, i1, _, j1, _) in zip(codes, codes[1:]):
        assert (pi2, pj2) == (i1, j1)
    rebuilt = []
    for tag, i1, i2, j1, j2 in codes:
        assert tag in {"equal", "delete", "insert", "replace"}
        if tag == "equal":
            assert list(a[i1:i2]) == list(b[j1:j2])
            rebuilt.extend(a[i1:i2])
        elif tag == "delete":
            assert j1 == j2
        elif tag == "insert":
            assert i1 == i2
            rebuilt.extend(b[j1:j2])
        else:
            rebuilt.extend(b[j1:j2])
    assert rebuilt == list(b)


# --- opcodes --------------------------------------------------------------


@given(seqs, seqs)
def test_opcodes_invariants_sequences(a, b):
    check_opcodes(a, b, ours.SequenceMatcher(a=a, b=b).get_opcodes())


@given(texts, texts)
def test_opcodes_invariants_str(a, b):
    check_opcodes(a, b, ours.SequenceMatcher(a=a, b=b).get_opcodes())


@given(unicode_texts, unicode_texts)
def test_opcodes_invariants_unicode(a, b):
    check_opcodes(a, b, ours.SequenceMatcher(a=a, b=b).get_opcodes())


def test_opcodes_empty_inputs():
    assert ours.SequenceMatcher(a="", b="").get_opcodes() == []
    assert ours.SequenceMatcher(a=[], b=[]).get_opcodes() == []
    assert stdlib.SequenceMatcher(a="", b="").get_opcodes() == []


@given(seqs)
def test_opcodes_identical_is_single_equal(a):
    codes = ours.SequenceMatcher(a=a, b=list(a)).get_opcodes()
    assert codes == ([("equal", 0, len(a), 0, len(a))] if a else [])


def test_algorithm_reaches_the_backend():
    # 'ab' vs 'baa' is a minimal input where myers and patience disagree.
    myers = ours.SequenceMatcher(a="ab", b="baa", algorithm="myers").get_opcodes()
    patience = ours.SequenceMatcher(a="ab", b="baa", algorithm="patience").get_opcodes()
    check_opcodes("ab", "baa", myers)
    check_opcodes("ab", "baa", patience)
    assert myers != patience


def test_unknown_algorithm_rejected():
    with pytest.raises(ValueError):
        ours.SequenceMatcher(a="x", b="y", algorithm="bogus").get_opcodes()


@pytest.mark.parametrize("setter", ["set_seq1", "set_seq2"])
def test_set_seq_invalidates_materialised_caches(setter):
    m = ours.SequenceMatcher(a=list("abc"), b=list("abc"))
    assert m.get_opcodes() and m.ratio() == 1.0 and m.quick_ratio() == 1.0
    getattr(m, setter)(list("xyz"))
    assert m.ratio() == 0.0
    assert m.quick_ratio() == 0.0
    assert m.get_opcodes() != [("equal", 0, 3, 0, 3)]
    assert m.get_matching_blocks() == [stdlib.Match(3, 3, 0)]


def test_grouped_opcodes_does_not_corrupt_cache():
    m = ours.SequenceMatcher(a=list("abcdefghij"), b=list("abcdefghij"))
    codes = list(m.get_opcodes())
    list(m.get_grouped_opcodes())
    assert m.get_opcodes() == codes


# --- matching blocks ------------------------------------------------------


@given(seqs, seqs)
def test_matching_blocks(a, b):
    blocks = ours.SequenceMatcher(a=a, b=b).get_matching_blocks()
    assert blocks[-1] == stdlib.Match(len(a), len(b), 0)
    assert all(isinstance(x, stdlib.Match) for x in blocks)
    for blk in blocks[:-1]:
        assert blk.size > 0
        assert a[blk.a : blk.a + blk.size] == b[blk.b : blk.b + blk.size]
    for prev, cur in zip(blocks, blocks[1:]):
        assert prev.a + prev.size <= cur.a and prev.b + prev.size <= cur.b


# --- ratios ---------------------------------------------------------------


@given(seqs, seqs)
def test_ratio_matches_own_opcodes(a, b):
    m = ours.SequenceMatcher(a=a, b=b)
    codes = m.get_opcodes()
    total = sum((i2 - i1) + (j2 - j1) for _, i1, i2, j1, j2 in codes)
    matches = sum(i2 - i1 for tag, i1, i2, _, _ in codes if tag == "equal")
    assert m.ratio() == (2.0 * matches / total if total else 1.0)
    assert 0.0 <= m.ratio() <= 1.0


def test_known_ratio():
    assert ours.SequenceMatcher(None, "kitten", "sitting").ratio() == 0.6153846153846154
    assert stdlib.SequenceMatcher(None, "kitten", "sitting").ratio() == (
        ours.SequenceMatcher(None, "kitten", "sitting").ratio()
    )


@given(seqs)
def test_ratio_identical_is_one(a):
    assert ours.SequenceMatcher(a=a, b=list(a)).ratio() == 1.0


@given(
    st.lists(st.sampled_from("ab"), min_size=1, max_size=10),
    st.lists(st.sampled_from("cd"), min_size=1, max_size=10),
)
def test_ratio_disjoint_is_zero(a, b):
    assert ours.SequenceMatcher(a=a, b=b).ratio() == 0.0


@given(seqs, seqs)
def test_quick_ratios_match_stdlib(a, b):
    mine = ours.SequenceMatcher(a=a, b=b)
    theirs = stdlib.SequenceMatcher(None, a, b, autojunk=False)
    assert mine.quick_ratio() == theirs.quick_ratio()
    assert mine.real_quick_ratio() == theirs.real_quick_ratio()


# --- unified_diff ---------------------------------------------------------

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def apply_unified(a, diff):
    """Apply our unified diff output to `a`, returning the patched sequence."""
    out, pos, seen_hunk = [], 0, False
    for line in diff:
        if not seen_hunk and (line.startswith("--- ") or line.startswith("+++ ")):
            continue
        m = HUNK.match(line)
        if m:
            seen_hunk = True
            start = int(m.group(1))
            count = 1 if m.group(2) is None else int(m.group(2))
            idx = start - 1 if count else start
            out.extend(a[pos:idx])
            pos = idx
            continue
        tag, text = line[0], line[1:]
        if tag == " ":
            assert text == a[pos]
            out.append(a[pos])
            pos += 1
        elif tag == "-":
            assert text == a[pos]
            pos += 1
        else:
            out.append(text)
    out.extend(a[pos:])
    return out


@given(line_seqs, line_seqs, st.integers(min_value=0, max_value=5))
def test_unified_diff_applies_as_patch(a, b, n):
    assert apply_unified(a, ours.unified_diff(a, b, n=n)) == b


TEN = [f"line{i}\n" for i in range(10)]
GOLDEN = [
    ([], [], {}),
    (["a\n", "b\n"], ["a\n", "b\n"], {}),
    (["x\n", "y\n"], ["p\n", "q\n"], {}),
    (TEN, TEN[:5] + ["NEW\n"] + TEN[5:], {}),
    (TEN, TEN[:5] + ["NEW\n"] + TEN[5:], {"n": 0}),
    (
        ["a\n", "b\n"],
        ["a\n", "c\n"],
        {"fromfile": "f", "tofile": "t", "fromfiledate": "D1", "tofiledate": "D2"},
    ),
    (["a", "b"], ["a", "c"], {"lineterm": ""}),
    ([], ["a\n"], {"fromfile": "old", "tofile": "new"}),
    (["a\n"], [], {}),
]


@pytest.mark.parametrize("a,b,kw", GOLDEN)
def test_unified_diff_matches_stdlib(a, b, kw):
    assert list(ours.unified_diff(a, b, **kw)) == list(stdlib.unified_diff(a, b, **kw))


def test_unified_diff_identical_is_empty():
    assert list(ours.unified_diff(TEN, TEN)) == []


# --- get_close_matches ----------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ("appel", ["ape", "apple", "peach", "puppy"]),
        ("appel", ["ape", "apple", "peach", "puppy"], 1),
        ("x", []),
        ("a", ["a", "a", "a"], 3, 0.0),
        ("", ["", "a"]),
    ],
)
def test_get_close_matches_matches_stdlib(args):
    assert ours.get_close_matches(*args) == stdlib.get_close_matches(*args)


@given(
    st.text(alphabet="abc", max_size=6),
    st.lists(st.text(alphabet="abc", max_size=6), max_size=10),
    st.integers(min_value=1, max_value=5),
    st.floats(min_value=0.0, max_value=1.0),
)
def test_get_close_matches_properties(word, possibilities, n, cutoff):
    got = ours.get_close_matches(word, possibilities, n, cutoff)
    assert len(got) <= n
    remaining = list(possibilities)
    for cand in got:
        remaining.remove(cand)  # raises if not a member
    ratios = [ours.SequenceMatcher(a=word, b=c).ratio() for c in got]
    assert all(r >= cutoff for r in ratios)
    assert ratios == sorted(ratios, reverse=True)


def test_get_close_matches_tie_break_matches_stdlib():
    # Equal ratios: difflib's heapq.nlargest compares the strings, larger wins.
    args = ("ab", ["ax", "ay", "az"], 2, 0.0)
    assert ours.get_close_matches(*args) == ["az", "ay"]
    assert ours.get_close_matches(*args) == stdlib.get_close_matches(*args)


def _scored_by_brute_force(word, possibilities, n, cutoff):
    scored = [
        (ours.SequenceMatcher(a=cand, b=word).ratio(), cand) for cand in possibilities
    ]
    return [c for _, c in heapq.nlargest(n, [t for t in scored if t[0] >= cutoff])]


@given(
    st.text(alphabet="abcde", max_size=6),
    st.lists(st.text(alphabet="abcde", max_size=6), max_size=8),
    st.integers(min_value=1, max_value=4),
    st.floats(min_value=0.0, max_value=1.0),
)
def test_get_close_matches_skips_only_hopeless_candidates(word, possibilities, n, cutoff):
    # get_close_matches drops candidates by cheap upper bounds before diffing them.
    # Scoring every candidate the slow way must give the very same answer.
    assert ours.get_close_matches(word, possibilities, n, cutoff) == (
        _scored_by_brute_force(word, possibilities, n, cutoff)
    )


@given(st.text(alphabet="abcde", max_size=12), st.text(alphabet="abcde", max_size=12))
def test_cheap_ratio_bounds_never_undercut_the_real_ratio(a, b):
    # The bounds those skips rest on: neither may ever fall below ratio().
    total = len(a) + len(b)
    if not total:
        return
    real = ours.SequenceMatcher(a=a, b=b).ratio()
    assert 2.0 * min(len(a), len(b)) / total >= real
    assert 2.0 * sum((Counter(a) & Counter(b)).values()) / total >= real


@pytest.mark.parametrize("kw,msg", [({"n": 0}, "n must be"), ({"cutoff": 1.5}, "cutoff")])
def test_get_close_matches_validation(kw, msg):
    with pytest.raises(ValueError) as ours_exc:
        ours.get_close_matches("a", ["b"], **kw)
    with pytest.raises(ValueError) as std_exc:
        stdlib.get_close_matches("a", ["b"], **kw)
    assert str(ours_exc.value) == str(std_exc.value)


# --- lone surrogates fall back to stdlib -----------------------------------


def test_sequence_matcher_handles_lone_surrogates():
    codes = ours.SequenceMatcher(None, "\ud800x", "x").get_opcodes()
    check_opcodes("\ud800x", "x", codes)
    assert codes == stdlib.SequenceMatcher(None, "\ud800x", "x").get_opcodes()


def test_get_close_matches_handles_lone_surrogates():
    args = ("\ud800a", ["\ud800b", "zz"], 3, 0.0)
    assert ours.get_close_matches(*args) == stdlib.get_close_matches(*args)


def test_diff_bytes_handles_non_ascii():
    # diff_bytes decodes with surrogateescape, so \xe9 arrives as a surrogate.
    got = list(ours.diff_bytes(ours.unified_diff, [b"caf\xe9\n"], [b"cafe\n"], b"f", b"t"))
    assert got == list(
        stdlib.diff_bytes(stdlib.unified_diff, [b"caf\xe9\n"], [b"cafe\n"], b"f", b"t")
    )


# --- arbitrary sequences of str --------------------------------------------


def test_sequence_matcher_accepts_userlist():
    m = ours.SequenceMatcher(None, UserList(["a\n", "b\n"]), UserList(["a\n", "c\n"]))
    assert m.ratio() == 0.5
    assert m.quick_ratio() == 0.5
    check_opcodes(list(m.a), list(m.b), m.get_opcodes())


def test_unified_diff_accepts_userlist():
    a, b = UserList(["a\n", "b\n"]), UserList(["a\n", "c\n"])
    assert list(ours.unified_diff(a, b)) == list(stdlib.unified_diff(a, b))


# --- junk arguments and stdlib delegation ---------------------------------


def test_isjunk_warns():
    with pytest.warns(RuntimeWarning, match="ignores isjunk"):
        ours.SequenceMatcher(bool, "abc", "abd")


@pytest.mark.parametrize("autojunk", [True, False])
def test_autojunk_silent(recwarn, autojunk):
    ours.SequenceMatcher(None, "abc", "abd", autojunk)
    assert not recwarn.list


@pytest.mark.parametrize(
    "a, b",
    [
        ("abxcd", "abycd"),
        ("", ""),
        ("abc", ""),
        (["a\n", "b\n", "c\n"], ["x\n", "b\n", "c\n"]),
        # len(b) >= 200 with popular elements: autojunk=True would purge them
        # and pick a different block, pinning the documented autojunk=False.
        (
            ["p\n"] * 50 + ["u1\n", "u2\n", "u3\n"],
            ["z\n"] * 100 + ["p\n"] * 150 + ["q\n", "u1\n", "u2\n", "u3\n"],
        ),
    ],
)
def test_find_longest_match_matches_stdlib(a, b):
    la, lb = len(a), len(b)
    for args in [(), (0, None, 0, None), (0, la, 0, lb), (1, la, 0, max(lb - 1, 0))]:
        expected = stdlib.SequenceMatcher(
            None, a, b, autojunk=False
        ).find_longest_match(*args)
        assert ours.SequenceMatcher(a=a, b=b).find_longest_match(*args) == expected
    kwargs = dict(alo=0, ahi=la, blo=0, bhi=lb)
    expected = stdlib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(
        **kwargs
    )
    assert ours.SequenceMatcher(a=a, b=b).find_longest_match(**kwargs) == expected


def test_find_longest_match_after_set_seqs():
    sm = ours.SequenceMatcher(a="abcd", b="abcd")
    assert sm.find_longest_match() == stdlib.Match(0, 0, 4)
    sm.set_seq2("zzcd")
    assert sm.find_longest_match() == stdlib.Match(2, 2, 2)
    sm.set_seq1("zzzd")
    assert sm.find_longest_match() == stdlib.Match(0, 0, 2)


# --- re-exports -----------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Differ",
        "HtmlDiff",
        "Match",
        "IS_CHARACTER_JUNK",
        "IS_LINE_JUNK",
        "context_diff",
        "diff_bytes",
        "ndiff",
        "restore",
    ],
)
def test_reexports_are_stdlib(name):
    assert getattr(ours, name) is getattr(stdlib, name)


def test_all_matches_stdlib():
    assert ours.__all__ == stdlib.__all__
