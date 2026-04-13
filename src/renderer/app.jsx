import { useEffect, useState } from "react";
import ActivatePage from "./pages/ActivatePage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import ChatApp from "./apps/ChatApp.jsx";

export default function App() {
  const appName = window.electronAPI?.appName ?? "Enterprise Software Electron";
  const searchParams = new URLSearchParams(window.location.search);
  const screen = searchParams.get("screen");
  const tenantIdFromQuery = searchParams.get("tenantId") || "";
  const businessNameFromQuery = searchParams.get("businessName") || "";
  const userEmailFromQuery = searchParams.get("userEmail") || "";
  const [isLoading, setIsLoading] = useState(true);
  const [bootstrapState, setBootstrapState] = useState(null);
  const userIdFromQuery = searchParams.get("userId") || "";

  if (screen === "dashboard") {
    return (
      <DashboardPage
        appName={appName}
        tenantId={tenantIdFromQuery}
        businessName={businessNameFromQuery}
        userEmail={userEmailFromQuery}
        userId={Number(userIdFromQuery) || null}
      />
    );
  }

    if (screen === "chat") {
    return (
      <ChatApp
        tenantId={tenantIdFromQuery}
        userId={Number(userIdFromQuery) || null}
        userEmail={userEmailFromQuery}
        businessName={businessNameFromQuery}
      />
    );
  }

  useEffect(() => {
    let mounted = true;

    async function loadBootstrapState() {
      try {
        const state = await window.electronAPI.bootstrap.getState();
        if (mounted) {
          setBootstrapState(state);
        }
      } catch (_error) {
        if (mounted) {
          setBootstrapState(null);
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    loadBootstrapState();

    return () => {
      mounted = false;
    };
  }, []);

  if (isLoading) {
    return (
      <main className="page">
        <section className="card">
          <h1>{appName}</h1>
          <p className="subtitle">Loading application state...</p>
        </section>
      </main>
    );
  }

  if (!bootstrapState?.tenantId) {
    return <ActivatePage appName={appName} onActivated={setBootstrapState} />;
  }

  return (
    <LoginPage
      appName={appName}
      tenantId={bootstrapState.tenantId}
      businessName={bootstrapState.businessName}
    />
  );
}
