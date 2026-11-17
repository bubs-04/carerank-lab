import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { test, expect, vi } from "vitest";
import App from "./App";
import { AuthProvider } from "./Auth";
const live = process.env.LIVE_URL;
test.skipIf(!live)(
  "live React to Vite proxy to FastAPI to PostgreSQL workflow",
  async () => {
    const actualFetch = globalThis.fetch;
    const username = process.env.E2E_VIEWER_USERNAME;
    const password = process.env.E2E_VIEWER_PASSWORD;
    if (!username || !password)
      throw new Error(
        "Provision E2E viewer credentials before running LIVE_URL tests",
      );
    const origin = new URL(live!).origin;
    const login = await actualFetch(`${live}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: origin },
      body: JSON.stringify({ username, password }),
    });
    expect(login.status).toBe(200);
    const session = await login.json();
    const cookie = login.headers.get("set-cookie")?.split(";")[0];
    expect(cookie).toMatch(/^carerank_session=/);
    vi.stubGlobal("fetch", (url: string, options?: RequestInit) => {
      const headers = new Headers(options?.headers);
      headers.set("Cookie", cookie!);
      headers.set("Origin", origin);
      return actualFetch(live + url, { ...options, headers });
    });
    try {
      render(
        <AuthProvider>
          <App />
        </AuthProvider>,
      );
      // Real session restoration and the subsequent analytics request are two
      // network round trips; retain the content assertion with a bounded wait.
      await screen.findByText(
        "Provider intelligence, explained.",
        {},
        { timeout: 10000 },
      );
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
      const logout = await actualFetch(`${live}/api/auth/logout`, {
        method: "POST",
        headers: {
          Cookie: cookie!,
          Origin: origin,
          "X-CSRF-Token": session.csrf_token,
        },
      });
      expect(logout.status).toBe(204);
    }
  },
  20000,
);
