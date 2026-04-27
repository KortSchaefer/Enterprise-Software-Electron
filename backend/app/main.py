from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth import SessionContext, create_session, get_session_context, require_manager, revoke_session
from app.chat import router as chat_router
from app.database import first_row, get_supabase, require_row, rows
from app.pos import router as pos_router
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
    {
        "key": "pos",
        "name": "POS",
        "description": "Table-service board for dining room tickets and printing.",
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
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=255)
    role: str = Field(default="staff", max_length=64)


class UserResponse(BaseModel):
    id: int
    tenant_id: str
    email: str
    role: str


class LoginRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class LoginResponse(BaseModel):
    user_id: int
    tenant_id: str
    email: str
    role: str
    access_token: str
    expires_at: str


class AppCatalogEntry(BaseModel):
    key: str
    name: str
    description: str


class TenantAppInstallRequest(BaseModel):
    app_key: str = Field(min_length=1, max_length=64)


class TenantAppResponse(BaseModel):
    app_key: str
    installed_at: str


class InventoryItemCreateRequest(BaseModel):
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
    item_id: int
    change_amount: int
    reason: str = Field(min_length=1, max_length=255)
    performed_by: str = Field(default="", max_length=255)


app.include_router(timeclock_router)
app.include_router(chat_router)
app.include_router(pos_router)


@app.get("/health")
def health() -> dict[str, str]:
    get_supabase()
    return {"status": "ok"}


@app.post("/activation/validate", response_model=ActivationResponse)
def validate_activation(payload: ActivationRequest) -> ActivationResponse:
    tenant_key = payload.tenant_key.strip().lower()

    if not HEX_256_PATTERN.match(tenant_key):
        raise HTTPException(status_code=400, detail="Tenant key must be a valid 64-character hex string.")

    tenant_segment = tenant_key[:12]
    tenant_id = f"tenant-{tenant_segment}"

    return ActivationResponse(
        tenant_id=tenant_id,
        business_name=f"Business {tenant_segment.upper()}",
        api_base_url=f"https://api.example.com/{tenant_id}",
    )


@app.post("/users", response_model=UserResponse)
def create_user(
    payload: CreateUserRequest,
    context: SessionContext = Depends(get_session_context),
) -> UserResponse:
    require_manager(context)
    supabase = get_supabase()
    email = payload.email.strip().lower()

    existing = first_row(
        supabase.table("users").select("id").eq("tenant_id", context.tenant_id).eq("email", email).limit(1).execute()
    )
    if existing:
        raise HTTPException(status_code=409, detail="User email already exists.")

    row = first_row(
        supabase.table("users")
        .insert(
            {
                "tenant_id": context.tenant_id,
                "email": email,
                "password_hash": hash_password(payload.password),
            }
        )
        .execute()
    )
    row = require_row(row, 500, "User creation failed.")
    supabase.table("tenant_memberships").insert(
        {
            "tenant_id": context.tenant_id,
            "user_id": row["id"],
            "role": payload.role.strip().lower(),
            "is_active": 1,
        }
    ).execute()
    return UserResponse(id=row["id"], tenant_id=row["tenant_id"], email=row["email"], role=payload.role.strip().lower())


@app.get("/users", response_model=list[UserResponse])
def list_users(context: SessionContext = Depends(get_session_context)) -> list[UserResponse]:
    supabase = get_supabase()
    users = rows(
        supabase.table("users")
        .select("id, tenant_id, email")
        .eq("tenant_id", context.tenant_id)
        .order("id", desc=True)
        .execute()
    )
    memberships = rows(
        supabase.table("tenant_memberships")
        .select("user_id, role")
        .eq("tenant_id", context.tenant_id)
        .eq("is_active", 1)
        .execute()
    )
    roles_by_user_id = {row["user_id"]: row["role"] for row in memberships}
    return [
        UserResponse(id=user["id"], tenant_id=user["tenant_id"], email=user["email"], role=roles_by_user_id.get(user["id"], "staff"))
        for user in users
    ]


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

    membership = first_row(
        supabase.table("tenant_memberships")
        .select("tenant_id, role, is_active")
        .eq("user_id", user["id"])
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if not membership or membership["is_active"] != 1:
        raise HTTPException(status_code=403, detail="User is not active for this tenant.")

    valid_password = verify_password(payload.password, user["password_hash"])
    if not valid_password and user["password_hash"].startswith("plain:"):
        valid_password = user["password_hash"] == f"plain:{payload.password}"
    if not valid_password:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    session = create_session(user, membership)
    return LoginResponse(
        user_id=user["id"],
        tenant_id=user["tenant_id"],
        email=user["email"],
        role=membership["role"],
        access_token=session["access_token"],
        expires_at=session["expires_at"],
    )


@app.post("/auth/logout")
def logout(context: SessionContext = Depends(get_session_context)) -> dict[str, str]:
    revoke_session(context)
    return {"status": "ok"}


@app.get("/auth/session")
def get_session(context: SessionContext = Depends(get_session_context)) -> dict[str, str | int]:
    return {
        "user_id": context.user_id,
        "tenant_id": context.tenant_id,
        "email": context.email,
        "role": context.role,
    }


@app.get("/apps/catalog", response_model=list[AppCatalogEntry])
def list_app_catalog() -> list[AppCatalogEntry]:
    return [AppCatalogEntry(**entry) for entry in APP_CATALOG]


@app.get("/apps/installed", response_model=list[TenantAppResponse])
def list_installed_apps(context: SessionContext = Depends(get_session_context)) -> list[TenantAppResponse]:
    result = rows(
        get_supabase().table("tenant_apps")
        .select("app_key, installed_at")
        .eq("tenant_id", context.tenant_id)
        .order("id")
        .execute()
    )
    return [TenantAppResponse(**row) for row in result]


@app.post("/apps/install", response_model=TenantAppResponse)
def install_app(
    payload: TenantAppInstallRequest,
    context: SessionContext = Depends(get_session_context),
) -> TenantAppResponse:
    require_manager(context)
    app_key = payload.app_key.strip().lower()
    catalog_keys = {entry["key"] for entry in APP_CATALOG}
    if app_key not in catalog_keys:
        raise HTTPException(status_code=404, detail="Unknown app key.")

    supabase = get_supabase()
    existing = first_row(
        supabase.table("tenant_apps")
        .select("app_key, installed_at")
        .eq("tenant_id", context.tenant_id)
        .eq("app_key", app_key)
        .limit(1)
        .execute()
    )
    if existing:
        return TenantAppResponse(**existing)

    row = first_row(
        supabase.table("tenant_apps")
        .insert({"tenant_id": context.tenant_id, "app_key": app_key})
        .execute()
    )
    row = require_row(row, 500, "App installation failed.")
    return TenantAppResponse(app_key=row["app_key"], installed_at=row["installed_at"])


@app.get("/inventory/items", response_model=list[InventoryItemResponse])
def list_inventory_items(low_stock_only: bool = False, context: SessionContext = Depends(get_session_context)) -> list[InventoryItemResponse]:
    query = (
        get_supabase().table("inventory_items")
        .select("id, tenant_id, sku, name, description, quantity_on_hand, reorder_point")
        .eq("tenant_id", context.tenant_id)
        .order("name")
    )
    rows_out = rows(query.execute())
    if low_stock_only:
        rows_out = [row for row in rows_out if row["quantity_on_hand"] <= row["reorder_point"]]
    return [InventoryItemResponse(**row) for row in rows_out]


@app.post("/inventory/items", response_model=InventoryItemResponse)
def create_inventory_item(
    payload: InventoryItemCreateRequest,
    context: SessionContext = Depends(get_session_context),
) -> InventoryItemResponse:
    require_manager(context)
    sku = payload.sku.strip().upper()
    supabase = get_supabase()

    existing = first_row(
        supabase.table("inventory_items")
        .select("id")
        .eq("tenant_id", context.tenant_id)
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
                "tenant_id": context.tenant_id,
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
def adjust_inventory(
    payload: InventoryAdjustRequest,
    context: SessionContext = Depends(get_session_context),
) -> InventoryItemResponse:
    require_manager(context)
    if payload.change_amount == 0:
        raise HTTPException(status_code=400, detail="change_amount cannot be zero.")

    result = first_row(
        get_supabase().rpc(
            "adjust_inventory_item",
            {
                "p_tenant_id": context.tenant_id,
                "p_item_id": payload.item_id,
                "p_change_amount": payload.change_amount,
                "p_reason": payload.reason.strip(),
                "p_performed_by": payload.performed_by.strip() or context.email,
            },
        )
    )
    result = require_row(result, 500, "Inventory update failed.")
    return InventoryItemResponse(**result)
