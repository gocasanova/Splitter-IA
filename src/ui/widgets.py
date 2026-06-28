# Custom PyQt6 widgets for the application
from PyQt6.QtWidgets import (
    QSlider, QPushButton, QLabel, QWidget, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QFrame, QStyle, QStyleOptionSlider
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
import numpy as np


class SeekSlider(QSlider):
    """Timeline slider that supports both handle dragging and direct groove clicks."""

    seek_requested = pyqtSignal(int)

    def mousePressEvent(self, event):
        if (
            event.button() != Qt.MouseButton.LeftButton
            or self.orientation() != Qt.Orientation.Horizontal
            or not self.isEnabled()
        ):
            super().mousePressEvent(event)
            return

        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )
        if handle.contains(event.position().toPoint()):
            super().mousePressEvent(event)
            return

        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )
        span = max(1, groove.width())
        position = max(0, min(int(event.position().x()) - groove.left(), span))
        value = QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            position,
            span,
            option.upsideDown,
        )
        self.setValue(value)
        self.seek_requested.emit(value)
        event.accept()


class PlaybackControls(QFrame):
    """Reusable view over the application's single global audio player."""

    play_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    seek_requested = pyqtSignal(int)
    volume_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        layout = QVBoxLayout(self)

        timeline = QHBoxLayout()
        self.time_label = QLabel("00:00")
        self.seek_slider = SeekSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setEnabled(False)
        self.seek_slider.sliderMoved.connect(self.seek_requested.emit)
        self.seek_slider.seek_requested.connect(self.seek_requested.emit)
        self.duration_label = QLabel("00:00")
        timeline.addWidget(self.time_label)
        timeline.addWidget(self.seek_slider, 1)
        timeline.addWidget(self.duration_label)
        layout.addLayout(timeline)

        buttons = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(lambda: self.play_requested.emit())
        buttons.addWidget(self.play_btn)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(lambda: self.pause_requested.emit())
        buttons.addWidget(self.pause_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(lambda: self.stop_requested.emit())
        buttons.addWidget(self.stop_btn)

        buttons.addWidget(QLabel("Volumen master:"))
        self.master_volume = VolumeSlider()
        self.master_volume.setMaximumWidth(150)
        self.master_volume.value_changed.connect(self.volume_changed.emit)
        buttons.addWidget(self.master_volume)
        buttons.addStretch()
        layout.addLayout(buttons)

class VolumeSlider(QSlider):
    """Custom volume slider (0-100)."""

    value_changed = pyqtSignal(float)  # Emits 0.0-1.0

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setMinimum(0)
        self.setMaximum(100)
        self.setValue(100)
        self.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.setTickInterval(10)
        self.valueChanged.connect(self._on_value_changed)

    def _on_value_changed(self):
        self.value_changed.emit(self.value() / 100.0)

    def set_volume(self, value: float):
        """Set volume from 0.0-1.0."""
        self.blockSignals(True)
        self.setValue(int(value * 100))
        self.blockSignals(False)

class ControlButton(QPushButton):
    """Custom button for mixer controls."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.setFixedSize(34, 28)
        self.setCheckable(True)

class StemControlWidget(QWidget):
    """DAW-style strip for controlling a single stem."""

    volume_changed = pyqtSignal(str, float)  # stem_name, volume
    mute_toggled = pyqtSignal(str, bool)     # stem_name, is_muted
    solo_toggled = pyqtSignal(str, bool)     # stem_name, is_soloed

    STEM_COLORS = {
        "vocals": "#f25f5c",
        "drums": "#ffe066",
        "bass": "#70c1b3",
        "other": "#8ecae6",
    }

    def __init__(self, stem_name: str, audio: np.ndarray | None = None, parent=None):
        super().__init__(parent)
        self.stem_name = stem_name
        self.accent = self.STEM_COLORS.get(stem_name.lower(), "#4cc9f0")
        self._init_ui()
        if audio is not None:
            self.set_audio(audio)

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        self.setMinimumHeight(78)
        self.setObjectName("StemTrack")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        label_col = QVBoxLayout()
        label_col.setSpacing(2)
        label = QLabel(self.stem_name.upper())
        label.setMinimumWidth(78)
        label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {self.accent};")
        label_col.addWidget(label)

        self.volume_value = QLabel("100")
        self.volume_value.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.volume_value.setFont(QFont("Arial", 9))
        self.volume_value.setStyleSheet("color: #9ca3af;")
        label_col.addWidget(self.volume_value)
        label_col.addStretch()
        layout.addLayout(label_col)

        self.waveform = WaveformWidget(accent=self.accent, empty_text="")
        self.waveform.setMinimumHeight(50)
        self.waveform.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.waveform, 1)

        controls = QHBoxLayout()
        controls.setSpacing(6)

        # Volume slider
        self.volume_slider = VolumeSlider()
        self.volume_slider.setFixedWidth(96)
        self.volume_slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self.volume_slider.value_changed.connect(self._on_volume_changed)
        controls.addWidget(self.volume_slider)

        # Mute button
        self.mute_btn = ControlButton("M")
        self.mute_btn.setObjectName("MuteButton")
        self.mute_btn.setToolTip("Mute")
        self.mute_btn.clicked.connect(self._on_mute_clicked)
        controls.addWidget(self.mute_btn)

        # Solo button
        self.solo_btn = ControlButton("S")
        self.solo_btn.setObjectName("SoloButton")
        self.solo_btn.setToolTip("Solo")
        self.solo_btn.clicked.connect(self._on_solo_clicked)
        controls.addWidget(self.solo_btn)
        layout.addLayout(controls)

        self.setLayout(layout)

    def _on_volume_changed(self, value: float):
        self.volume_value.setText(f"{int(value * 100)}")
        self.volume_changed.emit(self.stem_name, value)

    def _on_mute_clicked(self):
        is_muted = self.mute_btn.isChecked()
        self.mute_toggled.emit(self.stem_name, is_muted)

    def _on_solo_clicked(self):
        is_soloed = self.solo_btn.isChecked()
        self.solo_toggled.emit(self.stem_name, is_soloed)

    def set_volume(self, value: float):
        self.volume_slider.set_volume(value)

    def set_muted(self, muted: bool):
        self.mute_btn.setChecked(muted)

    def set_soloed(self, soloed: bool):
        self.solo_btn.setChecked(soloed)

    def set_audio(self, audio: np.ndarray) -> None:
        self.waveform.set_audio(audio)

    def set_playhead_frame(self, current_frame: int, total_frames: int) -> None:
        ratio = current_frame / total_frames if total_frames else 0.0
        self.waveform.set_position_ratio(ratio)


class WaveformWidget(QWidget):
    """Compact waveform preview for the loaded song."""

    def __init__(self, parent=None, accent: str = "#4cc9f0", empty_text: str = "Waveform preview"):
        super().__init__(parent)
        self._peaks = np.array([], dtype=np.float32)
        self._position_ratio = 0.0
        self.accent = accent
        self.empty_text = empty_text
        self.setMinimumHeight(96)

    def set_audio(self, audio: np.ndarray, points: int = 900) -> None:
        """Set mono or multi-channel audio and downsample it into drawable peaks."""
        if audio.size == 0:
            self._peaks = np.array([], dtype=np.float32)
            self.update()
            return

        mono = np.mean(audio, axis=0) if audio.ndim == 2 else audio
        mono = mono.astype(np.float32, copy=False)
        block_size = max(1, int(np.ceil(mono.size / points)))
        padded = np.pad(mono, (0, (-mono.size) % block_size), mode="constant")
        blocks = padded.reshape(-1, block_size)
        peaks = np.max(np.abs(blocks), axis=1)
        max_peak = float(np.max(peaks)) if peaks.size else 0.0
        self._peaks = peaks / max_peak if max_peak > 0 else peaks
        self.update()

    def set_position_ratio(self, ratio: float) -> None:
        self._position_ratio = float(np.clip(ratio, 0.0, 1.0))
        self.update()

    def clear(self) -> None:
        self._peaks = np.array([], dtype=np.float32)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#181818"))

        mid_y = self.height() / 2
        painter.setPen(QPen(QColor("#30363d"), 1))
        painter.drawLine(0, int(mid_y), self.width(), int(mid_y))

        if self._peaks.size == 0:
            painter.setPen(QColor("#7d8590"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.empty_text)
            return

        painter.setPen(QPen(QColor(self.accent), 2))
        step = self.width() / max(self._peaks.size, 1)
        amp = max(2, self.height() * 0.42)
        for index, peak in enumerate(self._peaks):
            x = int(index * step)
            y = int(peak * amp)
            painter.drawLine(x, int(mid_y - y), x, int(mid_y + y))

        if self._position_ratio > 0:
            x = int(self.width() * self._position_ratio)
            painter.setPen(QPen(QColor("#f8fafc"), 1))
            painter.drawLine(x, 0, x, self.height())
