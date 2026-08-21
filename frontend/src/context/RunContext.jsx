import { createContext, useContext, useEffect, useMemo, useState } from "react";
import api from "../api/client";

const STORAGE_KEY = "razorrecon.currentRun";
const RunContext = createContext(null);

function loadInitial() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : { datasetId: null, runId: null };
  } catch {
    return { datasetId: null, runId: null };
  }
}

export function RunProvider({ children }) {
  const [current, setCurrent] = useState(loadInitial);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
    } catch {
      // localStorage unavailable (e.g. private mode) - non-fatal, state still works in-memory
    }
  }, [current]);

  // On first load with no locally-remembered run, ask the backend which
  // run is most recent so a page refresh doesn't lose context.
  useEffect(() => {
    if (current.runId) return;
    let cancelled = false;
    api
      .getDashboardSummary()
      .then((summary) => {
        if (!cancelled && summary?.run_id) {
          setCurrent((c) => ({ ...c, runId: summary.run_id }));
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const value = useMemo(
    () => ({
      datasetId: current.datasetId,
      runId: current.runId,
      refreshKey,
      setDataset: (datasetId) => setCurrent((c) => ({ ...c, datasetId })),
      setRun: (runId, datasetId) =>
        setCurrent((c) => ({ datasetId: datasetId ?? c.datasetId, runId })),
      bumpRefresh: () => setRefreshKey((k) => k + 1),
    }),
    [current, refreshKey]
  );

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRunContext() {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useRunContext must be used within a RunProvider");
  return ctx;
}
