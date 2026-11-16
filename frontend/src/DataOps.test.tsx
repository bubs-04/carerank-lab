import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import DataOps from "./DataOps";
import App from "./App";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const run = {
  id: "run-0001",
  status: "succeeded",
  started_at: "2026-11-15T12:00:00Z",
  seconds: 1.2,
  snapshot_id: "new-0001",
  requested: 5,
  received: 5,
  valid: 4,
  rejected: 1,
  warnings: 3,
  error_code: null,
  provenance: { release: "2026-11-12" },
};
const version = {
  id: "new-0001",
  created_at: run.started_at,
  checksum: "a".repeat(64),
  received: 5,
  valid: 4,
  rejected: 1,
  warnings: 3,
  scope: { max_rows: 5 },
  policy: "cms-registry-v1",
  provenance: {},
};
const page = (items: unknown[]) => ({
  items,
  total: items.length,
  page: 1,
  page_size: 10,
});
function setup(empty = false) {
  const fetch = vi.fn(async (url: string) => ({
    ok: true,
    json: async () => {
      if (url.includes("/dataops/status"))
        return {
          sources: [],
          latest_attempt: empty ? null : run,
          latest_success: empty ? null : run,
          snapshot_count: empty ? 0 : 2,
        };
      if (url.includes("/findings"))
        return page([
          {
            row_number: 4,
            severity: "error",
            code: "invalid_identifier",
            field: "npi",
          },
        ]);
      if (url.includes("/records"))
        return page([
          {
            row_number: 1,
            record_key: "hash",
            accepted: true,
            data: {
              npi: "1000000000",
              ind_enrl_id: "I20200101000001",
              adrs_id: "LOCATION_A",
              org_pac_id: "",
              pri_spec: "CARDIOLOGY",
              citytown: "AUSTIN",
              state: "TX",
            },
          },
        ]);
      if (url.includes("/dataops/versions"))
        return page(empty ? [] : [version, { ...version, id: "old-0001" }]);
      if (url.includes("/dataops/runs")) return page(empty ? [] : [run]);
      if (url.includes("/dataops/compare"))
        return {
          added: 1,
          removed: 1,
          changed: 1,
          unchanged: 2,
          specialty_changes: 1,
          location_changes: 1,
          validation_delta: { missing_optional: -3 },
          caveat: "Bounded samples only",
          examples: [],
          examples_truncated: false,
        };
      return {
        providers: 0,
        encounters: 0,
        scored: 0,
        mean_score: null,
        specialties: [],
        distribution: [],
        locations: [],
        latest_run: null,
        last_success: null,
      };
    },
  }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
it("explains the empty live workspace and CLI-only initiation", async () => {
  setup(true);
  render(<DataOps />);
  expect(
    await screen.findByText(/No live CMS ingestion yet/),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /start ingestion/i }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText(/never joined to the synthetic ranking system/),
  ).toBeInTheDocument();
});
it("separates fixture requests and labels them as test records", async () => {
  const fetch = setup();
  render(<DataOps />);
  fireEvent.change(screen.getByLabelText("Data source mode"), {
    target: { value: "fixture" },
  });
  expect(
    await screen.findByText(/these are artificial test records/),
  ).toBeInTheDocument();
  expect(
    fetch.mock.calls.some(([u]) => u.includes("status?mode=fixture")),
  ).toBe(true);
});
it("shows record outcomes without counting warnings as rejected rows", async () => {
  setup();
  render(<DataOps />);
  const chart = await screen.findByRole("group", {
    name: "Accepted versus rejected record counts",
  });
  expect(within(chart).getByText("4")).toBeInTheDocument();
  expect(within(chart).getByText("1")).toBeInTheDocument();
  expect(screen.getByText(/3 warning findings/)).toBeInTheDocument();
});
it("compares selected versions and explains the sampling limit", async () => {
  const fetch = setup();
  render(<DataOps />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Set older old-0001" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Set newer new-0001" }));
  expect(await screen.findByText("Bounded samples only")).toBeInTheDocument();
  expect(
    fetch.mock.calls.some(([u]) =>
      u.includes("old_id=old-0001&new_id=new-0001"),
    ),
  ).toBe(true);
  expect(
    screen.getByRole("group", {
      name: "Accepted-record changes in captured samples",
    }),
  ).toHaveTextContent("Unchanged2");
});
it("opens findings and projected source records", async () => {
  setup();
  render(<DataOps />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Inspect latest findings" }),
  );
  expect(await screen.findByText("invalid_identifier")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect version new-0001" }),
  );
  expect(await screen.findByText("1000000000")).toBeInTheDocument();
  expect(screen.queryByText("Telephone Number")).not.toBeInTheDocument();
});
it("announces loading and API failures", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Offline")));
  render(<DataOps />);
  expect(screen.getAllByRole("status")).toHaveLength(3);
  expect(await screen.findAllByRole("alert")).toHaveLength(3);
});
it("uses a public-registry disclaimer without changing synthetic pages", async () => {
  setup();
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Data operations" }));
  expect(
    await screen.findByRole("heading", { name: "Data operations" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(/All data and scores are synthetic/),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Overview" }));
  expect(
    await screen.findByText(/All data and scores are synthetic/),
  ).toBeInTheDocument();
});
