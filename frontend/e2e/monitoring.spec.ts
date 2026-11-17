import { test, expect } from "./authenticated";
test("monitoring evidence, safe read-only investigation, refresh and mobile navigation", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.DATAOPS_E2E !== "1",
    "Ingest offline fixtures after migration 003 first",
  );
  const summary = await (
    await request.get("/api/dataops/monitoring/summary?mode=fixture")
  ).json();
  expect(summary.evaluations.failed).toBeGreaterThan(0);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Data operations", exact: true })
    .click();
  await page.getByLabel("Data source mode").selectOption("fixture");
  await page
    .getByRole("button", { name: "Quality monitoring", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Data quality monitoring", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("group", { name: "Latest rule evaluation outcomes" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /Inspect alert/ })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Append-only investigation history" }),
  ).toBeVisible();
  await page.screenshot({ path: "../docs/monitoring.png", fullPage: true });
  await page.getByRole("button", { name: "Refresh status" }).click();
  await expect(page.getByLabel("Data source mode")).toHaveValue("fixture");
  await expect(
    page.getByRole("button", { name: "Quality monitoring" }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Data operations", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../docs/mobile-monitoring.png",
    fullPage: true,
  });
  const alerts = await (
    await request.get("/api/dataops/monitoring/alerts?mode=fixture")
  ).json();
  expect(
    (
      await request.patch(
        `/api/dataops/monitoring/alerts/${alerts.items[0].id}`,
        { data: { status: "resolved" } },
      )
    ).status(),
  ).toBe(405);
});
