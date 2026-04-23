import React from "react";

function formatRelativeTimestamp(value) {
  if (!value) return "No messages yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "No messages yet";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function previewText(conversation) {
  if (!conversation.last_message_text) {
    return "Start the conversation";
  }
  const prefix = conversation.last_message_direction === "outgoing" ? "You: " : "";
  return `${prefix}${conversation.last_message_text}`;
}

export default function ChatConversationRail({
  activeConversationId,
  conversations,
  isLoading,
  onSelectConversation,
}) {
  return (
    <aside className="chat-rail">
      <div className="chat-rail-header">
        <div>
          <p className="chat-kicker">Messaging</p>
          <h2>Conversations</h2>
        </div>
      </div>

      <div className="chat-rail-body">
        {isLoading ? <div className="chat-rail-empty">Loading conversations...</div> : null}
        {!isLoading && conversations.length === 0 ? (
          <div className="chat-rail-empty">No coworkers are available in this tenant yet.</div>
        ) : null}
        {!isLoading &&
          conversations.map((conversation) => {
            const isActive = conversation.other_user_id === activeConversationId;
            const title = (conversation.other_user_email || "").split("@")[0] || `User ${conversation.other_user_id}`;
            return (
              <button
                key={conversation.conversation_id}
                type="button"
                className={isActive ? "chat-conversation chat-conversation-active" : "chat-conversation"}
                onClick={() => onSelectConversation(conversation.other_user_id)}
              >
                <div className="chat-conversation-topline">
                  <strong>{title}</strong>
                  <span>{formatRelativeTimestamp(conversation.last_message_created_at)}</span>
                </div>
                <div className="chat-conversation-preview">{previewText(conversation)}</div>
                <div className="chat-conversation-meta">
                  <span>{conversation.other_user_role}</span>
                  {conversation.unread_count > 0 ? (
                    <span className="chat-unread-badge">{conversation.unread_count}</span>
                  ) : null}
                </div>
              </button>
            );
          })}
      </div>
    </aside>
  );
}
