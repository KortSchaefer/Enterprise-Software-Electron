from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.database import first_row, get_supabase, rows

router = APIRouter(prefix="/timeclock", tags=["timeclock"])
EVENT_TYPES = {"clock_in", "clock_out", "break_start", "break_end"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=f"Invalid datetime: {value}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=f"Invalid date: {value}") from error


def row_dt(row: dict[str, Any], field: str) -> datetime:
    return parse_datetime(row[field])


def insert_audit_log(tenant_id: str, actor: str, action: str, details: str) -> None:
    get_supabase().table("audit_logs").insert(
        {
            "tenant_id": tenant_id,
            "actor": actor or "system",
            "action": action,
            "details": details,
        }
    ).execute()


def get_or_create_policy(tenant_id: str) -> dict[str, Any]:
    supabase = get_supabase()
    policy = first_row(supabase.table("time_policies").select("*").eq("tenant_id", tenant_id).limit(1).execute())
    if policy:
        return policy
    created = first_row(supabase.table("time_policies").insert({"tenant_id": tenant_id}).execute())
    if not created:
        raise HTTPException(status_code=500, detail="Unable to create policy.")
    return created


def get_employee(tenant_id: str, employee_id: int) -> dict[str, Any]:
    row = first_row(
        get_supabase().table("employees")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("id", employee_id)
        .limit(1)
        .execute()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Employee not found.")
    return row


def list_employee_rows(tenant_id: str, active_only: bool = False) -> list[dict[str, Any]]:
    query = get_supabase().table("employees").select("*").eq("tenant_id", tenant_id).order("full_name")
    if active_only:
        query = query.eq("is_active", 1)
    return rows(query.execute())


def list_time_events_for_employee(tenant_id: str, employee_id: int, start_dt: datetime, end_dt: datetime) -> list[dict[str, Any]]:
    return rows(
        get_supabase().table("time_events")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("employee_id", employee_id)
        .gte("occurred_at", start_dt.isoformat())
        .lte("occurred_at", end_dt.isoformat())
        .order("occurred_at")
        .execute()
    )


def list_shifts_for_range(tenant_id: str, start_dt: datetime, end_dt: datetime) -> list[dict[str, Any]]:
    return rows(
        get_supabase().table("shifts")
        .select("*")
        .eq("tenant_id", tenant_id)
        .gte("start_at", start_dt.isoformat())
        .lte("start_at", end_dt.isoformat())
        .order("start_at")
        .execute()
    )


def first_clock_in_for_shift(tenant_id: str, shift: dict[str, Any]) -> dict[str, Any] | None:
    return first_row(
        get_supabase().table("time_events")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("employee_id", shift["employee_id"])
        .eq("event_type", "clock_in")
        .gte("occurred_at", shift["start_at"])
        .lte("occurred_at", shift["end_at"])
        .order("occurred_at")
        .limit(1)
        .execute()
    )


def compute_worked_minutes(events: list[dict[str, Any]], range_start: datetime, range_end: datetime) -> int:
    events_sorted = sorted(events, key=lambda event: event["occurred_at"])
    clock_in_at = None
    break_start_at = None
    worked_seconds = 0

    for event in events_sorted:
        occurred_at = row_dt(event, "occurred_at")
        if occurred_at < range_start or occurred_at > range_end:
            continue

        if event["event_type"] == "clock_in":
            clock_in_at = occurred_at
            break_start_at = None
        elif event["event_type"] == "break_start" and clock_in_at and not break_start_at:
            break_start_at = occurred_at
        elif event["event_type"] == "break_end" and clock_in_at and break_start_at:
            if occurred_at > break_start_at:
                clock_in_at += occurred_at - break_start_at
            break_start_at = None
        elif event["event_type"] == "clock_out" and clock_in_at:
            end_at = occurred_at
            if break_start_at and end_at > break_start_at:
                end_at = break_start_at
            if end_at > clock_in_at:
                worked_seconds += int((end_at - clock_in_at).total_seconds())
            clock_in_at = None
            break_start_at = None

    return worked_seconds // 60


class EmployeeCreateRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    role: str = Field(default="staff", max_length=64)
    location: str = Field(default="", max_length=128)


class EmployeeResponse(BaseModel):
    id: int
    tenant_id: str
    full_name: str
    email: str
    role: str
    location: str
    is_active: bool


class TimeEventRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    employee_id: int
    event_type: Literal["clock_in", "clock_out", "break_start", "break_end"]
    occurred_at: str
    source: Literal["employee", "manager", "system"] = "employee"
    reason: str = Field(default="", max_length=255)
    created_by: str = Field(default="", max_length=255)


class ShiftCreateRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    employee_id: int
    start_at: str
    end_at: str
    location: str = Field(default="", max_length=128)
    role: str = Field(default="staff", max_length=64)


class ShiftResponse(BaseModel):
    id: int
    employee_id: int
    start_at: str
    end_at: str
    location: str
    role: str
    status: str


class ApprovalRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    employee_id: int
    period_start: str
    period_end: str
    status: Literal["approved", "rejected"]
    approved_by: str = Field(default="", max_length=255)


class PolicyUpdateRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    overtime_daily_hours: int = Field(ge=1, le=24)
    overtime_weekly_hours: int = Field(ge=1, le=168)
    max_break_minutes: int = Field(ge=0, le=720)
    late_tolerance_minutes: int = Field(ge=0, le=120)
    early_clock_in_minutes: int = Field(ge=0, le=180)
    geofence_required: bool = False


class AlertResolveRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    alert_id: int


class AlertSyncRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    day: str


@router.post("/employees", response_model=EmployeeResponse)
def create_employee(payload: EmployeeCreateRequest) -> EmployeeResponse:
    tenant_id = payload.tenant_id.strip()
    email = payload.email.strip().lower()
    supabase = get_supabase()

    existing = first_row(
        supabase.table("employees")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("email", email)
        .limit(1)
        .execute()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Employee email already exists for this tenant.")

    employee = first_row(
        supabase.table("employees")
        .insert(
            {
                "tenant_id": tenant_id,
                "full_name": payload.full_name.strip(),
                "email": email,
                "role": payload.role.strip(),
                "location": payload.location.strip(),
                "is_active": 1,
            }
        )
        .execute()
    )
    if not employee:
        raise HTTPException(status_code=500, detail="Employee creation failed.")

    insert_audit_log(tenant_id, "manager", "employee.create", f"employee_id={employee['id']}")
    return EmployeeResponse(
        id=employee["id"],
        tenant_id=employee["tenant_id"],
        full_name=employee["full_name"],
        email=employee["email"],
        role=employee["role"],
        location=employee["location"],
        is_active=bool(employee["is_active"]),
    )


@router.get("/employees", response_model=list[EmployeeResponse])
def list_employees(tenant_id: str) -> list[EmployeeResponse]:
    return [
        EmployeeResponse(
            id=row["id"],
            tenant_id=row["tenant_id"],
            full_name=row["full_name"],
            email=row["email"],
            role=row["role"],
            location=row["location"],
            is_active=bool(row["is_active"]),
        )
        for row in list_employee_rows(tenant_id.strip())
    ]


@router.post("/events")
def create_time_event(payload: TimeEventRequest) -> dict[str, str]:
    if payload.event_type not in EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid event_type.")

    tenant_id = payload.tenant_id.strip()
    get_employee(tenant_id, payload.employee_id)
    get_supabase().table("time_events").insert(
        {
            "tenant_id": tenant_id,
            "employee_id": payload.employee_id,
            "event_type": payload.event_type,
            "occurred_at": parse_datetime(payload.occurred_at).isoformat(),
            "source": payload.source,
            "reason": payload.reason.strip(),
            "created_by": payload.created_by.strip(),
        }
    ).execute()
    insert_audit_log(
        tenant_id,
        payload.created_by or "system",
        "time_event.create",
        f"employee_id={payload.employee_id};type={payload.event_type};reason={payload.reason}",
    )
    return {"status": "ok"}


@router.get("/live")
def live_board(tenant_id: str) -> list[dict]:
    tenant_id = tenant_id.strip()
    result = []
    for employee in list_employee_rows(tenant_id, active_only=True):
        last_event = first_row(
            get_supabase().table("time_events")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("employee_id", employee["id"])
            .order("occurred_at", desc=True)
            .limit(1)
            .execute()
        )
        status = "out"
        if last_event:
            if last_event["event_type"] == "clock_in":
                status = "in"
            elif last_event["event_type"] == "break_start":
                status = "break"
            elif last_event["event_type"] == "break_end":
                status = "in"
        result.append(
            {
                "employee_id": employee["id"],
                "full_name": employee["full_name"],
                "status": status,
                "last_event_type": last_event["event_type"] if last_event else "",
                "last_event_at": last_event["occurred_at"] if last_event else "",
            }
        )
    return result


@router.post("/shifts", response_model=ShiftResponse)
def create_shift(payload: ShiftCreateRequest) -> ShiftResponse:
    start_at = parse_datetime(payload.start_at)
    end_at = parse_datetime(payload.end_at)
    if end_at <= start_at:
        raise HTTPException(status_code=400, detail="Shift end must be after start.")

    tenant_id = payload.tenant_id.strip()
    get_employee(tenant_id, payload.employee_id)
    row = first_row(
        get_supabase().table("shifts")
        .insert(
            {
                "tenant_id": tenant_id,
                "employee_id": payload.employee_id,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "location": payload.location.strip(),
                "role": payload.role.strip(),
                "status": "scheduled",
            }
        )
        .execute()
    )
    if not row:
        raise HTTPException(status_code=500, detail="Shift creation failed.")

    insert_audit_log(tenant_id, "manager", "shift.create", f"employee_id={payload.employee_id};start={start_at.isoformat()}")
    return ShiftResponse(
        id=row["id"],
        employee_id=row["employee_id"],
        start_at=row["start_at"],
        end_at=row["end_at"],
        location=row["location"],
        role=row["role"],
        status=row["status"],
    )


@router.get("/shifts", response_model=list[ShiftResponse])
def list_shifts(tenant_id: str, date_from: str, date_to: str) -> list[ShiftResponse]:
    start_date = parse_date(date_from)
    end_date = parse_date(date_to)
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

    return [
        ShiftResponse(
            id=row["id"],
            employee_id=row["employee_id"],
            start_at=row["start_at"],
            end_at=row["end_at"],
            location=row["location"],
            role=row["role"],
            status=row["status"],
        )
        for row in list_shifts_for_range(tenant_id.strip(), start_dt, end_dt)
    ]


@router.get("/exceptions")
def list_exceptions(tenant_id: str, day: str) -> list[dict]:
    tenant_id = tenant_id.strip()
    target_day = parse_date(day)
    start_dt = datetime.combine(target_day, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(target_day, time.max, tzinfo=timezone.utc)

    policy = get_or_create_policy(tenant_id)
    exceptions = []
    for shift in list_shifts_for_range(tenant_id, start_dt, end_dt):
        first_event = first_clock_in_for_shift(tenant_id, shift)
        if not first_event:
            exceptions.append(
                {
                    "type": "no_show",
                    "employee_id": shift["employee_id"],
                    "message": "No clock-in during scheduled shift.",
                }
            )
            continue

        minutes_late = int((row_dt(first_event, "occurred_at") - row_dt(shift, "start_at")).total_seconds() // 60)
        if minutes_late > policy["late_tolerance_minutes"]:
            exceptions.append(
                {
                    "type": "late_arrival",
                    "employee_id": shift["employee_id"],
                    "message": f"Late by {minutes_late} minutes.",
                }
            )

    for employee in list_employee_rows(tenant_id, active_only=True):
        events = list_time_events_for_employee(tenant_id, employee["id"], start_dt, end_dt)
        worked_minutes = compute_worked_minutes(events, start_dt, end_dt)
        if worked_minutes > policy["overtime_daily_hours"] * 60:
            exceptions.append(
                {
                    "type": "overtime_risk",
                    "employee_id": employee["id"],
                    "message": f"Daily hours {worked_minutes / 60:.2f} exceed threshold.",
                }
            )
    return exceptions


@router.get("/timesheet-summary")
def timesheet_summary(tenant_id: str, period_start: str, period_end: str) -> list[dict]:
    tenant_id = tenant_id.strip()
    start_dt = parse_datetime(period_start)
    end_dt = parse_datetime(period_end)
    output = []
    for employee in list_employee_rows(tenant_id, active_only=True):
        events = list_time_events_for_employee(tenant_id, employee["id"], start_dt, end_dt)
        minutes = compute_worked_minutes(events, start_dt, end_dt)
        approval = first_row(
            get_supabase().table("timesheet_approvals")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("employee_id", employee["id"])
            .eq("period_start", start_dt.isoformat())
            .eq("period_end", end_dt.isoformat())
            .limit(1)
            .execute()
        )
        output.append(
            {
                "employee_id": employee["id"],
                "full_name": employee["full_name"],
                "hours": round(minutes / 60, 2),
                "status": approval["status"] if approval else "pending",
            }
        )
    return output


@router.post("/timesheet-approval")
def approve_timesheet(payload: ApprovalRequest) -> dict[str, str]:
    tenant_id = payload.tenant_id.strip()
    start_dt = parse_datetime(payload.period_start)
    end_dt = parse_datetime(payload.period_end)
    supabase = get_supabase()
    row = first_row(
        supabase.table("timesheet_approvals")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("employee_id", payload.employee_id)
        .eq("period_start", start_dt.isoformat())
        .eq("period_end", end_dt.isoformat())
        .limit(1)
        .execute()
    )
    approval_payload = {
        "tenant_id": tenant_id,
        "employee_id": payload.employee_id,
        "period_start": start_dt.isoformat(),
        "period_end": end_dt.isoformat(),
        "status": payload.status,
        "approved_by": payload.approved_by.strip(),
        "approved_at": utc_now_iso(),
    }
    if row:
        supabase.table("timesheet_approvals").update(approval_payload).eq("id", row["id"]).execute()
    else:
        supabase.table("timesheet_approvals").insert(approval_payload).execute()
    insert_audit_log(
        tenant_id,
        payload.approved_by or "manager",
        "timesheet.approval",
        f"employee_id={payload.employee_id};status={payload.status}",
    )
    return {"status": "ok"}


@router.get("/policy")
def get_policy(tenant_id: str) -> dict:
    row = get_or_create_policy(tenant_id.strip())
    return {
        "tenant_id": row["tenant_id"],
        "overtime_daily_hours": row["overtime_daily_hours"],
        "overtime_weekly_hours": row["overtime_weekly_hours"],
        "max_break_minutes": row["max_break_minutes"],
        "late_tolerance_minutes": row["late_tolerance_minutes"],
        "early_clock_in_minutes": row["early_clock_in_minutes"],
        "geofence_required": bool(row["geofence_required"]),
    }


@router.put("/policy")
def update_policy(payload: PolicyUpdateRequest) -> dict[str, str]:
    row = get_or_create_policy(payload.tenant_id.strip())
    get_supabase().table("time_policies").update(
        {
            "overtime_daily_hours": payload.overtime_daily_hours,
            "overtime_weekly_hours": payload.overtime_weekly_hours,
            "max_break_minutes": payload.max_break_minutes,
            "late_tolerance_minutes": payload.late_tolerance_minutes,
            "early_clock_in_minutes": payload.early_clock_in_minutes,
            "geofence_required": 1 if payload.geofence_required else 0,
            "updated_at": utc_now_iso(),
        }
    ).eq("id", row["id"]).execute()
    insert_audit_log(row["tenant_id"], "manager", "policy.update", "timeclock policy updated")
    return {"status": "ok"}


@router.get("/alerts")
def list_alerts(tenant_id: str) -> list[dict]:
    return [
        {
            "id": row["id"],
            "employee_id": row["employee_id"],
            "alert_type": row["alert_type"],
            "message": row["message"],
            "resolved": bool(row["resolved"]),
            "created_at": row["created_at"],
        }
        for row in rows(
            get_supabase().table("manager_alerts")
            .select("*")
            .eq("tenant_id", tenant_id.strip())
            .order("created_at", desc=True)
            .execute()
        )
    ]


@router.post("/alerts/sync")
def sync_alerts(payload: AlertSyncRequest) -> dict[str, int]:
    tenant_id = payload.tenant_id.strip()
    target_day = parse_date(payload.day)
    start_dt = datetime.combine(target_day, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(target_day, time.max, tzinfo=timezone.utc)

    policy = get_or_create_policy(tenant_id)
    supabase = get_supabase()
    created = 0
    for shift in list_shifts_for_range(tenant_id, start_dt, end_dt):
        first_event = first_clock_in_for_shift(tenant_id, shift)
        to_create = None
        if not first_event:
            to_create = ("no_show", "No clock-in during scheduled shift.")
        else:
            minutes_late = int((row_dt(first_event, "occurred_at") - row_dt(shift, "start_at")).total_seconds() // 60)
            if minutes_late > policy["late_tolerance_minutes"]:
                to_create = ("late_arrival", f"Late by {minutes_late} minutes.")

        if not to_create:
            continue

        exists = first_row(
            supabase.table("manager_alerts")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("employee_id", shift["employee_id"])
            .eq("alert_type", to_create[0])
            .eq("resolved", 0)
            .limit(1)
            .execute()
        )
        if exists:
            continue

        supabase.table("manager_alerts").insert(
            {
                "tenant_id": tenant_id,
                "employee_id": shift["employee_id"],
                "alert_type": to_create[0],
                "message": to_create[1],
                "resolved": 0,
            }
        ).execute()
        created += 1

    return {"created": created}


@router.post("/alerts/resolve")
def resolve_alert(payload: AlertResolveRequest) -> dict[str, str]:
    row = first_row(
        get_supabase().table("manager_alerts")
        .select("id")
        .eq("id", payload.alert_id)
        .eq("tenant_id", payload.tenant_id.strip())
        .limit(1)
        .execute()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found.")

    get_supabase().table("manager_alerts").update({"resolved": 1}).eq("id", row["id"]).execute()
    return {"status": "ok"}


@router.get("/export.csv")
def export_timesheet_csv(tenant_id: str, period_start: str, period_end: str) -> Response:
    tenant_id = tenant_id.strip()
    start_dt = parse_datetime(period_start)
    end_dt = parse_datetime(period_end)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["employee_id", "employee_name", "hours", "period_start", "period_end"])
    for employee in list_employee_rows(tenant_id, active_only=True):
        events = list_time_events_for_employee(tenant_id, employee["id"], start_dt, end_dt)
        minutes = compute_worked_minutes(events, start_dt, end_dt)
        writer.writerow([employee["id"], employee["full_name"], round(minutes / 60, 2), start_dt.isoformat(), end_dt.isoformat()])
    return Response(content=output.getvalue(), media_type="text/csv")
