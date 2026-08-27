"""The README's Benchmarks section must agree with benchmarks/results.md.

Regenerating results.md without updating the README is the drift this catches.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = " ".join((ROOT / "README.md").read_text().split())  # unwrap prose
RESULTS = (ROOT / "benchmarks" / "results.md").read_text()

# README medians row -> the bullet it comes from in the Medians section
MEDIAN_ROWS = {
    "`unified_diff`, native": "unified_diff (native)",
    "`unified_diff`, difflib-shaped": "unified_diff (similar.difflib)",
    "`SequenceMatcher.ratio` vs stdlib's default": "ratio vs autojunk=True",
    "`get_close_matches` (aggregate": "get_close_matches (whole query set)",
}


def _table(title):
    """Data rows of the one table in the `## title...` section of results.md."""
    section = RESULTS.split(f"## {title}")[1].split("\n## ")[0]
    rows = [r for r in section.splitlines() if r.startswith("|")]
    return [[c.strip() for c in r.strip("|").split("|")] for r in rows][2:]


def _num(cell):
    return float(cell.replace(",", "").rstrip("x").split()[0].rstrip("x"))


def test_medians_table():
    bullets = dict(re.findall(r"- (.+?): \*\*([\d.]+)x\*\*",
                              RESULTS.split("## Medians")[1]))
    for row, bullet in MEDIAN_ROWS.items():
        m = re.search(re.escape(row) + r"[^|]*\| ([\d.]+)x \|", README)
        assert m, f"no README medians row for {row}"
        assert m.group(1) == bullets[bullet], (
            f"{row}: README says {m.group(1)}x, results.md {bullets[bullet]}x")


def test_per_pair_speedup_range():
    vals = [_num(v) for r in _table("unified_diff (line level)")
            for v in r[5].split("/")]
    want = f"ranged from {min(vals):.1f}x to {max(vals):.1f}x"
    assert want in README, f"README per-pair range is not {want!r}"


def test_autojunk_false_sentence():
    row = next(r for r in _table("SequenceMatcher") if "n/a" not in r[3])
    want = (f"one pair finished in {_num(row[3]) / 1000:.1f} s "
            f"against our {_num(row[1]) / 1000:.2f} s")
    assert want in README, f"README autojunk=False sentence is not {want!r}"


def test_small_inputs_range():
    vals = [_num(r[3]) for r in _table("Small inputs")]
    want = f"the win is {min(vals):.1f}x to {max(vals):.1f}x"
    assert want in README, f"README small-inputs range is not {want!r}"
