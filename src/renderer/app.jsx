import { useEffect, useState } from "react";
import ActivatePage from "./pages/ActivatePage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import ChatApp from "./apps/ChatApp.jsx";
import SwitchTenantPage from "./pages/SwitchTenantPage.jsx";
import { ChatProvider } from "./chat/ChatProvider.jsx";

export default function App() {
  const appName = window.electronAPI?.appName ?? "Enterprise Software Electron";
  const searchParams = new URLSearchParams(window.location.search);
  const screen = searchParams.get("screen");
  const tenantIdFromQuery = searchParams.get("tenantId") || "";
  const businessNameFromQuery = searchParams.get("businessName") || "";
  const userEmailFromQuery = searchParams.get("userEmail") || "";
  const parentWindowIdFromQuery = searchParams.get("parentWindowId") || "";
  const [isLoading, setIsLoading] = useState(true);
  const [bootstrapState, setBootstrapState] = useState(null);
  const [authState, setAuthState] = useState(null);
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
      <ChatProvider
        tenantId={tenantIdFromQuery}
        userId={Number(userIdFromQuery) || null}
        userEmail={userEmailFromQuery}
        syncEnabled={true}
      >
        <ChatApp mode="popup" businessName={businessNameFromQuery} />
      </ChatProvider>
    );
  }

  if (screen === "switch-tenant") {
    return (
      <SwitchTenantPage
        appName={appName}
        parentWindowId={Number(parentWindowIdFromQuery) || null}
      />
    );
  }

  useEffect(() => {
    let mounted = true;

    async function loadAppState() {
      try {
        const [state, session] = await Promise.all([
          window.electronAPI.bootstrap.getState(),
          window.electronAPI.auth.getSession(),
        ]);
        if (mounted) {
          setBootstrapState(state);
          setAuthState(session);
        }
      } catch (_error) {
        if (mounted) {
          setBootstrapState(null);
          setAuthState(null);
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    loadAppState();

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

  if (authState?.accessToken) {
    return (
      <DashboardPage
        appName={appName}
        tenantId={authState.tenantId || bootstrapState.tenantId}
        businessName={bootstrapState.businessName}
        userEmail={authState.email}
        userId={authState.userId}
      />
    );
  }

  return (
    <LoginPage
      appName={appName}
      tenantId={bootstrapState.tenantId}
      businessName={bootstrapState.businessName}
      onLoggedIn={setAuthState}
    />
  );
}
