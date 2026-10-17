"""Bounded request metadata, separate from durable project memory."""

from collections import deque
from datetime import datetime, timezone
from threading import Lock


class ActivityJournal:
    def __init__(self, capacity=200):
        self.entries = deque(maxlen=capacity)
        self.lock = Lock()

    def record(self, route, body, status, client, elapsed_ms):
        # Never retain raw inputs, response bodies, or exception messages.
        entry = {"route": route, "status": status, "client": client,
                 "recorded_at": datetime.now(timezone.utc).isoformat(),
                 "elapsed_ms": round(elapsed_ms),
                 **{key: value[:160] for key in ("project_id", "scope", "event_id")
                    if isinstance(value := body.get(key), str)}}
        with self.lock:
            self.entries.append(entry)

    def read(self, project, scope=None):
        with self.lock:
            return [dict(item) for item in reversed(self.entries)
                    if item.get("project_id") == project
                    and (scope is None or item.get("scope") in (None, scope))][:50]
