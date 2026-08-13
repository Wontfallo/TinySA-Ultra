<div align="center">

# TinySA Ultra Spectrum Analyzer — Pro Suite

**A high-performance, dark-themed desktop companion for the TinySA / TinySA Ultra hardware spectrum analyzer.**

Real-time sweeps · Rolling waterfall · Trace math · Multi-markers · Presets · Recording & playback

![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/GUI-PySide6%20(Qt%206)-41CD52?logo=qt&logoColor=white)
![Plotting](https://img.shields.io/badge/Plotting-pyqtgraph-orange)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)
![Hardware](https://img.shields.io/badge/Hardware-TinySA%20%2F%20TinySA%20Ultra-cyan)

<img src="docs/screenshots/main-window.png" alt="TinySA Ultra Pro Suite — main window showing live sweep, max/min hold, averaging and trace math over the 2.4 GHz Wi-Fi band with a viridis waterfall" width="100%">

*Live capture of the 2.4 GHz Wi-Fi band: five simultaneous traces (Live, Max Hold, Min Hold, Average, Trace Math), a peak marker parked on an active Wi-Fi channel, and a rolling viridis waterfall underneath.*

</div>

---

## Highlights

- **Real-time streaming sweeps** over USB serial with a background acquisition thread — the UI never blocks while the hardware scans.
- **Five simultaneous traces**: Live, Max Hold, Min Hold, rolling Average (configurable sweep count), and a computed Math trace (e.g. `T1 − T2`).
- **Rolling waterfall / spectrogram** with selectable colormaps (viridis, plasma, inferno, and more), adjustable floor/ceiling, and auto-contrast.
- **Six markers with peak search** — snap to max/min, hop to next peak left/right/strongest, auto peak tracking, delta-mode readouts relative to Marker 1, and a level-crossing alarm.
- **Frequency presets** for the bands you actually look at: Wi-Fi 2.4/5 GHz, Bluetooth, FM broadcast, 2 m / 6 m ham, ISM 433/868/915 MHz, GPS L1, cellular 700/850/1900 MHz, 5G mid-band — plus your own saved custom ranges. Band presets overlay channel gridlines (Wi-Fi channels, LoRa centers) on the plot.
- **Data recorder**: capture sweep sessions to file and play them back, export CSV/JSON, and save PNG snapshots of the plot.
- **Deep hardware access**: signal generator control, battery/hardware info, spur removal, LNA preamp, attenuation, RBW selection, input port switching, and a raw terminal console speaking the TinySA serial protocol.
- **Demo / simulation mode** — explore the full UI with a simulated RF environment, no hardware required.

## The dashboard at a glance

| Area | What you get |
|---|---|
| **LCD readouts** | Peak frequency, peak power, center frequency, span width, and live sweep rate |
| **Spectrum plot** | pyqtgraph-accelerated multi-trace view with channel gridlines, interactive markers, and one-shot or continuous Y auto-scaling |
| **Waterfall** | Rolling history of hundreds of sweeps with per-colormap floor/ceil sliders |
| **Dock panels** | Sweep & Hardware Controls, Frequency Presets, Markers & Peak Search, Trace Manager & Math, Data Recorder & Playback — all dockable and rearrangeable |

## Getting started

### Requirements

- Python **3.14+**
- A **TinySA** or **TinySA Ultra** connected over USB (a virtual COM port) — or just use **Demo / Sim Mode**
- Packages: `PySide6`, `pyqtgraph`, `pyserial`, `numpy`, `scipy`, `pillow`

```bash
pip install PySide6 pyqtgraph pyserial numpy scipy pillow
```

### Run from source

```bash
python main.py
```

The app auto-detects TinySA devices on available COM ports. Hit **Refresh**, pick your port, and click **Connect** — or press **Demo / Sim Mode** to drive the whole UI against a simulated spectrum.

### Build a standalone executable

A PyInstaller spec is included:

```bash
pyinstaller TinySA_Ultra_Suite.spec
```

The bundled app lands in `dist/TinySA_Ultra_Suite/`.

## Typical workflow

1. **Connect** (or enter Demo mode) — the status bar confirms the firmware version and link.
2. **Pick a band** — double-click a preset (say, *Wi-Fi 2.4 GHz Band*) or type start/stop or center/span frequencies and **Apply Frequency Range**.
3. **Tune the front end** — RBW filter, attenuation, LNA preamp, spur removal, input port.
4. **Analyze** — enable Max/Min hold and averaging, park markers on peaks, set up delta measurements or a threshold alarm.
5. **Capture** — record the session, export CSV/JSON, or snapshot the plot to PNG.

## Architecture

```
PySide6 GUI (docks, LCDs, pyqtgraph plot + waterfall)
        │  Qt signals/slots
        ▼
Acquisition thread (QThread) — command queue + sweep parser
        │  pyserial @ 115200/921600 baud
        ▼
TinySA / TinySA Ultra hardware (USB CDC virtual COM port)
```

| Module | Role |
|---|---|
| [main.py](main.py) | App entry point, DPI scaling, theme bootstrap |
| [tinysa_driver.py](tinysa_driver.py) | Serial driver, protocol parser, threaded sweep streaming |
| [gui/main_window.py](gui/main_window.py) | Main window, docks, menus, toolbar |
| [gui/spectrum_plot.py](gui/spectrum_plot.py) | Multi-trace spectrum view + markers |
| [gui/waterfall_widget.py](gui/waterfall_widget.py) | Rolling spectrogram with colormaps |
| [gui/control_panel.py](gui/control_panel.py) | Connection, frequency tuning, RF front-end settings |
| [gui/marker_panel.py](gui/marker_panel.py) | Marker table, peak search, tracking, alarm |
| [gui/trace_panel.py](gui/trace_panel.py) | Trace enable/display, averaging, trace math, Y scaling |
| [gui/preset_panel.py](gui/preset_panel.py) | Built-in and custom frequency presets |
| [gui/recorder_panel.py](gui/recorder_panel.py) | Session recording, playback, CSV/JSON/PNG export |
| [gui/device_settings_dialog.py](gui/device_settings_dialog.py) | Signal generator, hardware info, terminal console |

More detail lives in the [Technical Blueprint](TECHNICAL_BLUEPRINT.md).

## Hardware notes

Talks the TinySA serial protocol directly: `sweep`, `rbw`, `attenuate`, `lna`, `spur`, `input`, and continuous `threadsweep` streaming. Works with TinySA (100 kHz – 960 MHz) and TinySA Ultra (100 kHz – 6 GHz) firmware.

## License

Not yet specified — all rights reserved by the author until a license is added.
