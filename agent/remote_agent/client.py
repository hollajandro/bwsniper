"""
Thin HTTP client for the backend remote-agent control plane.
"""

from __future__ import annotations

from typing import Any

import httpx


class BackendControlClient:
    def __init__(self, base_url: str, agent_id: str, api_key: str) -> None:
        self.agent_id = agent_id
        self._client = httpx.Client(
            base_url=base_url,
            headers={"X-Agent-Key": api_key},
            timeout=15.0,
        )

    def sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(
            f"/internal/remote-agents/{self.agent_id}/sync",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def post_event(self, payload: dict[str, Any]) -> None:
        response = self._client.post(
            f"/internal/remote-agents/{self.agent_id}/events",
            json=payload,
        )
        response.raise_for_status()

    def close(self) -> None:
        self._client.close()
