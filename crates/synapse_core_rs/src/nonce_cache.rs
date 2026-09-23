use std::collections::{HashMap, HashSet};
use std::sync::RwLock;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

/// Two-Bucket (Çift Kova) In-Memory Nonce Cache & L1 IP Ban Engine
/// Provides sub-microsecond O(1) Replay Attack protection and zero-disk IP ban checking.
pub struct StateEngine {
    // Nonce Buckets
    current_bucket: HashSet<String>,
    previous_bucket: HashSet<String>,
    last_rotation: Instant,
    window_duration: Duration,

    // L1 In-Memory IP Ban Cache (IP -> expires_at_epoch_sec)
    ip_bans: HashMap<String, u64>,
}

impl StateEngine {
    pub fn new(window_secs: u64) -> Self {
        Self::with_duration(Duration::from_secs(window_secs))
    }

    pub fn with_duration(duration: Duration) -> Self {
        Self {
            current_bucket: HashSet::with_capacity(8192),
            previous_bucket: HashSet::with_capacity(8192),
            last_rotation: Instant::now(),
            window_duration: duration,
            ip_bans: HashMap::with_capacity(1024),
        }
    }

    /// Rotate buckets if the time window has elapsed.
    /// Drops the old previous bucket in O(1) time without iterating or disk locks.
    fn maybe_rotate(&mut self) {
        if self.last_rotation.elapsed() >= self.window_duration {
            self.previous_bucket = std::mem::replace(
                &mut self.current_bucket,
                HashSet::with_capacity(8192),
            );
            self.last_rotation = Instant::now();
        }
    }

    /// Records a nonce.
    /// Returns true if this is the first time the nonce is seen (VALID).
    /// Returns false if already consumed in current or previous bucket (REPLAY ATTACK).
    pub fn consume_nonce(&mut self, nonce: &str) -> bool {
        self.maybe_rotate();

        // 1. Check if present in either bucket
        if self.current_bucket.contains(nonce) || self.previous_bucket.contains(nonce) {
            return false;
        }

        // 2. Insert into current bucket
        self.current_bucket.insert(nonce.to_string());
        true
    }

    /// Checks if an IP is currently banned in the L1 In-Memory Cache.
    pub fn is_ip_banned(&self, ip: &str, now_epoch: u64) -> bool {
        if let Some(&expires_at) = self.ip_bans.get(ip) {
            if now_epoch < expires_at {
                return true;
            }
        }
        false
    }

    /// Bans an IP in the L1 In-Memory Cache until expires_at_epoch.
    pub fn ban_ip(&mut self, ip: &str, expires_at_epoch: u64) {
        self.ip_bans.insert(ip.to_string(), expires_at_epoch);
    }

    /// Removes an IP from the L1 In-Memory Cache.
    pub fn unban_ip(&mut self, ip: &str) {
        self.ip_bans.remove(ip);
    }

    /// Hydrates the L1 cache from SQLite on cold-start/restart.
    pub fn hydrate_bans(&mut self, bans: Vec<(String, u64)>) {
        let now_epoch = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        for (ip, expires_at) in bans {
            if expires_at > now_epoch {
                self.ip_bans.insert(ip, expires_at);
            }
        }
    }

    /// Clears both buckets and all IP bans (used for tests or admin reset).
    pub fn clear_all(&mut self) {
        self.current_bucket.clear();
        self.previous_bucket.clear();
        self.ip_bans.clear();
        self.last_rotation = Instant::now();
    }

    /// Returns statistics for telemetry/benchmarks: (current_nonces, previous_nonces, active_bans)
    pub fn get_stats(&self) -> (usize, usize, usize) {
        let now_epoch = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        let active_bans = self
            .ip_bans
            .values()
            .filter(|&&exp| exp > now_epoch)
            .count();

        (
            self.current_bucket.len(),
            self.previous_bucket.len(),
            active_bans,
        )
    }
}

// Global thread-safe singleton
static GLOBAL_ENGINE: RwLock<Option<StateEngine>> = RwLock::new(None);

fn with_engine_write<F, R>(f: F) -> R
where
    F: FnOnce(&mut StateEngine) -> R,
{
    let mut lock = GLOBAL_ENGINE.write().expect("RwLock write poisoned");
    if lock.is_none() {
        *lock = Some(StateEngine::new(60)); // 60-second default rotation
    }
    f(lock.as_mut().unwrap())
}

fn with_engine_read<F, R>(f: F) -> R
where
    F: FnOnce(&StateEngine) -> R,
{
    // Fast path: try read lock
    {
        let lock = GLOBAL_ENGINE.read().expect("RwLock read poisoned");
        if let Some(ref engine) = *lock {
            return f(engine);
        }
    }
    // Cold path: initialize
    with_engine_write(|engine| f(engine))
}

// Exported high-level functions for PyO3
pub fn consume_nonce_global(nonce: &str) -> bool {
    with_engine_write(|engine| engine.consume_nonce(nonce))
}

pub fn is_ip_banned_global(ip: &str) -> bool {
    let now_epoch = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    with_engine_read(|engine| engine.is_ip_banned(ip, now_epoch))
}

pub fn ban_ip_global(ip: &str, duration_sec: u64) {
    let expires_at = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
        + duration_sec;
    with_engine_write(|engine| engine.ban_ip(ip, expires_at));
}

pub fn unban_ip_global(ip: &str) {
    with_engine_write(|engine| engine.unban_ip(ip));
}

pub fn hydrate_bans_global(bans: Vec<(String, u64)>) {
    with_engine_write(|engine| engine.hydrate_bans(bans));
}

pub fn clear_all_global() {
    with_engine_write(|engine| engine.clear_all());
}

pub fn get_stats_global() -> (usize, usize, usize) {
    with_engine_read(|engine| engine.get_stats())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_two_bucket_deduplication() {
        let mut engine = StateEngine::new(60);
        let n1 = "4f8a1234567890abcdef1234567890ab";
        let n2 = "5e9b1234567890abcdef1234567890cd";

        // First consume succeeds
        assert!(engine.consume_nonce(n1));
        assert!(engine.consume_nonce(n2));

        // Replay fails
        assert!(!engine.consume_nonce(n1));
        assert!(!engine.consume_nonce(n2));
    }

    #[test]
    fn test_bucket_rotation() {
        let mut engine = StateEngine::with_duration(Duration::from_millis(40));
        let n1 = "token_period_1";
        assert!(engine.consume_nonce(n1));
        assert!(!engine.consume_nonce(n1)); // Immediate replay fails

        // Sleep 50ms: triggers 1st rotation. n1 moves to previous_bucket
        std::thread::sleep(Duration::from_millis(50));
        let n2 = "token_period_2";
        assert!(engine.consume_nonce(n2)); // n2 in current_bucket

        // n1 is still in previous_bucket, so replay still fails!
        assert!(!engine.consume_nonce(n1));

        // Sleep 50ms: triggers 2nd rotation. n2 moves to previous_bucket, n1 is evicted!
        std::thread::sleep(Duration::from_millis(50));
        let n3 = "token_period_3";
        assert!(engine.consume_nonce(n3));

        // n2 is in previous_bucket, so replay fails
        assert!(!engine.consume_nonce(n2));
        // n1 was completely evicted after 2 full rotations, so it is treated as fresh
        assert!(engine.consume_nonce(n1));
    }

    #[test]
    fn test_l1_ip_ban() {
        let mut engine = StateEngine::new(60);
        let ip = "192.168.1.100";

        assert!(!engine.is_ip_banned(ip, 1000));

        // Ban until 2000
        engine.ban_ip(ip, 2000);
        assert!(engine.is_ip_banned(ip, 1000));
        assert!(engine.is_ip_banned(ip, 1999));
        assert!(!engine.is_ip_banned(ip, 2000)); // Expired

        // Unban
        engine.unban_ip(ip);
        assert!(!engine.is_ip_banned(ip, 1500));
    }
}
