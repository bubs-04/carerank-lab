import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { test, expect, vi } from "vitest";
import App from "./App";
const live = process.env.LIVE_URL;
test.skipIf(!live)(
  "live React to Vite proxy to FastAPI to PostgreSQL workflow",
  async () => {
    const actualFetch = globalThis.fetch;
    vi.stubGlobal("fetch", (url: string, options: RequestInit) =>
      actualFetch(live + url, options),
    );
    try {
      render(<App />);
      await screen.findByText("Provider intelligence, explained.");
      expect(screen.getByText("100,000")).toBeInTheDocument();
      fireEvent.click(
        screen.getByRole("button", { name: "Explore providers" }),
      );
      await waitFor(() =>
        expect(screen.getByLabelText("Specialty")).toHaveTextContent(
          "Cardiology",
        ),
      );
      fireEvent.change(screen.getByLabelText("Specialty"), {
        target: { value: "Cardiology" },
      });
      await waitFor(() =>
        expect(screen.getAllByRole("checkbox")).toHaveLength(12),
      );
      await waitFor(() =>
        expect(
          screen.getByText("200", { selector: ".count" }),
        ).toBeInTheDocument(),
      );
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      await screen.findByText("Page 2 of 17");
      fireEvent.click(screen.getByRole("button", { name: "Previous" }));
      await screen.findByText("Page 1 of 17");
      fireEvent.click(screen.getAllByRole("checkbox")[0]);
      fireEvent.click(screen.getAllByRole("checkbox")[1]);
      fireEvent.click(screen.getByRole("button", { name: "Compare (2)" }));
      await screen.findByRole("heading", { name: "Provider comparison" });
      await waitFor(() =>
        expect(screen.getAllByText("Score breakdown")).toHaveLength(2),
      );
      fireEvent.click(
        screen.getByRole("button", { name: "Back to providers" }),
      );
      fireEvent.change(screen.getByPlaceholderText("Search demo providers…"), {
        target: { value: "Demo Provider 0001" },
      });
      fireEvent.click(
        await screen.findByRole("button", {
          name: "Demo Provider 0001",
        }),
      );
      await screen.findByText("Score breakdown");
      expect(
        screen.getByRole("heading", { name: "Provider profile" }),
      ).toBeInTheDocument();
    } finally {
      cleanup();
      vi.unstubAllGlobals();
    }
  },
  20000,
);
