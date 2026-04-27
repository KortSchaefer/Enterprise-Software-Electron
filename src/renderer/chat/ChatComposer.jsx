import React from "react";

export default function ChatComposer({
  disabled,
  draft,
  error,
  onChange,
  onSend,
  placeholder,
}) {
  return (
    <div className="chat-composer">
      {error ? <p className="chat-inline-error">{error}</p> : null}
      <div className="chat-composer-row">
        <textarea
          className="chat-composer-input"
          rows={3}
          value={draft}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
          placeholder={placeholder}
          disabled={disabled}
        />
        <button type="button" className="chat-send-button" onClick={onSend} disabled={disabled}>
          Send
        </button>
      </div>
    </div>
  );
}
