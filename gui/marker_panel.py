"""
Multi-Marker & Peak Search Control Panel.
Provides table readouts for Markers 1-6, Peak Max/Min/Next search, Delta Mode,
Auto-Tracking, and the spectrum threshold alarm.
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget,
    QTableWidgetItem, QPushButton, QCheckBox, QHeaderView, QComboBox,
    QDoubleSpinBox, QLabel
)
from PySide6.QtCore import Signal, Qt
from utils.presets import format_frequency, format_frequency_fixed


class MarkerPanelWidget(QWidget):
    """Marker readout table and peak search management panel."""

    marker_updated = Signal(int, bool)          # (index, active)
    peak_search_requested = Signal(str)         # "max" | "min" | "next_left" | "next_right" | "next_peak"
    alarm_config_changed = Signal(bool, float)  # (enabled, threshold_dbm)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.auto_tracking = False
        self._alarm_style_state = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        # -------------------------------------------------------------
        # 1. Peak Search & Actions Box
        # -------------------------------------------------------------
        peak_box = QGroupBox("Peak Search & Marker Actions")
        peak_layout = QVBoxLayout(peak_box)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Apply search to:"))
        self.combo_target = QComboBox()
        self.combo_target.addItems([f"Marker {i + 1}" for i in range(6)])
        self.combo_target.setToolTip("Which marker the peak search buttons move")
        target_row.addWidget(self.combo_target)
        peak_layout.addLayout(target_row)

        btn_grid1 = QHBoxLayout()
        self.btn_peak_max = QPushButton("Peak Max")
        self.btn_peak_max.setObjectName("accentButton")
        self.btn_peak_max.setToolTip("Snap the target marker to the highest signal peak")
        self.btn_peak_max.clicked.connect(lambda: self.peak_search_requested.emit("max"))
        btn_grid1.addWidget(self.btn_peak_max)

        self.btn_peak_min = QPushButton("Peak Min")
        self.btn_peak_min.setToolTip("Snap the target marker to the lowest noise floor point")
        self.btn_peak_min.clicked.connect(lambda: self.peak_search_requested.emit("min"))
        btn_grid1.addWidget(self.btn_peak_min)

        peak_layout.addLayout(btn_grid1)

        btn_grid2 = QHBoxLayout()
        self.btn_next_left = QPushButton("< Next Left")
        self.btn_next_left.setToolTip("Move the target marker to the next local peak to the left")
        self.btn_next_left.clicked.connect(lambda: self.peak_search_requested.emit("next_left"))
        btn_grid2.addWidget(self.btn_next_left)

        self.btn_next_right = QPushButton("Next Right >")
        self.btn_next_right.setToolTip("Move the target marker to the next local peak to the right")
        self.btn_next_right.clicked.connect(lambda: self.peak_search_requested.emit("next_right"))
        btn_grid2.addWidget(self.btn_next_right)

        peak_layout.addLayout(btn_grid2)

        self.btn_next_peak = QPushButton("Next Highest Peak")
        self.btn_next_peak.setToolTip("Jump to the next strongest peak regardless of direction")
        self.btn_next_peak.clicked.connect(lambda: self.peak_search_requested.emit("next_peak"))
        peak_layout.addWidget(self.btn_next_peak)

        self.chk_auto_track = QCheckBox("Auto-Track Highest Signal Peak")
        self.chk_auto_track.setToolTip("Continuously follow the maximum signal peak with Marker 1")
        self.chk_auto_track.toggled.connect(self.on_auto_track_toggled)
        peak_layout.addWidget(self.chk_auto_track)

        self.chk_delta_mode = QCheckBox("Delta Marker Mode (Mn - M1)")
        self.chk_delta_mode.setToolTip("Show markers 2-6 relative to Marker 1")
        peak_layout.addWidget(self.chk_delta_mode)

        layout.addWidget(peak_box)

        # -------------------------------------------------------------
        # 2. Threshold Alarm Box
        # -------------------------------------------------------------
        alarm_box = QGroupBox("Signal Threshold Alarm")
        alarm_layout = QVBoxLayout(alarm_box)

        self.chk_alarm = QCheckBox("Enable threshold alarm line")
        self.chk_alarm.setToolTip("Warn in the status bar whenever the peak crosses the threshold")
        self.chk_alarm.toggled.connect(self._emit_alarm_config)
        alarm_layout.addWidget(self.chk_alarm)

        thr_row = QHBoxLayout()
        thr_row.addWidget(QLabel("Threshold:"))
        self.spin_alarm = QDoubleSpinBox()
        self.spin_alarm.setRange(-140.0, 30.0)
        self.spin_alarm.setValue(-20.0)
        self.spin_alarm.setSuffix(" dBm")
        self.spin_alarm.setToolTip("Alarm trips when the live peak exceeds this level")
        self.spin_alarm.valueChanged.connect(self._emit_alarm_config)
        thr_row.addWidget(self.spin_alarm)
        alarm_layout.addLayout(thr_row)

        self.lbl_alarm_state = QLabel("Alarm disabled")
        self.lbl_alarm_state.setStyleSheet("color: #64748b; font-size: 11px;")
        alarm_layout.addWidget(self.lbl_alarm_state)

        layout.addWidget(alarm_box)

        # -------------------------------------------------------------
        # 3. Markers Table Readout
        # -------------------------------------------------------------
        table_box = QGroupBox("Markers Readout (1 - 6)")
        table_layout = QVBoxLayout(table_box)

        self.table = QTableWidget(6, 4)
        self.table.setHorizontalHeaderLabels(["Marker", "Active", "Frequency", "Power (dBm)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)

        self._checkboxes = []
        for row in range(6):
            item_lbl = QTableWidgetItem(f"M{row+1}")
            item_lbl.setFlags(Qt.ItemIsEnabled)
            item_lbl.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_lbl)

            chk = QCheckBox()
            chk.setChecked(row == 0)  # Marker 1 on by default
            chk.toggled.connect(lambda state, r=row: self.marker_updated.emit(r, state))
            self.table.setCellWidget(row, 1, chk)
            self._checkboxes.append(chk)

            item_freq = QTableWidgetItem("---")
            item_freq.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 2, item_freq)

            item_pwr = QTableWidgetItem("---")
            item_pwr.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 3, item_pwr)

        table_layout.addWidget(self.table)
        layout.addWidget(table_box)
        layout.addStretch()

    # -- accessors ----------------------------------------------------------

    def target_marker_index(self) -> int:
        """Index of the marker that peak-search actions apply to."""
        return max(0, self.combo_target.currentIndex())

    def alarm_enabled(self) -> bool:
        return self.chk_alarm.isChecked()

    def alarm_threshold(self) -> float:
        return float(self.spin_alarm.value())

    def set_alarm_threshold(self, dbm: float):
        """Update the spin box without re-emitting a config change."""
        self.spin_alarm.blockSignals(True)
        self.spin_alarm.setValue(float(dbm))
        self.spin_alarm.blockSignals(False)

    def _emit_alarm_config(self, *_):
        enabled = self.chk_alarm.isChecked()
        if not enabled:
            self.lbl_alarm_state.setText("Alarm disabled")
            self.lbl_alarm_state.setStyleSheet("color: #64748b; font-size: 11px;")
        self.alarm_config_changed.emit(enabled, float(self.spin_alarm.value()))

    #: Cached alarm styling, so the sheet is only re-applied on a real change.
    _ALARM_STYLES = {
        True: "color: #ef4444; font-weight: bold; font-size: 11px;",
        False: "color: #00ff9d; font-size: 11px;",
    }

    def show_alarm_state(self, tripped: bool, peak_dbm: float):
        """Reflect the live alarm state in the panel.

        The stylesheet is only re-applied when the tripped state flips.
        Assigning it every frame forces a full style re-parse at render rate.
        """
        if not self.chk_alarm.isChecked():
            return
        tripped = bool(tripped)
        self.lbl_alarm_state.setText(
            f"ALARM: peak {peak_dbm:+.1f} dBm over threshold" if tripped
            else f"Armed - peak {peak_dbm:+.1f} dBm"
        )
        if tripped != self._alarm_style_state:
            self.lbl_alarm_state.setStyleSheet(self._ALARM_STYLES[tripped])
            self._alarm_style_state = tripped

    def on_auto_track_toggled(self, checked: bool):
        """Enable or disable auto peak tracking."""
        self.auto_tracking = checked

    def set_marker_active(self, index: int, active: bool):
        """Programmatically tick a marker's checkbox without signal feedback."""
        if 0 <= index < len(self._checkboxes):
            chk = self._checkboxes[index]
            chk.blockSignals(True)
            chk.setChecked(bool(active))
            chk.blockSignals(False)

    # -- readouts -----------------------------------------------------------

    def update_marker_readouts(self, marker_data_list: list):
        """
        Update table values from the marker list.
        marker_data_list = [{"active": True, "freq": hz, "dbm": dbm}, ...]

        Checkbox state is written with signals blocked. Previously this fired
        ``toggled`` back into the main window on every sweep, producing a
        signal loop at acquisition rate.
        """
        if not marker_data_list:
            return

        delta_enabled = self.chk_delta_mode.isChecked()
        ref_freq = marker_data_list[0].get("freq", 0.0)
        ref_dbm = marker_data_list[0].get("dbm", 0.0)

        for i, m in enumerate(marker_data_list):
            if i >= 6:
                break

            chk = self._checkboxes[i]
            if chk.isChecked() != bool(m["active"]):
                chk.blockSignals(True)
                chk.setChecked(bool(m["active"]))
                chk.blockSignals(False)

            item_f = self.table.item(i, 2)
            item_p = self.table.item(i, 3)

            if m["active"]:
                # Fixed formatting keeps every digit, so a marker parked on a
                # round frequency still reads at full resolution.
                if i > 0 and delta_enabled:
                    freq_text = f"Δ {format_frequency_fixed(m['freq'] - ref_freq, pad=False)}"
                    pwr_text = f"Δ {m['dbm'] - ref_dbm:+.2f} dB"
                else:
                    freq_text = format_frequency_fixed(m["freq"], pad=False)
                    pwr_text = f"{m['dbm']:+.2f} dBm"
            else:
                freq_text = pwr_text = "---"

            # Avoid needless item repaints.
            if item_f.text() != freq_text:
                item_f.setText(freq_text)
            if item_p.text() != pwr_text:
                item_p.setText(pwr_text)
