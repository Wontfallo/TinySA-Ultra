"""
Splash Screen for TinySA Ultra Spectrum Analyzer Desktop Application.
Renders logo artwork, version header, progress bar, and hardware initialization messages on startup.
"""

import time
import os
from PySide6.QtWidgets import QSplashScreen, QProgressBar, QLabel, QVBoxLayout, QWidget, QFrame
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QFont, QColor


class TinySASplashScreen(QSplashScreen):
    """Modern dark-themed Splash Screen with progress indicator."""

    def __init__(self, icon_path="resources/icon.png"):
        # Create base pixmap surface
        splash_pixmap = QPixmap(600, 360)
        splash_pixmap.fill(QColor("#080b10"))
        super().__init__(splash_pixmap, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)

        # Main Frame Layout
        container = QFrame(self)
        container.setGeometry(0, 0, 600, 360)
        container.setStyleSheet("""
            QFrame {
                background-color: #080b10;
                border: 2px solid #00e5ff;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(10)

        # Header Row with Logo Image & Title
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setAlignment(Qt.AlignCenter)

        if os.path.exists(icon_path):
            lbl_icon = QLabel()
            icon_pixmap = QPixmap(icon_path).scaled(110, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_icon.setPixmap(icon_pixmap)
            lbl_icon.setAlignment(Qt.AlignCenter)
            lbl_icon.setStyleSheet("border: none; background: transparent;")
            header_layout.addWidget(lbl_icon)

        lbl_title = QLabel("TinySA Ultra Spectrum Analyzer")
        lbl_title.setStyleSheet("""
            color: #00e5ff;
            font-family: 'Segoe UI', 'Inter', sans-serif;
            font-size: 22px;
            font-weight: 800;
            letter-spacing: 1px;
            border: none;
            background: transparent;
        """)
        lbl_title.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(lbl_title)

        lbl_sub = QLabel("Pro Suite v1.0.0 — High-Speed DSP & Waterfall Engine")
        lbl_sub.setStyleSheet("""
            color: #00ff9d;
            font-family: 'Segoe UI', sans-serif;
            font-size: 13px;
            font-weight: 600;
            border: none;
            background: transparent;
        """)
        lbl_sub.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(lbl_sub)

        layout.addWidget(header_widget)

        layout.addStretch()

        # Status Message Label
        self.lbl_status = QLabel("Initializing TinySA Ultra Application...")
        self.lbl_status.setStyleSheet("""
            color: #94a3b8;
            font-size: 12px;
            font-weight: 500;
            border: none;
            background: transparent;
        """)
        self.lbl_status.setAlignment(Qt.AlignLeft)
        layout.addWidget(self.lbl_status)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #111827;
                border: 1px solid #1e293b;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00e5ff, stop:1 #00ff9d);
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

    def set_progress(self, value: int, message: str):
        """Update progress bar value and status text."""
        self.progress_bar.setValue(value)
        self.lbl_status.setText(message)
        QTimer.singleShot(0, lambda: None)
        QSplashScreen.showMessage(self, "", Qt.AlignLeft, QColor(0, 0, 0, 0))
