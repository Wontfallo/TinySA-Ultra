"""
Sleek, ultra-modern Dark Theme stylesheet and styling tokens for TinySA Ultra Spectrum Analyzer.
Optimized for high-DPI displays with large, crisp, legible typography and neon accenting.
"""

DARK_STYLESHEET = """
/* Main Application Styling */
QMainWindow, QDialog {
    background-color: #0b0e14;
    color: #e2e8f0;
    font-family: 'Segoe UI', 'Inter', 'Roboto', 'Arial', sans-serif;
    font-size: 13px;
}

QWidget {
    color: #e2e8f0;
    font-family: 'Segoe UI', 'Inter', 'Roboto', sans-serif;
    font-size: 13px;
}

/* Tooltips */
QToolTip {
    background-color: #1e2538;
    color: #00e5ff;
    border: 1px solid #00e5ff;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
    font-weight: 500;
}

/* Dock Widgets & Panels */
QDockWidget {
    titlebar-close-icon: url(close.png);
    titlebar-normal-icon: url(undock.png);
    border: 1px solid #1e293b;
}

QDockWidget::title {
    text-align: left;
    background: #111827;
    padding: 8px 12px;
    font-weight: 700;
    font-size: 13px;
    color: #38bdf8;
    border-bottom: 1px solid #1e293b;
}

QGroupBox {
    background-color: #111827;
    border: 1px solid #1f293d;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 14px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    color: #00e5ff;
    background-color: #0b0e14;
    border: 1px solid #1f293d;
    border-radius: 4px;
    font-size: 12px;
    font-weight: bold;
}

/* Buttons */
QPushButton {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
    min-height: 24px;
}

QPushButton:hover {
    background-color: #0f766e;
    border-color: #14b8a6;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #0d9488;
}

QPushButton:disabled {
    background-color: #0f172a;
    color: #475569;
    border-color: #1e293b;
}

QPushButton#accentButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0ea5e9);
    border: 1px solid #38bdf8;
    color: #ffffff;
    font-weight: bold;
}

QPushButton#accentButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369a1, stop:1 #0284c7);
    border-color: #7dd3fc;
}

QPushButton#dangerButton {
    background-color: #991b1b;
    border: 1px solid #ef4444;
    color: #ffffff;
}

QPushButton#dangerButton:hover {
    background-color: #dc2626;
}

QPushButton#successButton {
    background-color: #065f46;
    border: 1px solid #10b981;
    color: #ffffff;
}

QPushButton#successButton:hover {
    background-color: #047857;
}

/* Combo Boxes & Inputs */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #0f172a;
    color: #38bdf8;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    font-weight: 600;
    selection-background-color: #0284c7;
}

QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
    border-color: #38bdf8;
}

QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border-color: #00e5ff;
    background-color: #1e293b;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left-width: 1px;
    border-left-color: #334155;
    border-left-style: solid;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}

QComboBox QAbstractItemView {
    background-color: #0f172a;
    border: 1px solid #38bdf8;
    selection-background-color: #0284c7;
    color: #f8fafc;
    padding: 4px;
}

/* Sliders */
QSlider::groove:horizontal {
    border: 1px solid #334155;
    height: 8px;
    background: #0f172a;
    border-radius: 4px;
}

QSlider::sub-page:horizontal {
    background: #00e5ff;
    border-radius: 4px;
}

QSlider::handle:horizontal {
    background: #38bdf8;
    border: 1px solid #e2e8f0;
    width: 18px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 9px;
}

QSlider::handle:horizontal:hover {
    background: #00e5ff;
    border-color: #ffffff;
}

/* Tab Widgets */
QTabWidget::pane {
    border: 1px solid #1e293b;
    background: #0b0e14;
    border-radius: 6px;
}

QTabBar::tab {
    background: #111827;
    color: #94a3b8;
    border: 1px solid #1e293b;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background: #1e293b;
    color: #00e5ff;
    border-bottom: 2px solid #00e5ff;
    font-weight: bold;
}

QTabBar::tab:hover:!selected {
    background: #1f293d;
    color: #cbd5e1;
}

/* Tables */
QTableWidget, QTreeWidget {
    background-color: #0f172a;
    color: #e2e8f0;
    gridline-color: #1e293b;
    border: 1px solid #1e293b;
    border-radius: 6px;
    font-size: 12px;
}

QHeaderView::section {
    background-color: #111827;
    color: #38bdf8;
    padding: 6px;
    font-weight: bold;
    border: 1px solid #1e293b;
}

QTableWidget::item:selected {
    background-color: #0284c7;
    color: #ffffff;
}

/* Scroll Bars */
QScrollBar:vertical {
    border: none;
    background: #0b0e14;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #334155;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #00e5ff;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #0b0e14;
    height: 10px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #334155;
    min-width: 20px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background: #00e5ff;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Checkboxes & Radio Buttons */
QCheckBox, QRadioButton {
    spacing: 8px;
    font-size: 13px;
    font-weight: 500;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #334155;
    background: #0f172a;
}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #00e5ff;
}

QCheckBox::indicator:checked {
    background-color: #00e5ff;
    border-color: #00e5ff;
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%230b0e14' stroke-width='4' stroke-linecap='round' stroke-linejoin='round'><polyline points='20 6 9 17 4 12'></polyline></svg>");
}

/* Status Bar */
QStatusBar {
    background-color: #0b0e14;
    color: #94a3b8;
    border-top: 1px solid #1e293b;
    font-weight: 500;
}

QStatusBar::item {
    border: none;
}
"""

COLOR_PALETTE = {
    "bg_dark": "#0b0e14",
    "card_bg": "#111827",
    "accent_cyan": "#00e5ff",
    "accent_emerald": "#00ff9d",
    "accent_yellow": "#ffb700",
    "accent_magenta": "#ff007f",
    "trace_live": "#00e5ff",      # Cyan
    "trace_maxhold": "#ff3366",   # Red/Pink
    "trace_minhold": "#00ff9d",   # Emerald Green
    "trace_avg": "#ffcc00",       # Amber Gold
    "trace_math": "#bd93f9",      # Purple/Violet
    "grid_color": "#1e293b",
    "text_primary": "#f8fafc",
    "text_secondary": "#94a3b8",
}
