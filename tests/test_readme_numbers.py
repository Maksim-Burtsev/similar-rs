"""The README's Benchmarks section must agree with benchmarks/results.md.

Regenerating results.md without updating the README is the drift this catches.
"""
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = " ".join((ROOT / "README.md").read_text().split())  # unwrap prose
RESULTS = (ROOT / "benchmarks" / "results.md").read_text()


def _table(title):
    """Data rows of the one table in the `## title...` section of results.md."""
    section = RESULTS.split(f"## {title}")[1].split("\n## ")[0]
    rows = [r for r in section.splitlines() if r.startswith("|")]
    return [[c.strip() for c in r.strip("|").split("|")] for r in rows][2:]


def _num(cell):
    return float(cell.replace(",", "").rstrip("x").split()[0].rstrip("x"))


def _readme_speedup(row_label):
    m = re.search(re.escape(row_label) + r"[^|]*\|[^|]*\|[^|]*\| ([\d.]+)x", README)
    assert m, f"no README benchmark row starting with {row_label!r}"
    return m.group(1)


def _expected():
    """The six chart/README speedups, recomputed from results.md tables."""
    small = _table("Small inputs")
    ud = _table("unified_diff (line level)")
    # the SequenceMatcher section holds two tables; keep the 6-column speedup one
    ratio = [r for r in _table("SequenceMatcher") if len(r) == 6]
    gcm = _table("get_close_matches")
    native = [_num(r[5].split("/")[1]) for r in ud]
    aj = [_num(r[4]) for r in ratio]
    noaj = [_num(r[5]) for r in ratio if "n/a" not in r[5]]
    return {
        "two-line diff": _num(small[0][3]),
        "`get_close_matches`, 20 queries": _num(gcm[0][2]),
        "`unified_diff`, five real file pairs": statistics.median(native),
        "`ratio`, whole files": statistics.median(aj),
        "`ratio`, stdlib's worst pair": max(aj),
        "accurate `ratio`": noaj[0] if len(noaj) == 1 else statistics.median(noaj),
    }


def test_benchmark_table_rows():
    for label, want in _expected().items():
        got = _readme_speedup(label)
        assert got == f"{want:.1f}", (
            f"{label}: README says {got}x, results.md gives {want:.1f}x")


def test_intro_understates_never_overstates():
    exp = _expected()
    m = re.search(r"about ([\d.]+)x on real file diffs", README)
    assert m, "intro is missing the everyday number"
    assert float(m.group(1)) <= exp["`unified_diff`, five real file pairs"] + 1e-9
    m = re.search(r"up to (\d+)x where stdlib trades accuracy", README)
    assert m, "intro is missing the ceiling number"
    assert float(m.group(1)) <= exp["accurate `ratio`"] + 1e-9
