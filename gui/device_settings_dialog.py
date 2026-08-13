"""
TinySA Ultra Deep Hardware Options & Raw Serial Terminal Command Console Dialog.
Exposes the signal generator, hardware/battery diagnostics, and a live ASCII CLI.

Every command is dispatched to the acquisition thread and answered
asynchronously via ``TinySAWorker.command_result``. Nothing here touches the
serial port directly -- doing so from the GUI thread was what froze the window
whenever the device stopped responding.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QGroupBox, QFormLayout, QLineEdit, QDoubleSpinBox, QPushButton,
    QLabel, QTextEdit, QCheckBox, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt
from utils.presets import format_frequency, parse_frequency_string


class DeviceSettingsDialog(QDialog):
    """Deep TinySA Ultra hardware options and terminal console dialog."""

    def __init__(self, worker, parent=None):
        super().__init__(parent)
        self.worker = worker
        self.driver = worker.driver if worker is not None else None
        self.setWindowTitle("TinySA Ultra Hardware Options & Command Console")
        self.resize(700, 560)

        #: Commands issued from this dialog, so we only echo our own replies.
        self._pending: set[str] = set()
        #: Diagnostics queries awaiting an answer, mapped to their handler.
        self._diag_expect: dict[str, str] = {}

        layout = QVBoxLayout(self)

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        self.tab_sig_gen = QWidget()
        self.setup_sig_gen_tab()
        self.tab_widget.addTab(self.tab_sig_gen, "Signal Generator")

        self.tab_hw_info = QWidget()
        self.setup_hw_info_tab()
        self.tab_widget.addTab(self.tab_hw_info, "Hardware & Battery")

        self.tab_console = QWidget()
        self.setup_console_tab()
        self.tab_widget.addTab(self.tab_console, "Terminal CLI Console")

        btn_close = QPushButton("Close Settings")
        btn_close.setObjectName("accentButton")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        if self.worker is not None:
            self.worker.command_result.connect(self.on_command_result)
            # accept()/reject() do not raise closeEvent, so detach on finished
            # as well -- a stale connection would deliver replies to a dead
            # dialog and raise RuntimeError.
            self.finished.connect(lambda _code: self._detach())

        self.refresh_hw_info()

    def _detach(self):
        """Stop receiving worker replies."""
        if self.worker is None:
            return
        try:
            self.worker.command_result.disconnect(self.on_command_result)
        except (RuntimeError, TypeError):
            pass
        self.worker = None

    # -- signal generator ---------------------------------------------------

    def setup_sig_gen_tab(self):
        """Set up the RF signal generator controls."""
        layout = QVBoxLayout(self.tab_sig_gen)

        box = QGroupBox("TinySA Output RF Signal Generator")
        form = QFormLayout(box)

        self.edit_sig_freq = QLineEdit("433.92 MHz")
        self.edit_sig_freq.setToolTip("Signal generator frequency (e.g. 433.92 MHz, 2.4 GHz)")
        form.addRow("Output Frequency:", self.edit_sig_freq)

        self.spin_sig_power = QDoubleSpinBox()
        self.spin_sig_power.setRange(-76.0, 13.0)
        self.spin_sig_power.setValue(-10.0)
        self.spin_sig_power.setSuffix(" dBm")
        self.spin_sig_power.setToolTip("Output signal power level (-76 dBm to +13 dBm)")
        form.addRow("Power Level:", self.spin_sig_power)

        self.chk_sig_enable = QCheckBox("Enable Signal Generator Output")
        self.chk_sig_enable.setToolTip("Activate the RF CW output on the low port")
        form.addRow(self.chk_sig_enable)

        self.btn_apply_sig = QPushButton("Apply Signal Generator Settings")
        self.btn_apply_sig.setObjectName("accentButton")
        self.btn_apply_sig.clicked.connect(self.apply_sig_gen)
        form.addRow(self.btn_apply_sig)

        self.lbl_sig_state = QLabel("Generator idle.")
        self.lbl_sig_state.setWordWrap(True)
        self.lbl_sig_state.setStyleSheet("color: #94a3b8; font-size: 11px;")
        form.addRow(self.lbl_sig_state)

        warn = QLabel(
            "Note: switching to output mode takes the device out of "
            "spectrum-analyser mode, so sweeping stops until you disable the "
            "generator again."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #ffcc00; font-size: 11px;")
        form.addRow(warn)

        layout.addWidget(box)
        layout.addStretch()

    def apply_sig_gen(self):
        """Queue the signal generator command on the acquisition thread."""
        if self.worker is None:
            return
        freq_hz = parse_frequency_string(self.edit_sig_freq.text())
        if freq_hz <= 0:
            QMessageBox.warning(self, "Invalid Frequency",
                                "Enter a frequency such as '433.92 MHz'.")
            return
        pwr_dbm = self.spin_sig_power.value()
        enabled = self.chk_sig_enable.isChecked()

        self.worker.post_setting("siggen", (freq_hz, pwr_dbm, enabled))
        state = "ACTIVE" if enabled else "OFF"
        self.lbl_sig_state.setText(
            f"Requested: generator {state} at {format_frequency(freq_hz)} "
            f"({pwr_dbm:+.1f} dBm). Awaiting device reply..."
        )

    # -- hardware info ------------------------------------------------------

    def setup_hw_info_tab(self):
        """Set up the hardware version and battery status tab."""
        layout = QVBoxLayout(self.tab_hw_info)

        box = QGroupBox("TinySA Ultra Hardware Diagnostic Info")
        vbox = QVBoxLayout(box)

        self.lbl_hw_version = QLabel("Firmware Version: not queried")
        self.lbl_hw_version.setWordWrap(True)
        self.lbl_hw_version.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 13px;")
        vbox.addWidget(self.lbl_hw_version)

        self.lbl_battery = QLabel("Battery: not queried")
        self.lbl_battery.setWordWrap(True)
        self.lbl_battery.setStyleSheet("color: #00ff9d; font-weight: bold; font-size: 13px;")
        vbox.addWidget(self.lbl_battery)

        self.txt_hw_info = QTextEdit()
        self.txt_hw_info.setReadOnly(True)
        self.txt_hw_info.setMaximumHeight(180)
        self.txt_hw_info.setStyleSheet(
            "background-color: #05070a; color: #94a3b8;"
            "font-family: Consolas, 'Courier New', monospace; font-size: 11px;"
            "border: 1px solid #1e293b;"
        )
        vbox.addWidget(self.txt_hw_info)

        self.btn_query_hw = QPushButton("Refresh Hardware Diagnostics")
        self.btn_query_hw.clicked.connect(self.refresh_hw_info)
        vbox.addWidget(self.btn_query_hw)

        layout.addWidget(box)
        layout.addStretch()

    def refresh_hw_info(self):
        """Ask the acquisition thread for version, info and battery voltage."""
        if self.worker is None or self.driver is None:
            return
        if not self.driver.is_connected:
            self.lbl_hw_version.setText("Firmware Version: no device connected")
            self.lbl_battery.setText("Battery: no device connected")
            self.txt_hw_info.setPlainText(
                "Connect the TinySA, or switch to Simulation Mode, then refresh."
            )
            return

        self.lbl_hw_version.setText("Firmware Version: querying...")
        self.lbl_battery.setText("Battery: querying...")
        for cmd, slot in (("version", "version"), ("info", "info"), ("vbat", "vbat")):
            self._diag_expect[cmd] = slot
            self.worker.post_command(cmd)

    # -- console ------------------------------------------------------------

    def setup_console_tab(self):
        """Set up the raw serial ASCII terminal console."""
        layout = QVBoxLayout(self.tab_console)

        lbl = QLabel("Direct TinySA Serial ASCII Console:")
        lbl.setStyleSheet("color: #94a3b8; font-weight: bold;")
        layout.addWidget(lbl)

        self.txt_console = QTextEdit()
        self.txt_console.setReadOnly(True)
        self.txt_console.setStyleSheet("""
            background-color: #05070a;
            color: #00ff9d;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px;
            border: 1px solid #1e293b;
        """)
        layout.addWidget(self.txt_console)

        cmd_row = QHBoxLayout()
        self.edit_cmd = QLineEdit()
        self.edit_cmd.setPlaceholderText(
            "Type a command (version, info, vbat, rbw, attenuate, spur, help)..."
        )
        self.edit_cmd.returnPressed.connect(self.send_console_cmd)
        cmd_row.addWidget(self.edit_cmd)

        self.btn_send_cmd = QPushButton("Send")
        self.btn_send_cmd.clicked.connect(self.send_console_cmd)
        cmd_row.addWidget(self.btn_send_cmd)

        layout.addLayout(cmd_row)

        hint = QLabel(
            "Commands run on the acquisition thread; sweeping continues "
            "between them."
        )
        hint.setStyleSheet("color: #64748b; font-size: 10px;")
        layout.addWidget(hint)

    def send_console_cmd(self):
        """Queue a raw ASCII command for the device."""
        cmd = self.edit_cmd.text().strip()
        if not cmd:
            return

        self.txt_console.append(f"<span style='color:#00e5ff;'>&gt;&gt; {cmd}</span>")
        self.edit_cmd.clear()

        if self.worker is None or self.driver is None or not self.driver.is_connected:
            self.txt_console.append(
                "<span style='color:#ef4444;'>[not connected - connect the device "
                "or use Simulation Mode]</span>"
            )
            return

        self._pending.add(cmd)
        self.worker.post_command(cmd)

    # -- async replies ------------------------------------------------------

    def on_command_result(self, cmd: str, ok: bool, response: str):
        """Handle a reply that arrived from the acquisition thread."""
        # Diagnostics tab.
        slot = self._diag_expect.pop(cmd, None)
        if slot == "version":
            self.lbl_hw_version.setText(
                f"Firmware Version: {response.splitlines()[0] if (ok and response.strip()) else 'query failed'}"
            )
        elif slot == "info":
            self.txt_hw_info.setPlainText(response if ok and response.strip() else "info query failed")
        elif slot == "vbat":
            self.lbl_battery.setText(
                f"Battery: {response.strip() if ok and response.strip() else 'query failed'}"
            )

        # Signal generator acknowledgement.
        if cmd.startswith("siggen="):
            self.lbl_sig_state.setText(
                ("Generator command accepted.\n" if ok else "Generator command FAILED.\n")
                + (response or "").strip()
            )
            self.lbl_sig_state.setStyleSheet(
                f"color: {'#00ff9d' if ok else '#ef4444'}; font-size: 11px;"
            )

        # Console echo, for commands typed here.
        if cmd in self._pending:
            self._pending.discard(cmd)
            colour = "#00ff9d" if ok else "#ef4444"
            text = (response or "").strip() or ("[empty reply]" if ok else "[command failed]")
            safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            self.txt_console.append(
                f"<pre style='color:{colour}; margin:0;'>{safe}</pre>"
            )

    def closeEvent(self, event):
        """Detach from the worker so replies do not reach a dead dialog."""
        self._detach()
        super().closeEvent(event)
