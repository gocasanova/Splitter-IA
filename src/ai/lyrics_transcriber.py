"""Automatic lyric transcription using optional local Whisper backends."""
import os
from pathlib import Path

from src.models.lyrics import LyricSegment, LyricWord
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class TranscriptionDependencyError(RuntimeError):
    """Raised when no supported local transcription backend is installed."""


class LyricsTranscriber:
    """Transcribe vocals or fallback audio into timed lyric segments."""

    def __init__(self, model_size: str | None = None):
        self.model_size = model_size or os.environ.get("WHISPER_MODEL", "small")

    def transcribe(self, audio_path: Path, language: str | None = None) -> list[LyricSegment]:
        """Return timed lyric segments from an audio file."""
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise TranscriptionDependencyError(
                "faster-whisper is not installed. Install it with: pip install faster-whisper"
            ) from exc

        logger.info("Transcribing lyrics from: %s", audio_path)
        model = WhisperModel(self.model_size, device="auto", compute_type="auto")
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
            beam_size=5,
            word_timestamps=True,
        )
        language = getattr(info, "language", "") or ""
        output = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            output.append(
                LyricSegment(
                    start=float(segment.start),
                    end=float(segment.end),
                    text=text,
                    language=language,
                    words=tuple(
                        LyricWord(
                            start=float(word.start),
                            end=float(word.end),
                            word=word.word.strip(),
                        )
                        for word in (segment.words or [])
                        if word.word.strip()
                    ),
                )
            )
        return output
