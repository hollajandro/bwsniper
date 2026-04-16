"""
backend/app/services/worker_pool.py — Registry of active AuctionWorker threads.

Singleton pattern: one pool per server process, keyed by snipe_id.
"""

import threading
from typing import Optional


class WorkerPool:
    """Thread-safe registry of running auction workers."""

    def __init__(self):
        self._lock    = threading.Lock()
        self._workers: dict[str, "AuctionWorker"] = {}  # snipe_id → worker

    def spawn(self, snipe_id: str, worker: "AuctionWorker") -> bool:
        """Register and start a worker.  Returns False if already running.

        worker.start() is called inside the lock to eliminate the TOCTOU window
        between the existence check and start, which prevents a race where two
        concurrent spawn() calls for the same snipe_id could both pass the
        existence check and start two workers.
        """
        with self._lock:
            if snipe_id in self._workers:
                return False
            self._workers[snipe_id] = worker
            worker.start()  # ← inside the lock to prevent TOCTOU race
        return True

    def stop(self, snipe_id: str) -> bool:
        """Signal a worker to stop and remove from registry."""
        with self._lock:
            worker = self._workers.pop(snipe_id, None)
        if worker:
            worker.stop()
            return True
        return False

    def get(self, snipe_id: str) -> Optional["AuctionWorker"]:
        with self._lock:
            return self._workers.get(snipe_id)

    def is_running(self, snipe_id: str) -> bool:
        with self._lock:
            w = self._workers.get(snipe_id)
            return w is not None and w.is_alive()

    def stop_all(self) -> int:
        """Stop all workers (called on shutdown).  Returns count stopped."""
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for w in workers:
            w.stop()
        return len(workers)

    def active_count(self) -> int:
        with self._lock:
            return len(self._workers)

    def active_snipe_ids(self) -> list[str]:
        with self._lock:
            return list(self._workers.keys())

    def cleanup_dead(self) -> list[str]:
        """Remove workers that have finished running.  Returns cleaned IDs."""
        cleaned = []
        with self._lock:
            for sid, w in list(self._workers.items()):
                if not w.is_alive():
                    del self._workers[sid]
                    cleaned.append(sid)
        return cleaned


# Singleton instance — imported by other modules
pool = WorkerPool()
