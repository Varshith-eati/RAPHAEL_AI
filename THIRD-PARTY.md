# Included third-party components

The complete portable package includes copies of locally installed dependencies and models for use with Raphael. Their existing license and notice files are preserved; these dependencies are not authored by Raphael. The GitHub/source-only version excludes these bundled runtimes and model weights; the locations below refer to the complete package.

- Python: `engines/python/LICENSE.txt`.
- Python libraries: versions in `requirements.lock.txt`; metadata and licenses in `engines/python/Lib/site-packages/*.dist-info/`. This includes Kokoro-ONNX, ONNX Runtime, faster-whisper, CTranslate2, NumPy and the eSpeak NG phonemizer stack.
- Ollama and its inference backends: `engines/ollama/lib/ollama/*LICENSE*` and bundled library notices. Upstream: https://github.com/ollama/ollama
- Llama 3.2 and Qwen 3.5: original model license layers are kept in the Ollama model store.
- Kokoro model/voice assets: exact source URLs and checksums in `models/checksums.json`. Upstream model: https://huggingface.co/hexgrad/Kokoro-82M
- Whisper base conversion: https://huggingface.co/Systran/faster-whisper-base ; upstream https://github.com/openai/whisper .

Model/runtime files are unchanged. This package does not copy Ollama account keys, browser credentials or personal user files. Preserve upstream license/notice materials when making further copies. The model and dependency licenses apply independently of Raphael's own source.


## Desktop additions in 0.6
PySide6-Essentials / shiboken6 6.11.3 (Qt LGPL/GPL/commercial terms, component dependent), and sounddevice 0.5.6 / PortAudio. Original notices are retained in their bundled package/dist-info directories. No Qt WebEngine is included. Review all upstream obligations before redistributing commercially.
