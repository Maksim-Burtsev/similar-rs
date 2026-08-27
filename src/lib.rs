use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use similar::{Algorithm, DiffTag, TextDiff};

// Algorithm is #[non_exhaustive], so match on the name instead of the enum.
fn parse_algorithm(s: &str) -> PyResult<Algorithm> {
    match s {
        "myers" => Ok(Algorithm::Myers),
        "raw-myers" => Ok(Algorithm::RawMyers),
        "patience" => Ok(Algorithm::Patience),
        "lcs" => Ok(Algorithm::Lcs),
        "hunt" => Ok(Algorithm::Hunt),
        "histogram" => Ok(Algorithm::Histogram),
        other => Err(PyValueError::new_err(format!(
            "unknown algorithm {other:?}; expected one of: myers, raw-myers, patience, lcs, hunt, histogram"
        ))),
    }
}

fn tag_str(tag: DiffTag) -> &'static str {
    match tag {
        DiffTag::Equal => "equal",
        DiffTag::Delete => "delete",
        DiffTag::Insert => "insert",
        DiffTag::Replace => "replace",
    }
}

/// Render a unified diff of two texts.
#[pyfunction]
#[pyo3(signature = (old, new, context_radius=3, algorithm="myers", header=None))]
fn unified_diff(
    py: Python<'_>,
    old: &str,
    new: &str,
    context_radius: usize,
    algorithm: &str,
    header: Option<(String, String)>,
) -> PyResult<String> {
    let alg = parse_algorithm(algorithm)?;
    let header = header.as_ref().map(|(a, b)| (a.as_str(), b.as_str()));
    Ok(py.detach(|| similar::udiff::unified_diff(alg, old, new, context_radius, header)))
}

/// Diff two texts at the given granularity, returning (tag, i1, i2, j1, j2) tuples.
#[pyfunction]
#[pyo3(signature = (kind, old, new, algorithm="myers"))]
fn opcodes_str(
    py: Python<'_>,
    kind: &str,
    old: String,
    new: String,
    algorithm: &str,
) -> PyResult<Vec<(&'static str, usize, usize, usize, usize)>> {
    let alg = parse_algorithm(algorithm)?;
    if !matches!(kind, "lines" | "words" | "chars") {
        return Err(PyValueError::new_err(format!(
            "unknown granularity {kind:?}; expected one of: lines, words, chars"
        )));
    }
    Ok(py.detach(|| {
        // Owned Strings cross the GIL boundary; borrow them only inside the closure.
        let mut cfg = TextDiff::configure();
        cfg.algorithm(alg);
        let (o, n) = (old.as_str(), new.as_str());
        let diff = match kind {
            "words" => cfg.diff_words(o, n),
            "chars" => cfg.diff_chars(o, n),
            _ => cfg.diff_lines(o, n),
        };
        diff.ops()
            .iter()
            .map(|op| {
                let (tag, r1, r2) = op.as_tag_tuple();
                (tag_str(tag), r1.start, r1.end, r2.start, r2.end)
            })
            .collect()
    }))
}

#[pymodule]
fn _similar(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__doc__", "Rust bindings to the `similar` diffing crate.")?;
    m.add_function(wrap_pyfunction!(unified_diff, m)?)?;
    m.add_function(wrap_pyfunction!(opcodes_str, m)?)?;
    Ok(())
}
