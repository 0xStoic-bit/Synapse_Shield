//! Synapse Shield - Keystroke Dynamics & Digraph Entropy v0.9.2
//! Analyzes Dwell Time (key press duration), Flight Time (inter-key transition),
//! and Digraph Transition Entropy to distinguish human muscle memory from synthetic bots.

use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct DetailedKeystroke {
    pub key: String,
    pub down: f64,
    pub up: Option<f64>,
}

#[derive(Debug, Clone, Copy, Default)]
pub struct KeystrokeMetrics {
    pub key_count: usize,
    pub avg_dwell_time: f64,
    pub dwell_time_var: f64,
    pub avg_flight_time: f64,
    pub flight_time_var: f64,
    pub digraph_entropy: f64,
    pub keystroke_score: f64, // 0.0 (natural human) .. 1.0 (robotic bot)
}

/// Evaluates keystroke dynamics telemetry including dwell time, flight time, and digraph entropy.
pub fn evaluate_keystroke_dynamics(keystrokes: &[DetailedKeystroke]) -> KeystrokeMetrics {
    let key_count = keystrokes.len();
    if key_count == 0 {
        return KeystrokeMetrics::default();
    }

    // 1. Sort keystrokes chronologically by keydown timestamp
    let mut sorted_keys = keystrokes.to_vec();
    sorted_keys.sort_by(|a, b| a.down.partial_cmp(&b.down).unwrap_or(std::cmp::Ordering::Equal));

    // 2. Dwell Time Analysis (Td = tup - tdown)
    let mut dwell_times = Vec::with_capacity(key_count);
    for k in &sorted_keys {
        if let Some(up_time) = k.up {
            let dwell = up_time - k.down;
            if dwell > 0.0 && dwell < 5000.0 {
                dwell_times.push(dwell);
            }
        }
    }

    let (avg_dwell, var_dwell) = if !dwell_times.is_empty() {
        let count = dwell_times.len() as f64;
        let avg: f64 = dwell_times.iter().sum::<f64>() / count;
        let var: f64 = dwell_times.iter().map(|&d| (d - avg).powi(2)).sum::<f64>() / count;
        (avg, var)
    } else {
        (0.0, 0.0)
    };

    // 3. Flight Time Analysis (Tf = tdown[i+1] - tup[i] or tdown[i+1] - tdown[i])
    let mut flight_times = Vec::with_capacity(key_count.saturating_sub(1));
    for i in 1..key_count {
        let prev = &sorted_keys[i - 1];
        let curr = &sorted_keys[i];
        
        let flight = if let Some(prev_up) = prev.up {
            curr.down - prev_up
        } else {
            curr.down - prev.down
        };

        if flight > -500.0 && flight < 5000.0 {
            flight_times.push(flight);
        }
    }

    let (avg_flight, var_flight) = if !flight_times.is_empty() {
        let count = flight_times.len() as f64;
        let avg: f64 = flight_times.iter().sum::<f64>() / count;
        let var: f64 = flight_times.iter().map(|&f| (f - avg).powi(2)).sum::<f64>() / count;
        (avg, var)
    } else {
        (0.0, 0.0)
    };

    // 4. Digraph N-Gram & Shannon Entropy Analysis
    // Sık kullanılan harf ikilileri (İngilizce & Türkçe ortak frekans kümesi)
    const FREQUENT_DIGRAPHS: &[&str] = &[
        "th", "er", "on", "an", "re", "he", "in", "ed", "nd", "ha",
        "at", "en", "es", "of", "or", "nt", "ea", "ti", "to", "it",
        "st", "io", "le", "is", "ou", "ar", "as", "de", "rt", "ve",
        "la", "le", "ik", "ak", "el", "al", "ma", "me", "ba", "ka"
    ];

    let mut digraph_flights: HashMap<String, Vec<f64>> = HashMap::new();
    for i in 1..key_count {
        let prev_key = sorted_keys[i - 1].key.to_lowercase();
        let curr_key = sorted_keys[i].key.to_lowercase();
        
        if prev_key.len() == 1 && curr_key.len() == 1 {
            let pair = format!("{}{}", prev_key, curr_key);
            let flight = sorted_keys[i].down - sorted_keys[i - 1].down;
            if flight > 0.0 && flight < 2000.0 {
                digraph_flights.entry(pair).or_default().push(flight);
            }
        }
    }

    // Flight time histogram entropy calculation (8 bins between 0 and 400ms)
    let entropy = compute_flight_entropy(&flight_times);

    // 5. Bot vs Human Keystroke Classification Score
    let mut score: f64 = 0.0;

    if key_count >= 3 {
        // Robotic timer detection: deterministic flight interval
        if var_flight < 2.0 && flight_times.len() >= 3 {
            score += 0.85; // Fixed interval bot
        } else if var_flight < 15.0 && flight_times.len() >= 4 {
            score += 0.60;
        }

        // Superhuman typing speed (< 25ms average flight time)
        if avg_flight > 0.0 && avg_flight < 25.0 {
            score += 0.70;
        }

        // Robotic dwell time: zero variance or instant keypress
        if !dwell_times.is_empty() {
            if avg_dwell < 15.0 {
                score += 0.75; // Superhuman instantaneous press
            } else if var_dwell < 2.0 && dwell_times.len() >= 3 {
                score += 0.80; // Synthetic fixed dwell duration (e.g. exactly 50ms)
            }
        }

        // Digraph linguistic correlation check
        if !digraph_flights.is_empty() {
            let mut freq_avg = Vec::new();
            let mut non_freq_avg = Vec::new();

            for (pair, times) in &digraph_flights {
                let mean_t: f64 = times.iter().sum::<f64>() / (times.len() as f64);
                if FREQUENT_DIGRAPHS.contains(&pair.as_str()) {
                    freq_avg.push(mean_t);
                } else {
                    non_freq_avg.push(mean_t);
                }
            }

            // In humans with muscle memory, frequent digraphs are executed noticeably faster
            if !freq_avg.is_empty() && !non_freq_avg.is_empty() {
                let f_mean: f64 = freq_avg.iter().sum::<f64>() / (freq_avg.len() as f64);
                let nf_mean: f64 = non_freq_avg.iter().sum::<f64>() / (non_freq_avg.len() as f64);

                if f_mean >= nf_mean * 1.05 && key_count >= 8 {
                    // Artificial bot with uniform random generator has no linguistic memory
                    score += 0.40;
                } else if f_mean < nf_mean * 0.85 {
                    // Natural human muscle memory: frequent combinations are noticeably faster!
                    score = (score - 0.25).max(0.0);
                }
            }
        }

        // Entropy verification
        if entropy < 0.15 && flight_times.len() >= 5 {
            score += 0.70; // Highly deterministic
        } else if entropy > 0.98 && flight_times.len() >= 8 {
            score += 0.50; // Pure uniform distribution without cognitive variance
        }
    }

    KeystrokeMetrics {
        key_count,
        avg_dwell_time: avg_dwell,
        dwell_time_var: var_dwell,
        avg_flight_time: avg_flight,
        flight_time_var: var_flight,
        digraph_entropy: entropy,
        keystroke_score: score.clamp(0.0, 1.0),
    }
}

/// Computes normalized Shannon entropy of flight time distribution across 8 bins (0 - 400ms)
fn compute_flight_entropy(flights: &[f64]) -> f64 {
    let valid_flights: Vec<f64> = flights.iter().copied().filter(|&f| f >= 0.0 && f <= 800.0).collect();
    let n = valid_flights.len();
    if n < 4 {
        return 0.5; // Neutral
    }

    const NUM_BINS: usize = 8;
    const BIN_WIDTH: f64 = 800.0 / (NUM_BINS as f64);
    let mut bins = [0usize; NUM_BINS];

    for &f in &valid_flights {
        let bin_idx = ((f / BIN_WIDTH).floor() as usize).min(NUM_BINS - 1);
        bins[bin_idx] += 1;
    }

    let mut entropy = 0.0;
    let n_f64 = n as f64;
    for &count in &bins {
        if count > 0 {
            let p = (count as f64) / n_f64;
            entropy -= p * p.log2();
        }
    }

    let max_entropy = (NUM_BINS as f64).log2();
    if max_entropy > 0.0 {
        entropy / max_entropy
    } else {
        0.0
    }
}
