/// botte_nn_cli — CLI binary with embedded model support.
///
/// Usage:
///     botte_nn_cli predict <model.json> <input floats...>
///     botte_nn_cli embedded <model_name> <input floats...>
///     botte_nn_cli list
///
/// Examples:
///     botte_nn_cli predict models/effort_classifier.json 0.1 0.2 0.8 0.0
///     botte_nn_cli embedded effort_classifier 0.1 0.2 0.8 0.0
///     botte_nn_cli list
use std::env;
use std::fs;
use std::process;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage:");
        eprintln!("  {} predict <model.json> <input floats...>", args[0]);
        eprintln!("  {} embedded <model_name> <input floats...>", args[0]);
        eprintln!("  {} list", args[0]);
        process::exit(1);
    }

    match args[1].as_str() {
        "predict" => cmd_predict(&args),
        "embedded" => cmd_embedded(&args),
        "list" => cmd_list(),
        _ => {
            eprintln!("Unknown command: {}", args[1]);
            process::exit(1);
        }
    }
}

fn parse_input(args: &[String], start: usize) -> Vec<f64> {
    args[start..]
        .iter()
        .map(|s| s.parse().unwrap_or_else(|_| {
            eprintln!("Invalid float: {s}");
            process::exit(1);
        }))
        .collect()
}

fn cmd_predict(args: &[String]) {
    if args.len() < 4 {
        eprintln!("Usage: {} predict <model.json> <input floats...>", args[0]);
        process::exit(1);
    }
    let model_path = &args[2];
    let input = parse_input(args, 3);

    let json = fs::read_to_string(model_path).unwrap_or_else(|e| {
        eprintln!("Failed to read {model_path}: {e}");
        process::exit(1);
    });

    match botte_nn::predict_json(&json, &input) {
        Ok(output) => println!("{output}"),
        Err(e) => {
            eprintln!("Prediction error: {e}");
            process::exit(1);
        }
    }
}

fn cmd_embedded(args: &[String]) {
    if args.len() < 4 {
        eprintln!("Usage: {} embedded <model_name> <input floats...>", args[0]);
        eprintln!("Available: effort_classifier, binary_router, anomaly_detector, token_estimator, priority_estimator");
        process::exit(1);
    }
    let model_name = &args[2];
    let input = parse_input(args, 3);

    // Find and load the embedded model
    let json = match model_name.as_str() {
        "effort_classifier" => botte_nn::embedded::effort_classifier::load(),
        "binary_router" => botte_nn::embedded::binary_router::load(),
        "anomaly_detector" => botte_nn::embedded::anomaly_detector::load(),
        "token_estimator" => botte_nn::embedded::token_estimator::load(),
        "priority_estimator" => botte_nn::embedded::priority_estimator::load(),
        _ => {
            eprintln!("Unknown embedded model: {model_name}");
            eprintln!("Available: effort_classifier, binary_router, anomaly_detector, token_estimator, priority_estimator");
            process::exit(1);
        }
    };

    let json = json.unwrap_or_else(|e| {
        eprintln!("Failed to load embedded model: {e}");
        process::exit(1);
    });

    match botte_nn::predict_json(&json, &input) {
        Ok(output) => println!("{output}"),
        Err(e) => {
            eprintln!("Prediction error: {e}");
            process::exit(1);
        }
    }
}

fn cmd_list() {
    println!("Embedded models:");
    for (name, _, input_size, output_size) in botte_nn::embedded::EMBEDDED_MODELS {
        println!("  {name:<20} {input_size} inputs → {output_size} outputs");
    }
    println!("\nUse: {} embedded <name> <input...>", env::args().next().unwrap_or_default());
}
