# similar-rs

[![PyPI](https://img.shields.io/pypi/v/similar-rs.svg)](https://pypi.org/project/similar-rs/)
[![CI](https://github.com/Maksim-Burtsev/similar-rs/actions/workflows/wheels.yml/badge.svg)](https://github.com/Maksim-Burtsev/similar-rs/actions/workflows/wheels.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/similar-rs.svg)](https://pypi.org/project/similar-rs/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Rust-powered text diffing for Python: bindings to the
[`similar`](https://github.com/mitsuhiko/similar) crate by Armin Ronacher.
It also ships a drop-in replacement for the standard library's `difflib`,
which runs [2 to 4 times faster](#benchmarks) on real file diffs and adds
six diff algorithms stdlib does not have.

## Install

```bash
pip install similar-rs
```

Wheels: Linux (x86_64, aarch64), macOS (arm64, x86_64) and Windows (AMD64).
They are abi3 — one wheel per platform, CPython 3.9+. No system
dependencies. An sdist is published too; building from it needs a Rust
toolchain.

## Usage

```python
import similar

print(similar.unified_diff("a\nb\n", "a\nc\n", header=("old", "new")))
```

`TextDiff` computes the diff once and exposes the opcodes and a similarity
ratio:

```python
d = similar.TextDiff("a\nb\n", "a\nc\n", granularity="lines")
d.ops()    # [("equal", (0, 1), (0, 1)), ("replace", (1, 2), (1, 2))]
d.ratio()  # 0.5
```

`granularity` is `lines`, `words` or `chars`. `algorithm` is one of `myers`
(default), `raw-myers`, `patience`, `lcs`, `hunt` or `histogram`; both
`TextDiff` and `unified_diff` accept it.

### difflib drop-in

Change one import line — `SequenceMatcher`, `unified_diff` and
`get_close_matches` then run on Rust:

```python
from similar import difflib  # instead of: import difflib

difflib.SequenceMatcher(None, "kitten", "sitting").ratio()  # 0.6153...
"".join(difflib.unified_diff(["a\n", "b\n"], ["a\n", "c\n"], "old", "new"))
```

## difflib compatibility

| API | Status |
|---|---|
| `SequenceMatcher.ratio`, `quick_ratio`, `real_quick_ratio` | Rust |
| `SequenceMatcher.get_opcodes`, `get_matching_blocks`, `get_grouped_opcodes` | Rust |
| `unified_diff`, `get_close_matches` | Rust |
| `Differ`, `HtmlDiff`, `ndiff`, `context_diff`, `restore`, `diff_bytes` | stdlib passthrough |
| `SequenceMatcher.find_longest_match` | stdlib passthrough |

Known differences:

- `isjunk` and `autojunk` are ignored; passing an `isjunk` raises a
  `RuntimeWarning`.
- Opcodes are a valid edit script, but not byte-for-byte the one stdlib
  produces — it is a different algorithm, finding a different (as a rule, no
  smaller) set of matches. `ratio()` and `get_opcodes()` can therefore differ
  from stdlib's at *either* `autojunk` setting, not just `autojunk=True`.
- `get_close_matches` can return a different set for the same reason: the
  underlying ratios differ. The tie order among equal ratios matches stdlib.
- `find_longest_match` runs stdlib's algorithm with `autojunk=False`, so its
  result can differ from a default stdlib matcher's (`autojunk=True`) — and it
  may name a block that `get_matching_blocks()` of the same object (Rust
  opcodes) does not contain.
- Inputs must be `str` or sequences of `str`.
- The stdlib instance attributes `b2j`, `bjunk`, `bpopular`, `opcodes` and
  `matching_blocks` are absent; the caches are private.
- Strings holding lone surrogates (as `diff_bytes` produces) cannot cross into
  Rust, so they take a slow pure-Python fallback via stdlib `difflib`.

## Limitations

No `isjunk`/`autojunk`, `str` only (no `bytes`), and no grapheme or
Unicode-word granularity yet. Open an issue if you need any of these.

## Benchmarks

Five CPython standard-library modules, each diffed against its own release
four versions later (v3.9.0 to v3.13.0) — real edits to real code, roughly
1000 to 3800 lines a side:

![unified_diff timings and median speedups](https://raw.githubusercontent.com/Maksim-Burtsev/similar-rs/f720068/benchmarks/speedup.svg)

| operation | median speedup |
|---|---|
| `unified_diff`, native (`similar.unified_diff`) | 2.4x |
| `unified_diff`, difflib-shaped (`similar.difflib.unified_diff`) | 2.1x |
| `SequenceMatcher.ratio` vs stdlib's default | 2.8x |
| `get_close_matches` | 2.4x |

A few honest caveats, all of them measured:

- **Two to four times, not two orders of magnitude.** stdlib `difflib` is
  pure Python but it is not naive, and the per-pair speedup ranged from 1.0x
  to 4.0x. The win comes from the diff itself, so it grows with how much of
  the file actually changed.
- `ratio()` on whole files at character level is the one case where the
  numbers are not like-for-like: stdlib's `autojunk` is a *speed* heuristic,
  and our Myers has a cost cut-off of its own, so we return a coarser match
  set (a lower ratio) for the lower price. Against stdlib with `autojunk=False`
  — the algorithmically comparable setting — one pair finished in 23.5 s
  against our 0.12 s, and the other four had to be aborted at 30 s.
- On inputs too small to contain work (two lines, a pair of words) the win is
  1.3x to 6.3x, which is the call overhead and nothing else.

[`benchmarks/results.md`](benchmarks/results.md) has the per-pair tables and
the exact method; `python benchmarks/bench.py` reproduces all of it,
including the chart. Numbers above are from one Apple M4, Python 3.13.

## Contributing

Issues and PRs welcome. Build from a clone:

```bash
uv venv && uv pip install maturin pytest hypothesis
maturin develop
pytest
```

## License

Apache-2.0 (see [LICENSE](LICENSE)). The difflib-compatible formatting code
in `python/similar/difflib.py` is derived from CPython's `difflib` and is
covered by the PSF License Version 2; see the notice at the end of
[LICENSE](LICENSE). The wheel statically links the Rust crates it is built
from; their licenses are collected in
[LICENSE-THIRD-PARTY](LICENSE-THIRD-PARTY), which ships inside the wheel.
