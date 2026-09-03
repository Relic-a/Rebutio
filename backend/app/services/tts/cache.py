import asyncio
import time
from typing import AsyncIterator, Callable, Dict, List, Optional, Tuple


class ActiveAudioStream:
    def __init__(self, session_id: str, turn_id: str, text: str, voice: Optional[str] = None):
        self.session_id = session_id
        self.turn_id = turn_id
        self.text = text
        self.voice = voice
        self.chunks: List[bytes] = []
        self.subscribers: List[asyncio.Queue] = []
        self.is_done = False
        self.error: Optional[Exception] = None
        self.task: Optional[asyncio.Task] = None

    async def run(self, stream_fn: Callable):
        try:
            async for chunk in stream_fn(self.text, voice=self.voice):
                if chunk:
                    self.chunks.append(chunk)
                    for q in list(self.subscribers):
                        await q.put(chunk)
        except Exception as e:
            self.error = e
        finally:
            self.is_done = True
            for q in list(self.subscribers):
                await q.put(None)

    async def subscribe(self) -> AsyncIterator[bytes]:
        # First yield all chunks accumulated so far
        accumulated = list(self.chunks)
        for chunk in accumulated:
            yield chunk

        if self.is_done:
            return

        q: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self.subscribers.append(q)
        try:
            while True:
                chunk = await q.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            if q in self.subscribers:
                self.subscribers.remove(q)


class EphemeralTTSCache:
    def __init__(self, max_items: int = 200, ttl_seconds: int = 1800):
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        # key -> (audio_bytes, timestamp)
        self._cache: Dict[str, Tuple[bytes, float]] = {}
        # key -> ActiveAudioStream
        self._streams: Dict[str, ActiveAudioStream] = {}

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

    def get_stream(self, session_id: str, turn_id: str) -> Optional[ActiveAudioStream]:
        key = f"{session_id}:{turn_id}"
        stream = self._streams.get(key)
        if stream and not stream.is_done:
            return stream
        return None

    def start_stream(
        self,
        session_id: str,
        turn_id: str,
        text: str,
        stream_fn: Callable,
        voice: Optional[str] = None,
    ) -> ActiveAudioStream:
        key = f"{session_id}:{turn_id}"
        existing = self._streams.get(key)
        if existing and not existing.is_done:
            return existing

        stream = ActiveAudioStream(session_id=session_id, turn_id=turn_id, text=text, voice=voice)
        self._streams[key] = stream

        async def _stream_runner():
            try:
                await stream.run(stream_fn)
                if stream.chunks:
                    full_audio = b"".join(stream.chunks)
                    self.put(session_id, turn_id, full_audio)
            finally:
                # Keep in _streams until subscribers have finished, or clean up
                if key in self._streams and self._streams[key] is stream:
                    # Let existing subscribers complete, schedule removal shortly
                    asyncio.get_event_loop().call_later(5.0, lambda: self._streams.pop(key, None))

        stream.task = asyncio.create_task(_stream_runner())
        return stream

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

        stream_keys_to_delete = [k for k in self._streams if k.startswith(prefix)]
        for k in stream_keys_to_delete:
            stream = self._streams.pop(k, None)
            if stream and stream.task and not stream.task.done():
                stream.task.cancel()


tts_cache = EphemeralTTSCache()

