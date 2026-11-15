import { useEffect, useState } from "react";
export function useApi<T>(url: string) {
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
      .then((data) => setState({ data, error: "", loading: false }))
      .catch((e) => {
        if (e.name !== "AbortError")
          setState({ data: null, error: e.message, loading: false });
      });
    return () => controller.abort();
  }, [url]);
  return state;
}
