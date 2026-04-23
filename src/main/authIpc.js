const { ipcMain } = require("electron");
const { getBackendUrl, requestJson } = require("./backendClient");
const { clearAuthState, readAuthState, writeAuthState } = require("./authStore");

async function loginWithBackend(payload) {
  const loginUrl = new URL("/auth/login", getBackendUrl()).toString();
  return requestJson(
    loginUrl,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    false
  );
}

function registerAuthIpc() {
  ipcMain.handle("auth:login", async (_event, payload) => {
    const tenantId = String(payload?.tenantId || "").trim();
    const email = String(payload?.email || "").trim().toLowerCase();
    const password = String(payload?.password || "");

    if (!tenantId || !email || !password) {
      return { ok: false, error: "Tenant, email, and password are required." };
    }

    try {
      const result = await loginWithBackend({ tenant_id: tenantId, email, password });
      if (!result.ok) {
        return result;
      }
      const nextAuthState = {
        accessToken: result.data.access_token,
        tenantId: result.data.tenant_id,
        userId: result.data.user_id,
        email: result.data.email,
        role: result.data.role,
        expiresAt: result.data.expires_at,
      };
      await writeAuthState(nextAuthState);
      return { ok: true, data: nextAuthState };
    } catch (_error) {
      return { ok: false, error: "Could not reach authentication service at http://127.0.0.1:8000." };
    }
  });

  ipcMain.handle("auth:get-session", async () => {
    return readAuthState();
  });

  ipcMain.handle("auth:logout", async () => {
    try {
      const logoutUrl = new URL("/auth/logout", getBackendUrl()).toString();
      await requestJson(logoutUrl, { method: "POST" });
    } catch (_error) {
    }
    await clearAuthState();
    return { ok: true };
  });
}

module.exports = { registerAuthIpc, loginWithBackend };
