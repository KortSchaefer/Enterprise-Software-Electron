from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import SessionContext, get_session_context
from app.database import first_row, get_supabase, rows

router = APIRouter()


class ChatSendRequest(BaseModel):
    to_user_id: int
    text: str = Field(min_length=1, max_length=1000)


class ChatMessageResponse(BaseModel):
    id: int
    tenant_id: str
    from_user_id: int
    to_user_id: int
    text: str
    created_at: str
    read_at: str | None


class ChatListRequest(BaseModel):
    with_user_id: int


def get_user(tenant_id: str, user_id: int) -> dict:
    row = first_row(
        get_supabase().table("users")
        .select("id, tenant_id")
        .eq("id", user_id)
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    return row


@router.post("/chat/send", response_model=ChatMessageResponse)
def chat_send(payload: ChatSendRequest, context: SessionContext = Depends(get_session_context)) -> ChatMessageResponse:
    supabase = get_supabase()
    to_user = get_user(context.tenant_id, payload.to_user_id)

    row = first_row(
        supabase.table("messages")
        .insert(
            {
                "tenant_id": context.tenant_id,
                "from_user_id": context.user_id,
                "to_user_id": to_user["id"],
                "text": payload.text.strip(),
            }
        )
        .execute()
    )
    if not row:
        raise HTTPException(status_code=500, detail="Message creation failed.")

    return ChatMessageResponse(**row)


@router.post("/chat/messages", response_model=list[ChatMessageResponse])
def chat_messages(payload: ChatListRequest, context: SessionContext = Depends(get_session_context)) -> list[ChatMessageResponse]:
    supabase = get_supabase()
    other = get_user(context.tenant_id, payload.with_user_id)

    sent = rows(
        supabase.table("messages")
        .select("id, tenant_id, from_user_id, to_user_id, text, created_at, read_at")
        .eq("tenant_id", context.tenant_id)
        .eq("from_user_id", context.user_id)
        .eq("to_user_id", other["id"])
        .execute()
    )
    received = rows(
        supabase.table("messages")
        .select("id, tenant_id, from_user_id, to_user_id, text, created_at, read_at")
        .eq("tenant_id", context.tenant_id)
        .eq("from_user_id", other["id"])
        .eq("to_user_id", context.user_id)
        .execute()
    )

    merged = sorted([*sent, *received], key=lambda row: row["created_at"])
    return [ChatMessageResponse(**row) for row in merged]
