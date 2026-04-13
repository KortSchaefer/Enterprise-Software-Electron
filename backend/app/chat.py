from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database import SessionLocal
from app.models import User, Message

router = APIRouter()


class ChatSendRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    from_user_id: int
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
    tenant_id: str = Field(min_length=1, max_length=64)
    user_id: int
    with_user_id: int


@router.post("/chat/send", response_model=ChatMessageResponse)
def chat_send(payload: ChatSendRequest) -> ChatMessageResponse:
    tenant_id = payload.tenant_id.strip()
    session = SessionLocal()
    try:
        from_user = session.execute(
            select(User).where(User.id == payload.from_user_id, User.tenant_id == tenant_id)
        ).scalar_one_or_none()
        if not from_user:
            raise HTTPException(status_code=404, detail="Sender not found")

        to_user = session.execute(
            select(User).where(User.id == payload.to_user_id, User.tenant_id == tenant_id)
        ).scalar_one_or_none()
        if not to_user:
            raise HTTPException(status_code=404, detail="Recipient not found")

        row = Message(
            tenant_id=tenant_id,
            from_user_id=from_user.id,
            to_user_id=to_user.id,
            text=payload.text.strip(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        return ChatMessageResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            from_user_id=row.from_user_id,
            to_user_id=row.to_user_id,
            text=row.text,
            created_at=row.created_at.isoformat(),
            read_at=row.read_at.isoformat() if row.read_at else None,
        )
    finally:
        session.close()


@router.post("/chat/messages", response_model=list[ChatMessageResponse])
def chat_messages(payload: ChatListRequest) -> list[ChatMessageResponse]:
    tenant_id = payload.tenant_id.strip()
    session = SessionLocal()
    try:
        user = session.execute(
            select(User).where(User.id == payload.user_id, User.tenant_id == tenant_id)
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        other = session.execute(
            select(User).where(User.id == payload.with_user_id, User.tenant_id == tenant_id)
        ).scalar_one_or_none()
        if not other:
            raise HTTPException(status_code=404, detail="Other user not found")

        rows = session.execute(
            select(Message).where(
                Message.tenant_id == tenant_id,
                (
                    (Message.from_user_id == user.id) & (Message.to_user_id == other.id)
                ) | (
                    (Message.from_user_id == other.id) & (Message.to_user_id == user.id)
                ),
            ).order_by(Message.created_at.asc())
        ).scalars().all()

        return [
            ChatMessageResponse(
                id=row.id,
                tenant_id=row.tenant_id,
                from_user_id=row.from_user_id,
                to_user_id=row.to_user_id,
                text=row.text,
                created_at=row.created_at.isoformat(),
                read_at=row.read_at.isoformat() if row.read_at else None,
            )
            for row in rows
        ]
    finally:
        session.close()