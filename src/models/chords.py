"""Timed chord segment models and lookup helpers."""
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class ChordSegment:
    """An approximate chord label with playback timestamps in seconds."""

    start: float
    end: float
    chord: str
    confidence: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "ChordSegment":
        return cls(
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            chord=str(data.get("chord", "")),
            confidence=float(data.get("confidence", 0.0)),
        )

    def to_dict(self) -> dict:
        return {
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "chord": self.chord,
            "confidence": round(float(self.confidence), 3),
        }


def normalize_chords(segments: Iterable[dict | ChordSegment]) -> list[ChordSegment]:
    """Return valid chord segments sorted by start time."""
    normalized = []
    for segment in segments:
        item = segment if isinstance(segment, ChordSegment) else ChordSegment.from_dict(segment)
        if item.end <= item.start or not item.chord.strip():
            continue
        normalized.append(item)
    return sorted(normalized, key=lambda item: item.start)


def get_current_chord(
    current_time: float,
    segments: Iterable[dict | ChordSegment],
) -> tuple[Optional[ChordSegment], Optional[ChordSegment]]:
    """Return the current and next chord segment for a playback time."""
    chords = normalize_chords(segments)
    current = None
    next_segment = None

    for index, segment in enumerate(chords):
        if segment.start <= current_time < segment.end:
            current = segment
            next_segment = chords[index + 1] if index + 1 < len(chords) else None
            break
        if segment.start > current_time:
            next_segment = segment
            break

    return current, next_segment
