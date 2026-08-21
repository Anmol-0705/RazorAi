import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Minimal data-fetching hook: runs `fn` on mount and whenever `deps`
 * change, tracks loading/error/data, and exposes `refetch` for manual
 * retries. Deliberately tiny — no cache, no global store — this app's
 * data needs don't warrant one.
 */
export function useAsync(fn, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const requestId = useRef(0);

  const run = useCallback(() => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    fn()
      .then((result) => {
        if (id === requestId.current) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (id === requestId.current) {
          setError(err);
          setLoading(false);
        }
      });
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    run();
  }, [run]);

  return { data, error, loading, refetch: run };
}
