//! Matrix operations for the feedforward network.
//! Minimal implementation — no external dep.

/// Dot product of two vectors.
pub fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}

/// Matrix-vector multiplication: output = matrix * vector
/// matrix is shape [rows, cols], stored row-major as flat vec.
pub fn mat_vec_mul(matrix: &[f64], vector: &[f64], rows: usize, cols: usize) -> Vec<f64> {
    let mut result = vec![0.0; rows];
    for i in 0..rows {
        let start = i * cols;
        let row = &matrix[start..start + cols];
        result[i] = dot(row, vector);
    }
    result
}

/// Add bias vector to result in-place.
pub fn add_bias(result: &mut [f64], bias: &[f64]) {
    for (r, b) in result.iter_mut().zip(bias.iter()) {
        *r += b;
    }
}
