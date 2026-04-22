const { BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const { getBackendUrl, requestJson } = require("./backendClient");
const { readAuthState } = require("./authStore");

let chatWindow = null;
const CHAT_REQUEST_TIMEOUT_MS = 20000;

function describeUnexpectedError(error, fallbackMessage) {
  if (error?.message) {
    return `${fallbackMessage} ${error.message}`;
  }
  return fallbackMessage;
}

function logChatIpcError(operation, error) {
  console.error(`[chatIpc] ${operation} failed`, error);
}

function registerChatIpc(loadRendererWindow) {
  ipcMain.handle("window:open-chat", async () => {
    const authState = await readAuthState();
    if (!authState?.accessToken) {
      return { ok: false, error: "You must be signed in to open chat." };
    }

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
      tenantId: authState.tenantId,
      userEmail: authState.email,
      userId: authState.userId,
    });

    return { ok: true };
  });

  ipcMain.handle("chat:list-conversations", async () => {
    try {
      const url = new URL("/chat/conversations", getBackendUrl()).toString();
      return await requestJson(url, {}, true, { timeoutMs: CHAT_REQUEST_TIMEOUT_MS });
    } catch (error) {
      logChatIpcError("list-conversations", error);
      return {
        ok: false,
        error: describeUnexpectedError(error, "Could not reach backend chat conversations endpoint."),
      };
    }
  });

  ipcMain.handle("chat:get-messages", async (_event, payload) => {
    const withUserId = Number(payload?.withUserId);
    const limit = Number(payload?.limit) || 40;
    const before = String(payload?.before || "").trim();
    if (!Number.isInteger(withUserId)) {
      return { ok: false, error: "withUserId is required." };
    }

    try {
      const url = new URL(`/chat/conversations/${withUserId}/messages`, getBackendUrl());
      url.searchParams.set("limit", String(limit));
      if (before) {
        url.searchParams.set("before", before);
      }
      return await requestJson(url.toString(), {}, true, { timeoutMs: CHAT_REQUEST_TIMEOUT_MS });
    } catch (error) {
      logChatIpcError(`get-messages withUserId=${withUserId}`, error);
      return {
        ok: false,
        error: describeUnexpectedError(error, "Could not reach backend chat messages endpoint."),
      };
    }
  });

  ipcMain.handle("chat:send-message", async (_event, payload) => {
    const toUserId = Number(payload?.toUserId);
    const text = String(payload?.text || "").trim();
    if (!Number.isInteger(toUserId) || !text) {
      return { ok: false, error: "toUserId and text are required." };
    }

    try {
      const url = new URL("/chat/messages", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to_user_id: toUserId, text }),
      }, true, { timeoutMs: CHAT_REQUEST_TIMEOUT_MS });
    } catch (error) {
      logChatIpcError(`send-message toUserId=${toUserId}`, error);
      return {
        ok: false,
        error: describeUnexpectedError(error, "Could not reach backend chat send endpoint."),
      };
    }
  });

  ipcMain.handle("chat:mark-read", async (_event, payload) => {
    const withUserId = Number(payload?.withUserId);
    if (!Number.isInteger(withUserId)) {
      return { ok: false, error: "withUserId is required." };
    }

    try {
      const url = new URL(`/chat/conversations/${withUserId}/read`, getBackendUrl()).toString();
      return await requestJson(url, { method: "POST" }, true, { timeoutMs: CHAT_REQUEST_TIMEOUT_MS });
    } catch (error) {
      logChatIpcError(`mark-read withUserId=${withUserId}`, error);
      return {
        ok: false,
        error: describeUnexpectedError(error, "Could not reach backend chat read endpoint."),
      };
    }
  });

  ipcMain.handle("chat:get-stream-url", async () => {
    const authState = await readAuthState();
    if (!authState?.accessToken) {
      return { ok: false, error: "You must be signed in to subscribe to chat events." };
    }

    const url = new URL("/chat/events/stream", getBackendUrl());
    url.searchParams.set("access_token", authState.accessToken);
    return { ok: true, data: { url: url.toString() } };
  });
}

module.exports = { registerChatIpc };
