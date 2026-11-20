# Integrations

How to put Synapse Shield in front of your routes, and how to send the token from the browser.
Back to the [documentation index](README.md).

- [How a protected request works](#how-a-protected-request-works)
- [Backend frameworks](#backend-frameworks): FastAPI, Django, Flask, Litestar, Sanic, ASGI
- [Frontend SDKs](#frontend-sdks): React / Next.js, Vue 3 / Nuxt 3, plain JavaScript
- [Proof-of-work challenges](#proof-of-work-challenges)
- [Calling `POST /api/score` yourself](#calling-post-apiscore-yourself)
- [Subresource Integrity (payment pages)](#subresource-integrity-payment-pages)

## How a protected request works

1. The browser SDK fetches a single-use, signed challenge (`GET /api/challenge`).
2. While the visitor uses the page, the SDK records movement, taps and key *timing* (never typed text).
3. On submit, the SDK sends a token (the challenge + the telemetry) in the `X-Synapse-Token` header or in the JSON body (`synapse_token`).
4. The middleware verifies the token and scores the session: **allow**, **challenge** (HTTP 429, background proof-of-work) or **block** (HTTP 403).

### `protected_paths` (all adapters)

The middleware checks only state-changing requests (`POST`, `PUT`, `PATCH`, `DELETE`; a body-less `DELETE` sends its token in the `X-Synapse-Token` header) whose path starts with one of the listed prefixes. **If the list is empty or missing, every `POST`/`PUT`/`PATCH` route is protected.** This fail-safe default is the same in FastAPI, raw ASGI, Django, Flask, Sanic and Litestar. Up to v0.10.4, Flask, FastAPI and Django protected *nothing* when the list was empty, so list your paths explicitly if you relied on that.

## Backend frameworks

Install the adapters with `pip install "synapse-shield[frameworks]"` (FastAPI comes with `[server]`).

### FastAPI

Global middleware, or a decorator per route:

```python
from fastapi import FastAPI, Request
from synapse_shield import shield_protect, SynapseShieldMiddleware

app = FastAPI()
app.add_middleware(SynapseShieldMiddleware, protected_paths=["/api/auth"])

@app.post("/api/login")
@shield_protect(max_risk_score=50.0, accessibility_mode=False)
async def login(request: Request):
    return {"status": "authenticated"}
```

### Django

`settings.py`:

```python
MIDDLEWARE = [
    # ...
    "synapse_shield.django.SynapseShieldMiddleware",
]
SYNAPSE_SHIELD_PROTECTED_PATHS = ["/api/login"]
SYNAPSE_SHIELD_MAX_RISK = 50.0
SYNAPSE_SHIELD_ACCESSIBILITY = False
# SYNAPSE_SHIELD_ENABLE_POW = False  # gray-area proof-of-work challenge
```

### Flask

```python
from flask import Flask
from synapse_shield.flask import shield_protect_flask

app = Flask(__name__)

@app.route("/login", methods=["POST"])
@shield_protect_flask(max_risk_score=50.0)
def login():
    return {"status": "authenticated"}
```

### Litestar

Route guards or application-wide middleware:

```python
from litestar import Litestar, post
from synapse_shield.litestar import synapse_guard, LitestarSynapseMiddleware

@post("/api/checkout", guards=[synapse_guard(max_risk_score=40.0)])
async def checkout(data: dict) -> dict:
    return {"status": "success"}

app = Litestar(
    route_handlers=[checkout],
    middleware=[LitestarSynapseMiddleware(protected_paths=["/api/auth"], max_risk_score=50.0)],
)
```

### Sanic

Native HTTP server and ASGI mode:

```python
from sanic import Sanic, text
from synapse_shield.sanic import shield_protect_sanic, SynapseSanicMiddleware

app = Sanic("secure_app")

@app.post("/api/login")
@shield_protect_sanic(max_risk_score=50.0)
async def login(request):
    return text("Authenticated!")

# or request middleware
middleware = SynapseSanicMiddleware(protected_paths=["/api/auth"])
app.register_middleware(middleware, "request")
```

### Any ASGI 3.0 app

Zero-dependency wrapper with replay-safe body reading and a 256 KB body limit. Works with Quart, BlackSheep, Falcon or raw ASGI:

```python
from synapse_shield import SynapseShieldASGIMiddleware

app = SynapseShieldASGIMiddleware(
    base_app,
    protected_paths=["/api/auth", "/checkout"],
    max_risk_score=50.0,
)
```

### Using the evaluator directly

Every adapter calls the same function, which you can call from any code path:

```python
from synapse_shield import evaluate_synapse_request_sync  # or the async evaluate_synapse_request

decision = evaluate_synapse_request_sync(client_ip=ip, user_agent=ua, token=token)
if decision.action == "allow":
    ...
elif decision.action == "challenge":     # HTTP 429, see below
    return decision.to_dict(), 429
else:                                    # "block"
    return decision.to_dict(), 403
```

## Frontend SDKs

| SDK | Package | Automatic proof-of-work retry |
| :--- | :--- | :--- |
| React / Next.js | [`synapse-shield-react`](../synapse-shield-react/README.md) | Yes, `submitProtected()` |
| Vue 3 / Nuxt 3 | [`synapse-shield-vue`](../synapse-shield-vue/README.md) | Yes, `submitProtected()` |
| Plain JavaScript | `synapse_shield/static/synapse-sdk.js` | Only `submit()` to `/api/score`; `protectFetch` / `protectAxios` do **not** solve it |

All three run the same Zero-PII contract: only standard named keys (`Enter`, `Backspace`, arrow keys, …) are sent by name, every other key is sent as `"masked"`, sensitive fields are fully masked, and autofill / paste / IME input is recorded only as `input_events: [{t, kind}]` with no content.

### React / Next.js

```tsx
import { useSynapseShield } from "synapse-shield-react";

export function LoginForm() {
  const { submitProtected } = useSynapseShield();

  async function onSubmit(e) {
    e.preventDefault();
    const res = await submitProtected("/api/login", (p) => ({
      username, password,
      synapse_token: p.token,
      pow_salt: p.pow_salt,   // set only on the proof-of-work retry
      pow_nonce: p.pow_nonce,
    }));
  }
  // ...
}
```

`<SynapseProtect />` is a drop-in component for forms; see the [package README](../synapse-shield-react/README.md).

### Vue 3 / Nuxt 3

SSR-safe for Nuxt 3. Same `submitProtected(url, buildBody)` API as React:

```vue
<script setup>
import { ref } from "vue";
import { useSynapseShield } from "synapse-shield-vue";

const { submitProtected } = useSynapseShield();
const username = ref(""), password = ref("");

async function onSubmit() {
  const res = await submitProtected("/api/login", (p) => ({
    username: username.value, password: password.value,
    synapse_token: p.token, pow_salt: p.pow_salt, pow_nonce: p.pow_nonce,
  }));
}
</script>
```

See the [package README](../synapse-shield-vue/README.md) for `<SynapseProtect />`.

### Plain JavaScript

The built-in server serves the SDK at `/static/synapse-sdk.js`. In your own app, serve `synapse_shield/static/synapse-sdk.js` from the installed package.

```html
<script src="/static/synapse-sdk.js"></script>
<script>
  SynapseShield.init();
  SynapseShield.protectFetch(["/api/login", /\/api\/checkout/]); // adds X-Synapse-Token
  // SynapseShield.protectAxios(axios, "/api/login");             // same for Axios
  // const token = await SynapseShield.getToken();                // or attach it yourself
</script>
```

## Proof-of-work challenges

When a session is unsure, the server answers **HTTP 429** with `status: "challenge_required"`, a signed `pow_salt` and a `pow_difficulty`. The client finds a nonce such that `sha256(pow_salt + nonce)` starts with `pow_difficulty` zero hex digits, then repeats the request with a fresh token plus `pow_salt` and `pow_nonce` (top level of the JSON body, or `X-Synapse-PoW-Salt` / `X-Synapse-PoW-Nonce` headers).

Who gets a challenge:

- **Gray area (risk 35-55)** when proof-of-work is enabled: always in the built-in server; in the adapters only with `SYNAPSE_ENABLE_POW=1` (or `enable_pow=True`).
- **Keyboard-only sessions** (no mouse movement, at least 3 keystrokes) and **short pointer traces** (<40 samples) that would otherwise be allowed: always, even with proof-of-work off. Turn off with `SYNAPSE_KEYBOARD_ONLY_CHALLENGE=0` / `SYNAPSE_SHORT_TRACE_CHALLENGE=0`.

Proof-of-work does not tell humans from bots; it makes automation cost more. A client that cannot solve it (no SDK, or an insecure `http://` page without Web Crypto) is refused. See [Configuration](CONFIGURATION.md) for difficulty and scoring details.

## Calling `POST /api/score` yourself

Branch on `decision` (`"allow"` / `"block"` / `"challenge"` / `"error"`), not on `status`. `status: "success"` only means the request was scored, and is returned for bots too.

## Subresource Integrity (payment pages)

Serving the SDK on a payment page (PCI DSS 6.4.3)? Pin it with Subresource Integrity and regenerate the hash for every SDK release:

```bash
python scripts/sri_hash.py            # prints the <script ... integrity="sha384-..."> tag
python scripts/sri_hash.py --check sha384-...   # for CI
```

```html
<script src="/static/synapse-sdk.js" integrity="sha384-..." crossorigin="anonymous"></script>
```
