from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

from app.database import first_row, get_supabase, hash_token


SESSION_DURATION_HOURS = int(os.getenv("SESSION_DURATION_HOURS", "12"))


@dataclass
class SessionContext:
    session_id: int
    session_token: str
    user_id: int
    email: str
    tenant_id: str
    role: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_session(user: dict, membership: dict) -> dict:
    token = secrets.token_urlsafe(48)
    expires_at = utc_now() + timedelta(hours=SESSION_DURATION_HOURS)
    row = first_row(
        get_supabase().table("app_sessions")
        .insert(
            {
                "user_id": user["id"],
                "tenant_id": membership["tenant_id"],
                "token_hash": hash_token(token),
                "expires_at": expires_at.isoformat(),
            }
        )
        .execute()
    )
    if not row:
        raise HTTPException(status_code=500, detail="Could not create session.")
    return {
        "access_token": token,
        "expires_at": expires_at.isoformat(),
        "tenant_id": membership["tenant_id"],
        "role": membership["role"],
    }


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid authorization header.")
    return token.strip()


def get_session_context(authorization: str | None = Header(default=None)) -> SessionContext:
    token = _extract_bearer_token(authorization)
    token_hash = hash_token(token)
    now_iso = utc_now().isoformat()
    supabase = get_supabase()

    session = first_row(
        supabase.table("app_sessions")
        .select("id, user_id, tenant_id, expires_at, revoked_at")
        .eq("token_hash", token_hash)
        .limit(1)
        .execute()
    )
    if not session or session.get("revoked_at") or session["expires_at"] <= now_iso:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")

    user = first_row(
        supabase.table("users")
        .select("id, email")
        .eq("id", session["user_id"])
        .limit(1)
        .execute()
    )
    if not user:
        raise HTTPException(status_code=401, detail="Session user not found.")

    membership = first_row(
        supabase.table("tenant_memberships")
        .select("tenant_id, role")
        .eq("user_id", session["user_id"])
        .eq("tenant_id", session["tenant_id"])
        .eq("is_active", 1)
        .limit(1)
        .execute()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="User is not active for this tenant.")

    return SessionContext(
        session_id=session["id"],
        session_token=token,
        user_id=user["id"],
        email=user["email"],
        tenant_id=membership["tenant_id"],
        role=membership["role"],
    )


def revoke_session(context: SessionContext) -> None:
    get_supabase().table("app_sessions").update({"revoked_at": utc_now().isoformat()}).eq("id", context.session_id).execute()


def require_manager(context: SessionContext) -> SessionContext:
    if context.role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Manager access required.")
    return context
