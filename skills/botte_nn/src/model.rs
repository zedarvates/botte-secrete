//! Model — the full neural network model.
//!
//! A sequence of layers. The output of layer N is the input to layer N+1.
//! The last layer's output is the model's prediction.

use crate::layer::Layer;
use serde::Deserialize;

/// Complete model weights structure (matches the JSON export format).
#[derive(Debug, Clone, Deserialize)]
pub struct Weights {
    /// Number of neurons per layer: [input, hidden_1, ..., output]
    pub layers: Vec<usize>,
    /// Weight matrices and biases for each layer (excluding input)
    pub weights: Vec<Vec<f64>>,
    pub biases: Vec<Vec<f64>>,
    /// Activation for each layer (excluding input)
    pub activations: Vec<String>,
}

/// A compiled neural network model ready for inference.
#[derive(Debug, Clone)]
pub struct Model {
    layers: Vec<Layer>,
    input_size: usize,
}

impl Model {
    /// Build a Model from the Weights definition.
    pub fn from_weights(weights: &Weights) -> Result<Self, String> {
        if weights.layers.len() < 2 {
            return Err("Need at least 2 layers (input + output)".into());
        }
        let num_hidden = weights.layers.len() - 1;
        if weights.weights.len() != num_hidden {
            return Err(format!("Expected {} weight matrices, got {}", num_hidden, weights.weights.len()));
        }
        if weights.biases.len() != num_hidden {
            return Err(format!("Expected {} bias vectors, got {}", num_hidden, weights.biases.len()));
        }
        if weights.activations.len() != num_hidden {
            return Err(format!("Expected {} activations, got {}", num_hidden, weights.activations.len()));
        }

        let first_input = weights.layers[0];
        let mut input_size = first_input;
        let mut layers = Vec::with_capacity(num_hidden);

        for i in 0..num_hidden {
            let output_size = weights.layers[i + 1];
            let w = &weights.weights[i];
            let b = &weights.biases[i];
            let act_str = &weights.activations[i];

            // Validate dimensions
            let expected_w = input_size * output_size;
            if w.len() != expected_w {
                return Err(format!("Layer {}: expected {} weights, got {}", i, expected_w, w.len()));
            }
            if b.len() != output_size {
                return Err(format!("Layer {}: expected {} biases, got {}", i, output_size, b.len()));
            }

            let activation = match act_str.as_str() {
                "relu" => crate::activation::Activation::ReLU,
                "sigmoid" => crate::activation::Activation::Sigmoid,
                "softmax" => crate::activation::Activation::Softmax,
                "linear" => crate::activation::Activation::Linear,
                other => return Err(format!("Unknown activation: {other}")),
            };

            layers.push(Layer {
                weights: w.clone(),
                biases: b.clone(),
                activation,
            });

            input_size = output_size; // next layer's input size
        }

        Ok(Model { layers, input_size: first_input })
    }

    /// Load model from a JSON string.
    pub fn from_json(json: &str) -> Result<Self, String> {
        let weights: Weights = serde_json::from_str(json)
            .map_err(|e| format!("JSON parse error: {e}"))?;
        Self::from_weights(&weights)
    }

    /// Number of input features expected.
    pub fn input_size(&self) -> usize {
        self.input_size
    }

    /// Number of output values (classes or regression values).
    pub fn output_size(&self) -> usize {
        self.layers.last().map(|l| l.output_size()).unwrap_or(0)
    }

    /// Forward pass through all layers.
    pub fn predict(&self, input: &[f64]) -> Result<Vec<f64>, String> {
        if input.len() != self.input_size {
            return Err(format!(
                "Expected {} inputs, got {}", self.input_size, input.len()
            ));
        }

        let mut current = input.to_vec();
        for layer in &self.layers {
            current = layer.forward(&current);
        }
        Ok(current)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Weights;

    #[test]
    fn test_model_from_weights() {
        let w = Weights {
            layers: vec![2, 4, 1],
            weights: vec![
                vec![0.1; 8],   // 2→4: 2*4 = 8 weights
                vec![0.2; 4],   // 4→1: 4*1 = 4 weights
            ],
            biases: vec![
                vec![0.0; 4],
                vec![0.0; 1],
            ],
            activations: vec!["relu".into(), "sigmoid".into()],
        };
        let model = Model::from_weights(&w).unwrap();
        assert_eq!(model.input_size(), 2);
        assert_eq!(model.output_size(), 1);
    }

    #[test]
    fn test_predict_output_shape() {
        let w = Weights {
            layers: vec![3, 8, 4],
            weights: vec![
                vec![0.1; 24],  // 3*8
                vec![0.2; 32],  // 8*4
            ],
            biases: vec![
                vec![0.0; 8],
                vec![0.0; 4],
            ],
            activations: vec!["relu".into(), "softmax".into()],
        };
        let model = Model::from_weights(&w).unwrap();
        let out = model.predict(&[0.5, 0.3, 0.1]).unwrap();
        assert_eq!(out.len(), 4);
        // Softmax output sums to ~1.0
        let sum: f64 = out.iter().sum();
        assert!((sum - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_wrong_input_size_errors() {
        let w = Weights {
            layers: vec![2, 1],
            weights: vec![vec![0.1; 2]],
            biases: vec![vec![0.0; 1]],
            activations: vec!["linear".into()],
        };
        let model = Model::from_weights(&w).unwrap();
        let result = model.predict(&[0.5, 0.3, 0.1]); // 3 inputs, expects 2
        assert!(result.is_err());
    }

    #[test]
    fn test_from_json_roundtrip() {
        let json = r#"{
            "layers": [2, 3, 1],
            "weights": [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6], [0.7, 0.8, 0.9]],
            "biases": [[0.0, 0.0, 0.0], [0.0]],
            "activations": ["relu", "sigmoid"]
        }"#;
        let model = Model::from_json(json).unwrap();
        assert_eq!(model.input_size(), 2);
        assert_eq!(model.output_size(), 1);
        let out = model.predict(&[1.0, 0.5]).unwrap();
        assert_eq!(out.len(), 1);
    }

    #[test]
    fn test_deterministic() {
        let json = r#"{
            "layers": [2, 4, 2],
            "weights": [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8], [0.9, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]],
            "biases": [[0.0, 0.0, 0.0, 0.0], [0.0, 0.0]],
            "activations": ["relu", "softmax"]
        }"#;
        let model = Model::from_json(json).unwrap();
        let a = model.predict(&[0.5, 0.1]).unwrap();
        let b = model.predict(&[0.5, 0.1]).unwrap();
        assert_eq!(a, b);
    }
}
