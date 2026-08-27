# similar-rs

[![PyPI](https://img.shields.io/pypi/v/similar-rs.svg)](https://pypi.org/project/similar-rs/)
[![CI](https://github.com/Maksim-Burtsev/similar-rs/actions/workflows/wheels.yml/badge.svg)](https://github.com/Maksim-Burtsev/similar-rs/actions/workflows/wheels.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/similar-rs.svg)](https://pypi.org/project/similar-rs/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Rust-powered text diffing for Python: bindings to the
[`similar`](https://github.com/mitsuhiko/similar) crate by Armin Ronacher.
It also ships a drop-in replacement for the standard library's `difflib`.

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

Change one import line and the diffing runs in Rust:

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
| `SequenceMatcher.find_longest_match` | `NotImplementedError` |

Known differences:

- `isjunk` is ignored; passing one raises a `RuntimeWarning`.
- `autojunk` is ignored: results always match `autojunk=False`.
- Inputs must be `str` or sequences of `str`.
- Opcodes are a valid edit script, but not byte-for-byte the one stdlib
  produces — it is a different algorithm. `ratio()` can therefore differ
  from stdlib's on inputs with several equally good alignments.

## Limitations

No `isjunk`/`autojunk`, `str` only (no `bytes`), and no grapheme or
Unicode-word granularity yet. Open an issue if you need any of these.

## Benchmarks

Coming soon; the goal of this project is to be a much faster drop-in for
`difflib` on large inputs.

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
[LICENSE](LICENSE).
