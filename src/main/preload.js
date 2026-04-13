const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  appName: "Enterprise Software Electron",
  bootstrap: {
    getState: () => ipcRenderer.invoke("bootstrap:get-state"),
    activate: (activationCode) =>
      ipcRenderer.invoke("bootstrap:activate", activationCode),
    reset: () => ipcRenderer.invoke("bootstrap:reset"),
    switchTenantId: (payload) => ipcRenderer.invoke("bootstrap:switch-tenant-id", payload),
  },
  auth: {
    login: (payload) => ipcRenderer.invoke("auth:login", payload),
    getSession: () => ipcRenderer.invoke("auth:get-session"),
    logout: () => ipcRenderer.invoke("auth:logout"),
  },
  apps: {
    listCatalog: () => ipcRenderer.invoke("apps:list-catalog"),
    listInstalled: () => ipcRenderer.invoke("apps:list-installed"),
    install: (payload) => ipcRenderer.invoke("apps:install", payload),
  },
  inventory: {
    listItems: (payload) => ipcRenderer.invoke("inventory:list-items", payload),
    createItem: (payload) => ipcRenderer.invoke("inventory:create-item", payload),
    adjustItem: (payload) => ipcRenderer.invoke("inventory:adjust-item", payload),
  },
  timeclock: {
    listEmployees: () => ipcRenderer.invoke("timeclock:list-employees"),
    createEmployee: (payload) => ipcRenderer.invoke("timeclock:create-employee", payload),
    createEvent: (payload) => ipcRenderer.invoke("timeclock:create-event", payload),
    liveBoard: () => ipcRenderer.invoke("timeclock:live-board"),
    createShift: (payload) => ipcRenderer.invoke("timeclock:create-shift", payload),
    listShifts: (payload) => ipcRenderer.invoke("timeclock:list-shifts", payload),
    listExceptions: (payload) => ipcRenderer.invoke("timeclock:list-exceptions", payload),
    timesheetSummary: (payload) => ipcRenderer.invoke("timeclock:timesheet-summary", payload),
    approveTimesheet: (payload) => ipcRenderer.invoke("timeclock:approve-timesheet", payload),
    getPolicy: () => ipcRenderer.invoke("timeclock:get-policy"),
    updatePolicy: (payload) => ipcRenderer.invoke("timeclock:update-policy", payload),
    listAlerts: () => ipcRenderer.invoke("timeclock:list-alerts"),
    resolveAlert: (payload) => ipcRenderer.invoke("timeclock:resolve-alert", payload),
    syncAlerts: (payload) => ipcRenderer.invoke("timeclock:sync-alerts", payload),
    exportCsv: (payload) => ipcRenderer.invoke("timeclock:export-csv", payload),
  },
    chat: {
    listUsers: () => ipcRenderer.invoke("chat:list-users"),
    listMessages: (payload) => ipcRenderer.invoke("chat:list-messages", payload),
    sendMessage: (payload) => ipcRenderer.invoke("chat:send-message", payload),
  },
  window: {
    openDashboard: (payload) => ipcRenderer.invoke("window:open-dashboard", payload),
    openChat: (payload) => ipcRenderer.invoke("window:open-chat", payload),
    closeSelf: () => ipcRenderer.invoke("window:close-self"),
  },

});
