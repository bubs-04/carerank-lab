import { test, expect } from "@playwright/test";

test("scheduled pipeline fails safely, recovers, and retains inspectable evidence", async ({
  page,
}) => {
  test.setTimeout(90000);
  page.setDefaultTimeout(10000);
  test.skip(
    process.env.DATAOPS_E2E !== "1",
    "Requires isolated fixtures and a running worker",
  );
  await page.goto("/");
  await page
    .getByLabel("Username", { exact: true })
    .fill(process.env.E2E_ADMIN_USERNAME!);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.E2E_ADMIN_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("button", { name: "Pipeline operations", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Pipeline operations", exact: true }),
  ).toBeVisible();
  const form = page.getByRole("form", { name: "Create pipeline", exact: true });
  await expect(
    page.getByText("Create a pipeline", { exact: true }),
  ).toBeVisible();
  if (!(await form.isVisible()))
    await page.getByText("Create a pipeline", { exact: true }).click();
  const name = `Recovery verification ${Date.now()}`;
  await form.getByLabel("Pipeline name").fill(name);
  await form
    .getByRole("combobox", { name: "Source", exact: true })
    .selectOption("fixture_retry");
  await form.getByLabel("Maximum attempts").fill("2");
  await form.getByLabel("Initial backoff (seconds)").fill("8");
  await form.getByLabel("Execution timeout (seconds)").fill("30");
  await form.getByLabel("Enable scheduled ingestion").check();
  await form
    .getByRole("button", { name: "Create pipeline", exact: true })
    .click();
  await expect(
    page.getByText("Pipeline created. Enable its schedule or run it manually."),
  ).toBeVisible();
  const definitions = await (
    await page.request.get("/api/operations/pipelines")
  ).json();
  const pipeline = definitions.items.find(
    (item: { name: string }) => item.name === name,
  );
  expect(pipeline.enabled).toBe(true);
  await page
    .getByRole("combobox", { name: "Pipeline", exact: true })
    .selectOption(pipeline.id);
  const history = async () =>
    (
      await (
        await page.request.get(
          `/api/operations/executions?pipeline_id=${pipeline.id}`,
        )
      ).json()
    ).items;
  await expect
    .poll(async () => (await history())[0]?.status, { timeout: 20000 })
    .toBe("retry_wait");
  const execution = (await history())[0];
  expect(execution.trigger).toBe("scheduled");
  const detail = async () =>
    (
      await page.request.get(`/api/operations/executions/${execution.id}`)
    ).json();
  const failed = await detail();
  expect(failed.attempts[0].error_code).toBe("demo_transient_failure");
  await page.getByRole("button", { name: "Refresh operations" }).click();
  await expect(
    page.getByText("Retry eligible at", { exact: false }),
  ).toBeVisible();
  await expect
    .poll(async () => (await detail()).status, { timeout: 30000 })
    .toBe("succeeded");
  const recovered = await detail();
  expect(
    recovered.attempts.map((item: { status: string }) => item.status),
  ).toEqual(["failed", "succeeded"]);
  expect(
    recovered.events.map((item: { action: string }) => item.action),
  ).toEqual(["queued", "claimed", "retry_scheduled", "claimed", "succeeded"]);
  expect(recovered.snapshot_id).toBeTruthy();
  expect(recovered.published_run_id).toBe(
    recovered.attempts[1].ingestion_run_id,
  );
  expect(recovered.finished_at).toBeTruthy();
  expect(recovered.duration_seconds).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Refresh operations" }).click();
  await expect(page.getByText("Attempt 2", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Publication recorded.", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/pipeline-operations-5.0.png",
    fullPage: true,
  });
  // Pause future scheduling through the same reviewed configuration interface.
  await page
    .getByRole("article")
    .filter({
      has: page.getByRole("heading", { name, exact: true }),
    })
    .getByText("Edit schedule and recovery policy", { exact: true })
    .click();
  const edit = page.getByRole("form", {
    name: `Configure ${name}`,
    exact: true,
  });
  await edit.getByLabel("Enable scheduled ingestion").uncheck();
  await edit.getByRole("button", { name: "Save pipeline settings" }).click();
  await expect(page.getByText("Pipeline settings saved.")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await expect(
    page.getByRole("button", { name: "Pipeline operations", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Inspect ingestion and quality evidence",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("heading", { name: "Data operations", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Data source mode")).toHaveValue("fixture");
});
