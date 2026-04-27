from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import SessionContext, get_session_context, require_manager
from app.database import first_row, get_supabase, require_row, rows

router = APIRouter(prefix="/pos", tags=["pos"])

TABLE_STATUSES = {"open", "firing", "ready", "closed"}
TICKET_STATUSES = {"open", "firing", "ready", "closed"}


class PosMenuItemResponse(BaseModel):
    id: int
    tenant_id: str
    category_id: int
    name: str
    description: str
    price_cents: int
    is_active: int
    sort_order: int


class PosMenuCategoryResponse(BaseModel):
    id: int
    tenant_id: str
    name: str
    sort_order: int
    items: list[PosMenuItemResponse]


class PosTicketItemResponse(BaseModel):
    id: int
    tenant_id: str
    ticket_id: int
    menu_item_id: int
    item_name_snapshot: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int
    course: str | None
    seat_label: str | None
    created_at: str
    updated_at: str


class PosBoardTableResponse(BaseModel):
    id: int
    tenant_id: str
    table_number: str
    guest_count: int
    status: str
    opened_at: str
    updated_at: str
    closed_at: str | None
    subtotal_cents: int
    item_count: int
    summary_lines: list[str]
    last_printed_at: str | None
    ticket_id: int
    ticket_status: str
    ticket_updated_at: str


class PosTableDetailResponse(BaseModel):
    table: PosBoardTableResponse
    ticket_items: list[PosTicketItemResponse]


class PosCreateTableRequest(BaseModel):
    table_number: str = Field(min_length=1, max_length=32)
    guest_count: int = Field(default=1, ge=0, le=50)


class PosCreateTableResponse(BaseModel):
    table: PosBoardTableResponse


class PosAddTicketItemRequest(BaseModel):
    menu_item_id: int
    quantity: int = Field(default=1, ge=1, le=50)
    course: str | None = Field(default=None, max_length=64)
    seat_label: str | None = Field(default=None, max_length=64)


class PosUpdateTicketItemRequest(BaseModel):
    quantity: int = Field(ge=1, le=50)


class PosUpdateTableStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=32)
    guest_count: int | None = Field(default=None, ge=0, le=50)


class PosPrintTicketRequest(BaseModel):
    print_type: str = Field(default="guest_check", min_length=1, max_length=64)


class PosCloseTableRequest(BaseModel):
    note: str | None = Field(default=None, max_length=255)


class PosPrintTicketResponse(BaseModel):
    ticket_id: int
    table_number: str
    print_type: str
    printed_at: str
    subtotal_cents: int
    guest_count: int
    items: list[PosTicketItemResponse]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_audit_log(tenant_id: str, actor: str, action: str, details: str = "") -> None:
    get_supabase().table("audit_logs").insert(
        {
            "tenant_id": tenant_id,
            "actor": actor,
            "action": action,
            "details": details,
        }
    ).execute()


def list_pos_tables(context: SessionContext) -> list[dict]:
    return rows(
        get_supabase().table("pos_tables")
        .select("id, tenant_id, table_number, guest_count, status, opened_at, updated_at, closed_at")
        .eq("tenant_id", context.tenant_id)
        .order("table_number")
        .execute()
    )


def get_table_or_404(context: SessionContext, table_id: int) -> dict:
    row = first_row(
        get_supabase().table("pos_tables")
        .select("id, tenant_id, table_number, guest_count, status, opened_at, updated_at, closed_at")
        .eq("tenant_id", context.tenant_id)
        .eq("id", table_id)
        .limit(1)
        .execute()
    )
    return require_row(row, 404, "POS table not found.")


def get_active_ticket_or_404(context: SessionContext, table_id: int) -> dict:
    row = first_row(
        get_supabase().table("pos_tickets")
        .select("id, tenant_id, table_id, status, subtotal_cents, printed_at, kitchen_note, created_at, updated_at")
        .eq("tenant_id", context.tenant_id)
        .eq("table_id", table_id)
        .limit(1)
        .execute()
    )
    return require_row(row, 404, "POS ticket not found.")


def list_ticket_items(context: SessionContext, ticket_id: int) -> list[dict]:
    items = rows(
        get_supabase().table("pos_ticket_items")
        .select("id, tenant_id, ticket_id, menu_item_id, item_name_snapshot, unit_price_cents, quantity, line_total_cents, course, seat_label, created_at, updated_at")
        .eq("tenant_id", context.tenant_id)
        .eq("ticket_id", ticket_id)
        .order("id")
        .execute()
    )
    return items


def get_menu_item_or_404(context: SessionContext, menu_item_id: int) -> dict:
    row = first_row(
        get_supabase().table("pos_menu_items")
        .select("id, tenant_id, category_id, name, description, price_cents, is_active, sort_order")
        .eq("tenant_id", context.tenant_id)
        .eq("id", menu_item_id)
        .eq("is_active", 1)
        .limit(1)
        .execute()
    )
    return require_row(row, 404, "Menu item not found.")


def summarize_ticket_items(items: list[dict]) -> list[str]:
    if not items:
        return []
    summary: list[str] = []
    for item in items[:3]:
        if item["quantity"] > 1:
            summary.append(f"{item['item_name_snapshot']} x {item['quantity']}")
        else:
            summary.append(item["item_name_snapshot"])
    if len(items) > 3:
        summary.append(f"+{len(items) - 3} more")
    return summary


def refresh_ticket_totals(context: SessionContext, ticket_id: int) -> dict:
    supabase = get_supabase()
    ticket = first_row(
        supabase.table("pos_tickets")
        .select("id, tenant_id, table_id, status, subtotal_cents, printed_at, kitchen_note, created_at, updated_at")
        .eq("tenant_id", context.tenant_id)
        .eq("id", ticket_id)
        .limit(1)
        .execute()
    )
    ticket = require_row(ticket, 404, "POS ticket not found.")
    items = list_ticket_items(context, ticket_id)
    subtotal_cents = sum(int(item["line_total_cents"]) for item in items)
    updated = first_row(
        supabase.table("pos_tickets")
        .update({"subtotal_cents": subtotal_cents, "updated_at": utc_now_iso()})
        .eq("id", ticket_id)
        .execute()
    )
    return require_row(updated, 500, "Could not refresh ticket totals.")


def build_board_row(context: SessionContext, table_row: dict) -> PosBoardTableResponse:
    supabase = get_supabase()
    ticket = first_row(
        supabase.table("pos_tickets")
        .select("id, tenant_id, table_id, status, subtotal_cents, printed_at, kitchen_note, created_at, updated_at")
        .eq("tenant_id", context.tenant_id)
        .eq("table_id", table_row["id"])
        .limit(1)
        .execute()
    )
    ticket = require_row(ticket, 500, "Table is missing its ticket.")
    items = list_ticket_items(context, ticket["id"])
    return PosBoardTableResponse(
        id=table_row["id"],
        tenant_id=table_row["tenant_id"],
        table_number=table_row["table_number"],
        guest_count=table_row["guest_count"],
        status=table_row["status"],
        opened_at=table_row["opened_at"],
        updated_at=table_row["updated_at"],
        closed_at=table_row.get("closed_at"),
        subtotal_cents=ticket["subtotal_cents"],
        item_count=sum(int(item["quantity"]) for item in items),
        summary_lines=summarize_ticket_items(items),
        last_printed_at=ticket.get("printed_at"),
        ticket_id=ticket["id"],
        ticket_status=ticket["status"],
        ticket_updated_at=ticket["updated_at"],
    )


def ensure_open_table(table_row: dict) -> None:
    if table_row["status"] == "closed":
        raise HTTPException(status_code=400, detail="Table is already closed.")


@router.get("/menu", response_model=list[PosMenuCategoryResponse])
def get_menu(context: SessionContext = Depends(get_session_context)) -> list[PosMenuCategoryResponse]:
    require_manager(context)
    supabase = get_supabase()
    categories = rows(
        supabase.table("pos_menu_categories")
        .select("id, tenant_id, name, sort_order")
        .eq("tenant_id", context.tenant_id)
        .order("sort_order")
        .execute()
    )
    items = rows(
        supabase.table("pos_menu_items")
        .select("id, tenant_id, category_id, name, description, price_cents, is_active, sort_order")
        .eq("tenant_id", context.tenant_id)
        .eq("is_active", 1)
        .order("sort_order")
        .execute()
    )
    by_category: dict[int, list[PosMenuItemResponse]] = {}
    for item in items:
        by_category.setdefault(item["category_id"], []).append(PosMenuItemResponse(**item))
    return [
        PosMenuCategoryResponse(
            id=category["id"],
            tenant_id=category["tenant_id"],
            name=category["name"],
            sort_order=category["sort_order"],
            items=by_category.get(category["id"], []),
        )
        for category in categories
    ]


@router.get("/board", response_model=list[PosBoardTableResponse])
def get_board(context: SessionContext = Depends(get_session_context)) -> list[PosBoardTableResponse]:
    require_manager(context)
    table_rows = [row for row in list_pos_tables(context) if row["status"] != "closed"]
    return [build_board_row(context, row) for row in table_rows]


@router.post("/tables", response_model=PosCreateTableResponse)
def create_table(payload: PosCreateTableRequest, context: SessionContext = Depends(get_session_context)) -> PosCreateTableResponse:
    require_manager(context)
    table_number = payload.table_number.strip()
    supabase = get_supabase()

    existing = first_row(
        supabase.table("pos_tables")
        .select("id, status")
        .eq("tenant_id", context.tenant_id)
        .eq("table_number", table_number)
        .limit(1)
        .execute()
    )
    if existing and existing["status"] != "closed":
        raise HTTPException(status_code=409, detail="Table number is already open.")

    now = utc_now_iso()
    if existing and existing["status"] == "closed":
        table_row = first_row(
            supabase.table("pos_tables")
            .update(
                {
                    "guest_count": payload.guest_count,
                    "status": "open",
                    "opened_at": now,
                    "closed_at": None,
                    "updated_at": now,
                }
            )
            .eq("id", existing["id"])
            .execute()
        )
    else:
        table_row = first_row(
            supabase.table("pos_tables")
            .insert(
                {
                    "tenant_id": context.tenant_id,
                    "table_number": table_number,
                    "guest_count": payload.guest_count,
                    "status": "open",
                    "opened_at": now,
                    "updated_at": now,
                    "assigned_to_user_id": context.user_id,
                }
            )
            .execute()
        )
    table_row = require_row(table_row, 500, "Could not create POS table.")

    existing_ticket = first_row(
        supabase.table("pos_tickets")
        .select("id")
        .eq("tenant_id", context.tenant_id)
        .eq("table_id", table_row["id"])
        .limit(1)
        .execute()
    )
    if existing_ticket:
        supabase.table("pos_tickets").update(
            {
                "status": "open",
                "subtotal_cents": 0,
                "printed_at": None,
                "updated_at": now,
            }
        ).eq("id", existing_ticket["id"]).execute()
        ticket_id = existing_ticket["id"]
        for item in list_ticket_items(context, ticket_id):
            supabase.table("pos_ticket_items").delete().eq("id", item["id"]).execute()
    else:
        ticket = first_row(
            supabase.table("pos_tickets")
            .insert(
                {
                    "tenant_id": context.tenant_id,
                    "table_id": table_row["id"],
                    "status": "open",
                    "subtotal_cents": 0,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            .execute()
        )
        require_row(ticket, 500, "Could not create POS ticket.")

    insert_audit_log(context.tenant_id, context.email, "pos.table.open", f"table={table_number}")
    return PosCreateTableResponse(table=build_board_row(context, table_row))


@router.get("/tables/{table_id}", response_model=PosTableDetailResponse)
def get_table_detail(table_id: int, context: SessionContext = Depends(get_session_context)) -> PosTableDetailResponse:
    require_manager(context)
    table_row = get_table_or_404(context, table_id)
    board_row = build_board_row(context, table_row)
    items = list_ticket_items(context, board_row.ticket_id)
    return PosTableDetailResponse(table=board_row, ticket_items=[PosTicketItemResponse(**item) for item in items])


@router.post("/tables/{table_id}/items", response_model=PosTableDetailResponse)
def add_ticket_item(
    table_id: int,
    payload: PosAddTicketItemRequest,
    context: SessionContext = Depends(get_session_context),
) -> PosTableDetailResponse:
    require_manager(context)
    table_row = get_table_or_404(context, table_id)
    ensure_open_table(table_row)
    menu_item = get_menu_item_or_404(context, payload.menu_item_id)
    ticket = get_active_ticket_or_404(context, table_id)
    now = utc_now_iso()

    first_row(
        get_supabase().table("pos_ticket_items")
        .insert(
            {
                "tenant_id": context.tenant_id,
                "ticket_id": ticket["id"],
                "menu_item_id": menu_item["id"],
                "item_name_snapshot": menu_item["name"],
                "unit_price_cents": menu_item["price_cents"],
                "quantity": payload.quantity,
                "line_total_cents": menu_item["price_cents"] * payload.quantity,
                "course": (payload.course or "").strip() or None,
                "seat_label": (payload.seat_label or "").strip() or None,
                "created_at": now,
                "updated_at": now,
            }
        )
        .execute()
    )
    refresh_ticket_totals(context, ticket["id"])
    get_supabase().table("pos_tables").update({"updated_at": now}).eq("id", table_id).execute()
    insert_audit_log(context.tenant_id, context.email, "pos.item.add", f"table={table_row['table_number']};item={menu_item['name']}")
    return get_table_detail(table_id, context)


@router.patch("/tables/{table_id}/items/{ticket_item_id}", response_model=PosTableDetailResponse)
def update_ticket_item(
    table_id: int,
    ticket_item_id: int,
    payload: PosUpdateTicketItemRequest,
    context: SessionContext = Depends(get_session_context),
) -> PosTableDetailResponse:
    require_manager(context)
    table_row = get_table_or_404(context, table_id)
    ensure_open_table(table_row)
    ticket = get_active_ticket_or_404(context, table_id)
    item = first_row(
        get_supabase().table("pos_ticket_items")
        .select("id, tenant_id, ticket_id, menu_item_id, item_name_snapshot, unit_price_cents, quantity, line_total_cents, course, seat_label, created_at, updated_at")
        .eq("tenant_id", context.tenant_id)
        .eq("ticket_id", ticket["id"])
        .eq("id", ticket_item_id)
        .limit(1)
        .execute()
    )
    item = require_row(item, 404, "Ticket item not found.")
    now = utc_now_iso()
    get_supabase().table("pos_ticket_items").update(
        {
            "quantity": payload.quantity,
            "line_total_cents": int(item["unit_price_cents"]) * payload.quantity,
            "updated_at": now,
        }
    ).eq("id", ticket_item_id).execute()
    refresh_ticket_totals(context, ticket["id"])
    get_supabase().table("pos_tables").update({"updated_at": now}).eq("id", table_id).execute()
    insert_audit_log(context.tenant_id, context.email, "pos.item.update", f"table={table_row['table_number']};item_id={ticket_item_id};qty={payload.quantity}")
    return get_table_detail(table_id, context)


@router.delete("/tables/{table_id}/items/{ticket_item_id}", response_model=PosTableDetailResponse)
def remove_ticket_item(table_id: int, ticket_item_id: int, context: SessionContext = Depends(get_session_context)) -> PosTableDetailResponse:
    require_manager(context)
    table_row = get_table_or_404(context, table_id)
    ensure_open_table(table_row)
    ticket = get_active_ticket_or_404(context, table_id)
    item = first_row(
        get_supabase().table("pos_ticket_items")
        .select("id")
        .eq("tenant_id", context.tenant_id)
        .eq("ticket_id", ticket["id"])
        .eq("id", ticket_item_id)
        .limit(1)
        .execute()
    )
    require_row(item, 404, "Ticket item not found.")
    now = utc_now_iso()
    get_supabase().table("pos_ticket_items").delete().eq("id", ticket_item_id).execute()
    refresh_ticket_totals(context, ticket["id"])
    get_supabase().table("pos_tables").update({"updated_at": now}).eq("id", table_id).execute()
    insert_audit_log(context.tenant_id, context.email, "pos.item.remove", f"table={table_row['table_number']};item_id={ticket_item_id}")
    return get_table_detail(table_id, context)


@router.post("/tables/{table_id}/status", response_model=PosTableDetailResponse)
def update_table_status(
    table_id: int,
    payload: PosUpdateTableStatusRequest,
    context: SessionContext = Depends(get_session_context),
) -> PosTableDetailResponse:
    require_manager(context)
    status = payload.status.strip().lower()
    if status not in TABLE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid POS status.")
    table_row = get_table_or_404(context, table_id)
    ticket = get_active_ticket_or_404(context, table_id)
    now = utc_now_iso()
    table_update = {"status": status, "updated_at": now}
    if payload.guest_count is not None:
        table_update["guest_count"] = payload.guest_count
    ticket_update = {"status": status, "updated_at": now}
    if status == "closed":
        table_update["closed_at"] = now
    get_supabase().table("pos_tables").update(table_update).eq("id", table_id).execute()
    get_supabase().table("pos_tickets").update(ticket_update).eq("id", ticket["id"]).execute()
    insert_audit_log(context.tenant_id, context.email, "pos.table.status", f"table={table_row['table_number']};status={status}")
    return get_table_detail(table_id, context)


@router.post("/tables/{table_id}/print", response_model=PosPrintTicketResponse)
def print_ticket(
    table_id: int,
    payload: PosPrintTicketRequest,
    context: SessionContext = Depends(get_session_context),
) -> PosPrintTicketResponse:
    require_manager(context)
    table_row = get_table_or_404(context, table_id)
    ticket = refresh_ticket_totals(context, get_active_ticket_or_404(context, table_id)["id"])
    items = list_ticket_items(context, ticket["id"])
    now = utc_now_iso()
    get_supabase().table("pos_ticket_prints").insert(
        {
            "tenant_id": context.tenant_id,
            "ticket_id": ticket["id"],
            "printed_by": context.email,
            "printed_at": now,
            "print_type": payload.print_type.strip(),
        }
    ).execute()
    get_supabase().table("pos_tickets").update({"printed_at": now, "updated_at": now}).eq("id", ticket["id"]).execute()
    get_supabase().table("pos_tables").update({"updated_at": now}).eq("id", table_id).execute()
    insert_audit_log(context.tenant_id, context.email, "pos.ticket.print", f"table={table_row['table_number']};type={payload.print_type.strip()}")
    return PosPrintTicketResponse(
        ticket_id=ticket["id"],
        table_number=table_row["table_number"],
        print_type=payload.print_type.strip(),
        printed_at=now,
        subtotal_cents=ticket["subtotal_cents"],
        guest_count=table_row["guest_count"],
        items=[PosTicketItemResponse(**item) for item in items],
    )


@router.post("/tables/{table_id}/close", response_model=PosTableDetailResponse)
def close_table(
    table_id: int,
    payload: PosCloseTableRequest,
    context: SessionContext = Depends(get_session_context),
) -> PosTableDetailResponse:
    require_manager(context)
    table_row = get_table_or_404(context, table_id)
    ensure_open_table(table_row)
    ticket = refresh_ticket_totals(context, get_active_ticket_or_404(context, table_id)["id"])
    now = utc_now_iso()
    get_supabase().table("pos_tables").update({"status": "closed", "closed_at": now, "updated_at": now}).eq("id", table_id).execute()
    get_supabase().table("pos_tickets").update({"status": "closed", "updated_at": now}).eq("id", ticket["id"]).execute()
    insert_audit_log(context.tenant_id, context.email, "pos.table.close", f"table={table_row['table_number']};note={(payload.note or '').strip()}")
    return get_table_detail(table_id, context)
