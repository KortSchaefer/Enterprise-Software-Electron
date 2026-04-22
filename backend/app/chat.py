from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import SessionContext, get_session_context
from app.database import first_row, get_supabase, rows

router = APIRouter(tags=["chat"])


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
    
class ChatSendResponse(BaseModel):
    success: bool
    id: int
    tenant_id: str
    from_user_id: int
    to_user_id: int
    text: str
    created_at: str
    read_at: str | None
    
class ChatMessagesResponse(BaseModel):
    success: bool
    messages: list[ChatMessageResponse]


def get_user(tenant_id: str, user_id: int) -> dict:
    supabase = get_supabase()

    membership = first_row(
        supabase.table("tenant_memberships")
        .select("user_id")
        .eq("tenant_id", tenant_id)
        .eq("user_id", user_id)
        .eq("is_active", 1)
        .limit(1)
        .execute()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="User not found.")

    user = first_row(
        supabase.table("users")
        .select("id")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    return user


@router.post("/chat/send", response_model=ChatSendResponse)
def chat_send(payload: ChatSendRequest, context: SessionContext = Depends(get_session_context)) -> ChatSendResponse:
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

    return ChatSendResponse(success=True, **row)


@router.post("/chat/messages", response_model=ChatMessagesResponse)
def chat_messages(payload: ChatListRequest, context: SessionContext = Depends(get_session_context)) -> ChatMessagesResponse:
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
    messages = [ChatMessageResponse(**row) for row in merged]
    return ChatMessagesResponse(success=True, messages=messages)