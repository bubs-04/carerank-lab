import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import AnalyticsPage, {
  Scatter,
  EvidenceCharts,
  ComparisonChart,
  type Cohort,
} from "./Analytics";
import App from "./App";
import type { Provider } from "./types";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const cohort: Cohort = {
  specialty: "Cardiology",
  count: 2,
  mean_cost: 150,
  mean_score: 60,
  items: [
    { id: 1, name: "Alpha", quality: 70, avg_cost: 100, highlighted: true },
    { id: 2, name: "Beta", quality: 50, avg_cost: 200, highlighted: false },
  ],
};
const evidence = {
  total: 2,
  specialties: [
    {
      specialty: "Cardiology",
      eligible: 1,
      insufficient_outcomes: 1,
      low_completeness: 0,
      not_processed: 0,
    },
  ],
  completeness: [
    { name: "80–100%", count: 1 },
    { name: "No encounters", count: 1 },
  ],
};
function setupFetch() {
  const fetch = vi.fn(async (url: string) => ({
    ok: true,
    json: async () =>
      url.includes("quality-cost")
        ? url.includes("Neurology")
          ? { ...cohort, specialty: "Neurology", items: [], count: 0 }
          : cohort
        : url.endsWith("evidence")
          ? evidence
          : {
              specialties: [
                { name: "Cardiology", count: 2 },
                { name: "Neurology", count: 1 },
              ],
              providers: 3,
              encounters: 40,
              scored: 1,
              mean_score: 70,
              distribution: [],
              locations: [],
              latest_run: null,
              last_success: null,
            },
  }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
it("supports hover, focus, keyboard and table profile navigation", () => {
  const open = vi.fn();
  render(<Scatter data={cohort} open={open} />);
  const point = screen.getByRole("button", { name: /Open Alpha/ });
  fireEvent.mouseEnter(point);
  expect(screen.getByRole("status")).toHaveTextContent("Score 70.00");
  fireEvent.focus(point);
  expect(screen.getByRole("status")).toHaveTextContent("$100.00");
  fireEvent.keyDown(point, { key: "Enter" });
  expect(open).toHaveBeenLastCalledWith([1]);
  fireEvent.click(screen.getByRole("button", { name: /Open Beta/ }));
  expect(open).toHaveBeenLastCalledWith([2]);
  fireEvent.click(screen.getByText(/Accessible data table/));
  fireEvent.click(screen.getByRole("button", { name: "Alpha" }));
  expect(open).toHaveBeenLastCalledWith([1]);
});
it("renders every eligible provider beyond search page boundaries", () => {
  const items = Array.from({ length: 105 }, (_, i) => ({
    ...cohort.items[0],
    id: i,
    name: `Provider ${i}`,
  }));
  render(<Scatter data={{ ...cohort, count: 105, items }} open={vi.fn()} />);
  expect(screen.getAllByRole("button", { name: /Open Provider/ })).toHaveLength(
    105,
  );
});
it("loads Cardiology then requests selected specialty and handles empty cohort", async () => {
  const fetch = setupFetch();
  render(<AnalyticsPage open={vi.fn()} />);
  expect(
    await screen.findByText(/2 eligible providers · complete/),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Comparable specialty"), {
    target: { value: "Neurology" },
  });
  expect(
    await screen.findByText(/No eligible providers in this specialty/),
  ).toBeInTheDocument();
  expect(
    fetch.mock.calls.some(
      ([url]) => url === "/api/analytics/quality-cost?specialty=Neurology",
    ),
  ).toBe(true);
});
it("shows loading and independent errors", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Offline")));
  render(<AnalyticsPage open={vi.fn()} />);
  expect(screen.getAllByRole("status")).toHaveLength(2);
  expect((await screen.findAllByRole("alert")).length).toBe(3);
});
it("labels disjoint exclusion categories and undefined completeness", () => {
  render(<EvidenceCharts data={evidence} />);
  expect(screen.getByText(/takes precedence/)).toBeInTheDocument();
  expect(screen.getByText("No encounters")).toBeInTheDocument();
  expect(screen.getByRole("img")).toHaveAccessibleName(
    /Eligible: 1; Fewer than 30 observed: 1/,
  );
});
it("handles an empty evidence dataset", () => {
  render(
    <EvidenceCharts data={{ total: 0, specialties: [], completeness: [] }} />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("No providers yet");
});
it("shows weighted components without converting unscored providers to zero", () => {
  const p = {
    id: 1,
    name: "Alpha",
    quality: null,
    components: { outcome: 50, cost: 60, reliability: 40, volume: 20 },
  } as Provider;
  render(
    <ComparisonChart
      providers={[p, { ...p, id: 2, name: "Beta", quality: 60 }]}
    />,
  );
  expect(screen.getByText("Alpha (unscored)")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Outcome · 60%" }),
  ).toBeInTheDocument();
  expect(
    within(screen.getByRole("table")).getAllByText("50.00 → 30.00"),
  ).toHaveLength(2);
});
it("opens Analytics through existing application navigation", async () => {
  setupFetch();
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Analytics" }));
  expect(
    await screen.findByRole("button", { name: /Open Alpha/ }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Analytics" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(
    screen.getByRole("button", { name: "Provider explorer" }),
  ).not.toHaveAttribute("aria-current");
});
