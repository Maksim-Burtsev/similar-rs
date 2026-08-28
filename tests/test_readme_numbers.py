"""The README's Benchmarks section must agree with benchmarks/results.md.

Regenerating results.md without updating the README is the drift this catches.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = " ".join((ROOT / "README.md").read_text().split())  # unwrap prose
RESULTS = (ROOT / "benchmarks" / "results.md").read_text()


def _table(title):
    """Data rows of the first table in the `## title...` section of results.md."""
    section = RESULTS.split(f"## {title}")[1].split("\n## ")[0]
    rows = [r for r in section.splitlines() if r.startswith("|")]
    parsed = [[c.strip() for c in r.strip("|").split("|")] for r in rows][2:]
    width = len(parsed[0])
    return [r for r in parsed if len(r) == width]


def _num(cell):
    return float(cell.replace(",", "").rstrip("x").split()[0].rstrip("x"))


def _expected():
    """The three chart/README speedups, recomputed from results.md tables."""
    small = _table("Small inputs")
    argparse_row = next(r for r in _table("unified_diff (line level)")
                        if r[0] == "argparse.py")
    noaj_row = next(r for r in _table("SequenceMatcher") if "n/a" not in r[3])
    return {
        "two-line diff": _num(small[0][3]),
        "real file diff": _num(argparse_row[5].split("/")[1]),
        "accurate similarity": _num(noaj_row[5]),
    }


def test_benchmark_table_rows():
    for label, want in _expected().items():
        m = re.search(re.escape(label) + r"[^|]*\|[^|]*\|[^|]*\| ([\d.]+)x",
                      README, re.IGNORECASE)
        assert m, f"no README benchmark row for {label!r}"
        assert m.group(1) == f"{want:.1f}", (
            f"{label}: README says {m.group(1)}x, results.md gives {want:.1f}x")


def test_intro_never_overstates():
    # 3% headroom absorbs run-to-run drift; real overstatement still fails.
    exp = _expected()
    m = re.search(r"(\d+)-(\d+)x faster", README)
    assert m, "intro is missing the range claim"
    assert float(m.group(2)) <= exp["real file diff"] * 1.03, (
        f"intro high end {m.group(2)}x, measured {exp['real file diff']}x")
    m = re.search(r"~(\d+)x on accurate", README)
    assert m, "intro is missing the accurate-similarity number"
    assert float(m.group(1)) <= exp["accurate similarity"] * 1.03, (
        f"intro says ~{m.group(1)}x, measured {exp['accurate similarity']}x")
