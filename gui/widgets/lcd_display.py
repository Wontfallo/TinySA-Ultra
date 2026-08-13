"""
Custom LCD Readout Widget for TinySA Ultra Spectrum Analyzer.
Presents high-contrast, large-font digital readouts for frequency, dBm, and marker metrics.
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt
from utils.presets import format_frequency_fixed


class DigitalLCDDisplay(QFrame):
    """High-contrast digital readout panel for key RF metrics."""

    def __init__(self, title="PEAK FREQUENCY", unit="MHz", accent_color="#00e5ff",
                 initial_value="---.---"):
        """
        ``unit`` is the small caption under the reading. Pass ``initial_value``
        for the large digits; putting a measurement in ``unit`` leaves a stale
        number sitting in the caption until the first update arrives.
        """
        super().__init__()
        self.accent_color = accent_color
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #080b10;
                border: 1px solid #1f293d;
                border-radius: 8px;
                padding: 6px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        # Title Label
        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        layout.addWidget(self.lbl_title)

        # Value Readout
        self.lbl_value = QLabel(initial_value)
        self.lbl_value.setStyleSheet(f"""
            color: {accent_color};
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 22px;
            font-weight: bold;
        """)
        self.lbl_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # The reading changes many times a second. Reserve a fixed width for the
        # widest value this field can ever show, so the banner never re-flows
        # and the row stops visibly jittering as digits come and go.
        self.lbl_value.setMinimumWidth(
            self.lbl_value.fontMetrics().horizontalAdvance("-8888.8888 MHz") + 8
        )
        self.lbl_value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.lbl_value)

        # Subtitle / Unit
        self.lbl_unit = QLabel(unit)
        self.lbl_unit.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.lbl_unit)

    def _set_text(self, text: str):
        """Write the reading, skipping the repaint when nothing changed."""
        if self.lbl_value.text() != text:
            self.lbl_value.setText(text)

    def set_value(self, val_text: str, unit_text: str = None):
        """Update LCD value text, and optionally the caption."""
        self._set_text(str(val_text))
        if unit_text and self.lbl_unit.text() != unit_text:
            self.lbl_unit.setText(unit_text)

    def set_frequency(self, hz: float):
        """Set a frequency reading directly in Hz.

        Uses the fixed-width formatter: trailing zeros are kept so the reading
        neither loses visible precision nor changes width between sweeps.
        """
        self._set_text(format_frequency_fixed(hz))

    def set_power(self, dbm: float):
        """Set a power reading in dBm, at constant width."""
        self._set_text(f"{dbm:+9.2f} dBm")

    def set_caption(self, text: str):
        """Change the small caption beneath the reading."""
        if self.lbl_unit.text() != text:
            self.lbl_unit.setText(text)
