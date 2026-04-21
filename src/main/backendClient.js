const { readAuthState } = require("./authStore");

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

function getBackendUrl() {
  return process.env.BACKEND_URL || DEFAULT_BACKEND_URL;
}

async function getAuthHeaders() {
  const authState = await readAuthState();
  const headers = {};
  if (authState?.accessToken) {
    headers.Authorization = `Bearer ${authState.accessToken}`;
  }
  return headers;
}

async function requestJson(url, options = {}, requireAuth = true) {
  const authHeaders = requireAuth ? await getAuthHeaders() : {};
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...authHeaders,
    },
  });

  if (!response.ok) {
    let detail = "Request failed.";
    try {
      const payload = await response.json();
      detail = payload?.detail || detail;
    } catch (_error) {
      detail = `Request failed with HTTP ${response.status}.`;
    }
    return { ok: false, error: detail };
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("text/csv")) {
    return { ok: true, data: await response.text() };
  }
  return { ok: true, data: await response.json() };
}

module.exports = {
  DEFAULT_BACKEND_URL,
  getBackendUrl,
  requestJson,
};
