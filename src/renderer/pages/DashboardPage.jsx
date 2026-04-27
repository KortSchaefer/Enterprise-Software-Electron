import { useEffect, useMemo, useState } from "react";
import InventoryApp from "../apps/InventoryApp.jsx";
import TimeclockApp from "../apps/TimeclockApp.jsx";
import ChatApp from "../apps/ChatApp.jsx";
import { ChatProvider, useChat } from "../chat/ChatProvider.jsx";

const APP_COMPONENTS = {
  inventory: InventoryApp,
  timeclock: TimeclockApp,
  chat: ChatApp,
};

export default function DashboardPage({ appName, tenantId, businessName, userEmail, userId }) {
  const [selectedAppKey, setSelectedAppKey] = useState("");

  return (
    <ChatProvider
      tenantId={tenantId}
      userId={userId}
      userEmail={userEmail}
      syncEnabled={selectedAppKey === "chat"}
    >
      <DashboardShell
        appName={appName}
        tenantId={tenantId}
        businessName={businessName}
        userEmail={userEmail}
        userId={userId}
        selectedAppKey={selectedAppKey}
        setSelectedAppKey={setSelectedAppKey}
      />
    </ChatProvider>
  );
}

function DashboardShell({ appName, tenantId, businessName, userEmail, userId, selectedAppKey, setSelectedAppKey }) {
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const [isResizing, setIsResizing] = useState(false);
  const [catalog, setCatalog] = useState([]);
  const [installedApps, setInstalledApps] = useState([]);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState("");
  const { unreadTotal: chatUnreadTotal } = useChat();
  
  const availableToInstall = useMemo(() => {
    const installedKeys = new Set(installedApps.map((app) => app.app_key));
    return catalog.filter((app) => !installedKeys.has(app.key));
  }, [catalog, installedApps]);

  const ActiveApp = APP_COMPONENTS[selectedAppKey];

  async function loadShellData() {
    setIsLoading(true);
    const [catalogResult, installedResult] = await Promise.all([
      window.electronAPI.apps.listCatalog(),
      window.electronAPI.apps.listInstalled(tenantId),
    ]);

    if (!catalogResult.ok) {
      setMessage(catalogResult.error || "Failed to load app catalog.");
      setIsLoading(false);
      return;
    }
    if (!installedResult.ok) {
      setMessage(installedResult.error || "Failed to load installed apps.");
      setIsLoading(false);
      return;
    }

    setCatalog(catalogResult.data);
    setInstalledApps(installedResult.data);
    if (installedResult.data.length > 0) {
      const preferredApp = installedResult.data.find((app) => app.app_key !== "pos") || installedResult.data[0];
      setSelectedAppKey(preferredApp.app_key);
    } else {
      setSelectedAppKey("");
    }
    setIsLoading(false);
  }

  useEffect(() => {
    loadShellData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  async function handleInstall(appKey) {
    setMessage(`Installing ${appKey}...`);
    const result = await window.electronAPI.apps.install({ tenantId, appKey });
    if (!result.ok) {
      setMessage(result.error || "Install failed.");
      return;
    }
    await loadShellData();
    setSelectedAppKey(appKey);
    setIsAddModalOpen(false);
    if (appKey === "pos") {
      const openResult = await window.electronAPI.window.openPos();
      setMessage(openResult.ok ? "Installed pos. POS opened in a separate window." : openResult.error || "Installed pos, but POS window failed to open.");
      return;
    }
    setMessage(`Installed ${appKey}.`);
  }

  async function handleAppSelect(appKey) {
    setSelectedAppKey(appKey);
    if (appKey !== "pos") {
      return;
    }
    const result = await window.electronAPI.window.openPos();
    setMessage(result.ok ? "POS opened in a separate window." : result.error || "POS window failed to open.");
  }
  
  useEffect(() => {
    if (!isResizing) {
      return undefined;
    }

    function handleMouseMove(event) {
      const nextWidth = Math.max(220, Math.min(440, event.clientX));
      setSidebarWidth(nextWidth);
    }

    function handleMouseUp() {
      setIsResizing(false);
    }

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing]);

  async function handleLogout() {
    await window.electronAPI.auth.logout();
    window.location.reload();
  }

  return (
    <main className="app-shell" style={{ gridTemplateColumns: `${sidebarWidth}px 8px 1fr` }}>
      <aside className="app-nav">
        <h1>{appName}</h1>
        <p className="subtitle">{businessName || tenantId}</p>
        <p className="subtitle">{userEmail || ""}</p>

        <button onClick={() => setIsAddModalOpen(true)}>Add New App</button>
        <button className="secondary-btn" onClick={handleLogout}>Log Out</button>

        <div className="app-list">
          <h3>Installed Apps</h3>
          {installedApps.length === 0 ? (
            <p className="subtitle">No apps installed yet.</p>
          ) : (
            installedApps.map((app) => (
              <button
                key={app.app_key}
                className={app.app_key === selectedAppKey ? "app-tab app-tab-active" : "app-tab"}
                onClick={() => handleAppSelect(app.app_key)}
                style={app.app_key === "chat" && chatUnreadTotal > 0 ? { display: "flex", alignItems: "center", gap: "8px" } : {}}
              >
                {app.app_key}
                {app.app_key === "chat" && chatUnreadTotal > 0 ? (
                  <span style={{ display: "flex", alignItems: "center", justifyContent: "center", width: "18px", height: "18px", borderRadius: "50%", backgroundColor: "#ef4444", color: "white", fontSize: "12px", fontWeight: "700" }}>
                    {chatUnreadTotal}
                  </span>
                ) : null}
              </button>
            ))
          )}
        </div>
      </aside>

      <div
        className="app-resizer"
        onMouseDown={() => setIsResizing(true)}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
      />

      <section className="app-workspace">
        {isLoading ? <p className="subtitle">Loading workspace...</p> : null}
        {!isLoading && !selectedAppKey ? (
          <div className="card">
            <h2>App Shell Ready</h2>
            <p className="subtitle">
              Click <strong>Add New App</strong> to install your first tenant app.
            </p>
          </div>
        ) : null}
        {!isLoading && selectedAppKey === "pos" ? (
          <div className="card">
            <h2>POS Opened</h2>
            <p className="subtitle">The POS table board runs in a dedicated popout window.</p>
            <button onClick={() => handleAppSelect("pos")}>Focus POS Window</button>
          </div>
        ) : null}
        {!isLoading && selectedAppKey !== "pos" && selectedAppKey && ActiveApp ? (
          <ActiveApp tenantId={tenantId} userId={userId} userEmail={userEmail} />
        ) : null}
        {!isLoading && selectedAppKey !== "pos" && selectedAppKey && !ActiveApp ? (
          <div className="card">
            <h2>Unknown App</h2>
            <p className="subtitle">No renderer module mapped for: {selectedAppKey}</p>
          </div>
        ) : null}

        {message ? <p className="message">{message}</p> : null}
      </section>

      {isAddModalOpen ? (
        <div className="modal-overlay" onClick={() => setIsAddModalOpen(false)}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()}>
            <h2>Add New App</h2>
            <p className="subtitle">Install apps available for this tenant.</p>
            {availableToInstall.length === 0 ? (
              <p className="subtitle">No additional apps available right now.</p>
            ) : (
              <div className="catalog-list">
                {availableToInstall.map((app) => (
                  <div key={app.key} className="catalog-row">
                    <div>
                      <p className="catalog-title">{app.name}</p>
                      <p className="subtitle">{app.description}</p>
                    </div>
                    <button onClick={() => handleInstall(app.key)}>Install</button>
                  </div>
                ))}
              </div>
            )}
            <button className="secondary-btn" onClick={() => setIsAddModalOpen(false)}>
              Close
            </button>
          </div>
        </div>
      ) : null}
    </main>
  );
}
