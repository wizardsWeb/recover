import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Agent tooling, not application source. These are CommonJS helper scripts
    // that ship with skill definitions; linting them with the app's TypeScript
    // rules reports `require()` as an error in files that cannot use `import`.
    ".claude/**",
  ]),
]);

export default eslintConfig;
