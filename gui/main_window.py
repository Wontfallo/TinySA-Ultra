"""
Main Window for the TinySA Ultra Spectrum Analyzer Desktop Application.
Assembles docks, spectrum plot, waterfall, digital LCD readouts, toolbar, and
the hardware acquisition thread.

Rendering model
---------------
The acquisition thread never pushes frames into the GUI. It keeps only the most
recent sweep in a single slot, and this window pulls it on a fixed-rate timer.
The previous design emitted a Qt signal per sweep at up to 60/second while each
frame needed far longer than 16 ms to draw; the queued events accumulated
without bound and the window locked solid. A single-slot pull cannot back up:
if rendering falls behind, intermediate sweeps are dropped and counted.
"""

import os
import time

import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QDockWidget, QStatusBar, QToolBar, QLabel,
    QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence

from tinysa_driver import TinySADriver, TinySAWorker, SIMULATION_PORT
from styles.dark_theme import DARK_STYLESHEET
from gui.widgets.lcd_display import DigitalLCDDisplay
from gui.spectrum_plot import SpectrumPlotWidget
from gui.waterfall_widget import WaterfallWidget
from gui.control_panel import ControlPanelWidget
from gui.marker_panel import MarkerPanelWidget
from gui.trace_panel import TracePanelWidget
from gui.preset_panel import PresetPanelWidget
from gui.recorder_panel import RecorderPanelWidget
from gui.device_settings_dialog import DeviceSettingsDialog
from utils.presets import format_frequency, format_frequency_fixed, channel_plan_for


class MainWindow(QMainWindow):
    """Main application window for the TinySA Ultra Spectrum Analyzer."""

    #: Display refresh rate. Acquisition runs independently and may be faster
    #: (simulation) or much slower (a 450-point hardware scan over 115200 baud).
    RENDER_INTERVAL_MS = 33
    #: The marker table is comparatively expensive and unreadable at 30 Hz.
    MARKER_TABLE_INTERVAL_MS = 200
    #: A local maximum must stand this far above the median floor to count.
    PEAK_EXCURSION_DB = 4.0
    #: How fast continuous Y auto-scaling chases the signal (0..1 per frame).
    AUTO_Y_EASING = 0.12
    #: Axis movement smaller than this is not worth a redraw.
    AUTO_Y_DEADBAND_DB = 1.0

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TinySA Ultra Spectrum Analyzer - Pro Suite")
        self.resize(1600, 950)
        self.setStyleSheet(DARK_STYLESHEET)

        # Hardware driver plus the thread that exclusively owns it.
        self.driver = TinySADriver()
        self.worker = TinySAWorker(self.driver)

        # Trace accumulators
        self.max_hold_data = None
        self.min_hold_data = None
        self.avg_buffer = []
        self.stored_ref_data = None
        self.stored_ref_freqs = None

        # Latest rendered sweep, used by exports, peak search and autoscale.
        self.last_freqs = None
        self.last_dbm = None

        # Marker state: six independent markers.
        self.marker_data = [
            {"active": (i == 0), "freq": 2_441_750_000.0, "dbm": -100.0}
            for i in range(6)
        ]

        # Render statistics
        self._rendered_frames = 0
        self._render_window_start = time.monotonic()
        self._render_fps = 0.0
        self._dropped_frames = 0
        self._acq_rate = 0.0
        self._sweep_ms = 0.0
        self._playback_active = False
        self._alarm_tripped = False
        self._auto_scale_y = False
        self._auto_y_lo = None
        self._auto_y_hi = None
        #: Whether the pending connection attempt was user-initiated. Startup
        #: auto-detection must not raise a modal dialog.
        self._interactive_connect = False
        self._requested_port = None
        #: True when we are in simulation because hardware was missing, rather
        #: than because the user asked for it. Only then do we auto-reconnect.
        self._sim_is_fallback = False

        self.setup_ui()
        self.connect_signals()

        # Timers drive all display updates.
        self.render_timer = QTimer(self)
        self.render_timer.setInterval(self.RENDER_INTERVAL_MS)
        self.render_timer.timeout.connect(self.on_render_tick)

        self.marker_timer = QTimer(self)
        self.marker_timer.setInterval(self.MARKER_TABLE_INTERVAL_MS)
        self.marker_timer.timeout.connect(self.on_marker_table_tick)

        # Watch for the hardware appearing while we are running simulated,
        # so plugging the TinySA in just works instead of needing a manual
        # re-detect.
        self.hotplug_timer = QTimer(self)
        self.hotplug_timer.setInterval(4000)
        self.hotplug_timer.timeout.connect(self.on_hotplug_tick)

        self.worker.start()
        self.render_timer.start()
        self.marker_timer.start()
        self.hotplug_timer.start()

        # Push the initial range so the worker and the UI agree, then connect.
        start, stop, points = self.panel_controls.current_range()
        self.update_sweep_range(start, stop, points)
        QTimer.singleShot(150, self.auto_connect_startup)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def setup_ui(self):
        """Construct the application layout, visualizers and dock panels."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # Top LCD banner
        banner_layout = QHBoxLayout()
        banner_layout.setSpacing(10)

        self.lcd_peak_freq = DigitalLCDDisplay(
            "PEAK FREQUENCY", "waiting for data", accent_color="#00e5ff")
        banner_layout.addWidget(self.lcd_peak_freq)

        self.lcd_peak_power = DigitalLCDDisplay(
            "PEAK POWER", "waiting for data", accent_color="#ff3366")
        banner_layout.addWidget(self.lcd_peak_power)

        self.lcd_center_freq = DigitalLCDDisplay(
            "CENTER FREQ", "centre of span", accent_color="#00ff9d")
        banner_layout.addWidget(self.lcd_center_freq)

        self.lcd_span_width = DigitalLCDDisplay(
            "SPAN WIDTH", "sweep width", accent_color="#ffcc00")
        banner_layout.addWidget(self.lcd_span_width)

        self.lcd_fps = DigitalLCDDisplay(
            "SWEEP RATE", "sweeps / sec", accent_color="#bd93f9")
        banner_layout.addWidget(self.lcd_fps)

        main_layout.addLayout(banner_layout)

        # Spectrum plot over waterfall
        self.visual_splitter = QSplitter(Qt.Vertical)

        self.spectrum_plot = SpectrumPlotWidget()
        self.visual_splitter.addWidget(self.spectrum_plot)

        self.waterfall_widget = WaterfallWidget()
        self.visual_splitter.addWidget(self.waterfall_widget)

        self.visual_splitter.setStretchFactor(0, 3)
        self.visual_splitter.setStretchFactor(1, 2)
        main_layout.addWidget(self.visual_splitter)

        # Dockable control panels
        self.setDockNestingEnabled(True)

        self.dock_controls = QDockWidget("Sweep & Hardware Controls", self)
        self.panel_controls = ControlPanelWidget()
        self.dock_controls.setWidget(self.panel_controls)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_controls)

        self.dock_presets = QDockWidget("Frequency Presets", self)
        self.panel_presets = PresetPanelWidget()
        self.dock_presets.setWidget(self.panel_presets)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_presets)
        self.tabifyDockWidget(self.dock_controls, self.dock_presets)

        self.dock_markers = QDockWidget("Markers & Peak Search", self)
        self.panel_markers = MarkerPanelWidget()
        self.dock_markers.setWidget(self.panel_markers)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_markers)

        self.dock_traces = QDockWidget("Trace Manager & Math", self)
        self.panel_traces = TracePanelWidget()
        self.dock_traces.setWidget(self.panel_traces)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_traces)
        self.tabifyDockWidget(self.dock_markers, self.dock_traces)

        self.dock_recorder = QDockWidget("Data Recorder & Playback", self)
        self.panel_recorder = RecorderPanelWidget()
        self.dock_recorder.setWidget(self.panel_recorder)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_recorder)
        self.tabifyDockWidget(self.dock_traces, self.dock_recorder)

        self.dock_controls.raise_()
        self.dock_markers.raise_()

        # Let the preset panel read the live sweep range.
        self.panel_presets.current_range_provider = self._current_range_for_preset

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Connection state lives in a permanent widget. Transient
        # showMessage() text expires and leaves the bar blank, which would hide
        # the one thing the user always needs to know -- whether this is real
        # hardware or the simulator.
        self.lbl_conn = QLabel("Starting up...")
        self.lbl_conn.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.status_bar.addPermanentWidget(self.lbl_conn)

        self.lbl_perf = QLabel("")
        self.lbl_perf.setStyleSheet("color: #64748b; font-size: 11px;")
        self.status_bar.addPermanentWidget(self.lbl_perf)

        self.setup_menus_and_toolbars()

    def setup_menus_and_toolbars(self):
        """Build the main window menus and action toolbar."""
        menu_bar = self.menuBar()

        menu_file = menu_bar.addMenu("&File")

        act_snapshot = QAction("Save Plot Snapshot (PNG)", self)
        act_snapshot.setShortcut(QKeySequence("Ctrl+S"))
        act_snapshot.triggered.connect(self.save_plot_snapshot)
        menu_file.addAction(act_snapshot)

        act_export_csv = QAction("Export Sweep Data (CSV)", self)
        act_export_csv.triggered.connect(self.panel_recorder.export_csv_snapshot)
        menu_file.addAction(act_export_csv)

        menu_file.addSeparator()
        act_exit = QAction("Exit", self)
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        menu_view = menu_bar.addMenu("&View")
        for dock in (self.dock_controls, self.dock_presets, self.dock_markers,
                     self.dock_traces, self.dock_recorder):
            menu_view.addAction(dock.toggleViewAction())

        menu_hw = menu_bar.addMenu("&Hardware")
        act_hw_settings = QAction("TinySA Ultra Deep Options & Console...", self)
        act_hw_settings.setShortcut(QKeySequence("Ctrl+H"))
        act_hw_settings.triggered.connect(self.open_device_settings)
        menu_hw.addAction(act_hw_settings)

        act_autoscale = QAction("Auto Scale Spectrum Y-Axis", self)
        act_autoscale.setShortcut(QKeySequence("Ctrl+A"))
        act_autoscale.triggered.connect(self.on_autoscale_clicked)
        menu_hw.addAction(act_autoscale)

        menu_hw.addSeparator()
        act_sim = QAction("Switch to Simulation Mode", self)
        act_sim.triggered.connect(lambda: self.connect_hardware(SIMULATION_PORT))
        menu_hw.addAction(act_sim)

        act_reconnect = QAction("Re-detect && Reconnect TinySA", self)
        act_reconnect.setShortcut(QKeySequence("Ctrl+R"))
        act_reconnect.triggered.connect(self.redetect_and_connect)
        menu_hw.addAction(act_reconnect)

        toolbar = QToolBar("Quick Actions")
        self.addToolBar(toolbar)

        btn_auto = toolbar.addAction("Auto Scale Y")
        btn_auto.setToolTip("Fit the Y axis to the current spectrum once (Ctrl+A)")
        btn_auto.triggered.connect(self.on_autoscale_clicked)

        self.act_auto_y = QAction("Auto Y (continuous)", self)
        self.act_auto_y.setCheckable(True)
        self.act_auto_y.setToolTip("Keep the Y axis fitted to the signal every sweep")
        self.act_auto_y.toggled.connect(
            lambda on: self.panel_traces.chk_auto_y.setChecked(on)
        )
        toolbar.addAction(self.act_auto_y)
        # Keep the toolbar toggle and the panel checkbox in step, without
        # bouncing the signal back and forth.
        self.panel_traces.chk_auto_y.toggled.connect(
            lambda on: self.act_auto_y.setChecked(on)
        )

        btn_peak = toolbar.addAction("Peak Search")
        btn_peak.setToolTip("Find the maximum peak signal")
        btn_peak.triggered.connect(lambda: self.on_peak_search("max"))

        btn_reset_hold = toolbar.addAction("Reset Max Hold")
        btn_reset_hold.setToolTip("Clear the Max/Min hold accumulators")
        btn_reset_hold.triggered.connect(self.reset_hold_data)

        toolbar.addSeparator()

        btn_deep_opts = toolbar.addAction("TinySA Options")
        btn_deep_opts.setToolTip("Open hardware configuration and the terminal console")
        btn_deep_opts.triggered.connect(self.open_device_settings)

    def connect_signals(self):
        """Wire UI signals to the worker and to processing slots."""
        # Control panel
        self.panel_controls.connect_requested.connect(self.connect_hardware)
        self.panel_controls.disconnect_requested.connect(self.disconnect_hardware)
        self.panel_controls.sweep_params_changed.connect(self.update_sweep_range)
        self.panel_controls.hardware_setting_changed.connect(self.on_hardware_setting_changed)
        self.panel_controls.pause_toggled.connect(self.on_pause_toggled)

        # Worker
        self.worker.connection_changed.connect(self.on_connection_changed)
        self.worker.settings_read.connect(self.on_device_settings_read)
        self.worker.stats_updated.connect(self.on_stats_updated)
        self.worker.fault.connect(self.on_worker_fault)

        # Markers
        self.panel_markers.peak_search_requested.connect(self.on_peak_search)
        self.panel_markers.marker_updated.connect(self.on_marker_toggled_by_user)
        self.panel_markers.alarm_config_changed.connect(self.on_alarm_config_changed)
        self.spectrum_plot.alarm_level_changed.connect(self.on_alarm_line_dragged)

        # Traces
        self.panel_traces.trace_config_changed.connect(self.on_trace_config_changed)
        self.panel_traces.clear_traces_requested.connect(self.reset_hold_data)
        self.panel_traces.store_ref_requested.connect(self.store_reference_trace)
        self.panel_traces.auto_scale_y_changed.connect(self.on_auto_scale_y_changed)
        self.panel_traces.y_range_changed.connect(self.on_manual_y_range)

        # Presets
        self.panel_presets.preset_selected.connect(self.on_preset_selected)

        # Recorder / playback
        self.panel_recorder.snapshot_requested.connect(self.save_plot_snapshot)
        self.panel_recorder.playback_sweep_emitted.connect(self.on_playback_frame)
        self.panel_recorder.playback_state_changed.connect(self.on_playback_state_changed)

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    def auto_connect_startup(self):
        """Find a TinySA automatically, falling back to simulation.

        Startup never raises a modal dialog: if the probe fails we drop straight
        into simulation so the window is immediately usable, and explain what
        happened in the status bar.
        """
        port = TinySADriver.autodetect_port()
        if port:
            self.status_bar.showMessage(f"TinySA detected on {port}, connecting...")
            self.connect_hardware(port, interactive=False)
        else:
            self.status_bar.showMessage(
                "No TinySA detected - running simulated. Plug the device in and "
                "it will be picked up automatically."
            )
            self._sim_is_fallback = True
            self.connect_hardware(SIMULATION_PORT, interactive=False)

    def on_hotplug_tick(self):
        """Adopt the TinySA if it shows up while we are running simulated.

        Only when simulation was a fallback: if the user deliberately chose
        Demo mode, silently yanking them onto hardware would be wrong.
        """
        if not (self.driver.is_simulation and self._sim_is_fallback):
            return
        if self._playback_active:
            return
        port = TinySADriver.autodetect_port()
        if not port:
            return
        self.status_bar.showMessage(
            f"TinySA detected on {port} - switching from simulation...", 6000
        )
        self.connect_hardware(port, interactive=False)

    def redetect_and_connect(self):
        """Re-scan the serial bus and reconnect to whatever is found."""
        self.panel_controls.refresh_ports()
        port = TinySADriver.autodetect_port()
        if port:
            self.connect_hardware(port, interactive=True)
        else:
            QMessageBox.information(
                self, "No TinySA Found",
                "No TinySA was detected on any serial port.\n\n"
                "Check that the device is plugged in and powered on, then try "
                "again. Staying in the current mode for now."
            )

    def connect_hardware(self, port_name: str, interactive: bool = True):
        """Request a connection. Runs on the acquisition thread, never here.

        Opening a port and probing a device can block for seconds; doing that in
        this method was one of the two causes of the startup freeze.

        ``interactive`` controls the failure path: a connection the user asked
        for explicitly gets an explanatory dialog, while automatic startup
        detection falls back to simulation silently.
        """
        label = "Simulation Mode" if port_name == SIMULATION_PORT else port_name
        self._interactive_connect = bool(interactive)
        self._requested_port = port_name
        if port_name == SIMULATION_PORT and interactive:
            # An explicit Demo-mode choice: do not hijack it on hotplug.
            self._sim_is_fallback = False
        elif port_name != SIMULATION_PORT:
            self._sim_is_fallback = False
        self.status_bar.showMessage(f"Connecting to {label}...")
        self.panel_controls.set_connection_state(False, f"Connecting to {label}...")
        self.worker.post_connect(port_name)

    def disconnect_hardware(self):
        """Request a disconnect."""
        self.worker.post_disconnect()

    def on_connection_changed(self, connected: bool, message: str):
        """Handle the acquisition thread's connection result."""
        self.panel_controls.set_connection_state(connected, message)
        self.status_bar.showMessage(message, 8000)
        self._set_connection_label(connected, message)
        self.reset_hold_data()

        if connected:
            # Never come up paused. Pause is a transient user action, and a
            # stale paused worker after a reconnect means no data ever arrives.
            if not self._playback_active:
                self.worker.set_paused(False)
                self.panel_controls.set_paused(False)

            sim = self.driver.is_simulation
            self.setWindowTitle(
                "TinySA Ultra Spectrum Analyzer - Pro Suite - "
                + ("SIMULATION MODE (no hardware)" if sim
                   else f"{self.driver.port_name} ({self.driver.device_version})")
            )
            return

        self.setWindowTitle("TinySA Ultra Spectrum Analyzer - Pro Suite - disconnected")

        # Nothing to explain if the user asked to disconnect.
        if self._requested_port in (None, "", SIMULATION_PORT):
            return
        if "disconnected" in message.lower():
            return

        if self._interactive_connect:
            # The user chose this port, so tell them exactly what went wrong.
            self._offer_simulation_fallback(message)
        else:
            # Automatic startup detection: never block the window with a modal,
            # just fall back so there is something on screen.
            self.status_bar.showMessage(
                f"{message}  ->  falling back to Simulation Mode.", 0
            )
            self._sim_is_fallback = True
            self.connect_hardware(SIMULATION_PORT, interactive=False)

    def _offer_simulation_fallback(self, message: str):
        """Explain a failed connection and offer to run simulated instead."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("TinySA Not Responding")
        box.setText("Could not talk to the TinySA hardware.")
        box.setInformativeText(
            f"{message}\n\n"
            "If the port exists but the device never answers, its USB link has "
            "wedged: unplug the TinySA, wait a few seconds, plug it back in, "
            "then use Hardware > Re-detect & Reconnect.\n\n"
            "Run in Simulation Mode meanwhile?"
        )
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.Yes)
        if box.exec() == QMessageBox.Yes:
            self.connect_hardware(SIMULATION_PORT)

    def _set_connection_label(self, connected: bool, message: str):
        """Keep a permanent, never-expiring summary of the connection state."""
        if not connected:
            text, colour = "DISCONNECTED", "#ff3366"
        elif self.driver.is_simulation:
            text, colour = "SIMULATION MODE - no hardware attached", "#ffcc00"
        else:
            text = f"CONNECTED  {self.driver.port_name}  {self.driver.device_version}"
            colour = "#00ff9d"
        self.lbl_conn.setText(text)
        self.lbl_conn.setStyleSheet(
            f"color: {colour}; font-size: 11px; font-weight: 600;"
        )

    def on_device_settings_read(self, settings: dict):
        """Show the device's real RF settings in the control panel."""
        if not settings:
            return

        rbw = settings.get("rbw")
        if rbw:
            combo = self.panel_controls.combo_rbw
            wanted = str(rbw).strip().lower()
            for i in range(combo.count()):
                entry = combo.itemText(i).split()[0].lower()
                if entry == wanted or (wanted == "auto" and entry == "auto"):
                    combo.blockSignals(True)      # reflect, never re-send
                    combo.setCurrentIndex(i)
                    combo.blockSignals(False)
                    break

        bits = []
        if rbw:
            bits.append(f"RBW {rbw}" + ("" if str(rbw).lower() == "auto" else " kHz"))
        if settings.get("vbat"):
            bits.append(f"battery {settings['vbat']}")
        if bits:
            self.status_bar.showMessage(
                f"{self.driver.device_version}  -  " + ", ".join(bits), 8000
            )

    def on_worker_fault(self, description: str):
        """Surface a transport fault without interrupting the user."""
        self.status_bar.showMessage(f"Acquisition fault: {description}", 5000)

    def on_hardware_setting_changed(self, name: str, val):
        """Forward a hardware setting change to the acquisition thread."""
        if name in ("rbw", "atten", "input"):
            self.worker.post_setting(name, str(val).split()[0].lower())
        elif name in ("lna", "spur"):
            self.worker.post_setting(name, bool(val))

    def on_pause_toggled(self, paused: bool):
        self.worker.set_paused(paused)
        self.status_bar.showMessage(
            "Acquisition paused." if paused else "Acquisition resumed.", 3000
        )

    # ------------------------------------------------------------------
    # Sweep range
    # ------------------------------------------------------------------

    def update_sweep_range(self, start_hz: float, stop_hz: float, points: int):
        """Apply a new sweep range to the worker and the display."""
        self.reset_hold_data()
        self.worker.set_sweep_range(start_hz, stop_hz, points)

        start, stop, _ = self.worker.sweep_range()
        self.lcd_center_freq.set_frequency((start + stop) / 2.0)
        self.lcd_span_width.set_frequency(stop - start)
        self.spectrum_plot.set_x_range(start, stop)

    def _current_range_for_preset(self):
        start, stop, _ = self.worker.sweep_range()
        return start, stop

    def on_preset_selected(self, start_hz: float, stop_hz: float, name: str):
        """Apply a preset band and overlay its channel plan, if it has one."""
        self.panel_controls.set_frequency_range(start_hz, stop_hz)

        plan = channel_plan_for(name)
        self.spectrum_plot.set_channel_plan(plan, span=(start_hz, stop_hz))

        if plan:
            shown = sum(1 for c in plan if start_hz <= c["freq_hz"] <= stop_hz)
            self.status_bar.showMessage(
                f"Applied preset: {name}  -  {shown} channel markers shown", 5000
            )
        else:
            self.status_bar.showMessage(f"Applied preset: {name}", 4000)

    # ------------------------------------------------------------------
    # Render loop
    # ------------------------------------------------------------------

    def on_render_tick(self):
        """Pull the newest sweep, if any, and draw it."""
        if self._playback_active:
            return
        frame = self.worker.take_frame()
        if frame is None:
            return
        self.process_sweep(frame.freqs, frame.dbm)

    def on_playback_frame(self, freqs: np.ndarray, dbm: np.ndarray):
        """Render a frame coming from recorded-session playback."""
        self.process_sweep(freqs, dbm, record=False)

    def on_playback_state_changed(self, playing: bool):
        """Suspend live acquisition while a session is replaying."""
        self._playback_active = bool(playing)
        self.worker.set_paused(bool(playing))
        self.panel_controls.set_paused(bool(playing))
        self.status_bar.showMessage(
            "Replaying recorded session - live acquisition paused."
            if playing else "Replay stopped - live acquisition resumed.",
            4000,
        )

    def process_sweep(self, freqs: np.ndarray, dbm: np.ndarray, record: bool = True):
        """Update every visualizer from one sweep.

        Only visible traces are computed: the hidden ones cost a full array
        operation plus a pyqtgraph bounds recalculation for nothing.
        """
        if freqs is None or dbm is None or len(dbm) == 0 or len(freqs) != len(dbm):
            return

        self.last_freqs = freqs
        self.last_dbm = dbm

        plot = self.spectrum_plot
        plot.update_trace("live", freqs, dbm)

        # Max / Min hold accumulators. These are kept even when their traces are
        # hidden, because trace math and "reset hold" depend on them.
        if self.max_hold_data is None or len(self.max_hold_data) != len(dbm):
            self.max_hold_data = np.array(dbm, dtype=float, copy=True)
        else:
            np.maximum(self.max_hold_data, dbm, out=self.max_hold_data)
        plot.update_trace("max_hold", freqs, self.max_hold_data)

        if self.min_hold_data is None or len(self.min_hold_data) != len(dbm):
            self.min_hold_data = np.array(dbm, dtype=float, copy=True)
        else:
            np.minimum(self.min_hold_data, dbm, out=self.min_hold_data)
        plot.update_trace("min_hold", freqs, self.min_hold_data)

        # Averaging
        if plot.is_trace_visible("average"):
            depth = max(2, self.panel_traces.spin_avg_count.value())
            if self.avg_buffer and len(self.avg_buffer[0]) != len(dbm):
                self.avg_buffer.clear()
            self.avg_buffer.append(dbm)
            while len(self.avg_buffer) > depth:
                self.avg_buffer.pop(0)
            plot.update_trace("average", freqs, np.mean(self.avg_buffer, axis=0))
        elif self.avg_buffer:
            self.avg_buffer.clear()

        # Trace math
        if plot.is_trace_visible("math"):
            math_data = self._compute_trace_math(dbm)
            if math_data is not None:
                plot.update_trace("math", freqs, math_data)

        self.waterfall_widget.add_sweep(freqs, dbm)

        if record:
            self.panel_recorder.update_latest_sweep(freqs, dbm)

        # Peak readouts
        max_idx = int(np.argmax(dbm))
        peak_freq = float(freqs[max_idx])
        peak_dbm = float(dbm[max_idx])
        self.lcd_peak_freq.set_frequency(peak_freq)
        self.lcd_peak_power.set_power(peak_dbm)

        if self.panel_markers.auto_tracking:
            self.marker_data[0].update({"freq": peak_freq, "dbm": peak_dbm, "active": True})

        if self._auto_scale_y:
            self._tick_auto_scale_y(dbm)

        self._update_plot_markers(freqs, dbm)
        self._check_alarm(peak_dbm)
        self._tick_render_stats()

    def _compute_trace_math(self, dbm: np.ndarray):
        """Evaluate the selected trace-math expression, or None if unavailable."""
        op = self.panel_traces.combo_math_op.currentText()
        n = len(dbm)

        def usable(arr):
            return arr is not None and len(arr) == n

        if "T1 - T2" in op:
            return dbm - self.max_hold_data if usable(self.max_hold_data) else None
        if "T1 - Ref" in op:
            if usable(self.stored_ref_data):
                return dbm - self.stored_ref_data
            # Be explicit rather than silently plotting a different expression.
            self.status_bar.showMessage(
                "Trace math needs a stored reference - use 'Store Reference Trace'.",
                4000,
            )
            return None
        if "T1 + T2" in op:
            return dbm + self.max_hold_data if usable(self.max_hold_data) else None
        if usable(self.max_hold_data) and usable(self.min_hold_data):
            return self.max_hold_data - self.min_hold_data
        return None

    def _update_plot_markers(self, freqs: np.ndarray, dbm: np.ndarray):
        """Snap every active marker to the nearest bin and redraw it."""
        for i, m in enumerate(self.marker_data):
            if not m["active"]:
                self.spectrum_plot.set_marker_pos(i, 0.0, -100.0, False)
                continue
            idx = int(np.abs(freqs - m["freq"]).argmin())
            m["freq"] = float(freqs[idx])
            m["dbm"] = float(dbm[idx])
            self.spectrum_plot.set_marker_pos(i, m["freq"], m["dbm"], True)

    def on_marker_table_tick(self):
        """Refresh the marker table at its own, slower cadence."""
        if self.last_dbm is None:
            return
        self.panel_markers.update_marker_readouts(self.marker_data)

    def _tick_render_stats(self):
        """Maintain the rendered-frames-per-second figure."""
        self._rendered_frames += 1
        now = time.monotonic()
        elapsed = now - self._render_window_start
        if elapsed >= 1.0:
            self._render_fps = self._rendered_frames / elapsed
            self._rendered_frames = 0
            self._render_window_start = now
            self._refresh_perf_label()

    def on_stats_updated(self, sweeps_per_sec: float, sweep_ms: float, dropped: int):
        """Receive acquisition statistics from the worker (about 2 Hz)."""
        self._acq_rate = sweeps_per_sec
        self._sweep_ms = sweep_ms
        self._dropped_frames = dropped
        self.lcd_fps.set_value(f"{sweeps_per_sec:.1f}", "sweeps / sec")
        self._refresh_perf_label()

    def _refresh_perf_label(self):
        mode = "SIM" if self.driver.is_simulation else "HW"
        self.lbl_perf.setText(
            f"{mode} | acq {self._acq_rate:.1f}/s ({self._sweep_ms:.0f} ms) | "
            f"draw {self._render_fps:.0f} fps | dropped {self._dropped_frames}"
        )

    # ------------------------------------------------------------------
    # Traces
    # ------------------------------------------------------------------

    def reset_hold_data(self):
        """Clear Max/Min hold and averaging memory."""
        self.max_hold_data = None
        self.min_hold_data = None
        self.avg_buffer = []

    def store_reference_trace(self):
        """Store the current live trace as the math reference."""
        if self.last_dbm is None:
            QMessageBox.warning(
                self, "No Data",
                "There is no live sweep yet. Connect the TinySA or switch to "
                "Simulation Mode first."
            )
            return
        self.stored_ref_data = np.array(self.last_dbm, dtype=float, copy=True)
        self.stored_ref_freqs = np.array(self.last_freqs, dtype=float, copy=True)
        QMessageBox.information(
            self, "Reference Stored",
            f"Stored {len(self.stored_ref_data)} points as the reference baseline."
        )

    def on_trace_config_changed(self, trace_key: str, cfg: dict):
        """Handle a trace visibility change."""
        if "visible" in cfg:
            self.spectrum_plot.set_trace_visible(trace_key, cfg["visible"])

    # ------------------------------------------------------------------
    # Peak search
    # ------------------------------------------------------------------

    def _local_peak_indices(self, dbm: np.ndarray) -> np.ndarray:
        """Indices of local maxima that rise clearly above the noise floor."""
        if dbm is None or len(dbm) < 3:
            return np.empty(0, dtype=int)
        interior = dbm[1:-1]
        candidates = np.where((interior > dbm[:-2]) & (interior >= dbm[2:]))[0] + 1
        if candidates.size == 0:
            return candidates
        threshold = float(np.median(dbm)) + self.PEAK_EXCURSION_DB
        return candidates[dbm[candidates] >= threshold]

    def on_peak_search(self, mode: str):
        """Move the targeted marker according to the requested search."""
        if self.last_dbm is None or self.last_freqs is None:
            self.status_bar.showMessage("No sweep data to search yet.", 3000)
            return

        freqs, dbm = self.last_freqs, self.last_dbm
        target = self.panel_markers.target_marker_index()
        current_freq = self.marker_data[target]["freq"]
        current_idx = int(np.abs(freqs - current_freq).argmin())

        idx = None
        if mode == "max":
            idx = int(np.argmax(dbm))
        elif mode == "min":
            idx = int(np.argmin(dbm))
        else:
            peaks = self._local_peak_indices(dbm)
            if peaks.size == 0:
                self.status_bar.showMessage(
                    "No distinct peaks stand above the noise floor.", 3000)
                return

            if mode == "next_left":
                left = peaks[peaks < current_idx]
                if left.size == 0:
                    self.status_bar.showMessage("No further peak to the left.", 3000)
                    return
                idx = int(left[-1])
            elif mode == "next_right":
                right = peaks[peaks > current_idx]
                if right.size == 0:
                    self.status_bar.showMessage("No further peak to the right.", 3000)
                    return
                idx = int(right[0])
            elif mode == "next_peak":
                # The strongest peak strictly weaker than where we are now,
                # so repeated presses walk down the peak list.
                current_level = dbm[current_idx]
                weaker = peaks[dbm[peaks] < current_level]
                idx = int(weaker[np.argmax(dbm[weaker])]) if weaker.size else int(
                    peaks[np.argmax(dbm[peaks])]
                )
            else:
                idx = int(np.argmax(dbm))

        self.marker_data[target].update({
            "freq": float(freqs[idx]),
            "dbm": float(dbm[idx]),
            "active": True,
        })
        self.panel_markers.set_marker_active(target, True)
        self.panel_markers.update_marker_readouts(self.marker_data)
        self.status_bar.showMessage(
            f"Marker {target + 1} -> {format_frequency(freqs[idx])} "
            f"at {dbm[idx]:+.2f} dBm",
            4000,
        )

    def on_marker_toggled_by_user(self, index: int, active: bool):
        """Handle the user ticking a marker on or off."""
        if 0 <= index < len(self.marker_data):
            self.marker_data[index]["active"] = bool(active)
            if active and self.last_freqs is not None:
                # Place a newly enabled marker somewhere useful.
                if not (self.last_freqs[0] <= self.marker_data[index]["freq"] <= self.last_freqs[-1]):
                    self.marker_data[index]["freq"] = float(np.median(self.last_freqs))

    # ------------------------------------------------------------------
    # Threshold alarm
    # ------------------------------------------------------------------

    def on_alarm_config_changed(self, enabled: bool, threshold_dbm: float):
        self.spectrum_plot.set_alarm_enabled(enabled)
        self.spectrum_plot.set_alarm_level(threshold_dbm)
        self._alarm_tripped = False

    def on_alarm_line_dragged(self, level_dbm: float):
        """Keep the spin box in step when the line is dragged on the plot."""
        self.panel_markers.set_alarm_threshold(level_dbm)

    def _check_alarm(self, peak_dbm: float):
        """Compare the live peak against the threshold."""
        if not self.panel_markers.alarm_enabled():
            self._alarm_tripped = False
            return
        threshold = self.spectrum_plot.alarm_level()
        tripped = peak_dbm >= threshold
        self.panel_markers.show_alarm_state(tripped, peak_dbm)
        if tripped and not self._alarm_tripped:
            self.status_bar.showMessage(
                f"THRESHOLD ALARM: peak {peak_dbm:+.2f} dBm crossed "
                f"{threshold:+.1f} dBm", 5000
            )
        self._alarm_tripped = tripped

    # ------------------------------------------------------------------
    # Misc actions
    # ------------------------------------------------------------------

    def on_autoscale_clicked(self):
        """One-shot: fit the plot Y axis to the current sweep."""
        if self.last_dbm is None:
            self.status_bar.showMessage("No sweep data to scale to yet.", 3000)
            return
        self.spectrum_plot.auto_scale_y(self.last_dbm)
        lo, hi = self.spectrum_plot.plot_item.vb.viewRange()[1]
        self._auto_y_lo, self._auto_y_hi = lo, hi
        self.panel_traces.show_y_range(lo, hi)

    def on_auto_scale_y_changed(self, enabled: bool):
        """Turn continuous Y auto-scaling on or off."""
        self._auto_scale_y = bool(enabled)
        if enabled:
            # Seed from the current view so the first eased step is small.
            lo, hi = self.spectrum_plot.plot_item.vb.viewRange()[1]
            self._auto_y_lo, self._auto_y_hi = lo, hi
            self.status_bar.showMessage("Y axis auto-scaling enabled.", 3000)
        else:
            self.status_bar.showMessage("Y axis auto-scaling disabled.", 3000)

    def on_manual_y_range(self, lo: float, hi: float):
        """Apply hand-set Y limits."""
        self.spectrum_plot.set_y_range(lo, hi)
        self._auto_y_lo, self._auto_y_hi = lo, hi

    def _tick_auto_scale_y(self, dbm: np.ndarray):
        """Ease the Y axis toward a fit of the live signal.

        Snapping straight to min/max every sweep would make the axis twitch
        continuously -- the same jitter the readouts had. So the target is
        eased, and it is only committed once it has drifted past a dead band.
        """
        finite = dbm[np.isfinite(dbm)]
        if finite.size == 0:
            return

        # 1st percentile rather than the minimum, so a single dropout does not
        # drag the floor down; headroom above the peak keeps it off the ceiling.
        target_lo = float(np.percentile(finite, 1.0)) - 8.0
        target_hi = float(np.max(finite)) + 12.0
        if target_hi - target_lo < 20.0:
            target_hi = target_lo + 20.0
        target_lo = max(target_lo, -140.0)
        target_hi = min(target_hi, 30.0)

        if self._auto_y_lo is None or self._auto_y_hi is None:
            self._auto_y_lo, self._auto_y_hi = target_lo, target_hi
        else:
            self._auto_y_lo += (target_lo - self._auto_y_lo) * self.AUTO_Y_EASING
            self._auto_y_hi += (target_hi - self._auto_y_hi) * self.AUTO_Y_EASING

        cur_lo, cur_hi = self.spectrum_plot.plot_item.vb.viewRange()[1]
        if (abs(cur_lo - self._auto_y_lo) > self.AUTO_Y_DEADBAND_DB
                or abs(cur_hi - self._auto_y_hi) > self.AUTO_Y_DEADBAND_DB):
            self.spectrum_plot.set_y_range(self._auto_y_lo, self._auto_y_hi)
            self.panel_traces.show_y_range(self._auto_y_lo, self._auto_y_hi)

    def save_plot_snapshot(self):
        """Export a PNG screenshot of the current plot."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Spectrum Plot Snapshot",
            "tinysa_spectrum_plot.png", "PNG Image (*.png)"
        )
        if not filepath:
            return
        pixmap = self.spectrum_plot.grab()
        if pixmap.save(filepath, "PNG"):
            QMessageBox.information(
                self, "Snapshot Saved",
                f"Saved plot snapshot to {os.path.basename(filepath)}"
            )
        else:
            QMessageBox.critical(
                self, "Snapshot Failed",
                f"Could not write the image to {filepath}."
            )

    def open_device_settings(self):
        """Open the TinySA hardware options dialog."""
        dlg = DeviceSettingsDialog(self.worker, self)
        # Parented to the window, so without this each open/close cycle leaves
        # a hidden dialog alive for the lifetime of the app.
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.exec()
        dlg.deleteLater()

    def closeEvent(self, event):
        """Shut down cleanly; this must never be able to hang."""
        self.render_timer.stop()
        self.marker_timer.stop()
        self.hotplug_timer.stop()
        self.panel_recorder.stop_playback()
        self.worker.stop()
        event.accept()
