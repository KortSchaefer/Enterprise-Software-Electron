import React from "react";
import ChatWorkspace from "../chat/ChatWorkspace.jsx";

export default function ChatApp({ mode = "embedded" }) {
  return <ChatWorkspace mode={mode} />;
}
