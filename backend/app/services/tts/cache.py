import time
from typing import Dict, Optional, Tuple


class EphemeralTTSCache:
    def __init__(self, max_items: int = 200, ttl_seconds: int = 1800):
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        # key -> (audio_bytes, timestamp)
        self._cache: Dict[str, Tuple[bytes, float]] = {}

    def get(self, session_id: str, turn_id: str) -> Optional[bytes]:
        key = f"{session_id}:{turn_id}"
        entry = self._cache.get(key)
        if not entry:
            return None

        audio_bytes, created_at = entry
        if time.time() - created_at > self.ttl_seconds:
            self._cache.pop(key, None)
            return None

        return audio_bytes

    def put(self, session_id: str, turn_id: str, audio_bytes: bytes):
        if not audio_bytes:
            return

        # Evict expired or oldest if capacity reached
        if len(self._cache) >= self.max_items:
            now = time.time()
            expired_keys = [k for k, (_, t) in self._cache.items() if now - t > self.ttl_seconds]
            for k in expired_keys:
                self._cache.pop(k, None)

            if len(self._cache) >= self.max_items:
                # Evict oldest entry
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                self._cache.pop(oldest_key, None)

        key = f"{session_id}:{turn_id}"
        self._cache[key] = (audio_bytes, time.time())

    def clear_session(self, session_id: str):
        prefix = f"{session_id}:"
        keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
        for k in keys_to_delete:
            self._cache.pop(k, None)


tts_cache = EphemeralTTSCache()
