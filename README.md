# similar-rs

[![PyPI](https://img.shields.io/pypi/v/similar-rs.svg)](https://pypi.org/project/similar-rs/)
[![CI](https://github.com/Maksim-Burtsev/similar-rs/actions/workflows/wheels.yml/badge.svg)](https://github.com/Maksim-Burtsev/similar-rs/actions/workflows/wheels.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/similar-rs.svg)](https://pypi.org/project/similar-rs/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Rust-powered text diffing for Python: bindings to the
[`similar`](https://github.com/mitsuhiko/similar) crate by Armin Ronacher.
It also ships a drop-in replacement for the standard library's `difflib`
that runs [2-200x faster](https://github.com/Maksim-Burtsev/similar-rs#benchmarks)
— about 2.5x on real file diffs, up to 200x where stdlib trades accuracy
for speed — and adds six diff algorithms stdlib does not have.

<p align="center"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Maksim-Burtsev/similar-rs/e682ea7/benchmarks/speedup-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/Maksim-Burtsev/similar-rs/e682ea7/benchmarks/speedup.svg">
  <img alt="Bar chart: similar-rs speedup over stdlib difflib across six workloads, from parity on tiny inputs to about 200x on accurate whole-file similarity." src="https://raw.githubusercontent.com/Maksim-Burtsev/similar-rs/e682ea7/benchmarks/speedup.svg">
</picture></p>
<p align="center"><i>Five CPython stdlib modules, v3.9.0 vs v3.13.0 — per-pair tables in <a href="https://github.com/Maksim-Burtsev/similar-rs/blob/master/benchmarks/results.md">benchmarks/results.md</a>.</i></p>

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

| workload | stdlib | similar-rs | speedup |
|---|---|---|---|
| two-line diff (call overhead) | 3.7 us | 2.9 us | 1.3x |
| `get_close_matches`, 20 queries over 2000 identifiers | 31.5 ms | 13.3 ms | 2.4x |
| `unified_diff`, five real file pairs | 0.8-3.8 ms | 0.4-1.5 ms | 2.5x median |
| `ratio`, whole files at char level | 241-1764 ms | 3.4-643 ms | 2.7x median |
| `ratio`, stdlib's worst pair (difflib.py) | 794.4 ms | 3.4 ms | 234.5x |
| accurate `ratio` (`autojunk=False`), tasks.py | 24.7 s | 120.8 ms | 204.2x |

Why the floor is about 2x: stdlib `difflib` is not naive — it hashes lines
once and diffs the hashes through C-backed dicts, so a Rust port removes
the interpreter, not the algorithm. One to four times on real diffs —
2.5x at the median, 1.1x on a pair that barely changed — is the whole,
honest win for a one-line import change.

Why the ceiling is about 200x: stdlib's `autojunk` heuristic trades
accuracy for speed, and on char-level input it discards most of the
alphabet. Turn it off for an accurate answer and stdlib exceeded a 30 s
cap on four of the five pairs, while similar-rs stays under 0.7 s. On the
pair that did finish, `algorithm="raw-myers"` returned a better match set
than accurate stdlib (0.783 vs 0.759) in 0.5 s instead of 24.7 s. The
heuristic also has bad days of its own: on the difflib.py pair stdlib's
default ran 794 ms against our 3.4 ms. Note that with `autojunk` on, the
two libraries price the answer differently — our default `ratio` is
coarser than stdlib's on some inputs, which is why that row says median,
not like-for-like.

Crossing into Rust costs a fixed ~2 us per call, which only shows on
inputs too small to contain work — that is the 1.3x row. For whole texts,
prefer the native entry point (`similar.unified_diff`): the line splitting
and formatting happen in Rust too.

When to use it:

| you are doing | what you get |
|---|---|
| diffs in a hot loop (services, CI, batch pipelines) | typically 2-4x for a one-line import change |
| accurate similarity of long texts (dedup, fuzzy matching) | the 200x class: feasible where stdlib times out |
| git-style diffs (`patience`, `histogram`) | algorithms stdlib does not have at any speed |

[`benchmarks/results.md`](https://github.com/Maksim-Burtsev/similar-rs/blob/master/benchmarks/results.md)
has the per-pair tables and the exact method; `python benchmarks/bench.py`
reproduces all of it, charts included. Numbers above are from one Apple
M4, Python 3.13.

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
