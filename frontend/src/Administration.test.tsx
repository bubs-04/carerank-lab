import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Administration from "./Administration";
import { AuthContext } from "./Auth";

const administrator = {
  id: "admin",
  username: "administrator",
  display_name: "Workspace Administrator",
  role: "administrator" as const,
};
const analyst = {
  id: "analyst",
  username: "analyst",
  display_name: "Workspace Analyst",
  role: "analyst",
  active: true,
};
const response = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function renderAdmin() {
  render(
    <AuthContext.Provider
      value={{ user: administrator, csrf_token: "csrf-test", logout: vi.fn() }}
    >
      <Administration />
    </AuthContext.Provider>,
  );
}

it("records role and activation changes through the protected PATCH endpoint and refreshes the security audit", async () => {
  const fetch = vi.fn(async (url: string, options?: RequestInit) =>
    response(
      200,
      options?.method === "PATCH"
        ? { ...analyst, role: "viewer", active: false }
        : url.endsWith("/events")
          ? []
          : [analyst],
    ),
  );
  vi.stubGlobal("fetch", fetch);
  renderAdmin();
  await screen.findByText("Workspace Analyst");
  fireEvent.change(screen.getByLabelText("Role for analyst"), {
    target: { value: "viewer" },
  });
  fireEvent.click(screen.getByLabelText("Active account analyst"));
  fireEvent.click(screen.getByRole("button", { name: "Update access" }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/auth/users/analyst",
      expect.objectContaining({
        method: "PATCH",
        credentials: "same-origin",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-test" }),
        body: JSON.stringify({ role: "viewer", active: false }),
      }),
    ),
  );
  await waitFor(() =>
    expect(
      fetch.mock.calls.filter(([url]) => url.endsWith("/events")),
    ).toHaveLength(2),
  );
});

it("shows a rejected account change and retains the user's selections without claiming success", async () => {
  const fetch = vi.fn(async (url: string, options?: RequestInit) =>
    response(
      options?.method === "PATCH" ? 409 : 200,
      options?.method === "PATCH"
        ? { detail: "At least one active administrator must remain" }
        : url.endsWith("/events")
          ? []
          : [{ ...administrator, active: true }],
    ),
  );
  vi.stubGlobal("fetch", fetch);
  renderAdmin();
  await screen.findByText("Workspace Administrator");
  fireEvent.change(screen.getByLabelText("Role for administrator"), {
    target: { value: "viewer" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Update access" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "At least one active administrator",
  );
  expect(screen.getByLabelText("Role for administrator")).toHaveValue("viewer");
  expect(
    fetch.mock.calls.filter(([url]) => url.endsWith("/events")),
  ).toHaveLength(1);
});
