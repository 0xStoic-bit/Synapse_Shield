# Synapse Shield Vue 3 & Nuxt 3 SDK

Official Vue 3 and Nuxt 3 integration for **Synapse Shield** behavioral biometrics, bot mitigation, and anti-stealth engine.

## Installation

```bash
npm install synapse-shield-vue
# or
pnpm add synapse-shield-vue
# or
yarn add synapse-shield-vue
```

## Quick Start (Vue 3 / Vite)

### Using the Composable (`useSynapseShield`)

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { useSynapseShield } from 'synapse-shield-vue';

const { getProtectedPayload, isReady } = useSynapseShield({
  apiEndpoint: '/api',
});

const username = ref('');
const password = ref('');
const message = ref('');

const handleLogin = async () => {
  // Get cryptographically signed token with behavioral biometrics
  const payload = getProtectedPayload();

  const response = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: username.value,
      password: password.value,
      synapse_token: payload.token,
    }),
  });

  const result = await response.json();
  message.value = result.message || 'Done';
};
</script>

<template>
  <form @submit.prevent="handleLogin" class="login-form">
    <h2>Secure Login</h2>
    <input v-model="username" type="text" placeholder="Username" required />
    <input v-model="password" type="password" placeholder="Password" required />
    <button type="submit" :disabled="!isReady">Sign In</button>
    <p v-if="message">{{ message }}</p>
  </form>
</template>
```

### Using the Form Shield Component (`SynapseProtect`)

For traditional or standard HTML form submissions, simply drop `<SynapseProtect />` inside your form:

```vue
<script setup lang="ts">
import { SynapseProtect } from 'synapse-shield-vue';
</script>

<template>
  <form action="/api/submit" method="POST">
    <SynapseProtect />
    <input type="text" name="comment" />
    <button type="submit">Submit</button>
  </form>
</template>
```

### Automatic Proof-of-Work retry (`submitProtected`)

Same API as the React SDK. On HTTP 429 `challenge_required` it fetches a fresh challenge, solves the PoW and retries **once**. A second 429 is returned as is.

```ts
const { submitProtected } = useSynapseShield();

const res = await submitProtected('/api/login', (p) => ({
  username: username.value,
  synapse_token: p.token,
  pow_salt: p.pow_salt,   // set only on the retry
  pow_nonce: p.pow_nonce, // read by the server middleware from the top level of the JSON body
}));
```

The retry waits 1.6-3 s (up to 8 s only when needed to keep the last 3 mouse points). It then sends the most recent telemetry window the server accepts. A long session is scored on its last few seconds. Tokens only carry events their challenge can vouch for, so long SPA sessions are not rejected as stale. Autofill, paste and IME entry are recorded in `input_events` as `{ t, kind }` only (no content, `key_count` unchanged).

---

## Nuxt 3 (SSR Safe)

`synapse-shield-vue` is completely SSR-safe and guards all browser interactions with `onMounted` and `typeof window !== 'undefined'`. No special plugins or SSR flags are required!

```vue
<!-- pages/login.vue in Nuxt 3 -->
<script setup>
import { useSynapseShield } from 'synapse-shield-vue';

const { getProtectedPayload } = useSynapseShield();
// Works automatically on client mount
</script>
```

---

## Features (v0.11.0)

- **Universal Keystroke Zero-PII Shield (v0.10.4):** Automatic client-side masking of all single-character inputs (`rawKey.length === 1 -> "masked"`) and sensitive fields, local digraph frequency computation (`is_freq_digraph`), transmitting zero raw text or PII across the wire (GDPR & KVKK compliant).
- **SPA Token Lifecycle & Coalescing Mutex (v0.10.3):** Single-use challenge token lifecycle invalidation to eliminate 403 Replay Attack loops in Vue 3 and Nuxt applications.
- **PoW Telemetry Retention (v0.10.3):** Shifts historical telemetry timestamps forward upon PoW challenge retry, eliminating empty telemetry 403 blocks for genuine users.
- **Mobile SDK v2.0 & Handheld Biometrics (v0.10.0):** Tap hold duration tracking (`tap_duration_ms`), passive 3-axis gyroscope motion variance, and WebGL emulator detection.
- **Hardened Security Architecture:** Full alignment with Synapse Shield production hardening (Algorithmic DoS mitigation, Rust SIMD differential curvature $\kappa(t)$, zero-copy buffers, and keystroke entropy analysis).
- **Transparent Token Expiration Refresh:** Seamlessly renegotiates expired tokens (`HTTP 400 EXPIRED`) without triggering IP quarantine or streak bans.
- **Distributed State & Redis Support:** Full compatibility with Synapse Shield multi-worker cluster deployments.
- **Transient Iframe Prototype Unhooking:** Detects stealth tools tampering with `Function.prototype.toString`.
- **Zero-Jank Touch Events:** Passive listeners (`touchstart`, `touchmove`, `touchend`) for high-precision mobile biometrics with zero scroll jank.
- **Dynamic Yielding PoW Solver:** `solvePow(powSalt, difficulty)` takes the signed `pow_salt` from the server's `challenge_required` response (sha256(salt + nonce), bounded at 20M attempts) and yields to the UI thread every 1,000 iterations to avoid freezing browser rendering. `getProtectedPayload()` consumes the single-use challenge and fetches the next one in the background.
- **Safe Unicode Base64:** Robust UTF-8 payload encoding across internationalized environments.
- **Docker Ready Backend:** See the main repository `README.md` for zero-configuration `docker-compose` engine deployment instructions.

## License

MIT © Mustafa Güngör
