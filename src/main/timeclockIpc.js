const { ipcMain } = require("electron");
const { getBackendUrl, requestJson } = require("./backendClient");

function registerTimeclockIpc() {
  ipcMain.handle("timeclock:list-employees", async () => {
    try {
      const url = new URL("/timeclock/employees", getBackendUrl()).toString();
      return await requestJson(url);
    } catch (_error) {
      return { ok: false, error: "Could not reach timeclock employees endpoint." };
    }
  });

  ipcMain.handle("timeclock:create-employee", async (_event, payload) => {
    try {
      const url = new URL("/timeclock/employees", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: payload?.fullName,
          email: payload?.email,
          role: payload?.role || "staff",
          location: payload?.location || "",
        }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach timeclock employee create endpoint." };
    }
  });

  ipcMain.handle("timeclock:create-event", async (_event, payload) => {
    try {
      const url = new URL("/timeclock/events", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          employee_id: payload?.employeeId,
          event_type: payload?.eventType,
          occurred_at: payload?.occurredAt,
          source: payload?.source || "manager",
          reason: payload?.reason || "",
          created_by: payload?.createdBy || "manager",
        }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach timeclock event endpoint." };
    }
  });

  ipcMain.handle("timeclock:live-board", async () => {
    try {
      const url = new URL("/timeclock/live", getBackendUrl()).toString();
      return await requestJson(url);
    } catch (_error) {
      return { ok: false, error: "Could not reach live board endpoint." };
    }
  });

  ipcMain.handle("timeclock:create-shift", async (_event, payload) => {
    try {
      const url = new URL("/timeclock/shifts", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          employee_id: payload?.employeeId,
          start_at: payload?.startAt,
          end_at: payload?.endAt,
          location: payload?.location || "",
          role: payload?.role || "staff",
        }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach shift create endpoint." };
    }
  });

  ipcMain.handle("timeclock:list-shifts", async (_event, payload) => {
    try {
      const url = new URL("/timeclock/shifts", getBackendUrl());
      url.searchParams.set("date_from", payload?.dateFrom);
      url.searchParams.set("date_to", payload?.dateTo);
      return await requestJson(url.toString());
    } catch (_error) {
      return { ok: false, error: "Could not reach shift list endpoint." };
    }
  });

  ipcMain.handle("timeclock:list-exceptions", async (_event, payload) => {
    try {
      const url = new URL("/timeclock/exceptions", getBackendUrl());
      url.searchParams.set("day", payload?.day);
      return await requestJson(url.toString());
    } catch (_error) {
      return { ok: false, error: "Could not reach exceptions endpoint." };
    }
  });

  ipcMain.handle("timeclock:timesheet-summary", async (_event, payload) => {
    try {
      const url = new URL("/timeclock/timesheet-summary", getBackendUrl());
      url.searchParams.set("period_start", payload?.periodStart);
      url.searchParams.set("period_end", payload?.periodEnd);
      return await requestJson(url.toString());
    } catch (_error) {
      return { ok: false, error: "Could not reach timesheet summary endpoint." };
    }
  });

  ipcMain.handle("timeclock:approve-timesheet", async (_event, payload) => {
    try {
      const url = new URL("/timeclock/timesheet-approval", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          employee_id: payload?.employeeId,
          period_start: payload?.periodStart,
          period_end: payload?.periodEnd,
          status: payload?.status,
          approved_by: payload?.approvedBy || "manager",
        }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach timesheet approval endpoint." };
    }
  });

  ipcMain.handle("timeclock:get-policy", async () => {
    try {
      const url = new URL("/timeclock/policy", getBackendUrl()).toString();
      return await requestJson(url);
    } catch (_error) {
      return { ok: false, error: "Could not reach policy endpoint." };
    }
  });

  ipcMain.handle("timeclock:update-policy", async (_event, payload) => {
    try {
      const url = new URL("/timeclock/policy", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          overtime_daily_hours: payload?.overtimeDailyHours,
          overtime_weekly_hours: payload?.overtimeWeeklyHours,
          max_break_minutes: payload?.maxBreakMinutes,
          late_tolerance_minutes: payload?.lateToleranceMinutes,
          early_clock_in_minutes: payload?.earlyClockInMinutes,
          geofence_required: Boolean(payload?.geofenceRequired),
        }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach policy update endpoint." };
    }
  });

  ipcMain.handle("timeclock:list-alerts", async () => {
    try {
      const url = new URL("/timeclock/alerts", getBackendUrl()).toString();
      return await requestJson(url);
    } catch (_error) {
      return { ok: false, error: "Could not reach alerts endpoint." };
    }
  });

  ipcMain.handle("timeclock:resolve-alert", async (_event, payload) => {
    try {
      const url = new URL("/timeclock/alerts/resolve", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alert_id: payload?.alertId }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach alert resolve endpoint." };
    }
  });

  ipcMain.handle("timeclock:sync-alerts", async (_event, payload) => {
    try {
      const url = new URL("/timeclock/alerts/sync", getBackendUrl()).toString();
      return await requestJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ day: payload?.day }),
      });
    } catch (_error) {
      return { ok: false, error: "Could not reach alert sync endpoint." };
    }
  });

  ipcMain.handle("timeclock:export-csv", async (_event, payload) => {
    try {
      const url = new URL("/timeclock/export.csv", getBackendUrl());
      url.searchParams.set("period_start", payload?.periodStart);
      url.searchParams.set("period_end", payload?.periodEnd);
      return await requestJson(url.toString());
    } catch (_error) {
      return { ok: false, error: "Could not reach export endpoint." };
    }
  });
}

module.exports = { registerTimeclockIpc };
