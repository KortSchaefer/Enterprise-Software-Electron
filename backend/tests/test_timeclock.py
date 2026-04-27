from fastapi.testclient import TestClient


PERIOD_START = "2026-03-22T00:00:00+00:00"
PERIOD_END = "2026-03-22T23:59:59+00:00"
DAY = "2026-03-22"


def _create_employee(client: TestClient, email: str = "jane@example.com", full_name: str = "Jane Doe"):
    response = client.post(
        "/timeclock/employees",
        json={
            "full_name": full_name,
            "email": email,
            "role": "staff",
            "location": "Main",
        },
    )
    assert response.status_code == 200
    return response.json()


def _create_shift(client: TestClient, employee_id: int, start_at: str = PERIOD_START, end_at: str = PERIOD_END):
    response = client.post(
        "/timeclock/shifts",
        json={
            "employee_id": employee_id,
            "start_at": start_at,
            "end_at": end_at,
            "location": "Main",
            "role": "staff",
        },
    )
    assert response.status_code == 200
    return response.json()


def _create_event(
    client: TestClient,
    employee_id: int,
    event_type: str,
    occurred_at: str,
    source: str = "employee",
    reason: str = "",
    created_by: str = "",
):
    response = client.post(
        "/timeclock/events",
        json={
            "employee_id": employee_id,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "source": source,
            "reason": reason,
            "created_by": created_by,
        },
    )
    return response


def test_create_employee_success(client: TestClient):
    response = client.post(
        "/timeclock/employees",
        json={
            "full_name": "  Jane Doe  ",
            "email": "  JANE@EXAMPLE.COM  ",
            "role": " staff ",
            "location": " Main ",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["tenant_id"].startswith("tenant-test-")
    assert data["full_name"] == "Jane Doe"
    assert data["email"] == "jane@example.com"
    assert data["role"] == "staff"
    assert data["location"] == "Main"
    assert data["is_active"] is True
    assert "id" in data


def test_create_employee_duplicate_email_returns_409(client: TestClient):
    _create_employee(client, email="dup@example.com", full_name="First Jane")

    response = client.post(
        "/timeclock/employees",
        json={
            "full_name": "Second Jane",
            "email": "dup@example.com",
            "role": "staff",
            "location": "Main",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Employee email already exists for this tenant."


def test_list_employees_returns_created_employee(client: TestClient):
    created = _create_employee(client, email="listme@example.com", full_name="List Me")

    response = client.get("/timeclock/employees")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert any(row["id"] == created["id"] and row["email"] == "listme@example.com" for row in data)


def test_create_time_event_success(client: TestClient):
    employee = _create_employee(client, email="eventsuccess@example.com")

    response = _create_event(
        client,
        employee_id=employee["id"],
        event_type="clock_in",
        occurred_at=PERIOD_START,
        reason="Start shift",
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_time_event_invalid_datetime_returns_400(client: TestClient):
    employee = _create_employee(client, email="baddatetime@example.com")

    response = _create_event(
        client,
        employee_id=employee["id"],
        event_type="clock_in",
        occurred_at="not-a-datetime",
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Invalid datetime:")


def test_create_time_event_missing_employee_returns_404(client: TestClient):
    response = _create_event(
        client,
        employee_id=999999,
        event_type="clock_in",
        occurred_at=PERIOD_START,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Employee not found."


def test_live_board_shows_in_status_after_clock_in(client: TestClient):
    employee = _create_employee(client, email="livein@example.com")

    create_event = _create_event(
        client,
        employee_id=employee["id"],
        event_type="clock_in",
        occurred_at=PERIOD_START,
    )
    assert create_event.status_code == 200

    response = client.get("/timeclock/live")
    assert response.status_code == 200

    data = response.json()
    match = next(row for row in data if row["employee_id"] == employee["id"])
    assert match["status"] == "in"
    assert match["last_event_type"] == "clock_in"


def test_live_board_shows_break_status_after_break_start(client: TestClient):
    employee = _create_employee(client, email="livebreak@example.com")

    assert _create_event(client, employee["id"], "clock_in", "2026-03-22T08:00:00+00:00").status_code == 200
    assert _create_event(client, employee["id"], "break_start", "2026-03-22T10:00:00+00:00").status_code == 200

    response = client.get("/timeclock/live")
    assert response.status_code == 200

    data = response.json()
    match = next(row for row in data if row["employee_id"] == employee["id"])
    assert match["status"] == "break"
    assert match["last_event_type"] == "break_start"


def test_live_board_shows_out_status_with_no_events(client: TestClient):
    employee = _create_employee(client, email="liveout@example.com")

    response = client.get("/timeclock/live")
    assert response.status_code == 200

    data = response.json()
    match = next(row for row in data if row["employee_id"] == employee["id"])
    assert match["status"] == "out"
    assert match["last_event_type"] == ""
    assert match["last_event_at"] == ""


def test_create_shift_success(client: TestClient):
    employee = _create_employee(client, email="shiftcreate@example.com")

    response = client.post(
        "/timeclock/shifts",
        json={
            "employee_id": employee["id"],
            "start_at": PERIOD_START,
            "end_at": PERIOD_END,
            "location": "Front Desk",
            "role": "staff",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["employee_id"] == employee["id"]
    assert data["location"] == "Front Desk"
    assert data["role"] == "staff"
    assert data["status"] == "scheduled"


def test_create_shift_end_before_start_returns_400(client: TestClient):
    employee = _create_employee(client, email="shiftbad@example.com")

    response = client.post(
        "/timeclock/shifts",
        json={
            "employee_id": employee["id"],
            "start_at": PERIOD_END,
            "end_at": PERIOD_START,
            "location": "Main",
            "role": "staff",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Shift end must be after start."


def test_list_shifts_returns_created_shift(client: TestClient):
    employee = _create_employee(client, email="listshift@example.com")
    created_shift = _create_shift(client, employee["id"])

    response = client.get("/timeclock/shifts", params={"date_from": DAY, "date_to": DAY})
    assert response.status_code == 200

    data = response.json()
    assert any(row["id"] == created_shift["id"] for row in data)


def test_get_policy_returns_policy(client: TestClient):
    response = client.get("/timeclock/policy")
    assert response.status_code == 200

    data = response.json()
    assert data["tenant_id"].startswith("tenant-test-")
    assert "overtime_daily_hours" in data
    assert "overtime_weekly_hours" in data
    assert "max_break_minutes" in data
    assert "late_tolerance_minutes" in data
    assert "early_clock_in_minutes" in data
    assert "geofence_required" in data


def test_update_policy_success(client: TestClient):
    response = client.put(
        "/timeclock/policy",
        json={
            "overtime_daily_hours": 10,
            "overtime_weekly_hours": 45,
            "max_break_minutes": 30,
            "late_tolerance_minutes": 7,
            "early_clock_in_minutes": 15,
            "geofence_required": True,
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    verify = client.get("/timeclock/policy")
    assert verify.status_code == 200
    data = verify.json()
    assert data["overtime_daily_hours"] == 10
    assert data["overtime_weekly_hours"] == 45
    assert data["max_break_minutes"] == 30
    assert data["late_tolerance_minutes"] == 7
    assert data["early_clock_in_minutes"] == 15
    assert data["geofence_required"] is True


def test_update_policy_validation_error(client: TestClient):
    response = client.put(
        "/timeclock/policy",
        json={
            "overtime_daily_hours": 0,
            "overtime_weekly_hours": 45,
            "max_break_minutes": 30,
            "late_tolerance_minutes": 7,
            "early_clock_in_minutes": 15,
            "geofence_required": False,
        },
    )
    assert response.status_code == 422


def test_timesheet_summary_returns_pending_status(client: TestClient):
    employee = _create_employee(client, email="pendingstatus@example.com")
    assert _create_event(client, employee["id"], "clock_in", "2026-03-22T08:00:00+00:00").status_code == 200
    assert _create_event(client, employee["id"], "clock_out", "2026-03-22T16:00:00+00:00").status_code == 200

    response = client.get(
        "/timeclock/timesheet-summary",
        params={
            "period_start": PERIOD_START,
            "period_end": PERIOD_END,
        },
    )
    assert response.status_code == 200

    data = response.json()
    row = next(item for item in data if item["employee_id"] == employee["id"])
    assert row["status"] == "pending"
    assert row["hours"] == 8.0


def test_timesheet_approval_success(client: TestClient):
    employee = _create_employee(client, email="approvalsuccess@example.com")

    response = client.post(
        "/timeclock/timesheet-approval",
        json={
            "employee_id": employee["id"],
            "period_start": PERIOD_START,
            "period_end": PERIOD_END,
            "status": "approved",
            "approved_by": "",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    summary = client.get(
        "/timeclock/timesheet-summary",
        params={
            "period_start": PERIOD_START,
            "period_end": PERIOD_END,
        },
    )
    assert summary.status_code == 200
    data = summary.json()
    row = next(item for item in data if item["employee_id"] == employee["id"])
    assert row["status"] == "approved"


def test_exceptions_returns_no_show_for_scheduled_shift_without_clock_in(client: TestClient):
    employee = _create_employee(client, email="noshow@example.com")
    _create_shift(client, employee["id"])

    response = client.get("/timeclock/exceptions", params={"day": DAY})
    assert response.status_code == 200

    data = response.json()
    assert any(
        row["employee_id"] == employee["id"] and row["type"] == "no_show"
        for row in data
    )


def test_alerts_sync_creates_alert_and_resolve_marks_it_resolved(client: TestClient):
    employee = _create_employee(client, email="alertsync@example.com")
    _create_shift(client, employee["id"])

    sync_response = client.post("/timeclock/alerts/sync", json={"day": DAY})
    assert sync_response.status_code == 200
    assert "created" in sync_response.json()

    alerts_response = client.get("/timeclock/alerts")
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()

    alert = next(
        row for row in alerts
        if row["employee_id"] == employee["id"] and row["alert_type"] == "no_show"
    )

    resolve_response = client.post(
        "/timeclock/alerts/resolve",
        json={"alert_id": alert["id"]},
    )
    assert resolve_response.status_code == 200
    assert resolve_response.json() == {"status": "ok"}


def test_resolve_alert_not_found(client: TestClient):
    response = client.post("/timeclock/alerts/resolve", json={"alert_id": 999999})
    assert response.status_code == 404
    assert response.json()["detail"] == "Alert not found."


def test_export_csv_returns_csv(client: TestClient):
    employee = _create_employee(client, email="csvexport@example.com")
    assert _create_event(client, employee["id"], "clock_in", "2026-03-22T08:00:00+00:00").status_code == 200
    assert _create_event(client, employee["id"], "clock_out", "2026-03-22T16:00:00+00:00").status_code == 200

    response = client.get(
        "/timeclock/export.csv",
        params={
            "period_start": PERIOD_START,
            "period_end": PERIOD_END,
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "employee_id,employee_name,hours,period_start,period_end" in response.text
    assert "csvexport@example.com" not in response.text


def test_export_csv_empty_range_returns_header(client: TestClient):
    response = client.get(
        "/timeclock/export.csv",
        params={
            "period_start": "2026-04-01T00:00:00+00:00",
            "period_end": "2026-04-01T23:59:59+00:00",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "employee_id,employee_name,hours,period_start,period_end" in response.text