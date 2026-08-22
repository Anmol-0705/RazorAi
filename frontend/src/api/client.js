import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const http = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
});

// Reconciliation/evaluation runs do real work (persisting hundreds of
// rows) against a hosted backend + database that can have real-world
// latency the default 30s doesn't budget for -- most notably a Render
// free-tier web service waking from an idle cold start, which alone
// can take 30-50s before the request is even accepted. Only these
// long-running run-triggering calls get the longer budget; every
// other endpoint (health, listing, review actions, AI) keeps the
// default 30s so a genuinely unreachable backend still fails fast.
const LONG_RUN_TIMEOUT_MS = 90000;

// Normalizes axios/network errors into a small, UI-friendly shape so
// components never have to poke at axios internals.
function toApiError(error) {
  if (error.response) {
    const detail = error.response.data?.detail;
    return {
      status: error.response.status,
      message: typeof detail === "string" ? detail : `Request failed (${error.response.status})`,
    };
  }
  if (error.code === "ECONNABORTED") {
    // The client gave up waiting -- the backend may still be
    // reachable and even still processing the request. Distinct from
    // a genuine connection failure so the user isn't told the API is
    // down when it might just be slow.
    return {
      status: 0,
      message: "The request timed out waiting for the backend. It may still be processing — please try again shortly.",
    };
  }
  if (error.request) {
    return { status: 0, message: "Could not reach the backend. Is the API running?" };
  }
  return { status: -1, message: error.message || "Unexpected error" };
}

async function request(config) {
  try {
    const response = await http.request(config);
    return response.data;
  } catch (error) {
    throw toApiError(error);
  }
}

export const api = {
  baseUrl: BASE_URL,

  getHealth: () => request({ method: "GET", url: "/health" }),

  generateDemoDataset: ({ seed, numRecords }) =>
    request({ method: "POST", url: "/datasets/demo", data: { seed, num_records: numRecords } }),

  runReconciliation: ({ datasetId, runId }) =>
    request({
      method: "POST",
      url: "/reconciliation/runs",
      data: { dataset_id: datasetId, ...(runId ? { run_id: runId } : {}) },
      timeout: LONG_RUN_TIMEOUT_MS,
    }),

  listRuns: ({ limit = 50 } = {}) =>
    request({ method: "GET", url: "/reconciliation/runs", params: { limit } }),

  getRun: (runId) => request({ method: "GET", url: `/reconciliation/runs/${runId}` }),

  getRunResults: (runId, { status } = {}) =>
    request({
      method: "GET",
      url: `/reconciliation/runs/${runId}/results`,
      params: status ? { status } : {},
    }),

  getDashboardSummary: ({ runId } = {}) =>
    request({ method: "GET", url: "/dashboard/summary", params: runId ? { run_id: runId } : {} }),

  listExceptions: ({ status, severity, exceptionType, runId, limit = 200 } = {}) =>
    request({
      method: "GET",
      url: "/exceptions",
      params: {
        ...(status ? { status } : {}),
        ...(severity ? { severity } : {}),
        ...(exceptionType ? { exception_type: exceptionType } : {}),
        ...(runId ? { run_id: runId } : {}),
        limit,
      },
    }),

  getExceptionDetail: (exceptionId) =>
    request({ method: "GET", url: `/exceptions/${exceptionId}` }),

  reviewAction: (exceptionId, action, { reviewer, note = "" }) =>
    request({
      method: "POST",
      url: `/exceptions/${exceptionId}/${action}`,
      data: { reviewer, note },
    }),

  executeControllerAction: (exceptionId) =>
    request({ method: "POST", url: `/exceptions/${exceptionId}/execute-action` }),

  explainExceptionWithAI: (exceptionId) =>
    request({ method: "POST", url: `/ai/exceptions/${exceptionId}/explain` }),

  recommendResolutionWithAI: (exceptionId) =>
    request({ method: "POST", url: `/ai/exceptions/${exceptionId}/recommend` }),

  askAIController: ({ question, runId }) =>
    request({ method: "POST", url: "/ai/query", data: { question, ...(runId ? { run_id: runId } : {}) } }),

  summarizeRunWithAI: (runId) =>
    request({ method: "POST", url: `/ai/runs/${runId}/summary` }),

  runEvaluation: ({ datasetName = "n250" } = {}) =>
    request({
      method: "POST",
      url: "/evaluation/run",
      data: { dataset_name: datasetName },
      timeout: LONG_RUN_TIMEOUT_MS,
    }),

  getLatestEvaluation: () => request({ method: "GET", url: "/evaluation/latest" }),

  runStressEvaluation: ({ datasetName = "n250" } = {}) =>
    request({
      method: "POST",
      url: "/evaluation/stress/run",
      data: { dataset_name: datasetName },
      timeout: LONG_RUN_TIMEOUT_MS,
    }),

  getLatestStressEvaluation: () => request({ method: "GET", url: "/evaluation/stress/latest" }),
};

export default api;
