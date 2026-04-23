const http = require("http");
const https = require("https");
const { readAuthState } = require("./authStore");

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";
const DEFAULT_FETCH_TIMEOUT_MS = 5000;
const NETWORK_RETRY_DELAYS_MS = [250, 750, 1500];
const httpAgent = new http.Agent({ keepAlive: true, maxSockets: 8 });
const httpsAgent = new https.Agent({ keepAlive: true, maxSockets: 8 });
let hasLoggedBackendUrl = false;

function getBackendUrl() {
  return process.env.BACKEND_URL || DEFAULT_BACKEND_URL;
}

function logResolvedBackendUrl(context = "request") {
  const backendUrl = getBackendUrl();
  console.log(`[backendClient] resolved backend URL (${context}): ${backendUrl}`);
  hasLoggedBackendUrl = true;
  return backendUrl;
}

async function getAuthHeaders() {
  const authState = await readAuthState();
  const headers = {};
  if (authState?.accessToken) {
    headers.Authorization = `Bearer ${authState.accessToken}`;
  }
  return headers;
}

function isRetryableNetworkError(error) {
  const code = error?.cause?.code || error?.code;
  return (
    code === "ECONNREFUSED" ||
    code === "ECONNRESET" ||
    code === "EADDRINUSE" ||
    code === "ETIMEDOUT" ||
    error?.name === "AbortError"
  );
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizeHeaders(headers = {}) {
  const normalized = {};
  for (const [key, value] of Object.entries(headers || {})) {
    if (value !== undefined && value !== null) {
      normalized[key] = value;
    }
  }
  return normalized;
}

function sendHttpRequest(url, options = {}, timeoutMs = DEFAULT_FETCH_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const transport = target.protocol === "https:" ? https : http;
    const headers = normalizeHeaders(options.headers);
    const body = options.body ?? null;

    if (body && headers["Content-Length"] === undefined && headers["content-length"] === undefined) {
      headers["Content-Length"] = Buffer.byteLength(body);
    }

    const request = transport.request(
      {
        protocol: target.protocol,
        hostname: target.hostname,
        port: target.port || (target.protocol === "https:" ? 443 : 80),
        path: `${target.pathname}${target.search}`,
        method: options.method || "GET",
        headers,
        agent: target.protocol === "https:" ? httpsAgent : httpAgent,
      },
      (response) => {
        const chunks = [];

        response.on("data", (chunk) => {
          chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
        });

        response.on("end", () => {
          resolve({
            ok: response.statusCode >= 200 && response.statusCode < 300,
            status: response.statusCode || 0,
            headers: response.headers,
            text: Buffer.concat(chunks).toString("utf8"),
          });
        });
      }
    );

    request.setTimeout(timeoutMs, () => {
      const timeoutError = new Error(`Request timed out after ${timeoutMs}ms.`);
      timeoutError.code = "ETIMEDOUT";
      request.destroy(timeoutError);
    });

    request.on("error", (error) => {
      reject(error);
    });

    if (body) {
      request.write(body);
    }
    request.end();
  });
}

async function fetchWithRetry(url, options, timeoutMs = DEFAULT_FETCH_TIMEOUT_MS) {
  let lastError = null;

  for (let attempt = 0; attempt <= NETWORK_RETRY_DELAYS_MS.length; attempt += 1) {
    try {
      return await sendHttpRequest(url, options, timeoutMs);
    } catch (error) {
      lastError = error;
      if (!isRetryableNetworkError(error) || attempt === NETWORK_RETRY_DELAYS_MS.length) {
        throw error;
      }
      await delay(NETWORK_RETRY_DELAYS_MS[attempt]);
    }
  }

  throw lastError;
}

async function requestJson(url, options = {}, requireAuth = true, requestConfig = {}) {
  if (!hasLoggedBackendUrl) {
    logResolvedBackendUrl("first-request");
  }
  const { timeoutMs = DEFAULT_FETCH_TIMEOUT_MS } = requestConfig;
  const authHeaders = requireAuth ? await getAuthHeaders() : {};
  let response;
  try {
    response = await fetchWithRetry(
      url,
      {
        ...options,
        headers: {
          ...(options.headers || {}),
          ...authHeaders,
        },
      },
      timeoutMs
    );
  } catch (error) {
    throw error;
  }

  if (!response.ok) {
    let detail = "Request failed.";
    try {
      const payload = JSON.parse(response.text || "");
      detail = payload?.detail || detail;
    } catch (_error) {
      detail = `Request failed with HTTP ${response.status}.`;
    }
    return { ok: false, error: detail };
  }

  const contentType = response.headers["content-type"] || "";
  if (contentType.includes("text/csv")) {
    return { ok: true, data: response.text };
  }
  return { ok: true, data: response.text ? JSON.parse(response.text) : null };
}

module.exports = {
  DEFAULT_BACKEND_URL,
  getBackendUrl,
  logResolvedBackendUrl,
  requestJson,
};
