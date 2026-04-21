const { ipcMain } = require("electron");
const { getBackendUrl, requestJson } = require("./backendClient");

function registerAppsIpc() {
  ipcMain.handle("apps:list-catalog", async () => {
    try {
      const url = new URL("/apps/catalog", getBackendUrl()).toString();
      return await requestJson(url, {}, false);
    } catch (_error) {
      return { ok: false, error: "Could not reach backend app catalog." };
    }
  });

  ipcMain.handle("apps:list-installed", async () => {
    try {
      const url = new URL("/apps/installed", getBackendUrl()).toString();
      return await requestJson(url);
    } catch (_error) {
      return { ok: false, error: "Could not reach backend installed apps endpoint." };
    }
  });

  ipcMain.handle("apps:install", async (_event, payload) => {
    const appKey = String(payload?.appKey || "").trim();
    if (!appKey) {
      return { ok: false, error: "appKey is required." };
    }

    try {
      const url = new URL("/apps/install", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ app_key: appKey }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach backend app install endpoint." };
    }
  });
}

module.exports = { registerAppsIpc };
