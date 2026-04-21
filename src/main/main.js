const { app, BrowserWindow, Menu, ipcMain } = require("electron");
const path = require("path");
const { loadBackendEnv } = require("./loadBackendEnv");
const { registerBootstrapIpc } = require("./bootstrapIpc");
const { registerAuthIpc } = require("./authIpc");
const { registerAppsIpc } = require("./appsIpc");
const { registerInventoryIpc } = require("./inventoryIpc");
const { registerTimeclockIpc } = require("./timeclockIpc");
const { registerChatIpc } = require("./chatIpc");
const { readBootstrapState, writeBootstrapState } = require("./bootstrapStore");
const { clearAuthState, readAuthState } = require("./authStore");

loadBackendEnv();

function canSwitchTenant() {
  return process.env.ALLOW_TENANT_SWITCH === "true" || process.env.NODE_ENV === "development";
}

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

function createTenantSwitchWindow(parentWindow) {
  const switchWindow = new BrowserWindow({
    width: 520,
    height: 380,
    resizable: false,
    maximizable: false,
    minimizable: false,
    modal: Boolean(parentWindow),
    parent: parentWindow || undefined,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  loadRendererWindow(switchWindow, "switch-tenant", {
    parentWindowId: parentWindow?.id,
  });
}

function buildApplicationMenu() {
  const template = [
    {
      label: "File",
      submenu: [
        ...(canSwitchTenant()
          ? [
              {
                label: "Switch Tenant",
                accelerator: "CmdOrCtrl+Shift+T",
                click: () => {
                  const focusedWindow = BrowserWindow.getFocusedWindow();
                  createTenantSwitchWindow(focusedWindow || null);
                },
              },
            ]
          : []),
        { type: "separator" },
        { role: "quit" },
      ],
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "selectAll" },
      ],
    },
    {
      label: "View",
      submenu: [{ role: "reload" }, { role: "forceReload" }, { role: "toggleDevTools" }],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(() => {
  registerBootstrapIpc();
  registerAuthIpc();
  registerAppsIpc();
  registerInventoryIpc();
  registerTimeclockIpc();
  buildApplicationMenu();
  ipcMain.handle("window:open-dashboard", async (_event, payload) => {
    const authState = await readAuthState();
    createDashboardWindow({
      tenantId: authState?.tenantId || payload?.tenantId,
      businessName: payload?.businessName,
      userEmail: authState?.email || payload?.userEmail,
      userId: authState?.userId || payload?.userId,
    });
    return { ok: true };
  });
  ipcMain.handle("window:close-self", async (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    window?.close();
    return { ok: true };
  });
  ipcMain.handle("bootstrap:switch-tenant-id", async (event, payload) => {
    if (!canSwitchTenant()) {
      return { ok: false, error: "Tenant switching is disabled outside development mode." };
    }
    const tenantId = String(payload?.tenantId || "").trim();
    const businessName = String(payload?.businessName || "").trim();
    const parentWindowId = Number(payload?.parentWindowId) || null;

    if (!tenantId) {
      return { ok: false, error: "tenantId is required." };
    }

    const currentState = (await readBootstrapState()) || {};
    const nextState = {
      ...currentState,
      tenantId,
      businessName: businessName || tenantId,
      switchedAt: new Date().toISOString(),
    };
    await writeBootstrapState(nextState);
    await clearAuthState();

    const parentWindow = parentWindowId ? BrowserWindow.fromId(parentWindowId) : null;
    if (parentWindow && !parentWindow.isDestroyed()) {
      loadRendererWindow(parentWindow);
      parentWindow.focus();
    }

    const currentWindow = BrowserWindow.fromWebContents(event.sender);
    if (currentWindow && !currentWindow.isDestroyed()) {
      currentWindow.close();
    }

    return { ok: true, data: nextState };
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
