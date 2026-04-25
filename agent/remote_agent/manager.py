"""
Agent manager loop that syncs desired work from the backend and reconciles
local remote workers.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .client import BackendControlClient
from .config import AGENT_VERSION, SYNC_INTERVAL_MS
from .worker import RemoteAuctionWorker

logger = logging.getLogger(__name__)


class RemoteAgentManager:
    def __init__(self, client: BackendControlClient) -> None:
        self.client = client
        self._workers: dict[str, RemoteAuctionWorker] = {}
        self._stop_event = threading.Event()
        self._clock_offset_ms: int | None = None

    def stop(self) -> None:
        self._stop_event.set()
        for worker in list(self._workers.values()):
            worker.stop()
            worker.join(timeout=2.0)

    def _collect_worker_reports(self) -> list[dict]:
        return [worker.report_state() for worker in self._workers.values()]

    @staticmethod
    def _parse_server_clock_offset_ms(response: dict) -> int | None:
        server_time = response.get("server_time")
        if not server_time:
            return None
        try:
            server_dt = parsedate_to_datetime(server_time)
        except (TypeError, ValueError):
            try:
                server_dt = datetime.fromisoformat(str(server_time).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return None
        if server_dt.tzinfo is None:
            server_dt = server_dt.replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc) - server_dt.astimezone(timezone.utc)).total_seconds() * 1000)

    def _replace_worker(self, desired: dict) -> None:
        current = self._workers.get(desired["snipe_id"])
        if current:
            current.stop()
            current.join(timeout=2.0)

        worker = RemoteAuctionWorker(desired, report_event=self.client.post_event)
        self._workers[desired["snipe_id"]] = worker
        worker.start()
        logger.info("Started remote worker for %s", desired["snipe_id"])

    def _reconcile(self, response: dict) -> int:
        desired_by_id = {item["snipe_id"]: item for item in response.get("snipes", [])}

        if not response.get("enabled", False):
            for worker in list(self._workers.values()):
                worker.stop()
                worker.join(timeout=2.0)
            self._workers.clear()
            return int(response.get("poll_interval_ms") or SYNC_INTERVAL_MS)

        for snipe_id, desired in desired_by_id.items():
            worker = self._workers.get(snipe_id)
            if worker is None:
                self._replace_worker(desired)
                continue

            if worker.payload_hash != desired["payload_hash"]:
                self._replace_worker(desired)
                continue

            if not worker.is_alive() and not worker.is_terminal():
                self._replace_worker(desired)

        for snipe_id in list(self._workers.keys()):
            if snipe_id in desired_by_id:
                continue
            worker = self._workers.pop(snipe_id)
            worker.stop()
            worker.join(timeout=2.0)
            logger.info("Stopped remote worker for %s", snipe_id)

        poll_interval_ms = int(response.get("poll_interval_ms") or SYNC_INTERVAL_MS)
        return max(500, poll_interval_ms)

    def run_forever(self) -> None:
        poll_interval_ms = SYNC_INTERVAL_MS
        while not self._stop_event.is_set():
            try:
                response = self.client.sync(
                    {
                        "agent_version": AGENT_VERSION,
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                        "clock_offset_ms": self._clock_offset_ms,
                        "workers": self._collect_worker_reports(),
                    }
                )
                parsed_offset = self._parse_server_clock_offset_ms(response)
                if parsed_offset is not None:
                    self._clock_offset_ms = parsed_offset
                poll_interval_ms = self._reconcile(response)
            except Exception as ex:
                logger.warning("Remote agent sync failed: %s", ex)

            self._stop_event.wait(poll_interval_ms / 1000.0)
