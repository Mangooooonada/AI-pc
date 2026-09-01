"""Speech to text using SpeechRecognition + the system microphone."""
from __future__ import annotations

from typing import Optional

from ..config import config


class Ears:
    """Thin wrapper so the rest of the app doesn't care which engine is used."""

    def __init__(self) -> None:
        self.ok = False
        self.error: Optional[str] = None
        try:
            import speech_recognition as sr  # type: ignore

            self.sr = sr
            self.recognizer = sr.Recognizer()
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
            self.microphone = sr.Microphone()
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.6)
            self.ok = True
        except Exception as exc:
            self.error = (
                f"Microphone unavailable ({exc}). Install with: "
                "pip install SpeechRecognition pyaudio"
            )

    def listen(self, timeout: float = 6.0, phrase_limit: float = 12.0) -> str:
        """Record one utterance and transcribe it. Returns '' on silence."""
        if not self.ok:
            return ""
        try:
            with self.microphone as source:
                audio = self.recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_limit
                )
        except Exception:
            return ""
        # Prefer local Whisper if installed, otherwise Google's free endpoint.
        try:
            import whisper  # type: ignore  # noqa: F401

            return self.recognizer.recognize_whisper(audio, model="base.en").strip()
        except Exception:
            pass
        try:
            return self.recognizer.recognize_google(audio).strip()
        except Exception:
            return ""


def strip_wake_word(text: str) -> tuple[bool, str]:
    """Return (heard_wake_word, command_text)."""
    low = text.lower().strip()
    wake = config.wake_word
    if wake in low:
        idx = low.index(wake) + len(wake)
        return True, text[idx:].strip(" ,.:;!?")
    return False, text.strip()
