import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AuthProvider, authenticatedMutation, SESSION_EXPIRED } from "./Auth";

const session = {
  user: {
    id: "user-1",
    username: "analyst",
    display_name: "Avery Analyst",
    role: "analyst",
  },
  csrf_token: "test-csrf-token",
};
const response = (status: number, body: unknown = {}) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("keeps protected content unmounted until the server confirms the session", async () => {
  let resolve!: (value: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    ),
  );
  render(
    <AuthProvider>
      <p>Protected workspace</p>
    </AuthProvider>,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Checking your session");
  expect(screen.queryByText("Protected workspace")).not.toBeInTheDocument();
  await act(async () => resolve(response(401)));
  expect(
    await screen.findByRole("heading", { name: "Sign in to CareRank" }),
  ).toBeVisible();
  expect(screen.queryByText("Protected workspace")).not.toBeInTheDocument();
});

it("signs in through the server and revokes the session with its CSRF token on logout", async () => {
  const fetch = vi.fn(async (url: string, _options?: RequestInit) =>
    response(
      url.endsWith("/me") ? 401 : url.endsWith("/logout") ? 204 : 200,
      session,
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <AuthProvider>
      <p>Protected workspace</p>
    </AuthProvider>,
  );
  await screen.findByRole("heading", { name: "Sign in to CareRank" });
  fireEvent.change(screen.getByLabelText("Username"), {
    target: { value: "analyst" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "test-only-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("Protected workspace")).toBeVisible();
  expect(screen.getByText("Avery Analyst")).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    "/api/auth/login",
    expect.objectContaining({
      method: "POST",
      credentials: "same-origin",
      body: JSON.stringify({
        username: "analyst",
        password: "test-only-password",
      }),
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await screen.findByRole("heading", { name: "Sign in to CareRank" });
  expect(fetch).toHaveBeenCalledWith(
    "/api/auth/logout",
    expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ "X-CSRF-Token": session.csrf_token }),
    }),
  );
  expect(screen.queryByText("Protected workspace")).not.toBeInTheDocument();
});

it("clears a rejected password and presents rate limiting without exposing protected content", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => response(url.endsWith("/me") ? 401 : 429)),
  );
  render(
    <AuthProvider>
      <p>Protected workspace</p>
    </AuthProvider>,
  );
  await screen.findByRole("heading", { name: "Sign in to CareRank" });
  fireEvent.change(screen.getByLabelText("Username"), {
    target: { value: "analyst" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "test-only-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Too many attempts",
  );
  expect(screen.getByLabelText("Password")).toHaveValue("");
  expect(screen.queryByText("Protected workspace")).not.toBeInTheDocument();
});

it("removes protected content immediately when an API reports session expiry", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      response(
        url.endsWith("/me") ? 200 : 401,
        url.endsWith("/me") ? session : { detail: "Sign in to continue" },
      ),
    ),
  );
  render(
    <AuthProvider>
      <p>Protected workspace</p>
    </AuthProvider>,
  );
  await screen.findByText("Protected workspace");
  await act(async () => {
    await expect(
      authenticatedMutation("/api/protected", session.csrf_token, {}),
    ).rejects.toThrow("Sign in to continue");
  });
  expect(
    await screen.findByRole("heading", { name: "Sign in to CareRank" }),
  ).toBeVisible();
  expect(screen.getByRole("status")).toHaveTextContent("Your session expired");
  expect(screen.queryByText("Protected workspace")).not.toBeInTheDocument();
});

it("provides a retry for a session service outage instead of treating it as signed in", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(response(503))
    .mockResolvedValueOnce(response(200, session));
  vi.stubGlobal("fetch", fetch);
  render(
    <AuthProvider>
      <p>Protected workspace</p>
    </AuthProvider>,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "sign-in service is unavailable",
  );
  expect(screen.queryByText("Protected workspace")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Protected workspace")).toBeVisible();
});

it("retains the session and allows a retry when logout fails", async () => {
  const fetch = vi.fn(async (url: string) =>
    response(
      url.endsWith("/me") ? 200 : 503,
      url.endsWith("/me") ? session : { detail: "Temporarily unavailable" },
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <AuthProvider>
      <p>Protected workspace</p>
    </AuthProvider>,
  );
  await screen.findByText("Protected workspace");
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Temporarily unavailable",
  );
  expect(screen.getByText("Protected workspace")).toBeVisible();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Sign out" })).toBeEnabled(),
  );
});

it("handles an expiration notification without persisting bearer credentials in browser storage", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response(200, session)),
  );
  const localSet = vi.spyOn(Storage.prototype, "setItem");
  render(
    <AuthProvider>
      <p>Protected workspace</p>
    </AuthProvider>,
  );
  await screen.findByText("Protected workspace");
  act(() => window.dispatchEvent(new Event(SESSION_EXPIRED)));
  await screen.findByRole("heading", { name: "Sign in to CareRank" });
  expect(localSet).not.toHaveBeenCalled();
  localSet.mockRestore();
});
