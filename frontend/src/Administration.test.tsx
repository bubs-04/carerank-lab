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
  revision: 1,
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
        body: JSON.stringify({
          expected_revision: 1,
          role: "viewer",
          active: false,
        }),
      }),
    ),
  );
  await waitFor(() =>
    expect(
      fetch.mock.calls.filter(([url]) => url.endsWith("/events")),
    ).toHaveLength(2),
  );
});

it("shows the last-administrator rejection and reloads account state without claiming success", async () => {
  const fetch = vi.fn(async (url: string, options?: RequestInit) =>
    response(
      options?.method === "PATCH" ? 409 : 200,
      options?.method === "PATCH"
        ? { detail: "At least one active administrator must remain" }
        : url.endsWith("/events")
          ? []
          : [{ ...administrator, active: true, revision: 1 }],
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
  await waitFor(() =>
    expect(screen.getByLabelText("Role for administrator")).toHaveValue(
      "administrator",
    ),
  );
  expect(screen.getByRole("button", { name: "Update access" })).toBeDisabled();
  expect(
    fetch.mock.calls.filter(([url]) => url.endsWith("/events")),
  ).toHaveLength(2);
});

it.each([
  ["role", { expected_revision: 1, role: "viewer" }],
  ["active", { expected_revision: 1, active: false }],
])(
  "submits only the intentionally changed %s field and the reviewed revision",
  async (field, body) => {
    const fetch = vi.fn(async (url: string, options?: RequestInit) =>
      response(
        200,
        options?.method === "PATCH"
          ? analyst
          : url.endsWith("/events")
            ? []
            : [analyst],
      ),
    );
    vi.stubGlobal("fetch", fetch);
    renderAdmin();
    await screen.findByText("Workspace Analyst");
    if (field === "role") {
      fireEvent.change(screen.getByLabelText("Role for analyst"), {
        target: { value: "viewer" },
      });
    } else {
      fireEvent.click(screen.getByLabelText("Active account analyst"));
    }
    fireEvent.click(screen.getByRole("button", { name: "Update access" }));
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        "/api/auth/users/analyst",
        expect.objectContaining({ body: JSON.stringify(body) }),
      ),
    );
  },
);

it("reloads revoked access after a stale write and requires a new intentional change at the latest revision", async () => {
  let stale = false;
  const latest = { ...analyst, role: "viewer", active: false, revision: 2 };
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    if (options?.method === "PATCH") {
      if (!stale) {
        stale = true;
        return response(409, {
          detail: "Account changed; reload its latest revision",
        });
      }
      return response(200, { ...latest, role: "analyst", revision: 3 });
    }
    return response(
      200,
      url.endsWith("/events") ? [] : [stale ? latest : analyst],
    );
  });
  vi.stubGlobal("fetch", fetch);
  renderAdmin();
  await screen.findByText("Workspace Analyst");
  fireEvent.change(screen.getByLabelText("Role for analyst"), {
    target: { value: "administrator" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Update access" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Account changed");
  await waitFor(() =>
    expect(screen.getByLabelText("Role for analyst")).toHaveValue("viewer"),
  );
  expect(screen.getByLabelText("Active account analyst")).not.toBeChecked();
  expect(screen.getByRole("button", { name: "Update access" })).toBeDisabled();
  expect(
    fetch.mock.calls.filter(([, options]) => options?.method === "PATCH"),
  ).toHaveLength(1);
  fireEvent.change(screen.getByLabelText("Role for analyst"), {
    target: { value: "analyst" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Update access" }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/auth/users/analyst",
      expect.objectContaining({
        body: JSON.stringify({ expected_revision: 2, role: "analyst" }),
      }),
    ),
  );
  expect(
    fetch.mock.calls.filter(([, options]) => options?.method === "PATCH")[0][1]
      ?.body,
  ).toBe(JSON.stringify({ expected_revision: 1, role: "administrator" }));
});

it("hides stale forms when refreshing a conflict fails", async () => {
  let stale = false;
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    if (options?.method === "PATCH") {
      stale = true;
      return response(409, {
        detail: "Account changed; reload its latest revision",
      });
    }
    return url.endsWith("/events")
      ? response(200, [])
      : stale
        ? response(503, { detail: "Account service unavailable" })
        : response(200, [analyst]);
  });
  vi.stubGlobal("fetch", fetch);
  renderAdmin();
  await screen.findByText("Workspace Analyst");
  fireEvent.click(screen.getByLabelText("Active account analyst"));
  fireEvent.click(screen.getByRole("button", { name: "Update access" }));
  await screen.findByText("Account service unavailable");
  expect(
    screen.queryByRole("button", { name: "Update access" }),
  ).not.toBeInTheDocument();
  expect(
    fetch.mock.calls.filter(([, options]) => options?.method === "PATCH"),
  ).toHaveLength(1);
});

it("shows forbidden account changes without claiming success or automatically retrying", async () => {
  const fetch = vi.fn(async (url: string, options?: RequestInit) =>
    options?.method === "PATCH"
      ? response(403, { detail: "Administrator access required" })
      : response(200, url.endsWith("/events") ? [] : [analyst]),
  );
  vi.stubGlobal("fetch", fetch);
  renderAdmin();
  await screen.findByText("Workspace Analyst");
  fireEvent.click(screen.getByLabelText("Active account analyst"));
  fireEvent.click(screen.getByRole("button", { name: "Update access" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Administrator access required",
  );
  expect(screen.getByLabelText("Active account analyst")).not.toBeChecked();
  expect(
    fetch.mock.calls.filter(([, options]) => options?.method === "PATCH"),
  ).toHaveLength(1);
  expect(
    fetch.mock.calls.filter(([url]) => url.endsWith("/events")),
  ).toHaveLength(1);
});
