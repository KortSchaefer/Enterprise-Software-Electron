from __future__ import annotations

import argparse
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


def seed_bootstrap(tenant_id: str) -> None:
    for app_key in ("inventory", "timeclock", "chat", "pos"):
        upsert_by_keys("tenant_apps", {"tenant_id": tenant_id, "app_key": app_key}, ["tenant_id", "app_key"])
    upsert_by_keys("time_policies", {"tenant_id": tenant_id}, ["tenant_id"])
    print(f"Bootstrap seed complete for tenant '{tenant_id}'.")


def seed_users() -> dict[str, dict]:
    definitions = [
        ("admin", "admin@demo-tenant.local", "admin"),
        ("alice", "alice@demo-tenant.local", "manager"),
        ("bob", "bob@demo-tenant.local", "staff"),
    ]
    users: dict[str, dict] = {}

    for key, email, role in definitions:
        user = upsert_by_keys(
            "users",
            {"tenant_id": TENANT_ID, "email": email, "password_hash": hash_password(USER_PASSWORD)},
            ["tenant_id", "email"],
        )
        upsert_by_keys(
            "tenant_memberships",
            {"tenant_id": TENANT_ID, "user_id": user["id"], "role": role, "is_active": 1},
            ["tenant_id", "user_id"],
        )
        users[key] = user

    return users


def seed_inventory() -> None:
    definitions = [
        {"sku": "LAPTOP-15", "name": "15in Laptop", "description": "Primary workstation for office staff.", "quantity_on_hand": 14, "reorder_point": 5},
        {"sku": "DOCK-USBC", "name": "USB-C Dock", "description": "Docking station for desks and meeting rooms.", "quantity_on_hand": 6, "reorder_point": 4},
        {"sku": "BADGE-RFID", "name": "RFID Access Badge", "description": "Employee access badge stock.", "quantity_on_hand": 42, "reorder_point": 10},
    ]

    for item in definitions:
        row = upsert_by_keys(
            "inventory_items",
            {"tenant_id": TENANT_ID, **item, "updated_at": datetime.now(timezone.utc).isoformat()},
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
        {"key": "alice", "full_name": "Alice Johnson", "email": "alice.johnson@demo-tenant.local", "role": "manager", "location": "Chicago HQ"},
        {"key": "bob", "full_name": "Bob Smith", "email": "bob.smith@demo-tenant.local", "role": "staff", "location": "Chicago HQ"},
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


def seed_schedule(employees: dict[str, dict]) -> None:
    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)
    schedule_definitions = [
        (employees["alice"], datetime.combine(yesterday, time(hour=13, minute=0), tzinfo=timezone.utc), datetime.combine(yesterday, time(hour=21, minute=0), tzinfo=timezone.utc), "manager"),
        (employees["bob"], datetime.combine(today, time(hour=14, minute=0), tzinfo=timezone.utc), datetime.combine(today, time(hour=22, minute=0), tzinfo=timezone.utc), "staff"),
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
        (employees["alice"], "clock_in", datetime.combine(yesterday, time(hour=12, minute=56), tzinfo=timezone.utc), "Arrived early"),
        (employees["alice"], "clock_out", datetime.combine(yesterday, time(hour=21, minute=3), tzinfo=timezone.utc), "Completed shift"),
        (employees["bob"], "clock_in", datetime.combine(today, time(hour=14, minute=4), tzinfo=timezone.utc), "Started morning shift"),
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
            {"tenant_id": TENANT_ID, "from_user_id": from_user_id, "to_user_id": to_user_id, "text": text},
            ["tenant_id", "from_user_id", "to_user_id", "text"],
        )


def seed_pos(users: dict[str, dict]) -> None:
    category_definitions = [
        ("Steaks", 10),
        ("Drinks", 20),
        ("Appetizers", 30),
        ("Sides", 40),
    ]
    categories: dict[str, dict] = {}
    for name, sort_order in category_definitions:
        categories[name] = upsert_by_keys(
            "pos_menu_categories",
            {
                "tenant_id": TENANT_ID,
                "name": name,
                "sort_order": sort_order,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            ["tenant_id", "name"],
        )

    menu_item_definitions = [
        ("Steaks", "8 oz Sirloin", "Signature sirloin cut.", 2299, 10),
        ("Steaks", "12 oz Ribeye", "Marbled ribeye with herb butter.", 3199, 20),
        ("Steaks", "Roadkill", "Smothered chopped steak.", 1899, 30),
        ("Drinks", "Water", "Still water.", 299, 10),
        ("Drinks", "Coke", "Classic fountain soda.", 349, 20),
        ("Drinks", "Island Cooler", "House mocktail.", 599, 30),
        ("Appetizers", "Cactus Blossom", "Fried onion appetizer.", 899, 10),
        ("Sides", "Cheese Fries", "Loaded cheese fries.", 699, 10),
    ]
    menu_items: dict[str, dict] = {}
    for category_name, item_name, description, price_cents, sort_order in menu_item_definitions:
        payload = {
            "tenant_id": TENANT_ID,
            "category_id": categories[category_name]["id"],
            "name": item_name,
            "description": description,
            "price_cents": 99 if price_cents <= 0 else price_cents,
            "is_active": 1,
            "sort_order": sort_order,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        menu_items[item_name] = upsert_by_keys("pos_menu_items", payload, ["tenant_id", "category_id", "name"])

    now = datetime.now(timezone.utc)
    table_definitions = [
        {
            "table_number": "122",
            "guest_count": 6,
            "status": "firing",
            "opened_at": (now - timedelta(minutes=24)).isoformat(),
            "updated_at": (now - timedelta(minutes=1)).isoformat(),
            "items": [
                ("8 oz Sirloin", 1),
                ("12 oz Ribeye", 1),
                ("Roadkill", 1),
                ("Water", 4),
                ("Coke", 1),
                ("Island Cooler", 2),
                ("Cactus Blossom", 1),
                ("Cheese Fries", 1),
            ],
            "print_minutes_ago": 5,
        },
        {
            "table_number": "111",
            "guest_count": 2,
            "status": "ready",
            "opened_at": (now - timedelta(minutes=42)).isoformat(),
            "updated_at": (now - timedelta(minutes=2)).isoformat(),
            "items": [
                ("8 oz Sirloin", 2),
                ("Water", 2),
            ],
            "print_minutes_ago": 4,
        },
        {
            "table_number": "121",
            "guest_count": 5,
            "status": "open",
            "opened_at": (now - timedelta(minutes=2)).isoformat(),
            "updated_at": (now - timedelta(minutes=2)).isoformat(),
            "items": [],
            "print_minutes_ago": None,
        },
    ]

    for definition in table_definitions:
        table_row = upsert_by_keys(
            "pos_tables",
            {
                "tenant_id": TENANT_ID,
                "table_number": definition["table_number"],
                "guest_count": definition["guest_count"],
                "status": definition["status"],
                "assigned_to_user_id": users["alice"]["id"],
                "opened_at": definition["opened_at"],
                "updated_at": definition["updated_at"],
                "closed_at": None,
            },
            ["tenant_id", "table_number"],
        )
        subtotal_cents = 0
        ticket_row = upsert_by_keys(
            "pos_tickets",
            {
                "tenant_id": TENANT_ID,
                "table_id": table_row["id"],
                "status": definition["status"],
                "subtotal_cents": 0,
                "kitchen_note": "",
                "printed_at": None,
                "updated_at": definition["updated_at"],
            },
            ["tenant_id", "table_id"],
        )
        for item_name, quantity in definition["items"]:
            menu_item = menu_items[item_name]
            price_cents = menu_item["price_cents"]
            line_total = price_cents * quantity
            subtotal_cents += line_total
            upsert_by_keys(
                "pos_ticket_items",
                {
                    "tenant_id": TENANT_ID,
                    "ticket_id": ticket_row["id"],
                    "menu_item_id": menu_item["id"],
                    "item_name_snapshot": item_name,
                    "unit_price_cents": price_cents,
                    "quantity": quantity,
                    "line_total_cents": line_total,
                    "updated_at": definition["updated_at"],
                },
                ["tenant_id", "ticket_id", "menu_item_id", "item_name_snapshot"],
            )
        get_supabase().table("pos_tickets").update({"subtotal_cents": subtotal_cents, "updated_at": definition["updated_at"]}).eq("id", ticket_row["id"]).execute()
        get_supabase().table("pos_tables").update({"updated_at": definition["updated_at"]}).eq("id", table_row["id"]).execute()
        if definition["print_minutes_ago"] is not None:
            printed_at = (now - timedelta(minutes=definition["print_minutes_ago"])).isoformat()
            upsert_by_keys(
                "pos_ticket_prints",
                {
                    "tenant_id": TENANT_ID,
                    "ticket_id": ticket_row["id"],
                    "printed_by": "alice@demo-tenant.local",
                    "printed_at": printed_at,
                    "print_type": "guest_check",
                },
                ["tenant_id", "ticket_id", "printed_by", "printed_at"],
            )
            get_supabase().table("pos_tickets").update({"printed_at": printed_at}).eq("id", ticket_row["id"]).execute()


def print_demo_summary() -> None:
    supabase = get_supabase()
    counts = {
        "users": len(rows(supabase.table("users").select("id").eq("tenant_id", TENANT_ID).execute())),
        "memberships": len(rows(supabase.table("tenant_memberships").select("id").eq("tenant_id", TENANT_ID).execute())),
        "apps": len(rows(supabase.table("tenant_apps").select("id").eq("tenant_id", TENANT_ID).execute())),
        "inventory_items": len(rows(supabase.table("inventory_items").select("id").eq("tenant_id", TENANT_ID).execute())),
        "employees": len(rows(supabase.table("employees").select("id").eq("tenant_id", TENANT_ID).execute())),
        "messages": len(rows(supabase.table("messages").select("id").eq("tenant_id", TENANT_ID).execute())),
        "pos_tables": len(rows(supabase.table("pos_tables").select("id").eq("tenant_id", TENANT_ID).execute())),
    }
    print(f"Demo seed complete for tenant '{TENANT_ID}'.")
    print(f"Default user password: {USER_PASSWORD}")
    for label, value in counts.items():
        print(f"{label}: {value}")


def seed_demo() -> None:
    seed_bootstrap(TENANT_ID)
    users = seed_users()
    seed_inventory()
    employees = seed_employees()
    seed_schedule(employees)
    seed_alerts_and_approvals(employees)
    seed_messages(users)
    seed_pos(users)
    print_demo_summary()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Supabase data.")
    parser.add_argument("--bootstrap-tenant", default=None, help="Create only baseline tenant records for a tenant id.")
    parser.add_argument("--demo", action="store_true", help="Create demo data for the seeded demo tenant.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.bootstrap_tenant:
        seed_bootstrap(args.bootstrap_tenant.strip())
    if args.demo:
        seed_demo()
    if not args.bootstrap_tenant and not args.demo:
        raise SystemExit("No seed mode selected. Use --demo or --bootstrap-tenant <tenant-id>.")


if __name__ == "__main__":
    main()
