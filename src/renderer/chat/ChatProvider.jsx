import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

const ChatContext = createContext(null);
const THREAD_PAGE_SIZE = 40;
const VISIBLE_REFRESH_MS = 5000;

function draftStorageKey(tenantId, userId, withUserId) {
  return `chat:draft:${tenantId}:${userId}:${withUserId}`;
}

function sortMessages(messages) {
  return [...messages].sort((left, right) => {
    const leftStamp = `${left.created_at}|${String(left.id)}`;
    const rightStamp = `${right.created_at}|${String(right.id)}`;
    return leftStamp.localeCompare(rightStamp);
  });
}

function upsertMessages(existing, incoming) {
  const byId = new Map(existing.map((message) => [String(message.id), message]));
  for (const message of incoming) {
    byId.set(String(message.id), { ...byId.get(String(message.id)), ...message });
  }
  return sortMessages([...byId.values()]);
}

function mergeConversationState(existing, incoming) {
  const previousById = new Map(existing.map((conversation) => [conversation.other_user_id, conversation]));
  return incoming.map((conversation) => {
    const previous = previousById.get(conversation.other_user_id);
    return previous ? { ...previous, ...conversation } : conversation;
  });
}

export function ChatProvider({ tenantId, userId, userEmail, syncEnabled = false, children }) {
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [threadsByUserId, setThreadsByUserId] = useState({});
  const [draftsByUserId, setDraftsByUserId] = useState({});
  const [isLoadingConversations, setIsLoadingConversations] = useState(true);
  const [conversationError, setConversationError] = useState("");
  const [streamState, setStreamState] = useState(syncEnabled ? "polling" : "idle");
  const pollTimerRef = useRef(null);
  const activeConversationIdRef = useRef(activeConversationId);
  const threadsRef = useRef(threadsByUserId);
  const selectedConversationIdRef = useRef(null);

  function debugChat(label, payload = {}) {
    console.log(`[chatDebug] ${label}`, payload);
  }

  useEffect(() => {
    activeConversationIdRef.current = activeConversationId;
  }, [activeConversationId]);

  useEffect(() => {
    threadsRef.current = threadsByUserId;
  }, [threadsByUserId]);

  const clearFallbackPolling = useCallback(() => {
    if (pollTimerRef.current) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const updateDraft = useCallback(
    (withUserId, value) => {
      if (!tenantId || !userId || !withUserId) return;
      setDraftsByUserId((current) => ({ ...current, [withUserId]: value }));
      window.localStorage.setItem(draftStorageKey(tenantId, userId, withUserId), value);
    },
    [tenantId, userId]
  );

  const markConversationRead = useCallback(async (withUserId) => {
    if (!withUserId) return;
    const result = await window.electronAPI.chat.markRead({ withUserId });
    if (!result.ok) {
      return;
    }
    setConversations((current) =>
      current.map((conversation) =>
        conversation.other_user_id === withUserId
          ? { ...conversation, unread_count: 0, last_read_at: new Date().toISOString() }
          : conversation
      )
    );
  }, []);

  const loadMessages = useCallback(
    async (withUserId, options = {}) => {
      const { before = null, append = false, silent = false } = options;
      if (!tenantId || !userId || !withUserId) return;

      setThreadsByUserId((current) => {
        const existing = current[withUserId] || {};
        return {
          ...current,
          [withUserId]: {
            ...existing,
            loadingInitial: !append && !silent,
            loadingOlder: append,
            error: "",
          },
        };
      });

      const result = await window.electronAPI.chat.getMessages({
        withUserId,
        before,
        limit: THREAD_PAGE_SIZE,
      });

      if (!result.ok) {
        debugChat("getMessages:error", { withUserId, before, silent, append, error: result.error });
        setThreadsByUserId((current) => {
          const existing = current[withUserId] || {};
          return {
            ...current,
            [withUserId]: {
              ...existing,
              loadingInitial: false,
              loadingOlder: false,
              initialized: true,
              error: result.error || "Failed to load messages.",
            },
          };
        });
        return;
      }

      const payload = result.data || {};
      const nextMessages = Array.isArray(payload.messages) ? payload.messages : [];
      debugChat("getMessages:success", {
        withUserId,
        before,
        silent,
        append,
        count: nextMessages.length,
        firstMessageId: nextMessages[0]?.id || null,
        lastMessageId: nextMessages[nextMessages.length - 1]?.id || null,
      });
      setThreadsByUserId((current) => {
        const existing = current[withUserId] || {};
        const mergedMessages = append
          ? upsertMessages(nextMessages, existing.messages || [])
          : silent
            ? upsertMessages(existing.messages || [], nextMessages)
            : upsertMessages([], nextMessages);
        return {
          ...current,
          [withUserId]: {
            ...existing,
            messages: mergedMessages,
            hasMore: Boolean(payload.has_more),
            nextBefore: payload.next_before || null,
            initialized: true,
            loadingInitial: false,
            loadingOlder: false,
            error: "",
          },
        };
      });
    },
    [tenantId, userId]
  );

  const refreshConversations = useCallback(async () => {
    if (!tenantId || !userId) return [];

    const result = await window.electronAPI.chat.listConversations();
    if (!result.ok) {
      debugChat("listConversations:error", { error: result.error });
      setConversationError(result.error || "Failed to load conversations.");
      return [];
    }

    const nextConversations = Array.isArray(result.data) ? result.data : [];
    debugChat("listConversations:success", {
      count: nextConversations.length,
      ids: nextConversations.map((conversation) => conversation.other_user_id),
    });
    setConversationError("");
    setConversations((current) => sortConversations(mergeConversationState(current, nextConversations)));
    setActiveConversationId((current) => {
      const preferredId = selectedConversationIdRef.current ?? current;
      if (
        preferredId &&
        nextConversations.some((conversation) => conversation.other_user_id === preferredId)
      ) {
        return preferredId;
      }
      const fallbackId = nextConversations[0]?.other_user_id ?? null;
      selectedConversationIdRef.current = fallbackId;
      return fallbackId;
    });
    return nextConversations;
  }, [tenantId, userId]);

  const refreshVisibleChat = useCallback(async () => {
    if (!syncEnabled || !tenantId || !userId) return;
    await refreshConversations();
  }, [refreshConversations, syncEnabled, tenantId, userId]);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      setIsLoadingConversations(true);
      await refreshConversations();
      if (!cancelled) {
        setIsLoadingConversations(false);
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, [refreshConversations]);

  useEffect(() => {
    const currentWithUserId = activeConversationId;
    if (!syncEnabled) return;
    if (!currentWithUserId) return;
    if (draftsByUserId[currentWithUserId] === undefined) {
      setDraftsByUserId((current) => ({
        ...current,
        [currentWithUserId]: window.localStorage.getItem(draftStorageKey(tenantId, userId, currentWithUserId)) || "",
      }));
    }
    const conversation = conversations.find((item) => item.other_user_id === currentWithUserId);
    if (conversation?.unread_count > 0) {
      markConversationRead(currentWithUserId);
    }
  }, [activeConversationId, conversations, draftsByUserId, markConversationRead, syncEnabled, tenantId, userId]);

  useEffect(() => {
    if (!tenantId || !userId) return undefined;
    if (!syncEnabled) {
      clearFallbackPolling();
      setStreamState("idle");
      return undefined;
    }

    setStreamState("polling");
    clearFallbackPolling();
    refreshVisibleChat();
    pollTimerRef.current = window.setInterval(() => {
      refreshVisibleChat();
    }, VISIBLE_REFRESH_MS);

    return () => {
      clearFallbackPolling();
    };
  }, [
    clearFallbackPolling,
    refreshVisibleChat,
    syncEnabled,
    tenantId,
    userId,
  ]);

  useEffect(() => {
    if (!syncEnabled) return undefined;

    function handleWindowFocus() {
      refreshVisibleChat();
    }

    function handleVisibilityChange() {
      if (!document.hidden) {
        refreshVisibleChat();
      }
    }

    window.addEventListener("focus", handleWindowFocus);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.removeEventListener("focus", handleWindowFocus);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [refreshVisibleChat, syncEnabled]);

  const selectConversation = useCallback(
    (withUserId) => {
      debugChat("selectConversation", {
        withUserId,
        previousActiveConversationId: activeConversationIdRef.current,
      });
      selectedConversationIdRef.current = withUserId;
      setActiveConversationId(withUserId);
    },
    []
  );

  const loadOlderMessages = useCallback(async (withUserId) => {
    if (!withUserId) return;
    const thread = threadsRef.current[withUserId];
    if (!thread?.hasMore || !thread?.nextBefore || thread.loadingOlder) return;
    await loadMessages(withUserId, { before: thread.nextBefore, append: true });
  }, [loadMessages]);

  const sendMessage = useCallback(async (withUserId, draftValue) => {
    debugChat("sendMessage:start", {
      withUserId,
      draftLength: String(draftValue ?? draftsByUserId[withUserId] ?? "").trim().length,
    });
    if (!withUserId) return { ok: false, error: "Select a conversation first." };

    const currentDraft = String(draftValue ?? draftsByUserId[withUserId] ?? "").trim();
    if (!currentDraft) {
      return { ok: false, error: "Message text is required." };
    }

    const optimisticId = `optimistic-${Date.now()}`;
    const optimisticMessage = {
      id: optimisticId,
      tenant_id: tenantId,
      from_user_id: userId,
      to_user_id: withUserId,
      text: currentDraft,
      created_at: new Date().toISOString(),
      read_at: null,
      pending: true,
    };

    updateDraft(withUserId, "");
    setThreadsByUserId((current) => {
      const existing = current[withUserId] || {};
      return {
        ...current,
        [withUserId]: {
          ...existing,
          initialized: true,
          error: "",
          messages: upsertMessages(existing.messages || [], [optimisticMessage]),
        },
      };
    });
    setConversations((current) =>
      sortConversations(
        current.map((conversation) =>
          conversation.other_user_id === withUserId
            ? {
                ...conversation,
                last_message_id: null,
                last_message_text: currentDraft,
                last_message_created_at: optimisticMessage.created_at,
                last_message_direction: "outgoing",
              }
            : conversation
        )
      )
    );

    const result = await window.electronAPI.chat.sendMessage({ toUserId: withUserId, text: currentDraft });
    if (!result.ok) {
      debugChat("sendMessage:error", { withUserId, error: result.error });
      updateDraft(withUserId, currentDraft);
      setThreadsByUserId((current) => {
        const existing = current[withUserId] || {};
        return {
          ...current,
          [withUserId]: {
            ...existing,
            error: result.error || "Failed to send message.",
            messages: (existing.messages || []).map((message) =>
              String(message.id) === optimisticId ? { ...message, pending: false, failed: true } : message
            ),
          },
        };
      });
      return { ok: false, error: result.error || "Failed to send message." };
    }

    const sentMessage = result.data;
    debugChat("sendMessage:success", { withUserId, id: sentMessage?.id || null });
    setThreadsByUserId((current) => {
      const existing = current[withUserId] || {};
      return {
        ...current,
        [withUserId]: {
          ...existing,
          error: "",
          messages: upsertMessages(
            (existing.messages || []).filter((message) => String(message.id) !== optimisticId),
            [sentMessage]
          ),
        },
      };
    });
    setConversations((current) =>
      sortConversations(
        current.map((conversation) =>
          conversation.other_user_id === withUserId
            ? {
                ...conversation,
                last_message_id: sentMessage.id,
                last_message_text: sentMessage.text,
                last_message_created_at: sentMessage.created_at,
                last_message_direction: "outgoing",
              }
            : conversation
        )
      )
    );
    return { ok: true };
  }, [draftsByUserId, tenantId, updateDraft, userId]);

  const openPopup = useCallback(() => window.electronAPI.window.openChat({ tenantId, userId, userEmail }), [tenantId, userEmail, userId]);

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.other_user_id === activeConversationId) || null,
    [activeConversationId, conversations]
  );

  const activeThread = activeConversation
    ? threadsByUserId[activeConversation.other_user_id] || {
        messages: [],
        hasMore: false,
        nextBefore: null,
        initialized: false,
        loadingInitial: false,
        loadingOlder: false,
        error: "",
      }
    : null;
  useEffect(() => {
    debugChat("renderState", {
      activeConversationId,
      activeConversationUserId: activeConversation?.other_user_id || null,
      activeThreadInitialized: Boolean(activeThread?.initialized),
      activeThreadMessageCount: activeThread?.messages?.length || 0,
      conversationsCount: conversations.length,
    });
  }, [activeConversation, activeConversationId, activeThread, conversations.length]);
  const unreadTotal = conversations.reduce((total, conversation) => total + (conversation.unread_count || 0), 0);

  const value = useMemo(
    () => ({
      activeConversation,
      activeConversationId,
      activeThread,
      conversationError,
      conversations,
      draftsByUserId,
      isLoadingConversations,
      loadOlderMessages,
      markConversationRead,
      openPopup,
      refreshConversations,
      selectConversation,
      sendMessage,
      streamState,
      syncEnabled,
      userId,
      unreadTotal,
      updateDraft,
    }),
    [
      activeConversation,
      activeConversationId,
      activeThread,
      conversationError,
      conversations,
      draftsByUserId,
      isLoadingConversations,
      loadOlderMessages,
      markConversationRead,
      openPopup,
      refreshConversations,
      selectConversation,
      sendMessage,
      streamState,
      syncEnabled,
      userId,
      unreadTotal,
      updateDraft,
    ]
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

function sortConversations(conversations) {
  return [...conversations].sort((left, right) => {
    const leftStamp = left.last_message_created_at || "";
    const rightStamp = right.last_message_created_at || "";
    if (leftStamp !== rightStamp) {
      return rightStamp.localeCompare(leftStamp);
    }
    return left.other_user_email.localeCompare(right.other_user_email);
  });
}

export function useChat() {
  const value = useContext(ChatContext);
  if (!value) {
    throw new Error("useChat must be used within a ChatProvider.");
  }
  return value;
}
