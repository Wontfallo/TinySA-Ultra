"""
Preset frequency ranges and configurations for TinySA Ultra Spectrum Analyzer.
Includes popular RF bands: WiFi, Cellular, Ham Radio, ISM, Aviation, FM, Bluetooth, GPS, etc.
"""

PRESETS = [
    {
        "name": "Wi-Fi 2.4 GHz Band",
        "category": "Wi-Fi & Wireless",
        "start_freq": 2400000000,
        "stop_freq": 2483500000,
        "rbw": 100,
        "description": "2.4 GHz IEEE 802.11 b/g/n/ax Wi-Fi Channels 1-14",
    },
    {
        "name": "Wi-Fi 5 GHz UNII-1/2/3",
        "category": "Wi-Fi & Wireless",
        "start_freq": 5150000000,
        "stop_freq": 5850000000,
        "rbw": 300,
        "description": "5 GHz Wi-Fi UNII-1, UNII-2, UNII-3 bands",
    },
    {
        "name": "Bluetooth / BLE",
        "category": "Wi-Fi & Wireless",
        "start_freq": 2400000000,
        "stop_freq": 2483500000,
        "rbw": 10,
        "description": "Bluetooth Classic & BLE (2402 - 2480 MHz)",
    },
    {
        "name": "FM Broadcast Band",
        "category": "Broadcast & Radio",
        "start_freq": 88000000,
        "stop_freq": 108000000,
        "rbw": 30,
        "description": "Commercial FM Broadcast (88 - 108 MHz)",
    },
    {
        "name": "Aviation Airband (AM)",
        "category": "Aviation & Maritime",
        "start_freq": 108000000,
        "stop_freq": 137000000,
        "rbw": 10,
        "description": "VHF Aircraft Communications (Civil Aviation)",
    },
    {
        "name": "2 Meter Ham Band (144-148 MHz)",
        "category": "Amateur Radio",
        "start_freq": 144000000,
        "stop_freq": 148000000,
        "rbw": 3,
        "description": "VHF Amateur Radio 2 Meter Allocation",
    },
    {
        "name": "70 Centimeter Ham Band",
        "category": "Amateur Radio",
        "start_freq": 420000000,
        "stop_freq": 450000000,
        "rbw": 10,
        "description": "UHF Amateur Radio 70cm Allocation",
    },
    {
        "name": "6 Meter Ham Band (50-54 MHz)",
        "category": "Amateur Radio",
        "start_freq": 50000000,
        "stop_freq": 54000000,
        "rbw": 3,
        "description": "VHF Magic Band Amateur Radio",
    },
    {
        "name": "ISM 433 MHz",
        "category": "ISM & IoT",
        "start_freq": 433050000,
        "stop_freq": 434790000,
        "rbw": 3,
        "description": "Sub-GHz ISM Band (Remote controls, sensors)",
    },
    {
        "name": "ISM 868 MHz (EU)",
        "category": "ISM & IoT",
        "start_freq": 863000000,
        "stop_freq": 870000000,
        "rbw": 10,
        "description": "European Short Range Devices & LoRaWAN",
    },
    {
        "name": "ISM 915 MHz (US)",
        "category": "ISM & IoT",
        "start_freq": 902000000,
        "stop_freq": 928000000,
        "rbw": 30,
        "description": "US Sub-GHz ISM Band (LoRa, RFID, Smart Meters)",
    },
    {
        "name": "GPS L1 Signal",
        "category": "Navigation",
        "start_freq": 1565420000,
        "stop_freq": 1585420000,
        "rbw": 10,
        "description": "GPS L1 Civilian Frequency (1575.42 MHz ± 10 MHz)",
    },
    {
        "name": "Cellular 700 MHz (B12/B13/B17)",
        "category": "Cellular & 5G",
        "start_freq": 698000000,
        "stop_freq": 798000000,
        "rbw": 100,
        "description": "Low-band LTE / 5G Mobile Networks",
    },
    {
        "name": "Cellular 850 MHz Band",
        "category": "Cellular & 5G",
        "start_freq": 824000000,
        "stop_freq": 894000000,
        "rbw": 100,
        "description": "Cellular 850 MHz Uplink / Downlink",
    },
    {
        "name": "Cellular PCS 1900 MHz",
        "category": "Cellular & 5G",
        "start_freq": 1850000000,
        "stop_freq": 1990000000,
        "rbw": 300,
        "description": "PCS 1900 LTE / 5G Band",
    },
    {
        "name": "Cellular 5G C-Band (n77/n78)",
        "category": "Cellular & 5G",
        "start_freq": 3300000000,
        "stop_freq": 3800000000,
        "rbw": 600,
        "description": "5G Mid-Band Spectrum (3.3 - 3.8 GHz)",
    },
    {
        "name": "Full Low Spectrum (100kHz - 800MHz)",
        "category": "Full Spectrum",
        "start_freq": 100000,
        "stop_freq": 800000000,
        "rbw": 300,
        "description": "Standard TinySA Low Input Range",
    },
    {
        "name": "TinySA Ultra Full Sweep (100kHz - 6GHz)",
        "category": "Full Spectrum",
        "start_freq": 100000,
        "stop_freq": 6000000000,
        "rbw": 600,
        "description": "Complete TinySA Ultra High/Ultra Mode Sweep",
    },
]

import json
import os
import re

#: Where user-defined presets are persisted between sessions.
USER_PRESET_PATH = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"),
    "TinySA_Ultra_Suite",
    "user_presets.json",
)


def format_frequency(hz: float) -> str:
    """Format a frequency in Hz as a human-readable string.

    Handles negative values so marker delta readouts scale correctly instead of
    falling through to raw Hz.
    """
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        return "--"
    sign = "-" if hz < 0 else ""
    mag = abs(hz)

    # Decimal counts are chosen to be lossless down to 1 Hz at every scale.
    # ".6f" at GHz quantised to 1 kHz, so a frequency typed into a control and
    # formatted back into that same control silently drifted by up to 500 Hz.
    if mag >= 1e9:
        return sign + f"{mag / 1e9:.9f}".rstrip('0').rstrip('.') + " GHz"
    elif mag >= 1e6:
        return sign + f"{mag / 1e6:.6f}".rstrip('0').rstrip('.') + " MHz"
    elif mag >= 1e3:
        return sign + f"{mag / 1e3:.3f}".rstrip('0').rstrip('.') + " kHz"
    else:
        return sign + f"{mag:.1f} Hz"


def _wifi_24_channels():
    """802.11 2.4 GHz channels 1-14 (centres, MHz)."""
    chans = [(str(n), 2412.0 + 5.0 * (n - 1)) for n in range(1, 14)]
    chans.append(("14", 2484.0))
    return [{"label": f"ch{n}", "freq_hz": mhz * 1e6} for n, mhz in chans]


def _wifi_5_channels():
    """Common 5 GHz UNII channel centres (20 MHz), MHz."""
    nums = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120,
            124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]
    return [{"label": f"ch{n}", "freq_hz": (5000.0 + 5.0 * n) * 1e6} for n in nums]


def _ble_advertising():
    """The three BLE advertising channels - the useful ones to eyeball."""
    return [{"label": "adv37", "freq_hz": 2402e6},
            {"label": "adv38", "freq_hz": 2426e6},
            {"label": "adv39", "freq_hz": 2480e6}]


def _lora_915():
    """US 915 MHz ISM band edges and a few LoRa uplink centres."""
    return [{"label": f"{int(f)}M", "freq_hz": f * 1e6}
            for f in (903.0, 907.4, 911.8, 916.2, 920.6, 925.0)]


#: Channel plans keyed by preset name. Drawn as labelled markers over the
#: spectrum so a preselected band shows where each channel actually sits.
CHANNEL_PLANS = {
    "Wi-Fi 2.4 GHz Band": _wifi_24_channels(),
    "Wi-Fi 5 GHz UNII-1/2/3": _wifi_5_channels(),
    "Bluetooth / BLE": _ble_advertising(),
    "ISM 915 MHz (US)": _lora_915(),
}


def channel_plan_for(preset_name: str):
    """Return the channel plan for a preset, or [] if it has none."""
    return CHANNEL_PLANS.get(preset_name, [])


#: Decimal places per unit for fixed-width readouts, chosen so the resolution
#: is meaningful at that scale (1 kHz at GHz, 100 Hz at MHz).
_FIXED_DECIMALS = (("GHz", 1e9, 6), ("MHz", 1e6, 4), ("kHz", 1e3, 3), ("Hz", 1.0, 1))

#: Character width every fixed readout is padded to. Live displays must not
#: change width between frames or the surrounding layout visibly jitters.
FREQ_FIELD_WIDTH = 13


def format_frequency_fixed(hz: float, pad: bool = True) -> str:
    """Format a frequency at constant width, keeping trailing zeros.

    ``format_frequency`` strips trailing zeros, so a live readout flips between
    "2.4 GHz" and "2.431730 GHz" from one sweep to the next. In a layout that
    sizes to its contents, that re-flows the whole row many times a second and
    reads as jitter, while also hiding real precision. This keeps every digit
    and a constant field width instead.
    """
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        return "--".rjust(FREQ_FIELD_WIDTH) if pad else "--"

    sign = "-" if hz < 0 else ""
    mag = abs(hz)
    for unit, scale, decimals in _FIXED_DECIMALS:
        if mag >= scale or scale == 1.0:
            text = f"{sign}{mag / scale:.{decimals}f} {unit}"
            break
    else:  # pragma: no cover - the Hz branch always matches
        text = f"{sign}{mag:.1f} Hz"

    return text.rjust(FREQ_FIELD_WIDTH) if pad else text


#: Unit suffixes, longest first so "ghz" is matched before a bare "g".
_UNITS = (
    ("ghz", 1e9), ("mhz", 1e6), ("khz", 1e3), ("hz", 1.0),
    ("g", 1e9), ("m", 1e6), ("k", 1e3),
)

_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def parse_frequency_string(text: str) -> float:
    """Parse '2.4 GHz', '433.92 MHz', '100 kHz' or a bare number into Hz.

    A bare number with no unit is interpreted as MHz, which is what users
    actually mean when they type "433.92" into an RF frequency field.
    """
    if text is None:
        return 0.0
    s = str(text).strip().lower().replace(",", "")
    if not s:
        return 0.0

    match = _NUMBER_RE.search(s)
    if not match:
        return 0.0
    try:
        value = float(match.group(0))
    except ValueError:
        return 0.0

    suffix = s[match.end():].strip()
    for unit, mult in _UNITS:
        if suffix.startswith(unit):
            return value * mult

    # No unit given. Small numbers are almost always MHz ("433.92", "2400"),
    # while anything from five figures up was meant as raw Hz -- reading
    # "500000" as 500 GHz and clamping it to the 6 GHz ceiling was not useful.
    return value * 1e6 if abs(value) < 10_000 else value


def load_user_presets() -> list:
    """Load persisted custom presets; returns [] if none or unreadable."""
    try:
        with open(USER_PRESET_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return [
            p for p in data
            if isinstance(p, dict) and "name" in p and "start_freq" in p and "stop_freq" in p
        ]
    except (OSError, ValueError):
        return []


def save_user_presets(presets: list) -> tuple[bool, str]:
    """Persist custom presets. Returns ``(ok, message)``."""
    try:
        os.makedirs(os.path.dirname(USER_PRESET_PATH), exist_ok=True)
        with open(USER_PRESET_PATH, "w", encoding="utf-8") as f:
            json.dump(presets, f, indent=2)
        return True, USER_PRESET_PATH
    except OSError as e:
        return False, str(e)
