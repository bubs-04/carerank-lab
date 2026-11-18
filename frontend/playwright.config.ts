import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  // These real workflows share accounts; access-management tests revoke sessions.
  workers: 1,
  use: {
    baseURL: process.env.BASE_URL || "http://127.0.0.1:5173",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    launchOptions: {
      args: ["--no-sandbox"],
      ...(process.env.CHROMIUM_PATH
        ? { executablePath: process.env.CHROMIUM_PATH }
        : {}),
    },
  },
  reporter: "list",
});
