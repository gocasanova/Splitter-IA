"""Small synchronized chord display panel."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QHBoxLayout, QWidget

from src.models.chords import ChordSegment, get_current_chord


class ChordSyncPanel(QWidget):
    """Display current/next approximate chords and the full timeline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.segments: list[ChordSegment] = []
        self.details_visible = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        actions = QHBoxLayout()
        self.analyze_btn = QPushButton("Analizar acordes automaticamente")
        self.reanalyze_btn = QPushButton("Reanalizar acordes")
        actions.addWidget(self.analyze_btn)
        actions.addWidget(self.reanalyze_btn)
        actions.addStretch()
        layout.addLayout(actions)

        self.status_label = QLabel("Sin acordes automaticos")
        self.status_label.setStyleSheet("color: #9ca3af;")
        layout.addWidget(self.status_label)

        self.current_label = QLabel("...")
        self.current_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_label.setFont(QFont("Arial", 30, QFont.Weight.Bold))
        self.current_label.setStyleSheet("color: #f8fafc; padding: 10px;")
        layout.addWidget(self.current_label)

        self.next_label = QLabel("")
        self.next_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_label.setStyleSheet("color: #9ca3af; padding: 6px;")
        layout.addWidget(self.next_label)

        self.details_btn = QPushButton("Mostrar detalle tecnico")
        self.details_btn.setCheckable(True)
        self.details_btn.clicked.connect(self._toggle_details)
        layout.addWidget(self.details_btn)

        self.full_text = QPlainTextEdit()
        self.full_text.setReadOnly(True)
        self.full_text.setPlaceholderText("La linea completa de acordes aparecera aca. Resultado aproximado.")
        self.full_text.setVisible(False)
        layout.addWidget(self.full_text, 1)

    def set_segments(self, segments: list[ChordSegment]) -> None:
        self.segments = segments
        self.status_label.setText(
            f"{len(segments)} acordes sincronizados (aproximado)"
            if segments else "Sin acordes automaticos"
        )
        self.full_text.setPlainText(
            "\n".join(
                f"{self._format_time(segment.start)} - {self._format_time(segment.end)}   "
                f"{segment.chord}   ({segment.confidence:.2f})"
                for segment in segments
            )
        )
        self.update_time(0.0)

    def set_status(self, status: str) -> None:
        self.status_label.setText(status)

    def update_time(self, current_time: float) -> None:
        current, next_segment = get_current_chord(current_time, self.segments)
        self.current_label.setText(current.chord if current else "...")
        if next_segment:
            self.next_label.setText(f"Siguiente: {next_segment.chord}")
        else:
            self.next_label.setText("")

    def _toggle_details(self):
        self.details_visible = self.details_btn.isChecked()
        self.full_text.setVisible(self.details_visible)
        self.details_btn.setText("Ocultar detalle tecnico" if self.details_visible else "Mostrar detalle tecnico")

    @staticmethod
    def _format_time(seconds: float) -> str:
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes}:{secs:02d}"
