const { BrowserWindow, ipcMain } = require("electron");
const path = require("path");

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

function getBackendUrl() {
  return process.env.BACKEND_URL || DEFAULT_BACKEND_URL;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = "Request failed.";
    try {
      const payload = await response.json();
      detail = payload?.detail || detail;
    } catch (_error) {
      detail = "Request failed with HTTP " + response.status + ".";
    }
    return { ok: false, error: detail };
  }
  return { ok: true, data: await response.json() };
}

let chatWindow = null;

function registerChatIpc(loadRendererWindow) {
  ipcMain.handle("window:open-chat", async (_event, payload) => {
    if (chatWindow && !chatWindow.isDestroyed()) {
      if (chatWindow.isMinimized()) chatWindow.restore();
      chatWindow.focus();
      return { ok: true };
    }

    chatWindow = new BrowserWindow({
      width: 420,
      height: 640,
      minWidth: 360,
      minHeight: 520,
      webPreferences: {
        preload: path.join(__dirname, "preload.js"),
        contextIsolation: true,
        nodeIntegration: false,
      },
    });

    chatWindow.on("closed", () => {
      chatWindow = null;
    });

    loadRendererWindow(chatWindow, "chat", {
      tenantId: payload?.tenantId,
      businessName: payload?.businessName,
      userEmail: payload?.userEmail,
      userId: payload?.userId,
    });

    return { ok: true };
  });

  ipcMain.handle("chat:list-users", async (_event, tenantId) => {
    const normalizedTenantId = String(tenantId || "").trim();
    if (!normalizedTenantId) {
      return { ok: false, error: "tenantId is required." };
    }

    try {
      const url = new URL("/users", getBackendUrl());
      url.searchParams.set("tenant_id", normalizedTenantId);
      return await requestJson(url.toString());
    } catch (_error) {
      return { ok: false, error: "Could not reach backend users endpoint." };
    }
  });

  ipcMain.handle("chat:list-messages", async (_event, payload) => {
    const tenantId = String(payload?.tenantId || "").trim();
    const userId = Number(payload?.userId);
    const withUserId = Number(payload?.withUserId);

    if (!tenantId || !Number.isInteger(userId) || !Number.isInteger(withUserId)) {
      return { ok: false, error: "tenantId, userId, and withUserId are required." };
    }

    try {
      const url = new URL("/chat/messages", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          user_id: userId,
          with_user_id: withUserId,
        }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach backend chat messages endpoint." };
    }
  });

  ipcMain.handle("chat:send-message", async (_event, payload) => {
    const tenantId = String(payload?.tenantId || "").trim();
    const fromUserId = Number(payload?.fromUserId);
    const toUserId = Number(payload?.toUserId);
    const text = String(payload?.text || "").trim();

    if (!tenantId || !Number.isInteger(fromUserId) || !Number.isInteger(toUserId) || !text) {
      return { ok: false, error: "tenantId, fromUserId, toUserId, and text are required." };
    }

    try {
      const url = new URL("/chat/send", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          from_user_id: fromUserId,
          to_user_id: toUserId,
          text,
        }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach backend chat send endpoint." };
    }
  });
}

module.exports = { registerChatIpc };