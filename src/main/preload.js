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
  pos: {
    getBoard: () => ipcRenderer.invoke("pos:get-board"),
    createTable: (payload) => ipcRenderer.invoke("pos:create-table", payload),
    getMenu: () => ipcRenderer.invoke("pos:get-menu"),
    getTableDetail: (payload) => ipcRenderer.invoke("pos:get-table-detail", payload),
    addItem: (payload) => ipcRenderer.invoke("pos:add-item", payload),
    updateItem: (payload) => ipcRenderer.invoke("pos:update-item", payload),
    removeItem: (payload) => ipcRenderer.invoke("pos:remove-item", payload),
    updateStatus: (payload) => ipcRenderer.invoke("pos:update-status", payload),
    printTicket: (payload) => ipcRenderer.invoke("pos:print-ticket", payload),
    closeTable: (payload) => ipcRenderer.invoke("pos:close-table", payload),
  },
  chat: {
    listConversations: () => ipcRenderer.invoke("chat:list-conversations"),
    getMessages: (payload) => ipcRenderer.invoke("chat:get-messages", payload),
    sendMessage: (payload) => ipcRenderer.invoke("chat:send-message", payload),
    markRead: (payload) => ipcRenderer.invoke("chat:mark-read", payload),
    getStreamUrl: () => ipcRenderer.invoke("chat:get-stream-url"),
  },
  window: {
    openDashboard: (payload) => ipcRenderer.invoke("window:open-dashboard", payload),
    openChat: (payload) => ipcRenderer.invoke("window:open-chat", payload),
    openPos: () => ipcRenderer.invoke("window:open-pos"),
    closeSelf: () => ipcRenderer.invoke("window:close-self"),
  },

});
