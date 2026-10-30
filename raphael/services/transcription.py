"""Speech-input service; the job manager owns its single recognition worker."""
from ..providers.base import TranscriptionProvider


class TranscriptionService:
    def __init__(self, provider: TranscriptionProvider):
        self.provider = provider

    def start(self):
        self.provider.start()

    def execute(self, request, cancel, on_delta):
        return self.provider.transcribe(request, cancel, on_delta)

    def close(self):
        self.provider.close()
