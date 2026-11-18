import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Reliability, { type ReliabilityReport } from "./Reliability";

const report: ReliabilityReport = {
  window: {
    hours: 24,
    from: "2026-11-17T12:15:00Z",
    to: "2026-11-18T12:15:00Z",
  },
  generated_at: "2026-11-18T12:15:00Z",
  workers: [
    {
      worker_id: "worker-healthy",
      instance_id: "platform-a",
      state: "running",
      started_at: "2026-11-18T11:00:00Z",
      heartbeat_at: "2026-11-18T12:14:59Z",
      execution_id: "execution-1",
      healthy: true,
      age_seconds: 1,
    },
    {
      worker_id: "worker-stale",
      instance_id: "platform-b",
      state: "running",
      started_at: "2026-11-18T10:00:00Z",
      heartbeat_at: "2026-11-18T12:13:00Z",
      execution_id: "execution-2",
      healthy: false,
      age_seconds: 120,
    },
    {
      worker_id: "worker-degraded",
      instance_id: "platform-c",
      state: "degraded",
      started_at: "2026-11-18T11:00:00Z",
      heartbeat_at: "2026-11-18T12:14:59Z",
      execution_id: null,
      healthy: false,
      age_seconds: 1,
    },
  ],
  summary: {
    completed: 12,
    succeeded: 8,
    failed: 2,
    cancelled: 2,
    retried_executions: 3,
    retry_attempts: 4,
    success_rate: 0.8,
    p50_duration_seconds: 2.4,
    p95_duration_seconds: 14.8,
  },
  queue: {
    queued: 1,
    running: 2,
    retry_wait: 3,
    overdue_leases: 1,
    oldest_ready_age_seconds: 63,
  },
  activity: [
    {
      hour: "2026-11-18T12:00:00Z",
      completed: 12,
      succeeded: 8,
      failed: 2,
      retries: 4,
    },
  ],
  quality: { open_alerts: 4, critical_open_alerts: 2 },
  limits: { heartbeat_stale_seconds: 30, max_window_hours: 168 },
};
const respond = (body: unknown, status = 200, requestId?: string) =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...(requestId ? { "X-Request-ID": requestId } : {}),
    },
  });
const show = () => {
  const onPipelines = vi.fn();
  const onDataOperations = vi.fn();
  render(
    <Reliability
      onPipelines={onPipelines}
      onDataOperations={onDataOperations}
    />,
  );
  return { onPipelines, onDataOperations };
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("presents measured denominators, worker states and read-only evidence navigation", async () => {
  const fetcher = vi.fn(async (_url: string) => respond(report));
  vi.stubGlobal("fetch", fetcher);
  const actions = show();
  expect(await screen.findByText("80.0%")).toBeVisible();
  expect(
    screen.getByText("8 succeeded / 10 non-cancelled outcomes"),
  ).toBeVisible();
  expect(screen.getByText("14.8s")).toBeVisible();
  expect(screen.getByText("Healthy · running")).toBeVisible();
  expect(screen.getByText("Stale heartbeat · running")).toBeVisible();
  expect(screen.getByText("Not ready · degraded")).toBeVisible();
  expect(
    screen.getByText(/1 running execution\(s\) have an expired lease/),
  ).toBeVisible();
  expect(
    screen.getByRole("img", { name: /Hourly pipeline activity/ }),
  ).toBeVisible();
  fireEvent.click(screen.getByText("Exact hourly activity", { exact: true }));
  const table = screen.getByRole("table");
  expect(
    within(table).getByRole("columnheader", { name: "Retry attempts" }),
  ).toBeVisible();
  expect(within(table).getByRole("cell", { name: /^12$/ })).toBeVisible();
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect pipeline histories" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Open data operations" }));
  expect(actions.onPipelines).toHaveBeenCalledOnce();
  expect(actions.onDataOperations).toHaveBeenCalledOnce();
  expect(fetcher).toHaveBeenCalledOnce();
  expect(fetcher.mock.calls[0][0]).toBe("/api/operations/reliability?hours=24");
});

it("does not fabricate a success percentage or duration when no samples exist", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      respond({
        ...report,
        workers: [],
        activity: [],
        summary: {
          completed: 0,
          succeeded: 0,
          failed: 0,
          cancelled: 0,
          retried_executions: 0,
          retry_attempts: 0,
          success_rate: null,
          p50_duration_seconds: null,
          p95_duration_seconds: null,
        },
        queue: {
          queued: 0,
          running: 0,
          retry_wait: 0,
          overdue_leases: 0,
          oldest_ready_age_seconds: null,
        },
      }),
    ),
  );
  show();
  expect(
    await screen.findByText("No healthy worker heartbeat recorded"),
  ).toBeVisible();
  expect(screen.getAllByText("No sample")).toHaveLength(2);
  expect(screen.queryByText("0.0%")).not.toBeInTheDocument();
  expect(screen.getByText("None ready")).toBeVisible();
  expect(screen.getByText(/No workers have reported presence/)).toBeVisible();
  fireEvent.click(screen.getByText("Exact hourly activity", { exact: true }));
  expect(
    screen.getByText(
      "No execution completions or retry starts recorded in this window.",
    ),
  ).toBeVisible();
});

it("retains last evidence on refresh failure and exposes the server correlation ID", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(respond(report))
    .mockResolvedValueOnce(
      respond({ detail: "Database unavailable" }, 503, "correlation-example"),
    );
  vi.stubGlobal("fetch", fetcher);
  show();
  await screen.findByText("80.0%");
  fireEvent.click(screen.getByRole("button", { name: "Refresh reliability" }));
  const warning = await screen.findByRole("alert");
  expect(warning).toHaveTextContent(
    "Database unavailable · Request ID: correlation-example",
  );
  expect(warning).toHaveTextContent("Worker states may now be stale");
  expect(screen.getByText("80.0%")).toBeVisible();
  expect(screen.getByText("Last recorded operational state")).toBeVisible();
});

it("clears the old window while another window loads and leaves it empty on failure", async () => {
  let resolveWindow!: (value: Response) => void;
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(respond(report))
    .mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          resolveWindow = resolve;
        }),
    );
  vi.stubGlobal("fetch", fetcher);
  show();
  await screen.findByText("80.0%");
  fireEvent.change(
    screen.getByRole("combobox", { name: "Observation window" }),
    { target: { value: "168" } },
  );
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  expect(fetcher.mock.calls[1][0]).toBe(
    "/api/operations/reliability?hours=168",
  );
  expect(screen.queryByText("80.0%")).not.toBeInTheDocument();
  resolveWindow(respond({ detail: "Temporarily unavailable" }, 503));
  await screen.findByRole("alert");
  expect(screen.getByRole("status")).toHaveTextContent(
    "No reliability evidence is available for this window",
  );
  expect(screen.queryByText("80.0%")).not.toBeInTheDocument();
});
