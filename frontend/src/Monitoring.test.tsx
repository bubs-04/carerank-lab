import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Monitoring from "./Monitoring";
import DataOps from "./DataOps";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const run = {
  id: "run-00001",
  status: "succeeded",
  started_at: "2026-11-16T00:00:00Z",
  snapshot_id: "snapshot-001",
  received: 5,
  requested: 5,
  error_code: null,
};
const evaluation = {
  id: "eval-001",
  run_id: run.id,
  snapshot_id: run.snapshot_id,
  baseline_run_id: null,
  profile: "profile-001",
  observed: 20,
  status: "failed",
  explanation: "One of five rows lacks specialty; threshold is five percent.",
  evidence: { missing_pri_spec_rows: 1, received: 5 },
  rule: {
    id: "rule-001",
    rule_id: "missing_pri_spec",
    version: "1.0",
    threshold: 5,
    unit: "%",
    description: "Missing specialty rows",
    severity: "warning",
  },
};
const alert = {
  id: "alert-001",
  run_id: run.id,
  severity: "warning",
  status: "open",
  assigned_to: null,
  resolution: null,
  revision: 1,
  created_at: run.started_at,
};
const page = (items: unknown[], total = items.length) => ({
  items,
  total,
  page: 1,
  page_size: 20,
});
function mock({
  empty = false,
  health = "attention",
  fail = false,
  unavailable = false,
} = {}) {
  const fetch = vi.fn(async (url: string, _options?: RequestInit) => ({
    ok: !fail,
    status: fail ? 503 : 200,
    json: async () => {
      if (fail) return { detail: "Database unavailable" };
      if (url.includes("/monitoring/summary"))
        return {
          health,
          explanation:
            health === "partial"
              ? "Some rules lack comparable history."
              : "Check current rule coverage.",
          profile: "profile-001",
          expected_rules: 12,
          latest_run: empty ? null : run,
          evaluations: empty ? {} : { passed: 6, failed: 1, not_evaluable: 5 },
          open_by_severity: empty ? {} : { warning: 1 },
          caveat: "Cutoff shifts are not clinician exits.",
        };
      if (url.includes("/events"))
        return page([
          {
            id: "event-001",
            revision: 1,
            actor: "system",
            from_status: null,
            to_status: "open",
            note: "Threshold exceeded",
            created_at: run.started_at,
          },
        ]);
      if (url.includes("/alerts/")) return { alert, evaluation };
      if (url.includes("/alerts?"))
        return page(empty ? [] : [alert], empty ? 0 : 21);
      if (url.includes("/evaluations"))
        return page(
          empty
            ? []
            : [
                {
                  ...evaluation,
                  ...(unavailable
                    ? { observed: null, status: "not_evaluable" }
                    : {}),
                },
              ],
        );
      if (url.includes("/trends"))
        return {
          scope: { max_rows: 5 },
          policy: "v1",
          caveat: "Only compatible samples",
          points: empty
            ? []
            : [0, 1].map((i) => ({
                run_id: `trend-${i}`,
                started_at: run.started_at,
                received: 5,
                valid: 4 + i,
                rejected: 1 - i,
                warnings: 1,
              })),
        };
      if (url.includes("/monitoring/runs/")) return run;
      if (url.includes("/dataops/runs?")) return page(empty ? [] : [run]);
      if (url.includes("/dataops/status"))
        return {
          sources: [],
          latest_attempt: null,
          latest_success: null,
          snapshot_count: 0,
        };
      return page([]);
    },
  }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
it("shows explainable health and numerical accessible charts", async () => {
  mock();
  render(<Monitoring mode="fixture" onInspect={vi.fn()} />);
  expect(await screen.findByText("attention")).toBeVisible();
  expect(
    screen.getByRole("group", { name: "Latest rule evaluation outcomes" }),
  ).toHaveTextContent("not evaluable5");
  expect(
    await screen.findByRole("img", { name: /Accepted record counts/ }),
  ).toBeVisible();
  expect(
    screen.getByRole("table", { name: /Comparable retrieval counts/ }),
  ).toHaveTextContent("Accepted");
});
it("does not turn no evidence into green health", async () => {
  mock({ empty: true, health: "no_data" });
  render(<Monitoring mode="cms" onInspect={vi.fn()} />);
  expect(
    (await screen.findByText("no data")).closest(".monitor-health"),
  ).not.toHaveClass("monitor-passed");
  expect(await screen.findByText(/No matching evaluations/)).toBeVisible();
  expect(screen.getByText(/No alerts match these filters/)).toBeVisible();
});
it("renders unavailable metrics explicitly, with threshold evidence", async () => {
  mock({ health: "partial", unavailable: true });
  render(<Monitoring mode="fixture" onInspect={vi.fn()} />);
  const summary = await screen.findByText(/missing_pri_spec · not evaluable/);
  fireEvent.click(summary);
  expect(screen.getByText(/Observed: Unavailable/)).toHaveTextContent(
    "Alert threshold: > 5 %",
  );
});
it("filters and paginates alerts using bounded API queries", async () => {
  const fetch = mock();
  render(<Monitoring mode="fixture" onInspect={vi.fn()} />);
  await screen.findByText("attention");
  fireEvent.change(screen.getByLabelText("Alert severity"), {
    target: { value: "critical" },
  });
  fireEvent.change(screen.getByLabelText("Alert status"), {
    target: { value: "open" },
  });
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("status=open&severity=critical"),
      expect.anything(),
    ),
  );
  const panel = screen
    .getByRole("heading", { name: "Alert history" })
    .closest("section")!;
  await waitFor(() => expect(within(panel).getByText("Next")).toBeEnabled());
  fireEvent.click(within(panel).getByText("Next"));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("page=2&status=open"),
      expect.anything(),
    ),
  );
});
it("opens evidence, audit history and safe local CLI instructions", async () => {
  const inspect = vi.fn();
  const fetch = mock();
  render(<Monitoring mode="fixture" onInspect={inspect} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Inspect alert alert-00" }),
  );
  const panel = await screen.findByRole("region", {
    name: "Alert investigation",
  });
  expect(within(panel).getByText(/One of five rows/)).toBeVisible();
  expect(await within(panel).findByText("Threshold exceeded")).toBeVisible();
  fireEvent.click(within(panel).getByText("View snapshot records"));
  expect(inspect).toHaveBeenCalledWith(run.id, run.snapshot_id);
  expect(panel).toHaveTextContent("--expected-revision 1");
  expect(
    fetch.mock.calls.every(([, opts]) => !(opts as RequestInit)?.method),
  ).toBe(true);
});
it("preserves monitoring tab and fixture mode when refreshing status", async () => {
  const fetch = mock();
  render(<DataOps />);
  fireEvent.change(screen.getByLabelText("Data source mode"), {
    target: { value: "fixture" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Quality monitoring" }));
  await screen.findByText("attention");
  const before = fetch.mock.calls.filter(([url]) =>
    url.includes("monitoring/summary"),
  ).length;
  fireEvent.click(screen.getByRole("button", { name: "Refresh status" }));
  await screen.findByText("attention");
  expect(screen.getByLabelText("Data source mode")).toHaveValue("fixture");
  expect(
    screen.getByRole("button", { name: "Quality monitoring" }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(
    fetch.mock.calls.filter(([url]) => url.includes("monitoring/summary"))
      .length,
  ).toBe(before + 1);
});
it("links an investigation back to the actual attempt and finding panel", async () => {
  mock();
  render(<DataOps />);
  fireEvent.click(screen.getByRole("button", { name: "Quality monitoring" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Inspect alert alert-00" }),
  );
  const panel = await screen.findByRole("region", {
    name: "Alert investigation",
  });
  fireEvent.click(within(panel).getByText("View attempt and findings"));
  expect(
    await screen.findByRole("heading", {
      name: "Selected investigation evidence",
    }),
  ).toBeVisible();
  expect(await screen.findByText(/succeeded · requested 5/)).toBeVisible();
});
it("reports service failures without a success state", async () => {
  mock({ fail: true });
  render(<Monitoring mode="cms" onInspect={vi.fn()} />);
  expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent(
    "Check migration 003",
  );
  expect(screen.queryByText("passed", { exact: true })).not.toBeInTheDocument();
});
it("shows loading while evidence requests are pending", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise(() => {})),
  );
  render(<Monitoring mode="cms" onInspect={vi.fn()} />);
  expect(screen.getAllByRole("status")[0]).toHaveTextContent(
    "Loading monitoring evidence",
  );
});
