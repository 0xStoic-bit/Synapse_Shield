# Security Policy

## Supported Versions

Synapse Shield is currently in active development. We recommend always using the latest minor version to ensure you have the latest behavioral biometrics models, anomaly detection heuristics, and security patches.

| Version | Supported          |
| ------- | ------------------ |
| 0.7.x   | :white_check_mark: |
| < 0.7.1 | :x:                |

## Reporting a Vulnerability

If you discover any security-related issues (such as bypasses for the 1D-CNN engine, cryptographic vulnerabilities in the token handling, or memory/resource leak vectors), please do NOT report them via public GitHub issues.

Instead, please email the maintainer directly at: **mustafagungor181881@gmail.com**

We take security seriously and will adhere to the following protocol:
1. You will receive an acknowledgment of your report within 48 hours.
2. We will investigate the issue and determine the validity and impact.
3. If confirmed, we will provide an estimated timeline for a patch.
4. A CVE may be requested, and you will be credited for the discovery in our release notes (unless you prefer to remain anonymous).

### Scope
The following types of reports are highly appreciated:
- Cryptographic bypasses (e.g., HMAC forgery, Replay Attack vectors)
- Browser Tampering Evasion (new stealth frameworks bypassing WebGL/Canvas hooks)
- Time-travel or timestamp manipulation vectors
- Denial of Service (DoS) vectors in the Fast API server

*Note: Minor theoretical issues requiring impossible human speeds or unattainable local network latencies may be classified as "Accepted Risk" rather than critical vulnerabilities.*
