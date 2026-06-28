"""Timed lyric segment models and lookup helpers."""
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class LyricWord:
    """A word-level timestamp within a lyric segment."""

    start: float
    end: float
    word: str

    @classmethod
    def from_dict(cls, data: dict) -> "LyricWord":
        return cls(
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            word=str(data.get("word", data.get("text", ""))).strip(),
        )

    def to_dict(self) -> dict:
        return {
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "word": self.word,
        }


@dataclass(frozen=True)
class LyricSegment:
    """A transcribed lyric phrase with playback timestamps in seconds."""

    start: float
    end: float
    text: str
    language: str = ""
    words: tuple[LyricWord, ...] = ()

    @classmethod
    def from_dict(cls, data: dict) -> "LyricSegment":
        return cls(
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            text=str(data.get("text", "")),
            language=str(data.get("language", "")),
            words=tuple(
                word for word in (LyricWord.from_dict(item) for item in data.get("words", []))
                if word.word
            ),
        )

    def to_dict(self) -> dict:
        return {
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "text": self.text,
            "language": self.language,
            "words": [word.to_dict() for word in self.words],
        }


def normalize_lyrics(segments: Iterable[dict | LyricSegment]) -> list[LyricSegment]:
    """Return valid lyric segments sorted by start time."""
    normalized = []
    for segment in segments:
        item = segment if isinstance(segment, LyricSegment) else LyricSegment.from_dict(segment)
        if item.end <= item.start or not item.text.strip():
            continue
        normalized.append(item)
    return sorted(normalized, key=lambda item: item.start)


def get_current_lyric(
    current_time: float,
    segments: Iterable[dict | LyricSegment],
) -> tuple[Optional[LyricSegment], Optional[LyricSegment]]:
    """Return the current and next lyric segment for a playback time."""
    lyrics = normalize_lyrics(segments)
    current = None
    next_segment = None

    for index, segment in enumerate(lyrics):
        if segment.start <= current_time < segment.end:
            current = segment
            next_segment = lyrics[index + 1] if index + 1 < len(lyrics) else None
            break
        if segment.start > current_time:
            next_segment = segment
            break

    return current, next_segment


def get_current_word(
    current_time: float,
    segment: LyricSegment | None,
) -> LyricWord | None:
    """Return the active word inside a lyric segment, when word timestamps exist."""
    if not segment or not segment.words:
        return None
    for word in segment.words:
        if word.start <= current_time < word.end:
            return word
    return None
