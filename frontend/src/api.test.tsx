import { act, renderHook, waitFor, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useApi } from "./api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
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
