from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.chat import router as chat_router
from app.database import first_row, get_supabase, require_row, rows
from app.security import hash_password, verify_password
from app.timeclock import router as timeclock_router

app = FastAPI(title="Enterprise Software Backend")
origins = ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEX_256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")
APP_CATALOG = [
    {
        "key": "inventory",
        "name": "Inventory System",
        "description": "Track stock, reorder levels, and inventory adjustments.",
    },
    {
        "key": "timeclock",
        "name": "Employee Timeclock",
        "description": "Manager-side attendance, scheduling, approvals, and payroll export.",
    },
    {
        "key": "chat",
        "name": "Chat",
        "description": "One-to-one messaging between users.",
    },
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActivationRequest(BaseModel):
    tenant_key: str = Field(min_length=64, max_length=64)


class ActivationResponse(BaseModel):
    tenant_id: str
    business_name: str
    api_base_url: str


class CreateUserRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=255)


class UserResponse(BaseModel):
    id: int
    tenant_id: str
    email: str


class LoginRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class LoginResponse(BaseModel):
    user_id: int
    tenant_id: str
    email: str


class AppCatalogEntry(BaseModel):
    key: str
    name: str
    description: str


class TenantAppInstallRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    app_key: str = Field(min_length=1, max_length=64)


class TenantAppResponse(BaseModel):
    app_key: str
    installed_at: str


class InventoryItemCreateRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=1000)
    quantity_on_hand: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=0, ge=0)


class InventoryItemResponse(BaseModel):
    id: int
    tenant_id: str
    sku: str
    name: str
    description: str
    quantity_on_hand: int
    reorder_point: int


class InventoryAdjustRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    item_id: int
    change_amount: int
    reason: str = Field(min_length=1, max_length=255)
    performed_by: str = Field(default="", max_length=255)


app.include_router(timeclock_router)
app.include_router(chat_router)


@app.get("/health")
def health() -> dict[str, str]:
    get_supabase()
    return {"status": "ok"}


@app.post("/activation/validate", response_model=ActivationResponse)
def validate_activation(payload: ActivationRequest) -> ActivationResponse:
    tenant_key = payload.tenant_key.strip().lower()

    if not HEX_256_PATTERN.match(tenant_key):
        raise HTTPException(
            status_code=400,
            detail="Tenant key must be a valid 64-character hex string.",
        )

    tenant_segment = tenant_key[:12]
    tenant_id = f"tenant-{tenant_segment}"

    return ActivationResponse(
        tenant_id=tenant_id,
        business_name=f"Business {tenant_segment.upper()}",
        api_base_url=f"https://api.example.com/{tenant_id}",
    )


@app.post("/users", response_model=UserResponse)
def create_user(payload: CreateUserRequest) -> UserResponse:
    supabase = get_supabase()
    tenant_id = payload.tenant_id.strip()
    email = payload.email.strip().lower()

    existing = first_row(
        supabase.table("users").select("id").eq("tenant_id", tenant_id).eq("email", email).limit(1).execute()
    )
    if existing:
        raise HTTPException(status_code=409, detail="User email already exists.")

    row = first_row(
        supabase.table("users")
        .insert(
            {
                "tenant_id": tenant_id,
                "email": email,
                "password_hash": hash_password(payload.password),
            }
        )
        .execute()
    )
    row = require_row(row, 500, "User creation failed.")
    return UserResponse(id=row["id"], tenant_id=row["tenant_id"], email=row["email"])


@app.get("/users", response_model=list[UserResponse])
def list_users(tenant_id: str | None = None) -> list[UserResponse]:
    supabase = get_supabase()
    query = supabase.table("users").select("id, tenant_id, email").order("id", desc=True)
    if tenant_id:
        query = query.eq("tenant_id", tenant_id.strip())

    return [UserResponse(**row) for row in rows(query.execute())]


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    supabase = get_supabase()
    email = payload.email.strip().lower()
    tenant_id = payload.tenant_id.strip()
    user = first_row(
        supabase.table("users")
        .select("id, tenant_id, email, password_hash")
        .eq("email", email)
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    valid_password = verify_password(payload.password, user["password_hash"])
    if not valid_password and user["password_hash"].startswith("plain:"):
        valid_password = user["password_hash"] == f"plain:{payload.password}"

    if not valid_password:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    return LoginResponse(user_id=user["id"], tenant_id=user["tenant_id"], email=user["email"])


@app.get("/apps/catalog", response_model=list[AppCatalogEntry])
def list_app_catalog() -> list[AppCatalogEntry]:
    return [AppCatalogEntry(**entry) for entry in APP_CATALOG]


@app.get("/apps/installed", response_model=list[TenantAppResponse])
def list_installed_apps(tenant_id: str) -> list[TenantAppResponse]:
    supabase = get_supabase()
    result = rows(
        supabase.table("tenant_apps")
        .select("app_key, installed_at")
        .eq("tenant_id", tenant_id.strip())
        .order("id")
        .execute()
    )
    return [TenantAppResponse(**row) for row in result]


@app.post("/apps/install", response_model=TenantAppResponse)
def install_app(payload: TenantAppInstallRequest) -> TenantAppResponse:
    tenant_id = payload.tenant_id.strip()
    app_key = payload.app_key.strip().lower()
    catalog_keys = {entry["key"] for entry in APP_CATALOG}
    if app_key not in catalog_keys:
        raise HTTPException(status_code=404, detail="Unknown app key.")

    supabase = get_supabase()
    existing = first_row(
        supabase.table("tenant_apps")
        .select("app_key, installed_at")
        .eq("tenant_id", tenant_id)
        .eq("app_key", app_key)
        .limit(1)
        .execute()
    )
    if existing:
        return TenantAppResponse(**existing)

    row = first_row(
        supabase.table("tenant_apps")
        .insert({"tenant_id": tenant_id, "app_key": app_key})
        .execute()
    )
    row = require_row(row, 500, "App installation failed.")
    return TenantAppResponse(app_key=row["app_key"], installed_at=row["installed_at"])


@app.get("/inventory/items", response_model=list[InventoryItemResponse])
def list_inventory_items(tenant_id: str, low_stock_only: bool = False) -> list[InventoryItemResponse]:
    supabase = get_supabase()
    query = (
        supabase.table("inventory_items")
        .select("id, tenant_id, sku, name, description, quantity_on_hand, reorder_point")
        .eq("tenant_id", tenant_id.strip())
        .order("name")
    )
    rows_out = rows(query.execute())
    if low_stock_only:
        rows_out = [row for row in rows_out if row["quantity_on_hand"] <= row["reorder_point"]]
    return [InventoryItemResponse(**row) for row in rows_out]


@app.post("/inventory/items", response_model=InventoryItemResponse)
def create_inventory_item(payload: InventoryItemCreateRequest) -> InventoryItemResponse:
    supabase = get_supabase()
    tenant_id = payload.tenant_id.strip()
    sku = payload.sku.strip().upper()

    existing = first_row(
        supabase.table("inventory_items")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("sku", sku)
        .limit(1)
        .execute()
    )
    if existing:
        raise HTTPException(status_code=409, detail="SKU already exists for this tenant.")

    row = first_row(
        supabase.table("inventory_items")
        .insert(
            {
                "tenant_id": tenant_id,
                "sku": sku,
                "name": payload.name.strip(),
                "description": payload.description.strip(),
                "quantity_on_hand": payload.quantity_on_hand,
                "reorder_point": payload.reorder_point,
                "updated_at": utc_now_iso(),
            }
        )
        .execute()
    )
    row = require_row(row, 500, "Inventory item creation failed.")
    return InventoryItemResponse(**row)


@app.post("/inventory/adjust", response_model=InventoryItemResponse)
def adjust_inventory(payload: InventoryAdjustRequest) -> InventoryItemResponse:
    if payload.change_amount == 0:
        raise HTTPException(status_code=400, detail="change_amount cannot be zero.")

    supabase = get_supabase()
    tenant_id = payload.tenant_id.strip()
    row = first_row(
        supabase.table("inventory_items")
        .select("id, tenant_id, sku, name, description, quantity_on_hand, reorder_point")
        .eq("id", payload.item_id)
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Inventory item not found.")

    next_qty = row["quantity_on_hand"] + payload.change_amount
    if next_qty < 0:
        raise HTTPException(status_code=400, detail="Adjustment would result in negative stock.")

    updated = first_row(
        supabase.table("inventory_items")
        .update({"quantity_on_hand": next_qty, "updated_at": utc_now_iso()})
        .eq("id", row["id"])
        .eq("tenant_id", tenant_id)
        .execute()
    )
    require_row(updated, 500, "Inventory update failed.")

    supabase.table("inventory_movements").insert(
        {
            "item_id": row["id"],
            "tenant_id": tenant_id,
            "change_amount": payload.change_amount,
            "reason": payload.reason.strip(),
            "performed_by": payload.performed_by.strip(),
        }
    ).execute()

    return InventoryItemResponse(**updated)
