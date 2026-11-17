import { test as base, expect } from "@playwright/test";

// Existing read workflows exercise the least privileged role against the real API.
export const test = base.extend({
  context: async ({ context, baseURL }, use) => {
    const username = process.env.E2E_VIEWER_USERNAME;
    const password = process.env.E2E_VIEWER_PASSWORD;
    if (!username || !password)
      throw new Error("Provision E2E viewer credentials first");
    const response = await context.request.post("/api/auth/login", {
      headers: { Origin: new URL(baseURL!).origin },
      data: { username, password },
    });
    expect(response.status()).toBe(200);
    await use(context);
  },
  request: async ({ context }, use) => {
    await use(context.request);
  },
});
export { expect } from "@playwright/test";
