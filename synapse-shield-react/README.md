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

## Features (v0.7.7)

- **Hardened Security Architecture:** Full alignment with Synapse Shield v0.7.7 core security patches (P0-P2).
- **Transparent Token Expiration Refresh:** Seamlessly renegotiates expired tokens (`HTTP 400 EXPIRED`) without triggering IP quarantine or streak bans.
- **Distributed State & Redis Support:** Seamless integration with Synapse Shield's distributed multi-server cluster mode.
- **Transient Iframe Prototype Unhooking:** Detects stealth tools tampering with native APIs.
- **Zero-Jank Touch Events:** Passive listeners (`touchstart`, `touchmove`, `touchend`) for mobile touch kinematics.
- **Safe Unicode Base64:** Robust UTF-8 payload encoding across internationalized environments.
- **Dynamic Yielding PoW Solver:** Seamless client-side cryptographic challenges.
- **Docker Ready Backend:** See the main repository `README.md` for zero-configuration `docker-compose` engine deployment instructions.

## License

MIT © Mustafa Güngör
