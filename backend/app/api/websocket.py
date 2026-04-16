"""
backend/app/api/websocket.py — WebSocket endpoint for real-time updates.

Authentication uses the first-message pattern:
  1. Client connects to /ws  (no token in path — avoids server log exposure)
  2. Server accepts the socket
  3. Client sends {"type": "auth", "token": "<access_jwt>"}  within 10 seconds
  4. Server validates the token; closes with 4001 on failure
  5. Normal message loop begins (ping/pong, future subscriptions)
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..utils.jwt_utils import decode_token
from ..websocket.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """WebSocket endpoint with first-message JWT authentication."""
    await ws.accept()

    # ── Step 1: wait for auth message ────────────────────────────────────────
    try:
        auth_msg = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
    except asyncio.TimeoutError:
        await ws.close(code=4001, reason="Auth timeout")
        return
    except Exception:
        await ws.close(code=4001, reason="Auth error")
        return

    if not isinstance(auth_msg, dict) or auth_msg.get("type") != "auth":
        await ws.close(code=4001, reason="Expected auth message")
        return

    token = auth_msg.get("token", "")
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        await ws.close(code=4001, reason="Invalid token")
        return

    user_id = payload["sub"]
    ws_manager._register(ws, user_id)
    await ws.send_json({"type": "auth_ok"})

    # ── Step 2: message loop ──────────────────────────────────────────────────
    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await ws.send_json({"type": "pong"})
            # Future: "subscribe_snipes", "unsubscribe_snipes", etc.

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WebSocket error for user %s: %s", user_id, exc)
    finally:
        ws_manager.disconnect(ws, user_id)
