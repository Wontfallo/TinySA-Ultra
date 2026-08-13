"""
TinySA / TinySA Ultra hardware serial driver and single-owner acquisition thread.

Design notes (these exist because the previous version deadlocked the GUI):

* Every serial operation has BOTH a read timeout and a write timeout. A TinySA
  whose USB CDC endpoint has wedged accepts the port open but never drains it,
  so ``write()`` blocks forever when ``write_timeout`` is None. That was the
  original "app freezes and locks" bug.
* Responses are framed by the shell prompt ``ch>``, not by the first newline.
  The device echoes the command back, so breaking on the first ``\\n`` returned
  nothing but the echo.
* Trace data comes from ``scan``, not ``sweep``. ``sweep`` only sets the sweep
  range and emits no samples, which is why the plot stayed flat.
* Exactly one thread ever touches the port: :class:`TinySAWorker`. Callers post
  requests onto its queue. Nothing serial-related runs on the GUI thread.
"""

from __future__ import annotations

import queue
import re
import threading
import time
from dataclasses import dataclass

import numpy as np
import serial
import serial.tools.list_ports
from PySide6.QtCore import QThread, Signal
from serial import SerialException, SerialTimeoutException

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIMULATION_PORT = "SIMULATION"

#: USB VID:PID pairs that identify a TinySA (STM32 CDC virtual COM port).
TINYSA_USB_IDS = {(0x0483, 0x5740)}

PROMPT = "ch>"

#: Hardware sample-count limits. The device rejects very large scans; the
#: simulator has no such limit.
HW_POINTS_MIN, HW_POINTS_MAX = 50, 450
SIM_POINTS_MIN, SIM_POINTS_MAX = 50, 2000

#: Frequency guard rails (Hz).
FREQ_MIN = 100_000.0
FREQ_MAX = 6_000_000_000.0

_NUM_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$")


@dataclass
class SweepFrame:
    """One acquired spectrum sweep."""

    freqs: np.ndarray
    dbm: np.ndarray
    simulated: bool
    seq: int
    acquired_at: float
    duration_ms: float


# ---------------------------------------------------------------------------
# Low-level driver
# ---------------------------------------------------------------------------


class TinySADriver:
    """Serial transport and protocol codec for TinySA / TinySA Ultra.

    Not thread-safe by contract: only :class:`TinySAWorker` may drive it. An
    internal lock is still held so that a stray call cannot interleave bytes.
    """

    def __init__(self, port: str | None = None, baudrate: int = 115200):
        self.port_name = port
        self.baudrate = baudrate

        self.read_timeout = 1.0
        self.write_timeout = 1.5

        self._port: serial.Serial | None = None
        self._lock = threading.RLock()

        self.is_connected = False
        self.is_simulation = False
        self.device_version = "Unknown"
        self.device_info = ""
        self.last_error = ""

        #: Discovered data-retrieval strategy, one of "scan2", "scan3",
        #: "sweep_data" or None (not yet probed).
        self.scan_mode: str | None = None
        self.consecutive_failures = 0
        #: Consecutive failed *sweeps*, independent of per-command successes.
        self.consecutive_sweep_failures = 0
        #: Longest per-point dwell seen so far; drives the idle-gap allowance.
        self._slowest_gap = 1.0
        #: Set to abort a blocking read immediately during shutdown.
        self._abort = threading.Event()
        #: Session to fall back to if the pending connect attempt fails.
        self._restore_to: str | None = None
        #: Guard so a restore attempt cannot recurse into another restore.
        self._restoring = False

        self._sim_t0 = time.time()
        self._sim_rng = np.random.default_rng()

    # -- port discovery -----------------------------------------------------

    @staticmethod
    def get_available_ports() -> list[dict]:
        """List serial ports, flagging any that look like a TinySA."""
        ports = []
        for p in serial.tools.list_ports.comports():
            desc = p.description or p.device
            vidpid = (p.vid, p.pid) if p.vid is not None else None
            is_tinysa = bool(
                (vidpid in TINYSA_USB_IDS)
                or "TINYSA" in desc.upper()
                or "TINYSA" in (p.product or "").upper()
            )
            ports.append(
                {
                    "device": p.device,
                    "description": desc,
                    "hwid": p.hwid,
                    "vid": p.vid,
                    "pid": p.pid,
                    "is_tinysa": is_tinysa,
                }
            )
        # Most likely candidate first.
        ports.sort(key=lambda d: (not d["is_tinysa"], d["device"]))
        return ports

    @classmethod
    def autodetect_port(cls) -> str | None:
        """Return the device path of the first port that looks like a TinySA."""
        for p in cls.get_available_ports():
            if p["is_tinysa"]:
                return p["device"]
        return None

    # -- connection ---------------------------------------------------------

    def request_abort(self) -> None:
        """Ask any in-flight blocking read to give up promptly."""
        self._abort.set()

    def clear_abort(self) -> None:
        self._abort.clear()

    def connect(self, port: str | None = None) -> tuple[bool, str]:
        """Open the port and identify the device.

        Returns ``(ok, message)``. On failure nothing is left half-open and
        ``is_connected`` is False -- the caller decides whether to fall back to
        simulation. This never raises and never blocks indefinitely.
        """
        target = port or self.port_name

        # Remember any working session. A failed attempt at a different device
        # must not destroy a connection that is currently delivering data --
        # picking a bad port previously left the app completely dead.
        # ``_restoring`` stops the recovery attempt from recursing.
        restore_to = None
        if self.is_connected and not self._restoring:
            restore_to = SIMULATION_PORT if self.is_simulation else self.port_name

        self.port_name = target
        self.disconnect()
        self.clear_abort()
        self.last_error = ""
        self.scan_mode = None
        self.consecutive_failures = 0
        self.consecutive_sweep_failures = 0
        self._slowest_gap = 1.0
        self._restore_to = restore_to

        if self.port_name == SIMULATION_PORT:
            self.is_simulation = True
            self.is_connected = True
            self.device_version = "TinySA Ultra (Simulated Engine v1.4-88)"
            self.device_info = "Simulated device - no hardware attached."
            self.scan_mode = "sim"
            self._sim_t0 = time.time()
            return True, "Connected in Simulation Mode"

        if not self.port_name:
            self.last_error = "No port specified"
            return self._fail("No serial port selected.")

        try:
            p = serial.Serial()
            p.port = self.port_name
            p.baudrate = self.baudrate
            p.timeout = self.read_timeout
            p.write_timeout = self.write_timeout
            # TinySA is USB CDC: no hardware/software flow control. Leaving
            # rtscts on makes Windows gate writes on CTS, which the device
            # never asserts.
            p.rtscts = False
            p.dsrdtr = False
            p.xonxoff = False
            p.open()
        except (SerialException, OSError, ValueError) as e:
            self.last_error = str(e)
            self._port = None
            return self._fail(f"Could not open {self.port_name}: {e}")

        with self._lock:
            self._port = p
            self.is_simulation = False

        try:
            p.reset_input_buffer()
            p.reset_output_buffer()
        except SerialException:
            pass

        # Probe with a bare carriage return. If the endpoint is wedged this
        # raises a write timeout instead of hanging forever.
        #
        # Retry a few times: immediately after another process releases the
        # port, Windows can hand back a handle before the CDC endpoint is ready
        # again, and a single probe then reports a healthy device as dead.
        ok = False
        for attempt in range(3):
            ok, _ = self.send_command("", budget=1.5)
            if ok:
                break
            time.sleep(0.25 * (attempt + 1))

        if not ok:
            msg = (
                f"{self.port_name} opened but the device is not responding "
                f"({self.last_error}). The TinySA's USB link is wedged - "
                f"unplug and reconnect it, and check it is powered on."
            )
            self.disconnect()
            return self._fail(msg)

        ok, ver = self.send_command("version", budget=2.0)
        if ok and ver.strip():
            self.device_version = ver.strip().splitlines()[0].strip()
        else:
            self.device_version = "TinySA (version query failed)"

        ok_info, info = self.send_command("info", budget=2.0)
        self.device_info = info.strip() if ok_info else ""

        # Deliberately no "pause" and no configuration push here. `scan` runs
        # its own sweep regardless, so there is nothing to gain, and silently
        # rewriting the device's mode/attenuator/ultra settings every time the
        # app connects would change a instrument the user has already set up.
        # Settings are sent only when the user actually changes a control.

        self.is_connected = True
        return True, f"Connected to {self.port_name} ({self.device_version})"

    def _fail(self, reason: str) -> tuple[bool, str]:
        """Report a failed connect, restoring the previous session if there was one."""
        restore_to, self._restore_to = self._restore_to, None
        if restore_to is None or self._restoring:
            return False, reason

        self._restoring = True
        try:
            ok, _ = self.connect(restore_to)
        except Exception:
            ok = False
        finally:
            self._restoring = False

        if ok:
            where = "Simulation Mode" if restore_to == SIMULATION_PORT else restore_to
            return False, f"{reason}  (kept the existing {where} session)"
        return False, reason

    def disconnect(self) -> None:
        """Close the port cleanly. Safe to call repeatedly; never hangs.

        The port is drained until the device goes quiet BEFORE the handle is
        closed. Closing while the device is still pushing a scan response
        leaves its USB IN endpoint with nobody reading it; the firmware blocks
        there, never returns to its command loop, and stops draining the OUT
        endpoint. From the host that looks exactly like a device that accepts
        no writes and sends no data, and it needs a physical replug to clear.
        """
        with self._lock:
            p, self._port = self._port, None
            self.is_connected = False
            self.is_simulation = False
            self.scan_mode = None

        if p is None:
            return

        try:
            if p.is_open:
                # Hand the instrument back to its own front panel. Best effort:
                # an already-wedged device times out here, which is fine.
                try:
                    p.write(b"resume\r\n")
                except Exception:
                    pass
                self._drain_quiet(p)
                p.close()
        except Exception:
            pass

    @staticmethod
    def _drain_quiet(p, quiet_for: float = 0.20, budget: float = 2.0) -> int:
        """Read and discard until the device has been silent for a moment.

        Returns the number of bytes discarded. Bounded by ``budget`` so a
        chattering device can never block shutdown.
        """
        discarded = 0
        deadline = time.monotonic() + budget
        last_data = time.monotonic()
        while time.monotonic() < deadline:
            try:
                n = p.in_waiting
            except Exception:
                break
            if n:
                try:
                    discarded += len(p.read(n))
                except Exception:
                    break
                last_data = time.monotonic()
            else:
                if time.monotonic() - last_data >= quiet_for:
                    break
                time.sleep(0.01)
        return discarded

    # -- command / response -------------------------------------------------

    def _read_until_prompt(self, idle_timeout: float, hard_cap: float = 90.0) -> str:
        """Read until the shell prompt appears, the device goes quiet, or we cap out.

        This waits on an IDLE GAP, not a total budget. A total budget cannot
        work: sweep time depends on RBW and span, so a 3 kHz RBW scan legitimately
        takes ten seconds while a wide auto-RBW scan takes a fraction of one.
        Guessing that total from the baud rate under-estimated the slow cases,
        and abandoning a response mid-transfer is what leaves the device's USB
        endpoint blocked with nobody reading it -- the wedge.

        The device emits samples progressively, so "no bytes at all for
        ``idle_timeout``" is a sound liveness test, and ``hard_cap`` bounds the
        pathological case.
        """
        p = self._port
        if p is None:
            return ""
        chunks: list[bytes] = []
        tail = b""
        started = time.monotonic()
        last_data = started
        prompt_bytes = PROMPT.encode()

        while True:
            if self._abort.is_set():
                self.last_error = "read aborted (shutting down)"
                break

            now = time.monotonic()
            if now - last_data >= idle_timeout:
                break
            if now - started >= hard_cap:
                self.last_error = f"response exceeded {hard_cap:.0f}s cap"
                break

            try:
                n = p.in_waiting
            except (SerialException, OSError) as e:
                self.last_error = f"read failed: {e}"
                break

            if n:
                try:
                    data = p.read(n)
                except (SerialException, OSError) as e:
                    self.last_error = f"read failed: {e}"
                    break
                chunks.append(data)
                last_data = time.monotonic()
                # Only the tail matters for prompt detection.
                tail = (tail + data)[-(len(prompt_bytes) + 4):]
                if tail.rstrip().endswith(prompt_bytes):
                    break
            else:
                time.sleep(0.004)

        return b"".join(chunks).decode("utf-8", errors="ignore")

    def _resync(self) -> None:
        """Return the shell to a known state after an abandoned response.

        Without this the next command is written while the device is still
        streaming the previous one, the reply stream stays one response behind,
        and the endpoint eventually blocks.
        """
        p = self._port
        if p is None or not p.is_open:
            return
        try:
            self._drain_quiet(p, quiet_for=0.25, budget=3.0)
            p.write(b"\r\n")
            self._read_until_prompt(idle_timeout=0.6, hard_cap=3.0)
            self._drain_quiet(p, quiet_for=0.15, budget=1.0)
        except Exception:
            pass

    @staticmethod
    def _strip_framing(raw: str, cmd: str) -> str:
        """Remove the command echo and trailing shell prompt."""
        text = raw.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        # Drop a leading echo of the command we just sent.
        if cmd and lines and lines[0].strip() == cmd.strip():
            lines = lines[1:]
        # Drop the trailing prompt.
        while lines and lines[-1].strip() in ("", PROMPT):
            lines.pop()
        if lines and lines[-1].rstrip().endswith(PROMPT):
            lines[-1] = lines[-1].rstrip()[: -len(PROMPT)].rstrip()
        return "\n".join(lines)

    def send_command(self, cmd: str, budget: float = 2.0) -> tuple[bool, str]:
        """Send an ASCII command and return ``(ok, response_text)``.

        ``ok`` is False when the transport failed -- a wedged device, a closed
        port, a write timeout. Callers must surface that instead of silently
        treating it as an empty reply, which is what hid the original fault.
        """
        if self.is_simulation:
            return True, self._simulated_response(cmd)

        with self._lock:
            p = self._port
            if p is None or not p.is_open:
                self.last_error = "port is not open"
                return False, ""

            try:
                p.reset_input_buffer()
            except (SerialException, OSError):
                pass

            payload = (cmd.strip() + "\r\n").encode("utf-8")
            try:
                p.write(payload)
            except SerialTimeoutException:
                # The definitive symptom of a wedged CDC endpoint.
                self.last_error = "write timeout (device not draining USB endpoint)"
                self.consecutive_failures += 1
                return False, ""
            except (SerialException, OSError) as e:
                self.last_error = f"write failed: {e}"
                self.consecutive_failures += 1
                return False, ""

            raw = self._read_until_prompt(budget)

            # If we stopped before the prompt, the device may still be mid
            # response. Resynchronise so the next command is not written into a
            # stream that is still being produced.
            if not raw.rstrip().endswith(PROMPT):
                self._resync()

        if not raw:
            self.last_error = self.last_error or "no response before timeout"
            self.consecutive_failures += 1
            return False, ""

        self.consecutive_failures = 0
        return True, self._strip_framing(raw, cmd)

    # -- sweep acquisition --------------------------------------------------

    @staticmethod
    def clamp_range(start_hz: float, stop_hz: float) -> tuple[float, float]:
        """Coerce a requested span into a valid, strictly increasing range.

        Guarantees ``FREQ_MIN <= start < stop <= FREQ_MAX`` for ANY input,
        including NaN and inverted or degenerate ranges. A NaN slipping through
        used to reach ``int()`` inside the scan builder and raise, which killed
        the acquisition thread outright.
        """
        try:
            start = float(start_hz)
            stop = float(stop_hz)
        except (TypeError, ValueError):
            start, stop = float("nan"), float("nan")

        if not np.isfinite(start):
            start = FREQ_MIN
        if not np.isfinite(stop):
            stop = FREQ_MAX

        start = float(min(max(start, FREQ_MIN), FREQ_MAX))
        stop = float(min(max(stop, FREQ_MIN), FREQ_MAX))

        if stop <= start:
            # Widen upward if there is headroom, otherwise downward. At the
            # ceiling `start + 10 kHz` cannot widen, which previously returned
            # a zero-width span.
            if start + 10_000.0 <= FREQ_MAX:
                stop = start + 10_000.0
            else:
                stop = FREQ_MAX
                start = FREQ_MAX - 10_000.0
        return start, stop

    def _read_budget(self, points: int) -> float:
        """Idle-gap tolerance, in seconds, for a scan response.

        This is the gap between consecutive bytes we are willing to wait
        through, NOT the total response time -- see :meth:`_read_until_prompt`.
        A narrow RBW makes the device dwell longer on each point, so the
        allowance scales with the slowest per-point time observed so far.
        """
        return max(4.0, self._slowest_gap * 3.0)

    def _parse_scan(self, text: str, pairs: bool) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Parse a ``scan``/``data`` response into ``(freqs|None, dbm)``.

        Firmware emits a trailing dummy column on every scan mask::

            mask 2   -9.109375e+01 0.000000000
            mask 3   2400000000 -8.959375e+01 0.000000000
            data 0   -8.859375e+01

        so the measurement is always the FIRST field of the value group, never
        the last. Reading the last field yielded a spectrum of solid zeros.
        """
        freqs: list[float] = []
        levels: list[float] = []
        for line in text.split("\n"):
            parts = line.strip().split()
            if not parts:
                continue
            if pairs:
                if len(parts) < 2 or not (_NUM_RE.match(parts[0]) and _NUM_RE.match(parts[1])):
                    continue
                freqs.append(float(parts[0]))
                levels.append(float(parts[1]))
            else:
                tok = parts[0]
                if not _NUM_RE.match(tok):
                    continue
                levels.append(float(tok))
        if not levels:
            return None, None
        return (np.asarray(freqs, dtype=float) if pairs else None), np.asarray(levels, dtype=float)

    @staticmethod
    def _plausible_spectrum(freqs, dbm, start: float, stop: float, points: int) -> bool:
        """Reject a parsed response that cannot be a real spectrum.

        Counting parsed numbers is not enough: an unsupported output mask can
        return the right number of perfectly valid-looking zeros. A sweep is
        only accepted if the levels are finite, physically plausible, actually
        vary (thermal noise always does), and -- when the mask reports them --
        the frequencies match the span that was requested.
        """
        if dbm is None or len(dbm) < max(8, points // 4):
            return False
        if not np.all(np.isfinite(dbm)):
            return False
        # A dummy column reads as an exact run of zeros.
        if np.all(dbm == 0.0):
            return False
        # Real measurements are dBm; anything outside this cannot be one.
        if float(np.min(dbm)) < -200.0 or float(np.max(dbm)) > 60.0:
            return False
        # Deliberately NO flatness test. A strong CW carrier saturating the
        # front end, or a span narrower than one RBW bin, legitimately produces
        # a constant trace -- and the device quantises to 0.25 dB, so even
        # ordinary noise can span a single step. Rejecting flat data stalled
        # the display permanently on exactly those measurements. The all-zeros
        # test above is what actually catches the dummy column.
        if freqs is not None:
            if len(freqs) != len(dbm) or not np.all(np.isfinite(freqs)):
                return False
            # Absolute floor as well as a proportional one: at the 10 kHz
            # minimum span a 5% tolerance is only 500 Hz, which the firmware's
            # own rounding of the sweep endpoints can exceed.
            span = max(stop - start, 1.0)
            tol = max(span * 0.05, 10_000.0)
            if abs(freqs[0] - start) > tol or abs(freqs[-1] - stop) > tol:
                return False
        return True

    def _try_scan_mode(self, mode: str, start: float, stop: float, points: int):
        """Attempt one data-retrieval strategy. Returns (freqs|None, dbm|None)."""
        a, b, n = int(start), int(stop), int(points)
        budget = self._read_budget(n)

        if mode == "scan2":
            ok, text = self.send_command(f"scan {a} {b} {n} 2", budget)
            if not ok:
                return None, None
            return self._parse_scan(text, pairs=False)

        if mode == "scan3":
            ok, text = self.send_command(f"scan {a} {b} {n} 3", budget)
            if not ok:
                return None, None
            return self._parse_scan(text, pairs=True)

        if mode == "sweep_data":
            ok, _ = self.send_command(f"sweep {a} {b} {n}", 2.5)
            if not ok:
                return None, None
            ok, text = self.send_command("data 0", budget)
            if not ok:
                return None, None
            return self._parse_scan(text, pairs=False)

        return None, None

    #: Data-retrieval strategies, best first.
    #:
    #: ``scan3`` leads because it reports the frequency of every sample, so the
    #: result can be checked against the span that was asked for. ``scan2`` is
    #: cheaper on the wire but self-describes nothing, and ``sweep_data`` needs
    #: two round trips and reads back whatever trace the device happens to hold.
    SCAN_MODES = ("scan3", "scan2", "sweep_data")

    def _discover_scan_mode(self, start: float, stop: float, points: int):
        """Find a data command that returns a believable spectrum.

        Returns ``(mode, freqs, dbm)``. The probe's own sweep is handed back
        rather than discarded, so discovery does not cost an extra full scan on
        connect and on every recovery.
        """
        for mode in self.SCAN_MODES:
            freqs, dbm = self._try_scan_mode(mode, start, stop, points)
            if self._plausible_spectrum(freqs, dbm, start, stop, points):
                self.scan_mode = mode
                return mode, freqs, dbm
        self.last_error = (
            self.last_error or "no scan command returned a usable spectrum"
        )
        return None, None, None

    def request_sweep(self, start_hz: float, stop_hz: float, points: int = 201):
        """Acquire one sweep.

        Returns ``(freqs, dbm, ok)``. On hardware failure ``ok`` is False and
        the arrays are None, so the caller can report the fault rather than
        plotting a fabricated flat line.
        """
        start, stop = self.clamp_range(start_hz, stop_hz)

        if self.is_simulation:
            n = int(np.clip(points, SIM_POINTS_MIN, SIM_POINTS_MAX))
            return self._simulate_sweep(start, stop, n) + (True,)

        n = int(np.clip(points, HW_POINTS_MIN, HW_POINTS_MAX))
        t0 = time.monotonic()

        if self.scan_mode is None:
            mode, freqs, dbm = self._discover_scan_mode(start, stop, n)
            if mode is None:
                self.consecutive_sweep_failures += 1
                return None, None, False
        else:
            freqs, dbm = self._try_scan_mode(self.scan_mode, start, stop, n)

            # Validate every sweep, not just the probe. A firmware mode change
            # or a partially-read response can start returning nonsense at any
            # time, and plotting that silently is the failure this app shipped
            # with.
            if not self._plausible_spectrum(freqs, dbm, start, stop, n):
                self.scan_mode = None
                mode, freqs, dbm = self._discover_scan_mode(start, stop, n)
                if mode is None:
                    self.last_error = self.last_error or "scan returned an implausible spectrum"
                    self.consecutive_sweep_failures += 1
                    return None, None, False

        # Learn how long this device actually dwells per point, so a narrow RBW
        # widens the idle allowance instead of tripping a timeout.
        gap = (time.monotonic() - t0) / max(n, 1)
        if gap > self._slowest_gap:
            self._slowest_gap = min(gap, 20.0)

        self.consecutive_sweep_failures = 0

        if freqs is None or len(freqs) != len(dbm):
            # Firmware spaces samples linearly across the requested span.
            freqs = np.linspace(start, stop, len(dbm))

        return freqs, dbm, True

    # -- simulation ---------------------------------------------------------

    def _simulate_sweep(self, start: float, stop: float, points: int):
        """Generate a plausible, time-varying RF spectrum.

        Deterministic in shape but animated, so the display visibly lives even
        with no hardware attached.
        """
        freqs = np.linspace(start, stop, points)
        span = stop - start
        t = time.time() - self._sim_t0

        # Thermal noise floor with a gentle tilt across the span.
        floor = -103.0 + 3.0 * (freqs - start) / max(span, 1.0)
        dbm = floor + self._sim_rng.normal(0.0, 1.8, points)

        def peak(center_frac, width_frac, amp):
            c = start + span * center_frac
            w = max(span * width_frac, 1.0)
            return amp * np.exp(-(((freqs - c) / w) ** 2))

        # A drifting carrier, a breathing wideband channel, and a fixed CW spur.
        dbm += peak(0.45 + 0.06 * np.sin(t * 0.35), 0.010, 52.0 + 5.0 * np.sin(t * 1.7))
        dbm += peak(0.70, 0.030, 34.0 + 8.0 * np.sin(t * 0.6 + 1.0))
        dbm += peak(0.20, 0.002, 58.0)
        # Occasional bursty interferer.
        burst = 30.0 * max(0.0, np.sin(t * 0.8) - 0.7) / 0.3
        if burst > 0:
            dbm += peak(0.85, 0.006, burst)
        # Broad noise hump around mid-span.
        dbm += 10.0 * np.exp(-(((freqs - (start + span * 0.5)) / (span * 0.35)) ** 2))

        np.clip(dbm, -125.0, 12.0, out=dbm)
        return freqs, dbm

    def _simulated_response(self, cmd: str) -> str:
        """Canned replies so the console and settings dialog behave offline."""
        c = cmd.strip().lower()
        if not c:
            return ""
        if c.startswith("version"):
            return "tinySA4_v1.4-88-g1e2b3c4\nHW Version:V0.4.5.1 (Simulated)"
        if c.startswith("info"):
            return (
                "tinySA ULTRA (Simulated)\n"
                "2019-2024 Copyright @Erik Kaashoek\n"
                "License: GPL version 3\n"
                "Version: tinySA4_v1.4-88\n"
                "Build Time: simulated\n"
            )
        if c.startswith("vbat"):
            return "4123 mV"
        if c.startswith("deviceid"):
            return "deviceid 0"
        if c.startswith(("rbw", "attenuate", "lna", "spur", "mode", "level", "output", "ultra", "pause", "resume", "sweep")):
            return f"{c} applied (simulated)"
        if c.startswith("help"):
            return (
                "commands: version info vbat deviceid scan scanraw sweep rbw "
                "attenuate lna spur mode level output pause resume data marker "
                "trigger capture help"
            )
        return f"[simulated] '{cmd}' accepted"

    def read_settings(self) -> dict:
        """Query the device's current RF settings.

        The panel must reflect the instrument, not the other way round. Pushing
        the UI's defaults on connect would silently rewrite a setup the user had
        already dialled in; showing defaults the device does not have is just as
        wrong, only quieter.

        Bare config commands answer with a usage line followed by the current
        value, e.g. ``usage: rbw 0.2..850|auto`` / ``850kHz``. Anything that
        cannot be parsed is simply omitted.
        """
        settings: dict = {}
        if not self.is_connected:
            return settings

        def current_value(cmd: str) -> str | None:
            ok, text = self.send_command(cmd, budget=2.0)
            if not ok:
                return None
            for line in reversed(text.split("\n")):
                line = line.strip()
                if line and not line.lower().startswith("usage"):
                    return line
            return None

        rbw = current_value("rbw")
        if rbw:
            m = re.search(r"([\d.]+)\s*k?hz", rbw, re.IGNORECASE)
            settings["rbw"] = m.group(1) if m else rbw

        sweep = current_value("sweep")
        if sweep:
            parts = sweep.split()
            if len(parts) >= 2:
                try:
                    settings["start_hz"] = float(parts[0])
                    settings["stop_hz"] = float(parts[1])
                    if len(parts) >= 3:
                        settings["points"] = int(float(parts[2]))
                except ValueError:
                    pass

        vbat = current_value("vbat")
        if vbat:
            settings["vbat"] = vbat

        return settings

    # -- hardware configuration --------------------------------------------

    def set_rbw(self, rbw_val: str) -> tuple[bool, str]:
        """Resolution bandwidth: ``auto`` or a value in kHz."""
        return self.send_command(f"rbw {rbw_val}")

    def set_attenuation(self, atten_val: str) -> tuple[bool, str]:
        """Input attenuator: ``auto`` or 0..31 dB."""
        return self.send_command(f"attenuate {atten_val}")

    def set_lna(self, enabled: bool) -> tuple[bool, str]:
        return self.send_command(f"lna {'on' if enabled else 'off'}")

    def set_spur(self, enabled: bool) -> tuple[bool, str]:
        return self.send_command(f"spur {'on' if enabled else 'off'}")

    def set_input(self, input_mode: str) -> tuple[bool, str]:
        """Select the RF front end.

        TinySA spells this ``mode <low|high> input``; the Ultra's extended range
        is a separate ``ultra on`` toggle.
        """
        m = input_mode.strip().lower()
        if m.startswith("ultra"):
            ok1, r1 = self.send_command("ultra on")
            ok2, r2 = self.send_command("mode low input")
            return (ok1 and ok2), f"{r1}\n{r2}".strip()
        if m.startswith("high"):
            return self.send_command("mode high input")
        ok1, r1 = self.send_command("ultra off")
        ok2, r2 = self.send_command("mode low input")
        return (ok1 and ok2), f"{r1}\n{r2}".strip()

    def set_signal_gen(self, freq_hz: float, level_dbm: float = -10.0, enabled: bool = True):
        """Drive the built-in CW signal generator."""
        if not enabled:
            ok1, r1 = self.send_command("output off")
            ok2, r2 = self.send_command("mode low input")
            return (ok1 or ok2), f"{r1}\n{r2}".strip()
        replies = []
        ok_all = True
        for c in (
            "mode low output",
            f"sweep {int(freq_hz)} {int(freq_hz)} 2",
            f"level {level_dbm:.1f}",
            "output on",
        ):
            ok, r = self.send_command(c)
            ok_all = ok_all and ok
            replies.append(r)
        return ok_all, "\n".join(x for x in replies if x).strip()


# ---------------------------------------------------------------------------
# Acquisition thread -- the ONLY owner of the serial port
# ---------------------------------------------------------------------------


class TinySAWorker(QThread):
    """Background thread that owns the driver and produces sweep frames.

    The GUI never calls the driver. It posts control requests here and pulls
    the most recent frame with :meth:`take_frame` on its own timer. Frames are
    single-slot: if the GUI cannot keep up, older frames are dropped instead of
    piling up in Qt's event queue. That bounded-backlog property is what stops
    the window from locking solid.
    """

    connection_changed = Signal(bool, str)        # (connected, message)
    settings_read = Signal(dict)                  # device's actual RF settings
    command_result = Signal(str, bool, str)       # (command, ok, response)
    stats_updated = Signal(float, float, int)     # (sweeps/s, last sweep ms, dropped)
    fault = Signal(str)                           # transport failure description

    #: Simulated acquisition is essentially free; cap it so we do not spin.
    MAX_SIM_RATE = 30.0

    def __init__(self, driver: TinySADriver):
        super().__init__()
        self.driver = driver

        self._requests: queue.Queue[tuple] = queue.Queue()
        self._state_lock = threading.Lock()
        self._frame: SweepFrame | None = None

        self._running = True
        self._paused = False

        self._start_hz = 2_400_000_000.0
        self._stop_hz = 2_483_500_000.0
        self._points = 201

        self._seq = 0
        self._dropped = 0
        self._fault_reported = False

    # -- GUI-facing API (thread-safe) ---------------------------------------

    def post_connect(self, port: str) -> None:
        self._requests.put(("connect", port))

    def post_disconnect(self) -> None:
        self._requests.put(("disconnect", None))

    def post_command(self, cmd: str) -> None:
        """Run a raw command on the serial thread and emit ``command_result``."""
        self._requests.put(("cmd", cmd))

    def post_setting(self, name: str, value) -> None:
        self._requests.put(("set", (name, value)))

    def set_sweep_range(self, start_hz: float, stop_hz: float, points: int) -> None:
        start, stop = TinySADriver.clamp_range(start_hz, stop_hz)
        with self._state_lock:
            self._start_hz = start
            self._stop_hz = stop
            self._points = int(points)

    def sweep_range(self) -> tuple[float, float, int]:
        with self._state_lock:
            return self._start_hz, self._stop_hz, self._points

    def set_paused(self, paused: bool) -> None:
        with self._state_lock:
            self._paused = bool(paused)

    def is_paused(self) -> bool:
        with self._state_lock:
            return self._paused

    def take_frame(self) -> SweepFrame | None:
        """Remove and return the newest frame, or None if nothing is pending."""
        with self._state_lock:
            f, self._frame = self._frame, None
            return f

    def stop(self) -> None:
        """Stop the thread without any possibility of hanging the caller.

        The driver is told to abort in-flight reads first, so an ordinary close
        during a slow sweep unwinds quickly instead of burning the whole grace
        period. If the thread still will not exit, the port is closed from here
        before resorting to terminate() -- otherwise the device would be left
        paused with its port never closed, which is how it gets stranded.
        """
        self._running = False
        self.driver.request_abort()
        self._requests.put(("quit", None))

        if self.wait(6000):
            return

        # Thread is stuck. Release the hardware ourselves, then kill it.
        try:
            self.driver.disconnect()
        except Exception:
            pass
        if not self.wait(1500):
            self.terminate()
            self.wait(1000)

    # -- thread body --------------------------------------------------------

    def run(self) -> None:
        """Thread body, wrapped so nothing can silently kill acquisition.

        An unhandled exception here used to end the thread while the GUI kept
        ticking a render timer that would never receive another frame -- a
        frozen display with no error anywhere.
        """
        try:
            self._run_loop()
        except Exception as e:
            self.fault.emit(f"acquisition thread crashed: {e!r}")
            self.connection_changed.emit(False, f"Acquisition stopped: {e}")
        finally:
            try:
                self.driver.disconnect()
            except Exception:
                pass

    def _run_loop(self) -> None:
        rate_window_start = time.monotonic()
        sweeps_in_window = 0
        last_stats_emit = 0.0
        last_duration_ms = 0.0

        while self._running:
            self._drain_requests()
            if not self._running:
                break
            # A trailing disconnect() in the loop body is not enough; the
            # normal exit path runs through run()'s finally block.

            with self._state_lock:
                paused = self._paused
                start, stop, points = self._start_hz, self._stop_hz, self._points

            if paused or not self.driver.is_connected:
                self.msleep(40)
                rate_window_start = time.monotonic()
                sweeps_in_window = 0
                continue

            t0 = time.perf_counter()
            freqs, dbm, ok = self.driver.request_sweep(start, stop, points)
            last_duration_ms = (time.perf_counter() - t0) * 1000.0

            if not ok:
                self._handle_acquisition_failure()
                continue

            self._fault_reported = False
            self._seq += 1
            frame = SweepFrame(
                freqs=freqs,
                dbm=dbm,
                simulated=self.driver.is_simulation,
                seq=self._seq,
                acquired_at=time.time(),
                duration_ms=last_duration_ms,
            )
            with self._state_lock:
                if self._frame is not None:
                    # GUI has not consumed the previous frame: drop it. This is
                    # the backpressure that replaces the unbounded signal queue.
                    self._dropped += 1
                self._frame = frame

            sweeps_in_window += 1
            now = time.monotonic()
            elapsed = now - rate_window_start
            if elapsed >= 0.5:
                rate = sweeps_in_window / elapsed
                sweeps_in_window = 0
                rate_window_start = now
                if now - last_stats_emit >= 0.5:
                    self.stats_updated.emit(rate, last_duration_ms, self._dropped)
                    last_stats_emit = now

            # Throttle the simulator so it does not saturate a core.
            if self.driver.is_simulation:
                target = 1.0 / self.MAX_SIM_RATE
                spare = target - (time.perf_counter() - t0)
                if spare > 0:
                    self.msleep(int(spare * 1000))

        self.driver.disconnect()

    #: Failed sweeps in a row before the device is declared lost.
    MAX_SWEEP_FAILURES = 4

    def _handle_acquisition_failure(self) -> None:
        """Report a transport fault once, then give up after a few tries.

        The watchdog counts failed SWEEPS, not failed commands. Counting
        commands could never trip it: any successful command inside the
        discovery chain reset the counter, so a half-dead device looped here
        forever with a frozen plot and no disconnect.
        """
        err = self.driver.last_error or "device stopped responding"
        if not self._fault_reported:
            self._fault_reported = True
            self.fault.emit(err)

        if self.driver.consecutive_sweep_failures >= self.MAX_SWEEP_FAILURES:
            self.driver.disconnect()
            self.connection_changed.emit(False, f"Lost connection to TinySA: {err}")
            self._fault_reported = False
        else:
            self.msleep(250)

    def _drain_requests(self) -> None:
        """Execute every queued control request. Runs on the serial thread."""
        while True:
            try:
                kind, payload = self._requests.get_nowait()
            except queue.Empty:
                return

            if kind == "quit":
                self._running = False
                return

            if kind == "connect":
                ok, msg = self.driver.connect(payload)
                self._fault_reported = False
                self._dropped = 0
                self.connection_changed.emit(ok, msg)
                if ok and not self.driver.is_simulation:
                    # Report what the instrument is actually set to, so the
                    # panel stops showing its own defaults as if they were the
                    # device's state.
                    try:
                        self.settings_read.emit(self.driver.read_settings())
                    except Exception:
                        pass

            elif kind == "disconnect":
                self.driver.disconnect()
                self.connection_changed.emit(False, "TinySA disconnected.")

            elif kind == "cmd":
                ok, resp = self.driver.send_command(payload, budget=3.0)
                if not ok and not resp:
                    resp = f"[no response: {self.driver.last_error}]"
                self.command_result.emit(payload, ok, resp)

            elif kind == "set":
                name, value = payload
                self._apply_setting(name, value)

    def _apply_setting(self, name: str, value) -> None:
        d = self.driver
        try:
            if name == "rbw":
                ok, resp = d.set_rbw(value)
            elif name == "atten":
                ok, resp = d.set_attenuation(value)
            elif name == "lna":
                ok, resp = d.set_lna(bool(value))
            elif name == "spur":
                ok, resp = d.set_spur(bool(value))
            elif name == "input":
                ok, resp = d.set_input(str(value))
            elif name == "siggen":
                freq, level, enabled = value
                ok, resp = d.set_signal_gen(freq, level, enabled)
            else:
                return
        except Exception as e:  # never let a config command kill the thread
            ok, resp = False, str(e)
        self.command_result.emit(f"{name}={value}", ok, resp)
