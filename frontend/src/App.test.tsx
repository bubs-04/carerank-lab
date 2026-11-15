import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import App, { ScoreBadge } from "./App";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("does not turn insufficient evidence into zero", () => {
  render(<ScoreBadge value={null} />);
  expect(screen.getByText("Insufficient data")).toBeInTheDocument();
});
it("renders numeric scores", () => {
  render(<ScoreBadge value={62.35} />);
  expect(screen.getByText("62.4")).toBeInTheDocument();
});
it("shows errors and a synthetic disclaimer", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Offline")));
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Offline");
  expect(
    screen.getByText(/All data and scores are synthetic/),
  ).toBeInTheDocument();
});
it("opens provider search", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Offline")));
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Provider explorer" }));
  expect(
    screen.getByPlaceholderText("Search demo providers…"),
  ).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("Offline");
});
