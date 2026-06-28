"""Audio metadata extraction, filename cleanup, and cached tempo analysis."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

_TRACK_PREFIX = re.compile(r"^\s*\d{1,3}(?:[\s._-]+)")
_SPOTISAVER_SUFFIX = re.compile(r"\s*\(\s*spotisaver\s*\)\s*$", re.IGNORECASE)
_TRAILING_ID = re.compile(r"\s*\[([A-Za-z0-9_-]{8,})\]\s*$")
_ARTIST_TITLE_SEPARATOR = re.compile(r"\s+(?:-|–)\s+")


def clean_display_name(value: str) -> str:
    """Remove common downloader/track noise without stripping meaningful text."""
    cleaned = " ".join(str(value or "").strip().split())
    cleaned = _TRACK_PREFIX.sub("", cleaned)
    cleaned = _TRAILING_ID.sub("", cleaned)
    cleaned = _SPOTISAVER_SUFFIX.sub("", cleaned)
    return cleaned.strip(" ._-")


def infer_artist_title(filename: str | Path) -> tuple[str, str]:
    """Infer ``artist, title`` from a conventional audio filename."""
    stem = Path(filename).stem
    cleaned = clean_display_name(stem)
    parts = _ARTIST_TITLE_SEPARATOR.split(cleaned, maxsplit=1)
    if len(parts) == 2 and all(part.strip() for part in parts):
        return clean_display_name(parts[0]), clean_display_name(parts[1])
    return "", cleaned


def _first_tag(tags: Any, *keys: str) -> str:
    if not tags:
        return ""
    lowered = {str(key).lower(): value for key, value in tags.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def read_audio_metadata(file_path: Path) -> dict:
    """Read embedded tags first, then fill missing values from the filename."""
    inferred_artist, inferred_title = infer_artist_title(file_path.name)
    title = ""
    artist = ""
    duration = None
    tempo = None

    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(str(file_path), easy=True)
        if audio is not None:
            title = _first_tag(audio.tags, "title")
            artist = _first_tag(audio.tags, "artist", "albumartist", "album artist")
            tempo = _positive_float(_first_tag(audio.tags, "bpm", "tempo"))
            duration = _positive_float(getattr(getattr(audio, "info", None), "length", None))
    except ImportError:
        logger.warning("mutagen is not installed; embedded audio tags are unavailable")
    except Exception as exc:
        logger.warning("Could not read embedded metadata from %s: %s", file_path, exc)

    if duration is None:
        try:
            import soundfile as sf

            info = sf.info(str(file_path))
            if info.samplerate:
                duration = info.frames / info.samplerate
        except Exception:
            try:
                import librosa

                duration = _positive_float(librosa.get_duration(path=str(file_path)))
            except Exception as exc:
                logger.warning("Could not read duration from %s: %s", file_path, exc)

    cleaned_artist = clean_display_name(artist) or inferred_artist
    cleaned_title = clean_display_name(title) or inferred_title
    title_parts = _ARTIST_TITLE_SEPARATOR.split(cleaned_title, maxsplit=1)
    if (
        cleaned_artist
        and len(title_parts) == 2
        and title_parts[0].strip().casefold() == cleaned_artist.casefold()
    ):
        cleaned_title = clean_display_name(title_parts[1])

    return {
        "file": file_path.name,
        "title": cleaned_title,
        "artist": cleaned_artist,
        "duration": duration or 0.0,
        "tempo": tempo or "",
        "size_mb": file_path.stat().st_size / (1024 * 1024),
    }


def analyze_tempo(file_path: Path, max_seconds: float = 120.0) -> float | None:
    """Estimate BPM from a bounded audio window for background library analysis."""
    try:
        import librosa
        import numpy as np

        duration = _positive_float(librosa.get_duration(path=str(file_path))) or 0.0
        offset = min(15.0, max(0.0, duration - max_seconds) / 2.0)
        audio, sample_rate = librosa.load(
            str(file_path),
            sr=22050,
            mono=True,
            offset=offset,
            duration=max_seconds,
        )
        tempo, _ = librosa.beat.beat_track(y=audio, sr=sample_rate)
        value = float(np.asarray(tempo).reshape(-1)[0])
        if value <= 0:
            return None
        while value < 55:
            value *= 2
        while value > 220:
            value /= 2
        return round(value, 1)
    except Exception as exc:
        logger.warning("Could not analyze tempo from %s: %s", file_path, exc)
        return None
