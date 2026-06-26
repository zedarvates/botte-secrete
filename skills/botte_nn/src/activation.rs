//! Activation functions for the neural network.

/// Enum of supported activation functions.
#[derive(Debug, Clone, Copy, PartialEq, serde::Deserialize)]
pub enum Activation {
    ReLU,
    Sigmoid,
    Softmax,
    Linear,
}

impl Activation {
    /// Apply activation function to a layer's output in-place.
    pub fn apply(&self, values: &mut [f64]) {
        match self {
            Activation::ReLU => relu(values),
            Activation::Sigmoid => sigmoid(values),
            Activation::Softmax => softmax(values),
            Activation::Linear => {}, // identity
        }
    }
}

fn relu(values: &mut [f64]) {
    for v in values.iter_mut() {
        if *v < 0.0 {
            *v = 0.0;
        }
    }
}

fn sigmoid(values: &mut [f64]) {
    for v in values.iter_mut() {
        *v = 1.0 / (1.0 + (-*v).exp());
    }
}

fn softmax(values: &mut [f64]) {
    let max = values.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let mut sum = 0.0;
    for v in values.iter_mut() {
        *v = (*v - max).exp();
        sum += *v;
    }
    if sum > 0.0 {
        for v in values.iter_mut() {
            *v /= sum;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_relu_positive() {
        let mut v = vec![1.0, 2.0, 0.5];
        relu(&mut v);
        assert_eq!(v, vec![1.0, 2.0, 0.5]);
    }

    #[test]
    fn test_relu_negative() {
        let mut v = vec![-1.0, 0.0, -0.5];
        relu(&mut v);
        assert_eq!(v, vec![0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_sigmoid() {
        let mut v = vec![0.0];
        sigmoid(&mut v);
        assert!((v[0] - 0.5).abs() < 1e-6);
    }

    #[test]
    fn test_softmax_sum_to_one() {
        let mut v = vec![1.0, 2.0, 3.0];
        softmax(&mut v);
        let sum: f64 = v.iter().sum();
        assert!((sum - 1.0).abs() < 1e-6);
    }
}
