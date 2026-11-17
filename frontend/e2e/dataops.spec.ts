import { test, expect } from "./authenticated";
test("fixture ingestion history, comparison, findings and mobile layout", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.DATAOPS_E2E !== "1",
    "Run the two CLI fixtures first; never trigger ingestion through HTTP",
  );
  const versions = await (
    await request.get("/api/dataops/versions?mode=fixture")
  ).json();
  expect(versions.items.length).toBeGreaterThanOrEqual(2);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Data operations", exact: true })
    .click();
  await page.getByLabel("Data source mode").selectOption("fixture");
  await expect(page.getByText(/artificial test records/)).toBeVisible();
  await page
    .getByRole("button", {
      name: `Set older ${versions.items[1].id.slice(0, 8)}`,
      exact: true,
    })
    .click();
  await page
    .getByRole("button", {
      name: `Set newer ${versions.items[0].id.slice(0, 8)}`,
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("group", {
      name: "Accepted-record changes in captured samples",
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect latest findings", exact: true })
    .click();
  await expect(
    page.getByText("invalid_identifier", { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: "../docs/dataops.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({ path: "../docs/mobile-dataops.png", fullPage: true });
});

test("refresh status stays on Data operations and preserves fixture mode", async ({
  page,
}) => {
  await page.goto("/");

  await page
    .getByRole("button", { name: "Data operations", exact: true })
    .click();

  const mode = page.getByLabel("Data source mode");
  await mode.selectOption("fixture");
  await expect(mode).toHaveValue("fixture");

  await page.getByRole("button", { name: "Refresh status" }).click();

  await expect(
    page.getByRole("button", { name: "Refresh status" }),
  ).toBeVisible();
  await expect(page.getByLabel("Data source mode")).toHaveValue("fixture");
});
