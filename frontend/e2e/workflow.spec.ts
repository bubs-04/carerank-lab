import { test, expect } from "@playwright/test";
test("live data supports search, pagination, details, and comparison", async ({
  page,
  request,
}) => {
  const response = await request.get(
    "/api/providers?specialty=Cardiology&page_size=3",
  );
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.total).toBeGreaterThan(12);
  await page.goto("/");
  await expect(
    page.getByText("Provider intelligence, explained."),
  ).toBeVisible();
  await page.screenshot({ path: "../docs/overview.png", fullPage: true });
  await page.getByRole("button", { name: "Explore providers" }).click();
  await page
    .getByLabel("Specialty", { exact: true })
    .selectOption("Cardiology");
  await expect(
    page.getByRole("button", { name: body.items[0].name, exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText(/Page 2 of/)).toBeVisible();
  await page.getByRole("button", { name: "Previous", exact: true }).click();
  await page.getByRole("checkbox").nth(0).check();
  await page.getByRole("checkbox").nth(1).check();
  await page.screenshot({ path: "../docs/explorer.png", fullPage: true });
  await page.getByRole("button", { name: "Compare (2)", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Provider comparison" }),
  ).toBeVisible();
  await expect(page.getByText("Score breakdown", { exact: true })).toHaveCount(
    2,
  );
  await page.screenshot({ path: "../docs/comparison.png", fullPage: true });
  await page.getByRole("button", { name: "Back to providers" }).click();
  await page
    .getByPlaceholder("Search demo providers…")
    .fill(body.items[0].name);
  await page
    .getByRole("button", { name: body.items[0].name, exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Provider profile" }),
  ).toBeVisible();
  await expect(
    page.getByText("Score breakdown", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/provider-profile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(
    page.getByText("Provider intelligence, explained."),
  ).toBeVisible();
  await page.screenshot({ path: "../docs/mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
