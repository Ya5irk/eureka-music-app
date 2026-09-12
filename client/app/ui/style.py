"""A single coherent visual style for the app - not custom iconography or
pixel-perfect design (explicitly not required per the brief), just enough
so the app doesn't look like an unstyled debug build: consistent color
palette, spacing, and visible focus/hover/pressed/checked states.
"""

STYLESHEET = """
QWidget {
    background-color: #121212;
    color: #E8E8E8;
    font-family: "Ubuntu", "Segoe UI", sans-serif;
    font-size: 10pt;
}

QLabel {
    color: #E8E8E8;
}

QLabel#nowPlayingLabel {
    font-weight: 600;
    font-size: 11pt;
    padding: 2px 0;
}

QLabel#emptyStateLabel {
    color: #7A7A7A;
    font-style: italic;
    padding: 24px;
}

QLineEdit, QComboBox {
    background-color: #2A2A2A;
    border: 1px solid #3A3A3A;
    border-radius: 4px;
    padding: 6px 8px;
    selection-background-color: #2DD4BF;
    selection-color: #121212;
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid #2DD4BF;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}

QPushButton {
    background-color: #2A2A2A;
    border: 1px solid #3A3A3A;
    border-radius: 4px;
    padding: 7px 16px;
}
QPushButton:hover {
    background-color: #333333;
    border-color: #2DD4BF;
}
QPushButton:pressed {
    background-color: #1F1F1F;
}
QPushButton:checked {
    background-color: #1B4B45;
    border-color: #2DD4BF;
    color: #2DD4BF;
}
QPushButton:focus {
    border: 1px solid #2DD4BF;
}
QPushButton:disabled {
    color: #6A6A6A;
    border-color: #2A2A2A;
}

QListView {
    background-color: #181818;
    border: 1px solid #2A2A2A;
    border-radius: 4px;
    outline: none;
}
QListView::item {
    padding: 7px 8px;
    border-radius: 3px;
}
QListView::item:selected {
    background-color: #1B4B45;
    color: #2DD4BF;
}
QListView::item:hover:!selected {
    background-color: #232323;
}

QTabWidget::pane {
    border: 1px solid #2A2A2A;
    border-radius: 4px;
    top: -1px;
}
QTabBar::tab {
    background-color: #181818;
    color: #A0A0A0;
    padding: 8px 18px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #2A2A2A;
    color: #2DD4BF;
}
QTabBar::tab:hover {
    color: #E8E8E8;
}

QSlider::groove:horizontal {
    height: 4px;
    background: #3A3A3A;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #2DD4BF;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #E8E8E8;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::handle:horizontal:hover {
    background: #2DD4BF;
}
QSlider:focus::handle:horizontal {
    background: #2DD4BF;
    border: 2px solid #E8E8E8;
}

QStatusBar {
    background-color: #181818;
    color: #A0A0A0;
    border-top: 1px solid #2A2A2A;
}

QProgressBar {
    background-color: #2A2A2A;
    border: none;
    border-radius: 3px;
    text-align: center;
    color: #E8E8E8;
    max-height: 8px;
}
QProgressBar::chunk {
    background-color: #2DD4BF;
    border-radius: 3px;
}

QScrollBar:vertical {
    background: #181818;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #3A3A3A;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #2DD4BF;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QSplitter::handle {
    background-color: #2A2A2A;
}
"""
