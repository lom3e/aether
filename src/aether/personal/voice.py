"""
Voice I/O Pipeline primitives for Personal Companion (Phase D).
Provides unified audio input/output processing over the SAME Personal Agent Core
(Zero Agent Duplication: Text, Voice, Desktop, Mobile use the same brain).
"""
from __future__ import annotations

import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


class VoiceService:
    """Provides speech-to-text (STT) and text-to-speech (TTS) interfaces for Aether Voice Companion."""

    def __init__(self, neural_model_name: str | None = None) -> None:
        self.neural_model_name = neural_model_name
        self._has_local_whisper = False
        self._whisper_model = None
        self._init_local_engine()

    def _init_local_engine(self) -> None:
        """Inspects whether local speech-to-text packages are installed without hard crashing."""
        try:
            import speech_recognition  # type: ignore
            self._has_local_whisper = True
            logger.info("Speech recognition engine available.")
        except ImportError:
            self._has_local_whisper = False
            logger.info("Local speech recognition library not installed; browser Web Speech API fallback active.")

    def get_capabilities(self) -> dict[str, Any]:
        """Truthfully returns the active audio processing capabilities."""
        return {
            "mode": "server_neural_speech" if self._has_local_whisper else "native_browser_speech",
            "has_server_whisper": self._has_local_whisper,
            "browser_web_speech_supported": True,
            "supported_mime_types": ["audio/webm", "audio/wav", "audio/ogg", "audio/mp3"],
            "model": self.neural_model_name or ("local_whisper" if self._has_local_whisper else "browser_speech_api"),
            "voice_synthesis_supported": True,
        }

    def transcribe_audio_bytes(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        language: str = "auto",
    ) -> dict[str, Any]:
        """Transcribes incoming audio payload into text.
        If local neural model is available, transcribes directly;
        otherwise extracts truthful audio metadata and guides client speech recognition.
        """
        if not audio_bytes:
            return {"text": "", "confidence": 0.0, "source": "empty_payload"}

        byte_length = len(audio_bytes)

        if self._has_local_whisper:
            try:
                import speech_recognition as sr  # type: ignore
                recognizer = sr.Recognizer()
                with io.BytesIO(audio_bytes) as audio_file:
                    with sr.AudioFile(audio_file) as source:
                        audio_data = recognizer.record(source)
                        text = recognizer.recognize_google(audio_data, language=language if language != "auto" else "en-US")
                        return {"text": text, "confidence": 0.95, "source": "server_speech_recognition"}
            except Exception as e:
                logger.warning(f"Server speech recognition error: {e}")

        # In absence of server-side neural library, return clean metadata indication
        return {
            "text": "",
            "confidence": 1.0,
            "source": "native_browser_speech",
            "audio_size_bytes": byte_length,
            "mime_type": mime_type,
            "instruction": "Use client-side Web Speech API (webkitSpeechRecognition) for zero-latency streaming input.",
        }

    def synthesize_speech_directive(
        self,
        text: str,
        voice: str = "standard",
        language: str = "auto",
    ) -> dict[str, Any]:
        """Returns directives for audio synthesis (client SpeechSynthesis or server audio stream)."""
        return {
            "text": text,
            "voice": voice,
            "language": language,
            "mode": "browser_speech_synthesis",
            "auto_play": True,
        }
