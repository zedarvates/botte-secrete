// Auto-generated — embedded model weights
// DO NOT EDIT

pub mod anomaly_detector;
pub mod binary_router;
pub mod effort_classifier;
pub mod error_classifier;

/// All available embedded models with their metadata.
pub const EMBEDDED_MODELS: &[(&str, fn() -> Result<String, String>, usize, usize)] = &[
    ("anomaly_detector", anomaly_detector::load, anomaly_detector::INPUT_SIZE, anomaly_detector::OUTPUT_SIZE),
    ("binary_router", binary_router::load, binary_router::INPUT_SIZE, binary_router::OUTPUT_SIZE),
    ("effort_classifier", effort_classifier::load, effort_classifier::INPUT_SIZE, effort_classifier::OUTPUT_SIZE),
    ("error_classifier", error_classifier::load, error_classifier::INPUT_SIZE, error_classifier::OUTPUT_SIZE),
];