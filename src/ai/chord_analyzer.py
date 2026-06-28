"""Approximate chord detection using librosa chroma features."""
from pathlib import Path

import numpy as np

from src.models.chords import ChordSegment
from src.utils.config import SAMPLE_RATE
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class ChordAnalysisError(RuntimeError):
    """Raised when chord analysis cannot be completed."""


class ChordAnalyzer:
    """Simple replaceable chord analyzer based on chroma templates."""

    NOTES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")

    def __init__(self, sample_rate: int = SAMPLE_RATE, hop_length: int = 2048):
        self.sample_rate = sample_rate
        self.hop_length = hop_length
        self.templates = self._build_templates()

    def analyze_paths(self, audio_paths: list[Path]) -> list[ChordSegment]:
        """Analyze one or more audio files and return approximate chord segments."""
        try:
            import librosa
        except ImportError as exc:
            raise ChordAnalysisError("librosa is not installed.") from exc

        paths = [path for path in audio_paths if path and path.exists()]
        if not paths:
            raise ChordAnalysisError("No audio source available for chord analysis.")

        logger.info("Analyzing chords from %s source file(s)", len(paths))
        tracks = []
        for path in paths:
            audio, _ = librosa.load(str(path), sr=self.sample_rate, mono=True)
            if audio.size:
                tracks.append(audio.astype(np.float32, copy=False))

        if not tracks:
            raise ChordAnalysisError("Audio source is empty.")

        min_length = min(track.size for track in tracks)
        mix = np.mean([track[:min_length] for track in tracks], axis=0)
        if not np.any(np.abs(mix) > 1e-5):
            raise ChordAnalysisError("Audio source is silent.")

        chroma = librosa.feature.chroma_cqt(
            y=mix,
            sr=self.sample_rate,
            hop_length=self.hop_length,
        )
        frame_times = librosa.frames_to_time(
            np.arange(chroma.shape[1]),
            sr=self.sample_rate,
            hop_length=self.hop_length,
        )
        boundaries = self._segment_boundaries(mix, frame_times)
        raw_segments = self._label_segments(chroma, frame_times, boundaries, len(mix) / self.sample_rate)
        return self._post_process_segments(raw_segments)

    def _segment_boundaries(self, audio: np.ndarray, frame_times: np.ndarray) -> list[float]:
        """Use beat boundaries when possible, otherwise fixed two-second windows."""
        import librosa

        try:
            _, beats = librosa.beat.beat_track(
                y=audio,
                sr=self.sample_rate,
                hop_length=self.hop_length,
            )
            beat_times = librosa.frames_to_time(beats, sr=self.sample_rate, hop_length=self.hop_length)
            if beat_times.size >= 2:
                return [0.0, *beat_times.tolist()]
        except Exception as exc:
            logger.warning("Beat tracking failed, using fixed chord windows: %s", exc)

        duration = frame_times[-1] if frame_times.size else 0.0
        if duration <= 0:
            return [0.0]
        return np.arange(0.0, duration + 2.0, 2.0).tolist()

    def _label_segments(
        self,
        chroma: np.ndarray,
        frame_times: np.ndarray,
        boundaries: list[float],
        duration: float,
    ) -> list[ChordSegment]:
        segments = []
        if not boundaries or boundaries[0] > 0:
            boundaries = [0.0, *boundaries]
        if boundaries[-1] < duration:
            boundaries.append(duration)

        previous: ChordSegment | None = None
        for start, end in zip(boundaries, boundaries[1:]):
            if end <= start:
                continue
            frame_mask = (frame_times >= start) & (frame_times < end)
            if not np.any(frame_mask):
                continue
            vector = np.mean(chroma[:, frame_mask], axis=1)
            chord, confidence = self._match_chord(vector)
            if previous and previous.chord == chord and abs(previous.confidence - confidence) < 0.12:
                previous = ChordSegment(previous.start, end, previous.chord, max(previous.confidence, confidence))
                segments[-1] = previous
            else:
                previous = ChordSegment(start, end, chord, confidence)
                segments.append(previous)
        return segments

    def _post_process_segments(
        self,
        segments: list[ChordSegment],
        min_duration: float = 1.2,
        low_confidence: float = 0.55,
    ) -> list[ChordSegment]:
        """Reduce noisy short chord changes for a more playable guitar view."""
        merged = self._merge_same_chords(segments)
        if not merged:
            return []

        smoothed: list[ChordSegment] = []
        index = 0
        while index < len(merged):
            segment = merged[index]
            duration = segment.end - segment.start
            previous = smoothed[-1] if smoothed else None
            next_segment = merged[index + 1] if index + 1 < len(merged) else None

            if duration < min_duration and (segment.confidence < low_confidence or previous or next_segment):
                if previous and next_segment and previous.chord == next_segment.chord:
                    smoothed[-1] = ChordSegment(
                        previous.start,
                        next_segment.end,
                        previous.chord,
                        max(previous.confidence, next_segment.confidence),
                    )
                    index += 2
                    continue
                if previous and (not next_segment or previous.confidence >= next_segment.confidence):
                    smoothed[-1] = ChordSegment(
                        previous.start,
                        segment.end,
                        previous.chord,
                        previous.confidence,
                    )
                    index += 1
                    continue
                if next_segment:
                    smoothed.append(
                        ChordSegment(segment.start, next_segment.end, next_segment.chord, next_segment.confidence)
                    )
                    index += 2
                    continue

            if segment.confidence < low_confidence and previous:
                smoothed[-1] = ChordSegment(previous.start, segment.end, previous.chord, previous.confidence)
            else:
                smoothed.append(segment)
            index += 1

        return self._merge_same_chords(smoothed)

    @staticmethod
    def _merge_same_chords(segments: list[ChordSegment]) -> list[ChordSegment]:
        """Merge consecutive segments with the same chord label."""
        merged: list[ChordSegment] = []
        for segment in segments:
            if not merged or merged[-1].chord != segment.chord:
                merged.append(segment)
                continue
            previous = merged[-1]
            merged[-1] = ChordSegment(
                previous.start,
                segment.end,
                previous.chord,
                max(previous.confidence, segment.confidence),
            )
        return merged

    def _match_chord(self, chroma_vector: np.ndarray) -> tuple[str, float]:
        norm = float(np.linalg.norm(chroma_vector))
        if norm <= 1e-9:
            return "N.C.", 0.0

        best_name = "N.C."
        best_score = -1.0
        for name, template in self.templates.items():
            score = float(np.dot(chroma_vector, template) / (norm * np.linalg.norm(template)))
            if score > best_score:
                best_name = name
                best_score = score
        return best_name, max(0.0, min(best_score, 1.0))

    def _build_templates(self) -> dict[str, np.ndarray]:
        templates = {}
        major = (0, 4, 7)
        minor = (0, 3, 7)
        for root_index, root in enumerate(self.NOTES):
            major_template = np.zeros(12, dtype=np.float32)
            minor_template = np.zeros(12, dtype=np.float32)
            for interval in major:
                major_template[(root_index + interval) % 12] = 1.0
            for interval in minor:
                minor_template[(root_index + interval) % 12] = 1.0
            templates[root] = major_template
            templates[f"{root}m"] = minor_template
        return templates
