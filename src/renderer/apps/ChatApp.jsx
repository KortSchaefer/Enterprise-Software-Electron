import React, { useEffect, useState } from "react";

export default function ChatApp({ tenantId, userId, userEmail }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const [users, setUsers] = useState([]);
  const [otherUserId, setOtherUserId] = useState(null);
  const [unreadByUser, setUnreadByUser] = useState({});

  function getLastSeenKey(withUserId) {
    return `chat:lastSeen:${tenantId}:${userId}:${withUserId}`;
  }

  function getLastSeenMs(withUserId) {
    const raw = localStorage.getItem(getLastSeenKey(withUserId));
    const ms = raw ? Date.parse(raw) : NaN;
    return Number.isNaN(ms) ? 0 : ms;
  }

  function setLastSeen(withUserId, isoTimestamp) {
    if (!withUserId || !isoTimestamp) return;
    localStorage.setItem(getLastSeenKey(withUserId), isoTimestamp);
  }

  function countUnreadForConversation(withUserId, conversation) {
    const lastSeenMs = getLastSeenMs(withUserId);
    return conversation.filter((m) => {
      const isIncoming = m.from_user_id === withUserId && m.to_user_id === userId;
      const createdMs = Date.parse(m.created_at);
      return isIncoming && Number.isFinite(createdMs) && createdMs > lastSeenMs;
    }).length;
  }

  function markConversationSeen(withUserId, conversation) {
    const latestIncoming = [...conversation]
      .reverse()
      .find((m) => m.from_user_id === withUserId && m.to_user_id === userId);
    if (latestIncoming?.created_at) {
      setLastSeen(withUserId, latestIncoming.created_at);
    }
  }

  async function fetchConversation(withUserId) {
    const result = await window.electronAPI.chat.listMessages({
      tenantId,
      userId,
      withUserId,
    });

    if (!result.ok) {
      console.error("Failed to load messages", result.error);
      return null;
    }

    const data = result.data;
    return Array.isArray(data) ? data : [];
  }

  async function loadUnreadCounts() {
    if (!tenantId || !userId || users.length === 0) return;

    const entries = await Promise.all(
      users.map(async (u) => {
        const convo = await fetchConversation(u.id);
        if (!convo) return [u.id, 0];
        return [u.id, countUnreadForConversation(u.id, convo)];
      })
    );

    setUnreadByUser(Object.fromEntries(entries));
  }

  async function loadUsers() {
    if (!tenantId || !userId) return;

    const result = await window.electronAPI.chat.listUsers(tenantId);
    if (!result.ok) {
      console.error("Failed to load users", result.error);
      return;
    }

    const data = Array.isArray(result.data) ? result.data : [];
    const others = data.filter((u) => u.id !== userId);
    setUsers(others);

    if (!otherUserId && others.length > 0) {
      setOtherUserId(others[0].id);
    }
  }

  async function loadMessages() {
    if (!tenantId || !userId || !otherUserId) return;

    setLoading(true);
    try {
      const data = await fetchConversation(otherUserId);
      if (!data) return;

      setMessages(data);
      markConversationSeen(otherUserId, data);
      setUnreadByUser((prev) => ({ ...prev, [otherUserId]: 0 }));
    } finally {
      setLoading(false);
    }
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || !otherUserId) return;

    setInput("");

    const result = await window.electronAPI.chat.sendMessage({
      tenantId,
      fromUserId: userId,
      toUserId: otherUserId,
      text,
    });

    if (!result.ok) {
      console.error("Failed to send message", result.error);
      return;
    }

    const msg = result.data;
    setMessages((prev) => [...prev, msg]);
  }

  useEffect(() => {
    loadUsers();
  }, [tenantId, userId]);

  useEffect(() => {
    loadMessages();
  }, [tenantId, userId, otherUserId]);

  useEffect(() => {
    if (!tenantId || !userId || !otherUserId) return;
    const id = setInterval(loadMessages, 3000);
    return () => clearInterval(id);
  }, [tenantId, userId, otherUserId]);

  useEffect(() => {
    if (!tenantId || !userId || users.length === 0) return;
    loadUnreadCounts();
    const id = setInterval(loadUnreadCounts, 3000);
    return () => clearInterval(id);
  }, [tenantId, userId, users]);

  const otherUser =
    otherUserId != null
      ? users.find((u) => u.id === otherUserId) || null
      : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div style={{ padding: "8px", borderBottom: "1px solid #ddd" }}>
        <strong>Chat</strong> (you: {userEmail || `user ${userId}`}
        {otherUser ? `, chatting with ${(otherUser.email || "").split("@")[0]}` : ""})
      </div>
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <div
          style={{
            width: "140px",
            minWidth: "140px",
            borderRight: "1px solid #ddd",
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: "4px",
            padding: "8px",
          }}
        >
          {users.map((u) => (
            <button
              key={u.id}
              onClick={() => setOtherUserId(u.id)}
              style={{
                padding: "4px 8px",
                borderRadius: "4px",
                border: otherUserId === u.id ? "2px solid #00ff9d" : "1px solid #ccccccc4",
                background: otherUserId === u.id ? "#e6f0ff91" : "rgba(255,255,255,0.9)",
                cursor: "pointer",
                color: "#000",
              }}
            >
              <span
                style={{
                  display: "inline-flex",
                  width: "100%",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                <span>{(u.email || "").split("@")[0]}</span>
                {unreadByUser[u.id] > 0 ? (
                  <span
                    style={{
                      minWidth: "18px",
                      height: "18px",
                      padding: "0 5px",
                      borderRadius: "999px",
                      background: "#ef4444",
                      color: "#fff",
                      fontSize: "11px",
                      fontWeight: 700,
                      lineHeight: "18px",
                      textAlign: "center",
                    }}
                  >
                    {unreadByUser[u.id]}
                  </span>
                ) : null}
              </span>
            </button>
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>
          <div
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "8px",
              background: "#f5f5f5",
            }}
          >
            {loading && <div>Loading...</div>}
            {!loading &&
              messages.map((m) => (
                <div
                  key={m.id}
                  style={{
                    marginBottom: "8px",
                    textAlign: m.from_user_id === userId ? "right" : "left",
                  }}
                >
                  <div
                    style={{
                      display: "inline-block",
                      padding: "6px 10px",
                      borderRadius: "6px",
                      background: m.from_user_id === userId ? "#007bff" : "#e0e0e0",
                      color: m.from_user_id === userId ? "#fff" : "#000",
                      maxWidth: "85%",
                    }}
                  >
                    <div>{m.text}</div>
                    <div
                      style={{
                        marginTop: "4px",
                        fontSize: "11px",
                        opacity: 0.8,
                      }}
                    >
                      {new Date(m.created_at + (m.created_at.includes("Z") ? "" : "Z")).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </div>
                  </div>
                </div>
              ))}
          </div>

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              padding: "8px",
              borderTop: "1px solid #ddd",
              gap: "8px",
            }}
          >
            <input
              style={{ flex: "1 1 140px", minWidth: 0 }}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") sendMessage();
              }}
              placeholder={
                otherUser
                  ? `Type a message to ${(otherUser.email || "").split("@")[0]}...`
                  : "Select a recipient..."
              }
              disabled={!otherUserId}
            />
            <button onClick={sendMessage} disabled={!otherUserId}>
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}