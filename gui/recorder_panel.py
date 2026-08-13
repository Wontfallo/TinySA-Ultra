"""
Data Recording, Session Logging, Exporting & Playback Scrubber Panel.
Supports real-time CSV/JSON sweep logging, PNG/SVG visual snapshots,
and offline session recording replay.
"""

import os
import csv
import json
import time
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton,
    QLabel, QFileDialog, QSlider, QCheckBox, QMessageBox
)
from PySide6.QtCore import Signal, Qt, QTimer
from utils.presets import format_frequency


class RecorderPanelWidget(QWidget):
    """Data recorder, exporter, and session playback panel."""

    snapshot_requested = Signal()
    playback_sweep_emitted = Signal(np.ndarray, np.ndarray)  # (freqs, dbm)
    playback_state_changed = Signal(bool)                    # (playing)

    #: Hard ceiling on retained sweeps. At acquisition rate an uncapped list
    #: of Python lists grows by megabytes per second and eventually stalls the
    #: machine, so recording stops itself here instead.
    MAX_RECORDED_SWEEPS = 20000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_recording = False
        self.recorded_sweeps = []  # List of {"timestamp": t, "freqs": list, "dbm": list}
        self.recording_file_path = None
        self.is_playing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        # -------------------------------------------------------------
        # 1. Real-Time Session Recorder Box
        # -------------------------------------------------------------
        box_rec = QGroupBox("Real-Time Data Session Recorder")
        layout_rec = QVBoxLayout(box_rec)

        self.lbl_rec_status = QLabel("Recorder Idle (0 sweeps captured)")
        self.lbl_rec_status.setStyleSheet("color: #94a3b8; font-weight: 600;")
        layout_rec.addWidget(self.lbl_rec_status)

        rec_btn_row = QHBoxLayout()
        self.btn_toggle_rec = QPushButton("Start Recording")
        self.btn_toggle_rec.setObjectName("successButton")
        self.btn_toggle_rec.setToolTip("Start capturing real-time spectrum sweeps to session file")
        self.btn_toggle_rec.clicked.connect(self.toggle_recording)
        rec_btn_row.addWidget(self.btn_toggle_rec)

        self.btn_export_csv = QPushButton("Export CSV Snapshot")
        self.btn_export_csv.setToolTip("Save current sweep line as a standalone CSV file")
        self.btn_export_csv.clicked.connect(self.export_csv_snapshot)
        rec_btn_row.addWidget(self.btn_export_csv)

        layout_rec.addLayout(rec_btn_row)

        self.btn_snapshot = QPushButton("📸 Save High-Res PNG Plot Snapshot")
        self.btn_snapshot.setObjectName("accentButton")
        self.btn_snapshot.setToolTip("Export high resolution PNG image of spectrum analyzer plot")
        self.btn_snapshot.clicked.connect(lambda: self.snapshot_requested.emit())
        layout_rec.addWidget(self.btn_snapshot)

        layout.addWidget(box_rec)

        # -------------------------------------------------------------
        # 2. Session Playback & Replay Scrubber Box
        # -------------------------------------------------------------
        box_play = QGroupBox("Recorded Session Replay Scrubber")
        layout_play = QVBoxLayout(box_play)

        play_btn_row = QHBoxLayout()
        self.btn_load_session = QPushButton("Open Recording File...")
        self.btn_load_session.setToolTip("Load a previously recorded .json or .csv session file")
        self.btn_load_session.clicked.connect(self.load_session_file)
        play_btn_row.addWidget(self.btn_load_session)

        self.btn_play_pause = QPushButton("Play Replay")
        self.btn_play_pause.setEnabled(False)
        self.btn_play_pause.clicked.connect(self.toggle_playback)
        play_btn_row.addWidget(self.btn_play_pause)

        layout_play.addLayout(play_btn_row)

        lbl_scrub = QLabel("Timeline Scrubber:")
        lbl_scrub.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout_play.addWidget(lbl_scrub)

        self.slider_playback = QSlider(Qt.Horizontal)
        self.slider_playback.setEnabled(False)
        self.slider_playback.valueChanged.connect(self.on_slider_scrubbed)
        layout_play.addWidget(self.slider_playback)

        self.lbl_playback_info = QLabel("No session loaded")
        self.lbl_playback_info.setStyleSheet("color: #64748b; font-size: 11px;")
        layout_play.addWidget(self.lbl_playback_info)

        layout.addWidget(box_play)
        layout.addStretch()

        self.last_freqs = None
        self.last_dbm = None

        # Playback clock. Replay runs at a fixed, readable 10 frames/second
        # rather than trying to reproduce original capture timing.
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(100)
        self._play_timer.timeout.connect(self._advance_playback)

    def update_latest_sweep(self, freqs: np.ndarray, dbm: np.ndarray):
        """Cache the latest live sweep for recording, export and snapshots."""
        self.last_freqs = freqs
        self.last_dbm = dbm

        if not self.is_recording:
            return

        if len(self.recorded_sweeps) >= self.MAX_RECORDED_SWEEPS:
            self.is_recording = False
            self.btn_toggle_rec.setText("Start Recording")
            self.lbl_rec_status.setText(
                f"Recording stopped: reached the {self.MAX_RECORDED_SWEEPS} sweep limit."
            )
            self.lbl_rec_status.setStyleSheet("color: #ffcc00; font-weight: bold;")
            if self.recorded_sweeps:
                self.save_recorded_session()
            return

        self.recorded_sweeps.append({
            "timestamp": time.time(),
            "start_hz": float(freqs[0]),
            "stop_hz": float(freqs[-1]),
            "freqs": freqs.tolist(),
            "dbm": dbm.tolist(),
        })
        # Refresh the counter ~4x/second instead of on every sweep.
        count = len(self.recorded_sweeps)
        if count % 5 == 0 or count == 1:
            self.lbl_rec_status.setText(f"🔴 Recording ACTIVE ({count} sweeps captured)")

    def _restyle(self, widget, object_name: str):
        """Swap a widget's stylesheet selector and force a re-polish."""
        widget.setObjectName(object_name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def toggle_recording(self):
        """Start or stop the recording session."""
        if not self.is_recording:
            if self.last_dbm is None:
                QMessageBox.warning(
                    self, "No Data",
                    "There is no live sweep data yet. Connect the TinySA (or "
                    "switch to Simulation Mode) before recording."
                )
                return
            self.stop_playback()
            self.is_recording = True
            self.recorded_sweeps = []
            self.btn_toggle_rec.setText("Stop Recording & Save")
            self._restyle(self.btn_toggle_rec, "dangerButton")
            self.lbl_rec_status.setText("🔴 Recording ACTIVE (0 sweeps captured)")
            self.lbl_rec_status.setStyleSheet("color: #ef4444; font-weight: bold;")
        else:
            self.is_recording = False
            self.btn_toggle_rec.setText("Start Recording")
            self._restyle(self.btn_toggle_rec, "successButton")
            self.lbl_rec_status.setText(f"Recorder Idle ({len(self.recorded_sweeps)} saved)")
            self.lbl_rec_status.setStyleSheet("color: #94a3b8; font-weight: 600;")

            if self.recorded_sweeps:
                self.save_recorded_session()

    def save_recorded_session(self):
        """Prompt file save dialog for recorded session."""
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Recorded Session", "", "JSON Session (*.json);;CSV Log (*.csv)")
        if filepath:
            try:
                if filepath.endswith(".csv"):
                    with open(filepath, "w", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Timestamp", "Frequency_Hz", "Power_dBm"])
                        for sw in self.recorded_sweeps:
                            t = sw["timestamp"]
                            for freq, power in zip(sw["freqs"], sw["dbm"]):
                                writer.writerow([t, freq, power])
                else:
                    with open(filepath, "w") as f:
                        json.dump(self.recorded_sweeps, f, indent=2)

                QMessageBox.information(self, "Session Saved", f"Saved {len(self.recorded_sweeps)} sweeps to {os.path.basename(filepath)}")
            except Exception as e:
                QMessageBox.critical(self, "Error Saving", f"Could not save session file: {e}")

    def export_csv_snapshot(self):
        """Export current live sweep line to CSV."""
        if self.last_freqs is None or self.last_dbm is None:
            QMessageBox.warning(self, "No Data", "No active sweep data available to export.")
            return

        filepath, _ = QFileDialog.getSaveFileName(self, "Export CSV Spectrum Snapshot", "tinysa_spectrum_snapshot.csv", "CSV File (*.csv)")
        if filepath:
            try:
                with open(filepath, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Frequency_Hz", "Frequency_Formatted", "Power_dBm"])
                    for freq, dbm in zip(self.last_freqs, self.last_dbm):
                        writer.writerow([freq, format_frequency(freq), dbm])
                QMessageBox.information(self, "Export Complete", f"Saved spectrum snapshot to {os.path.basename(filepath)}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Error exporting CSV: {e}")

    def load_session_file(self):
        """Load session file for playback."""
        filepath, _ = QFileDialog.getOpenFileName(self, "Load Session Recording", "", "JSON Session (*.json)")
        if filepath:
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    self.stop_playback()
                    self.recorded_sweeps = data
                    self.slider_playback.blockSignals(True)
                    self.slider_playback.setRange(0, len(data) - 1)
                    self.slider_playback.setValue(0)
                    self.slider_playback.blockSignals(False)
                    self.slider_playback.setEnabled(True)
                    self.btn_play_pause.setEnabled(True)
                    self.lbl_playback_info.setText(f"Loaded: {os.path.basename(filepath)} ({len(data)} frames)")
                    # Show the first frame immediately so the load is visible.
                    self.on_slider_scrubbed(0)
                else:
                    QMessageBox.warning(self, "Invalid File", "Recording file contains no valid sweep data frames.")
            except Exception as e:
                QMessageBox.critical(self, "Error Loading", f"Failed to open session recording: {e}")

    def toggle_playback(self):
        """Start or stop replaying the loaded session."""
        if not self.recorded_sweeps:
            return

        if self.is_playing:
            self.stop_playback()
            return

        self.is_playing = True
        self.btn_play_pause.setText("Pause Replay")
        self._play_timer.start()
        # Live acquisition must be suspended, otherwise incoming sweeps fight
        # replay frames for the same plot.
        self.playback_state_changed.emit(True)

    def stop_playback(self):
        """Halt replay and hand the display back to live acquisition."""
        if not self.is_playing:
            return
        self.is_playing = False
        self._play_timer.stop()
        self.btn_play_pause.setText("Play Replay")
        self.playback_state_changed.emit(False)

    def _advance_playback(self):
        """Step the scrubber one frame, wrapping at the end of the session."""
        if not self.recorded_sweeps:
            self.stop_playback()
            return
        nxt = self.slider_playback.value() + 1
        if nxt >= len(self.recorded_sweeps):
            nxt = 0
        # Setting the value emits valueChanged -> on_slider_scrubbed, which
        # publishes the frame.
        self.slider_playback.setValue(nxt)

    def on_slider_scrubbed(self, idx: int):
        """Emit the scrubbed frame's data."""
        if not (0 <= idx < len(self.recorded_sweeps)):
            return
        sw = self.recorded_sweeps[idx]
        try:
            dbm = np.asarray(sw["dbm"], dtype=float)
            freqs = sw.get("freqs")
            if freqs:
                freqs = np.asarray(freqs, dtype=float)
            else:
                # Older/CSV-derived sessions may only carry the band edges.
                freqs = np.linspace(
                    float(sw.get("start_hz", 0.0)),
                    float(sw.get("stop_hz", len(dbm))),
                    len(dbm),
                )
        except (TypeError, ValueError, KeyError):
            self.lbl_playback_info.setText(f"Frame {idx+1}: malformed, skipped")
            return

        if len(freqs) != len(dbm) or len(dbm) == 0:
            self.lbl_playback_info.setText(f"Frame {idx+1}: malformed, skipped")
            return

        self.playback_sweep_emitted.emit(freqs, dbm)
        self.lbl_playback_info.setText(
            f"Frame {idx+1}/{len(self.recorded_sweeps)} | "
            f"{format_frequency(freqs[0])} - {format_frequency(freqs[-1])}"
        )
