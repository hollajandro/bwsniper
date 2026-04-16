"""
backend/app/websocket/manager.py — WebSocket ConnectionManager.

Tracks connected clients per user_id and provides broadcast methods.
"""

import json
import asyncio
import logging
from typing import Optional
from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections grouped by user_id."""

    def __init__(self):
        # user_id -> set of WebSocket connections
        self._connections: dict[str, set[WebSocket]] = {}
        # Event loop captured at startup so background threads can schedule sends
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the running event loop.  Called once from the ASGI lifespan."""
        self._loop = loop

    async def connect(self, ws: WebSocket, user_id: str):
        """Accept and register an unauthenticated WebSocket (legacy helper)."""
        await ws.accept()
        self._register(ws, user_id)

    def _register(self, ws: WebSocket, user_id: str) -> None:
        """Register an already-accepted WebSocket under user_id."""
        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(ws)

    def disconnect(self, ws: WebSocket, user_id: str):
        conns = self._connections.get(user_id)
        if conns:
            conns.discard(ws)
            if not conns:
                del self._connections[user_id]

    async def _send_json(self, ws: WebSocket, data: dict):
        try:
            await ws.send_json(data)
        except Exception:
            pass  # connection may have closed

    async def send_to_user(self, user_id: str, message: dict):
        """Send a message to all connections for a specific user."""
        conns = self._connections.get(user_id, set()).copy()
        for ws in conns:
            await self._send_json(ws, message)

    def broadcast_to_user(self, user_id: str, message: dict):
        """Non-async broadcast — safe to call from background threads.

        Schedules the async send on the running event loop that was captured
        at startup via set_loop().  If the loop is not available, the message
        is silently dropped (worker threads should not block on WS delivery).
        """
        conns = self._connections.get(user_id, set()).copy()
        if not conns:
            return
        loop = self._loop
        if loop is None or not loop.is_running():
            log.warning(
                "WebSocket broadcast dropped — no event loop available (user_id=%s, type=%s)",
                user_id, message.get("type", "unknown"),
            )
            return
        for ws in conns:
            asyncio.run_coroutine_threadsafe(
                self._send_json(ws, message), loop)

    async def broadcast_all(self, message: dict):
        """Send to every connected client (all users)."""
        for user_id in list(self._connections.keys()):
            await self.send_to_user(user_id, message)

    def connected_user_ids(self) -> list[str]:
        return list(self._connections.keys())

    def connection_count(self, user_id: Optional[str] = None) -> int:
        if user_id:
            return len(self._connections.get(user_id, set()))
        return sum(len(v) for v in self._connections.values())


# Singleton
ws_manager = ConnectionManager()
