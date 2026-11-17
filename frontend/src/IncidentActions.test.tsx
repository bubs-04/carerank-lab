import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AuthContext } from "./Auth";
import type { User } from "./Auth";
import IncidentActions from "./IncidentActions";

const user: User = {
  id: "user-1",
  username: "analyst",
  display_name: "Avery Analyst",
  role: "analyst",
};
const incident = {
  id: "incident-1",
  revision: 7,
  status: "open",
  assigned_to: null,
};
const response = (status: number, body: unknown = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function workspace(role: User["role"] = "analyst", current = incident) {
  const onSaved = vi.fn(),
    onReload = vi.fn();
  render(
    <AuthContext.Provider
      value={{
        user: { ...user, role },
        csrf_token: "test-csrf-token",
        logout: vi.fn(),
      }}
    >
      <IncidentActions
        incident={current}
        onSaved={onSaved}
        onReload={onReload}
      />
    </AuthContext.Provider>,
  );
  return { onSaved, onReload };
}

it("gives viewers read access without a mutation form or assignment request", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  workspace("viewer");
  expect(screen.getByText("Viewer access.")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Save decision" }),
  ).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it("submits the current revision, CSRF token, selected owner and decision without a caller-supplied actor", async () => {
  const fetch = vi.fn(async (_url: string, options?: RequestInit) =>
    response(
      200,
      options?.method ? { status: "acknowledged", revision: 8 } : [user],
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const { onSaved } = workspace();
  await screen.findByRole("option", { name: /Avery Analyst/ });
  fireEvent.change(screen.getByLabelText("Next action"), {
    target: { value: "acknowledged" },
  });
  fireEvent.change(screen.getByLabelText("Assign to"), {
    target: { value: user.id },
  });
  fireEvent.change(screen.getByLabelText("Decision note"), {
    target: { value: "  Reviewed source evidence  " },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  const call = fetch.mock.calls.find(
    ([, options]) => options?.method === "POST",
  )!;
  expect(call[0]).toBe("/api/dataops/monitoring/alerts/incident-1/actions");
  expect(call[1]).toMatchObject({
    credentials: "same-origin",
    headers: { "X-CSRF-Token": "test-csrf-token" },
  });
  expect(JSON.parse(call[1]!.body as string)).toEqual({
    expected_revision: 7,
    note: "Reviewed source evidence",
    status: "acknowledged",
    assigned_to: user.id,
  });
  expect(screen.getByLabelText("Decision note")).toHaveValue("");
});

it("rejects a whitespace-only decision before any mutation", async () => {
  const fetch = vi.fn(async () => response(200, [user]));
  vi.stubGlobal("fetch", fetch);
  const { onSaved } = workspace();
  fireEvent.change(screen.getByLabelText("Decision note"), {
    target: { value: "   " },
  });
  fireEvent.submit(
    screen.getByRole("form", { name: "Record investigation decision" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Describe the evidence",
  );
  expect(onSaved).not.toHaveBeenCalled();
  expect(fetch.mock.calls).toHaveLength(1);
});

it("retains the decision on a revision conflict and offers a reload without claiming success", async () => {
  const fetch = vi.fn(async (_url: string, options?: RequestInit) =>
    response(options?.method ? 409 : 200, options?.method ? {} : [user]),
  );
  vi.stubGlobal("fetch", fetch);
  const { onSaved, onReload } = workspace();
  fireEvent.change(screen.getByLabelText("Decision note"), {
    target: { value: "Evidence to preserve after conflict" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "changed while you were reviewing",
  );
  expect(screen.getByLabelText("Decision note")).toHaveValue(
    "Evidence to preserve after conflict",
  );
  expect(onSaved).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", { name: "Reload latest incident" }),
  );
  expect(onReload).toHaveBeenCalledOnce();
});

it("allows a note when the assignee directory fails without accidentally clearing ownership", async () => {
  const fetch = vi.fn(async (_url: string, options?: RequestInit) =>
    response(
      options?.method ? 200 : 503,
      options?.method ? {} : { detail: "Directory unavailable" },
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const { onSaved } = workspace();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unable to load assignments",
  );
  expect(screen.getByLabelText("Assign to")).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Decision note"), {
    target: { value: "Reviewed current ownership" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  const call = fetch.mock.calls.find(
    ([, options]) => options?.method === "POST",
  )!;
  expect(JSON.parse(call[1]!.body as string)).toEqual({
    expected_revision: 7,
    note: "Reviewed current ownership",
  });
});

it("offers reopen for resolved incidents and prevents duplicate submissions while saving", async () => {
  let finish!: (response: Response) => void;
  const fetch = vi.fn((_url: string, options?: RequestInit) =>
    options?.method
      ? new Promise<Response>((done) => {
          finish = done;
        })
      : Promise.resolve(response(200, [user])),
  );
  vi.stubGlobal("fetch", fetch);
  const { onSaved } = workspace("administrator", {
    ...incident,
    status: "resolved",
  });
  expect(screen.getByRole("option", { name: "Reopen incident" })).toBeVisible();
  expect(
    screen.queryByRole("option", { name: "Resolve incident" }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Next action"), {
    target: { value: "open" },
  });
  fireEvent.change(screen.getByLabelText("Decision note"), {
    target: { value: "New supporting evidence" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
  expect(
    screen.getByRole("button", { name: "Saving decision…" }),
  ).toBeDisabled();
  expect(screen.getByLabelText("Decision note")).toBeDisabled();
  finish(response(200, {}));
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
});
