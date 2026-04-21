import { useState } from "react";

export default function SwitchTenantPage({ appName, parentWindowId }) {
  const [tenantId, setTenantId] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [status, setStatus] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();

    if (!tenantId.trim()) {
      setStatus("Enter a tenant id.");
      return;
    }

    setIsSubmitting(true);
    setStatus("Switching tenant...");

    try {
      const result = await window.electronAPI.bootstrap.switchTenantId({
        tenantId: tenantId.trim(),
        businessName: businessName.trim(),
        parentWindowId,
      });

      if (!result.ok) {
        setStatus(result.error || "Tenant switch failed.");
        return;
      }

      setStatus("Tenant switched.");
    } catch (_error) {
      setStatus("Tenant switch failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleCancel() {
    await window.electronAPI.window.closeSelf();
  }

  return (
    <main className="page">
      <section className="card">
        <h1>{appName}</h1>
        <p className="subtitle">Switch the active tenant for this workstation</p>

        <form className="form" onSubmit={handleSubmit}>
          <label htmlFor="tenantId">Tenant ID</label>
          <input
            id="tenantId"
            name="tenantId"
            value={tenantId}
            onChange={(event) => setTenantId(event.target.value)}
            placeholder="demo-tenant"
            required
          />

          <label htmlFor="businessName">Business name</label>
          <input
            id="businessName"
            name="businessName"
            value={businessName}
            onChange={(event) => setBusinessName(event.target.value)}
            placeholder="Optional"
          />

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Switching..." : "Switch Tenant"}
          </button>
          <button type="button" onClick={handleCancel} disabled={isSubmitting}>
            Cancel
          </button>
        </form>

        {status ? <p className="message">{status}</p> : null}
      </section>
    </main>
  );
}
