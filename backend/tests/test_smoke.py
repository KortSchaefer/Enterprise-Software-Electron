import os
import uuid

import requests


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = 10

TENANT_ID = "demo-tenant"
LOGIN_EMAIL = "admin@demo-tenant.local"
LOGIN_PASSWORD = "Password123!"


def _get(url, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.get(url, timeout=TIMEOUT, headers=headers, **kwargs)


def _post(url, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.post(url, timeout=TIMEOUT, headers=headers, **kwargs)


def _put(url, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.put(url, timeout=TIMEOUT, headers=headers, **kwargs)


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _login() -> str | None:
    payload = {
        "tenant_id": TENANT_ID,
        "email": LOGIN_EMAIL,
        "password": LOGIN_PASSWORD,
    }
    response = _post(f"{BASE_URL}/auth/login", json=payload)
    if response.status_code != 200:
        return None
    body = response.json()
    return body.get("access_token")


def _session(token: str) -> dict:
    response = _get(f"{BASE_URL}/auth/session", token=token)
    assert response.status_code == 200, response.text
    return response.json()


def _list_users(token: str) -> list[dict]:
    response = _get(f"{BASE_URL}/users", token=token)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    return body


def _pick_chat_recipient(token: str) -> int | None:
    session = _session(token)
    users = _list_users(token)
    for row in users:
        if row["id"] != session["user_id"]:
            return row["id"]
    return None


def _create_timeclock_employee(token: str) -> dict:
    unique = _suffix()
    payload = {
        "full_name": f"Smoke Employee {unique}",
        "email": f"smoke.employee.{unique}@example.com",
        "role": "staff",
        "location": "Smoke",
    }
    response = _post(f"{BASE_URL}/timeclock/employees", token=token, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _list_inventory_items(token: str) -> list[dict]:
    response = _get(f"{BASE_URL}/inventory/items", token=token, params={"low_stock_only": "false"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    return body


def test_smoke_health():
    response = _get(f"{BASE_URL}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_smoke_activation_validate():
    payload = {"tenant_key": "X" * 64}
    response = _post(f"{BASE_URL}/activation/validate", json=payload)
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "Tenant key must be a valid 64-character hex string."


def test_smoke_login_and_session_flow():
    token = _login()
    assert token, "Expected login to succeed for demo admin user"

    session_resp = _get(f"{BASE_URL}/auth/session", token=token)
    assert session_resp.status_code == 200
    session = session_resp.json()
    assert session["tenant_id"] == TENANT_ID
    assert session["email"] == LOGIN_EMAIL
    assert "user_id" in session
    assert "role" in session

    logout_resp = _post(f"{BASE_URL}/auth/logout", token=token)
    assert logout_resp.status_code == 200
    assert logout_resp.json() == {"status": "ok"}


def test_smoke_list_users():
    token = _login()
    assert token

    body = _list_users(token)
    assert len(body) >= 1
    for row in body:
        assert "id" in row
        assert "tenant_id" in row
        assert "email" in row
        assert row["tenant_id"] == TENANT_ID


def test_smoke_create_user():
    token = _login()
    assert token

    unique = _suffix()
    payload = {
        "email": f"smoke.user.{unique}@example.com",
        "password": "Password123!",
        "role": "staff",
    }
    response = _post(f"{BASE_URL}/users", token=token, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tenant_id"] == TENANT_ID
    assert body["email"] == payload["email"]


def test_smoke_list_app_catalog():
    response = _get(f"{BASE_URL}/apps/catalog")
    assert response.status_code == 200
    body = response.json()
    keys = {row.get("key") for row in body if isinstance(row, dict)}
    assert "inventory" in keys
    assert "timeclock" in keys
    assert "chat" in keys


def test_smoke_list_installed_apps():
    token = _login()
    assert token

    response = _get(f"{BASE_URL}/apps/installed", token=token)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_smoke_install_app():
    token = _login()
    assert token

    payload = {"app_key": "timeclock"}
    response = _post(f"{BASE_URL}/apps/install", token=token, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["app_key"] == "timeclock"
    assert "installed_at" in body


def test_smoke_list_inventory_items():
    token = _login()
    assert token

    body = _list_inventory_items(token)
    assert isinstance(body, list)


def test_smoke_create_inventory_item():
    token = _login()
    assert token

    unique = _suffix().upper()
    payload = {
        "sku": f"SMOKE-{unique}",
        "name": f"Smoke Test Item {unique}",
        "description": "Smoke-created inventory item.",
        "quantity_on_hand": 0,
        "reorder_point": 0,
    }
    response = _post(f"{BASE_URL}/inventory/items", token=token, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tenant_id"] == TENANT_ID
    assert body["sku"] == payload["sku"]


def test_smoke_adjust_inventory():
    token = _login()
    assert token

    items = _list_inventory_items(token)
    assert items, "Expected at least one inventory item in demo seed data"

    payload = {
        "item_id": items[0]["id"],
        "change_amount": 1,
        "reason": "Smoke test",
        "performed_by": "smoke-user",
    }
    response = _post(f"{BASE_URL}/inventory/adjust", token=token, json=payload)
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), dict)


def test_smoke_create_timeclock_employee():
    token = _login()
    assert token

    body = _create_timeclock_employee(token)
    assert body["tenant_id"] == TENANT_ID
    assert "id" in body
    assert "email" in body


def test_smoke_list_timeclock_employees():
    token = _login()
    assert token

    response = _get(f"{BASE_URL}/timeclock/employees", token=token)
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


def test_smoke_create_timeclock_event():
    token = _login()
    assert token

    employee = _create_timeclock_employee(token)
    payload = {
        "employee_id": employee["id"],
        "event_type": "clock_in",
        "occurred_at": "2026-03-22T19:45:00+00:00",
        "source": "employee",
        "reason": "",
        "created_by": "",
    }
    response = _post(f"{BASE_URL}/timeclock/events", token=token, json=payload)
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}


def test_smoke_timeclock_live_board():
    token = _login()
    assert token

    response = _get(f"{BASE_URL}/timeclock/live", token=token)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_smoke_create_timeclock_shift():
    token = _login()
    assert token

    employee = _create_timeclock_employee(token)
    payload = {
        "employee_id": employee["id"],
        "start_at": "2026-03-22T08:00:00+00:00",
        "end_at": "2026-03-22T16:00:00+00:00",
        "location": "",
        "role": "staff",
    }
    response = _post(f"{BASE_URL}/timeclock/shifts", token=token, json=payload)
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), dict)


def test_smoke_list_timeclock_shifts():
    token = _login()
    assert token

    params = {
        "date_from": "2026-03-22",
        "date_to": "2026-03-22",
    }
    response = _get(f"{BASE_URL}/timeclock/shifts", token=token, params=params)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_smoke_list_timeclock_exceptions():
    token = _login()
    assert token

    params = {"day": "2026-03-22"}
    response = _get(f"{BASE_URL}/timeclock/exceptions", token=token, params=params)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_smoke_timesheet_summary():
    token = _login()
    assert token

    params = {
        "period_start": "2026-03-22T00:00:00+00:00",
        "period_end": "2026-03-22T23:59:59+00:00",
    }
    response = _get(f"{BASE_URL}/timeclock/timesheet-summary", token=token, params=params)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_smoke_approve_timesheet():
    token = _login()
    assert token

    employee = _create_timeclock_employee(token)
    payload = {
        "employee_id": employee["id"],
        "period_start": "2026-03-22T00:00:00+00:00",
        "period_end": "2026-03-22T23:59:59+00:00",
        "status": "approved",
        "approved_by": "smoke-user",
    }
    response = _post(f"{BASE_URL}/timeclock/timesheet-approval", token=token, json=payload)
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}


def test_smoke_get_timeclock_policy():
    token = _login()
    assert token

    response = _get(f"{BASE_URL}/timeclock/policy", token=token)
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert body["tenant_id"] == TENANT_ID


def test_smoke_update_timeclock_policy():
    token = _login()
    assert token

    payload = {
        "overtime_daily_hours": 1,
        "overtime_weekly_hours": 1,
        "max_break_minutes": 720,
        "late_tolerance_minutes": 120,
        "early_clock_in_minutes": 180,
        "geofence_required": False,
    }
    response = _put(f"{BASE_URL}/timeclock/policy", token=token, json=payload)
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}


def test_smoke_list_timeclock_alerts():
    token = _login()
    assert token

    response = _get(f"{BASE_URL}/timeclock/alerts", token=token)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_smoke_sync_timeclock_alerts():
    token = _login()
    assert token

    payload = {"day": "2026-03-22"}
    response = _post(f"{BASE_URL}/timeclock/alerts/sync", token=token, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert "created" in body


def test_smoke_resolve_timeclock_alert():
    token = _login()
    assert token

    sync_resp = _post(f"{BASE_URL}/timeclock/alerts/sync", token=token, json={"day": "2026-03-22"})
    assert sync_resp.status_code == 200, sync_resp.text

    alerts_resp = _get(f"{BASE_URL}/timeclock/alerts", token=token)
    assert alerts_resp.status_code == 200, alerts_resp.text
    alerts = alerts_resp.json()
    assert isinstance(alerts, list)

    if not alerts:
        return

    payload = {"alert_id": alerts[0]["id"]}
    response = _post(f"{BASE_URL}/timeclock/alerts/resolve", token=token, json=payload)
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}


def test_smoke_export_timeclock_csv():
    token = _login()
    assert token

    params = {
        "period_start": "2026-03-22T00:00:00+00:00",
        "period_end": "2026-03-22T23:59:59+00:00",
    }
    response = _get(f"{BASE_URL}/timeclock/export.csv", token=token, params=params)
    assert response.status_code == 200
    assert isinstance(response.text, str)
    assert response.text.strip() != ""


def test_smoke_chat_send_and_messages():
    token = _login()
    assert token

    recipient_id = _pick_chat_recipient(token)
    assert recipient_id is not None, "Expected another user in demo tenant"

    send_resp = _post(
        f"{BASE_URL}/chat/send",
        token=token,
        json={"to_user_id": recipient_id, "text": "Hello from smoke!"},
    )
    assert send_resp.status_code == 200, send_resp.text
    send_body = send_resp.json()
    assert send_body["success"] is True

    messages_resp = _post(
        f"{BASE_URL}/chat/messages",
        token=token,
        json={"with_user_id": recipient_id},
    )
    assert messages_resp.status_code == 200, messages_resp.text
    messages_body = messages_resp.json()
    assert messages_body["success"] is True
    assert isinstance(messages_body["messages"], list)