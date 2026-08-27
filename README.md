# similar-rs

Rust-powered text diffing for Python: a fast drop-in replacement for `difflib`,
powered by the [`similar`](https://github.com/mitsuhiko/similar) crate.

```python
import similar

print(similar.unified_diff("a\nb\n", "a\nc\n", header=("old", "new")))

d = similar.TextDiff("a\nb\n", "a\nc\n")
d.ops()      # [("equal", (0, 1), (0, 1)), ("replace", (1, 2), (1, 2))]
d.ratio()    # 0.5
```

## Install

```sh
pip install similar-rs
```

## License

Apache-2.0
