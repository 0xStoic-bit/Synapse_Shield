# Synapse Shield React & Next.js SDK

Official React and Next.js integration for **Synapse Shield** behavioral biometrics, bot mitigation, and anti-stealth engine.

## Installation

```bash
npm install synapse-shield-react
# or
pnpm add synapse-shield-react
# or
yarn add synapse-shield-react
```

## Quick Start (React / Next.js)

### Using the Hook (`useSynapseShield`)

```tsx
import React, { useState } from 'react';
import { useSynapseShield } from 'synapse-shield-react';

export function LoginForm() {
  const { getProtectedPayload } = useSynapseShield();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload = getProtectedPayload();

    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username,
        password,
        synapse_token: payload.token,
      }),
    });

    const data = await res.json();
    console.log(data);
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2>Secure Login</h2>
      <input
        type="text"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        placeholder="Username"
        required
      />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
        required
      />
      <button type="submit">Sign In</button>
    </form>
  );
}
```

### Using the Form Shield Component (`SynapseProtect`)

For traditional HTML form submissions:

```tsx
import React from 'react';
import { SynapseProtect } from 'synapse-shield-react';

export function CommentForm() {
  return (
    <form action="/api/comment" method="POST">
      <SynapseProtect />
      <textarea name="comment" placeholder="Write a comment..." />
      <button type="submit">Submit</button>
    </form>
  );
}
```

### Automatic Proof-of-Work retry (`submitProtected`)

Gray-area sessions (and keyboard-only sessions) can receive HTTP 429 `challenge_required` with a signed `pow_salt`. `submitProtected` handles it for you: it fetches a fresh challenge, solves the PoW with Web Crypto (yielding to the event loop between batches), and retries **once**. A second 429 is returned to your code as is; there is no retry loop.

```tsx
const { submitProtected } = useSynapseShield();

const res = await submitProtected('/api/login', (p) => ({
  username,
  password,
  synapse_token: p.token,
  pow_salt: p.pow_salt,   // set only on the retry
  pow_nonce: p.pow_nonce, // the server middleware reads both from the top level of the JSON body
}));
```

The retry waits 1.6-3 s for the fresh token to age (up to 8 s only when needed to keep the last 3 mouse points). It then sends the most recent telemetry window the server accepts (span <= token age + 0.5 s), shifted into the token's window. It never waits 30+ s, but a long session is scored on its last few seconds. Every token only carries the events its challenge can vouch for: events older than the challenge window, for example from a long SPA session, are left out instead of making the server reject the token. Non-keyboard text entry (autofill, paste, IME) goes to a separate `input_events` list as `{ t, kind }` only; content is never read, and `key_count` is unchanged. If Web Crypto is unavailable (insecure `http://` context) the original 429 is returned. `solvePow(salt, difficulty)` and `isSolvingPow` are also exposed by the hook, and `solvePow` is a standalone export.

---

## Next.js (App & Pages Router)

`synapse-shield-react` is completely SSR-safe. In the Next.js App Router (`app/`), simply mark components using the hook with `'use client'`:

```tsx
'use client';

import { useSynapseShield } from 'synapse-shield-react';

export default function Page() {
  const { getProtectedPayload } = useSynapseShield();
  // Safe client-side biometrics
  return <div>Protected Page</div>;
}
```

---

## Features (v0.11.0)

- **Automatic PoW Challenge Solving (v0.10.8):** `submitProtected()` solves a gray-area `challenge_required` (HTTP 429) Proof-of-Work and retries exactly once; `solvePow()` is exported for custom flows.
- **Universal Keystroke Zero-PII Shield (v0.10.4):** Automatic client-side masking of all single-character inputs (`rawKey.length === 1 -> "masked"`) and sensitive fields, local digraph frequency computation (`is_freq_digraph`), transmitting zero raw text or PII across the wire (GDPR & KVKK compliant).
- **SPA Token Lifecycle & Coalescing Mutex (v0.10.3):** Single-use challenge token lifecycle invalidation to eliminate 403 Replay Attack loops in Next.js and React applications.
- **PoW Telemetry Retention (v0.10.3):** Shifts historical telemetry timestamps forward upon PoW challenge retry, eliminating empty telemetry 403 blocks for genuine users.
- **Mobile SDK v2.0 & Handheld Biometrics (v0.10.0):** Tap hold duration tracking (`tap_duration_ms`), passive 3-axis gyroscope motion variance, and WebGL emulator detection.
- **Hardened Security Architecture:** Full alignment with Synapse Shield production hardening (Algorithmic DoS mitigation, Rust SIMD differential curvature $\kappa(t)$, zero-copy buffers, and keystroke entropy analysis).
- **Transparent Token Expiration Refresh:** Seamlessly renegotiates expired tokens (`HTTP 400 EXPIRED`) without triggering IP quarantine or streak bans.
- **Distributed State & Redis Support:** Seamless integration with Synapse Shield's distributed multi-server cluster mode.
- **Transient Iframe Prototype Unhooking:** Detects stealth tools tampering with native APIs.
- **Zero-Jank Touch Events:** Passive listeners (`touchstart`, `touchmove`, `touchend`) for mobile touch kinematics.
- **Safe Unicode Base64:** Robust UTF-8 payload encoding across internationalized environments.
- **Dynamic Yielding PoW Solver:** Seamless client-side cryptographic challenges.
- **Docker Ready Backend:** See the main repository `README.md` for zero-configuration `docker-compose` engine deployment instructions.

## License

MIT © Mustafa Güngör
