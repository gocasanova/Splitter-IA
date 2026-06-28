"""Coordinates automatic lyric and chord analysis for cached songs."""
from pathlib import Path

from src.ai.chord_analyzer import ChordAnalyzer
from src.ai.lyrics_transcriber import LyricsTranscriber
from src.cache.chord_cache import ChordCache
from src.cache.lyrics_cache import LyricsCache
from src.models.chords import ChordSegment
from src.models.lyrics import LyricSegment


class SongAnalysisService:
    """Resolve sources, run analyzers, and persist results in song cache."""

    def __init__(
        self,
        transcriber: LyricsTranscriber | None = None,
        chord_analyzer: ChordAnalyzer | None = None,
    ):
        self.transcriber = transcriber or LyricsTranscriber()
        self.chord_analyzer = chord_analyzer or ChordAnalyzer()

    def load_cached_lyrics(self, cache_path: Path) -> list[LyricSegment]:
        return LyricsCache(cache_path).load()

    def load_cached_chords(self, cache_path: Path) -> list[ChordSegment]:
        return ChordCache(cache_path).load()

    def transcribe_lyrics(
        self,
        cache_path: Path,
        original_file: Path | None,
        force: bool = False,
        language: str | None = None,
    ) -> list[LyricSegment]:
        cache = LyricsCache(cache_path)
        if cache.exists() and not force:
            return cache.load()

        source = self.resolve_vocal_source(cache_path, original_file)
        segments = self.transcriber.transcribe(source, language=language)
        cache.save(segments)
        return segments

    def analyze_chords(
        self,
        cache_path: Path,
        original_file: Path | None,
        force: bool = False,
    ) -> list[ChordSegment]:
        cache = ChordCache(cache_path)
        if cache.exists() and not force:
            return cache.load()

        sources = self.resolve_chord_sources(cache_path, original_file)
        segments = self.chord_analyzer.analyze_paths(sources)
        cache.save(segments)
        return segments

    @staticmethod
    def resolve_vocal_source(cache_path: Path, original_file: Path | None) -> Path:
        """Prefer Demucs vocals stem, then fall back to the original file."""
        vocals_path = cache_path / "stems" / "vocals.wav"
        if vocals_path.exists():
            return vocals_path
        if original_file and original_file.exists():
            return original_file
        raise FileNotFoundError("No vocal stem or original audio file is available.")

    @staticmethod
    def resolve_chord_sources(cache_path: Path, original_file: Path | None) -> list[Path]:
        """Prefer instrumental stems and avoid vocals when possible."""
        stems_dir = cache_path / "stems"
        if stems_dir.exists():
            instrumental = [
                stems_dir / stem_name
                for stem_name in ("other.wav", "bass.wav", "drums.wav")
                if (stems_dir / stem_name).exists()
            ]
            if instrumental:
                return instrumental
        if original_file and original_file.exists():
            return [original_file]
        raise FileNotFoundError("No instrumental stems or original audio file are available.")
