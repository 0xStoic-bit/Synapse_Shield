# Browser SDK tests

Vitest + jsdom tests for the three browser SDKs: plain JavaScript (`src/synapse_shield/static/synapse-sdk.js`), React (`synapse-shield-react`) and Vue (`synapse-shield-vue`).

```bash
cd sdk-tests
npm ci
npx vitest run
```

| File | What it checks |
| :--- | :--- |
| `zero_pii_contract.test.js` | The same Zero-PII contract against all three SDKs: no typed character leaves the browser |
| `vanilla_token_lifecycle.test.js` | Single-use tokens, challenge refresh, expired-token recovery |
| `challenge_and_pow.test.js` | Proof-of-work solving and challenge handling |
| `react_pow_retry.test.js`, `vanilla_pow_retry.test.js` | Automatic retry after HTTP 429 `challenge_required`, exactly once |
| `long_session.test.js` | Long sessions: each token carries only the events its challenge window allows |
| `adapters.js`, `helpers.js` | Shared harness |
| `py_contract.py` | Cross-check helper: some tests verify tokens and proof-of-work with the real Python `tokens.py` (skipped when Python is not available) |

The React and Vue type checks run separately: `npx tsc --noEmit -p .` in each package folder.
