# similar-rs vs stdlib difflib

Date: 2026-08-28. similar-rs 0.1.0, Python 3.13.15 (CPython), Darwin 25.5.0, Apple M4.

Corpus: five CPython standard-library files, each in two released versions (v3.9.0 to v3.13.0), fetched from raw.githubusercontent.com at those immutable tags. Timing: one warm-up run, then `min()` of up to 5 runs (3 above 0.5 s, 1 above 5 s), `time.perf_counter`. Input preparation (reading, `splitlines`) happens outside the clock. Both generators are fully materialized with `list()`.

## unified_diff (line level)

`similar.difflib.unified_diff` takes and returns lines, exactly like stdlib. `similar.unified_diff` is the native entry point: it takes the two texts and returns the finished diff as one string, so the line splitting and the formatting happen in Rust too.

| pair | lines old/new | similar.difflib (ms) | native (ms) | stdlib (ms) | speedup (difflib/native) | output lines (ours/stdlib) | hunks |
|---|---|---|---|---|---|---|---|
| difflib.py | 2096/2056 | 0.3 | 0.4 | 0.8 | 2.3x / 2.1x | 74/74 | 4/4 |
| argparse.py | 2575/2669 | 1.0 | 0.9 | 3.7 | 3.6x / 4.0x | 1076/1075 | 67/67 |
| typing.py | 2147/3814 | 1.8 | 1.5 | 3.9 | 2.2x / 2.6x | 4036/4116 | 63/64 |
| asyncio/tasks.py | 980/1118 | 1.1 | 1.0 | 1.1 | 1.0x / 1.1x | 959/974 | 30/30 |
| dataclasses.py | 1284/1630 | 0.5 | 0.4 | 1.5 | 3.0x / 3.7x | 1431/1437 | 47/47 |

Output sizes and hunk counts differ slightly because the two libraries pick different (equally valid) edit scripts; both diffs are non-empty and of comparable size, which is the fairness check that matters here.

## SequenceMatcher(None, a_text, b_text).ratio() (char level, whole files)

stdlib is measured twice. `autojunk=True` is its default and is what users actually get, but it is a *speed heuristic*: it drops popular elements from the match search, which on char-level input means most of the alphabet. `autojunk=False` is the algorithmically comparable configuration.

| pair | similar-rs (ms) | stdlib autojunk=True (ms) | stdlib autojunk=False (ms) | speedup vs True | speedup vs False |
|---|---|---|---|---|---|
| difflib.py | 3.0 | 712.1 | n/a (aborted at 30 s) | 236.1x | n/a |
| argparse.py | 294.7 | 1,748.5 | n/a (aborted at 30 s) | 5.9x | n/a |
| typing.py | 645.7 | 1,258.5 | n/a (aborted at 30 s) | 1.9x | n/a |
| asyncio/tasks.py | 120.2 | 225.9 | 23,807.2 | 1.9x | 198.1x |
| dataclasses.py | 238.8 | 674.5 | n/a (aborted at 30 s) | 2.8x | n/a |

The ratio *values* differ too, and not in our favour on this input:

| pair | similar-rs ratio | stdlib ratio (autojunk=True) |
|---|---|---|
| difflib.py | 0.9935 | 0.9938 |
| argparse.py | 0.6967 | 0.9091 |
| typing.py | 0.2963 | 0.3942 |
| asyncio/tasks.py | 0.4863 | 0.6841 |
| dataclasses.py | 0.4225 | 0.5038 |

The `similar` crate's default Myers implementation has its own cost cut-off for very long sequences, so on whole-file char-level input it returns a coarser (lower-ratio) match set than stdlib does. Passing `algorithm="lcs"` or `"raw-myers"` to `similar.difflib.SequenceMatcher` recovers an optimal match set, at a higher cost. Treat the char-level `ratio()` numbers as "different answer, different price", not as a like-for-like win.

## get_close_matches

20 deterministically mistyped words (one letter substituted, seed 7) against the first 2000 unique identifiers of the corpus, `n=3, cutoff=0.6`, total time for all queries.

| similar-rs (ms) | stdlib (ms) | speedup | queries with a match (ours/stdlib) |
|---|---|---|---|
| 13.0 | 31.3 | 2.4x | 20/20 |

## Small inputs (PyO3 call overhead)

Per-call cost on inputs too small to contain real work, min over 5 batches of 2000 calls.

| case | similar-rs (us) | stdlib (us) | ratio |
|---|---|---|---|
| unified_diff, 2 lines | 2.9 | 3.7 | 1.26x faster |
| SequenceMatcher.ratio, 'kitten'/'sitting' | 1.9 | 4.5 | 2.32x faster |
| get_close_matches, 5 candidates | 2.0 | 12.8 | 6.35x faster |

The PyO3 boundary crossing shows up here undiluted: on inputs this small there is no diff work to amortize it against.

## Medians over the corpus

- unified_diff (similar.difflib): **2.3x**
- unified_diff (native): **2.6x**
- ratio vs autojunk=True: **2.8x**
- get_close_matches (whole query set): **2.4x** (aggregate over the whole query set, not a median)
- ratio vs autojunk=False: **198.1x** (1 of 5 pairs; the rest were aborted)

## Reproduce

```
pip install -e '.[bench]'   # release build; `maturin develop` alone is
                            # a DEBUG build and is ~5x slower
python benchmarks/bench.py
```

The corpus is cached in `benchmarks/corpus/` (git-ignored) and downloaded on first run. The run overwrites `benchmarks/results.md`, `benchmarks/speedup.svg` and `benchmarks/speedup-dark.svg` in place. A stdlib `autojunk=False` run that exceeds 30 s is aborted and reported as such (`--slow-cap` changes the limit). Numbers are from a single machine, unpinned CPU frequency; expect the usual laptop-benchmark variance of a few percent.
