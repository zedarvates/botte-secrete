//! Layer — a single layer in the feedforward network.
//!
//! Each layer has:
//!   - weights: [output_size × input_size] matrix (row-major)
//!   - biases:  [output_size] vector
//!   - activation: the activation function to apply

use crate::activation::Activation;
use crate::matrix::{mat_vec_mul, add_bias};
use serde::Deserialize;

/// A single neural network layer.
#[derive(Debug, Clone, Deserialize)]
pub struct Layer {
    /// Weight matrix: rows = output_size, cols = input_size
    pub weights: Vec<f64>,
    /// Bias vector: length = output_size
    pub biases: Vec<f64>,
    /// Activation function
    pub activation: Activation,
}

impl Layer {
    /// Number of input neurons (columns of the weight matrix).
    pub fn input_size(&self) -> usize {
        if self.weights.is_empty() { 0 } else { self.weights.len() / self.biases.len() }
    }

    /// Number of output neurons (rows of the weight matrix).
    pub fn output_size(&self) -> usize {
        self.biases.len()
    }

    /// Forward pass: input → weighted → biased → activated
    pub fn forward(&self, input: &[f64]) -> Vec<f64> {
        let rows = self.output_size();
        let cols = self.input_size();
        let mut output = mat_vec_mul(&self.weights, input, rows, cols);
        add_bias(&mut output, &self.biases);
        self.activation.apply(&mut output);
        output
    }
}
