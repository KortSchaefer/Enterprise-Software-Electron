from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import re
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal, engine, Base
from app.models import InventoryItem, InventoryMovement, TenantApp, User, Message
from app.security import hash_password, verify_password
from app.timeclock import router as timeclock_router
from app.chat import router as chat_router

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Enterprise Software Backend")
origins = [
    
    "http://localhost:5173",
]

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


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


app.include_router(timeclock_router)
app.include_router(chat_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/activation/validate", response_model=ActivationResponse)
def validate_activation(payload: ActivationRequest) -> ActivationResponse:
    tenant_key = payload.tenant_key.strip().lower()

    if not HEX_256_PATTERN.match(tenant_key):
        raise HTTPException(
            status_code=400,
            detail="Tenant key must be a valid 64-character hex string.",
        )

    # Placeholder tenancy mapping. Replace with DB lookup when tenant registry is ready.
    tenant_segment = tenant_key[:12]
    tenant_id = f"tenant-{tenant_segment}"

    return ActivationResponse(
        tenant_id=tenant_id,
        business_name=f"Business {tenant_segment.upper()}",
        api_base_url=f"https://api.example.com/{tenant_id}",
    )


@app.post("/users", response_model=UserResponse)
def create_user(payload: CreateUserRequest) -> UserResponse:
    session = SessionLocal()
    try:
        user = User(
            tenant_id=payload.tenant_id.strip(),
            email=payload.email.strip().lower(),
            password_hash=hash_password(payload.password),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return UserResponse(id=user.id, tenant_id=user.tenant_id, email=user.email)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="User email already exists.")
    finally:
        session.close()


@app.get("/users", response_model=list[UserResponse])
def list_users(tenant_id: str | None = None) -> list[UserResponse]:
    session = SessionLocal()
    try:
        query = select(User)
        if tenant_id:
            query = query.where(User.tenant_id == tenant_id.strip())

        users = session.execute(query.order_by(User.id.desc())).scalars().all()
        return [UserResponse(id=user.id, tenant_id=user.tenant_id, email=user.email) for user in users]
    finally:
        session.close()


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    session = SessionLocal()
    try:
        email = payload.email.strip().lower()
        tenant_id = payload.tenant_id.strip()
        user = session.execute(
            select(User).where(User.email == email, User.tenant_id == tenant_id)
        ).scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials.")

        valid_password = verify_password(payload.password, user.password_hash)
        if not valid_password and user.password_hash.startswith("plain:"):
            valid_password = user.password_hash == f"plain:{payload.password}"

        if not valid_password:
            raise HTTPException(status_code=401, detail="Invalid credentials.")

        return LoginResponse(user_id=user.id, tenant_id=user.tenant_id, email=user.email)
    finally:
        session.close()


@app.get("/apps/catalog", response_model=list[AppCatalogEntry])
def list_app_catalog() -> list[AppCatalogEntry]:
    return [AppCatalogEntry(**entry) for entry in APP_CATALOG]


@app.get("/apps/installed", response_model=list[TenantAppResponse])
def list_installed_apps(tenant_id: str) -> list[TenantAppResponse]:
    session = SessionLocal()
    try:
        rows = session.execute(
            select(TenantApp).where(TenantApp.tenant_id == tenant_id).order_by(TenantApp.id.asc())
        ).scalars().all()
        return [TenantAppResponse(app_key=row.app_key, installed_at=row.installed_at.isoformat()) for row in rows]
    finally:
        session.close()


@app.post("/apps/install", response_model=TenantAppResponse)
def install_app(payload: TenantAppInstallRequest) -> TenantAppResponse:
    tenant_id = payload.tenant_id.strip()
    app_key = payload.app_key.strip().lower()
    catalog_keys = {entry["key"] for entry in APP_CATALOG}
    if app_key not in catalog_keys:
        raise HTTPException(status_code=404, detail="Unknown app key.")

    session = SessionLocal()
    try:
        existing = session.execute(
            select(TenantApp).where(TenantApp.tenant_id == tenant_id, TenantApp.app_key == app_key)
        ).scalar_one_or_none()
        if existing:
            return TenantAppResponse(app_key=existing.app_key, installed_at=existing.installed_at.isoformat())

        row = TenantApp(tenant_id=tenant_id, app_key=app_key)
        session.add(row)
        session.commit()
        session.refresh(row)
        return TenantAppResponse(app_key=row.app_key, installed_at=row.installed_at.isoformat())
    finally:
        session.close()


@app.get("/inventory/items", response_model=list[InventoryItemResponse])
def list_inventory_items(tenant_id: str, low_stock_only: bool = False) -> list[InventoryItemResponse]:
    session = SessionLocal()
    try:
        query = select(InventoryItem).where(InventoryItem.tenant_id == tenant_id)
        if low_stock_only:
            query = query.where(InventoryItem.quantity_on_hand <= InventoryItem.reorder_point)
        rows = session.execute(query.order_by(InventoryItem.name.asc())).scalars().all()
        return [
            InventoryItemResponse(
                id=row.id,
                tenant_id=row.tenant_id,
                sku=row.sku,
                name=row.name,
                description=row.description,
                quantity_on_hand=row.quantity_on_hand,
                reorder_point=row.reorder_point,
            )
            for row in rows
        ]
    finally:
        session.close()


@app.post("/inventory/items", response_model=InventoryItemResponse)
def create_inventory_item(payload: InventoryItemCreateRequest) -> InventoryItemResponse:
    session = SessionLocal()
    try:
        row = InventoryItem(
            tenant_id=payload.tenant_id.strip(),
            sku=payload.sku.strip().upper(),
            name=payload.name.strip(),
            description=payload.description.strip(),
            quantity_on_hand=payload.quantity_on_hand,
            reorder_point=payload.reorder_point,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return InventoryItemResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            sku=row.sku,
            name=row.name,
            description=row.description,
            quantity_on_hand=row.quantity_on_hand,
            reorder_point=row.reorder_point,
        )
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="SKU already exists for this tenant.")
    finally:
        session.close()


@app.post("/inventory/adjust", response_model=InventoryItemResponse)
def adjust_inventory(payload: InventoryAdjustRequest) -> InventoryItemResponse:
    if payload.change_amount == 0:
        raise HTTPException(status_code=400, detail="change_amount cannot be zero.")

    session = SessionLocal()
    try:
        row = session.execute(
            select(InventoryItem).where(
                InventoryItem.id == payload.item_id,
                InventoryItem.tenant_id == payload.tenant_id.strip(),
            )
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Inventory item not found.")

        next_qty = row.quantity_on_hand + payload.change_amount
        if next_qty < 0:
            raise HTTPException(status_code=400, detail="Adjustment would result in negative stock.")

        row.quantity_on_hand = next_qty
        movement = InventoryMovement(
            item_id=row.id,
            tenant_id=row.tenant_id,
            change_amount=payload.change_amount,
            reason=payload.reason.strip(),
            performed_by=payload.performed_by.strip(),
        )
        session.add(movement)
        session.commit()
        session.refresh(row)
        return InventoryItemResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            sku=row.sku,
            name=row.name,
            description=row.description,
            quantity_on_hand=row.quantity_on_hand,
            reorder_point=row.reorder_point,
        )
    finally:
        session.close()
