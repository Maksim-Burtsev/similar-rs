#!/usr/bin/env python3
"""Benchmark similar-rs against the stdlib difflib on real CPython file pairs.

Three operations, each run both ways on every pair:
  1. unified_diff over readlines() output, fully materialized on both sides
  2. SequenceMatcher(None, a_text, b_text).ratio() on whole texts (chars);
     stdlib measured twice, autojunk=True (its default, and a speed heuristic)
     and autojunk=False (algorithmically comparable)
  3. get_close_matches over identifiers harvested from the corpus

Writes benchmarks/results.md, speedup.svg and speedup-dark.svg (overwrites in place).

Usage: python benchmarks/bench.py [--out DIR] [--slow-cap SECONDS]
"""
import argparse
import datetime
import difflib as std
import os
import platform
import random
import re
import signal
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import similar
from similar import difflib as fast

OLD_TAG, NEW_TAG = "v3.9.0", "v3.13.0"
PAIRS = [
    "Lib/difflib.py",
    "Lib/argparse.py",
    "Lib/typing.py",
    "Lib/asyncio/tasks.py",
    "Lib/dataclasses.py",
]
RAW = "https://raw.githubusercontent.com/python/cpython/{tag}/{path}"


class Timeout(Exception):
    pass


def fetch(url: str, dst: Path) -> bool:
    """Download to dst unless cached. False (with a message) on 404 etc."""
    if dst.exists():
        return True
    part = dst.parent / (dst.name + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            part.write_bytes(r.read())
    except (urllib.error.URLError, OSError) as e:
        print(f"  cannot fetch {url}: {e}")
        part.unlink(missing_ok=True)
        return False
    os.replace(part, dst)  # atomic: an interrupted download never counts
    return True


def load_corpus(cache: Path):
    """[(label, old_text, new_text)] for every pair that downloaded cleanly."""
    cache.mkdir(parents=True, exist_ok=True)
    out = []
    for path in PAIRS:
        texts = []
        for tag in (OLD_TAG, NEW_TAG):
            dst = cache / f"{path.replace('/', '_')}.{tag}"
            if not fetch(RAW.format(tag=tag, path=path), dst):
                break
            texts.append(dst.read_text(encoding="utf-8"))
        if len(texts) == 2:
            out.append((path[len("Lib/"):], texts[0], texts[1]))
        else:
            print(f"  skipping pair {path}")
    return out


def timed(fn, repeats=5, label=""):
    """Warm-up run, then min() of `repeats` runs. Repeats shrink for slow ops."""
    t0 = time.perf_counter()
    fn()
    first = time.perf_counter() - t0
    if first > 5:
        repeats = 1
    elif first > 0.5:
        repeats = min(repeats, 3)
    if repeats == 1:
        print(f"    {label}: {first:.2f}s for one run, not repeating")
        return first
    best = first
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def timed_capped(fn, cap: float, label: str):
    """Single timed run, aborted after `cap` seconds. Returns (seconds, note)."""

    def boom(signum, frame):
        raise Timeout

    old = signal.signal(signal.SIGALRM, boom)
    signal.setitimer(signal.ITIMER_REAL, cap)
    t0 = time.perf_counter()
    try:
        fn()
        dt = time.perf_counter() - t0
        note = "single run" if dt > 120 else ""
        if note:
            print(f"    {label}: {dt:.1f}s, single run")
        return dt, note
    except Timeout:
        print(f"    {label}: aborted after {cap:.0f}s")
        return None, f"aborted at {cap:.0f} s"
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def identifiers(text: str, limit=2000):
    seen = dict.fromkeys(re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", text))
    return list(seen)[:limit]


def typos(words, k=20, seed=7):
    """k deterministic one-letter substitutions, drawn from `words`."""
    rng = random.Random(seed)
    out = []
    for w in rng.sample(words, k):
        i = rng.randrange(len(w))
        out.append(w[:i] + rng.choice("abcdefghijklmnopqrstuvwxyz") + w[i + 1:])
    return out


def bench_unified(a_text, b_text, a_lines, b_lines):
    ours = timed(lambda: list(fast.unified_diff(a_lines, b_lines)))
    theirs = timed(lambda: list(std.unified_diff(a_lines, b_lines)))
    # The native path does the same job — two texts in, a unified diff out — but
    # splits, diffs and formats entirely in Rust, with no per-line Python objects.
    rust = timed(lambda: similar.unified_diff(a_text, b_text))
    o, t = list(fast.unified_diff(a_lines, b_lines)), list(std.unified_diff(a_lines, b_lines))
    assert o and t, "empty diff on both sides means the corpus is wrong"
    assert similar.unified_diff(a_text, b_text).count("@@"), "native path produced no hunks"
    hunks = (sum(l.startswith("@@") for l in o), sum(l.startswith("@@") for l in t))
    return ours, theirs, rust, len(o), len(t), hunks


def bench_ratio(a, b, cap, label):
    ours = timed(lambda: fast.SequenceMatcher(None, a, b).ratio(), label=f"{label} ours")
    aj = timed(lambda: std.SequenceMatcher(None, a, b).ratio(), label=f"{label} autojunk")
    noaj, note = timed_capped(
        lambda: std.SequenceMatcher(None, a, b, autojunk=False).ratio(), cap,
        f"{label} stdlib autojunk=False")
    r_ours = fast.SequenceMatcher(None, a, b).ratio()
    r_aj = std.SequenceMatcher(None, a, b).ratio()
    return ours, aj, noaj, note, r_ours, r_aj


def bench_gcm(queries, candidates):
    def run(fn):
        return lambda: [fn(q, candidates, n=3, cutoff=0.6) for q in queries]

    ours = timed(run(fast.get_close_matches), label="get_close_matches ours")
    theirs = timed(run(std.get_close_matches), label="get_close_matches stdlib")
    hits = (sum(bool(fast.get_close_matches(q, candidates)) for q in queries),
            sum(bool(std.get_close_matches(q, candidates)) for q in queries))
    return ours, theirs, hits


def small_inputs():
    """PyO3 call overhead on trivial inputs: microseconds per call, per op."""
    two_a, two_b = ["a\n", "b\n"], ["a\n", "c\n"]
    assert list(fast.unified_diff(two_a, two_b)) == list(std.unified_diff(two_a, two_b))
    words = ["apple", "apply", "ape", "banana", "orange"]
    cases = [
        ("unified_diff, 2 lines",
         lambda m: list(m.unified_diff(two_a, two_b))),
        ("SequenceMatcher.ratio, 'kitten'/'sitting'",
         lambda m: m.SequenceMatcher(None, "kitten", "sitting").ratio()),
        ("get_close_matches, 5 candidates",
         lambda m: m.get_close_matches("appel", words)),
    ]
    out = []
    for name, call in cases:
        us = [min(_loop(call, m) for _ in range(5)) / 2000 * 1e6 for m in (fast, std)]
        out.append((name, us[0], us[1]))
    return out


def _loop(call, m, n=2000):
    t0 = time.perf_counter()
    for _ in range(n):
        call(m)
    return time.perf_counter() - t0


def cpu_name():
    if sys.platform == "darwin":
        try:
            return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                  capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return platform.processor() or platform.machine()


def plot(groups, out_dir: Path) -> None:
    """Three workload groups, each on its own linear scale: the stdlib bar is
    always full width, ours is the honest fraction of it. Drawn twice:
    speedup.svg (light) and speedup-dark.svg (dark)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    def fmt(ms, unit):
        if unit:
            return f"{ms:.1f} {unit}"
        if ms >= 1000:
            return f"{ms / 1000:.1f} s"
        return f"{ms:.0f} ms" if ms >= 100 else f"{ms:.1f} ms"

    themes = {
        "speedup.svg": dict(bar="#0b7285", base="#c3c9cd", surface="#ffffff",
                            ink="#0b0b0b", muted="#52514e"),
        "speedup-dark.svg": dict(bar="#12a3ba", base="#3a3f42", surface="#111111",
                                 ink="#f2f2f0", muted="#a8a8a2"),
    }
    for name, c in themes.items():
        fig, ax = plt.subplots(figsize=(9.5, 4.0), facecolor=c["surface"])
        ax.set_facecolor(c["surface"])
        ys, h = [4.7, 2.7, 0.7], 0.55
        for (label, s_ms, o_ms, unit, note), y in zip(groups, ys):
            # 0.016 floor keeps the sliver visible at README width
            frac = max(o_ms / s_ms, 0.016)
            ax.barh([y + 0.32], [1.0], color=c["base"], height=h, zorder=3)
            ax.barh([y - 0.32], [frac], color=c["bar"], height=h, zorder=3)
            ax.text(1.012, y + 0.32, fmt(s_ms, unit), va="center",
                    color=c["muted"], fontsize=11)
            ax.text(frac + 0.012, y - 0.32, fmt(o_ms, unit), va="center",
                    color=c["ink"], fontsize=11, fontweight="bold")
            ax.text(1.30, y - 0.32, note, va="center", ha="right",
                    color=c["muted"] if note == "about the same" else c["bar"],
                    fontsize=13, fontweight="bold")
        ax.set_yticks(ys)
        ax.set_yticklabels([g[0] for g in groups], fontsize=12.5, color=c["ink"])
        ax.set_xticks([])
        ax.set_xlim(0, 1.31)
        ax.set_ylim(-0.2, 5.8)
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(False)
        ax.tick_params(length=0)
        ax.legend(handles=[Patch(color=c["base"], label="stdlib difflib"),
                           Patch(color=c["bar"], label="similar-rs")],
                  frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0),
                  ncol=2, fontsize=12, labelcolor=c["ink"])
        fig.savefig(out_dir / name, bbox_inches="tight", facecolor=c["surface"])
        plt.close(fig)


def fmt_ms(v):
    return "n/a" if v is None else f"{v * 1000:,.1f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent))
    ap.add_argument("--slow-cap", type=float, default=30.0,
                    help="abort a stdlib autojunk=False ratio run after N seconds")
    args = ap.parse_args()
    out_dir = Path(args.out)

    if getattr(similar._similar, "__debug_build__", False):
        sys.exit("this is a DEBUG build (~5x slower); benchmarking it is "
                 "meaningless. Reinstall with: pip install -e '.[bench]'")

    corpus = load_corpus(out_dir / "corpus")
    if not corpus:
        sys.exit("no corpus: every pair failed to download")
    print(f"corpus: {len(corpus)} pairs")

    rows = []
    for label, a_text, b_text in corpus:
        print(f"{label}:")
        a_lines, b_lines = a_text.splitlines(True), b_text.splitlines(True)
        ud_ours, ud_std, ud_rust, n_ours, n_std, hunks = bench_unified(
            a_text, b_text, a_lines, b_lines)
        r_ours, r_aj, r_noaj, note, val_ours, val_std = bench_ratio(
            a_text, b_text, args.slow_cap, label)
        rows.append(dict(
            label=label, a=len(a_lines), b=len(b_lines),
            lines=max(len(a_lines), len(b_lines)),
            ud_ours=ud_ours, ud_std=ud_std, ud_rust=ud_rust,
            out_ours=n_ours, out_std=n_std,
            hunks=hunks, r_ours=r_ours, r_aj=r_aj, r_noaj=r_noaj, note=note,
            val_ours=val_ours, val_std=val_std))
        print(f"  unified_diff {ud_ours*1000:.1f} vs {ud_std*1000:.1f} ms "
              f"({ud_std/ud_ours:.1f}x), native {ud_rust*1000:.1f} ms "
              f"({ud_std/ud_rust:.1f}x), lines out {n_ours}/{n_std}, hunks {hunks}")
        print(f"  ratio {r_ours*1000:.1f} / aj={r_aj*1000:.1f} / "
              f"noaj={fmt_ms(r_noaj)} ms; values {val_ours:.4f} vs {val_std:.4f}")

    cands = identifiers("".join(new for _, _, new in corpus))
    queries = typos(cands)
    g_ours, g_std, hits = bench_gcm(queries, cands)
    print(f"get_close_matches {g_ours*1000:.1f} vs {g_std*1000:.1f} ms "
          f"({g_std/g_ours:.1f}x), non-empty {hits}")

    small = small_inputs()
    for name, o, t in small:
        print(f"small input [{name}]: ours {o:.1f} us, stdlib {t:.1f} us "
              f"({t/o:.2f}x)")

    med = lambda vs: statistics.median(vs)
    m_ud = med([r["ud_std"] / r["ud_ours"] for r in rows])
    m_rust = med([r["ud_std"] / r["ud_rust"] for r in rows])
    m_aj = med([r["r_aj"] / r["r_ours"] for r in rows])
    m_gcm = g_std / g_ours
    # The first three are medians over the corpus. The last one is not: the
    # queries are timed as one batch, so it is a single aggregate ratio.
    medians = [("unified_diff\n(similar.difflib)", m_ud, ""),
               ("unified_diff\n(native)", m_rust, ""),
               ("ratio\nvs autojunk=True", m_aj, ""),
               ("get_close_matches\n(whole query set)", m_gcm,
                " (aggregate over the whole query set, not a median)")]
    # autojunk=False is not: most pairs were aborted, so it is reported with the
    # sample it actually rests on and kept out of the chart.
    noaj = [r["r_noaj"] / r["r_ours"] for r in rows if r["r_noaj"]]
    partial = []
    if noaj:
        pairs = "pair" if len(rows) == 1 else "pairs"
        partial = [("ratio vs autojunk=False", med(noaj),
                    f" ({len(noaj)} of {len(rows)} {pairs}; the rest were aborted)")]

    # Chart: three workloads, mild to wild, every value measured above. The
    # named pairs are fixed (not picked per run) so the chart stays comparable
    # between refreshes.
    texts = {label: (a, b) for label, a, b in corpus}
    groups = [("Tiny input\n(a two-line diff)",
               small[0][2], small[0][1], "us",
               "about the same")]
    real = next(r for r in rows if r["label"] == "argparse.py")
    groups.append((f"Real file diff\n(argparse.py, {real['lines']:,} lines)",
                   real["ud_std"] * 1000, real["ud_rust"] * 1000, "ms",
                   f"{real['ud_std'] / real['ud_rust']:.0f}x faster"))
    acc = next((r for r in rows if r["r_noaj"]), None)
    if acc:
        kb = round(sum(len(t) for t in texts[acc["label"]]) / 2048 / 5) * 5
        groups.append((f"Accurate similarity of two files\n(both ~{kb} KB)",
                       acc["r_noaj"] * 1000, acc["r_ours"] * 1000, None,
                       f"{acc['r_noaj'] / acc['r_ours']:.0f}x faster"))
    plot(groups, out_dir)
    medians = medians + partial
    write_report(out_dir / "results.md", rows, medians, g_ours, g_std, hits,
                 len(queries), len(cands), small, args.slow_cap)
    print(f"wrote {out_dir}/results.md, speedup.svg and speedup-dark.svg")


def write_report(path, rows, medians, g_ours, g_std, hits, nq, nc,
                 small, cap) -> None:
    sp = lambda a, b: "n/a" if a is None else f"{a / b:.1f}x"
    lines = [
        "# similar-rs vs stdlib difflib",
        "",
        f"Date: {datetime.date.today().isoformat()}. similar-rs "
        f"{similar.__version__}, Python {platform.python_version()} "
        f"({platform.python_implementation()}), {platform.system()} "
        f"{platform.release()}, {cpu_name()}.",
        "",
        f"Corpus: five CPython standard-library files, each in two released "
        f"versions ({OLD_TAG} to {NEW_TAG}), fetched from raw.githubusercontent.com "
        f"at those immutable tags. Timing: one warm-up run, then `min()` of up to 5 "
        f"runs (3 above 0.5 s, 1 above 5 s), `time.perf_counter`. Input preparation "
        f"(reading, `splitlines`) happens outside the clock. Both generators are "
        f"fully materialized with `list()`.",
        "",
        "## unified_diff (line level)",
        "",
        "`similar.difflib.unified_diff` takes and returns lines, exactly like "
        "stdlib. `similar.unified_diff` is the native entry point: it takes the "
        "two texts and returns the finished diff as one string, so the line "
        "splitting and the formatting happen in Rust too.",
        "",
        "| pair | lines old/new | similar.difflib (ms) | native (ms) | stdlib (ms) | speedup (difflib/native) | output lines (ours/stdlib) | hunks |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['label']} | {r['a']}/{r['b']} | {fmt_ms(r['ud_ours'])} | "
            f"{fmt_ms(r['ud_rust'])} | {fmt_ms(r['ud_std'])} | "
            f"{sp(r['ud_std'], r['ud_ours'])} / {sp(r['ud_std'], r['ud_rust'])} | "
            f"{r['out_ours']}/{r['out_std']} | {r['hunks'][0]}/{r['hunks'][1]} |")
    lines += [
        "",
        "Output sizes and hunk counts differ slightly because the two libraries "
        "pick different (equally valid) edit scripts; both diffs are non-empty and "
        "of comparable size, which is the fairness check that matters here.",
        "",
        "## SequenceMatcher(None, a_text, b_text).ratio() (char level, whole files)",
        "",
        "stdlib is measured twice. `autojunk=True` is its default and is what users "
        "actually get, but it is a *speed heuristic*: it drops popular elements from "
        "the match search, which on char-level input means most of the alphabet. "
        "`autojunk=False` is the algorithmically comparable configuration.",
        "",
        "| pair | similar-rs (ms) | stdlib autojunk=True (ms) | stdlib autojunk=False (ms) | speedup vs True | speedup vs False |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        noaj = fmt_ms(r["r_noaj"]) + (f" ({r['note']})" if r["note"] else "")
        lines.append(
            f"| {r['label']} | {fmt_ms(r['r_ours'])} | {fmt_ms(r['r_aj'])} | {noaj} | "
            f"{sp(r['r_aj'], r['r_ours'])} | {sp(r['r_noaj'], r['r_ours'])} |")
    lines += [
        "",
        "The ratio *values* differ too, and not in our favour on this input:",
        "",
        "| pair | similar-rs ratio | stdlib ratio (autojunk=True) |",
        "|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['label']} | {r['val_ours']:.4f} | {r['val_std']:.4f} |")
    lines += [
        "",
        "The `similar` crate's default Myers implementation has its own "
        "cost cut-off for very long sequences, so on whole-file char-level input it "
        "returns a coarser (lower-ratio) match set than stdlib does. Passing "
        "`algorithm=\"lcs\"` or `\"raw-myers\"` to `similar.difflib.SequenceMatcher` "
        "recovers an optimal match set, at a higher cost. Treat the char-level "
        "`ratio()` numbers as \"different answer, different price\", not as a "
        "like-for-like win.",
        "",
        "## get_close_matches",
        "",
        f"{nq} deterministically mistyped words (one letter substituted, seed 7) "
        f"against the first {nc} unique identifiers of the corpus, `n=3, cutoff=0.6`, "
        f"total time for all queries.",
        "",
        "| similar-rs (ms) | stdlib (ms) | speedup | queries with a match (ours/stdlib) |",
        "|---|---|---|---|",
        f"| {fmt_ms(g_ours)} | {fmt_ms(g_std)} | {sp(g_std, g_ours)} | {hits[0]}/{hits[1]} |",
        "",
        "## Small inputs (PyO3 call overhead)",
        "",
        "Per-call cost on inputs too small to contain real work, min over 5 batches "
        "of 2000 calls.",
        "",
        "| case | similar-rs (us) | stdlib (us) | ratio |",
        "|---|---|---|---|",
    ]
    for name, o, t in small:
        verdict = f"{t / o:.2f}x faster" if t > o else f"{o / t:.2f}x slower"
        lines.append(f"| {name} | {o:.1f} | {t:.1f} | {verdict} |")
    lines += [
        "",
        "The PyO3 boundary crossing shows up here undiluted: on inputs this small "
        "there is no diff work to amortize it against.",
        "",
        "## Medians over the corpus",
        "",
    ]
    for name, v, note in medians:
        lines.append(f"- {name.replace(chr(10), ' ')}: **{v:.1f}x**{note}")
    lines += [
        "",
        "## Reproduce",
        "",
        "```",
        "pip install -e '.[bench]'   # release build; `maturin develop` alone is",
        "                            # a DEBUG build and is ~5x slower",
        "python benchmarks/bench.py" + (
            "" if not sys.argv[1:] else " " + " ".join(sys.argv[1:])),
        "```",
        "",
        f"The corpus is cached in `benchmarks/corpus/` (git-ignored) and downloaded "
        f"on first run. The run overwrites `benchmarks/results.md`, "
        f"`benchmarks/speedup.svg` and `benchmarks/speedup-dark.svg` in place. "
        f"A stdlib `autojunk=False` run that "
        f"exceeds {cap:.0f} s is aborted and reported as such (`--slow-cap` changes "
        f"the limit). Numbers are from a single machine, unpinned CPU frequency; "
        f"expect the usual laptop-benchmark variance of a few percent.",
    ]
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
