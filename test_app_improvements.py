#!/usr/bin/env python3
"""Regression tests for export, library metadata, and clickable timelines."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "AI_STEMS_CACHE_DIR",
    str(Path(tempfile.gettempdir()) / f"splitter-ai-tests-{os.getpid()}"),
)

import numpy as np

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QSlider

from src.audio.metadata import clean_display_name, infer_artist_title, read_audio_metadata
from src.cache.cache_manager import CacheManager, EXPECTED_STEMS
from src.ui.main_window import MainWindow
from src.ui.lyrics_sync_panel import LyricsSyncPanel
from src.ui.widgets import SeekSlider


class MetadataAndExportTests(unittest.TestCase):
    def _cache_song(self, root: Path, filename: str = "Buitres - Azul.mp3") -> Path:
        cache_path = root / "song-cache"
        stems_dir = cache_path / "stems"
        stems_dir.mkdir(parents=True)
        for stem in EXPECTED_STEMS:
            (stems_dir / f"{stem}.wav").write_bytes(stem.encode())
        (cache_path / "metadata.json").write_text(json.dumps({
            "title": Path(filename).stem,
            "artist": "",
            "input_file": filename,
            "input_path": "",
            "duration_seconds": 220,
            "tempo": "",
            "stems": sorted(EXPECTED_STEMS),
        }))
        return cache_path

    def test_filename_cleanup_and_artist_title_inference(self):
        artist, title = infer_artist_title(
            "01 Bruno Mars, Anderson .Paak, Silk Sonic - Fly As Me (SPOTISAVER).mp3"
        )
        self.assertEqual(artist, "Bruno Mars, Anderson .Paak, Silk Sonic")
        self.assertEqual(title, "Fly As Me")
        self.assertEqual(clean_display_name("Rock With You [5X-Mrc2l1d0]"), "Rock With You")

    @patch("mutagen.File")
    def test_embedded_title_does_not_repeat_embedded_artist(self, mutagen_file):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "download.mp3"
            audio_path.write_bytes(b"not-real-audio")
            fake_audio = type("Audio", (), {})()
            fake_audio.tags = {
                "artist": ["Michael Jackson"],
                "title": ["Michael Jackson - Rock With You"],
                "bpm": ["114"],
            }
            fake_audio.info = type("Info", (), {"length": 201.4})()
            mutagen_file.return_value = fake_audio

            metadata = read_audio_metadata(audio_path)

        self.assertEqual(metadata["artist"], "Michael Jackson")
        self.assertEqual(metadata["title"], "Rock With You")
        self.assertEqual(metadata["tempo"], 114.0)

    def test_export_uses_clear_names_in_selected_destination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_path = self._cache_song(root)
            destination = root / "exports"
            destination.mkdir()
            manager = CacheManager(root)

            exported = manager.export_stems(cache_path, destination, "Azul")

            self.assertEqual(
                {path.name for path in exported},
                {f"Azul_{stem}.wav" for stem in EXPECTED_STEMS},
            )
            self.assertTrue(all(path.parent == destination for path in exported))

    def test_export_rejects_incomplete_cache_before_copying(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_path = self._cache_song(root)
            (cache_path / "stems" / "vocals.wav").unlink()
            destination = root / "exports"
            destination.mkdir()

            with self.assertRaises(FileNotFoundError):
                CacheManager(root).export_stems(cache_path, destination, "Azul")
            self.assertEqual(list(destination.iterdir()), [])

    def test_library_refresh_does_not_calculate_tempo_inline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._cache_song(root)
            manager = CacheManager(root)

            with patch("src.cache.cache_manager.analyze_tempo") as analyze:
                songs = manager.list_cached_songs()

            analyze.assert_not_called()
            self.assertEqual(songs[0]["artist"], "Buitres")
            self.assertEqual(songs[0]["title"], "Azul")
            self.assertTrue(songs[0]["metadata_pending"])

    def test_background_result_is_cached(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_path = self._cache_song(root)
            manager = CacheManager(root)

            with patch("src.cache.cache_manager.analyze_tempo", return_value=126.4):
                updated = manager.refresh_cached_metadata(cache_path)

            self.assertEqual(updated["tempo"], 126.4)
            self.assertFalse(manager.list_cached_songs()[0]["metadata_pending"])


class SeekSliderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_clicking_halfway_seeks_halfway(self):
        slider = SeekSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 220)
        slider.setEnabled(True)
        slider.resize(400, 30)
        slider.show()
        emitted = []
        slider.seek_requested.connect(emitted.append)

        QTest.mouseClick(
            slider,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(200, 15),
        )

        self.assertTrue(emitted)
        self.assertAlmostEqual(emitted[-1], 110, delta=4)

    def test_lyrics_panel_has_no_legacy_progress_slider(self):
        panel = LyricsSyncPanel()

        self.assertEqual(panel.findChildren(QSlider), [])

    def test_lyrics_panel_has_no_duplicate_chord_label(self):
        panel = LyricsSyncPanel()

        self.assertFalse(hasattr(panel, "chord_over_lyric_label"))
        self.assertIsNotNone(panel.current_chord_label)
        self.assertIsNotNone(panel.next_chord_label)

    def test_mixer_and_lyrics_controls_share_position_and_volume(self):
        window = MainWindow()
        stems = {
            stem: np.zeros((2, 44100), dtype=np.float32)
            for stem in EXPECTED_STEMS
        }
        window._update_mixer(stems)

        window._on_seek(22050)
        window._on_master_volume_changed(0.35)

        self.assertEqual(window.player.state.current_frame, 22050)
        self.assertEqual(window.mixer_playback_controls.seek_slider.value(), 22050)
        self.assertEqual(window.lyrics_playback_controls.seek_slider.value(), 22050)
        self.assertEqual(window.mixer_playback_controls.master_volume.value(), 35)
        self.assertEqual(window.lyrics_playback_controls.master_volume.value(), 35)
        self.assertAlmostEqual(window.player.state.volume, 0.35)
        window.update_timer.stop()
        window.close()


if __name__ == "__main__":
    unittest.main()
