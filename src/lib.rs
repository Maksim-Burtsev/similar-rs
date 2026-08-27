use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use similar::{Algorithm, DiffTag, TextDiff};
use std::collections::HashMap;

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

/// Diff two sequences of strings, returning (tag, i1, i2, j1, j2) tuples.
#[pyfunction]
#[pyo3(signature = (old, new, algorithm="myers"))]
fn opcodes_seq(
    py: Python<'_>,
    old: Vec<String>,
    new: Vec<String>,
    algorithm: &str,
) -> PyResult<Vec<(&'static str, usize, usize, usize, usize)>> {
    let alg = parse_algorithm(algorithm)?;
    Ok(py.detach(|| {
        similar::capture_diff_slices(alg, &old, &new)
            .iter()
            .map(|op| {
                let (tag, r1, r2) = op.as_tag_tuple();
                (tag_str(tag), r1.start, r1.end, r2.start, r2.end)
            })
            .collect()
    }))
}

/// Return the best `n` of `possibilities` scoring at least `cutoff`, by char ratio.
#[pyfunction]
#[pyo3(signature = (word, possibilities, n=3, cutoff=0.6))]
fn get_close_matches(
    py: Python<'_>,
    word: String,
    possibilities: Vec<String>,
    n: usize,
    cutoff: f64,
) -> Vec<String> {
    py.detach(|| {
        let w: Vec<char> = word.chars().collect();
        let mut wcount: HashMap<char, isize> = HashMap::new();
        for ch in &w {
            *wcount.entry(*ch).or_insert(0) += 1;
        }
        let mut scored: Vec<(f64, String)> = possibilities
            .into_iter()
            .filter_map(|cand| {
                let c: Vec<char> = cand.chars().collect();
                let total = w.len() + c.len();
                if total == 0 {
                    return (1.0 >= cutoff).then_some((1.0, cand));
                }
                let bound = |matches: usize| 2.0 * matches as f64 / total as f64;
                // Both are upper bounds on the real ratio, and both are far cheaper
                // than a diff, so candidates that cannot reach the cutoff are dropped
                // before Myers runs. Same two filters, in the same order, as difflib.
                if bound(w.len().min(c.len())) < cutoff {
                    return None;
                }
                let mut avail: HashMap<char, isize> = HashMap::new();
                let mut common = 0usize;
                for ch in &c {
                    let numb = match avail.get(ch) {
                        Some(&n) => n,
                        None => *wcount.get(ch).unwrap_or(&0),
                    };
                    avail.insert(*ch, numb - 1);
                    if numb > 0 {
                        common += 1;
                    }
                }
                if bound(common) < cutoff {
                    return None;
                }
                let matches: usize = similar::capture_diff_slices(Algorithm::Myers, &w, &c)
                    .iter()
                    .filter_map(|op| match op.as_tag_tuple() {
                        (DiffTag::Equal, r, _) => Some(r.len()),
                        _ => None,
                    })
                    .sum();
                let ratio = bound(matches);
                (ratio >= cutoff).then_some((ratio, cand))
            })
            .collect();
        // difflib does heapq.nlargest(n, [(ratio, x), ...]), so equal ratios break
        // on the candidate itself, larger first. Rust compares Strings byte-wise
        // over UTF-8, which orders identically to Python's code-point compare.
        scored.sort_by(|a, b| {
            b.0.partial_cmp(&a.0)
                .expect("ratios are never NaN")
                .then_with(|| b.1.cmp(&a.1))
        });
        scored.into_iter().take(n).map(|(_, cand)| cand).collect()
    })
}

#[pymodule]
fn _similar(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__doc__", "Rust bindings to the `similar` diffing crate.")?;
    m.add("__debug_build__", cfg!(debug_assertions))?;
    m.add_function(wrap_pyfunction!(unified_diff, m)?)?;
    m.add_function(wrap_pyfunction!(opcodes_str, m)?)?;
    m.add_function(wrap_pyfunction!(opcodes_seq, m)?)?;
    m.add_function(wrap_pyfunction!(get_close_matches, m)?)?;
    Ok(())
}
