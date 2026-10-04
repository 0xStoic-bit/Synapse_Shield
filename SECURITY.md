# Security Policy

## Supported Versions

Synapse Shield is currently in active production development. We strongly recommend always deploying the latest release to ensure you have the latest behavioral biometrics models, anomaly detection heuristics, cryptographic safeguards, and DoS mitigations.

| Version | Supported          | Status |
| ------- | ------------------ | ------ |
| 0.9.x   | :white_check_mark: | **Current Stable** (Active Hardening & SIMD Rust Core) |
| 0.8.x   | :warning:          | Maintenance Only (Critical Security Patches) |
| < 0.8.0 | :x:                | End of Life (Unsupported) |

## Reporting a Vulnerability

If you discover any security-related vulnerabilities (such as cryptographic flaws in HMAC/token evaluation, bypasses for the 1D-CNN or Rust SIMD differential curvature engine, memory/resource exhaustion vectors, or rate-anomaly bypasses), please do NOT report them via public GitHub issues.

Instead, please submit a responsible disclosure report privately via:
- **GitHub Security Advisory (Recommended):** Submit privately via [Security Advisories](https://github.com/0xStoic-bit/Synapse_Shield/security/advisories)

We adhere to the following coordinated disclosure protocol:
1. We will acknowledge receipt of your report as soon as feasible (typically within **3–5 business days**).
2. We will investigate the issue, reproduce the vector, and assess its severity (CVSS).
3. If confirmed, we will develop a mitigation, provide a target release timeline, and offer you early access to validate the patch.
4. For confirmed vulnerabilities with a working Proof-of-Concept (PoC), a CVE identifier may be requested, and you will be prominently credited in our release notes (unless you prefer to remain anonymous).

> **Notice:** Synapse Shield is a community-driven open-source project and does **not** offer a monetary bug bounty program. Automated scanner outputs (e.g., header lints, TLS informational notes) without a functional, demonstrated exploit vector will be closed as invalid.

### Scope & Priority Threat Vectors
The following areas are of critical interest during security audits:
- **Cryptographic Protocols:** HMAC-SHA256 signature forgery, nonce consumption order, and replay attack vectors.
- **Biometric & Kinematic Bypasses:** Novel adversarial curve synthesis evading differential curvature ($\kappa(t)$) or keystroke dynamics.
- **Algorithmic Complexity & DoS:** Resource exhaustion vectors in FastAPI, Event Loop blocking, or unbounded mathematical loops.
- **Browser Anti-Tampering & Stealth:** Evasions bypassing WebGL, Canvas, and V8 native prototype integrity checks.
- **Native Memory & FFI Safety:** Buffer boundaries, unaligned access, or memory safety in the Rust PyO3 core (`synapse_core_rs`).

*Note: Minor theoretical issues requiring impossible human reaction speeds (< 100ms full trajectory completion) or unattainable sub-millisecond local network conditions may be evaluated as Accepted Risk.*
