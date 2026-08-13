"""
Trace Manager Panel for TinySA Ultra.
Provides controls for Trace 1 (Live), Trace 2 (Max Hold), Trace 3 (Min Hold),
Trace 4 (Average), Trace 5 (Math: A-B, A+B, Ref Store), color customizers, and reset buttons.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QLabel, QPushButton, QComboBox, QSpinBox, QColorDialog
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor


class TracePanelWidget(QWidget):
    """Trace management and mathematical operations panel."""

    trace_config_changed = Signal(str, dict)  # (trace_key, config_dict)
    clear_traces_requested = Signal()
    store_ref_requested = Signal()
    auto_scale_y_changed = Signal(bool)       # continuous Y auto-scaling
    y_range_changed = Signal(float, float)    # manual (min_dbm, max_dbm)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        # -------------------------------------------------------------
        # 1. Active Traces Toggle Box
        # -------------------------------------------------------------
        box_traces = QGroupBox("Trace Enable & Display Mode")
        layout_traces = QVBoxLayout(box_traces)

        # Trace 1 (Live)
        row1 = QHBoxLayout()
        self.chk_t1 = QCheckBox("Trace 1: Live Sweep (Cyan)")
        self.chk_t1.setChecked(True)
        self.chk_t1.toggled.connect(lambda state: self.trace_config_changed.emit("live", {"visible": state}))
        row1.addWidget(self.chk_t1)
        layout_traces.addLayout(row1)

        # Trace 2 (Max Hold)
        row2 = QHBoxLayout()
        self.chk_t2 = QCheckBox("Trace 2: Max Hold (Pink/Red)")
        self.chk_t2.setChecked(True)
        self.chk_t2.toggled.connect(lambda state: self.trace_config_changed.emit("max_hold", {"visible": state}))
        row2.addWidget(self.chk_t2)
        layout_traces.addLayout(row2)

        # Trace 3 (Min Hold)
        row3 = QHBoxLayout()
        self.chk_t3 = QCheckBox("Trace 3: Min Hold (Emerald)")
        self.chk_t3.setChecked(False)
        self.chk_t3.toggled.connect(lambda state: self.trace_config_changed.emit("min_hold", {"visible": state}))
        row3.addWidget(self.chk_t3)
        layout_traces.addLayout(row3)

        # Trace 4 (Average)
        row4 = QHBoxLayout()
        self.chk_t4 = QCheckBox("Trace 4: Averaging (Amber)")
        self.chk_t4.setChecked(False)
        self.chk_t4.toggled.connect(lambda state: self.trace_config_changed.emit("average", {"visible": state}))
        row4.addWidget(self.chk_t4)
        layout_traces.addLayout(row4)

        # Trace 5 (Math)
        row5 = QHBoxLayout()
        self.chk_t5 = QCheckBox("Trace 5: Trace Math (Purple)")
        self.chk_t5.setChecked(False)
        self.chk_t5.toggled.connect(lambda state: self.trace_config_changed.emit("math", {"visible": state}))
        row5.addWidget(self.chk_t5)
        layout_traces.addLayout(row5)

        layout.addWidget(box_traces)

        # -------------------------------------------------------------
        # 2. Averaging & Trace Math Settings Box
        # -------------------------------------------------------------
        box_math = QGroupBox("Averaging & Trace Math Options")
        layout_math = QVBoxLayout(box_math)

        avg_row = QHBoxLayout()
        avg_row.addWidget(QLabel("Avg Sweep Count:"))
        self.spin_avg_count = QSpinBox()
        self.spin_avg_count.setRange(2, 128)
        self.spin_avg_count.setValue(10)
        self.spin_avg_count.setToolTip("Exponential/moving average sweeps (2 to 128)")
        avg_row.addWidget(self.spin_avg_count)
        layout_math.addLayout(avg_row)

        math_op_row = QHBoxLayout()
        math_op_row.addWidget(QLabel("Math Operation:"))
        self.combo_math_op = QComboBox()
        self.combo_math_op.addItems(["T1 - T2 (Live - MaxHold)", "T1 - Ref (Live - Stored Ref)", "T1 + T2 (Sum)", "T2 - T3 (Max - Min Span)"])
        self.combo_math_op.setToolTip("Select mathematical trace computation mode")
        math_op_row.addWidget(self.combo_math_op)
        layout_math.addLayout(math_op_row)

        btn_math_row = QHBoxLayout()
        self.btn_store_ref = QPushButton("Store Reference Trace")
        self.btn_store_ref.setToolTip("Save current live trace as reference baseline")
        self.btn_store_ref.clicked.connect(lambda: self.store_ref_requested.emit())
        btn_math_row.addWidget(self.btn_store_ref)

        self.btn_clear_traces = QPushButton("Reset Max/Min Hold")
        self.btn_clear_traces.setToolTip("Clear all accumulated hold memory and restart averaging")
        self.btn_clear_traces.clicked.connect(lambda: self.clear_traces_requested.emit())
        btn_math_row.addWidget(self.btn_clear_traces)

        layout_math.addLayout(btn_math_row)
        layout.addWidget(box_math)

        # -------------------------------------------------------------
        # 3. Y Axis / Amplitude Scaling
        # -------------------------------------------------------------
        box_y = QGroupBox("Y Axis (Amplitude) Scaling")
        layout_y = QVBoxLayout(box_y)

        self.chk_auto_y = QCheckBox("Auto-scale Y axis continuously")
        self.chk_auto_y.setToolTip(
            "Keep the amplitude axis fitted to the live signal every sweep.\n"
            "Movement is eased and dead-banded so the axis does not jitter."
        )
        self.chk_auto_y.toggled.connect(self.on_auto_y_toggled)
        layout_y.addWidget(self.chk_auto_y)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("Top:"))
        self.spin_y_max = QSpinBox()
        self.spin_y_max.setRange(-100, 30)
        self.spin_y_max.setValue(15)
        self.spin_y_max.setSuffix(" dBm")
        self.spin_y_max.setToolTip("Reference level - top of the amplitude axis")
        self.spin_y_max.valueChanged.connect(self.on_manual_range_changed)
        range_row.addWidget(self.spin_y_max)

        range_row.addWidget(QLabel("Bottom:"))
        self.spin_y_min = QSpinBox()
        self.spin_y_min.setRange(-140, 0)
        self.spin_y_min.setValue(-130)
        self.spin_y_min.setSuffix(" dBm")
        self.spin_y_min.setToolTip("Bottom of the amplitude axis")
        self.spin_y_min.valueChanged.connect(self.on_manual_range_changed)
        range_row.addWidget(self.spin_y_min)

        layout_y.addLayout(range_row)
        layout.addWidget(box_y)

        layout.addStretch()

    def on_auto_y_toggled(self, enabled: bool):
        """Enable or disable continuous Y scaling."""
        # Manual limits are meaningless while the axis is being fitted.
        self.spin_y_min.setEnabled(not enabled)
        self.spin_y_max.setEnabled(not enabled)
        self.auto_scale_y_changed.emit(bool(enabled))

    def on_manual_range_changed(self):
        """Apply hand-set axis limits, guarding against an inverted range."""
        if self.chk_auto_y.isChecked():
            return
        lo = float(self.spin_y_min.value())
        hi = float(self.spin_y_max.value())
        if hi <= lo:
            hi = lo + 10.0
        self.y_range_changed.emit(lo, hi)

    def show_y_range(self, lo: float, hi: float):
        """Reflect an externally applied range without re-emitting."""
        for spin, val in ((self.spin_y_min, lo), (self.spin_y_max, hi)):
            spin.blockSignals(True)
            spin.setValue(int(round(val)))
            spin.blockSignals(False)
