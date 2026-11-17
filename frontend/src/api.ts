import { useEffect, useState } from "react";
import { SESSION_EXPIRED } from "./Auth";
export function useApi<T>(url: string, refresh = 0) {
  const [state, setState] = useState<{
    data: T | null;
    error: string;
    loading: boolean;
  }>({ data: null, error: "", loading: true });
  useEffect(() => {
    const controller = new AbortController();
    setState({ data: null, error: "", loading: true });
    fetch(url, { signal: controller.signal })
      .then(async (r) => {
        if (r.status === 401 && !controller.signal.aborted)
          window.dispatchEvent(new Event(SESSION_EXPIRED));
        if (!r.ok) {
          const b = await r.json().catch(() => ({}));
          throw new Error(
            typeof b.detail === "string"
              ? b.detail
              : `Request failed (${r.status})`,
          );
        }
        return r.json();
      })
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ data, error: "", loading: false });
      })
      .catch((e) => {
        if (!controller.signal.aborted && e.name !== "AbortError")
          setState({ data: null, error: e.message, loading: false });
      });
    return () => controller.abort();
  }, [url, refresh]);
  return state;
}
