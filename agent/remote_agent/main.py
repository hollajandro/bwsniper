"""
Entry point for the remote redundant snipe agent.
"""

from __future__ import annotations

import logging

from .client import BackendControlClient
from .config import AGENT_API_KEY, AGENT_ID, LOG_LEVEL, MAIN_BACKEND_URL
from .manager import RemoteAgentManager


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = BackendControlClient(MAIN_BACKEND_URL, AGENT_ID, AGENT_API_KEY)
    manager = RemoteAgentManager(client)
    try:
        manager.run_forever()
    finally:
        manager.stop()
        client.close()


if __name__ == "__main__":
    main()
