# Dark theme styling for PyQt6
DARK_STYLESHEET = """
QMainWindow {
    background-color: #121417;
    color: #e5e7eb;
}

QWidget {
    background-color: #121417;
    color: #e5e7eb;
}

QLabel {
    color: #e5e7eb;
}

QPushButton {
    background-color: #242a31;
    color: #f8fafc;
    border: 1px solid #343c46;
    border-radius: 6px;
    padding: 8px 13px;
    font-weight: bold;
    font-size: 11px;
}

QPushButton:hover {
    background-color: #2f3741;
    border-color: #4cc9f0;
}

QPushButton:pressed {
    background-color: #1d232a;
}

QPushButton:checked {
    background-color: #b91c1c;
    border-color: #ef4444;
}

QPushButton:checked:hover {
    background-color: #dc2626;
}

QPushButton#MuteButton {
    color: #f8fafc;
    background-color: #303844;
    border-color: #4b5563;
}

QPushButton#MuteButton:checked {
    color: #ffffff;
    background-color: #b91c1c;
    border-color: #ef4444;
}

QPushButton#SoloButton {
    color: #f8fafc;
    background-color: #303844;
    border-color: #4b5563;
}

QPushButton#SoloButton:checked {
    color: #04130c;
    background-color: #34d399;
    border-color: #6ee7b7;
}

QPushButton#SoloButton:checked:hover {
    background-color: #6ee7b7;
}

QSlider::groove:horizontal {
    border: 1px solid #374151;
    height: 5px;
    margin: 2px 0;
    background-color: #1f2933;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background-color: #e5e7eb;
    border: 1px solid #f8fafc;
    width: 12px;
    margin: -5px 0;
    border-radius: 6px;
}

QSlider::handle:horizontal:hover {
    background-color: #4cc9f0;
    border: 1px solid #8be9ff;
}

QSlider::sub-page:horizontal {
    background-color: #4cc9f0;
    border-radius: 2px;
}

QProgressBar {
    border: 1px solid #343c46;
    border-radius: 5px;
    background-color: #1a1f25;
    text-align: center;
    color: #f8fafc;
}

QProgressBar::chunk {
    background-color: #4cc9f0;
    border-radius: 4px;
}

QLineEdit {
    background-color: #101317;
    border: 1px solid #252c34;
    border-radius: 5px;
    color: #e5e7eb;
    padding: 8px 10px;
    selection-background-color: #263544;
}

QLineEdit:focus {
    border: 1px solid #4cc9f0;
}

QPlainTextEdit {
    background-color: #101317;
    border: 1px solid #252c34;
    border-radius: 5px;
    color: #e5e7eb;
    padding: 8px;
    selection-background-color: #263544;
    font-size: 12px;
}

QPlainTextEdit:focus {
    border: 1px solid #4cc9f0;
}

QTabWidget::pane {
    border: 1px solid #252c34;
    border-radius: 7px;
    top: -1px;
}

QTabBar::tab {
    background-color: #1a1f25;
    color: #9ca3af;
    border: 1px solid #252c34;
    padding: 9px 18px;
    margin-right: 4px;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    font-weight: bold;
}

QTabBar::tab:selected {
    background-color: #22313c;
    color: #f8fafc;
    border-color: #4cc9f0;
}

QTabBar::tab:hover {
    background-color: #222a33;
    color: #f8fafc;
}

QScrollArea {
    background-color: #121417;
    border: none;
}

QScrollBar:vertical {
    background-color: #121417;
    width: 12px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #3a424d;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #5b6572;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
}

QFrame {
    background-color: #121417;
    border: none;
}

QFrame#Panel {
    background-color: #171c22;
    border: 1px solid #252c34;
    border-radius: 8px;
    padding: 10px;
}

QWidget#StemTrack {
    background-color: #1b2229;
    border: 1px solid #2a323c;
    border-radius: 8px;
}

QWidget#StemTrack:hover {
    border-color: #4b5563;
}

QListWidget {
    background-color: #101317;
    border: 1px solid #252c34;
    border-radius: 5px;
    color: #e5e7eb;
    padding: 3px;
}

QTableWidget {
    background-color: #101317;
    border: 1px solid #252c34;
    border-radius: 7px;
    color: #e5e7eb;
    gridline-color: #252c34;
    selection-background-color: #234357;
    selection-color: #f8fafc;
}

QTableWidget::item {
    padding: 8px 10px;
}

QHeaderView::section {
    background-color: #171c22;
    color: #9ca3af;
    border: none;
    border-bottom: 1px solid #2a323c;
    padding: 8px 10px;
    font-weight: bold;
}

QFrame#ChordCard, QFrame#ChordCardPrimary, QFrame#TempoCard {
    background-color: #101721;
    border: 1px solid #293542;
    border-radius: 8px;
}

QFrame#ChordCardPrimary {
    border-color: #4cc9f0;
}

QFrame#TempoCard {
    background-color: #111820;
}

QListWidget::item {
    padding: 8px 10px;
    border-radius: 6px;
}

QListWidget::item:selected {
    background-color: #234357;
    color: #f8fafc;
    border-left: 3px solid #4cc9f0;
}

QGroupBox {
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 3px 0 3px;
}

QMenu {
    background-color: #2a2a2a;
    color: #e0e0e0;
    border: 1px solid #555;
}

QMenu::item:selected {
    background-color: #0d47a1;
}

QMenuBar {
    background-color: #2a2a2a;
    color: #e0e0e0;
    border-bottom: 1px solid #555;
}

QMenuBar::item:selected {
    background-color: #0d47a1;
}

QDialog {
    background-color: #1e1e1e;
    color: #e0e0e0;
}

QFileDialog {
    background-color: #1e1e1e;
    color: #e0e0e0;
}
"""

def apply_dark_theme(app):
    """Apply dark theme to the application."""
    app.setStyleSheet(DARK_STYLESHEET)
