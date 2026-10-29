import { useCallback, useEffect, useRef, useState } from "react";

import { SessionChangedError } from "../auth/session";

export function useResource<T>(load: () => Promise<T>) {
  const mounted = useRef(true);
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await load();
      if (mounted.current) setData(result);
    } catch (caught) {
      if (mounted.current && !(caught instanceof SessionChangedError)) {
        setError(caught instanceof Error ? caught.message : "Unable to load this information.");
      }
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [load]);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => { mounted.current = false; };
  }, [refresh]);

  return { data, error, loading, refresh };
}
