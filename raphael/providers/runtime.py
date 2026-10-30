"""Serialize native SDK imports shared by independent audio workers."""
from threading import Lock

# ONNX and CTranslate2 both import NumPy. Concurrent first imports on Windows
# can expose partially initialized native modules; model loading stays parallel.
AUDIO_IMPORT_LOCK = Lock()
