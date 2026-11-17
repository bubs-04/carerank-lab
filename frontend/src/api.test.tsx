import { act, renderHook, waitFor, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useApi } from "./api";
import { SESSION_EXPIRED } from "./Auth";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("does not expire the current session when an aborted old request returns 401", async () => {
  let finishOld!: (value: Response) => void;
  const oldResponse = new Promise<Response>((resolve) => {
    finishOld = resolve;
  });
  const expired = vi.fn();
  window.addEventListener(SESSION_EXPIRED, expired);
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockReturnValueOnce(oldResponse)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ name: "current" }), { status: 200 }),
      ),
  );
  try {
    const { result, rerender } = renderHook(
      ({ url }) => useApi<{ name: string }>(url),
      { initialProps: { url: "/old-session" } },
    );
    rerender({ url: "/current-session" });
    await waitFor(() => expect(result.current.data?.name).toBe("current"));
    await act(async () => {
      finishOld(
        new Response(JSON.stringify({ detail: "expired" }), { status: 401 }),
      );
    });
    expect(expired).not.toHaveBeenCalled();
    expect(result.current.data?.name).toBe("current");
  } finally {
    window.removeEventListener(SESSION_EXPIRED, expired);
  }
});

it("keeps the newest result when an old response body finishes late", async () => {
  let finishOld!: (value: { name: string }) => void;
  const oldBody = new Promise((resolve) => {
    finishOld = resolve;
  });
  const oldJson = vi.fn(() => oldBody);
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: oldJson })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ name: "new" }) }),
  );
  const { result, rerender } = renderHook(
    ({ url }) => useApi<{ name: string }>(url),
    {
      initialProps: { url: "/old" },
    },
  );
  await waitFor(() => expect(oldJson).toHaveBeenCalled());
  rerender({ url: "/new" });
  await waitFor(() => expect(result.current.data?.name).toBe("new"));
  await act(async () => {
    finishOld({ name: "old" });
  });
  expect(result.current.data?.name).toBe("new");
});
