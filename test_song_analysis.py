#!/usr/bin/env python3
"""Tests for automatic lyrics/chord analysis helpers."""
import builtins
import tempfile
import unittest
from pathlib import Path

from src.ai.chord_analyzer import ChordAnalysisError, ChordAnalyzer
from src.ai.lyrics_transcriber import LyricsTranscriber, TranscriptionDependencyError
from src.cache.chord_cache import ChordCache
from src.cache.lyrics_cache import LyricsCache
from src.models.chords import ChordSegment, get_current_chord
from src.models.lyrics import LyricSegment, LyricWord, get_current_lyric, get_current_word
from src.services.song_analysis_service import SongAnalysisService


class SongAnalysisTests(unittest.TestCase):
    def test_save_and_load_lyrics_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = LyricsCache(Path(temp_dir))
            cache.save([
                LyricSegment(
                    1.0,
                    2.0,
                    "hola mundo",
                    "es",
                    words=(LyricWord(1.0, 1.4, "hola"), LyricWord(1.5, 2.0, "mundo")),
                )
            ])
            loaded = cache.load()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].text, "hola mundo")
        self.assertEqual(loaded[0].language, "es")
        self.assertEqual(loaded[0].words[1].word, "mundo")

    def test_save_and_load_chord_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ChordCache(Path(temp_dir))
            cache.save([ChordSegment(0.0, 3.2, "Am", 0.74)])
            loaded = cache.load()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].chord, "Am")
        self.assertAlmostEqual(loaded[0].confidence, 0.74)

    def test_get_current_lyric(self):
        segments = [
            LyricSegment(1.0, 2.0, "uno", "es"),
            LyricSegment(2.0, 3.0, "dos", "es"),
        ]
        current, next_segment = get_current_lyric(1.5, segments)

        self.assertEqual(current.text, "uno")
        self.assertEqual(next_segment.text, "dos")

    def test_get_current_word(self):
        segment = LyricSegment(
            0.0,
            2.0,
            "hola mundo",
            "es",
            words=(LyricWord(0.0, 1.0, "hola"), LyricWord(1.0, 2.0, "mundo")),
        )

        self.assertEqual(get_current_word(1.2, segment).word, "mundo")

    def test_get_current_chord(self):
        segments = [
            ChordSegment(0.0, 3.0, "C", 0.8),
            ChordSegment(3.0, 6.0, "G", 0.7),
        ]
        current, next_segment = get_current_chord(4.0, segments)

        self.assertEqual(current.chord, "G")
        self.assertIsNone(next_segment)

    def test_vocal_source_falls_back_to_original_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache"
            cache_path.mkdir()
            original = Path(temp_dir) / "song.wav"
            original.write_bytes(b"audio")

            source = SongAnalysisService.resolve_vocal_source(cache_path, original)

        self.assertEqual(source, original)

    def test_missing_transcription_model_error_is_clear(self):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "faster_whisper":
                raise ImportError("missing")
            return original_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "voice.wav"
            audio.write_bytes(b"audio")
            builtins.__import__ = fake_import
            try:
                with self.assertRaises(TranscriptionDependencyError):
                    LyricsTranscriber().transcribe(audio)
            finally:
                builtins.__import__ = original_import

    def test_chord_detection_without_source_raises_clear_error(self):
        with self.assertRaises(ChordAnalysisError):
            ChordAnalyzer().analyze_paths([])

    def test_chord_post_processing_merges_and_smooths_noise(self):
        analyzer = ChordAnalyzer()
        cleaned = analyzer._post_process_segments([
            ChordSegment(0.0, 4.0, "G", 0.9),
            ChordSegment(4.0, 4.5, "C", 0.4),
            ChordSegment(4.5, 8.0, "G", 0.8),
            ChordSegment(8.0, 10.0, "Em", 0.75),
            ChordSegment(10.0, 11.0, "Em", 0.7),
        ])

        self.assertEqual([segment.chord for segment in cleaned], ["G", "Em"])
        self.assertAlmostEqual(cleaned[0].start, 0.0)
        self.assertAlmostEqual(cleaned[0].end, 8.0)


if __name__ == "__main__":
    unittest.main()
