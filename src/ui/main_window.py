# Main PyQt6 application window
import sys
from pathlib import Path
from typing import Optional
import numpy as np
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QProgressBar, QScrollArea, QSlider, QFrame, QMessageBox,
    QListWidget, QListWidgetItem, QLineEdit, QPlainTextEdit, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QInputDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon, QDropEvent

from src.ui.widgets import PlaybackControls, StemControlWidget
from src.ui.lyrics_sync_panel import LyricsSyncPanel
from src.ui.chord_sync_panel import ChordSyncPanel
from src.ui.styles import apply_dark_theme
from src.audio.loader import AudioLoader
from src.audio.player import AudioPlayer
from src.audio.mixer import Mixer
from src.ai.demucs_handler import DemucsHandler
from src.ai.lyrics_analyzer import LyricsAnalyzer
from src.ai.lyrics_transcriber import TranscriptionDependencyError
from src.ai.chord_analyzer import ChordAnalysisError
from src.cache.cache_manager import CacheManager
from src.services.song_analysis_service import SongAnalysisService
from src.utils.logger import setup_logger
from src.utils.config import APP_NAME, APP_VERSION, SUPPORTED_FORMATS, SAMPLE_RATE

logger = setup_logger(__name__)

class SeparationWorker(QThread):
    """Worker thread for audio stem separation."""

    progress = pyqtSignal(int)  # 0-100
    finished = pyqtSignal(object, dict)  # input_file, stems dict
    error = pyqtSignal(str)

    def __init__(self, input_file: Path, audio: np.ndarray, sr: int):
        super().__init__()
        self.input_file = input_file
        self.audio = audio
        self.sr = sr
        self.handler = None

    def run(self):
        try:
            self.handler = DemucsHandler()
            self.progress.emit(5)
            self.handler.load_model()
            self.progress.emit(25)
            stems = self.handler.separate(self.audio, self.sr, self.progress.emit)
            self.progress.emit(100)
            self.finished.emit(self.input_file, stems)
        except Exception as e:
            logger.error(f"Separation error: {e}")
            self.error.emit(str(e))


class LyricsAnalysisWorker(QThread):
    """Worker thread for optional AI lyrics analysis."""

    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, title: str, lyrics: str, chords: str):
        super().__init__()
        self.title = title
        self.lyrics = lyrics
        self.chords = chords

    def run(self):
        try:
            analyzer = LyricsAnalyzer()
            self.finished.emit(analyzer.analyze(self.title, self.lyrics, self.chords))
        except Exception as e:
            logger.error(f"Lyrics analysis error: {e}")
            self.error.emit(str(e))


class PracticeTransformWorker(QThread):
    """Worker thread for offline tempo and pitch practice transforms."""

    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, stems: dict, tempo_percent: int, pitch_semitones: int, sr: int):
        super().__init__()
        self.stems = stems
        self.tempo_percent = tempo_percent
        self.pitch_semitones = pitch_semitones
        self.sr = sr

    def run(self):
        try:
            import librosa

            rate = max(self.tempo_percent / 100.0, 0.05)
            transformed = {}
            total = max(len(self.stems), 1)

            for index, (stem_name, audio) in enumerate(self.stems.items(), start=1):
                processed_channels = []
                for channel in audio:
                    channel_audio = channel.astype(np.float32, copy=False)
                    if self.pitch_semitones:
                        channel_audio = librosa.effects.pitch_shift(
                            y=channel_audio,
                            sr=self.sr,
                            n_steps=self.pitch_semitones,
                        )
                    if self.tempo_percent != 100:
                        channel_audio = librosa.effects.time_stretch(channel_audio, rate=rate)
                    processed_channels.append(channel_audio.astype(np.float32, copy=False))

                min_length = min(len(channel) for channel in processed_channels)
                transformed[stem_name] = np.vstack([
                    channel[:min_length] for channel in processed_channels
                ])
                self.progress.emit(int(index / total * 100))

            self.finished.emit(transformed)
        except Exception as e:
            logger.error(f"Practice transform error: {e}")
            self.error.emit(str(e))


class AutoLyricsWorker(QThread):
    """Worker thread for automatic lyric transcription."""

    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(
        self,
        cache_path: Path,
        original_file: Optional[Path],
        force: bool = False,
        language: Optional[str] = None,
    ):
        super().__init__()
        self.cache_path = cache_path
        self.original_file = original_file
        self.force = force
        self.language = language

    def run(self):
        try:
            service = SongAnalysisService()
            self.finished.emit(
                service.transcribe_lyrics(
                    self.cache_path,
                    self.original_file,
                    self.force,
                    language=self.language,
                )
            )
        except TranscriptionDependencyError as e:
            self.error.emit(str(e))
        except Exception as e:
            logger.error(f"Auto lyrics error: {e}")
            self.error.emit(f"Could not transcribe lyrics: {e}")


class AutoChordsWorker(QThread):
    """Worker thread for automatic chord detection."""

    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, cache_path: Path, original_file: Optional[Path], force: bool = False):
        super().__init__()
        self.cache_path = cache_path
        self.original_file = original_file
        self.force = force

    def run(self):
        try:
            service = SongAnalysisService()
            self.finished.emit(service.analyze_chords(self.cache_path, self.original_file, self.force))
        except ChordAnalysisError as e:
            self.error.emit(str(e))
        except Exception as e:
            logger.error(f"Auto chords error: {e}")
            self.error.emit(f"Could not detect chords: {e}")


class LibraryMetadataWorker(QThread):
    """Fill missing embedded metadata and BPM without blocking the UI."""

    song_updated = pyqtSignal(dict)

    def __init__(self, cache_manager: CacheManager, cache_paths: list[Path], parent=None):
        super().__init__(parent)
        self.cache_manager = cache_manager
        self.cache_paths = cache_paths

    def run(self):
        for cache_path in self.cache_paths:
            if self.isInterruptionRequested():
                return
            try:
                self.song_updated.emit(self.cache_manager.refresh_cached_metadata(cache_path))
            except Exception as exc:
                logger.warning("Could not refresh library metadata for %s: %s", cache_path, exc)

class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"AI Band Mixer v{APP_VERSION}")
        self.setGeometry(100, 100, 1380, 820)

        # Components
        self.audio_loader = AudioLoader()
        self.player = AudioPlayer(callback_fn=self._on_playback_update)
        self.mixer = Mixer()
        self.cache_manager = CacheManager()

        # State
        self.current_file: Optional[Path] = None
        self.current_cache_path: Optional[Path] = None
        self.current_stems = {}
        self.original_stems = {}
        self.stem_widgets = {}
        self.cached_songs = []
        self.markers = []
        self.separation_worker: Optional[SeparationWorker] = None
        self.lyrics_worker: Optional[LyricsAnalysisWorker] = None
        self.transform_worker: Optional[PracticeTransformWorker] = None
        self.auto_lyrics_worker: Optional[AutoLyricsWorker] = None
        self.auto_chords_worker: Optional[AutoChordsWorker] = None
        self.metadata_worker: Optional[LibraryMetadataWorker] = None

        self._init_ui()
        apply_dark_theme(self)
        self.setAcceptDrops(True)

    def _init_ui(self):
        """Initialize UI components."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Title
        title = QLabel("AI Band Mixer")
        title.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        main_layout.addWidget(title)

        self.main_tabs = QTabWidget()
        self.library_tab = QWidget()
        self.mixer_tab = QWidget()
        self.lyrics_chords_tab = QWidget()
        self.main_tabs.addTab(self.library_tab, "Biblioteca")
        self.main_tabs.addTab(self.mixer_tab, "Mixer")
        self.main_tabs.addTab(self.lyrics_chords_tab, "Letra y acordes")
        main_layout.addWidget(self.main_tabs, 1)

        library_tab_layout = QVBoxLayout(self.library_tab)
        library_tab_layout.setSpacing(10)
        library_tab_layout.setContentsMargins(0, 0, 0, 0)

        library_top = QFrame()
        library_top.setObjectName("Panel")
        library_top_layout = QVBoxLayout(library_top)
        library_top_layout.setContentsMargins(0, 0, 0, 0)

        file_layout = QHBoxLayout()
        self.file_label = QLabel("Sin canción cargada")
        self.file_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        file_layout.addWidget(self.file_label, 1)

        file_btn = QPushButton("Abrir canción")
        file_btn.clicked.connect(self._on_open_file)
        file_layout.addWidget(file_btn)
        library_top_layout.addLayout(file_layout)

        self.metadata_label = QLabel()
        self.metadata_label.setFont(QFont("Arial", 9))
        self.metadata_label.setStyleSheet("color: #888;")
        library_top_layout.addWidget(self.metadata_label)

        sep_layout = QHBoxLayout()
        self.separate_btn = QPushButton("Separar pistas")
        self.separate_btn.clicked.connect(self._on_separate)
        self.separate_btn.setEnabled(False)
        self.separate_btn.setMinimumHeight(40)
        sep_layout.addWidget(self.separate_btn, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        sep_layout.addWidget(self.progress_bar)
        library_top_layout.addLayout(sep_layout)
        library_tab_layout.addWidget(library_top)

        library_frame = QFrame()
        library_frame.setObjectName("Panel")
        library_layout = QVBoxLayout(library_frame)
        library_layout.setContentsMargins(0, 0, 0, 0)
        library_header = QHBoxLayout()
        library_label = QLabel("Biblioteca")
        library_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        library_header.addWidget(library_label)
        refresh_library_btn = QPushButton("Actualizar")
        refresh_library_btn.clicked.connect(self._refresh_library)
        library_header.addWidget(refresh_library_btn)
        library_layout.addLayout(library_header)

        self.library_search = QLineEdit()
        self.library_search.setPlaceholderText("Buscar en biblioteca")
        self.library_search.textChanged.connect(self._filter_library)
        library_layout.addWidget(self.library_search)

        self.library_list = QTableWidget(0, 4)
        self.library_list.setHorizontalHeaderLabels(["Canción", "Artista", "Duración", "Tempo"])
        self.library_list.verticalHeader().setVisible(False)
        self.library_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.library_list.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.library_list.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.library_list.cellDoubleClicked.connect(lambda row, _column: self._load_library_row(row))
        header = self.library_list.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        library_layout.addWidget(self.library_list, 1)

        load_library_btn = QPushButton("Cargar seleccionada")
        load_library_btn.clicked.connect(self._load_selected_library_item)
        library_layout.addWidget(load_library_btn)

        library_actions = QHBoxLayout()
        rename_library_btn = QPushButton("Renombrar")
        rename_library_btn.clicked.connect(self._rename_selected_library_item)
        library_actions.addWidget(rename_library_btn)
        export_library_btn = QPushButton("Exportar pistas")
        export_library_btn.clicked.connect(self._export_selected_library_item)
        library_actions.addWidget(export_library_btn)
        delete_library_btn = QPushButton("Eliminar")
        delete_library_btn.clicked.connect(self._delete_selected_library_item)
        library_actions.addWidget(delete_library_btn)
        library_layout.addLayout(library_actions)

        self.cache_size_label = QLabel()
        self.cache_size_label.setStyleSheet("color: #9ca3af;")
        library_layout.addWidget(self.cache_size_label)
        library_tab_layout.addWidget(library_frame, 1)

        mixer_tab_layout = QVBoxLayout(self.mixer_tab)
        mixer_tab_layout.setSpacing(10)
        mixer_tab_layout.setContentsMargins(0, 0, 0, 0)

        practice_header = QFrame()
        practice_header.setObjectName("Panel")
        practice_header_layout = QHBoxLayout(practice_header)
        practice_header_layout.setContentsMargins(0, 0, 0, 0)
        self.practice_file_label = QLabel("Cargá una canción desde Biblioteca")
        self.practice_file_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        practice_header_layout.addWidget(self.practice_file_label, 1)
        mixer_tab_layout.addWidget(practice_header)

        mixer_frame = QFrame()
        mixer_frame.setObjectName("Panel")
        mixer_frame.setMinimumWidth(560)
        mixer_layout = QVBoxLayout(mixer_frame)
        mixer_layout.setContentsMargins(0, 0, 0, 0)
        mixer_layout.setSpacing(12)

        mixer_label = QLabel("Pistas")
        mixer_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        mixer_layout.addWidget(mixer_label)

        # Stem controls (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        self.stems_layout = QVBoxLayout(scroll_widget)
        self.stems_layout.setSpacing(10)
        self.stems_layout.addStretch()
        scroll.setWidget(scroll_widget)
        mixer_layout.addWidget(scroll, 1)
        mixer_tab_layout.addWidget(mixer_frame, 1)

        lyrics_chords_layout = QVBoxLayout(self.lyrics_chords_tab)
        lyrics_chords_layout.setSpacing(10)
        lyrics_chords_layout.setContentsMargins(0, 0, 0, 0)

        notes_frame = QFrame()
        notes_frame.setObjectName("Panel")
        notes_layout = QVBoxLayout(notes_frame)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(12)
        notes_header = QHBoxLayout()
        notes_label = QLabel("Letra y acordes")
        notes_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        notes_header.addWidget(notes_label)

        self.notes_status_label = QLabel("Cargá una canción para ver la letra y los acordes")
        self.notes_status_label.setStyleSheet("color: #9ca3af;")
        notes_header.addWidget(self.notes_status_label, 1)

        save_notes_btn = QPushButton("Guardar notas")
        save_notes_btn.clicked.connect(self._save_song_notes)
        notes_header.addWidget(save_notes_btn)
        save_notes_btn.setVisible(False)

        analyze_btn = QPushButton("Analizar")
        analyze_btn.clicked.connect(self._analyze_lyrics)
        notes_header.addWidget(analyze_btn)
        analyze_btn.setVisible(False)
        notes_layout.addLayout(notes_header)

        self.notes_tabs = QTabWidget()
        self.notes_tabs.setVisible(False)
        self.lyrics_editor = QPlainTextEdit()
        self.lyrics_editor.setPlaceholderText("Pegá o escribí letra acá...")
        self.chords_editor = QPlainTextEdit()
        self.chords_editor.setPlaceholderText("Escribí acordes acá, ej. [Verso] Am  F  C  G")
        self.analysis_editor = QPlainTextEdit()
        self.analysis_editor.setPlaceholderText("El análisis de IA aparece acá si OPENAI_API_KEY está configurada.")
        self.notes_tabs.addTab(self.lyrics_editor, "Lyrics")
        self.notes_tabs.addTab(self.chords_editor, "Chords")
        self.notes_tabs.addTab(self.analysis_editor, "AI Analysis")
        self.lyrics_sync_panel = LyricsSyncPanel()
        self.lyrics_sync_panel.analyze_btn.clicked.connect(
            lambda: self._analyze_auto_lyrics(self.lyrics_sync_panel.has_lyrics())
        )
        self.lyrics_sync_panel.reanalyze_btn.clicked.connect(lambda: self._analyze_auto_lyrics(True))
        self.lyrics_sync_panel.language_changed.connect(self._on_lyrics_language_changed)
        self.chord_sync_panel = ChordSyncPanel()
        self.chord_sync_panel.analyze_btn.clicked.connect(lambda: self._analyze_auto_chords(False))
        self.chord_sync_panel.reanalyze_btn.clicked.connect(lambda: self._analyze_auto_chords(True))
        self.notes_tabs.addTab(self.chord_sync_panel, "Auto Chords")
        notes_layout.addWidget(self.lyrics_sync_panel, 1)
        notes_layout.addWidget(self.notes_tabs)
        lyrics_chords_layout.addWidget(notes_frame, 1)

        self.lyrics_playback_controls = PlaybackControls()
        lyrics_chords_layout.addWidget(self.lyrics_playback_controls)

        practice_frame = QFrame()
        practice_frame.setObjectName("Panel")
        practice_layout = QHBoxLayout(practice_frame)
        practice_layout.setContentsMargins(0, 0, 0, 0)
        practice_layout.setSpacing(14)

        fx_title = QLabel("Tempo / Pitch / FX")
        fx_title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        practice_layout.addWidget(fx_title)

        tempo_card = QFrame()
        tempo_card.setObjectName("TempoCard")
        tempo_card_layout = QVBoxLayout(tempo_card)
        tempo_card_layout.setContentsMargins(12, 10, 12, 10)
        self.tempo_label = QLabel("Tempo")
        self.tempo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tempo_label.setStyleSheet("color: #9ca3af; font-weight: bold;")
        tempo_card_layout.addWidget(self.tempo_label)
        self.tempo_value_label = QLabel("100%")
        self.tempo_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tempo_value_label.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        tempo_card_layout.addWidget(self.tempo_value_label)
        self.tempo_slider = QSlider(Qt.Orientation.Vertical)
        self.tempo_slider.setMinimum(50)
        self.tempo_slider.setMaximum(150)
        self.tempo_slider.setValue(100)
        self.tempo_slider.setMinimumHeight(120)
        self.tempo_slider.valueChanged.connect(self._on_tempo_slider_changed)
        tempo_card_layout.addWidget(self.tempo_slider, 1, Qt.AlignmentFlag.AlignHCenter)
        practice_layout.addWidget(tempo_card)

        pitch_card = QFrame()
        pitch_card.setObjectName("TempoCard")
        pitch_card_layout = QVBoxLayout(pitch_card)
        pitch_card_layout.setContentsMargins(12, 10, 12, 10)
        self.pitch_label = QLabel("Pitch")
        self.pitch_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pitch_label.setStyleSheet("color: #9ca3af; font-weight: bold;")
        pitch_card_layout.addWidget(self.pitch_label)
        self.pitch_value_label = QLabel("0 st")
        self.pitch_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pitch_value_label.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        pitch_card_layout.addWidget(self.pitch_value_label)
        self.pitch_slider = QSlider(Qt.Orientation.Vertical)
        self.pitch_slider.setMinimum(-12)
        self.pitch_slider.setMaximum(12)
        self.pitch_slider.setValue(0)
        self.pitch_slider.setMinimumHeight(120)
        self.pitch_slider.valueChanged.connect(self._on_pitch_slider_changed)
        pitch_card_layout.addWidget(self.pitch_slider, 1, Qt.AlignmentFlag.AlignHCenter)
        practice_layout.addWidget(pitch_card)

        fx_actions = QVBoxLayout()
        fx_actions.setSpacing(8)
        apply_fx_btn = QPushButton("Aplicar FX")
        apply_fx_btn.clicked.connect(self._apply_practice_fx)
        fx_actions.addWidget(apply_fx_btn)
        reset_fx_btn = QPushButton("Restablecer FX")
        reset_fx_btn.clicked.connect(self._reset_practice_fx)
        fx_actions.addWidget(reset_fx_btn)
        fx_actions.addStretch()
        practice_layout.addLayout(fx_actions)
        practice_layout.addStretch()

        self.marker_name_input = QLineEdit()
        self.marker_name_input.setVisible(False)
        self.marker_list = QListWidget()
        self.marker_list.setVisible(False)
        mixer_tab_layout.addWidget(practice_frame)

        self.mixer_playback_controls = PlaybackControls()
        mixer_tab_layout.addWidget(self.mixer_playback_controls)
        self.playback_controls = [self.mixer_playback_controls, self.lyrics_playback_controls]
        for controls in self.playback_controls:
            controls.play_requested.connect(self._on_play)
            controls.pause_requested.connect(self._on_pause)
            controls.stop_requested.connect(self._on_stop)
            controls.seek_requested.connect(self._on_seek)
            controls.volume_changed.connect(self._on_master_volume_changed)

        # Compatibility aliases for shortcuts and existing state checks.
        self.play_btn = self.mixer_playback_controls.play_btn
        self.pause_btn = self.mixer_playback_controls.pause_btn
        self.stop_btn = self.mixer_playback_controls.stop_btn
        self.seek_slider = self.mixer_playback_controls.seek_slider
        self.time_label = self.mixer_playback_controls.time_label
        self.duration_label = self.mixer_playback_controls.duration_label
        self.master_volume = self.mixer_playback_controls.master_volume

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_ui)
        self.update_timer.start(100)  # 100ms update rate
        self._refresh_library()

    def dragEnterEvent(self, event: QDropEvent):
        """Handle drag enter."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """Handle drop."""
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in SUPPORTED_FORMATS:
                self._load_file(path)
                break

    def keyPressEvent(self, event):
        """Handle global playback shortcuts."""
        if event.key() == Qt.Key.Key_Space and (self.play_btn.isEnabled() or self.player.is_playing()):
            if self.player.is_playing():
                self._on_pause()
            else:
                self._on_play()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Escape and self.stop_btn.isEnabled():
            self._on_stop()
            event.accept()
            return

        super().keyPressEvent(event)

    def _on_open_file(self):
        """Open file picker."""
        formats = " ".join(f"*{fmt}" for fmt in SUPPORTED_FORMATS)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir canción",
            str(Path.home() / "Music"),
            f"Archivos de audio ({formats});;Todos los archivos (*)"
        )

        if file_path:
            self._load_file(Path(file_path))

    def _load_file(self, file_path: Path):
        """Load an audio file."""
        try:
            if not self._stop_for_song_change():
                return
            logger.info(f"Loading file: {file_path}")
            self.current_file = file_path
            self.current_cache_path = None
            self.notes_status_label.setText("Cargando canción...")
            self.lyrics_sync_panel.set_status("Cargando canción...")

            # Load audio metadata
            metadata = self.audio_loader.get_metadata(file_path)
            duration_sec = metadata.get("duration", 0)
            duration_min = int(duration_sec) // 60
            duration_sec = int(duration_sec) % 60

            self.file_label.setText(f"Canción: {file_path.name}")
            self.practice_file_label.setText(f"Cargada: {file_path.name}")
            self.metadata_label.setText(
                f"Duration: {duration_min}:{duration_sec:02d} | "
                f"Size: {metadata.get('size_mb', 0):.1f} MB"
            )

            self.separate_btn.setEnabled(True)
            self.current_stems = {}
            self.original_stems = {}
            self.stem_widgets = {}
            self.player.clear_loop()
            self._reset_practice_sliders()

            # Check cache
            if self.cache_manager.cache_exists(file_path):
                logger.info("Stems found in cache, loading...")
                self.current_cache_path = self.cache_manager.get_cache_path(file_path)
                self._load_cached_stems()
            else:
                logger.info("No cached stems found")
                self._load_song_notes(None)
                QTimer.singleShot(0, self._on_separate)

        except Exception as e:
            logger.error(f"Error loading file: {e}")
            QMessageBox.critical(self, "Error", f"No se pudo cargar la canción: {e}")

    def _load_cached_stems(self):
        """Load stems from cache."""
        try:
            stems = self.cache_manager.load_stems(self.current_file)
            self._update_mixer(stems)
            self._load_song_notes(self.current_cache_path)
            if self.current_file:
                self.practice_file_label.setText(f"Mixer: {self.current_file.stem}")
            self.main_tabs.setCurrentWidget(self.mixer_tab)
            logger.info("Cached stems loaded successfully")
        except Exception as e:
            logger.error(f"Error loading cached stems: {e}")
            QMessageBox.warning(self, "Error de cache", f"No se pudieron cargar las pistas cacheadas: {e}")

    def _refresh_library(self):
        """Refresh processed songs library from cache."""
        self.cached_songs = self.cache_manager.list_cached_songs()
        self._filter_library(self.library_search.text())
        self.cache_size_label.setText(f"Tamaño de cache: {self.cache_manager.get_cache_size()} MB")
        self._start_library_metadata_refresh()

    def _start_library_metadata_refresh(self):
        """Analyze only uncached library metadata in the background."""
        if self.metadata_worker and self.metadata_worker.isRunning():
            return
        pending = [
            Path(song["cache_path"])
            for song in self.cached_songs
            if song.get("metadata_pending")
        ]
        if not pending:
            return
        self.metadata_worker = LibraryMetadataWorker(self.cache_manager, pending, self)
        self.metadata_worker.song_updated.connect(self._on_library_metadata_updated)
        self.metadata_worker.finished.connect(self._on_library_metadata_finished)
        self.metadata_worker.start()

    def _on_library_metadata_updated(self, updated: dict):
        """Update a resolved library row without disturbing the current selection."""
        cache_path = updated.get("cache_path")
        for index, song in enumerate(self.cached_songs):
            if song.get("cache_path") == cache_path:
                self.cached_songs[index] = updated
                break

        for row in range(self.library_list.rowCount()):
            first_item = self.library_list.item(row, 0)
            song = first_item.data(Qt.ItemDataRole.UserRole) if first_item else None
            if not song or song.get("cache_path") != cache_path:
                continue
            values = [
                updated.get("title") or "—",
                updated.get("artist") or "—",
                self._format_duration(updated.get("duration_seconds")),
                self._format_tempo(updated.get("tempo")),
            ]
            for column, value in enumerate(values):
                item = self.library_list.item(row, column)
                if item:
                    item.setText(value)
                    item.setData(Qt.ItemDataRole.UserRole, updated)
            break

    def _on_library_metadata_finished(self):
        self.metadata_worker = None

    def _filter_library(self, query: str = ""):
        """Filter processed songs by title or original file path."""
        self.library_list.setRowCount(0)
        normalized_query = query.strip().lower()
        for song in self.cached_songs:
            title = song.get("title") or Path(song.get("input_file", "Processed song")).stem
            searchable = " ".join([
                title,
                song.get("artist", ""),
                song.get("input_file", ""),
                song.get("input_path", ""),
            ]).lower()
            if normalized_query and normalized_query not in searchable:
                continue

            row = self.library_list.rowCount()
            self.library_list.insertRow(row)
            values = [
                title,
                song.get("artist") or "—",
                self._format_duration(song.get("duration_seconds")),
                self._format_tempo(song.get("tempo")),
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(song.get("input_path", song.get("cache_path", "")))
                cell.setData(Qt.ItemDataRole.UserRole, song)
                self.library_list.setItem(row, column, cell)

    def _load_selected_library_item(self):
        """Load the currently selected cached song."""
        row = self.library_list.currentRow()
        if row >= 0:
            self._load_library_row(row)

    def _selected_library_song(self) -> Optional[dict]:
        """Return metadata for the selected cached song."""
        row = self.library_list.currentRow()
        if row < 0:
            return None
        item = self.library_list.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _rename_selected_library_item(self):
        """Rename the selected cached song display title."""
        song = self._selected_library_song()
        if not song:
            return

        current_title = song.get("title") or Path(song.get("input_file", "Processed song")).stem
        title, ok = QInputDialog.getText(self, "Renombrar canción", "Título:", text=current_title)
        if not ok or not title.strip():
            return

        self.cache_manager.update_song_title(Path(song["cache_path"]), title.strip())
        self._refresh_library()

    def _export_selected_library_item(self):
        """Export selected or currently loaded cached stems to a chosen folder."""
        song = self._selected_library_song()
        cache_path = Path(song["cache_path"]) if song else self.current_cache_path
        if cache_path is None:
            QMessageBox.information(
                self,
                "Exportar pistas",
                "Seleccioná una canción de la Biblioteca o cargá una canción procesada.",
            )
            return
        if not self.cache_manager.has_complete_stems(cache_path):
            QMessageBox.warning(
                self,
                "Exportar pistas",
                "La canción no tiene todos los stems disponibles en cache.",
            )
            return

        destination = QFileDialog.getExistingDirectory(
            self,
            "Exportar pistas a carpeta",
            str(Path.home() / "Music"),
        )
        if not destination:
            return

        try:
            loaded_song = song or next(
                (
                    item for item in self.cached_songs
                    if item.get("cache_path") == str(cache_path)
                ),
                None,
            )
            title = (
                loaded_song.get("title", "")
                if loaded_song
                else (self.current_file.stem if self.current_file else "")
            )
            exported = self.cache_manager.export_stems(cache_path, Path(destination), title)
            QMessageBox.information(
                self,
                "Exportar pistas",
                f"Se exportaron {len(exported)} pistas en:\n{destination}",
            )
        except Exception as e:
            logger.error("Stem export failed: %s", e)
            QMessageBox.critical(self, "Error al exportar", f"No se pudieron exportar las pistas: {e}")

    def _delete_selected_library_item(self):
        """Delete the selected cached song."""
        song = self._selected_library_song()
        if not song:
            return

        title = song.get("title") or Path(song.get("input_file", "Processed song")).stem
        response = QMessageBox.question(
            self,
            "Eliminar canción",
            f"¿Eliminar pistas cacheadas de '{title}'?",
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        cache_path = Path(song["cache_path"])
        self.cache_manager.delete_cached_song(cache_path)
        if self.current_cache_path == cache_path:
            self.current_cache_path = None
            self.current_stems = {}
            self.original_stems = {}
            self.practice_file_label.setText("Cargá una canción desde Biblioteca")
            self.player.stop()
            self._set_playback_buttons(False, False, False)
            for controls in self.playback_controls:
                controls.seek_slider.setEnabled(False)
                controls.seek_slider.setValue(0)
                controls.time_label.setText("00:00")
                controls.duration_label.setText("00:00")
            self._load_song_notes(None)
        self._refresh_library()

    def _load_library_row(self, row: int):
        """Load a cached song from a table row."""
        item = self.library_list.item(row, 0)
        if item:
            self._load_library_item(item.data(Qt.ItemDataRole.UserRole), item.text())

    def _load_library_item(self, song: dict, display_title: str = ""):
        """Load a cached song from the processed library."""
        if not song:
            return

        try:
            if not self._stop_for_song_change():
                return
            cache_path = Path(song["cache_path"])
            stems = self.cache_manager.load_stems_from_cache(cache_path)
            self.current_cache_path = cache_path
            self.current_file = Path(song["input_path"]) if song.get("input_path") else None
            title = song.get("title", display_title)
            self.file_label.setText(f"Procesada: {title}")
            self.practice_file_label.setText(f"Mixer: {title}")
            self.metadata_label.setText("Canción cargada desde biblioteca")
            self.separate_btn.setEnabled(bool(self.current_file and self.current_file.exists()))
            self._update_mixer(stems)
            self._load_song_notes(cache_path)
            self.main_tabs.setCurrentWidget(self.mixer_tab)
            logger.info(f"Loaded processed song from library: {cache_path}")
        except Exception as e:
            logger.error(f"Error loading library item: {e}")
            QMessageBox.critical(self, "Error de biblioteca", f"No se pudo cargar la canción procesada: {e}")

    def _stop_for_song_change(self):
        """Stop playback before replacing the currently loaded song."""
        if self.current_stems or self.player.is_playing() or self.player.state.current_frame:
            if not self.player.stop():
                QMessageBox.warning(
                    self,
                    "Audio ocupado",
                    "El motor de audio todavía se está deteniendo. Esperá un momento y probá de nuevo.",
                )
                return False
        self._set_playback_buttons(False, False, False)
        for controls in self.playback_controls:
            controls.seek_slider.setEnabled(False)
            controls.seek_slider.setValue(0)
            controls.time_label.setText("00:00")
            controls.duration_label.setText("00:00")
        return True

    def _on_separate(self):
        """Start stem separation."""
        if not self.current_file:
            return

        try:
            logger.info("Starting separation...")
            self.separate_btn.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.notes_status_label.setText("Separando pistas...")
            self.lyrics_sync_panel.set_status("Separando pistas...")

            # Load audio
            audio, sr = self.audio_loader.load(self.current_file)

            # Start worker thread
            processing_file = self.current_file
            self.separation_worker = SeparationWorker(processing_file, audio, sr)
            self.separation_worker.progress.connect(self._on_separation_progress)
            self.separation_worker.finished.connect(self._on_separation_finished)
            self.separation_worker.error.connect(self._on_separation_error)
            self.separation_worker.start()

        except Exception as e:
            logger.error(f"Error starting separation: {e}")
            QMessageBox.critical(self, "Error", f"No se pudo iniciar la separación: {e}")
            self.separate_btn.setEnabled(True)
            self.progress_bar.setVisible(False)

    def _on_separation_progress(self, progress: int):
        """Update separation progress."""
        self.progress_bar.setValue(progress)

    def _on_separation_finished(self, input_file: Path, stems: dict):
        """Handle separation completion."""
        try:
            logger.info(f"Separation completed for {input_file}")

            # Cache stems
            cache_path = self.cache_manager.save_stems(input_file, stems, SAMPLE_RATE)
            self._refresh_library()

            # Update mixer only if the user is still looking at the processed file.
            if self.current_file == input_file:
                self.current_cache_path = cache_path
                self._update_mixer(stems)
                self._load_song_notes(cache_path)
                self.practice_file_label.setText(f"Mixer: {input_file.stem}")
                self.main_tabs.setCurrentWidget(self.mixer_tab)

            self.progress_bar.setVisible(False)
            self.separate_btn.setEnabled(True)
            self.separation_worker = None

            QMessageBox.information(self, "Listo", "Pistas separadas correctamente.")

        except Exception as e:
            logger.error(f"Error after separation: {e}")
            QMessageBox.critical(self, "Error", f"Error al guardar las pistas: {e}")

    def _on_separation_error(self, error: str):
        """Handle separation error."""
        logger.error(f"Separation error: {error}")
        self.progress_bar.setVisible(False)
        self.separate_btn.setEnabled(True)
        self.separation_worker = None
        QMessageBox.critical(self, "Error de separación", f"Error: {error}")

    def _load_song_notes(self, cache_path: Optional[Path]):
        """Load lyrics/chords/analysis into the notes panel."""
        if cache_path is None:
            notes = {"lyrics": "", "chords": "", "analysis": "", "markers": []}
            self.notes_status_label.setText("Cargá una canción para ver la letra y los acordes")
            self.lyrics_sync_panel.set_segments([])
            self.lyrics_sync_panel.set_chord_segments([])
            self.lyrics_sync_panel.set_status("Cargá una canción para ver la letra y los acordes")
            self.chord_sync_panel.set_segments([])
        else:
            notes = self.cache_manager.load_song_notes(cache_path)
            self.notes_status_label.setText("Preparando letra y acordes...")
            service = SongAnalysisService()
            lyric_segments = service.load_cached_lyrics(cache_path)
            self.lyrics_sync_panel.set_segments(lyric_segments)
            chord_segments = service.load_cached_chords(cache_path)
            self.chord_sync_panel.set_segments(chord_segments)
            self.lyrics_sync_panel.set_chord_segments(chord_segments)
            self._start_missing_auto_analysis(has_lyrics=bool(lyric_segments), has_chords=bool(chord_segments))

        self.lyrics_editor.setPlainText(notes["lyrics"])
        self.chords_editor.setPlainText(notes["chords"])
        self.analysis_editor.setPlainText(notes["analysis"])
        self.markers = self._normalize_markers(notes.get("markers", []))
        self._refresh_markers()

    def _start_missing_auto_analysis(self, has_lyrics: bool, has_chords: bool):
        """Load cached analysis and wait for user language choice before missing lyrics."""
        if not self.current_cache_path:
            return
        if has_lyrics:
            self.lyrics_sync_panel.set_status("Letra lista")
            self.notes_status_label.setText("Letra y acordes listos" if has_chords else "Analizando acordes...")
        else:
            self.lyrics_sync_panel.set_status("Elegí idioma y tocá Procesar letra")
            self.notes_status_label.setText("Elegí idioma y procesá la letra")

        if has_chords:
            self.chord_sync_panel.set_status("Acordes listos (aproximados)")
        else:
            self._analyze_auto_chords(False, show_errors=False)

    def _save_song_notes(self):
        """Persist the current notes for the loaded cached song."""
        if not self.current_cache_path:
            QMessageBox.information(self, "Notas", "Cargá o separá una canción antes de guardar notas.")
            return

        self.cache_manager.save_song_notes(
            self.current_cache_path,
            self.lyrics_editor.toPlainText(),
            self.chords_editor.toPlainText(),
            self.analysis_editor.toPlainText(),
            self.markers,
        )
        self.notes_status_label.setText("Notas guardadas")

    def _analyze_lyrics(self):
        """Run optional AI analysis for the current lyrics/chords."""
        lyrics = self.lyrics_editor.toPlainText().strip()
        chords = self.chords_editor.toPlainText().strip()
        if not lyrics and not chords:
            QMessageBox.information(self, "Analizar", "Agregá letra o acordes primero.")
            return

        title = self.file_label.text().replace("Procesada:", "").replace("Canción:", "").strip()
        self.notes_status_label.setText("Analizando...")
        self.lyrics_worker = LyricsAnalysisWorker(title, lyrics, chords)
        self.lyrics_worker.finished.connect(self._on_lyrics_analysis_finished)
        self.lyrics_worker.error.connect(self._on_lyrics_analysis_error)
        self.lyrics_worker.start()

    def _on_lyrics_analysis_finished(self, analysis: str):
        self.analysis_editor.setPlainText(analysis)
        self.notes_tabs.setCurrentWidget(self.analysis_editor)
        self.notes_status_label.setText("Análisis listo")
        if self.current_cache_path:
            self._save_song_notes()

    def _on_lyrics_analysis_error(self, error: str):
        self.notes_status_label.setText("Análisis no disponible")
        QMessageBox.warning(
            self,
            "Análisis de IA",
            f"No se pudo ejecutar el análisis de IA: {error}\n\n"
            "Configurá OPENAI_API_KEY e instalá el paquete openai para habilitar esta función.",
        )

    def _analyze_auto_lyrics(self, force: bool = False, show_errors: bool = True):
        """Run automatic lyric transcription for the loaded cached song."""
        if not self.current_cache_path:
            if show_errors:
                QMessageBox.information(self, "Letra automática", "Cargá o separá una canción antes de analizar la letra.")
            return
        if self.auto_lyrics_worker and self.auto_lyrics_worker.isRunning():
            return

        self.lyrics_sync_panel.set_status("Transcribiendo voz...")
        self.notes_status_label.setText("Analizando letra...")
        language = self.lyrics_sync_panel.selected_language() or None
        self.auto_lyrics_worker = AutoLyricsWorker(self.current_cache_path, self.current_file, force, language)
        self.auto_lyrics_worker.finished.connect(self._on_auto_lyrics_finished)
        self.auto_lyrics_worker.error.connect(lambda error: self._on_auto_lyrics_error(error, show_errors))
        self.auto_lyrics_worker.start()

    def _on_auto_lyrics_finished(self, segments: list):
        self.lyrics_sync_panel.set_segments(segments)
        self.lyrics_sync_panel.set_status("Letra lista")
        self.notes_status_label.setText(
            "Letra y acordes listos" if self.chord_sync_panel.segments else "Letra lista"
        )
        self.auto_lyrics_worker = None

    def _on_auto_lyrics_error(self, error: str, show_message: bool = True):
        self.lyrics_sync_panel.set_status("No se pudo generar la letra automáticamente")
        self.notes_status_label.setText("No se pudo generar la letra automáticamente")
        self.auto_lyrics_worker = None
        logger.warning("Automatic lyrics unavailable: %s", error)
        if show_message:
            QMessageBox.warning(self, "Letra automática", error)

    def _on_lyrics_language_changed(self, language: str):
        """Update hint; processing starts only when the user confirms."""
        if not self.current_cache_path or self.lyrics_sync_panel.has_lyrics():
            return
        self.lyrics_sync_panel.set_status("Elegí idioma y tocá Procesar letra")

    def _analyze_auto_chords(self, force: bool = False, show_errors: bool = True):
        """Run automatic chord detection for the loaded cached song."""
        if not self.current_cache_path:
            if show_errors:
                QMessageBox.information(self, "Acordes automáticos", "Cargá o separá una canción antes de analizar acordes.")
            return
        if self.auto_chords_worker and self.auto_chords_worker.isRunning():
            return

        self.chord_sync_panel.set_status("Detectando acordes...")
        self.notes_status_label.setText("Analizando acordes...")
        self.auto_chords_worker = AutoChordsWorker(self.current_cache_path, self.current_file, force)
        self.auto_chords_worker.finished.connect(self._on_auto_chords_finished)
        self.auto_chords_worker.error.connect(lambda error: self._on_auto_chords_error(error, show_errors))
        self.auto_chords_worker.start()

    def _on_auto_chords_finished(self, segments: list):
        self.chord_sync_panel.set_segments(segments)
        self.lyrics_sync_panel.set_chord_segments(segments)
        self.chord_sync_panel.set_status("Acordes listos (aproximados)")
        self.notes_status_label.setText(
            "Letra y acordes listos" if self.lyrics_sync_panel.has_lyrics() else "Acordes listos"
        )
        self.auto_chords_worker = None

    def _on_auto_chords_error(self, error: str, show_message: bool = True):
        self.chord_sync_panel.set_status("No se pudieron detectar acordes")
        self.notes_status_label.setText("No se pudieron detectar acordes")
        self.auto_chords_worker = None
        logger.warning("Automatic chords unavailable: %s", error)
        if show_message:
            QMessageBox.warning(self, "Acordes automáticos", error)

    def _add_marker(self):
        """Add a marker at the current playhead."""
        if not self.player.state.total_frames:
            return

        frame = self.player.state.current_frame
        name = self.marker_name_input.text().strip() or self._format_time(frame / SAMPLE_RATE)
        self.markers.append({"name": name, "frame": frame})
        self.markers = sorted(self.markers, key=lambda marker: marker["frame"])
        self.marker_name_input.clear()
        self._refresh_markers()
        if self.current_cache_path:
            self._save_song_notes()

    def _refresh_markers(self):
        """Refresh marker list widget."""
        self.marker_list.clear()
        for marker in self.markers:
            frame = int(marker.get("frame", 0))
            item = QListWidgetItem(f"{self._format_time(frame / SAMPLE_RATE)}  {marker.get('name', '')}")
            item.setData(Qt.ItemDataRole.UserRole, frame)
            self.marker_list.addItem(item)

    def _go_to_selected_marker(self):
        """Seek to the selected marker."""
        item = self.marker_list.currentItem()
        if item:
            self._go_to_marker(item)

    def _go_to_marker(self, item: QListWidgetItem):
        """Seek to a marker item."""
        frame = item.data(Qt.ItemDataRole.UserRole)
        if frame is not None:
            self.player.seek(int(frame))

    def _delete_selected_marker(self):
        """Delete selected marker."""
        item = self.marker_list.currentItem()
        if not item:
            return
        frame = item.data(Qt.ItemDataRole.UserRole)
        self.markers = [marker for marker in self.markers if int(marker.get("frame", 0)) != int(frame)]
        self._refresh_markers()
        if self.current_cache_path:
            self._save_song_notes()

    def _normalize_markers(self, markers: list) -> list:
        """Normalize persisted marker data."""
        normalized = []
        for marker in markers:
            try:
                frame = int(marker.get("frame", 0))
            except (TypeError, ValueError):
                continue
            normalized.append({
                "name": str(marker.get("name", self._format_time(frame / SAMPLE_RATE))),
                "frame": max(0, frame),
            })
        return sorted(normalized, key=lambda marker: marker["frame"])

    def _apply_practice_fx(self):
        """Apply offline tempo/pitch transforms to the loaded stems."""
        if not self.original_stems:
            QMessageBox.information(self, "FX", "Cargá o separá una canción primero.")
            return

        tempo = self.tempo_slider.value()
        pitch = self.pitch_slider.value()
        if tempo == 100 and pitch == 0:
            self._reset_practice_fx()
            return

        if self.player.is_playing():
            self.player.pause()
        self.notes_status_label.setText("Aplicando FX...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.transform_worker = PracticeTransformWorker(self.original_stems, tempo, pitch, SAMPLE_RATE)
        self.transform_worker.progress.connect(self.progress_bar.setValue)
        self.transform_worker.finished.connect(self._on_practice_fx_finished)
        self.transform_worker.error.connect(self._on_practice_fx_error)
        self.transform_worker.start()

    def _on_practice_fx_finished(self, stems: dict):
        """Load transformed practice stems."""
        self.progress_bar.setVisible(False)
        self.notes_status_label.setText("FX listo")
        self.transform_worker = None
        self.player.clear_loop()
        self._update_mixer(stems, update_original=False)

    def _on_practice_fx_error(self, error: str):
        """Handle tempo/pitch transform failure."""
        self.progress_bar.setVisible(False)
        self.notes_status_label.setText("FX no disponible")
        self.transform_worker = None
        QMessageBox.critical(self, "Error de FX", f"No se pudo aplicar tempo/pitch: {error}")

    def _reset_practice_fx(self):
        """Restore original loaded stems after practice transforms."""
        self._reset_practice_sliders()
        if self.original_stems:
            if self.player.is_playing():
                self.player.pause()
            self.player.clear_loop()
            self._update_mixer(self.original_stems, update_original=False)

    def _reset_practice_sliders(self):
        """Reset tempo and pitch UI controls."""
        self.tempo_slider.blockSignals(True)
        self.pitch_slider.blockSignals(True)
        self.tempo_slider.setValue(100)
        self.pitch_slider.setValue(0)
        self.tempo_slider.blockSignals(False)
        self.pitch_slider.blockSignals(False)
        self._on_tempo_slider_changed(100)
        self._on_pitch_slider_changed(0)

    def _on_tempo_slider_changed(self, value: int):
        """Update visible tempo value."""
        self.tempo_value_label.setText(f"{value}%")

    def _on_pitch_slider_changed(self, value: int):
        """Update visible pitch value."""
        self.pitch_value_label.setText(f"{value:+d} st")

    def _update_mixer(self, stems: dict, update_original: bool = True):
        """Update mixer UI with stems."""
        self.current_stems = stems
        if update_original:
            self.original_stems = stems

        # Clear existing stem controls
        self.mixer.reset()
        self.mixer.stems.clear()
        self.stem_widgets = {}
        while self.stems_layout.count() > 1:
            item = self.stems_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new stem controls
        for stem_name, audio in stems.items():
            self.mixer.add_stem(stem_name)
            widget = StemControlWidget(stem_name, audio)
            widget.volume_changed.connect(self._on_stem_volume_changed)
            widget.mute_toggled.connect(self._on_stem_mute_toggled)
            widget.solo_toggled.connect(self._on_stem_solo_toggled)
            self.stem_widgets[stem_name] = widget
            self.stems_layout.insertWidget(self.stems_layout.count() - 1, widget)

        # Enable playback
        self._set_playback_buttons(True, False, False)
        for controls in self.playback_controls:
            controls.seek_slider.setEnabled(True)

        # Set player stems
        self.player.load_stems(stems)
        self._update_player_mix_controls()
        self._update_seek_slider()

    def _on_stem_volume_changed(self, stem_name: str, volume: float):
        """Handle stem volume change."""
        self.mixer.set_volume(stem_name, volume)
        self._update_player_mix_controls()

    def _on_stem_mute_toggled(self, stem_name: str, is_muted: bool):
        """Handle stem mute toggle."""
        self.mixer.set_mute(stem_name, is_muted)
        self._update_player_mix_controls()

    def _on_stem_solo_toggled(self, stem_name: str, is_soloed: bool):
        """Handle stem solo toggle."""
        self.mixer.toggle_solo(stem_name)
        for name, widget in self.stem_widgets.items():
            if name in self.mixer.stems:
                widget.set_soloed(self.mixer.stems[name].soloed)
        self._update_player_mix_controls()

    def _update_player_mix_controls(self):
        """Update streaming player gains from current mixer controls."""
        if self.current_stems:
            gains = {
                name: self.mixer.stems[name].get_gain(self.mixer.any_soloed)
                for name in self.current_stems
                if name in self.mixer.stems
            }
            self.player.set_stem_gains(gains)

    def _update_seek_slider(self):
        """Update both timeline ranges from the shared player."""
        if self.player.state.total_frames > 0:
            for controls in self.playback_controls:
                controls.seek_slider.setMaximum(self.player.state.total_frames - 1)
                controls.duration_label.setText(self._format_time(self.player.get_duration_seconds()))

    def _on_seek(self, value: int):
        """Handle seek slider move."""
        self.player.seek(value)
        self._sync_playback_position()

    def _on_master_volume_changed(self, volume: float):
        """Apply one master volume and mirror it in both control views."""
        self.player.set_volume(volume)
        for controls in self.playback_controls:
            controls.master_volume.set_volume(volume)

    def _set_playback_buttons(self, play: bool, pause: bool, stop: bool):
        for controls in self.playback_controls:
            controls.play_btn.setEnabled(play)
            controls.pause_btn.setEnabled(pause)
            controls.stop_btn.setEnabled(stop)

    def _on_play(self):
        """Play button clicked."""
        try:
            self._update_player_mix_controls()
            self.player.play()
            self._set_playback_buttons(False, True, True)
        except Exception as e:
            logger.error(f"Error playing: {e}")
            QMessageBox.critical(self, "Error de reproducción", f"Error: {e}")

    def _on_pause(self):
        """Pause button clicked."""
        self.player.pause()
        self._set_playback_buttons(True, False, True)

    def _on_stop(self):
        """Stop button clicked."""
        self.player.stop()
        self._set_playback_buttons(bool(self.current_stems), False, False)
        self._sync_playback_position()

    def _sync_playback_position(self):
        """Mirror player position into timelines, waveforms, chords, and karaoke."""
        if self.player.state.total_frames <= 0:
            return
        current_sec = self.player.get_current_time_seconds()
        total_sec = self.player.get_duration_seconds()
        for controls in self.playback_controls:
            controls.time_label.setText(self._format_time(current_sec))
            controls.duration_label.setText(self._format_time(total_sec))
            if not controls.seek_slider.isSliderDown():
                controls.seek_slider.blockSignals(True)
                controls.seek_slider.setValue(self.player.state.current_frame)
                controls.seek_slider.blockSignals(False)

        for widget in self.stem_widgets.values():
            widget.set_playhead_frame(self.player.state.current_frame, self.player.state.total_frames)
        self.lyrics_sync_panel.update_time(current_sec)
        self.chord_sync_panel.update_time(current_sec)

    def _update_ui(self):
        """Update UI elements (timeline, buttons)."""
        if self.player.state.total_frames > 0:
            self._sync_playback_position()

            if not self.player.is_playing() and self.current_stems and not self.play_btn.isEnabled():
                self._set_playback_buttons(True, False, False)

    def _on_playback_update(self, frame: int):
        """Callback from player for progress updates."""
        pass  # UI is updated by timer instead

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format time as MM:SS."""
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes}:{secs:02d}"

    @staticmethod
    def _format_duration(seconds) -> str:
        """Format optional duration for the library table."""
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            return "—"
        if value <= 0:
            return "—"
        minutes = int(value) // 60
        secs = int(value) % 60
        return f"{minutes}:{secs:02d}"

    @staticmethod
    def _format_tempo(tempo) -> str:
        """Format optional tempo metadata for the library table."""
        if tempo in (None, ""):
            return "—"
        try:
            return f"{float(tempo):.0f} BPM"
        except (TypeError, ValueError):
            return str(tempo)

def main():
    """Run the application."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
