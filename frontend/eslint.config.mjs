// Flat config (ESLint v9). Next.js 16 removed `next lint`, so we run ESLint
// directly: `eslint . --max-warnings=0`.
//
// `eslint-config-next/core-web-vitals` and `.../typescript` ship as flat
// config arrays (CJS `module.exports = [...]`), so we can spread them as-is.

import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    ignores: [
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
      "public/**",
      "node_modules/**",
      "e2e/**",
    ],
  },
];

export default config;
