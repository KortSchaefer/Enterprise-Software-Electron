from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from app.database import first_row, get_supabase, rows
from app.security import hash_password

TENANT_ID = "demo-tenant"
USER_PASSWORD = "Password123!"


def upsert_by_keys(table: str, payload: dict, match_keys: list[str]) -> dict:
    supabase = get_supabase()
    query = supabase.table(table).select("*")
    for key in match_keys:
        query = query.eq(key, payload[key])
    existing = first_row(query.limit(1).execute())
    if existing:
        return existing

    created = first_row(supabase.table(table).insert(payload).execute())
    if not created:
        raise RuntimeError(f"Failed to insert into {table}")
    return created


def seed_users() -> dict[str, dict]:
    definitions = [
        ("admin", "admin@demo-tenant.local"),
        ("alice", "alice@demo-tenant.local"),
        ("bob", "bob@demo-tenant.local"),
    ]
    users: dict[str, dict] = {}

    for key, email in definitions:
        users[key] = upsert_by_keys(
            "users",
            {
                "tenant_id": TENANT_ID,
                "email": email,
                "password_hash": hash_password(USER_PASSWORD),
            },
            ["tenant_id", "email"],
        )

    return users


def seed_apps() -> None:
    for app_key in ("inventory", "timeclock", "chat"):
        upsert_by_keys("tenant_apps", {"tenant_id": TENANT_ID, "app_key": app_key}, ["tenant_id", "app_key"])


def seed_inventory() -> None:
    definitions = [
        {
            "sku": "LAPTOP-15",
            "name": "15in Laptop",
            "description": "Primary workstation for office staff.",
            "quantity_on_hand": 14,
            "reorder_point": 5,
        },
        {
            "sku": "DOCK-USBC",
            "name": "USB-C Dock",
            "description": "Docking station for desks and meeting rooms.",
            "quantity_on_hand": 6,
            "reorder_point": 4,
        },
        {
            "sku": "BADGE-RFID",
            "name": "RFID Access Badge",
            "description": "Employee access badge stock.",
            "quantity_on_hand": 42,
            "reorder_point": 10,
        },
    ]

    for item in definitions:
        row = upsert_by_keys(
            "inventory_items",
            {
                "tenant_id": TENANT_ID,
                **item,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            ["tenant_id", "sku"],
        )
        existing_movement = first_row(
            get_supabase().table("inventory_movements")
            .select("id")
            .eq("tenant_id", TENANT_ID)
            .eq("item_id", row["id"])
            .eq("reason", "initial seed")
            .limit(1)
            .execute()
        )
        if not existing_movement:
            get_supabase().table("inventory_movements").insert(
                {
                    "item_id": row["id"],
                    "tenant_id": TENANT_ID,
                    "change_amount": row["quantity_on_hand"],
                    "reason": "initial seed",
                    "performed_by": "seed-script",
                }
            ).execute()


def seed_employees() -> dict[str, dict]:
    definitions = [
        {
            "key": "alice",
            "full_name": "Alice Johnson",
            "email": "alice.johnson@demo-tenant.local",
            "role": "manager",
            "location": "Chicago HQ",
        },
        {
            "key": "bob",
            "full_name": "Bob Smith",
            "email": "bob.smith@demo-tenant.local",
            "role": "staff",
            "location": "Chicago HQ",
        },
    ]
    employees: dict[str, dict] = {}

    for definition in definitions:
        employees[definition["key"]] = upsert_by_keys(
            "employees",
            {
                "tenant_id": TENANT_ID,
                "full_name": definition["full_name"],
                "email": definition["email"],
                "role": definition["role"],
                "location": definition["location"],
                "is_active": 1,
            },
            ["tenant_id", "email"],
        )

    return employees


def seed_policy() -> None:
    upsert_by_keys("time_policies", {"tenant_id": TENANT_ID}, ["tenant_id"])


def seed_schedule(employees: dict[str, dict]) -> None:
    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)

    schedule_definitions = [
        (
            employees["alice"],
            datetime.combine(yesterday, time(hour=13, minute=0), tzinfo=timezone.utc),
            datetime.combine(yesterday, time(hour=21, minute=0), tzinfo=timezone.utc),
            "manager",
        ),
        (
            employees["bob"],
            datetime.combine(today, time(hour=14, minute=0), tzinfo=timezone.utc),
            datetime.combine(today, time(hour=22, minute=0), tzinfo=timezone.utc),
            "staff",
        ),
    ]

    for employee, start_at, end_at, role in schedule_definitions:
        upsert_by_keys(
            "shifts",
            {
                "tenant_id": TENANT_ID,
                "employee_id": employee["id"],
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "location": employee["location"],
                "role": role,
                "status": "scheduled",
            },
            ["tenant_id", "employee_id", "start_at", "end_at"],
        )

    event_definitions = [
        (
            employees["alice"],
            "clock_in",
            datetime.combine(yesterday, time(hour=12, minute=56), tzinfo=timezone.utc),
            "Arrived early",
        ),
        (
            employees["alice"],
            "clock_out",
            datetime.combine(yesterday, time(hour=21, minute=3), tzinfo=timezone.utc),
            "Completed shift",
        ),
        (
            employees["bob"],
            "clock_in",
            datetime.combine(today, time(hour=14, minute=4), tzinfo=timezone.utc),
            "Started morning shift",
        ),
    ]

    for employee, event_type, occurred_at, reason in event_definitions:
        upsert_by_keys(
            "time_events",
            {
                "tenant_id": TENANT_ID,
                "employee_id": employee["id"],
                "event_type": event_type,
                "occurred_at": occurred_at.isoformat(),
                "source": "seed",
                "reason": reason,
                "created_by": "seed-script",
            },
            ["tenant_id", "employee_id", "event_type", "occurred_at"],
        )


def seed_alerts_and_approvals(employees: dict[str, dict]) -> None:
    now = datetime.now(timezone.utc)
    period_start = datetime.combine(now.date() - timedelta(days=7), time.min, tzinfo=timezone.utc)
    period_end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)

    upsert_by_keys(
        "timesheet_approvals",
        {
            "tenant_id": TENANT_ID,
            "employee_id": employees["alice"]["id"],
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "status": "approved",
            "approved_by": "admin@demo-tenant.local",
            "approved_at": now.isoformat(),
        },
        ["tenant_id", "employee_id", "period_start", "period_end"],
    )

    upsert_by_keys(
        "manager_alerts",
        {
            "tenant_id": TENANT_ID,
            "employee_id": employees["bob"]["id"],
            "alert_type": "late_clock_in",
            "message": "Bob Smith clocked in after the scheduled start time.",
            "resolved": 0,
        },
        ["tenant_id", "employee_id", "alert_type", "resolved"],
    )


def seed_messages(users: dict[str, dict]) -> None:
    definitions = [
        (users["alice"]["id"], users["bob"]["id"], "Morning inventory check is complete."),
        (users["bob"]["id"], users["alice"]["id"], "Received. I am updating the reorder list now."),
        (users["admin"]["id"], users["alice"]["id"], "Please review the staffing exceptions before payroll export."),
    ]

    for from_user_id, to_user_id, text in definitions:
        upsert_by_keys(
            "messages",
            {
                "tenant_id": TENANT_ID,
                "from_user_id": from_user_id,
                "to_user_id": to_user_id,
                "text": text,
            },
            ["tenant_id", "from_user_id", "to_user_id", "text"],
        )


def print_summary() -> None:
    supabase = get_supabase()
    counts = {
        "users": len(rows(supabase.table("users").select("id").eq("tenant_id", TENANT_ID).execute())),
        "apps": len(rows(supabase.table("tenant_apps").select("id").eq("tenant_id", TENANT_ID).execute())),
        "inventory_items": len(rows(supabase.table("inventory_items").select("id").eq("tenant_id", TENANT_ID).execute())),
        "employees": len(rows(supabase.table("employees").select("id").eq("tenant_id", TENANT_ID).execute())),
        "messages": len(rows(supabase.table("messages").select("id").eq("tenant_id", TENANT_ID).execute())),
    }

    print(f"Seed complete for tenant '{TENANT_ID}'.")
    print(f"Default user password: {USER_PASSWORD}")
    for label, value in counts.items():
        print(f"{label}: {value}")


def main() -> None:
    users = seed_users()
    seed_apps()
    seed_inventory()
    employees = seed_employees()
    seed_policy()
    seed_schedule(employees)
    seed_alerts_and_approvals(employees)
    seed_messages(users)
    print_summary()


if __name__ == "__main__":
    main()
