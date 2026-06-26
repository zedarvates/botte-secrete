//! Inference — high-level forward pass helpers.
//!
//! Wraps Model::predict for ergonomic use from Python via subprocess,
//! or from the CLI.

use crate::model::Model;

/// Load model from JSON and predict on a single input vector.
/// Returns JSON string of the output.
pub fn predict_json(model_json: &str, input: &[f64]) -> Result<String, String> {
    let model = Model::from_json(model_json)?;
    let output = model.predict(input)?;
    serde_json::to_string(&output)
        .map_err(|e| format!("JSON serialize error: {e}"))
}

/// Load model from weights struct and predict.
pub fn predict_from_weights(weights: &crate::Weights, input: &[f64]) -> Result<Vec<f64>, String> {
    let model = Model::from_weights(weights)?;
    model.predict(input)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Weights;

    #[test]
    fn test_predict_json_roundtrip() {
        let json = r#"{
            "layers": [2, 3, 1],
            "weights": [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6], [0.7, 0.8, 0.9]],
            "biases": [[0.0, 0.0, 0.0], [0.0]],
            "activations": ["relu", "sigmoid"]
        }"#;
        let result = predict_json(json, &[0.5, 0.3]).unwrap();
        assert!(result.starts_with('['));
        assert!(result.ends_with(']'));
    }
}
