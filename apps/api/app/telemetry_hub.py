from __future__ import annotations

from dataclasses import dataclass
from queue import Queue
from threading import Lock


@dataclass(eq=False)
class TelemetrySubscription:
    tenant_id: str
    mission_id: str
    queue: Queue[dict]


class TelemetryHub:
    def __init__(self) -> None:
        self._lock = Lock()
        self._subscribers: dict[tuple[str, str], set[TelemetrySubscription]] = {}

    def subscribe(self, tenant_id: str, mission_id: str) -> TelemetrySubscription:
        subscription = TelemetrySubscription(
            tenant_id=tenant_id,
            mission_id=mission_id,
            queue=Queue(),
        )
        key = (tenant_id, mission_id)
        with self._lock:
            self._subscribers.setdefault(key, set()).add(subscription)
        return subscription

    def unsubscribe(self, subscription: TelemetrySubscription) -> None:
        key = (subscription.tenant_id, subscription.mission_id)
        with self._lock:
            subscribers = self._subscribers.get(key)
            if subscribers is None:
                return
            subscribers.discard(subscription)
            if not subscribers:
                self._subscribers.pop(key, None)

    def broadcast(self, tenant_id: str, mission_id: str, message: dict) -> None:
        key = (tenant_id, mission_id)
        with self._lock:
            subscribers = list(self._subscribers.get(key, set()))

        for subscription in subscribers:
            subscription.queue.put(message)
