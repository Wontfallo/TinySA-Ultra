"""
Real-Time 2D Waterfall / Spectrogram Heatmap Widget.
Renders rolling historical spectrum data over time using PyQtGraph ImageItem and pure NumPy colormaps.
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QSlider, QLabel, QPushButton,
    QCheckBox,
)
from PySide6.QtCore import Qt, Signal
import pyqtgraph as pg


def generate_colormap_lut(name: str) -> np.ndarray:
    """Generate 256x4 uint8 lookup table for waterfall plot using pure NumPy."""
    x = np.linspace(0, 1, 256)
    name = name.lower()
    
    if name == "plasma":
        r = np.clip(1.5 * x, 0, 1)
        g = np.clip(2.0 * x - 0.5, 0, 1)
        b = np.clip(1.0 - 1.2 * x, 0, 1)
    elif name == "inferno":
        r = np.clip(1.8 * x, 0, 1)
        g = np.clip(1.5 * x - 0.3, 0, 1)
        b = np.clip(2.0 * x - 1.0, 0, 1)
    elif name == "jet":
        r = np.clip(1.5 - np.abs(4.0 * x - 3.0), 0, 1)
        g = np.clip(1.5 - np.abs(4.0 * x - 2.0), 0, 1)
        b = np.clip(1.5 - np.abs(4.0 * x - 1.0), 0, 1)
    elif name in ("turbo", "rainbow"):
        r = np.clip(np.sin(x * np.pi), 0, 1)
        g = np.clip(np.sin((x + 0.33) * np.pi), 0, 1)
        b = np.clip(np.cos(x * np.pi * 0.5), 0, 1)
    else:  # Viridis (default)
        r = np.clip(0.2 + 0.7 * x, 0, 1)
        g = np.clip(1.1 * x, 0, 1)
        b = np.clip(0.6 - 0.5 * x + 0.4 * (x**2), 0, 1)

    lut = np.zeros((256, 4), dtype=np.uint8)
    lut[:, 0] = (r * 255).astype(np.uint8)
    lut[:, 1] = (g * 255).astype(np.uint8)
    lut[:, 2] = (b * 255).astype(np.uint8)
    lut[:, 3] = 255
    return lut


class WaterfallWidget(QWidget):
    """2D Rolling Spectrogram / Waterfall Plot Widget."""

    def __init__(self, history_depth=300, points=201, parent=None):
        super().__init__(parent)
        self.history_depth = history_depth
        self.points = points

        self.min_dbm = -110.0
        self.max_dbm = -10.0
        self.current_cmap_name = "viridis"

        # 2D Rolling Buffer: shape (history_depth, points)
        self.buffer = np.full((self.history_depth, self.points), self.min_dbm, dtype=np.float32)
        self.start_hz = 2400000000
        self.stop_hz = 2483500000
        #: Cached frequency span so setRect is only issued when it changes.
        self._rect_key = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Controls Header Bar
        control_bar = QHBoxLayout()
        control_bar.setContentsMargins(4, 2, 4, 2)

        lbl_cmap = QLabel("Colormap:")
        lbl_cmap.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 11px;")
        control_bar.addWidget(lbl_cmap)

        self.combo_cmap = QComboBox()
        self.combo_cmap.addItems(["viridis", "plasma", "inferno", "turbo", "jet", "rainbow"])
        self.combo_cmap.setToolTip("Select waterfall color intensity map palette")
        self.combo_cmap.currentTextChanged.connect(self.set_colormap)
        control_bar.addWidget(self.combo_cmap)

        control_bar.addSpacing(10)
        lbl_gain = QLabel("Floor (dBm):")
        lbl_gain.setStyleSheet("color: #94a3b8; font-size: 11px;")
        control_bar.addWidget(lbl_gain)

        self.slider_min_dbm = QSlider(Qt.Horizontal)
        self.slider_min_dbm.setRange(-140, -40)
        self.slider_min_dbm.setValue(-110)
        self.slider_min_dbm.setToolTip("Adjust waterfall minimum noise floor cut-off")
        self.slider_min_dbm.valueChanged.connect(self.on_contrast_changed)
        control_bar.addWidget(self.slider_min_dbm)

        lbl_ceiling = QLabel("Ceil (dBm):")
        lbl_ceiling.setStyleSheet("color: #94a3b8; font-size: 11px;")
        control_bar.addWidget(lbl_ceiling)

        self.slider_max_dbm = QSlider(Qt.Horizontal)
        self.slider_max_dbm.setRange(-60, 20)
        self.slider_max_dbm.setValue(-10)
        self.slider_max_dbm.setToolTip("Adjust waterfall peak ceiling intensity")
        self.slider_max_dbm.valueChanged.connect(self.on_contrast_changed)
        control_bar.addWidget(self.slider_max_dbm)

        self.chk_auto_levels = QCheckBox("Auto contrast")
        self.chk_auto_levels.setChecked(True)
        self.chk_auto_levels.setToolTip(
            "Continuously fit the colour range to the signal.\n"
            "A fixed -110..-10 dBm window wastes almost the entire palette when "
            "the noise floor sits near -90 dBm, which makes the display look flat."
        )
        self.chk_auto_levels.toggled.connect(self.on_auto_levels_toggled)
        control_bar.addWidget(self.chk_auto_levels)

        self.btn_clear = QPushButton("Clear Waterfall")
        self.btn_clear.setToolTip("Reset and clear rolling waterfall history buffer")
        self.btn_clear.clicked.connect(self.clear_waterfall)
        control_bar.addWidget(self.btn_clear)

        control_bar.addStretch()
        layout.addLayout(control_bar)

        # PyQtGraph Plot Widget for Waterfall Image
        self.plot_widget = pg.PlotWidget()
        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.showGrid(x=True, y=False, alpha=0.3)
        self.plot_item.setLabel('bottom', 'Frequency', units='Hz')
        self.plot_item.setLabel('left', 'History (sweeps ago)')

        # The newest sweep is written to row 0, and ImageItem maps row 0 to the
        # bottom of the view. Without inverting the axis the display scrolls
        # upward, which is backwards for a waterfall: newest belongs at the top
        # with history falling away beneath it.
        self.plot_item.getViewBox().invertY(True)

        self.img_item = pg.ImageItem()
        self.plot_item.addItem(self.img_item)

        # Build initial Lookup Table (LUT)
        self.update_lut()

        layout.addWidget(self.plot_widget)

    def set_colormap(self, cmap_name: str):
        """Change current colormap palette."""
        self.current_cmap_name = cmap_name
        self.update_lut()

    def update_lut(self):
        """Generate PyQtGraph Lookup Table from pure NumPy colormap function."""
        try:
            lut = generate_colormap_lut(self.current_cmap_name)
            self.img_item.setLookupTable(lut)
            self.img_item.setLevels([self.min_dbm, self.max_dbm])
        except Exception as e:
            print(f"Error setting colormap {self.current_cmap_name}: {e}")

    def on_auto_levels_toggled(self, enabled: bool):
        """Switch between fitted and manual contrast."""
        self.slider_min_dbm.setEnabled(not enabled)
        self.slider_max_dbm.setEnabled(not enabled)
        if not enabled:
            self.on_contrast_changed()

    def _auto_fit_levels(self):
        """Fit the colour window to the data actually in the buffer.

        Percentiles rather than min/max: a single strong carrier would
        otherwise stretch the ceiling and flatten everything else back into the
        noise.
        """
        finite = self.buffer[np.isfinite(self.buffer)]
        if finite.size < 16:
            return
        low = float(np.percentile(finite, 5.0))
        high = float(np.percentile(finite, 99.5))
        if high - low < 6.0:            # keep a usable spread on a quiet band
            high = low + 6.0
        # Ease toward the target so the palette does not flicker sweep to sweep.
        self.min_dbm += (low - self.min_dbm) * 0.15
        self.max_dbm += (high - self.max_dbm) * 0.15
        self.img_item.setLevels([self.min_dbm, self.max_dbm])

    def on_contrast_changed(self):
        """Update floor and ceiling image display levels."""
        if self.chk_auto_levels.isChecked():
            return
        low = float(self.slider_min_dbm.value())
        high = float(self.slider_max_dbm.value())
        # The two sliders have overlapping ranges, so guard against an inverted
        # or degenerate window, which makes ImageItem render a solid block.
        if high <= low:
            high = low + 1.0
        self.min_dbm, self.max_dbm = low, high
        self.img_item.setLevels([self.min_dbm, self.max_dbm])

    def add_sweep(self, freqs: np.ndarray, dbm_array: np.ndarray):
        """Push a new sweep line into the rolling waterfall buffer."""
        if freqs is None or dbm_array is None or len(dbm_array) == 0:
            return

        if len(dbm_array) != self.points:
            self.points = len(dbm_array)
            self.buffer = np.full((self.history_depth, self.points), self.min_dbm, dtype=np.float32)
            self._rect_key = None

        # Shift history down one row and write the newest sweep at the top.
        # np.roll allocated a fresh (history_depth x points) array on every
        # single frame; an in-place slice copy does the same work with no
        # allocation and no garbage.
        self.buffer[1:, :] = self.buffer[:-1, :]
        self.buffer[0, :] = dbm_array

        self.start_hz = float(freqs[0])
        self.stop_hz = float(freqs[-1])

        if self.chk_auto_levels.isChecked():
            self._auto_fit_levels()

        # Transposed so x=frequency, y=time.
        self.img_item.setImage(self.buffer.T, autoLevels=False)

        # setRect triggers a full scene-geometry update, so only call it when
        # the frequency span has actually changed.
        rect_key = (self.start_hz, self.stop_hz)
        if rect_key != self._rect_key:
            self.img_item.setRect(
                pg.QtCore.QRectF(self.start_hz, 0, self.stop_hz - self.start_hz, self.history_depth)
            )
            self._rect_key = rect_key

    def clear_waterfall(self):
        """Reset rolling buffer to the current floor level."""
        self.buffer.fill(self.min_dbm)
        self.img_item.setImage(self.buffer.T, autoLevels=False)
