import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import PipelineOperations from "./PipelineOperations";
import { AuthContext } from "./Auth";

const configuration = {
  name: "Fixture reliability",
  source: "fixture_a",
  max_rows: 5,
  enabled: false,
  interval_seconds: 3600,
  max_attempts: 3,
  backoff_seconds: 5,
  timeout_seconds: 120,
};
const execution = {
  id: "execution-1",
  pipeline_id: "pipeline-1",
  pipeline_name: configuration.name,
  status: "retry_wait",
  revision: 2,
  trigger: "scheduled",
  scheduled_for: "2026-11-17T10:00:00Z",
  created_at: "2026-11-17T10:00:00Z",
  started_at: "2026-11-17T10:00:01Z",
  finished_at: null,
  available_at: "2026-11-17T10:00:06Z",
  heartbeat_at: "2026-11-17T10:00:01Z",
  lease_expires_at: null,
  attempt_count: 1,
  max_attempts: 3,
  error_code: "demo_transient_failure",
  published_run_id: null,
  snapshot_id: null,
  duration_seconds: 1,
  config: configuration,
  attempts: [
    {
      id: "attempt-1",
      number: 1,
      worker_id: "worker-a",
      status: "failed",
      started_at: "2026-11-17T10:00:01Z",
      finished_at: "2026-11-17T10:00:02Z",
      heartbeat_at: "2026-11-17T10:00:01Z",
      lease_expires_at: null,
      error_code: "demo_transient_failure",
      ingestion_run_id: "run-1",
      duration_seconds: 1,
    },
  ],
  events: [
    {
      id: "event-1",
      created_at: "2026-11-17T10:00:02Z",
      action: "retry_scheduled",
      from_status: "running",
      to_status: "retry_wait",
      actor_user_id: null,
      details: { error_code: "demo_transient_failure" },
    },
  ],
};
const pipeline = {
  ...configuration,
  id: "pipeline-1",
  revision: 1,
  next_run_at: null,
  created_at: "2026-11-17T10:00:00Z",
  updated_at: "2026-11-17T10:00:00Z",
  latest_execution: execution,
};
const metrics = {
  queued: 0,
  running: 0,
  retry_wait: 1,
  succeeded: 0,
  failed: 0,
  cancelled: 0,
  timed_out: 0,
};
function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function reads(
  url: string,
  current: Omit<typeof execution, "published_run_id" | "snapshot_id"> & {
    published_run_id: string | null;
    snapshot_id: string | null;
  } = execution,
  schedules = [pipeline],
) {
  if (url === "/api/operations/pipelines")
    return response({ items: schedules, demo_enabled: true });
  if (url.startsWith("/api/operations/executions?"))
    return response({ items: [current], total: 1, metrics });
  return response(current);
}
function show(
  role: "viewer" | "analyst" | "administrator" = "viewer",
  onEvidence = vi.fn(),
) {
  render(
    <AuthContext.Provider
      value={{
        user: { id: "actor", username: role, display_name: role, role },
        csrf_token: "csrf",
        logout: vi.fn(),
      }}
    >
      <PipelineOperations onEvidence={onEvidence} />
    </AuthContext.Provider>,
  );
  return onEvidence;
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("gives viewers accurate attempt evidence without execution or schedule controls", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => reads(url)),
  );
  const onEvidence = show();
  expect(await screen.findByText("Attempt 1")).toBeVisible();
  expect(screen.getByText(/Retry eligible at/)).toBeVisible();
  expect(screen.getByText(/Worker worker-a/)).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /Run .* now/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Cancel execution" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("form", { name: "Create pipeline" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect attempt ingestion run-1" }),
  );
  expect(onEvidence).toHaveBeenCalledWith("run-1", null, "fixture");
});

it("retains a manual trigger's idempotency key after an uncertain network failure", async () => {
  let attempts = 0;
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    if (options?.method === "POST") {
      if (++attempts === 1) throw new TypeError("Connection lost");
      return response(execution);
    }
    return reads(url);
  });
  vi.stubGlobal("fetch", fetch);
  show("analyst");
  const button = await screen.findByRole("button", {
    name: "Run Fixture reliability now",
  });
  fireEvent.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent("Connection lost");
  fireEvent.click(button);
  await screen.findByText("Execution accepted. Follow its progress below.");
  const posts = fetch.mock.calls.filter(
    ([, options]) => options?.method === "POST",
  );
  expect(posts).toHaveLength(2);
  expect(posts[0][1]?.body).toBe(posts[1][1]?.body);
  expect(JSON.parse(posts[0][1]!.body as string).idempotency_key).toMatch(
    /^[0-9a-f-]{36}$/,
  );
  expect(posts[0][1]?.headers).toEqual(
    expect.objectContaining({ "X-CSRF-Token": "csrf" }),
  );
  fireEvent.click(button);
  await waitFor(() =>
    expect(
      fetch.mock.calls.filter(([, options]) => options?.method === "POST"),
    ).toHaveLength(3),
  );
  expect(
    fetch.mock.calls.filter(([, options]) => options?.method === "POST")[2][1]
      ?.body,
  ).not.toBe(posts[0][1]?.body);
});

it("lets an Administrator create the bounded deterministic recovery schedule", async () => {
  const fetch = vi.fn(async (url: string, options?: RequestInit) =>
    options?.method === "POST" ? response(pipeline) : reads(url, execution, []),
  );
  vi.stubGlobal("fetch", fetch);
  show("administrator");
  const form = await screen.findByRole("form", { name: "Create pipeline" });
  fireEvent.change(within(form).getByLabelText("Pipeline name"), {
    target: { value: "Recovery demonstration" },
  });
  fireEvent.change(within(form).getByLabelText("Source"), {
    target: { value: "fixture_retry" },
  });
  fireEvent.change(within(form).getByLabelText("Schedule interval (seconds)"), {
    target: { value: "10" },
  });
  fireEvent.change(within(form).getByLabelText("Initial backoff (seconds)"), {
    target: { value: "1" },
  });
  fireEvent.click(within(form).getByLabelText("Enable scheduled ingestion"));
  fireEvent.click(
    within(form).getByRole("button", { name: "Create pipeline" }),
  );
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/operations/pipelines",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          name: "Recovery demonstration",
          source: "fixture_retry",
          max_rows: 5,
          enabled: true,
          interval_seconds: 10,
          max_attempts: 3,
          backoff_seconds: 1,
          timeout_seconds: 120,
        }),
      }),
    ),
  );
});

it("refreshes a conflicting schedule and submits only intentionally changed configuration", async () => {
  let conflict = false;
  const latest = { ...pipeline, enabled: true, revision: 2 };
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    if (options?.method === "PATCH") {
      conflict = true;
      return response({ detail: "Pipeline changed; reload its revision" }, 409);
    }
    return reads(url, execution, [conflict ? latest : pipeline]);
  });
  vi.stubGlobal("fetch", fetch);
  show("administrator");
  await screen.findByText("Edit schedule and recovery policy");
  fireEvent.click(screen.getByText("Edit schedule and recovery policy"));
  let form = screen.getByRole("form", {
    name: "Configure Fixture reliability",
  });
  fireEvent.change(within(form).getByLabelText("Maximum attempts"), {
    target: { value: "4" },
  });
  fireEvent.click(
    within(form).getByRole("button", { name: "Save pipeline settings" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Pipeline changed",
  );
  await waitFor(() => {
    form = screen.getByRole("form", { name: "Configure Fixture reliability" });
    expect(
      within(form).getByLabelText("Enable scheduled ingestion"),
    ).toBeChecked();
  });
  expect(within(form).getByLabelText("Maximum attempts")).toHaveValue(3);
  expect(
    within(form).getByRole("button", { name: "Save pipeline settings" }),
  ).toBeDisabled();
  const patches = fetch.mock.calls.filter(
    ([, options]) => options?.method === "PATCH",
  );
  expect(patches).toHaveLength(1);
  expect(JSON.parse(patches[0][1]!.body as string)).toEqual({
    max_attempts: 4,
    expected_revision: 1,
  });
});

it("records a cancellation reason and revision without erasing attempt history", async () => {
  const fetch = vi.fn(async (url: string, options?: RequestInit) =>
    options?.method === "POST"
      ? response({ ...execution, status: "cancelled" })
      : reads(url),
  );
  vi.stubGlobal("fetch", fetch);
  show("analyst");
  const cancel = await screen.findByRole("button", {
    name: "Cancel execution",
  });
  expect(cancel).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Cancellation reason"), {
    target: { value: "Review source scope first" },
  });
  fireEvent.click(cancel);
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/operations/executions/execution-1/cancel",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          expected_revision: 2,
          reason: "Review source scope first",
        }),
      }),
    ),
  );
  expect(
    await screen.findByText("Execution cancelled. Its history is retained."),
  ).toBeVisible();
  expect(screen.getByText("Attempt 1")).toBeVisible();
});

it("keeps publication evidence visible when monitoring recovery has failed", async () => {
  const published = {
    ...execution,
    status: "failed",
    published_run_id: "run-2",
    snapshot_id: "snapshot-2",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => reads(url, published)),
  );
  const onEvidence = show("analyst");
  const evidence = await screen.findByRole("button", {
    name: "Inspect ingestion and quality evidence",
  });
  expect(screen.getByText(/published data is retained/)).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Cancel execution" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry execution" })).toBeVisible();
  fireEvent.click(evidence);
  expect(onEvidence).toHaveBeenCalledWith("run-2", "snapshot-2", "fixture");
});

it("shows rejected control requests without fabricating an accepted execution", async () => {
  const fetch = vi.fn(async (url: string, options?: RequestInit) =>
    options?.method === "POST"
      ? response({ detail: "Analyst role required" }, 403)
      : reads(url),
  );
  vi.stubGlobal("fetch", fetch);
  show("analyst");
  fireEvent.click(
    await screen.findByRole("button", { name: "Run Fixture reliability now" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Analyst role required",
  );
  expect(
    screen.queryByText("Execution accepted. Follow its progress below."),
  ).not.toBeInTheDocument();
  expect(
    fetch.mock.calls.filter(([, options]) => options?.method === "POST"),
  ).toHaveLength(1);
});

it("retains the last history but disables controls when a refresh fails", async () => {
  let fail = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      fail ? response({ detail: "Database unavailable" }, 503) : reads(url),
    ),
  );
  show("analyst");
  await screen.findByText("Attempt 1");
  fail = true;
  fireEvent.click(screen.getByRole("button", { name: "Refresh operations" }));
  await screen.findByText("Schedules could not refresh: Database unavailable");
  expect(screen.getByText("Attempt 1")).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Run Fixture reliability now" }),
  ).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "Cancel execution" }),
  ).not.toBeInTheDocument();
});

it("paginates retained execution history beyond the latest fifty", async () => {
  const fetcher = vi.fn(async (url: string) => {
    if (url.startsWith("/api/operations/executions?"))
      return response({ items: [execution], total: 51, metrics });
    return reads(url);
  });
  vi.stubGlobal("fetch", fetcher);
  show();
  fireEvent.click(
    await screen.findByRole("button", { name: "Older executions" }),
  );
  await waitFor(() =>
    expect(fetcher.mock.calls.some(([url]) => url.includes("offset=50"))).toBe(
      true,
    ),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Newer executions" }),
    ).toBeEnabled(),
  );
  expect(
    screen.getByRole("button", { name: "Older executions" }),
  ).toBeDisabled();
});
