"""A bounded, in-memory voice cache. No generated speech is written to disk."""
from collections import OrderedDict

from ..contracts import Result
from ..providers.base import VoiceProvider


class VoiceService:
    def __init__(self, provider: VoiceProvider, cache_bytes: int):
        self.provider = provider
        self.limit = cache_bytes
        self._cache = OrderedDict()
        self._size = 0

    def start(self):
        self.provider.start()

    def execute(self, request, cancel, on_delta):
        # Exactly one voice worker owns this cache and the native model.
        cancel.check()
        if request in self._cache:
            self._cache.move_to_end(request)
            result = self._cache[request]
            return Result({**result.details, "cached": True}, result.audio)
        result = self.provider.synthesize(request, cancel)
        cancel.check()
        if result.audio and len(result.audio) <= self.limit:
            while self._cache and self._size + len(result.audio) > self.limit:
                _, evicted = self._cache.popitem(last=False)
                self._size -= len(evicted.audio)
            self._cache[request] = result
            self._size += len(result.audio)
        return result

    def close(self):
        self.provider.close()
