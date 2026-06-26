//! botte_nn — Tiny feedforward neural network for Botte Secrète.
//!
//! Inference-only. Weights trained in Python (numpy) and exported as JSON.
//! Embedded in the binary at compile time via `include_bytes!`.
//!
//! Architecture:
//!   - Configurable layers: [input, hidden_1, ..., output]
//!   - Activations: ReLU, Sigmoid, Softmax, Linear
//!   - Forward pass only (training is done in Python)
//!   - Deterministic, 0 external deps beyond serde_json
//!
//! Usage:
//!   let model = botte_nn::Model::from_weights(weights)?;
//!   let output = model.predict(&[0.1, 0.5, 0.3, 0.9])?;
//!   println!("{:?}", output); // [0.02, 0.95, 0.03]

pub mod inference;
pub mod layer;
pub mod matrix;
pub mod model;
pub mod activation;
pub mod embedded;

// Re-export the main API
pub use model::Model;
pub use model::Weights;
pub use layer::Layer;
pub use activation::Activation;
pub use inference::predict_json;
