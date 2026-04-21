const { ipcMain } = require("electron");
const { getBackendUrl, requestJson } = require("./backendClient");

function registerInventoryIpc() {
  ipcMain.handle("inventory:list-items", async (_event, payload) => {
    const lowStockOnly = Boolean(payload?.lowStockOnly);

    try {
      const url = new URL("/inventory/items", getBackendUrl());
      if (lowStockOnly) {
        url.searchParams.set("low_stock_only", "true");
      }
      return await requestJson(url.toString());
    } catch (_error) {
      return { ok: false, error: "Could not reach inventory endpoint." };
    }
  });

  ipcMain.handle("inventory:create-item", async (_event, payload) => {
    try {
      const url = new URL("/inventory/items", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sku: payload?.sku,
          name: payload?.name,
          description: payload?.description || "",
          quantity_on_hand: payload?.quantityOnHand ?? 0,
          reorder_point: payload?.reorderPoint ?? 0,
        }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach inventory create endpoint." };
    }
  });

  ipcMain.handle("inventory:adjust-item", async (_event, payload) => {
    try {
      const url = new URL("/inventory/adjust", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          item_id: payload?.itemId,
          change_amount: payload?.changeAmount,
          reason: payload?.reason || "manual-adjustment",
          performed_by: payload?.performedBy || "",
        }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach inventory adjust endpoint." };
    }
  });
}

module.exports = { registerInventoryIpc };
