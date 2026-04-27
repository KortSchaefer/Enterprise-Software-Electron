const { BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const { getBackendUrl, requestJson } = require("./backendClient");
const { readAuthState } = require("./authStore");
const { readBootstrapState } = require("./bootstrapStore");

let posWindow = null;
const POS_REQUEST_TIMEOUT_MS = 20000;

function describeUnexpectedError(error, fallbackMessage) {
  if (error?.message) {
    return `${fallbackMessage} ${error.message}`;
  }
  return fallbackMessage;
}

function logPosIpcError(operation, error) {
  console.error(`[posIpc] ${operation} failed`, error);
}

function registerPosIpc(loadRendererWindow) {
  ipcMain.handle("window:open-pos", async () => {
    const authState = await readAuthState();
    const bootstrapState = await readBootstrapState();
    if (!authState?.accessToken) {
      return { ok: false, error: "You must be signed in to open POS." };
    }

    if (posWindow && !posWindow.isDestroyed()) {
      if (posWindow.isMinimized()) posWindow.restore();
      posWindow.focus();
      return { ok: true };
    }

    posWindow = new BrowserWindow({
      width: 1440,
      height: 900,
      minWidth: 1200,
      minHeight: 760,
      webPreferences: {
        preload: path.join(__dirname, "preload.js"),
        contextIsolation: true,
        nodeIntegration: false,
      },
    });

    posWindow.on("closed", () => {
      posWindow = null;
    });

    loadRendererWindow(posWindow, "pos", {
      tenantId: authState.tenantId,
      businessName: bootstrapState?.businessName || authState.tenantId,
      userEmail: authState.email,
      userId: authState.userId,
    });

    return { ok: true };
  });

  ipcMain.handle("pos:get-board", async () => {
    try {
      const url = new URL("/pos/board", getBackendUrl()).toString();
      return await requestJson(url, {}, true, { timeoutMs: POS_REQUEST_TIMEOUT_MS });
    } catch (error) {
      logPosIpcError("get-board", error);
      return { ok: false, error: describeUnexpectedError(error, "Could not reach POS board endpoint.") };
    }
  });

  ipcMain.handle("pos:create-table", async (_event, payload) => {
    try {
      const url = new URL("/pos/tables", getBackendUrl()).toString();
      return await requestJson(
        url,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            table_number: String(payload?.tableNumber || "").trim(),
            guest_count: Number(payload?.guestCount) || 1,
          }),
        },
        true,
        { timeoutMs: POS_REQUEST_TIMEOUT_MS }
      );
    } catch (error) {
      logPosIpcError("create-table", error);
      return { ok: false, error: describeUnexpectedError(error, "Could not reach POS table create endpoint.") };
    }
  });

  ipcMain.handle("pos:get-menu", async () => {
    try {
      const url = new URL("/pos/menu", getBackendUrl()).toString();
      return await requestJson(url, {}, true, { timeoutMs: POS_REQUEST_TIMEOUT_MS });
    } catch (error) {
      logPosIpcError("get-menu", error);
      return { ok: false, error: describeUnexpectedError(error, "Could not reach POS menu endpoint.") };
    }
  });

  ipcMain.handle("pos:get-table-detail", async (_event, payload) => {
    try {
      const tableId = Number(payload?.tableId);
      const url = new URL(`/pos/tables/${tableId}`, getBackendUrl()).toString();
      return await requestJson(url, {}, true, { timeoutMs: POS_REQUEST_TIMEOUT_MS });
    } catch (error) {
      logPosIpcError("get-table-detail", error);
      return { ok: false, error: describeUnexpectedError(error, "Could not reach POS table detail endpoint.") };
    }
  });

  ipcMain.handle("pos:add-item", async (_event, payload) => {
    try {
      const tableId = Number(payload?.tableId);
      const url = new URL(`/pos/tables/${tableId}/items`, getBackendUrl()).toString();
      return await requestJson(
        url,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            menu_item_id: Number(payload?.menuItemId),
            quantity: Number(payload?.quantity) || 1,
            course: String(payload?.course || "").trim() || null,
            seat_label: String(payload?.seatLabel || "").trim() || null,
          }),
        },
        true,
        { timeoutMs: POS_REQUEST_TIMEOUT_MS }
      );
    } catch (error) {
      logPosIpcError("add-item", error);
      return { ok: false, error: describeUnexpectedError(error, "Could not reach POS add item endpoint.") };
    }
  });

  ipcMain.handle("pos:update-item", async (_event, payload) => {
    try {
      const tableId = Number(payload?.tableId);
      const ticketItemId = Number(payload?.ticketItemId);
      const url = new URL(`/pos/tables/${tableId}/items/${ticketItemId}`, getBackendUrl()).toString();
      return await requestJson(
        url,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ quantity: Number(payload?.quantity) || 1 }),
        },
        true,
        { timeoutMs: POS_REQUEST_TIMEOUT_MS }
      );
    } catch (error) {
      logPosIpcError("update-item", error);
      return { ok: false, error: describeUnexpectedError(error, "Could not reach POS update item endpoint.") };
    }
  });

  ipcMain.handle("pos:remove-item", async (_event, payload) => {
    try {
      const tableId = Number(payload?.tableId);
      const ticketItemId = Number(payload?.ticketItemId);
      const url = new URL(`/pos/tables/${tableId}/items/${ticketItemId}`, getBackendUrl()).toString();
      return await requestJson(url, { method: "DELETE" }, true, { timeoutMs: POS_REQUEST_TIMEOUT_MS });
    } catch (error) {
      logPosIpcError("remove-item", error);
      return { ok: false, error: describeUnexpectedError(error, "Could not reach POS remove item endpoint.") };
    }
  });

  ipcMain.handle("pos:update-status", async (_event, payload) => {
    try {
      const tableId = Number(payload?.tableId);
      const url = new URL(`/pos/tables/${tableId}/status`, getBackendUrl()).toString();
      return await requestJson(
        url,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status: String(payload?.status || "").trim(),
            guest_count: payload?.guestCount ?? null,
          }),
        },
        true,
        { timeoutMs: POS_REQUEST_TIMEOUT_MS }
      );
    } catch (error) {
      logPosIpcError("update-status", error);
      return { ok: false, error: describeUnexpectedError(error, "Could not reach POS status endpoint.") };
    }
  });

  ipcMain.handle("pos:print-ticket", async (_event, payload) => {
    try {
      const tableId = Number(payload?.tableId);
      const url = new URL(`/pos/tables/${tableId}/print`, getBackendUrl()).toString();
      return await requestJson(
        url,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ print_type: String(payload?.printType || "guest_check").trim() }),
        },
        true,
        { timeoutMs: POS_REQUEST_TIMEOUT_MS }
      );
    } catch (error) {
      logPosIpcError("print-ticket", error);
      return { ok: false, error: describeUnexpectedError(error, "Could not reach POS print endpoint.") };
    }
  });

  ipcMain.handle("pos:close-table", async (_event, payload) => {
    try {
      const tableId = Number(payload?.tableId);
      const url = new URL(`/pos/tables/${tableId}/close`, getBackendUrl()).toString();
      return await requestJson(
        url,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note: String(payload?.note || "").trim() || null }),
        },
        true,
        { timeoutMs: POS_REQUEST_TIMEOUT_MS }
      );
    } catch (error) {
      logPosIpcError("close-table", error);
      return { ok: false, error: describeUnexpectedError(error, "Could not reach POS close endpoint.") };
    }
  });
}

module.exports = { registerPosIpc };
