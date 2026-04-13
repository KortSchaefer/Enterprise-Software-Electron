import { useEffect, useMemo, useState } from "react";
import InventoryApp from "../apps/InventoryApp.jsx";
import TimeclockApp from "../apps/TimeclockApp.jsx";
import ChatApp from "../apps/ChatApp.jsx";

const APP_COMPONENTS = {
  inventory: InventoryApp,
  timeclock: TimeclockApp,
  chat: ChatApp,
};

export default function DashboardPage({ appName, tenantId, businessName, userEmail, userId }) {
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const [isResizing, setIsResizing] = useState(false);
  const [catalog, setCatalog] = useState([]);
  const [installedApps, setInstalledApps] = useState([]);
  const [selectedAppKey, setSelectedAppKey] = useState("");
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [chatUnreadTotal, setChatUnreadTotal] = useState(0);
  
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
      setSelectedAppKey(installedResult.data[0].app_key);
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
    setMessage(`Installed ${appKey}.`);
  }

  function handleAppSelect(appKey) {
    if (appKey === "chat") {
      window.electronAPI.window.openChat({ tenantId, userId, userEmail, businessName });
    } else {
      setSelectedAppKey(appKey);
    }
  }

    function getLastSeenKey(withUserId) {
    return `chat:lastSeen:${tenantId}:${userId}:${withUserId}`;
  }

  function getLastSeenMs(withUserId) {
    const key = getLastSeenKey(withUserId);
    return Number(localStorage.getItem(key)) || 0;
  }

  async function loadChatUnreadTotal() {
    try {
      const usersRes = await fetch(`http://localhost:8000/users?tenant_id=${tenantId}`);
      if (!usersRes.ok) return;
      const users = await usersRes.json();

      let total = 0;
      for (const user of users) {
        if (user.id === userId) continue;
        const messagesRes = await fetch("http://localhost:8000/chat/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tenant_id: tenantId, with_user_id: user.id }),
        });
        if (!messagesRes.ok) continue;
        const data = await messagesRes.json();
        const lastSeenMs = getLastSeenMs(user.id);
        const unreadCount = data.filter((msg) => msg.from_user_id === user.id && new Date(msg.created_at).getTime() > lastSeenMs).length;
        total += unreadCount;
      }
      setChatUnreadTotal(total);
    } catch (err) {
      console.error("Error loading chat unread total:", err);
    }
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

    useEffect(() => {
    const interval = setInterval(loadChatUnreadTotal, 3000);
    loadChatUnreadTotal();
    return () => clearInterval(interval);
  }, [tenantId, userId]);

  return (
    <main className="app-shell" style={{ gridTemplateColumns: `${sidebarWidth}px 8px 1fr` }}>
      <aside className="app-nav">
        <h1>{appName}</h1>
        <p className="subtitle">{businessName || tenantId}</p>
        <p className="subtitle">{userEmail || ""}</p>

        <button onClick={() => setIsAddModalOpen(true)}>Add New App</button>

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
        {!isLoading && selectedAppKey && ActiveApp ? <ActiveApp tenantId={tenantId} userId={userId} userEmail={userEmail} /> : null}
        {!isLoading && selectedAppKey && !ActiveApp ? (
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
