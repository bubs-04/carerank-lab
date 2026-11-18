import { test, expect } from "./authenticated";

test("viewer inspects operational reliability, changes window and follows evidence on mobile", async ({
  page,
  request,
}) => {
  const response = await request.get("/api/operations/reliability?hours=24");
  expect(response.status()).toBe(200);
  const report = await response.json();
  await page.goto("/");
  await page.getByRole("button", { name: "Reliability", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Operational reliability", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Authenticated, read-only evidence"),
  ).toBeVisible();
  await expect(
    page.getByText("Keep the evidence separate.", { exact: true }),
  ).toBeVisible();
  expect(report.limits.heartbeat_stale_seconds).toBe(30);
  await page
    .getByRole("combobox", { name: "Observation window" })
    .selectOption("168");
  await expect(
    page.getByRole("img", {
      name: /Hourly pipeline activity over the last 168 hours/,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Refresh reliability", exact: true })
    .click();
  await expect(
    page.getByRole("combobox", { name: "Observation window" }),
  ).toHaveValue("168");
  await expect(
    page.getByRole("button", { name: "Refresh reliability", exact: true }),
  ).toBeEnabled();
  await page.screenshot({
    path: "../docs/reliability-6.0.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await expect(
    page.getByRole("button", { name: "Reliability", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect pipeline histories", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Pipeline operations", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reliability", exact: true }).click();
  await page
    .getByRole("button", { name: "Open data operations", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Data operations", exact: true }),
  ).toBeVisible();
});
