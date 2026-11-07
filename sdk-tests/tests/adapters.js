// Uniform drivers for the three SDK flavours so one contract suite can run against all of them.
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { createApp, defineComponent, nextTick } from "vue";
import { decodeToken, mockChallengeFetch } from "./helpers.js";

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

/**
 * Every adapter exposes:
 *   start()       -> mounts/initialises the SDK and waits until key listeners are attached
 *   envelope()    -> decoded `{ challenge, telemetry, created_at }` from the SDK's token
 *   keystrokes()  -> raw in-memory keystroke buffer (what would be sent)
 *   reset()       -> clears telemetry
 *   stop()        -> unmounts / detaches
 */
export const adapters = {
  vanilla: {
    name: "Vanilla JS (synapse-sdk.js)",
    async create() {
      mockChallengeFetch();
      // The IIFE installs a non-configurable window.SynapseShield once per test file (jsdom is
      // isolated per file), so later calls reuse the same instance and just reset its state.
      if (!window.SynapseShield) {
        await import("../../src/synapse_shield/static/synapse-sdk.js");
      }
      const sdk = window.SynapseShield;
      return {
        sdk,
        async start() {
          await sdk.init();
          if (!sdk.currentChallenge) await sdk.refreshChallenge();
          sdk.reset();
        },
        envelope() {
          return decodeToken(sdk.getPayload().token);
        },
        keystrokes: () => sdk.keystrokes,
        reset: () => sdk.reset(),
        async stop() {
          sdk.reset();
        },
      };
    },
  },

  react: {
    name: "React (useSynapseShield.ts)",
    async create() {
      mockChallengeFetch();
      globalThis.IS_REACT_ACT_ENVIRONMENT = true;
      const { useSynapseShield } = await import("../../synapse-shield-react/src/useSynapseShield.ts");
      let api = null;
      const Harness = () => {
        api = useSynapseShield();
        return null;
      };
      const container = document.createElement("div");
      document.body.appendChild(container);
      const root = createRoot(container);
      return {
        async start() {
          await act(async () => {
            root.render(createElement(Harness));
          });
          await act(async () => {
            await flush();
          });
        },
        envelope() {
          const payload = api.getProtectedPayload();
          if (!payload.token) throw new Error("React SDK returned no token (challenge missing)");
          return decodeToken(payload.token);
        },
        keystrokes() {
          const payload = api.getProtectedPayload();
          return payload.token ? decodeToken(payload.token).telemetry.keystrokes : payload.telemetry.keystrokes;
        },
        reset: () => api.reset(),
        payload: () => api.getProtectedPayload(),
        api: () => api,
        async stop() {
          await act(async () => root.unmount());
          container.remove();
        },
      };
    },
  },

  vue: {
    name: "Vue 3 (useSynapseShield.ts)",
    async create() {
      mockChallengeFetch();
      const { useSynapseShield } = await import("../../synapse-shield-vue/src/useSynapseShield.ts");
      let api = null;
      const Harness = defineComponent({
        setup() {
          api = useSynapseShield();
          return () => null;
        },
      });
      const container = document.createElement("div");
      document.body.appendChild(container);
      const app = createApp(Harness);
      return {
        async start() {
          app.mount(container);
          // onMounted awaits the challenge fetch before attaching listeners.
          for (let i = 0; i < 5 && !api.isReady.value; i++) {
            await flush();
            await nextTick();
          }
          if (!api.isReady.value) throw new Error("Vue SDK never became ready");
        },
        envelope() {
          const payload = api.getProtectedPayload();
          if (!payload.token) throw new Error("Vue SDK returned no token (challenge missing)");
          return decodeToken(payload.token);
        },
        keystrokes: () => api.telemetry.value.keystrokes,
        reset: () => api.reset(),
        payload: () => api.getProtectedPayload(),
        api: () => api,
        async stop() {
          app.unmount();
          container.remove();
        },
      };
    },
  },
};
