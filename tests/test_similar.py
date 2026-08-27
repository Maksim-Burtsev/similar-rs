import re

import pytest

from similar import TextDiff, unified_diff

ALGORITHMS = ["myers", "raw-myers", "patience", "lcs", "hunt", "histogram"]

OLD = "alpha\nbravo\ncharlie\ndelta\necho\n"
NEW = "alpha\nbravo\ncharlie\nDELTA\necho\n"


def tokenize(text, granularity):
    """Mirror of the Rust-side tokenizers, so tests can check ops against content."""
    if granularity == "lines":
        return text.splitlines(keepends=True)
    if granularity == "chars":
        return list(text)
    return re.findall(r"\s+|\S+", text)  # words: runs of whitespace / non-whitespace


# --- unified_diff ---------------------------------------------------------


def test_unified_diff_basic():
    out = unified_diff("a\nb\n", "a\nc\n")
    assert "@@" in out
    assert "-b" in out and "+c" in out


def test_unified_diff_context_radius():
    narrow = unified_diff(OLD, NEW, 0)
    wide = unified_diff(OLD, NEW, 3)
    assert len(narrow) < len(wide)
    assert "alpha" not in narrow and "alpha" in wide


def test_unified_diff_header():
    out = unified_diff("a\n", "b\n", 3, "myers", ("a", "b"))
    assert out.startswith("--- a\n+++ b\n")


def test_unified_diff_empty_inputs():
    assert unified_diff("", "") == ""


def test_unified_diff_identical_is_empty():
    assert unified_diff(OLD, OLD) == ""


def test_unified_diff_unknown_algorithm():
    with pytest.raises(ValueError):
        unified_diff("a\n", "b\n", 3, "bogus")


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_unified_diff_all_algorithms(algorithm):
    out = unified_diff(OLD, NEW, 3, algorithm)
    assert "@@" in out and "+DELTA" in out


# --- TextDiff -------------------------------------------------------------


@pytest.mark.parametrize("granularity", ["lines", "words", "chars"])
def test_ops_cover_inputs_contiguously(granularity):
    ops = TextDiff(OLD, NEW, granularity=granularity).ops()
    i, j = 0, 0
    for _, (i1, i2), (j1, j2) in ops:
        assert (i1, j1) == (i, j)
        assert i2 >= i1 and j2 >= j1
        i, j = i2, j2
    assert i == len(tokenize(OLD, granularity))
    assert j == len(tokenize(NEW, granularity))


@pytest.mark.parametrize("granularity", ["lines", "words", "chars"])
def test_equal_ops_have_equal_content(granularity):
    a, b = tokenize(OLD, granularity), tokenize(NEW, granularity)
    for tag, (i1, i2), (j1, j2) in TextDiff(OLD, NEW, granularity=granularity).ops():
        if tag == "equal":
            assert a[i1:i2] == b[j1:j2]


@pytest.mark.parametrize("granularity", ["lines", "words", "chars"])
@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_ops_reconstruct_new_from_old(granularity, algorithm):
    a, b = tokenize(OLD, granularity), tokenize(NEW, granularity)
    rebuilt = []
    for tag, (i1, i2), (j1, j2) in TextDiff(
        OLD, NEW, algorithm=algorithm, granularity=granularity
    ).ops():
        rebuilt.extend(a[i1:i2] if tag == "equal" else b[j1:j2])
    assert "".join(rebuilt) == NEW


@pytest.mark.parametrize("granularity", ["lines", "words", "chars"])
def test_ratio_in_unit_interval(granularity):
    assert 0.0 <= TextDiff(OLD, NEW, granularity=granularity).ratio() <= 1.0
    assert 0.0 <= TextDiff("abc\n", "xyz\n", granularity=granularity).ratio() <= 1.0


def test_ratio_of_empty_inputs_is_one():
    assert TextDiff("", "").ratio() == 1.0


def test_identical_inputs_are_one_equal_op():
    diff = TextDiff(OLD, OLD)
    assert diff.ratio() == 1.0
    assert [tag for tag, _, _ in diff.ops()] == ["equal"]


def test_known_ratio():
    assert TextDiff("a\nb\n", "a\nc\n").ratio() == 0.5
    assert TextDiff("kitten", "sitting", granularity="chars").ratio() == (
        0.6153846153846154
    )


def test_lone_surrogates_raise():
    with pytest.raises(UnicodeEncodeError):
        TextDiff("\ud800x", "x")


def test_unknown_granularity():
    with pytest.raises(ValueError):
        TextDiff("a\n", "b\n", granularity="paragraphs")


def test_unknown_algorithm():
    with pytest.raises(ValueError):
        TextDiff("a\n", "b\n", algorithm="bogus")


@pytest.mark.parametrize("bad", [b"a\n", 42, None, ["a"]])
def test_non_string_inputs_raise_type_error(bad):
    with pytest.raises(TypeError):
        TextDiff(bad, "a\n")
    with pytest.raises(TypeError):
        unified_diff("a\n", bad)
