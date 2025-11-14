"""Audio transcription via Groq Whisper.

Returns a structured ``tool_result`` dict that includes the transcript, duration
(mm:ss), and the detected language when available.
"""
import os
import struct
import wave
from typing import Optional, Tuple

from groq import Groq
from dotenv import load_dotenv

from .util import tool_result, with_retries

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def _wav_duration(filepath: str) -> Optional[float]:
    """Read duration from a WAV file without external deps."""
    try:
        with wave.open(filepath, "r") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return None


def _mp3_duration_heuristic(filepath: str) -> Optional[float]:
    """Very rough MP3 duration via file size (assuming ~128 kbps)."""
    try:
        size = os.path.getsize(filepath)
        return size / (128 * 1000 / 8)
    except Exception:
        return None


def _get_duration(filepath: str) -> Optional[float]:
    """Try several methods to get audio duration in seconds."""
    # 1. mutagen (optional but accurate for MP3/M4A)
    try:
        from mutagen import File as MutagenFile  # type: ignore
        audio = MutagenFile(filepath)
        if audio and audio.info:
            return float(audio.info.length)
    except Exception:
        pass

    # 2. wave stdlib for WAV
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".wav":
        dur = _wav_duration(filepath)
        if dur:
            return dur

    # 3. heuristic for MP3
    if ext == ".mp3":
        return _mp3_duration_heuristic(filepath)

    return None


def _fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "unknown"
    total = int(round(seconds))
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def transcribe_audio(filepath: str) -> dict:
    """Transcribe audio using Groq Whisper; return transcript + duration metadata."""
    duration_s = _get_duration(filepath)
    duration_str = _fmt_duration(duration_s)

    try:
        with open(filepath, "rb") as f:
            audio_bytes = f.read()

        response = with_retries(
            client.audio.transcriptions.create,
            file=(os.path.basename(filepath), audio_bytes),
            model="whisper-large-v3",
            response_format="verbose_json",  # gives language + segments
            temperature=0.0,
        )

        # verbose_json returns an object with .text and .language
        text = getattr(response, "text", "") or ""
        language = getattr(response, "language", None)

        # Attempt to get duration from Whisper's own metadata first.
        whisper_duration = getattr(response, "duration", None)
        if whisper_duration:
            duration_s = float(whisper_duration)
            duration_str = _fmt_duration(duration_s)

        if not text.strip():
            return tool_result(
                True, "", None,
                source_type="audio", method="whisper-large-v3",
                duration=duration_str, language=language or "unknown",
                note="Whisper returned no text.",
            )

        return tool_result(
            True, text.strip(), None,
            source_type="audio", method="whisper-large-v3",
            duration=duration_str, language=language or "auto",
        )

    except Exception as exc:  # noqa: BLE001
        return tool_result(
            False, "", f"Transcription failed: {exc}",
            source_type="audio", method="whisper-large-v3",
            duration=duration_str,
        )
