"""
Hardware Sweep Controls & Serial Connection Control Panel.
Provides easy frequency tuning (Start, Stop, Center, Span), RBW, Attenuation,
LNA Preamp, Spur mode, Input selector, and COM Port Connection Manager.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QComboBox, QLineEdit, QCheckBox, QSpinBox, QFormLayout
)
from PySide6.QtCore import Signal
from tinysa_driver import TinySADriver
from utils.presets import format_frequency, parse_frequency_string


class ControlPanelWidget(QWidget):
    """Primary control panel for frequency tuning and TinySA hardware settings."""

    sweep_params_changed = Signal(float, float, int)  # (start_hz, stop_hz, points)
    hardware_setting_changed = Signal(str, object)   # (setting_name, value)
    connect_requested = Signal(str)                  # (port_name)
    disconnect_requested = Signal()
    pause_toggled = Signal(bool)                     # (paused)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        # -------------------------------------------------------------
        # 1. Connection & Hardware COM Port Box
        # -------------------------------------------------------------
        conn_box = QGroupBox("Hardware Connection (COM Port)")
        conn_layout = QVBoxLayout(conn_box)

        port_row = QHBoxLayout()
        self.combo_ports = QComboBox()
        self.combo_ports.setToolTip("Select TinySA Virtual COM Port (Connected: COM16)")
        port_row.addWidget(self.combo_ports, stretch=2)

        self.btn_refresh_ports = QPushButton("Refresh")
        self.btn_refresh_ports.setToolTip("Scan system for connected serial devices")
        self.btn_refresh_ports.clicked.connect(self.refresh_ports)
        port_row.addWidget(self.btn_refresh_ports)

        conn_layout.addLayout(port_row)

        btn_row = QHBoxLayout()
        self.btn_connect = QPushButton("Connect Device")
        self.btn_connect.setObjectName("accentButton")
        self.btn_connect.setToolTip("Establish serial connection to TinySA / TinySA Ultra")
        self.btn_connect.clicked.connect(self.on_connect_clicked)
        btn_row.addWidget(self.btn_connect)

        self.btn_demo_mode = QPushButton("Demo / Sim Mode")
        self.btn_demo_mode.setToolTip("Switch to offline simulated RF signal generator mode")
        self.btn_demo_mode.clicked.connect(lambda: self.connect_requested.emit("SIMULATION"))
        btn_row.addWidget(self.btn_demo_mode)

        conn_layout.addLayout(btn_row)

        self.btn_pause = QPushButton("Pause Sweeping")
        self.btn_pause.setCheckable(True)
        self.btn_pause.setToolTip("Freeze acquisition without disconnecting the device")
        self.btn_pause.toggled.connect(self.on_pause_toggled)
        conn_layout.addWidget(self.btn_pause)

        self.lbl_status = QLabel("Status: Disconnected")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: #94a3b8; font-weight: 600; font-size: 12px;")
        conn_layout.addWidget(self.lbl_status)

        layout.addWidget(conn_box)

        # -------------------------------------------------------------
        # 2. Frequency Range Tuning Box
        # -------------------------------------------------------------
        freq_box = QGroupBox("Frequency Range Tuning")
        freq_form = QFormLayout(freq_box)

        self.edit_start_freq = QLineEdit("2.400 GHz")
        self.edit_start_freq.setToolTip("Sweep Start Frequency (e.g., 2.4 GHz, 100 MHz, 433.92 MHz)")
        self.edit_start_freq.editingFinished.connect(self.on_start_stop_changed)
        freq_form.addRow("Start Frequency:", self.edit_start_freq)

        self.edit_stop_freq = QLineEdit("2.4835 GHz")
        self.edit_stop_freq.setToolTip("Sweep Stop Frequency (e.g., 2.4835 GHz, 500 MHz, 6 GHz)")
        self.edit_stop_freq.editingFinished.connect(self.on_start_stop_changed)
        freq_form.addRow("Stop Frequency:", self.edit_stop_freq)

        self.edit_center_freq = QLineEdit("2.44175 GHz")
        self.edit_center_freq.setToolTip("Center Frequency (e.g., 2.44175 GHz)")
        self.edit_center_freq.editingFinished.connect(self.on_center_span_changed)
        freq_form.addRow("Center Frequency:", self.edit_center_freq)

        self.edit_span_freq = QLineEdit("83.5 MHz")
        self.edit_span_freq.setToolTip("Frequency Span Width (e.g., 83.5 MHz, 10 MHz)")
        self.edit_span_freq.editingFinished.connect(self.on_center_span_changed)
        freq_form.addRow("Span Width:", self.edit_span_freq)

        self.spin_points = QSpinBox()
        self.spin_points.setRange(50, 450)
        self.spin_points.setValue(201)
        self.spin_points.setSingleStep(50)
        self.spin_points.setToolTip(
            "Number of frequency sweep data points.\n"
            "Hardware accepts 50-450; more points means a slower sweep "
            "(each point is ~20 bytes over a 115200 baud link)."
        )
        self.spin_points.valueChanged.connect(self.on_points_changed)
        freq_form.addRow("Sweep Points:", self.spin_points)

        self.btn_apply_freq = QPushButton("Apply Frequency Range")
        self.btn_apply_freq.setObjectName("accentButton")
        self.btn_apply_freq.setToolTip("Update TinySA hardware sweep range parameters")
        self.btn_apply_freq.clicked.connect(self.emit_sweep_params)
        freq_form.addRow(self.btn_apply_freq)

        layout.addWidget(freq_box)

        # -------------------------------------------------------------
        # 3. Hardware RF Parameters Box
        # -------------------------------------------------------------
        hw_box = QGroupBox("Hardware RF Settings")
        hw_form = QFormLayout(hw_box)

        self.combo_rbw = QComboBox()
        self.combo_rbw.addItems(["Auto", "3 kHz", "10 kHz", "30 kHz", "100 kHz", "300 kHz", "600 kHz"])
        self.combo_rbw.setToolTip("Resolution Bandwidth (RBW) filter selection")
        self.combo_rbw.currentTextChanged.connect(lambda txt: self.hardware_setting_changed.emit("rbw", txt))
        hw_form.addRow("RBW Filter:", self.combo_rbw)

        self.combo_atten = QComboBox()
        self.combo_atten.addItems(["Auto", "0 dB", "6 dB", "12 dB", "18 dB", "24 dB", "30 dB"])
        self.combo_atten.setToolTip("Input Attenuator level (prevents RF front-end overload)")
        self.combo_atten.currentTextChanged.connect(lambda txt: self.hardware_setting_changed.emit("atten", txt))
        hw_form.addRow("Attenuation:", self.combo_atten)

        self.combo_input = QComboBox()
        self.combo_input.addItems(["Low (100kHz - 800MHz)", "High (240MHz - 960MHz)", "Ultra (100kHz - 6GHz)"])
        self.combo_input.setToolTip("Active RF input port / ultra mode selector")
        self.combo_input.currentTextChanged.connect(lambda txt: self.hardware_setting_changed.emit("input", txt))
        hw_form.addRow("Active Input:", self.combo_input)

        self.chk_lna = QCheckBox("LNA Preamplifier (+20 dB)")
        self.chk_lna.setToolTip("Enable Low Noise Amplifier for ultra-weak signal reception")
        self.chk_lna.toggled.connect(lambda state: self.hardware_setting_changed.emit("lna", state))
        hw_form.addRow(self.chk_lna)

        self.chk_spur = QCheckBox("Spur Removal Mode")
        self.chk_spur.setChecked(True)
        self.chk_spur.setToolTip("Filters out internal mixer spurious responses")
        self.chk_spur.toggled.connect(lambda state: self.hardware_setting_changed.emit("spur", state))
        hw_form.addRow(self.chk_spur)

        layout.addWidget(hw_box)

        layout.addStretch()

        # Initial COM port enumeration
        self.refresh_ports()

    def refresh_ports(self):
        """Populate the available COM ports dropdown.

        ``TinySADriver.get_available_ports`` already sorts likely TinySA
        devices first, so the best candidate is index 0.
        """
        self.combo_ports.blockSignals(True)
        self.combo_ports.clear()

        selected_index = 0
        for i, p in enumerate(TinySADriver.get_available_ports()):
            text = f"{p['device']} - {p['description']}"
            if p['is_tinysa']:
                text += "  [TinySA detected]"
                if selected_index == 0:
                    selected_index = i
            self.combo_ports.addItem(text, userData=p['device'])

        self.combo_ports.addItem("SIMULATION MODE (no hardware)", userData="SIMULATION")
        if self.combo_ports.count() == 1:
            selected_index = 0
        self.combo_ports.setCurrentIndex(selected_index)
        self.combo_ports.blockSignals(False)

    def on_connect_clicked(self):
        """Handle connect/disconnect button click."""
        if self._connected:
            self.disconnect_requested.emit()
            return
        port = self.combo_ports.currentData()
        if port and port != "NONE":
            self.connect_requested.emit(port)

    def on_pause_toggled(self, paused: bool):
        self.btn_pause.setText("Resume Sweeping" if paused else "Pause Sweeping")
        self.pause_toggled.emit(bool(paused))

    def set_paused(self, paused: bool, notify: bool = False):
        """Reflect a pause state set from elsewhere (e.g. session playback).

        ``notify=True`` re-emits ``pause_toggled`` so the worker follows. The
        button is the only place the UI records pause state, so silently
        un-ticking it on disconnect left the worker paused forever: after
        reconnecting, the button read "Pause Sweeping" and not one sweep ever
        arrived again.
        """
        changed = self.btn_pause.isChecked() != bool(paused)
        if changed:
            self.btn_pause.blockSignals(True)
            self.btn_pause.setChecked(bool(paused))
            self.btn_pause.blockSignals(False)
        self.btn_pause.setText("Resume Sweeping" if paused else "Pause Sweeping")
        if notify and changed:
            self.pause_toggled.emit(bool(paused))

    def _restyle(self, widget, object_name: str):
        """Swap a widget's style selector and force a re-polish.

        Setting objectName alone does not re-evaluate the stylesheet; the widget
        has to be unpolished and polished again.
        """
        widget.setObjectName(object_name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def set_connection_state(self, connected: bool, message: str):
        """Update UI status based on the serial connection result."""
        self._connected = bool(connected)
        self.lbl_status.setText(f"Status: {message}")
        if connected:
            self.lbl_status.setStyleSheet("color: #00ff9d; font-weight: bold; font-size: 12px;")
            self.btn_connect.setText("Disconnect Device")
            self._restyle(self.btn_connect, "dangerButton")
        else:
            self.lbl_status.setStyleSheet("color: #ff3366; font-weight: bold; font-size: 12px;")
            self.btn_connect.setText("Connect Device")
            self._restyle(self.btn_connect, "accentButton")
            # Clear pause AND tell the worker, so a reconnect actually sweeps.
            self.set_paused(False, notify=True)

    def current_range(self) -> tuple:
        """Return the (start_hz, stop_hz, points) currently shown in the UI."""
        return (
            parse_frequency_string(self.edit_start_freq.text()),
            parse_frequency_string(self.edit_stop_freq.text()),
            self.spin_points.value(),
        )

    def set_frequency_range(self, start_hz: float, stop_hz: float, emit: bool = True):
        """Update the frequency UI fields programmatically."""
        for edit, value in (
            (self.edit_start_freq, start_hz),
            (self.edit_stop_freq, stop_hz),
            (self.edit_center_freq, (start_hz + stop_hz) / 2.0),
            (self.edit_span_freq, stop_hz - start_hz),
        ):
            edit.blockSignals(True)
            edit.setText(format_frequency(value))
            edit.blockSignals(False)

        if emit:
            self.emit_sweep_params()

    def on_start_stop_changed(self):
        """Re-calculate Center & Span when Start/Stop change."""
        start = parse_frequency_string(self.edit_start_freq.text())
        stop = parse_frequency_string(self.edit_stop_freq.text())
        if stop > start:
            center = (start + stop) / 2.0
            span = stop - start
            self.edit_center_freq.setText(format_frequency(center))
            self.edit_span_freq.setText(format_frequency(span))
            self.emit_sweep_params()

    def on_center_span_changed(self):
        """Re-calculate Start & Stop when Center/Span change."""
        center = parse_frequency_string(self.edit_center_freq.text())
        span = parse_frequency_string(self.edit_span_freq.text())
        start = max(100000.0, center - (span / 2.0))
        stop = center + (span / 2.0)
        self.edit_start_freq.setText(format_frequency(start))
        self.edit_stop_freq.setText(format_frequency(stop))
        self.emit_sweep_params()

    def on_points_changed(self):
        """Trigger update when sweep points change."""
        self.emit_sweep_params()

    def emit_sweep_params(self):
        """Validate and emit the sweep parameters."""
        start = parse_frequency_string(self.edit_start_freq.text())
        stop = parse_frequency_string(self.edit_stop_freq.text())
        pts = self.spin_points.value()

        if not (start > 0 and stop > start):
            self.lbl_status.setText(
                "Status: invalid frequency range - stop must be above start."
            )
            self.lbl_status.setStyleSheet("color: #ffcc00; font-weight: bold; font-size: 12px;")
            return

        self.sweep_params_changed.emit(start, stop, pts)
