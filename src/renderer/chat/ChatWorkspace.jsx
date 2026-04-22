import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useChat } from "./ChatProvider.jsx";
import ChatConversationRail from "./ChatConversationRail.jsx";
import ChatMessagePane from "./ChatMessagePane.jsx";

function sortMessages(messages) {
  return [...messages].sort((left, right) => {
    const leftStamp = `${left.created_at}|${String(left.id)}`;
    const rightStamp = `${right.created_at}|${String(right.id)}`;
    return leftStamp.localeCompare(rightStamp);
  });
}

function mergeMessages(existing, incoming) {
  const byId = new Map(existing.map((message) => [String(message.id), message]));
  for (const message of incoming) {
    byId.set(String(message.id), { ...byId.get(String(message.id)), ...message });
  }
  return sortMessages([...byId.values()]);
}

function createEmptyThread() {
  return {
    messages: [],
    hasMore: false,
    nextBefore: null,
    initialized: false,
    loadingInitial: false,
    loadingOlder: false,
    error: "",
  };
}

export default function ChatWorkspace({ mode = "embedded" }) {
  const {
    conversationError,
    conversations,
    draftsByUserId,
    isLoadingConversations,
    markConversationRead,
    openPopup,
    refreshConversations,
    selectConversation,
    streamState,
    unreadTotal,
    updateDraft,
    userId,
  } = useChat();
  const [selectedConversationId, setSelectedConversationId] = useState(null);
  const [visibleThread, setVisibleThread] = useState(createEmptyThread());

  useEffect(() => {
    if (!conversations.length) {
      setSelectedConversationId(null);
      return;
    }
    setSelectedConversationId((current) => {
      if (current && conversations.some((conversation) => conversation.other_user_id === current)) {
        return current;
      }
      return conversations[0]?.other_user_id ?? null;
    });
  }, [conversations]);

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.other_user_id === selectedConversationId) || null,
    [conversations, selectedConversationId]
  );
  const draft = draftsByUserId[selectedConversationId] || "";

  const loadVisibleThread = useCallback(
    async ({ before = null, append = false } = {}) => {
      if (!selectedConversationId) {
        setVisibleThread(createEmptyThread());
        return;
      }

      setVisibleThread((current) => ({
        ...current,
        loadingInitial: !append,
        loadingOlder: append,
        error: "",
      }));

      const result = await window.electronAPI.chat.getMessages({
        withUserId: selectedConversationId,
        before,
        limit: 40,
      });

      if (!result.ok) {
        setVisibleThread((current) => ({
          ...current,
          initialized: true,
          loadingInitial: false,
          loadingOlder: false,
          error: result.error || "Failed to load messages.",
        }));
        return;
      }

      const payload = result.data || {};
      const nextMessages = Array.isArray(payload.messages) ? payload.messages : [];
      setVisibleThread((current) => ({
        ...current,
        messages: append ? mergeMessages(nextMessages, current.messages || []) : sortMessages(nextMessages),
        hasMore: Boolean(payload.has_more),
        nextBefore: payload.next_before || null,
        initialized: true,
        loadingInitial: false,
        loadingOlder: false,
        error: "",
      }));
    },
    [selectedConversationId]
  );

  useEffect(() => {
    if (!selectedConversationId) {
      setVisibleThread(createEmptyThread());
      return;
    }
    setVisibleThread(createEmptyThread());
    loadVisibleThread();
  }, [loadVisibleThread, selectedConversationId]);

  useEffect(() => {
    if (!selectedConversationId || !activeConversation?.unread_count) return;
    markConversationRead(selectedConversationId);
  }, [activeConversation?.unread_count, markConversationRead, selectedConversationId]);

  const handleSelectConversation = useCallback(
    (withUserId) => {
      setSelectedConversationId(withUserId);
      selectConversation(withUserId);
    },
    [selectConversation]
  );

  const handleLoadOlder = useCallback(async () => {
    if (!visibleThread.hasMore || !visibleThread.nextBefore || visibleThread.loadingOlder) return;
    await loadVisibleThread({ before: visibleThread.nextBefore, append: true });
  }, [loadVisibleThread, visibleThread.hasMore, visibleThread.loadingOlder, visibleThread.nextBefore]);

  const handleSend = useCallback(async () => {
    if (!selectedConversationId) {
      return { ok: false, error: "Select a conversation first." };
    }

    const currentDraft = draft.trim();
    if (!currentDraft) {
      return { ok: false, error: "Message text is required." };
    }

    const optimisticId = `optimistic-${Date.now()}`;
    const optimisticMessage = {
      id: optimisticId,
      from_user_id: userId,
      to_user_id: selectedConversationId,
      text: currentDraft,
      created_at: new Date().toISOString(),
      read_at: null,
      pending: true,
    };

    updateDraft(selectedConversationId, "");
    setVisibleThread((current) => ({
      ...current,
      initialized: true,
      error: "",
      messages: mergeMessages(current.messages || [], [optimisticMessage]),
    }));

    const result = await window.electronAPI.chat.sendMessage({
      toUserId: selectedConversationId,
      text: currentDraft,
    });

    if (!result.ok) {
      updateDraft(selectedConversationId, currentDraft);
      setVisibleThread((current) => ({
        ...current,
        error: result.error || "Failed to send message.",
        messages: (current.messages || []).map((message) =>
          String(message.id) === optimisticId ? { ...message, pending: false, failed: true } : message
        ),
      }));
      return { ok: false, error: result.error || "Failed to send message." };
    }

    const sentMessage = result.data;
    setVisibleThread((current) => ({
      ...current,
      error: "",
      messages: mergeMessages(
        (current.messages || []).filter((message) => String(message.id) !== optimisticId),
        [sentMessage]
      ),
    }));
    refreshConversations();
    return { ok: true };
  }, [draft, refreshConversations, selectedConversationId, updateDraft, userId]);

  return (
    <section className={mode === "popup" ? "chat-workspace chat-workspace-popup" : "chat-workspace"}>
      <div className="chat-shell-header">
        <div>
          <p className="chat-kicker">Workspace chat</p>
          <h1>Team messages</h1>
        </div>
        <div className="chat-shell-actions">
          <span className="chat-shell-summary">{unreadTotal > 0 ? `${unreadTotal} unread` : "All caught up"}</span>
          {mode === "embedded" ? (
            <button type="button" className="secondary-btn" onClick={openPopup}>
              Open popup
            </button>
          ) : null}
        </div>
      </div>

      {conversationError ? <p className="chat-inline-error">{conversationError}</p> : null}

      <div className={mode === "popup" ? "chat-layout chat-layout-popup" : "chat-layout"}>
        <ChatConversationRail
          activeConversationId={selectedConversationId}
          conversations={conversations}
          isLoading={isLoadingConversations}
          onSelectConversation={handleSelectConversation}
        />
        <ChatMessagePane
          key={selectedConversationId || "empty"}
          activeConversation={activeConversation}
          activeThread={visibleThread}
          currentUserId={userId}
          draft={draft}
          activeConversationId={selectedConversationId}
          mode={mode}
          onDraftChange={(value) => updateDraft(selectedConversationId, value)}
          onLoadOlder={handleLoadOlder}
          onSend={handleSend}
          streamState={streamState}
        />
      </div>
    </section>
  );
}
