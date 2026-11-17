import { test, expect } from "@playwright/test";

test("administrator manages access and sees the security audit", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Username", { exact: true })
    .fill(process.env.E2E_ADMIN_USERNAME!);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.E2E_ADMIN_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("button", { name: "Administration", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Access and accountability" }),
  ).toBeVisible();
  const username = process.env.E2E_VIEWER_USERNAME!;
  const form = page.getByRole("form", {
    name: `Manage ${username}`,
    exact: true,
  });
  await form
    .getByLabel(`Role for ${username}`, { exact: true })
    .selectOption("analyst");
  await form
    .getByRole("button", { name: "Update access", exact: true })
    .click();
  await expect(
    form.getByRole("button", { name: "Update access", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("account updated", { exact: true }).first(),
  ).toBeVisible();
  await form
    .getByLabel(`Role for ${username}`, { exact: true })
    .selectOption("viewer");
  await form
    .getByRole("button", { name: "Update access", exact: true })
    .click();
  await expect(
    form.getByRole("button", { name: "Update access", exact: true }),
  ).toBeDisabled();
  const accounts = await (
    await page.request.get("/api/auth/admin/users")
  ).json();
  expect(
    accounts.find((u: { username: string }) => u.username === username).role,
  ).toBe("viewer");
  await page.screenshot({
    path: "../docs/administration-4.0.png",
    fullPage: true,
  });
});

test("unauthenticated requests and forged identity cannot read protected data", async ({
  page,
  request,
}) => {
  for (const path of [
    "/api/providers",
    "/api/analytics",
    "/api/pipeline",
    "/api/dataops/monitoring/alerts",
    "/api/auth/users",
  ]) {
    expect(
      (
        await request.get(path, {
          headers: { "X-User": "administrator", "X-Role": "administrator" },
        })
      ).status(),
    ).toBe(401);
  }
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Sign in to CareRank" }),
  ).toBeVisible();
  await expect(page.getByText("Provider intelligence, explained.")).toHaveCount(
    0,
  );
  await page.screenshot({ path: "../docs/sign-in-4.0.png", fullPage: true });
});

test("real sign-in, viewer authorization, CSRF and logout revocation", async ({
  page,
  baseURL,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Username", { exact: true })
    .fill(process.env.E2E_VIEWER_USERNAME!);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.E2E_VIEWER_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByText("Provider intelligence, explained."),
  ).toBeVisible();
  const session = await (await page.request.get("/api/auth/me")).json();
  const alerts = await (
    await page.request.get("/api/dataops/monitoring/alerts?mode=fixture")
  ).json();
  const alert = alerts.items[0];
  const data = {
    expected_revision: alert.revision,
    status: "acknowledged",
    note: "Viewer cannot mutate",
  };
  const origin = new URL(baseURL!).origin;
  expect(
    (
      await page.request.post(
        `/api/dataops/monitoring/alerts/${alert.id}/actions`,
        {
          headers: { Origin: origin, "X-CSRF-Token": session.csrf_token },
          data,
        },
      )
    ).status(),
  ).toBe(403);
  expect(
    (
      await page.request.post("/api/auth/logout", {
        headers: { Origin: origin },
      })
    ).status(),
  ).toBe(403);
  await page
    .getByRole("button", { name: "Data operations", exact: true })
    .click();
  await page.getByLabel("Data source mode").selectOption("fixture");
  await page
    .getByRole("button", { name: "Quality monitoring", exact: true })
    .click();
  await page
    .getByRole("button", { name: /Inspect alert/ })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "Save decision", exact: true }),
  ).toHaveCount(0);
  const beforeLogout = await page.context().cookies();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in to CareRank" }),
  ).toBeVisible();
  expect((await page.request.get("/api/providers")).status()).toBe(401);
  await page.context().addCookies(beforeLogout);
  expect((await page.request.get("/api/providers")).status()).toBe(401);
});

test("analyst request security rejects missing CSRF, foreign origins and stale revisions", async ({
  request,
  baseURL,
}) => {
  const origin = new URL(baseURL!).origin;
  const login = await request.post("/api/auth/login", {
    headers: { Origin: origin },
    data: {
      username: process.env.E2E_USERNAME,
      password: process.env.E2E_PASSWORD,
    },
  });
  expect(login.status()).toBe(200);
  const session = await login.json();
  const alert = (
    await (
      await request.get("/api/dataops/monitoring/alerts?mode=fixture")
    ).json()
  ).items[0];
  const url = `/api/dataops/monitoring/alerts/${alert.id}/actions`;
  const data = {
    expected_revision: alert.revision,
    note: "Negative browser security verification",
  };
  expect(
    (await request.post(url, { headers: { Origin: origin }, data })).status(),
  ).toBe(403);
  expect(
    (
      await request.post(url, {
        headers: {
          Origin: "https://attacker.invalid",
          "X-CSRF-Token": session.csrf_token,
        },
        data,
      })
    ).status(),
  ).toBe(403);
  expect(
    (
      await request.post(url, {
        headers: { Origin: origin, "X-CSRF-Token": session.csrf_token },
        data: { ...data, expected_revision: alert.revision + 1 },
      })
    ).status(),
  ).toBe(409);
  const after = (
    await (
      await request.get(`/api/dataops/monitoring/alerts/${alert.id}`)
    ).json()
  ).alert;
  expect(after.revision).toBe(alert.revision);
});

test("analyst assigns, acknowledges, investigates, resolves and reopens with authenticated history", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Username", { exact: true })
    .fill(process.env.E2E_USERNAME!);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.E2E_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByText("Provider intelligence, explained."),
  ).toBeVisible();
  const session = await (await page.request.get("/api/auth/me")).json();
  await page
    .getByRole("button", { name: "Data operations", exact: true })
    .click();
  await page.getByLabel("Data source mode").selectOption("fixture");
  await page
    .getByRole("button", { name: "Quality monitoring", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Alert status", exact: true })
    .selectOption("open");
  await page
    .getByRole("button", { name: /Inspect alert/ })
    .first()
    .click();
  const alerts = await (
    await page.request.get(
      "/api/dataops/monitoring/alerts?mode=fixture&status=open",
    )
  ).json();
  const target = alerts.items[0];
  const decisionId = crypto.randomUUID();
  for (const [state, explanation] of [
    ["acknowledged", "Reviewed incoming evidence and accepted ownership."],
    [
      "investigating",
      "Compared source fields against the compatible baseline.",
    ],
    ["resolved", "Confirmed expected fixture anomaly; resolution documented."],
    ["open", "Reopened for a second source review."],
  ]) {
    const note = `${explanation} (${decisionId})`;
    await page
      .getByRole("combobox", { name: "Next action", exact: true })
      .selectOption(state);
    if (state === "acknowledged")
      await page
        .getByRole("combobox", { name: "Assign to", exact: true })
        .selectOption(session.user.id);
    await page.getByLabel("Decision note", { exact: true }).fill(note);
    await page
      .getByRole("button", { name: "Save decision", exact: true })
      .click();
    await expect(
      page.getByRole("list").getByText(note, { exact: true }),
    ).toBeVisible();
  }
  const detail = await (
    await page.request.get(`/api/dataops/monitoring/alerts/${target.id}`)
  ).json();
  expect(detail.alert.status).toBe("open");
  expect(detail.alert.revision).toBe(target.revision + 4);
  expect(detail.alert.assigned_user_id).toBe(session.user.id);
  const history = await (
    await page.request.get(`/api/dataops/monitoring/alerts/${target.id}/events`)
  ).json();
  for (const event of history.items.slice(0, 4))
    expect(event.actor_user_id).toBe(session.user.id);
  await page.screenshot({
    path: "../docs/analyst-workspace-4.0.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  const accountBar = await page
    .getByRole("banner", { name: "Signed-in account" })
    .boundingBox();
  const signOut = await page
    .getByRole("button", { name: "Sign out", exact: true })
    .boundingBox();
  expect(signOut!.y + signOut!.height).toBeLessThanOrEqual(
    accountBar!.y + accountBar!.height,
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await expect(
    page.getByRole("button", { name: "Save decision", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/analyst-mobile-4.0.png",
    fullPage: true,
  });
});
