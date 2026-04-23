from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth import SessionContext, get_session_context, get_session_context_from_token
from app.database import first_row, get_supabase, rows

router = APIRouter(tags=["chat"])

DEFAULT_THREAD_PAGE_SIZE = 40
MAX_THREAD_PAGE_SIZE = 100
STREAM_POLL_INTERVAL_SECONDS = 1.5
STREAM_RETRY_MS = 2000
SUMMARY_CACHE_TTL_SECONDS = 0.0
SUMMARY_CACHE: dict[tuple[str, int], tuple[float, list["ConversationSummaryResponse"]]] = {}


class ChatMessageCreateRequest(BaseModel):
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


class ChatThreadResponse(BaseModel):
    messages: list[ChatMessageResponse]
    next_before: str | None
    has_more: bool


class ConversationSummaryResponse(BaseModel):
    conversation_id: str
    other_user_id: int
    other_user_email: str
    other_user_role: str
    unread_count: int
    last_message_id: int | None
    last_message_text: str | None
    last_message_created_at: str | None
    last_message_direction: str | None
    last_read_at: str | None


class MarkConversationReadResponse(BaseModel):
    with_user_id: int
    unread_count: int
    read_through: str | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_conversation_id(user_id: int) -> str:
    return f"user:{user_id}"


def get_summary_cache_key(context: SessionContext) -> tuple[str, int]:
    return context.tenant_id, context.user_id


def invalidate_summary_cache(context: SessionContext, with_user_id: int | None = None) -> None:
    SUMMARY_CACHE.pop(get_summary_cache_key(context), None)
    if with_user_id is not None:
        SUMMARY_CACHE.pop((context.tenant_id, with_user_id), None)


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


def list_tenant_users(context: SessionContext) -> tuple[list[dict], dict[int, str]]:
    supabase = get_supabase()
    users = rows(
        supabase.table("users")
        .select("id, tenant_id, email")
        .eq("tenant_id", context.tenant_id)
        .order("id")
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
    return users, roles_by_user_id


def list_user_messages(context: SessionContext) -> list[dict]:
    supabase = get_supabase()
    sent = rows(
        supabase.table("messages")
        .select("id, tenant_id, from_user_id, to_user_id, text, created_at, read_at")
        .eq("tenant_id", context.tenant_id)
        .eq("from_user_id", context.user_id)
        .execute()
    )
    received = rows(
        supabase.table("messages")
        .select("id, tenant_id, from_user_id, to_user_id, text, created_at, read_at")
        .eq("tenant_id", context.tenant_id)
        .eq("to_user_id", context.user_id)
        .execute()
    )
    return sorted([*sent, *received], key=lambda row: (row["created_at"], row["id"]))


def conversation_partner_id(context: SessionContext, row: dict) -> int:
    return row["to_user_id"] if row["from_user_id"] == context.user_id else row["from_user_id"]


def list_conversation_messages(context: SessionContext, with_user_id: int) -> list[dict]:
    supabase = get_supabase()
    other = get_user(context.tenant_id, with_user_id)

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
    return sorted([*sent, *received], key=lambda row: (row["created_at"], row["id"]))


def parse_cursor(cursor: str | None) -> tuple[str, int] | None:
    if not cursor:
        return None
    created_at, separator, raw_id = cursor.rpartition("|")
    if not separator:
        return cursor, 0
    try:
        return created_at, int(raw_id)
    except ValueError:
        return created_at, 0


def build_cursor(row: dict) -> str:
    return f"{row['created_at']}|{row['id']}"


def paginate_messages(messages: list[dict], before: str | None, limit: int) -> tuple[list[dict], str | None, bool]:
    cursor = parse_cursor(before)
    if cursor:
        before_created_at, before_id = cursor
        if before_id > 0:
            filtered = [
                row
                for row in messages
                if (row["created_at"], row["id"]) < (before_created_at, before_id)
            ]
        else:
            filtered = [row for row in messages if row["created_at"] < before_created_at]
    else:
        filtered = messages

    page = filtered[-limit:]
    has_more = len(filtered) > len(page)
    next_before = build_cursor(page[0]) if has_more and page else None
    return page, next_before, has_more


def build_conversation_summaries(context: SessionContext) -> list[ConversationSummaryResponse]:
    cache_key = get_summary_cache_key(context)
    now = monotonic()
    if SUMMARY_CACHE_TTL_SECONDS > 0:
        cached = SUMMARY_CACHE.get(cache_key)
        if cached and now - cached[0] < SUMMARY_CACHE_TTL_SECONDS:
            return cached[1]

    users, roles_by_user_id = list_tenant_users(context)
    users_by_id = {user["id"]: user for user in users if user["id"] != context.user_id}
    summaries: dict[int, dict] = {
        user_id: {
            "conversation_id": make_conversation_id(user_id),
            "other_user_id": user_id,
            "other_user_email": user["email"],
            "other_user_role": roles_by_user_id.get(user_id, "staff"),
            "unread_count": 0,
            "last_message_id": None,
            "last_message_text": None,
            "last_message_created_at": None,
            "last_message_direction": None,
            "last_read_at": None,
        }
        for user_id, user in users_by_id.items()
    }

    for row in list_user_messages(context):
        other_user_id = conversation_partner_id(context, row)
        if other_user_id not in summaries:
            continue
        summary = summaries[other_user_id]
        direction = "outgoing" if row["from_user_id"] == context.user_id else "incoming"
        if summary["last_message_created_at"] is None or (row["created_at"], row["id"]) >= (
            summary["last_message_created_at"],
            summary["last_message_id"] or 0,
        ):
            summary["last_message_id"] = row["id"]
            summary["last_message_text"] = row["text"]
            summary["last_message_created_at"] = row["created_at"]
            summary["last_message_direction"] = direction
        if direction == "incoming" and row["read_at"] is None:
            summary["unread_count"] += 1
        if direction == "incoming" and row["read_at"]:
            if summary["last_read_at"] is None or row["read_at"] > summary["last_read_at"]:
                summary["last_read_at"] = row["read_at"]

    ordered = list(summaries.values())
    ordered.sort(key=lambda row: row["other_user_email"])
    ordered.sort(
        key=lambda row: row["last_message_created_at"] or "",
        reverse=True,
    )
    response = [ConversationSummaryResponse(**row) for row in ordered]
    if SUMMARY_CACHE_TTL_SECONDS > 0:
        SUMMARY_CACHE[cache_key] = (now, response)
    return response


def build_conversation_signature(context: SessionContext) -> str:
    payload = [
        {
            "other_user_id": row.other_user_id,
            "unread_count": row.unread_count,
            "last_message_id": row.last_message_id,
            "last_message_created_at": row.last_message_created_at,
            "last_read_at": row.last_read_at,
        }
        for row in build_conversation_summaries(context)
    ]
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


@router.get("/chat/conversations", response_model=list[ConversationSummaryResponse])
def list_conversations(context: SessionContext = Depends(get_session_context)) -> list[ConversationSummaryResponse]:
    return build_conversation_summaries(context)


@router.get("/chat/conversations/{with_user_id}/messages", response_model=ChatThreadResponse)
def get_conversation_messages(
    with_user_id: int,
    before: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_THREAD_PAGE_SIZE, ge=1, le=MAX_THREAD_PAGE_SIZE),
    context: SessionContext = Depends(get_session_context),
) -> ChatThreadResponse:
    messages = list_conversation_messages(context, with_user_id)
    page, next_before, has_more = paginate_messages(messages, before, limit)
    return ChatThreadResponse(
        messages=[ChatMessageResponse(**row) for row in page],
        next_before=next_before,
        has_more=has_more,
    )


@router.post("/chat/messages", response_model=ChatMessageResponse)
def create_message(payload: ChatMessageCreateRequest, context: SessionContext = Depends(get_session_context)) -> ChatMessageResponse:
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

    invalidate_summary_cache(context, with_user_id=to_user["id"])
    return ChatMessageResponse(**row)


@router.post("/chat/conversations/{with_user_id}/read", response_model=MarkConversationReadResponse)
def mark_conversation_read(with_user_id: int, context: SessionContext = Depends(get_session_context)) -> MarkConversationReadResponse:
    get_user(context.tenant_id, with_user_id)
    supabase = get_supabase()
    unread_rows = rows(
        supabase.table("messages")
        .select("id, created_at, read_at")
        .eq("tenant_id", context.tenant_id)
        .eq("from_user_id", with_user_id)
        .eq("to_user_id", context.user_id)
        .execute()
    )
    pending = [row for row in unread_rows if row.get("read_at") is None]
    read_at = utc_now_iso() if pending else None
    for row in pending:
        supabase.table("messages").update({"read_at": read_at}).eq("id", row["id"]).execute()

    latest_read = pending[-1]["created_at"] if pending else None
    invalidate_summary_cache(context, with_user_id=with_user_id)
    return MarkConversationReadResponse(with_user_id=with_user_id, unread_count=0, read_through=latest_read)


@router.get("/chat/events/stream")
async def stream_chat_events(request: Request, access_token: str = Query(default="")) -> StreamingResponse:
    context = get_session_context_from_token(access_token)

    async def event_generator():
        last_signature = ""
        yield f"retry: {STREAM_RETRY_MS}\n\n"
        yield "event: ready\n"
        yield 'data: {"type":"ready"}\n\n'
        while True:
            if await request.is_disconnected():
                break
            signature = build_conversation_signature(context)
            if signature != last_signature:
                last_signature = signature
                payload = json.dumps({"type": "chat.sync", "at": utc_now_iso()})
                yield "event: chat.sync\n"
                yield f"data: {payload}\n\n"
            await asyncio.sleep(STREAM_POLL_INTERVAL_SECONDS)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
