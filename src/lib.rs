use pyo3::prelude::*;

#[pymodule]
fn _similar(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__doc__", "Rust bindings to the `similar` diffing crate.")?;
    Ok(())
}
