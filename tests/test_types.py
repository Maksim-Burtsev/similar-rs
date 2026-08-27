"""Type boundaries: only str and sequences of str are accepted."""

from collections import UserList

import pytest

from similar import TextDiff
from similar import difflib as ours

BAD = [b"x", 5, [1, 2], ["a", 1], (1,), {"a": 1}, None]


@pytest.mark.parametrize("bad", BAD)
def test_sequence_matcher_rejects_seq1(bad):
    with pytest.raises(TypeError, match="only str or sequences of str"):
        ours.SequenceMatcher(a=bad, b="ok")


@pytest.mark.parametrize("bad", BAD)
def test_sequence_matcher_rejects_seq2(bad):
    with pytest.raises(TypeError, match="only str or sequences of str"):
        ours.SequenceMatcher(a="ok", b=bad)


@pytest.mark.parametrize("bad", BAD)
def test_set_seq1_rejects(bad):
    m = ours.SequenceMatcher(a="ok", b="ok")
    with pytest.raises(TypeError):
        m.set_seq1(bad)


@pytest.mark.parametrize("bad", BAD)
def test_set_seq2_rejects(bad):
    m = ours.SequenceMatcher(a="ok", b="ok")
    with pytest.raises(TypeError):
        m.set_seq2(bad)


def test_sequence_matcher_accepts_tuple_of_str():
    assert ours.SequenceMatcher(a=("a", "b"), b=("a", "c")).ratio() == 0.5


def test_sequence_matcher_accepts_any_sequence_of_str():
    assert ours.SequenceMatcher(a=UserList(["a", "b"]), b=("a", "c")).ratio() == 0.5


def test_sequence_matcher_rejects_generator():
    # stdlib needs len() too, so an iterator is no more supported than there.
    with pytest.raises(TypeError, match="only str or sequences of str"):
        ours.SequenceMatcher(a=(c for c in "ab"), b="ok")


def test_unified_diff_rejects_non_str_filename():
    with pytest.raises(TypeError, match="all arguments must be str"):
        list(ours.unified_diff(["a\n"], ["b\n"], fromfile=1))


def test_unified_diff_rejects_non_str_lines():
    with pytest.raises(TypeError, match="lines to compare must be str"):
        list(ours.unified_diff([1], ["b\n"]))


def test_text_diff_rejects_bytes():
    with pytest.raises(TypeError):
        TextDiff(b"x", "y")
