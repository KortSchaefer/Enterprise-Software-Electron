import { useState } from "react";

export default function LoginPage({ appName, tenantId, businessName }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setIsSubmitting(true);
    setMessage("Signing in...");

    try {
      const result = await window.electronAPI.auth.login({
        tenantId,
        email,
        password,
      });

      if (!result.ok) {
        setMessage(result.error || "Login failed.");
        return;
      }

      setMessage("Login successful. Opening dashboard...");
      await window.electronAPI.window.openDashboard({
        tenantId,
        businessName,
        userEmail: result.data.email,
        userId: result.data.user_id,
      });
    } catch (_error) {
      setMessage("Login failed. Check backend connectivity.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="page">
      <section className="card">
        <h1>{appName}</h1>
        {businessName ? <p className="subtitle">Business: {businessName}</p> : null}
        <p className="subtitle">Tenant: {tenantId}</p>
        <p className="subtitle">Sign in to continue</p>

        <form className="form" onSubmit={handleSubmit}>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@company.com"
            required
          />

          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Enter password"
            required
          />

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Signing In..." : "Log In"}
          </button>
        </form>

        {message ? <p className="message">{message}</p> : null}
      </section>
    </main>
  );
}
