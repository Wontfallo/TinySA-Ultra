"""
Real-Time 2D Spectrum Analyzer Plot Widget powered by PyQtGraph.
Provides multi-trace rendering (Live, Max Hold, Min Hold, Average, Math),
interactive markers, crosshairs, a threshold alarm line, and auto-scaling.
"""

import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Signal, Qt
import pyqtgraph as pg
from utils.presets import format_frequency


class SpectrumPlotWidget(QWidget):
    """PyQtGraph-based real-time Spectrum Analyzer View."""

    # Markers are positioned programmatically (TargetItem is non-movable), so
    # there is no drag signal to expose here.
    alarm_level_changed = Signal(float)        # dragged threshold level, dBm

    def __init__(self, parent=None):
        super().__init__(parent)

        # Global pyqtgraph styling. Antialiasing is deliberately OFF: with five
        # curves at up to 450 points redrawn ~30x/second it is the single most
        # expensive rendering option and the visual gain is negligible.
        pg.setConfigOption('background', '#06090e')
        pg.setConfigOption('foreground', '#94a3b8')
        pg.setConfigOption('antialias', False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget)

        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.showGrid(x=True, y=True, alpha=0.3)
        self.plot_item.setLabel('bottom', 'Frequency', units='Hz')
        self.plot_item.setLabel('left', 'Power', units='dBm')
        self.plot_item.setYRange(-130, 15)
        self.plot_item.addLegend(offset=(-10, 10), labelTextColor='#94a3b8')

        # Trace Curve Definitions
        self.traces = {}
        self.trace_configs = {
            "live": {"color": "#00e5ff", "width": 2, "name": "Live (T1)", "visible": True},
            "max_hold": {"color": "#ff3366", "width": 1.5, "name": "Max Hold (T2)", "visible": True},
            "min_hold": {"color": "#00ff9d", "width": 1.5, "name": "Min Hold (T3)", "visible": False},
            "average": {"color": "#ffcc00", "width": 2, "name": "Average (T4)", "visible": False},
            "math": {"color": "#bd93f9", "width": 2, "name": "Math (T5)", "visible": False},
        }

        for key, cfg in self.trace_configs.items():
            pen = pg.mkPen(color=cfg["color"], width=cfg["width"])
            curve = self.plot_item.plot(pen=pen, name=cfg["name"])
            curve.setVisible(cfg["visible"])
            self.traces[key] = curve

        # Crosshair Lines
        self.v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#475569', width=1, style=Qt.DashLine))
        self.h_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#475569', width=1, style=Qt.DashLine))
        self.plot_item.addItem(self.v_line, ignoreBounds=True)
        self.plot_item.addItem(self.h_line, ignoreBounds=True)

        # Hover text readout
        self.crosshair_label = pg.TextItem(text="", anchor=(0, 1), color="#00e5ff")
        self.plot_item.addItem(self.crosshair_label, ignoreBounds=True)

        # Interactive Markers (1 to 6)
        self.markers = []
        self.marker_colors = ["#00e5ff", "#ffcc00", "#ff3366", "#00ff9d", "#bd93f9", "#ff9100"]
        for i in range(6):
            m_point = pg.TargetItem(
                pos=(0, -100),
                size=14,
                symbol='+',
                movable=False,
                pen=pg.mkPen(self.marker_colors[i], width=2),
                brush=pg.mkBrush(self.marker_colors[i])
            )
            m_label = pg.TextItem(text=f"M{i+1}", color=self.marker_colors[i], anchor=(0.5, 1.3))
            m_point.setVisible(False)
            m_label.setVisible(False)
            self.plot_item.addItem(m_point, ignoreBounds=True)
            self.plot_item.addItem(m_label, ignoreBounds=True)
            # last_text caches the rendered label so we skip redundant, and
            # surprisingly costly, text re-layout on every frame.
            self.markers.append({
                "item": m_point, "label": m_label, "active": False,
                "freq": 0.0, "dbm": -100.0, "last_text": None,
            })

        # Threshold alarm line (hidden until enabled from the marker panel).
        self.alarm_line = pg.InfiniteLine(
            angle=0, movable=True,
            pen=pg.mkPen('#ef4444', width=1.5, style=Qt.DotLine),
            label='ALARM {value:0.1f} dBm',
            labelOpts={'color': '#ef4444', 'position': 0.05},
        )
        self.alarm_line.setPos(-20)
        self.alarm_line.setVisible(False)
        self.plot_item.addItem(self.alarm_line, ignoreBounds=True)
        self.alarm_line.sigPositionChangeFinished.connect(
            lambda line: self.alarm_level_changed.emit(float(line.value()))
        )

        # Channel-plan overlay (e.g. Wi-Fi channels for a preselected band).
        self._channel_items: list = []

        self.proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved, rateLimit=30, slot=self.on_mouse_moved
        )

    # -- channel plan overlay ----------------------------------------------

    def set_channel_plan(self, channels: list, span: tuple | None = None):
        """Draw labelled channel centres over the spectrum.

        ``channels`` is a list of ``{"label": str, "freq_hz": float}``. Passing
        an empty list clears the overlay. ``span`` optionally restricts drawing
        to (start_hz, stop_hz) so a plan wider than the sweep does not litter
        the edges of the view.
        """
        for item in self._channel_items:
            self.plot_item.removeItem(item)
        self._channel_items.clear()

        if not channels:
            return

        lo, hi = (span if span else (float("-inf"), float("inf")))
        for ch in channels:
            f = float(ch.get("freq_hz", 0.0))
            if not (lo <= f <= hi):
                continue
            line = pg.InfiniteLine(
                pos=f, angle=90, movable=False,
                pen=pg.mkPen("#3b82f6", width=1, style=Qt.DotLine),
                label=str(ch.get("label", "")),
                labelOpts={
                    "color": "#60a5fa", "position": 0.96,
                    "rotateAxis": (1, 0), "movable": False,
                },
            )
            # Channel guides must not participate in autoranging, or they drag
            # the view out to the widest channel in the plan.
            self.plot_item.addItem(line, ignoreBounds=True)
            self._channel_items.append(line)

    def clear_channel_plan(self):
        self.set_channel_plan([])

    # -- traces -------------------------------------------------------------

    def update_trace(self, trace_key: str, freqs: np.ndarray, dbm: np.ndarray):
        """Update x, y sweep data for a specific trace.

        Hidden curves are skipped: setData on an invisible curve still costs a
        full array copy and a bounds recalculation.
        """
        curve = self.traces.get(trace_key)
        if curve is None or not curve.isVisible():
            return
        if freqs is None or dbm is None or len(freqs) != len(dbm) or len(dbm) == 0:
            return
        curve.setData(freqs, dbm)

    def is_trace_visible(self, trace_key: str) -> bool:
        curve = self.traces.get(trace_key)
        return bool(curve is not None and curve.isVisible())

    def set_trace_visible(self, trace_key: str, visible: bool):
        """Show or hide a trace curve."""
        if trace_key in self.traces:
            self.traces[trace_key].setVisible(visible)
            if not visible:
                self.traces[trace_key].setData([], [])

    def set_trace_color(self, trace_key: str, color_hex: str):
        """Change color of a trace."""
        if trace_key in self.traces:
            pen = pg.mkPen(color=color_hex, width=self.trace_configs[trace_key]["width"])
            self.traces[trace_key].setPen(pen)
            self.trace_configs[trace_key]["color"] = color_hex

    def clear_all_traces(self):
        for curve in self.traces.values():
            curve.setData([], [])

    # -- axes ---------------------------------------------------------------

    def auto_scale_y(self, dbm_data: np.ndarray):
        """Auto fit Y range based on current signal min/max."""
        if dbm_data is None or len(dbm_data) == 0:
            return
        finite = dbm_data[np.isfinite(dbm_data)]
        if finite.size == 0:
            return
        min_y = float(np.min(finite)) - 10.0
        max_y = float(np.max(finite)) + 15.0
        if max_y - min_y < 20.0:
            max_y = min_y + 20.0
        self.plot_item.setYRange(max(-140.0, min_y), min(30.0, max_y), padding=0)

    def set_y_range(self, min_dbm: float, max_dbm: float):
        """Set explicit Y axis limits."""
        self.plot_item.setYRange(min_dbm, max_dbm, padding=0)

    def set_x_range(self, start_hz: float, stop_hz: float):
        if stop_hz > start_hz:
            self.plot_item.setXRange(start_hz, stop_hz, padding=0)

    # -- markers ------------------------------------------------------------

    def set_marker_pos(self, index: int, freq_hz: float, dbm: float, active: bool = True):
        """Set marker position and visibility."""
        if not (0 <= index < len(self.markers)):
            return
        m = self.markers[index]

        if not active:
            if m["active"]:
                m["item"].setVisible(False)
                m["label"].setVisible(False)
                m["active"] = False
            return

        if not m["active"]:
            m["item"].setVisible(True)
            m["label"].setVisible(True)
            m["active"] = True

        m["freq"] = freq_hz
        m["dbm"] = dbm
        m["item"].setPos(freq_hz, dbm)
        m["label"].setPos(freq_hz, dbm)

        text = f"M{index+1}: {format_frequency(freq_hz)}\n{dbm:.1f} dBm"
        if text != m["last_text"]:
            m["label"].setText(text)
            m["last_text"] = text

    # -- threshold alarm ----------------------------------------------------

    def set_alarm_enabled(self, enabled: bool):
        self.alarm_line.setVisible(bool(enabled))

    def set_alarm_level(self, dbm: float):
        self.alarm_line.setPos(float(dbm))

    def alarm_level(self) -> float:
        return float(self.alarm_line.value())

    # -- interaction --------------------------------------------------------

    def on_mouse_moved(self, evt):
        """Handle cursor crosshair movement over spectrum plot."""
        pos = evt[0]
        if not self.plot_widget.sceneBoundingRect().contains(pos):
            return
        mouse_point = self.plot_item.vb.mapSceneToView(pos)
        freq_hz = mouse_point.x()
        dbm = mouse_point.y()
        self.v_line.setPos(freq_hz)
        self.h_line.setPos(dbm)
        self.crosshair_label.setPos(freq_hz, dbm)
        self.crosshair_label.setText(f" {format_frequency(freq_hz)} | {dbm:.1f} dBm")
