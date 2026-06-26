// Auto-generated — embedded model weights
// DO NOT EDIT

pub mod anomaly_detector;
pub mod binary_router;
pub mod effort_classifier;
pub mod priority_estimator;
pub mod token_estimator;

/// All available embedded models with their metadata.
pub const EMBEDDED_MODELS: &[(&str, fn() -> Result<String, String>, usize, usize)] = &[
    ("anomaly_detector", anomaly_detector::load, anomaly_detector::INPUT_SIZE, anomaly_detector::OUTPUT_SIZE),
    ("binary_router", binary_router::load, binary_router::INPUT_SIZE, binary_router::OUTPUT_SIZE),
    ("effort_classifier", effort_classifier::load, effort_classifier::INPUT_SIZE, effort_classifier::OUTPUT_SIZE),
    ("priority_estimator", priority_estimator::load, priority_estimator::INPUT_SIZE, priority_estimator::OUTPUT_SIZE),
    ("token_estimator", token_estimator::load, token_estimator::INPUT_SIZE, token_estimator::OUTPUT_SIZE),
];