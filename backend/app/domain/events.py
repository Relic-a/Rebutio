import asyncio
import json
from typing import Dict, List, Set


class SessionEventManager:
    def __init__(self):
        # session_id -> list of asyncio.Queue
        self._listeners: Dict[str, Set[asyncio.Queue]] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._listeners:
            self._listeners[session_id] = set()
        queue: asyncio.Queue = asyncio.Queue()
        self._listeners[session_id].add(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue):
        if session_id in self._listeners:
            self._listeners[session_id].discard(queue)
            if not self._listeners[session_id]:
                self._listeners.pop(session_id, None)

    async def emit(self, session_id: str, event_type: str, data: dict = None):
        if session_id not in self._listeners:
            return

        payload = {"type": event_type, "data": data or {}}
        json_str = json.dumps(payload)
        
        dead_queues = []
        for q in self._listeners[session_id]:
            try:
                await q.put(json_str)
            except Exception:
                dead_queues.append(q)

        for dq in dead_queues:
            self.unsubscribe(session_id, dq)


session_events = SessionEventManager()
