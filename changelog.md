# Changelog

## 2026-03-30 — Chat IPC / Remove Machine Lock /Darrick

Emmanuel asked how I was handling traffic for the chat, which flagged
that I was locking it to a specific machine or network by hardcoding
localhost calls in the renderer.

To avoid tearing up too much existing code, I moved the chat calls out
of the renderer into the Electron main process using the FastAPI IPC
method already used by the rest of the app. Backend URL is now pulled
from a BACKEND_URL environment variable so when the backend gets hosted
on a server, all clients point there and chat is no longer machine or
network locked.

Files changed:
- src/main/chatIpc.js — added chat IPC handlers
- src/main/preload.js — exposed chat bridge under electronAPI.chat
- src/renderer/apps/ChatApp.jsx — switched from fetch(localhost) to electronAPI.chat.*