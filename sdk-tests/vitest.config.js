import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "..").split(path.sep).join("/");
const nm = (pkg) => path.join(here, "node_modules", pkg);

export default defineConfig({
  resolve: {
    // The React/Vue SDK sources live in sibling packages that may carry their own
    // node_modules copies. Pin every import to this suite's single copy so hooks and
    // reactivity run against one runtime instance (avoids "invalid hook call").
    alias: [
      { find: /^react$/, replacement: nm("react") },
      { find: /^react-dom$/, replacement: nm("react-dom") },
      { find: /^react-dom\/client$/, replacement: nm("react-dom/client.js") },
      { find: /^vue$/, replacement: nm("vue/dist/vue.runtime.esm-bundler.js") },
    ],
  },
  define: {
    __VUE_OPTIONS_API__: "true",
    __VUE_PROD_DEVTOOLS__: "false",
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: "false",
  },
  server: {
    fs: { allow: [path.resolve(here, "..")] },
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{js,ts}"],
    restoreMocks: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary"],
      reportsDirectory: "coverage",
      allowExternal: true,
      // Sources live outside this package, so match them by absolute path.
      include: [
        `${repo}/src/synapse_shield/static/synapse-sdk.js`,
        `${repo}/synapse-shield-react/src/useSynapseShield.ts`,
        `${repo}/synapse-shield-vue/src/useSynapseShield.ts`,
      ],
    },
  },
});
