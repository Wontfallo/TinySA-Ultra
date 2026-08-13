# TECHNICAL BLUEPRINT - TinySA Ultra Spectrum Analyzer Desktop Application

## 1. Executive Summary
The **TinySA Ultra Spectrum Analyzer Desktop Application** is a feature-rich, high-performance, dark-themed GUI application designed specifically for the TinySA and TinySA Ultra hardware spectrum analyzer devices. Built using Python 3.14, PySide6 (Qt 6), pyqtgraph, PySerial, and NumPy, it provides real-time spectrum scanning, high-resolution rolling waterfall heatmaps, extensive trace math, customizable multi-markers, frequency range presets, data recording/playback, audio demodulation / signal generator controls, and deep configuration options exposed by the TinySA serial protocol.

---

## 2. Architecture & Component Structure

### Architecture Overview
```
+-----------------------------------------------------------------------+
|                            PySide6 GUI                                |
|  +-----------------------+  +--------------------------------------+  |
|  | Controls & Settings   |  | pyqtgraph Plot Widget                |  |
|  | - Sweeps / Frequency  |  | - Live / Max Hold / Min Hold Traces  |  |
|  | - RBW / Attenuation   |  | - Multi-Markers & Peak Tracking      |  |
|  | - Presets (WiFi, etc) |  | - Waterfall / Spectrogram            |  |
|  | - Record & Playback   |  | - Trace Math & Averaging             |  |
|  +-----------------------+  +--------------------------------------+  |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
|                    TinySA Serial Communication Thread                  |
|  - Serial Driver (PySerial on COM16 @ 115200 / 921600 baud)           |
|  - Protocol Parser (sweep, scan, marker, rbw, threadsweep, info)       |
|  - Async Thread Worker (QThread / Signals & Slots)                    |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
|                     TinySA Ultra Hardware Device                      |
+-----------------------------------------------------------------------+
```

### Module Blueprint
- `main.py`: Application entry point, QApp lifecycle, DPI scaling, global stylesheet initialization.
- `tinysa_driver.py`: Low-level serial driver for TinySA / TinySA Ultra using `pyserial`. Handles protocol parsing, sweep data decoding, command queueing, and background QThread worker for 60 FPS real-time sweeps.
- `gui/`:
  - `main_window.py`: Main QMainWindow layout, dockable widgets, menu bars, toolbar, status bar.
  - `spectrum_plot.py`: Pyqtgraph graphics view with real-time spectrum curves, multi-color traces (Live, Max Hold, Min Hold, Average, Math), grid, auto-scaling, and interactive markers.
  - `waterfall_widget.py`: High-performance rolling 2D image spectrogram (waterfall plot) with colormaps (Viridis, Plasma, Inferno, Rainbow, Monokai) and historical scrolling buffer.
  - `control_panel.py`: Quick sweep settings (Start/Stop, Center/Span, RBW, Atten, LNA, Trigger, Input mode).
  - `preset_panel.py`: Presets for WiFi (2.4G/5G), Ham bands, Cellular, FM, Bluetooth, ISM bands, and custom user presets.
  - `marker_panel.py`: Marker table, peak search (Max, Min, Next Peak, Delta mode), peak tracking, readout display.
  - `trace_panel.py`: Trace manager (Traces 1-5, colors, math functions A-B, A+B, Averaging count, Hold controls).
  - `recorder_panel.py`: Session recorder (CSV export, JSON export, SVG/PNG snapshot, binary session recording & playback).
  - `device_settings_dialog.py`: Deep TinySA Ultra hardware options (Spur suppression, VNA mode, Audio output, Battery info, Calibrate, Firmware info, Command terminal).
- `styles/dark_theme.py`: Custom modern dark theme stylesheet with high legibility, large fonts, cyan/emerald accents, tooltips.

---

## 3. Technology Stack & Dependencies
- **Language**: Python 3.14+
- **GUI Framework**: PySide6 (Qt 6)
- **High-Speed Plotting**: `pyqtgraph` (OpenGL-accelerated)
- **Serial Communication**: `pyserial`
- **Data & Math Processing**: `numpy`, `scipy`
- **Image & Data Export**: `pillow`, `matplotlib` (optional fallback), CSV, JSON

---

## 4. Hardware Protocol Specifications (TinySA Ultra Protocol)
- Serial Interface: USB CDC Virtual COM Port (Default baud: 115200 / high speed)
- Commands:
  - `version`: Returns firmware version & hardware identification.
  - `info`: Returns battery status, hardware version, system flags.
  - `sweep <start_hz> <stop_hz> [points]`: Requests spectrum sweep. Points: 50 to 450 (Ultra mode up to 1000+ points).
  - `rbw <auto|3|10|30|100|300|600>`: Sets Resolution Bandwidth (kHz).
  - `attenuate <auto|0..31>`: Sets input attenuator.
  - `lna <on|off>`: Enables/disables Low Noise Amplifier (Preamplifier).
  - `spur <on|off>`: Toggles spur removal mode.
  - `input <low|high|ultra>`: Selects active input port/frequency mode.
  - `threadsweep <start_hz> <stop_hz> [points] [mode]`: Initiates continuous streaming sweep thread.
  - `resume` / `pause`: Controls streaming state.

---

## 5. Lessons Learned & Changelog
*(Append-only log for ongoing updates)*
- **2026-08-07**: Initial blueprint creation for TinySA Ultra Spectrum Analyzer Desktop Application.
