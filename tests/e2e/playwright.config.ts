import { defineConfig, devices } from "@playwright/test";

/**
 * Runs against an already-running full stack (postgres/redis/api/voice-worker/
 * workers/web — `make dev` or the `dev-native` targets), not a Playwright-
 * managed webServer: the product needs more than the Next.js process alone,
 * and orchestrating the whole stack from here would just reimplement the
 * Makefile. See docs/IMPLEMENTATION_CHECKLIST.md Phase 10.
 */
export default defineConfig({
  testDir: "./specs",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
