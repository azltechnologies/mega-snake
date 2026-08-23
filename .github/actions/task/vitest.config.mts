/**
 * Vitest configuration for the `task` action.
 *
 * Coverage thresholds mirror the repository's testing rules: the pure domain
 * layer has no excuse for uncovered branches, so the bar is set globally and
 * the suite fails below it rather than merely reporting.
 */

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/tests/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      reportsDirectory: "coverage",
      include: ["src/**/*.ts"],
      exclude: ["src/tests/**", "src/models/**"],
      thresholds: {
        lines: 95,
        branches: 95,
        functions: 95,
        statements: 95,
      },
    },
  },
});
