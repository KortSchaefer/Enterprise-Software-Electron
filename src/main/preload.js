const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  appName: "Enterprise Software Electron",
  bootstrap: {
    getState: () => ipcRenderer.invoke("bootstrap:get-state"),
    activate: (activationCode) =>
      ipcRenderer.invoke("bootstrap:activate", activationCode),
    reset: () => ipcRenderer.invoke("bootstrap:reset"),
  },
  auth: {
    login: (payload) => ipcRenderer.invoke("auth:login", payload),
  },
  apps: {
    listCatalog: () => ipcRenderer.invoke("apps:list-catalog"),
    listInstalled: (tenantId) => ipcRenderer.invoke("apps:list-installed", tenantId),
    install: (payload) => ipcRenderer.invoke("apps:install", payload),
  },
  inventory: {
    listItems: (payload) => ipcRenderer.invoke("inventory:list-items", payload),
    createItem: (payload) => ipcRenderer.invoke("inventory:create-item", payload),
    adjustItem: (payload) => ipcRenderer.invoke("inventory:adjust-item", payload),
  },
  timeclock: {
    listEmployees: (tenantId) => ipcRenderer.invoke("timeclock:list-employees", tenantId),
    createEmployee: (payload) => ipcRenderer.invoke("timeclock:create-employee", payload),
    createEvent: (payload) => ipcRenderer.invoke("timeclock:create-event", payload),
    liveBoard: (tenantId) => ipcRenderer.invoke("timeclock:live-board", tenantId),
    createShift: (payload) => ipcRenderer.invoke("timeclock:create-shift", payload),
    listShifts: (payload) => ipcRenderer.invoke("timeclock:list-shifts", payload),
    listExceptions: (payload) => ipcRenderer.invoke("timeclock:list-exceptions", payload),
    timesheetSummary: (payload) => ipcRenderer.invoke("timeclock:timesheet-summary", payload),
    approveTimesheet: (payload) => ipcRenderer.invoke("timeclock:approve-timesheet", payload),
    getPolicy: (tenantId) => ipcRenderer.invoke("timeclock:get-policy", tenantId),
    updatePolicy: (payload) => ipcRenderer.invoke("timeclock:update-policy", payload),
    listAlerts: (tenantId) => ipcRenderer.invoke("timeclock:list-alerts", tenantId),
    resolveAlert: (payload) => ipcRenderer.invoke("timeclock:resolve-alert", payload),
    syncAlerts: (payload) => ipcRenderer.invoke("timeclock:sync-alerts", payload),
    exportCsv: (payload) => ipcRenderer.invoke("timeclock:export-csv", payload),
  },
    chat: {
    listUsers: (tenantId) => ipcRenderer.invoke("chat:list-users", tenantId),
    listMessages: (payload) => ipcRenderer.invoke("chat:list-messages", payload),
    sendMessage: (payload) => ipcRenderer.invoke("chat:send-message", payload),
  },
  window: {
    openDashboard: (payload) => ipcRenderer.invoke("window:open-dashboard", payload),
    openChat: (payload) => ipcRenderer.invoke("window:open-chat", payload),
  },

});
