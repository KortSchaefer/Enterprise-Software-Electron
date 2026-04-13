const { BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const { getBackendUrl, requestJson } = require("./backendClient");
const { readAuthState } = require("./authStore");

let chatWindow = null;

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

  ipcMain.handle("chat:list-users", async () => {
    try {
      const url = new URL("/users", getBackendUrl()).toString();
      return await requestJson(url);
    } catch (_error) {
      return { ok: false, error: "Could not reach backend users endpoint." };
    }
  });

  ipcMain.handle("chat:list-messages", async (_event, payload) => {
    const withUserId = Number(payload?.withUserId);
    if (!Number.isInteger(withUserId)) {
      return { ok: false, error: "withUserId is required." };
    }

    try {
      const url = new URL("/chat/messages", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ with_user_id: withUserId }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach backend chat messages endpoint." };
    }
  });

  ipcMain.handle("chat:send-message", async (_event, payload) => {
    const toUserId = Number(payload?.toUserId);
    const text = String(payload?.text || "").trim();
    if (!Number.isInteger(toUserId) || !text) {
      return { ok: false, error: "toUserId and text are required." };
    }

    try {
      const url = new URL("/chat/send", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to_user_id: toUserId, text }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach backend chat send endpoint." };
    }
  });
}

module.exports = { registerChatIpc };
