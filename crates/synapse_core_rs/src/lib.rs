use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

mod kinematics;
mod nonce_cache;
use kinematics::{compute_kinematics, ExtractedFeatures, KeyPoint, MousePoint, RawTelemetry};
use nonce_cache::{
    ban_ip_global, clear_all_global, consume_nonce_global, get_stats_global, hydrate_bans_global,
    is_ip_banned_global, unban_ip_global,
};

fn features_to_pydict<'py>(py: Python<'py>, feat: &ExtractedFeatures) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new_bound(py);
    dict.set_item("mouse_points", feat.mouse_points)?;
    dict.set_item("total_distance", feat.total_distance)?;
    dict.set_item("straightness", feat.straightness)?;
    dict.set_item("avg_velocity", feat.avg_velocity)?;
    dict.set_item("max_velocity", feat.max_velocity)?;
    dict.set_item("velocity_var", feat.velocity_var)?;
    dict.set_item("avg_acceleration", feat.avg_acceleration)?;
    dict.set_item("acceleration_var", feat.acceleration_var)?;
    dict.set_item("avg_jerk", feat.avg_jerk)?;
    dict.set_item("dt_var", feat.dt_var)?;
    dict.set_item("click_count", feat.click_count)?;
    dict.set_item("key_count", feat.key_count)?;
    dict.set_item("key_interval_avg", feat.key_interval_avg)?;
    dict.set_item("key_interval_var", feat.key_interval_var)?;
    dict.set_item("webdriver", feat.webdriver)?;
    dict.set_item("screen_valid", feat.screen_valid)?;
    dict.set_item("scroll_count", feat.scroll_count)?;
    dict.set_item("terminal_decel_ratio", feat.terminal_decel_ratio)?;
    dict.set_item("plugins_length", feat.plugins_length)?;
    dict.set_item("touch_supported", feat.touch_supported)?;
    dict.set_item("screen_width", feat.screen_width)?;
    dict.set_item("spectral_purity", feat.spectral_purity)?;
    dict.set_item("spectral_entropy", feat.spectral_entropy)?;
    dict.set_item("submovement_count", feat.submovement_count)?;
    Ok(dict)
}

fn parse_python_telemetry(telemetry: &Bound<'_, PyAny>) -> RawTelemetry {
    let mut raw = RawTelemetry::default();
    if let Ok(dict) = telemetry.downcast::<PyDict>() {
        // 1. Browser info
        if let Ok(Some(browser_val)) = dict.get_item("browser") {
            if let Ok(browser) = browser_val.downcast::<PyDict>() {
                if let Ok(Some(wb)) = browser.get_item("webdriver") {
                    if let Ok(b) = wb.extract::<bool>() {
                        raw.webdriver = b;
                    }
                }
                let sw = browser.get_item("screen_width").ok().flatten().and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0);
                let sh = browser.get_item("screen_height").ok().flatten().and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0);
                raw.screen_width = sw;
                raw.screen_height = sh;
                if sw <= 0.0 || sh <= 0.0 || sw.is_nan() || sh.is_nan() {
                    raw.screen_valid = false;
                }
                if let Ok(Some(ts)) = browser.get_item("touch_supported") {
                    if let Ok(t) = ts.extract::<bool>() {
                        raw.touch_supported = t;
                    }
                }
                if let Ok(Some(pl)) = browser.get_item("plugins_length") {
                    if let Ok(p) = pl.extract::<i64>() {
                        raw.plugins_length = p;
                    }
                }
            }
        }

        // 2. Click count
        if let Ok(Some(clicks)) = dict.get_item("clicks") {
            if let Ok(list) = clicks.downcast::<PyList>() {
                raw.click_count = list.len();
            }
        }

        // 3. Scroll count
        if let Ok(Some(scrolls)) = dict.get_item("scrolls") {
            if let Ok(list) = scrolls.downcast::<PyList>() {
                raw.scroll_count = list.len();
            }
        }

        // 4. Keystrokes (DoS safe: max 150)
        if let Ok(Some(keystrokes)) = dict.get_item("keystrokes") {
            if let Ok(list) = keystrokes.downcast::<PyList>() {
                let limit = list.len().min(150);
                for i in 0..limit {
                    if let Ok(item) = list.get_item(i) {
                        if let Ok(k_dict) = item.downcast::<PyDict>() {
                            let mut t_opt = None;
                            for key_name in &["t", "down", "time"] {
                                if let Ok(Some(val)) = k_dict.get_item(key_name) {
                                    if let Ok(num) = val.extract::<f64>() {
                                        if !num.is_nan() && !num.is_infinite() {
                                            t_opt = Some(num);
                                            break;
                                        }
                                    }
                                }
                            }
                            if let Some(t) = t_opt {
                                raw.keystrokes.push(KeyPoint { t });
                            }
                        }
                    }
                }
            }
        }

        // 5. Mouse movements
        if let Ok(Some(mouse)) = dict.get_item("mouse_movements") {
            if let Ok(list) = mouse.downcast::<PyList>() {
                for i in 0..list.len() {
                    if let Ok(item) = list.get_item(i) {
                        if let Ok(m_dict) = item.downcast::<PyDict>() {
                            let x_res = m_dict.get_item("x").ok().flatten().and_then(|v| v.extract::<f64>().ok());
                            let y_res = m_dict.get_item("y").ok().flatten().and_then(|v| v.extract::<f64>().ok());
                            let t_res = m_dict.get_item("t").ok().flatten().and_then(|v| v.extract::<f64>().ok());

                            if let (Some(x), Some(y), Some(t)) = (x_res, y_res, t_res) {
                                if !x.is_nan() && !x.is_infinite() && !y.is_nan() && !y.is_infinite() && !t.is_nan() && !t.is_infinite() {
                                    raw.mouse_movements.push(MousePoint { x, y, t });
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    raw
}

#[pyfunction]
fn is_rust_core_active() -> bool {
    true
}

#[pyfunction]
fn get_core_version() -> &'static str {
    "0.8.0-native-rust"
}

#[pyfunction]
fn extract_features_rs<'py>(py: Python<'py>, telemetry: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let raw = parse_python_telemetry(telemetry);
    let feat = compute_kinematics(&raw);
    features_to_pydict(py, &feat)
}

#[pyfunction]
fn consume_nonce_rs(nonce: &str) -> bool {
    consume_nonce_global(nonce)
}

#[pyfunction]
fn is_ip_banned_rs(ip: &str) -> bool {
    is_ip_banned_global(ip)
}

#[pyfunction]
fn ban_ip_rs(ip: &str, duration_sec: u64) {
    ban_ip_global(ip, duration_sec);
}

#[pyfunction]
fn unban_ip_rs(ip: &str) {
    unban_ip_global(ip);
}

#[pyfunction]
fn hydrate_bans_rs(bans: Vec<(String, u64)>) {
    hydrate_bans_global(bans);
}

#[pyfunction]
fn clear_state_engine_rs() {
    clear_all_global();
}

#[pyfunction]
fn get_state_engine_stats_rs<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
    let (curr, prev, bans) = get_stats_global();
    let dict = PyDict::new_bound(py);
    dict.set_item("current_bucket_nonces", curr)?;
    dict.set_item("previous_bucket_nonces", prev)?;
    dict.set_item("active_ip_bans", bans)?;
    Ok(dict)
}

#[pymodule]
fn synapse_core_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(is_rust_core_active, m)?)?;
    m.add_function(wrap_pyfunction!(get_core_version, m)?)?;
    m.add_function(wrap_pyfunction!(extract_features_rs, m)?)?;
    m.add_function(wrap_pyfunction!(consume_nonce_rs, m)?)?;
    m.add_function(wrap_pyfunction!(is_ip_banned_rs, m)?)?;
    m.add_function(wrap_pyfunction!(ban_ip_rs, m)?)?;
    m.add_function(wrap_pyfunction!(unban_ip_rs, m)?)?;
    m.add_function(wrap_pyfunction!(hydrate_bans_rs, m)?)?;
    m.add_function(wrap_pyfunction!(clear_state_engine_rs, m)?)?;
    m.add_function(wrap_pyfunction!(get_state_engine_stats_rs, m)?)?;
    Ok(())
}
