"""Small synchronized lyrics display panel."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox, QLabel, QFrame, QPlainTextEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget
)

from src.models.chords import ChordSegment, get_current_chord
from src.models.lyrics import LyricSegment, get_current_lyric, get_current_word


class LyricsSyncPanel(QWidget):
    """Display current/next lyric lines and the full transcription."""

    language_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.segments: list[LyricSegment] = []
        self.chord_segments: list[ChordSegment] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        actions = QHBoxLayout()
        self.analyze_btn = QPushButton("Procesar letra")
        self.reanalyze_btn = QPushButton("Reanalizar letra")
        actions.addWidget(self.analyze_btn)
        actions.addWidget(self.reanalyze_btn)
        actions.addStretch()
        layout.addLayout(actions)
        self.reanalyze_btn.setVisible(False)

        status_row = QHBoxLayout()
        self.status_label = QLabel("○ Cargá una canción para ver la letra y los acordes")
        self.status_label.setStyleSheet("color: #9ca3af;")
        status_row.addWidget(self.status_label, 1)

        status_row.addWidget(QLabel("Idioma:"))
        self.language_combo = QComboBox()
        self.language_combo.addItem("Auto", "")
        self.language_combo.addItem("Español", "es")
        self.language_combo.addItem("Inglés", "en")
        self.language_combo.addItem("Portugués", "pt")
        self.language_combo.addItem("Francés", "fr")
        self.language_combo.addItem("Italiano", "it")
        self.language_combo.currentIndexChanged.connect(self._emit_language_changed)
        status_row.addWidget(self.language_combo)
        layout.addLayout(status_row)

        chord_row = QHBoxLayout()
        chord_row.setSpacing(12)
        self.current_chord_label = self._build_chord_card("Acorde actual", primary=True)
        chord_row.addWidget(self.current_chord_label, 1)

        self.next_chord_label = self._build_chord_card("Siguiente", primary=False)
        chord_row.addWidget(self.next_chord_label, 1)
        layout.addLayout(chord_row)

        self.current_label = QLabel("...")
        self.current_label.setWordWrap(True)
        self.current_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_label.setTextFormat(Qt.TextFormat.RichText)
        self.current_label.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        self.current_label.setStyleSheet("color: #f8fafc; padding: 12px;")
        layout.addWidget(self.current_label)

        self.next_label = QLabel("")
        self.next_label.setWordWrap(True)
        self.next_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_label.setFont(QFont("Arial", 13))
        self.next_label.setStyleSheet("color: #9ca3af; padding: 6px;")
        layout.addWidget(self.next_label)

        self.full_text = QPlainTextEdit()
        self.full_text.setReadOnly(True)
        self.full_text.setPlaceholderText("La transcripcion completa aparecera aca.")
        self.full_text.setVisible(False)
        layout.addWidget(self.full_text, 1)

    def set_segments(self, segments: list[LyricSegment]) -> None:
        self.segments = segments
        self.analyze_btn.setText("Reprocesar letra" if segments else "Procesar letra")
        self.status_label.setText("✓ Letra actualizando" if segments else "○ Sin letra automática")
        if segments:
            self.status_label.setStyleSheet("color: #34d399;")
        else:
            self.status_label.setStyleSheet("color: #9ca3af;")
        self.full_text.setPlainText("\n".join(segment.text for segment in segments))
        self.update_time(0.0)

    def set_chord_segments(self, segments: list[ChordSegment]) -> None:
        self.chord_segments = segments
        self.update_time(0.0)

    def set_status(self, status: str) -> None:
        ok_words = ("lista", "listos", "actualizando")
        prefix = "✓ " if any(word in status.lower() for word in ok_words) else "○ "
        self.status_label.setText(f"{prefix}{status}")
        self.status_label.setStyleSheet("color: #34d399;" if prefix == "✓ " else "color: #9ca3af;")

    def selected_language(self) -> str:
        return str(self.language_combo.currentData() or "")

    def has_lyrics(self) -> bool:
        return bool(self.segments)

    def update_time(self, current_time: float) -> None:
        _previous_segment, current, next_segment = self._get_karaoke_lines(current_time)
        current_chord, next_chord = get_current_chord(current_time, self.chord_segments)
        current_chord_text = current_chord.chord if current_chord else ""
        next_chord_text = next_chord.chord if next_chord else ""

        self.current_chord_label.findChild(QLabel, "ChordValue").setText(current_chord_text or "...")
        self.next_chord_label.findChild(QLabel, "ChordValue").setText(next_chord_text or "...")

        current_text = current.text if current else "..."
        next_text = next_segment.text if next_segment else ""
        current_word = get_current_word(current_time, current)
        self.current_label.setText(self._format_current_line(current, current_word) if current else current_text)
        self.next_label.setText(next_text)

    def _get_karaoke_lines(
        self,
        current_time: float,
    ) -> tuple[LyricSegment | None, LyricSegment | None, LyricSegment | None]:
        current, next_segment = get_current_lyric(current_time, self.segments)
        previous = None
        if current:
            for index, segment in enumerate(self.segments):
                if segment == current and index > 0:
                    previous = self.segments[index - 1]
                    break
        else:
            for segment in self.segments:
                if segment.end <= current_time:
                    previous = segment
                elif segment.start > current_time:
                    break
        return previous, current, next_segment

    @staticmethod
    def _build_chord_card(title: str, primary: bool) -> QFrame:
        card = QFrame()
        card.setObjectName("ChordCardPrimary" if primary else "ChordCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #9ca3af; font-size: 11px; font-weight: bold;")
        layout.addWidget(title_label)

        value_label = QLabel("...")
        value_label.setObjectName("ChordValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setFont(QFont("Arial", 28 if primary else 22, QFont.Weight.Bold))
        value_label.setStyleSheet("color: #f8fafc;")
        layout.addWidget(value_label)

        return card

    def _emit_language_changed(self):
        self.language_changed.emit(self.selected_language())

    @staticmethod
    def _format_current_line(segment, current_word) -> str:
        if not current_word or not segment.words:
            return segment.text
        parts = []
        for word in segment.words:
            clean = word.word.strip()
            if not clean:
                continue
            if word == current_word:
                parts.append(f"<span style='color:#4cc9f0;'>{clean}</span>")
            else:
                parts.append(clean)
        return " ".join(parts) or segment.text
