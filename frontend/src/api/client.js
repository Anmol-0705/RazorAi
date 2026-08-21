import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const http = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
});

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
};

export default api;
