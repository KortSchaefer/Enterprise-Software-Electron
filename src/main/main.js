const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const { registerBootstrapIpc } = require("./bootstrapIpc");
const { registerAuthIpc } = require("./authIpc");
const { registerAppsIpc } = require("./appsIpc");
const { registerInventoryIpc } = require("./inventoryIpc");
const { registerTimeclockIpc } = require("./timeclockIpc");
const { registerChatIpc } = require("./chatIpc");

function loadRendererWindow(browserWindow, screen, query = {}) {
  const rendererUrl = process.env.ELECTRON_RENDERER_URL;

  if (rendererUrl) {
    const url = new URL(rendererUrl);
    if (screen) {
      url.searchParams.set("screen", screen);
    }
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
    browserWindow.loadURL(url.toString());
  } else {
    const rendererPath = path.join(__dirname, "../../dist/renderer/index.html");
    const fileQuery = {};
    if (screen) {
      fileQuery.screen = screen;
    }
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        fileQuery[key] = String(value);
      }
    });
    const options = Object.keys(fileQuery).length > 0 ? { query: fileQuery } : undefined;
    browserWindow.loadFile(rendererPath, options);
  }
}

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  loadRendererWindow(mainWindow);
}

function createDashboardWindow(payload = {}) {
  const dashboardWindow = new BrowserWindow({
    width: 1100,
    height: 760,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  loadRendererWindow(dashboardWindow, "dashboard", {
    tenantId: payload.tenantId,
    businessName: payload.businessName,
    userEmail: payload.userEmail,
    userId: payload.userId,
  });
}


app.whenReady().then(() => {
  registerBootstrapIpc();
  registerAuthIpc();
  registerAppsIpc();
  registerInventoryIpc();
  registerTimeclockIpc();
  ipcMain.handle("window:open-dashboard", async (_event, payload) => {
    createDashboardWindow(payload);
    return { ok: true };
  });
  registerChatIpc(loadRendererWindow);

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
