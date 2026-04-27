from __future__ import annotations

import hashlib
import os
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import first_row, get_supabase
from app.security import hash_password, verify_password

router = APIRouter(prefix="/platform-admin")

PLATFORM_ADMIN_USERNAME = os.getenv("PLATFORM_ADMIN_USERNAME", "").strip().lower()
PLATFORM_ADMIN_PASSWORD_HASH = os.getenv("PLATFORM_ADMIN_PASSWORD_HASH", "").strip()
SESSION_COOKIE = "pa_session"
_active_sessions: set[str] = set()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _make_tenant_id(business_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", business_name.strip().lower()).strip("-")
    return f"tenant-{slug}-{secrets.token_hex(4)}"


def _require_session(pa_session: str | None) -> None:
    if not pa_session or pa_session not in _active_sessions:
        raise HTTPException(status_code=303, headers={"Location": "/platform-admin/"})


# --- Login page ---

@router.get("/", response_class=HTMLResponse)
def login_page() -> str:
    return """
    <html><body style="font-family:sans-serif;max-width:400px;margin:60px auto">
    <h2>Platform Admin Login</h2>
    <form method="post" action="/platform-admin/auth">
      <label>Username<br><input name="username" type="text" required style="width:100%"></label><br><br>
      <label>Password<br><input name="password" type="password" required style="width:100%"></label><br><br>
      <button type="submit">Login</button>
    </form>
    </body></html>
    """


@router.post("/auth")
def do_login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    username = username.strip().lower()
    if not PLATFORM_ADMIN_USERNAME or not PLATFORM_ADMIN_PASSWORD_HASH:
        raise HTTPException(status_code=503, detail="Platform admin not configured.")
    if username != PLATFORM_ADMIN_USERNAME or not verify_password(password, PLATFORM_ADMIN_PASSWORD_HASH):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    token = secrets.token_hex(32)
    _active_sessions.add(token)
    resp = RedirectResponse(url="/platform-admin/provision", status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict", max_age=3600)
    return resp


# --- Provision form ---

@router.get("/provision", response_class=HTMLResponse)
def provision_page(pa_session: str | None = Cookie(default=None)) -> str:
    _require_session(pa_session)
    return """
    <html><body style="font-family:sans-serif;max-width:500px;margin:60px auto">
    <h2>Provision New Tenant</h2>
    <form method="post" action="/platform-admin/provision">
      <label>Business Name<br><input name="business_name" required style="width:100%"></label><br><br>
      <label>Admin Email<br><input name="admin_email" type="email" required style="width:100%"></label><br><br>
      <label>Temporary Password<br><input name="admin_password" type="password" required style="width:100%"></label><br><br>
      <button type="submit">Provision Tenant</button>
    </form>
    </body></html>
    """


@router.post("/provision", response_class=HTMLResponse)
def do_provision(
    pa_session: str | None = Cookie(default=None),
    business_name: str = Form(...),
    admin_email: str = Form(...),
    admin_password: str = Form(...),
) -> str:
    _require_session(pa_session)

    business_name = business_name.strip()
    admin_email = admin_email.strip().lower()

    if len(admin_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    supabase = get_supabase()
    tenant_id = _make_tenant_id(business_name)

    # 1. Create tenant
    supabase.table("tenants").insert({"id": tenant_id, "name": business_name, "is_active": 1}).execute()

    # 2. Generate and store activation key
    raw_key = secrets.token_hex(32)  # 64-char hex
    supabase.table("tenant_activation_keys").insert({
        "tenant_id": tenant_id,
        "key_hash": _hash_key(raw_key),
        "key_last4": raw_key[-4:],
        "issued_to_email": admin_email,
        "issued_at": _utc_now(),
        "metadata": {"provisioned_by": PLATFORM_ADMIN_USERNAME},
    }).execute()

    # 3. Create first admin user
    user = first_row(
        supabase.table("users").insert({
            "tenant_id": tenant_id,
            "email": admin_email,
            "password_hash": hash_password(admin_password),
        }).execute()
    )
    if not user:
        raise HTTPException(status_code=500, detail="User creation failed.")

    # 4. Assign admin role
    supabase.table("tenant_memberships").insert({
        "tenant_id": tenant_id,
        "user_id": user["id"],
        "role": "admin",
        "is_active": 1,
    }).execute()

    return f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:60px auto">
    <h2>Tenant Provisioned</h2>
    <p>Send the following to the tenant admin:</p>
    <table border="1" cellpadding="8" style="border-collapse:collapse;width:100%">
      <tr><td><b>Tenant ID</b></td><td>{tenant_id}</td></tr>
      <tr><td><b>Business Name</b></td><td>{business_name}</td></tr>
      <tr><td><b>Activation Key</b></td><td style="font-family:monospace">{raw_key}</td></tr>
      <tr><td><b>Admin Email</b></td><td>{admin_email}</td></tr>
      <tr><td><b>Temp Password</b></td><td>{admin_password}</td></tr>
    </table>
    <br>
    <p style="color:red"><b>Copy this now. The activation key will not be shown again.</b></p>
    <a href="/platform-admin/provision">Provision Another</a>
    </body></html>
    """