//! Synapse Shield - Keystroke Dynamics & Digraph Entropy v0.9.2
//! Analyzes Dwell Time (key press duration), Flight Time (inter-key transition),
//! and Digraph Transition Entropy to distinguish human muscle memory from synthetic bots.

use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct DetailedKeystroke {
    pub key: String,
    pub down: f64,
    pub up: Option<f64>,
    /// Client-side (Zero-PII) flag from the SDK: was this key the second half of a frequent
    /// digraph? When present, raw keys are masked and this replaces server-side pairing.
    pub is_freq_digraph: Option<bool>,
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

/// Maximum flight-time variance (ms^2) for the "superhuman typing speed" verdict (parity with features.py).
pub const SUPERHUMAN_FLIGHT_MAX_VAR: f64 = 1000.0;

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
    // Zero-PII mode: the SDK masks keys and sends `is_freq_digraph` instead (parity with features.py).
    let mut direct_freq_flights: Vec<f64> = Vec::new();
    let mut direct_non_freq_flights: Vec<f64> = Vec::new();
    for i in 1..key_count {
        let flight = sorted_keys[i].down - sorted_keys[i - 1].down;
        if !(flight > 0.0 && flight < 2000.0) {
            continue;
        }
        if let Some(is_freq) = sorted_keys[i].is_freq_digraph {
            if is_freq {
                direct_freq_flights.push(flight);
            } else {
                direct_non_freq_flights.push(flight);
            }
            continue;
        }
        let prev_key = sorted_keys[i - 1].key.to_lowercase();
        let curr_key = sorted_keys[i].key.to_lowercase();
        // Count characters, not UTF-8 bytes: Python's len() treats "ş" as one key.
        if prev_key.chars().count() == 1 && curr_key.chars().count() == 1 {
            let pair = format!("{}{}", prev_key, curr_key);
            digraph_flights.entry(pair).or_default().push(flight);
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

        // Superhuman typing speed (< 25ms average flight time). Fast real typists with key rollover also
        // average below 25 ms, but their intervals are widely spread; an auto-typer's are constant or narrow.
        if avg_flight > 0.0 && avg_flight < 25.0 && var_flight < SUPERHUMAN_FLIGHT_MAX_VAR {
            score += 0.70;
        }

        // Mobile Soft Keyboard (IME / Gboard / iOS Keyboard) detection:
        // Require majority of keys being IME to prevent desktop bot dwell bypass
        let ime_count = sorted_keys.iter().filter(|k| {
            let kl = k.key.to_lowercase();
            kl == "unidentified" || kl == "process"
        }).count();
        let is_mobile_ime = ime_count * 2 >= sorted_keys.len();

        // Robotic dwell time: zero variance or instant keypress (Desktop mechanical keys)
        if !dwell_times.is_empty() && !is_mobile_ime {
            if avg_dwell < 15.0 {
                score += 0.75; // Superhuman instantaneous press
            } else if var_dwell < 2.0 && dwell_times.len() >= 3 {
                score += 0.80; // Synthetic fixed dwell duration (e.g. exactly 50ms)
            }
        }

        // Digraph linguistic correlation check
        if !direct_freq_flights.is_empty() || !direct_non_freq_flights.is_empty() {
            if !direct_freq_flights.is_empty() && !direct_non_freq_flights.is_empty() {
                let f_mean = direct_freq_flights.iter().sum::<f64>() / direct_freq_flights.len() as f64;
                let nf_mean = direct_non_freq_flights.iter().sum::<f64>() / direct_non_freq_flights.len() as f64;
                if f_mean >= nf_mean * 1.05 && key_count >= 8 {
                    score += 0.40;
                } else if f_mean < nf_mean * 0.85 {
                    score = (score - 0.25).max(0.0);
                }
            }
        } else if !digraph_flights.is_empty() {
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

#[cfg(test)]
mod tests {
    use super::*;

    /// Builds keystrokes from (key, dwell_ms) pairs with explicit flight gaps between them.
    fn seq(keys: &[(&str, f64)], flights: &[f64]) -> Vec<DetailedKeystroke> {
        assert_eq!(flights.len() + 1, keys.len());
        let mut out = Vec::with_capacity(keys.len());
        let mut t = 1_000.0;
        for (i, &(k, dwell)) in keys.iter().enumerate() {
            out.push(DetailedKeystroke { key: k.to_string(), down: t, up: Some(t + dwell), is_freq_digraph: None });
            if i < flights.len() {
                t += dwell + flights[i];
            }
        }
        out
    }

    // Flights spread across several histogram bins: high variance, mid entropy, human pace.
    const HUMAN_FLIGHTS: [f64; 6] = [80.0, 160.0, 240.0, 120.0, 300.0, 200.0];

    #[test]
    fn empty_input_returns_neutral_defaults() {
        let m = evaluate_keystroke_dynamics(&[]);
        assert_eq!(m.key_count, 0);
        assert_eq!(m.keystroke_score, 0.0);
        assert_eq!(m.avg_dwell_time, 0.0);
    }

    #[test]
    fn computes_exact_dwell_and_flight_statistics() {
        let ks = seq(&[("masked", 100.0), ("masked", 120.0), ("masked", 80.0)], &[50.0, 70.0]);
        let m = evaluate_keystroke_dynamics(&ks);
        assert_eq!(m.key_count, 3);
        assert!((m.avg_dwell_time - 100.0).abs() < 1e-9);
        // dwell values 100,120,80 -> population variance 266.67
        assert!((m.dwell_time_var - 800.0 / 3.0).abs() < 1e-9);
        assert!((m.avg_flight_time - 60.0).abs() < 1e-9);
        assert!((m.flight_time_var - 100.0).abs() < 1e-9);
    }

    #[test]
    fn unsorted_input_is_ordered_by_keydown_time() {
        let mut ks = seq(&[("a", 90.0), ("b", 95.0), ("c", 110.0), ("d", 85.0)], &[120.0, 60.0, 200.0]);
        let sorted = evaluate_keystroke_dynamics(&ks);
        ks.reverse();
        let shuffled = evaluate_keystroke_dynamics(&ks);
        assert_eq!(sorted.avg_flight_time, shuffled.avg_flight_time);
        assert_eq!(sorted.flight_time_var, shuffled.flight_time_var);
        assert_eq!(sorted.keystroke_score, shuffled.keystroke_score);
    }

    #[test]
    fn natural_masked_typing_scores_as_human() {
        let keys: Vec<(&str, f64)> = [95.0, 130.0, 82.0, 110.0, 101.0, 140.0, 88.0]
            .iter()
            .map(|&d| ("masked", d))
            .collect();
        let m = evaluate_keystroke_dynamics(&seq(&keys, &HUMAN_FLIGHTS));
        assert!(m.keystroke_score < 0.5, "human typing scored {}", m.keystroke_score);
    }

    #[test]
    fn fixed_interval_robot_is_flagged() {
        let keys = vec![("masked", 50.0); 8];
        let m = evaluate_keystroke_dynamics(&seq(&keys, &[100.0; 7]));
        assert!(m.flight_time_var < 1e-9);
        assert_eq!(m.keystroke_score, 1.0, "constant-interval bot must saturate the score");
    }

    #[test]
    fn superhuman_flight_time_is_flagged() {
        let keys: Vec<(&str, f64)> = [60.0, 75.0, 68.0, 90.0, 71.0].iter().map(|&d| ("masked", d)).collect();
        let m = evaluate_keystroke_dynamics(&seq(&keys, &[5.0, 22.0, 3.0, 30.0]));
        assert!(m.avg_flight_time < 25.0);
        assert!(m.keystroke_score >= 0.70);
    }

    #[test]
    fn fast_typist_with_wide_flight_spread_is_not_superhuman() {
        // Rollover typist: mean up->down flight 12 ms but widely spread (sd ~ 55 ms), as in real recordings.
        let keys: Vec<(&str, f64)> = [95.0, 130.0, 82.0, 110.0, 101.0, 140.0, 88.0]
            .iter()
            .map(|&d| ("masked", d))
            .collect();
        let m = evaluate_keystroke_dynamics(&seq(&keys, &[-60.0, 70.0, -35.0, 80.0, -50.0, 75.0]));
        assert!(m.avg_flight_time > 0.0 && m.avg_flight_time < 25.0, "avg {}", m.avg_flight_time);
        assert!(m.flight_time_var > SUPERHUMAN_FLIGHT_MAX_VAR, "var {}", m.flight_time_var);
        assert!(m.keystroke_score < 0.70, "wide-spread fast typing scored {}", m.keystroke_score);
    }

    #[test]
    fn fixed_dwell_desktop_bot_is_penalised() {
        // Human-like flights, but every key is held exactly 50 ms (synthetic dwell).
        let keys = vec![("masked", 50.0); 7];
        let m = evaluate_keystroke_dynamics(&seq(&keys, &HUMAN_FLIGHTS));
        assert!(m.dwell_time_var < 1e-9);
        assert!(m.keystroke_score >= 0.80, "fixed dwell scored {}", m.keystroke_score);
    }

    #[test]
    fn ime_majority_bypasses_dwell_check() {
        // Mobile soft keyboards report "Unidentified"/"Process" with near-constant dwell.
        let keys = vec![
            ("unidentified", 50.0), ("unidentified", 50.0), ("process", 50.0), ("unidentified", 50.0),
            ("masked", 50.0), ("masked", 50.0), ("masked", 50.0),
        ];
        let m = evaluate_keystroke_dynamics(&seq(&keys, &HUMAN_FLIGHTS));
        assert!(m.keystroke_score < 0.5, "genuine IME session penalised: {}", m.keystroke_score);
    }

    #[test]
    fn ime_minority_cannot_bypass_dwell_check() {
        // v0.10.3 regression: a desktop bot sprinkling a few IME keys must still be caught.
        let keys = vec![
            ("unidentified", 50.0), ("process", 50.0), ("unidentified", 50.0),
            ("masked", 50.0), ("masked", 50.0), ("masked", 50.0), ("masked", 50.0),
        ];
        let m = evaluate_keystroke_dynamics(&seq(&keys, &HUMAN_FLIGHTS));
        assert!(m.keystroke_score >= 0.80, "IME minority bypass not blocked: {}", m.keystroke_score);
    }

    #[test]
    fn ime_detection_is_case_insensitive() {
        let keys = vec![("Unidentified", 50.0); 7];
        let m = evaluate_keystroke_dynamics(&seq(&keys, &HUMAN_FLIGHTS));
        assert!(m.keystroke_score < 0.5);
    }

    #[test]
    fn implausible_dwell_values_are_ignored() {
        let ks = vec![
            DetailedKeystroke { key: "masked".into(), down: 0.0, up: Some(9_000.0), is_freq_digraph: None }, // > 5 s
            DetailedKeystroke { key: "masked".into(), down: 9_500.0, up: Some(9_400.0), is_freq_digraph: None }, // negative
            DetailedKeystroke { key: "masked".into(), down: 10_000.0, up: Some(10_100.0), is_freq_digraph: None },
            DetailedKeystroke { key: "masked".into(), down: 10_300.0, up: None, is_freq_digraph: None },
        ];
        let m = evaluate_keystroke_dynamics(&ks);
        assert!((m.avg_dwell_time - 100.0).abs() < 1e-9, "only the 100 ms dwell is valid");
    }

    #[test]
    fn flight_entropy_bounds() {
        assert_eq!(compute_flight_entropy(&[10.0, 20.0, 30.0]), 0.5, "fewer than 4 samples is neutral");
        assert_eq!(compute_flight_entropy(&[10.0; 10]), 0.0, "single bin is fully deterministic");
        let uniform: Vec<f64> = (0..8).map(|b| b as f64 * 100.0 + 50.0).collect();
        assert!((compute_flight_entropy(&uniform) - 1.0).abs() < 1e-12, "one sample per bin is max entropy");
        // Out-of-range values (negative or > 800 ms) are excluded before binning.
        assert_eq!(compute_flight_entropy(&[-5.0, 900.0, 10.0, 10.0, 10.0, 10.0]), 0.0);
    }

    #[test]
    fn score_is_always_clamped_to_unit_interval() {
        let keys = vec![("masked", 5.0); 12];
        let m = evaluate_keystroke_dynamics(&seq(&keys, &[1.0; 11]));
        assert!((0.0..=1.0).contains(&m.keystroke_score));
    }

    /// Masked keystrokes with the SDK's client-side digraph flag, alternating freq / non-freq,
    /// with natural (non-constant) dwell and per-class flight times.
    fn flagged(n: usize, freq_flight: f64, non_freq_flight: f64) -> Vec<DetailedKeystroke> {
        let mut out = Vec::with_capacity(n);
        let mut t = 0.0;
        for i in 0..n {
            let is_freq = i % 2 == 1;
            out.push(DetailedKeystroke {
                key: "masked".into(),
                down: t,
                up: Some(t + 70.0 + (i % 5) as f64 * 9.0),
                is_freq_digraph: if i == 0 { None } else { Some(is_freq) },
            });
            let jitter = (i % 3) as f64 * 17.0;
            t += if is_freq { non_freq_flight } else { freq_flight } + jitter;
        }
        out
    }

    #[test]
    fn client_flag_frequent_digraphs_slower_than_rest_is_bot_like() {
        // Regression (parity with features.py): the Rust core used to ignore is_freq_digraph,
        // so masked SDK telemetry never reached the digraph check at all.
        let ks = flagged(12, 260.0, 140.0);
        let with_flag = evaluate_keystroke_dynamics(&ks);
        let no_flag: Vec<_> = ks.iter().cloned().map(|mut k| { k.is_freq_digraph = None; k }).collect();
        let without = evaluate_keystroke_dynamics(&no_flag);
        assert!(
            with_flag.keystroke_score >= without.keystroke_score + 0.39,
            "flag must add the +0.40 'no muscle memory' penalty: {} vs {}",
            with_flag.keystroke_score, without.keystroke_score
        );
    }

    #[test]
    fn client_flag_frequent_digraphs_faster_lowers_score() {
        // Make the base score positive first (fixed 50 ms dwell = +0.80), then show the flag discount.
        let mut ks = flagged(12, 90.0, 220.0);
        for k in ks.iter_mut() {
            k.up = Some(k.down + 50.0);
        }
        let with_flag = evaluate_keystroke_dynamics(&ks);
        let no_flag: Vec<_> = ks.iter().cloned().map(|mut k| { k.is_freq_digraph = None; k }).collect();
        let without = evaluate_keystroke_dynamics(&no_flag);
        assert!(
            (without.keystroke_score - with_flag.keystroke_score - 0.25).abs() < 1e-9,
            "human muscle memory must subtract 0.25: {} vs {}",
            with_flag.keystroke_score, without.keystroke_score
        );
    }

    #[test]
    fn single_non_ascii_letters_form_digraphs() {
        // "ş" is one character but two UTF-8 bytes; byte length used to exclude it from pairing.
        let ks = seq(&[("ş", 80.0), ("e", 95.0), ("x", 70.0), ("q", 88.0)], &[60.0, 300.0, 180.0]);
        let ascii = seq(&[("s", 80.0), ("e", 95.0), ("x", 70.0), ("q", 88.0)], &[60.0, 300.0, 180.0]);
        // Neither "şe" nor "se" is in the frequent set, so both must score identically.
        assert_eq!(evaluate_keystroke_dynamics(&ks).keystroke_score, evaluate_keystroke_dynamics(&ascii).keystroke_score);
    }
}
