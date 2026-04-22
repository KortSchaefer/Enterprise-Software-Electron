import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import ChatComposer from "./ChatComposer.jsx";

function formatClock(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatHeaderTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "No activity yet";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function useMessageGroups(messages) {
  return useMemo(() => {
    const groups = [];
    for (const message of messages || []) {
      const previous = groups[groups.length - 1];
      const sameSender = previous && previous.senderId === message.from_user_id;
      if (sameSender) {
        previous.messages.push(message);
      } else {
        groups.push({
          key: `${message.from_user_id}-${message.created_at}-${message.id}`,
          senderId: message.from_user_id,
          messages: [message],
        });
      }
    }
    return groups;
  }, [messages]);
}

export default function ChatMessagePane({
  activeConversation,
  activeConversationId,
  activeThread,
  currentUserId,
  draft,
  mode,
  onDraftChange,
  onLoadOlder,
  onSend,
  streamState,
}) {
  const scrollerRef = useRef(null);
  const [shouldStickToBottom, setShouldStickToBottom] = useState(true);
  const [previousHeight, setPreviousHeight] = useState(0);
  const messageGroups = useMessageGroups(activeThread?.messages || []);

  useEffect(() => {
    const node = scrollerRef.current;
    if (!node) return;

    function handleScroll() {
      const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
      setShouldStickToBottom(distanceFromBottom < 80);
    }

    node.addEventListener("scroll", handleScroll);
    handleScroll();
    return () => node.removeEventListener("scroll", handleScroll);
  }, []);

  useLayoutEffect(() => {
    const node = scrollerRef.current;
    if (!node) return;

    if (activeThread?.loadingOlder && previousHeight > 0) {
      const delta = node.scrollHeight - previousHeight;
      node.scrollTop += delta;
      setPreviousHeight(0);
      return;
    }

    if (shouldStickToBottom) {
      node.scrollTop = node.scrollHeight;
    }
  }, [activeThread?.loadingOlder, activeThread?.messages, previousHeight, shouldStickToBottom]);

  if (!activeConversation) {
    return (
      <section className="chat-thread-empty">
        <h2>Select a conversation</h2>
        <p>Open a coworker thread to view history and send messages.</p>
      </section>
    );
  }

  const title = (activeConversation.other_user_email || "").split("@")[0] || `User ${activeConversation.other_user_id}`;

  return (
    <section className={mode === "popup" ? "chat-thread chat-thread-popup" : "chat-thread"}>
      <header className="chat-thread-header">
        <div>
          <p className="chat-kicker">{activeConversation.other_user_role}</p>
          <h2>{title}</h2>
        </div>
        <div className="chat-thread-status">
          <span>{streamState === "live" ? "Live" : streamState === "connecting" ? "Connecting" : "Polling fallback"}</span>
          <span>{formatHeaderTime(activeConversation.last_message_created_at)}</span>
        </div>
      </header>

      <div className="chat-thread-body" ref={scrollerRef}>
        {activeThread?.hasMore ? (
          <div className="chat-history-load">
            <button
              type="button"
              className="secondary-btn chat-history-button"
              onClick={() => {
                const node = scrollerRef.current;
                setPreviousHeight(node ? node.scrollHeight : 0);
                onLoadOlder();
              }}
              disabled={activeThread.loadingOlder}
            >
              {activeThread.loadingOlder ? "Loading older messages..." : "Load older messages"}
            </button>
          </div>
        ) : null}

        {activeThread?.loadingInitial ? <div className="chat-thread-empty">Loading messages...</div> : null}
        {!activeThread?.loadingInitial && messageGroups.length === 0 ? (
          <div className="chat-thread-empty">
            <h2>No messages yet</h2>
            <p>Send the first message to start this thread.</p>
          </div>
        ) : null}

        {!activeThread?.loadingInitial &&
          messageGroups.map((group) => {
            const isOwn = group.senderId === currentUserId;
            return (
              <div key={group.key} className={isOwn ? "chat-message-group chat-message-group-own" : "chat-message-group"}>
                {group.messages.map((message) => (
                  <article
                    key={String(message.id)}
                    className={isOwn ? "chat-message-bubble chat-message-bubble-own" : "chat-message-bubble"}
                  >
                    <p>{message.text}</p>
                    <div className="chat-message-meta">
                      <span>{formatClock(message.created_at)}</span>
                      {message.pending ? <span>Sending...</span> : null}
                      {message.failed ? <span>Failed</span> : null}
                    </div>
                  </article>
                ))}
              </div>
            );
          })}
      </div>

      <ChatComposer
        disabled={!activeConversation}
        draft={draft}
        error={activeThread?.error || ""}
        onChange={onDraftChange}
        onSend={onSend}
        placeholder={`Message ${title}`}
      />
    </section>
  );
}
