#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import queue
import re
import shlex
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "Temporal RGBW Calibration Host v7.3.0"
DEFAULT_SERIAL_BAUD = 30000000
DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parent / "captures"
FRAME_HEADER = b"TCAL"
FRAME_MAX_PAYLOAD = 128

KIND_HELLO_REQ = 0x01
KIND_HELLO_RSP = 0x81
KIND_PING_REQ = 0x02
KIND_PING_RSP = 0x82
KIND_CAL_REQ = 0x30
KIND_CAL_RSP = 0xB0
KIND_LOG = 0x90

OP_GET_STATE = 0x00
OP_SET_RENDER_ENABLED = 0x20
OP_SET_FILL = 0x21
OP_CLEAR = 0x23
OP_SET_PHASE = 0x24
OP_COMMIT = 0x26
OP_SET_PHASE_MODE = 0x28
OP_SET_SOLVER_ENABLED = 0x29
OP_SET_TEMPORAL_BLEND = 0x2A
OP_SET_FILL16 = 0x2B

PHASE_MODE_AUTO = 0
PHASE_MODE_MANUAL = 1

MAX_BFI = 4
BLEND_CYCLE_LENGTH = MAX_BFI + 1
MAX_BLEND_CYCLE_LENGTH = 60
PHASE_CONTROL_MAX = MAX_BLEND_CYCLE_LENGTH - 1

GENERIC_PLAN_FIELDS = [
    "name",
    "mode",
    "repeats",
    "r",
    "g",
    "b",
    "w",
    "lower_r",
    "lower_g",
    "lower_b",
    "lower_w",
    "upper_r",
    "upper_g",
    "upper_b",
    "upper_w",
    "r16",
    "g16",
    "b16",
    "w16",
    "bfi_r",
    "bfi_g",
    "bfi_b",
    "bfi_w",
    "use_fill16",
]


@dataclass
class MeasurementPlanRow:
    name: str
    r: int
    g: int
    b: int
    w: int
    bfi_r: int
    bfi_g: int
    bfi_b: int
    bfi_w: int
    repeats: int
    lower_r: int = 0
    lower_g: int = 0
    lower_b: int = 0
    lower_w: int = 0
    upper_r: int = 0
    upper_g: int = 0
    upper_b: int = 0
    upper_w: int = 0
    r16: int = 0
    g16: int = 0
    b16: int = 0
    w16: int = 0
    use_fill16: bool = False
    mode: str = "fill8"

    def normalized_mode(self) -> str:
        if self.mode == "blend8":
            return "blend8"
        if self.use_fill16 or self.mode == "fill16":
            return "fill16"
        return "fill8"

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["mode"] = self.normalized_mode()
        data["use_fill16"] = int(self.normalized_mode() == "fill16")
        return data


class DirectSerialClient:
    def __init__(self, log_queue, noise_filter=None):
        self.log_queue = log_queue
        self.noise_filter = noise_filter
        self.serial_port = None
        self.rx_thread = None
        self.stop_event = threading.Event()
        self.packet_handler = None
        self.write_lock = threading.Lock()

    def _log(self, line: str):
        if self.noise_filter and self.noise_filter(line):
            return
        self.log_queue.put(line)

    def start(self, port: str, baud: int):
        self.stop()
        self.serial_port = serial.Serial(port=port, baudrate=baud, timeout=0.05, write_timeout=1.0)
        self.stop_event.clear()
        self.rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self.rx_thread.start()
        self._log(f"[serial] connected to {port} @ {baud}")

    def stop(self):
        self.stop_event.set()
        if self.serial_port is not None:
            try:
                self.serial_port.close()
            except Exception:
                pass
        self.serial_port = None

    def is_connected(self) -> bool:
        return self.serial_port is not None and self.serial_port.is_open

    def send_frame(self, kind: int, payload: bytes = b""):
        if not self.is_connected():
            raise RuntimeError("Serial device is not connected")
        if len(payload) > FRAME_MAX_PAYLOAD:
            raise ValueError(f"Payload too large: {len(payload)} > {FRAME_MAX_PAYLOAD}")
        frame = bytearray(FRAME_HEADER)
        frame.append(kind & 0xFF)
        frame.append((len(payload) >> 8) & 0xFF)
        frame.append(len(payload) & 0xFF)
        frame.extend(payload)
        crc = 0
        for value in frame[4:]:
            crc ^= value
        frame.append(crc)
        with self.write_lock:
            self.serial_port.write(frame)
            self.serial_port.flush()
        self._log(f"[tx] kind=0x{kind:02X} payload={payload.hex()}")

    def _rx_loop(self):
        buffer = bytearray()
        while not self.stop_event.is_set():
            if self.serial_port is None:
                return
            try:
                chunk = self.serial_port.read(256)
            except serial.SerialException as exc:
                self._log(f"[serial] read error: {exc}")
                return
            if not chunk:
                continue
            buffer.extend(chunk)
            self._consume_frames(buffer)

    def _consume_frames(self, buffer: bytearray):
        while True:
            idx = buffer.find(FRAME_HEADER)
            if idx < 0:
                if len(buffer) > len(FRAME_HEADER):
                    del buffer[:-len(FRAME_HEADER)]
                return
            if idx > 0:
                del buffer[:idx]
            if len(buffer) < 8:
                return
            payload_len = (buffer[5] << 8) | buffer[6]
            if payload_len > FRAME_MAX_PAYLOAD:
                self._log(f"[rx] dropping oversized payload {payload_len}")
                del buffer[0]
                continue
            frame_len = 4 + 1 + 2 + payload_len + 1
            if len(buffer) < frame_len:
                return
            frame = bytes(buffer[:frame_len])
            del buffer[:frame_len]
            crc = 0
            for value in frame[4:-1]:
                crc ^= value
            if crc != frame[-1]:
                self._log("[rx] crc mismatch, dropping frame")
                continue
            kind = frame[4]
            payload = frame[7:-1]
            self._handle_frame(kind, payload)

    def _handle_frame(self, kind: int, payload: bytes):
        if kind == KIND_LOG:
            text = payload.decode("utf-8", errors="replace")
            self._log(f"[device] {text}")
            msg = {"type": "device_log", "text": text}
        elif kind == KIND_HELLO_RSP:
            text = payload.decode("utf-8", errors="replace")
            msg = {"type": "hello", "text": text}
            self._log(f"[rx] hello={text}")
        elif kind == KIND_PING_RSP:
            text = payload.decode("utf-8", errors="replace")
            msg = {"type": "ping", "text": text}
            self._log(f"[rx] ping={text}")
        elif kind == KIND_CAL_RSP:
            msg = {
                "type": "cal_response",
                "op": payload[0] if len(payload) > 0 else None,
                "status": payload[1] if len(payload) > 1 else None,
                "render_enabled": payload[2] if len(payload) > 2 else None,
                "manual_phase_mode": payload[3] if len(payload) > 3 else None,
                "phase": payload[4] if len(payload) > 4 else None,
                "payload_hex": payload.hex(),
            }
            if msg["op"] is not None and msg["status"] is not None:
                self._log(f"[rx] cal op=0x{msg['op']:02X} status=0x{msg['status']:02X} phase={msg['phase']}")
            else:
                self._log(f"[rx] cal payload={payload.hex()}")
        else:
            msg = {"type": "frame", "kind": kind, "payload_hex": payload.hex()}
            self._log(f"[rx] kind=0x{kind:02X} payload={payload.hex()}")
        if self.packet_handler is not None:
            try:
                self.packet_handler(msg)
            except Exception as exc:
                self._log(f"[rx] packet handler error: {exc}")

    @staticmethod
    def available_ports() -> list[str]:
        return [port.device for port in serial.tools.list_ports.comports()]


class ArgyllRunner:
    XYZ_RE = re.compile(r"XYZ:\s*([0-9.+\-eE]+)\s+([0-9.+\-eE]+)\s+([0-9.+\-eE]+)", re.I)
    YXY_RE = re.compile(r"Yxy:\s*([0-9.+\-eE]+)\s+([0-9.+\-eE]+)\s+([0-9.+\-eE]+)", re.I)

    def __init__(self, log_queue):
        self.log_queue = log_queue
        self.active_proc = None
        self.lock = threading.Lock()

    def cleanup_stale_processes(self):
        self.log_queue.put("[argyll] cleaning stale spotread")
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/IM", "spotread.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["pkill", "-f", "spotread"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.75)

    def abort_active(self):
        with self.lock:
            proc = self.active_proc
            self.active_proc = None
        if proc is None:
            self.log_queue.put("[argyll] no active process")
            return
        self.log_queue.put(f"[argyll] aborting pid={proc.pid}")
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass
        time.sleep(0.75)

    def run_spotread(self, command, timeout_s=45.0, send_trigger_newline=True, cleanup_first=True):
        if cleanup_first:
            self.cleanup_stale_processes()
        args = shlex.split(command, posix=False)
        self.log_queue.put(f"[argyll] running: {args!r}")
        started = time.time()
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags,
        )
        with self.lock:
            self.active_proc = proc
        stdout = ""
        stderr = ""
        timed_out = False
        try:
            if send_trigger_newline and proc.stdin is not None:
                time.sleep(0.2)
                proc.stdin.write("\n")
                proc.stdin.flush()
                self.log_queue.put("[argyll] sent newline trigger")
            stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            self.log_queue.put("[argyll] timeout expired, terminating")
            try:
                proc.terminate()
                stdout, stderr = proc.communicate(timeout=3)
            except Exception:
                try:
                    proc.kill()
                    stdout, stderr = proc.communicate(timeout=3)
                except Exception:
                    pass
        finally:
            with self.lock:
                if self.active_proc is proc:
                    self.active_proc = None
        result = {
            "ok": (proc.returncode == 0) and (not timed_out),
            "returncode": proc.returncode,
            "elapsed_s": time.time() - started,
            "stdout": stdout or "",
            "stderr": stderr or "",
            "timed_out": timed_out,
            "pid": proc.pid,
            "command": args,
        }
        match = self.XYZ_RE.search(result["stdout"])
        if match:
            result["X"] = float(match.group(1))
            result["Y_from_XYZ"] = float(match.group(2))
            result["Z"] = float(match.group(3))
        match = self.YXY_RE.search(result["stdout"])
        if match:
            result["Y"] = float(match.group(1))
            result["x"] = float(match.group(2))
            result["y"] = float(match.group(3))
        self.log_queue.put(f"[argyll] done rc={proc.returncode} timeout={timed_out}")
        time.sleep(0.75)
        return result


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1440x920")
        self.root.minsize(1240, 760)
        self.log_queue = queue.Queue()
        self.show_transport_spam_var = tk.BooleanVar(value=False)
        self.device = DirectSerialClient(self.log_queue, noise_filter=self.should_filter_transport_log)
        self.device.packet_handler = self.on_device_packet
        self.argyll = ArgyllRunner(self.log_queue)
        self.current_status = {}
        self.measurement_rows: list[MeasurementPlanRow] = []
        self.capture_dir = DEFAULT_ARTIFACT_DIR
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.last_measurement = None
        self.running_plan = False
        self.plan_pause_event = threading.Event()
        self.plan_stop_event = threading.Event()
        self.plan_report_path: Path | None = None
        self.resume_capture_path: Path | None = None
        self.plan_source_path: Path | None = None
        self.build_ui()
        self.refresh_serial_ports()
        self._start_log_pump()

    def should_filter_transport_log(self, line: str) -> bool:
        if self.show_transport_spam_var.get():
            return False
        return line.startswith("[tx]") or line.startswith("[rx]") or line.startswith("[serial]")

    def build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="both", expand=True)

        controls = ttk.LabelFrame(top, text="Connection")
        controls.pack(fill="x")

        self.serial_port_var = tk.StringVar(value="")
        self.serial_baud_var = tk.StringVar(value=str(DEFAULT_SERIAL_BAUD))
        self.argyll_cmd_var = tk.StringVar(value="spotread -x -O")
        self.phase_mode_var = tk.IntVar(value=PHASE_MODE_AUTO)
        self.phase_var = tk.IntVar(value=0)
        self.settle_delay_var = tk.DoubleVar(value=0.25)
        self.timeout_var = tk.DoubleVar(value=45.0)
        self.cleanup_first_var = tk.BooleanVar(value=True)
        self.send_newline_var = tk.BooleanVar(value=True)
        self.use_fill16_var = tk.BooleanVar(value=False)
        self.plan_use_solver_var = tk.BooleanVar(value=False)
        self.resume_row_var = tk.IntVar(value=0)
        self.resume_repeat_var = tk.IntVar(value=0)
        self.resume_report_text = tk.StringVar(value="resume: none")

        row = ttk.Frame(controls)
        row.pack(fill="x", padx=8, pady=6)
        ttk.Label(row, text="Serial port").pack(side="left")
        self.serial_port_combo = ttk.Combobox(row, textvariable=self.serial_port_var, width=24)
        self.serial_port_combo.pack(side="left", padx=4)
        ttk.Button(row, text="Refresh", command=self.refresh_serial_ports).pack(side="left", padx=4)
        ttk.Label(row, text="Baud").pack(side="left", padx=(12, 0))
        ttk.Entry(row, textvariable=self.serial_baud_var, width=12).pack(side="left", padx=4)
        ttk.Button(row, text="Connect", command=self.connect_device).pack(side="left", padx=8)
        ttk.Button(row, text="Hello", command=self.send_hello).pack(side="left", padx=4)
        ttk.Button(row, text="Ping", command=self.send_ping).pack(side="left", padx=4)
        ttk.Button(row, text="Get State", command=self.get_state).pack(side="left", padx=4)

        cmdrow = ttk.Frame(controls)
        cmdrow.pack(fill="x", padx=8, pady=6)
        ttk.Label(cmdrow, text="Argyll command").pack(side="left")
        ttk.Entry(cmdrow, textvariable=self.argyll_cmd_var).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(cmdrow, text="Capture dir", command=self.choose_capture_dir).pack(side="left", padx=4)

        opts = ttk.Frame(controls)
        opts.pack(fill="x", padx=8, pady=6)
        ttk.Label(opts, text="Settle s").pack(side="left")
        ttk.Entry(opts, textvariable=self.settle_delay_var, width=8).pack(side="left", padx=4)
        ttk.Label(opts, text="Timeout s").pack(side="left")
        ttk.Entry(opts, textvariable=self.timeout_var, width=8).pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="Cleanup stale before read", variable=self.cleanup_first_var).pack(side="left", padx=8)
        ttk.Checkbutton(opts, text="Send newline trigger", variable=self.send_newline_var).pack(side="left", padx=8)
        ttk.Checkbutton(opts, text="Show transport spam", variable=self.show_transport_spam_var).pack(side="left", padx=8)
        ttk.Checkbutton(opts, text="Plan uses solver mode", variable=self.plan_use_solver_var).pack(side="left", padx=8)
        ttk.Button(opts, text="Kill stale spotread", command=self.kill_stale).pack(side="left", padx=8)
        ttk.Button(opts, text="Abort Measurement", command=self.abort_measurement).pack(side="left", padx=4)

        resume = ttk.Frame(controls)
        resume.pack(fill="x", padx=8, pady=6)
        ttk.Label(resume, text="Resume row").pack(side="left")
        ttk.Entry(resume, textvariable=self.resume_row_var, width=8).pack(side="left", padx=4)
        ttk.Label(resume, text="Resume repeat").pack(side="left")
        ttk.Entry(resume, textvariable=self.resume_repeat_var, width=8).pack(side="left", padx=4)
        ttk.Button(resume, text="Load report", command=self.load_progress_report).pack(side="left", padx=8)
        ttk.Label(resume, textvariable=self.resume_report_text).pack(side="left", padx=8)

        mid = ttk.PanedWindow(top, orient="horizontal")
        mid.pack(fill="both", expand=True, pady=8)

        left = ttk.Frame(mid)
        right = ttk.Frame(mid)
        mid.add(left, weight=1)
        mid.add(right, weight=4)

        self.build_render_panel(left)

        right_split = ttk.PanedWindow(right, orient="vertical")
        right_split.pack(fill="both", expand=True)
        plan_frame = ttk.Frame(right_split)
        log_frame = ttk.Frame(right_split)
        right_split.add(plan_frame, weight=3)
        right_split.add(log_frame, weight=1)

        self.build_plan_panel(plan_frame)
        self.build_log_panel(log_frame)

    def refresh_serial_ports(self):
        ports = DirectSerialClient.available_ports()
        self.serial_port_combo["values"] = ports
        if not self.serial_port_var.get() and ports:
            self.serial_port_var.set(ports[0])
        self.log_queue.put(f"[serial] found ports: {ports}")

    def _make_int_scale(self, parent, label, variable, maxv, length=220):
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=8, pady=2)
        ttk.Label(row, text=label, width=8).pack(side="left")
        scale = tk.Scale(row, from_=0, to=maxv, variable=variable, orient="horizontal", resolution=1, showvalue=False, command=lambda _v: self._round_var(variable))
        scale.configure(length=length)
        scale.pack(side="left", fill="x", expand=True)
        ttk.Entry(row, textvariable=variable, width=8).pack(side="left", padx=4)

    def _round_var(self, var):
        try:
            var.set(int(round(float(var.get()))))
        except Exception:
            pass
        self.update_preview()

    def build_render_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Render / Manual Control")
        box.pack(fill="x", pady=6)

        self.manual_mode_var = tk.StringVar(value="fill8")
        self.r_var = tk.IntVar(value=0)
        self.g_var = tk.IntVar(value=0)
        self.b_var = tk.IntVar(value=0)
        self.w_var = tk.IntVar(value=0)
        self.lower_r_var = tk.IntVar(value=0)
        self.lower_g_var = tk.IntVar(value=0)
        self.lower_b_var = tk.IntVar(value=0)
        self.lower_w_var = tk.IntVar(value=0)
        self.r16_var = tk.IntVar(value=0)
        self.g16_var = tk.IntVar(value=0)
        self.b16_var = tk.IntVar(value=0)
        self.w16_var = tk.IntVar(value=0)
        self.bfi_r_var = tk.IntVar(value=0)
        self.bfi_g_var = tk.IntVar(value=0)
        self.bfi_b_var = tk.IntVar(value=0)
        self.bfi_w_var = tk.IntVar(value=0)

        mode_row = ttk.Frame(box)
        mode_row.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(mode_row, text="Mode").pack(side="left")
        ttk.Radiobutton(mode_row, text="Fill8", variable=self.manual_mode_var, value="fill8", command=self._on_manual_mode_changed).pack(side="left", padx=6)
        ttk.Radiobutton(mode_row, text="Blend8", variable=self.manual_mode_var, value="blend8", command=self._on_manual_mode_changed).pack(side="left", padx=6)
        ttk.Radiobutton(mode_row, text="Fill16", variable=self.manual_mode_var, value="fill16", command=self._on_manual_mode_changed).pack(side="left", padx=6)

        tabs = ttk.Notebook(box)
        tabs.pack(fill="x", padx=8, pady=4)
        base_tab = ttk.Frame(tabs)
        true16_tab = ttk.Frame(tabs)
        tabs.add(base_tab, text="8-bit / Blend8")
        tabs.add(true16_tab, text="True16")

        for label, var, maxv in [("R", self.r_var, 255), ("G", self.g_var, 255), ("B", self.b_var, 255), ("W", self.w_var, 255)]:
            self._make_int_scale(base_tab, label, var, maxv, length=180)

        blend8 = ttk.LabelFrame(base_tab, text="Blend8 lower / previous value")
        blend8.pack(fill="x", padx=8, pady=6)
        for label, var in [("Floor R", self.lower_r_var), ("Floor G", self.lower_g_var), ("Floor B", self.lower_b_var), ("Floor W", self.lower_w_var)]:
            self._make_int_scale(blend8, label, var, 255, length=180)

        bfi_box = ttk.LabelFrame(base_tab, text="BFI insertion counts")
        bfi_box.pack(fill="x", padx=8, pady=6)
        for label, var, maxv in [("BFI R", self.bfi_r_var, MAX_BFI), ("BFI G", self.bfi_g_var, MAX_BFI), ("BFI B", self.bfi_b_var, MAX_BFI), ("BFI W", self.bfi_w_var, MAX_BFI)]:
            self._make_int_scale(bfi_box, label, var, maxv, length=180)

        fill16 = ttk.LabelFrame(true16_tab, text="True 16-bit patch values")
        fill16.pack(fill="x", padx=8, pady=6)
        for txt, var in [("R16", self.r16_var), ("G16", self.g16_var), ("B16", self.b16_var), ("W16", self.w16_var)]:
            row = ttk.Frame(fill16)
            row.pack(fill="x", padx=4, pady=2)
            ttk.Label(row, text=txt, width=8).pack(side="left")
            scale = tk.Scale(row, from_=0, to=65535, variable=var, orient="horizontal", resolution=1, showvalue=False, command=lambda _v: self._sync_preview_from_16())
            scale.configure(length=180)
            scale.pack(side="left", fill="x", expand=True)
            ttk.Entry(row, textvariable=var, width=10).pack(side="left", padx=4)

        phase_box = ttk.Frame(box)
        phase_box.pack(fill="x", padx=8, pady=6)
        ttk.Label(phase_box, text="Phase mode").pack(side="left")
        ttk.Radiobutton(phase_box, text="Auto", variable=self.phase_mode_var, value=PHASE_MODE_AUTO, command=self.send_phase_mode).pack(side="left", padx=4)
        ttk.Radiobutton(phase_box, text="Manual", variable=self.phase_mode_var, value=PHASE_MODE_MANUAL, command=self.send_phase_mode).pack(side="left", padx=4)
        ttk.Label(phase_box, text="Phase index").pack(side="left", padx=(16, 4))
        tk.Scale(phase_box, from_=0, to=PHASE_CONTROL_MAX, variable=self.phase_var, orient="horizontal", resolution=1, showvalue=False, command=lambda _v: self._round_var(self.phase_var)).pack(side="left", fill="x", expand=True)
        ttk.Entry(phase_box, textvariable=self.phase_var, width=8).pack(side="left", padx=4)
        ttk.Button(phase_box, text="Apply phase", command=self.send_phase).pack(side="left", padx=4)

        btns = ttk.Frame(box)
        btns.pack(fill="x", padx=8, pady=8)
        ttk.Button(btns, text="Send State", command=self.send_fill).pack(side="left", padx=4)
        ttk.Button(btns, text="Commit", command=self.commit).pack(side="left", padx=4)
        ttk.Button(btns, text="Clear", command=self.clear).pack(side="left", padx=4)
        ttk.Button(btns, text="Measure Once", command=self.measure_once).pack(side="left", padx=12)

        pv = ttk.Frame(box)
        pv.pack(fill="x", padx=8, pady=8)
        current_box = ttk.Frame(pv)
        current_box.pack(side="left")
        ttk.Label(current_box, text="Upper / current").pack(anchor="w")
        self.preview_canvas = tk.Canvas(current_box, width=90, height=48, bg="#000000", highlightthickness=1, highlightbackground="#999")
        self.preview_canvas.pack(side="left")
        lower_box = ttk.Frame(pv)
        lower_box.pack(side="left", padx=(12, 0))
        ttk.Label(lower_box, text="Lower / previous").pack(anchor="w")
        self.lower_preview_canvas = tk.Canvas(lower_box, width=90, height=48, bg="#000000", highlightthickness=1, highlightbackground="#999")
        self.lower_preview_canvas.pack(side="left")
        self.preview_text = tk.StringVar(value="Preview RGB")
        ttk.Label(pv, textvariable=self.preview_text).pack(side="left", padx=12)

        status = ttk.Frame(box)
        status.pack(fill="x", padx=8, pady=6)
        self.status_text = tk.StringVar(value="status: idle")
        ttk.Label(status, textvariable=self.status_text).pack(side="left")
        self.measurement_text = tk.StringVar(value="last measurement: none")
        ttk.Label(status, textvariable=self.measurement_text).pack(side="left", padx=16)
        self.update_preview()

    def build_log_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Logs")
        box.pack(fill="both", expand=True, pady=6)
        self.log = tk.Text(box, height=10, wrap="word")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    def build_plan_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Measurement Plan")
        box.pack(fill="both", expand=True, pady=6)
        toolbar = ttk.Frame(box)
        toolbar.pack(fill="x", padx=6, pady=6)
        ttk.Button(toolbar, text="Add current", command=self.add_current_to_plan).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Import plan CSV", command=self.import_plan_csv).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Clear plan", command=self.clear_plan).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Delete selected", command=self.delete_selected_plan_rows).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Run plan", command=self.run_plan).pack(side="left", padx=8)
        ttk.Button(toolbar, text="Pause/Resume", command=self.toggle_pause_plan).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Stop", command=self.stop_plan).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Save plan CSV", command=self.save_plan_csv).pack(side="left", padx=4)
        cols = ("name", "mode", "rgbw", "rgbw16", "bfi", "lower", "upper", "timing", "repeats")
        tree_frame = ttk.Frame(box)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=6)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=16, selectmode="extended")
        widths = {"name": 200, "mode": 78, "rgbw": 110, "rgbw16": 180, "bfi": 90, "lower": 130, "upper": 130, "timing": 100, "repeats": 60}
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=widths.get(col, 70), stretch=(col in {"name", "rgbw16", "lower", "upper"}), anchor="center")
        self.tree.column("name", anchor="w")
        self.tree.bind("<<TreeviewSelect>>", self.on_plan_selection)

        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

    def _start_log_pump(self):
        def inner():
            try:
                while True:
                    self.log.insert("end", self.log_queue.get_nowait() + "\n")
                    self.log.see("end")
            except queue.Empty:
                pass
            self.root.after(100, inner)

        inner()

    def connect_device(self):
        try:
            port = self.serial_port_var.get().strip()
            if not port:
                raise ValueError("Select a serial port first")
            self.device.start(port, int(self.serial_baud_var.get().strip()))
        except Exception as exc:
            messagebox.showerror("Connect failed", str(exc))

    def _on_manual_mode_changed(self):
        self.use_fill16_var.set(self.manual_mode_var.get() == "fill16")
        self.update_preview()

    def set_preview_values(self, r, g, b, w, bfi_r, bfi_g, bfi_b, bfi_w, r16=None, g16=None, b16=None, w16=None, mode="fill8", lower_r=0, lower_g=0, lower_b=0, lower_w=0):
        self.manual_mode_var.set(mode)
        self.use_fill16_var.set(mode == "fill16")
        self.r_var.set(int(r))
        self.g_var.set(int(g))
        self.b_var.set(int(b))
        self.w_var.set(int(w))
        self.lower_r_var.set(int(lower_r))
        self.lower_g_var.set(int(lower_g))
        self.lower_b_var.set(int(lower_b))
        self.lower_w_var.set(int(lower_w))
        self.r16_var.set(int(r16) if r16 is not None else int(r) * 257)
        self.g16_var.set(int(g16) if g16 is not None else int(g) * 257)
        self.b16_var.set(int(b16) if b16 is not None else int(b) * 257)
        self.w16_var.set(int(w16) if w16 is not None else int(w) * 257)
        self.bfi_r_var.set(int(bfi_r))
        self.bfi_g_var.set(int(bfi_g))
        self.bfi_b_var.set(int(bfi_b))
        self.bfi_w_var.set(int(bfi_w))
        self.update_preview()

    def _sync_preview_from_16(self):
        self.r_var.set(int((self.r16_var.get() * 255 + 32767) // 65535))
        self.g_var.set(int((self.g16_var.get() * 255 + 32767) // 65535))
        self.b_var.set(int((self.b16_var.get() * 255 + 32767) // 65535))
        self.w_var.set(int((self.w16_var.get() * 255 + 32767) // 65535))
        self.update_preview()

    @staticmethod
    def _preview_rgb_with_white(r, g, b, w):
        r8 = max(0, min(255, int(r) + int(w)))
        g8 = max(0, min(255, int(g) + int(w)))
        b8 = max(0, min(255, int(b) + int(w)))
        return r8, g8, b8

    def update_preview(self):
        r = int(self.r_var.get())
        g = int(self.g_var.get())
        b = int(self.b_var.get())
        w = int(self.w_var.get())
        lower_r = int(self.lower_r_var.get())
        lower_g = int(self.lower_g_var.get())
        lower_b = int(self.lower_b_var.get())
        lower_w = int(self.lower_w_var.get())
        mode = self.manual_mode_var.get()
        preview_r, preview_g, preview_b = self._preview_rgb_with_white(r, g, b, w)
        lower_preview_r, lower_preview_g, lower_preview_b = self._preview_rgb_with_white(lower_r, lower_g, lower_b, lower_w)
        self.preview_canvas.configure(bg=f"#{preview_r:02x}{preview_g:02x}{preview_b:02x}")
        self.lower_preview_canvas.configure(bg=f"#{lower_preview_r:02x}{lower_preview_g:02x}{lower_preview_b:02x}")
        if mode == "blend8":
            self.preview_text.set(f"BLEND8 upper=({r},{g},{b},{self.w_var.get()}) lower=({self.lower_r_var.get()},{self.lower_g_var.get()},{self.lower_b_var.get()},{self.lower_w_var.get()}) BFI=({self.bfi_r_var.get()},{self.bfi_g_var.get()},{self.bfi_b_var.get()},{self.bfi_w_var.get()})")
        elif mode == "fill16":
            self.preview_text.set(f"FILL16 RGBW16=({self.r16_var.get()},{self.g16_var.get()},{self.b16_var.get()},{self.w16_var.get()}) RGBW8=({r},{g},{b},{self.w_var.get()})")
        else:
            self.preview_text.set(f"FILL8 RGBW=({r},{g},{b},{self.w_var.get()}) BFI=({self.bfi_r_var.get()},{self.bfi_g_var.get()},{self.bfi_b_var.get()},{self.bfi_w_var.get()})")

    def send_hello(self):
        self.device.send_frame(KIND_HELLO_REQ, b"")

    def send_ping(self):
        self.device.send_frame(KIND_PING_REQ, b"host-ping")

    def get_state(self):
        self.device.send_frame(KIND_CAL_REQ, bytes([OP_GET_STATE]))

    def send_phase_mode(self):
        self.device.send_frame(KIND_CAL_REQ, bytes([OP_SET_PHASE_MODE, self.phase_mode_var.get() & 0xFF]))

    def send_phase(self):
        phase = max(0, min(PHASE_CONTROL_MAX, int(self.phase_var.get())))
        self.phase_var.set(phase)
        self.device.send_frame(KIND_CAL_REQ, bytes([OP_SET_PHASE, phase]))

    def _pack_u16(self, value: int) -> bytes:
        value = max(0, min(65535, int(value)))
        return bytes([(value >> 8) & 0xFF, value & 0xFF])

    def _build_fill_payload(self, row: MeasurementPlanRow | None = None) -> bytes:
        if row is None:
            mode = self.manual_mode_var.get()
            if mode == "blend8":
                return self._build_blend8_payload(self._build_manual_row())
            if mode == "fill16":
                payload = bytearray([OP_SET_FILL16])
                for value in [self.r16_var.get(), self.g16_var.get(), self.b16_var.get(), self.w16_var.get()]:
                    payload.extend(self._pack_u16(value))
                return bytes(payload)
            return bytes([OP_SET_FILL, self.r_var.get() & 0xFF, self.g_var.get() & 0xFF, self.b_var.get() & 0xFF, self.w_var.get() & 0xFF, self.bfi_r_var.get() & 0xFF, self.bfi_g_var.get() & 0xFF, self.bfi_b_var.get() & 0xFF, self.bfi_w_var.get() & 0xFF])
        mode = row.normalized_mode()
        if mode == "blend8":
            return self._build_blend8_payload(row)
        if mode == "fill16":
            payload = bytearray([OP_SET_FILL16])
            for value in [row.r16, row.g16, row.b16, row.w16]:
                payload.extend(self._pack_u16(value))
            return bytes(payload)
        return bytes([OP_SET_FILL, row.r & 0xFF, row.g & 0xFF, row.b & 0xFF, row.w & 0xFF, row.bfi_r & 0xFF, row.bfi_g & 0xFF, row.bfi_b & 0xFF, row.bfi_w & 0xFF])

    def _build_blend8_payload(self, row: MeasurementPlanRow) -> bytes:
        return bytes([
            OP_SET_TEMPORAL_BLEND,
            row.lower_r & 0xFF,
            row.lower_g & 0xFF,
            row.lower_b & 0xFF,
            row.lower_w & 0xFF,
            row.upper_r & 0xFF,
            row.upper_g & 0xFF,
            row.upper_b & 0xFF,
            row.upper_w & 0xFF,
            row.bfi_r & 0xFF,
            row.bfi_g & 0xFF,
            row.bfi_b & 0xFF,
            row.bfi_w & 0xFF,
        ])

    def _build_manual_row(self) -> MeasurementPlanRow:
        mode = self.manual_mode_var.get()
        r = int(self.r_var.get())
        g = int(self.g_var.get())
        b = int(self.b_var.get())
        w = int(self.w_var.get())
        r16 = int(self.r16_var.get()) if mode == "fill16" else (r * 257)
        g16 = int(self.g16_var.get()) if mode == "fill16" else (g * 257)
        b16 = int(self.b16_var.get()) if mode == "fill16" else (b * 257)
        w16 = int(self.w16_var.get()) if mode == "fill16" else (w * 257)
        return MeasurementPlanRow(
            name="manual",
            r=r,
            g=g,
            b=b,
            w=w,
            bfi_r=int(self.bfi_r_var.get()),
            bfi_g=int(self.bfi_g_var.get()),
            bfi_b=int(self.bfi_b_var.get()),
            bfi_w=int(self.bfi_w_var.get()),
            repeats=1,
            lower_r=int(self.lower_r_var.get()),
            lower_g=int(self.lower_g_var.get()),
            lower_b=int(self.lower_b_var.get()),
            lower_w=int(self.lower_w_var.get()),
            upper_r=r,
            upper_g=g,
            upper_b=b,
            upper_w=w,
            r16=r16,
            g16=g16,
            b16=b16,
            w16=w16,
            use_fill16=(mode == "fill16"),
            mode=mode,
        )

    def send_fill(self):
        self.device.send_frame(KIND_CAL_REQ, self._build_fill_payload())

    def clear(self):
        self.device.send_frame(KIND_CAL_REQ, bytes([OP_CLEAR]))

    def commit(self):
        self.device.send_frame(KIND_CAL_REQ, bytes([OP_COMMIT]))

    def kill_stale(self):
        threading.Thread(target=self.argyll.cleanup_stale_processes, daemon=True).start()

    def abort_measurement(self):
        threading.Thread(target=self.argyll.abort_active, daemon=True).start()

    def choose_capture_dir(self):
        chosen = filedialog.askdirectory(initialdir=str(self.capture_dir))
        if chosen:
            self.capture_dir = Path(chosen)
            self.capture_dir.mkdir(parents=True, exist_ok=True)
            self.log_queue.put(f"[fs] capture dir = {self.capture_dir}")

    def on_device_packet(self, msg):
        self.current_status = msg
        self.status_text.set(f"status: {msg.get('type')}")

    def infer_repeats(self, r, g, b, w):
        y = 0.2126 * (r / 255.0) + 0.7152 * (g / 255.0) + 0.0722 * (b / 255.0) + 1.0 * (w / 255.0)
        if y > 0.5:
            return 1
        if y > 0.15:
            return 2
        if y > 0.03:
            return 4
        return 8

    def _q16_to_u8(self, value):
        q16 = max(0, min(65535, int(value)))
        return int((q16 * 255 + 32767) // 65535)

    def _parse_bool(self, value):
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    def _normalize_mode(self, rec: dict[str, object]) -> str:
        mode = str(rec.get("mode", "")).strip().lower()
        if mode and mode not in {"blend8", "fill16", "fill8"}:
            raise ValueError(f"unsupported mode '{mode}'")
        if mode in {"blend8", "fill16", "fill8"}:
            return mode
        if any(str(rec.get(field, "")).strip() for field in ["lower_r", "upper_r", "lower_g", "upper_g", "lower_b", "upper_b", "lower_w", "upper_w"]):
            return "blend8"
        if self._parse_bool(rec.get("use_fill16", "0")):
            return "fill16"
        return "fill8"

    def _tree_values_for_row(self, row: MeasurementPlanRow):
        lower = ""
        upper = ""
        timing = ""
        if row.normalized_mode() == "blend8":
            lower = f"{row.lower_r}/{row.lower_g}/{row.lower_b}/{row.lower_w}"
            upper = f"{row.upper_r}/{row.upper_g}/{row.upper_b}/{row.upper_w}"
            timing = f"{row.bfi_r}/{row.bfi_g}/{row.bfi_b}/{row.bfi_w}"
        return (
            row.name,
            row.normalized_mode(),
            f"{row.r}/{row.g}/{row.b}/{row.w}",
            f"{row.r16}/{row.g16}/{row.b16}/{row.w16}",
            f"{row.bfi_r}/{row.bfi_g}/{row.bfi_b}/{row.bfi_w}",
            lower,
            upper,
            timing,
            row.repeats,
        )

    def add_plan_row(self, row: MeasurementPlanRow):
        self.measurement_rows.append(row)
        self.tree.insert("", "end", values=self._tree_values_for_row(row))

    def add_current_to_plan(self):
        row = self._build_manual_row()
        row.name = f"state_{len(self.measurement_rows):04d}"
        row.repeats = self.infer_repeats(row.r, row.g, row.b, row.w)
        self.add_plan_row(row)

    def on_plan_selection(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        try:
            idx = self.tree.index(selected[0])
        except Exception:
            return
        if not (0 <= idx < len(self.measurement_rows)):
            return
        row = self.measurement_rows[idx]
        self.set_preview_values(
            row.r,
            row.g,
            row.b,
            row.w,
            row.bfi_r,
            row.bfi_g,
            row.bfi_b,
            row.bfi_w,
            r16=row.r16,
            g16=row.g16,
            b16=row.b16,
            w16=row.w16,
            mode=row.normalized_mode(),
            lower_r=row.lower_r,
            lower_g=row.lower_g,
            lower_b=row.lower_b,
            lower_w=row.lower_w,
        )

    def _clear_plan_rows(self):
        self.measurement_rows.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _reset_resume_state(self, report_label: str = "resume: none"):
        self.resume_row_var.set(0)
        self.resume_repeat_var.set(0)
        self.resume_capture_path = None
        self.plan_report_path = None
        self.resume_report_text.set(report_label)

    def clear_plan(self):
        if not self.measurement_rows:
            return
        if not messagebox.askyesno("Clear plan", "Remove all plan entries?"):
            return
        self._clear_plan_rows()
        self._reset_resume_state()
        self.log_queue.put("[plan] cleared all entries")

    def delete_selected_plan_rows(self):
        selected = list(self.tree.selection())
        if not selected:
            return
        indices = []
        for iid in selected:
            try:
                indices.append(self.tree.index(iid))
            except Exception:
                pass
        for iid in selected:
            self.tree.delete(iid)
        if indices:
            remove_set = set(indices)
            self.measurement_rows = [row for i, row in enumerate(self.measurement_rows) if i not in remove_set]
            self.log_queue.put(f"[plan] deleted {len(remove_set)} selected entries")

    def _dict_int(self, rec, key, default=0):
        value = rec.get(key, default)
        if value in (None, ""):
            return int(default)
        return int(value)

    def _row_from_record(self, rec: dict[str, str]) -> MeasurementPlanRow:
        mode = self._normalize_mode(rec)
        lower_r = self._dict_int(rec, "lower_r", 0)
        lower_g = self._dict_int(rec, "lower_g", 0)
        lower_b = self._dict_int(rec, "lower_b", 0)
        lower_w = self._dict_int(rec, "lower_w", 0)
        upper_r = self._dict_int(rec, "upper_r", self._dict_int(rec, "r", 0))
        upper_g = self._dict_int(rec, "upper_g", self._dict_int(rec, "g", 0))
        upper_b = self._dict_int(rec, "upper_b", self._dict_int(rec, "b", 0))
        upper_w = self._dict_int(rec, "upper_w", self._dict_int(rec, "w", 0))
        r16 = self._dict_int(rec, "r16", self._dict_int(rec, "r", 0) * 257)
        g16 = self._dict_int(rec, "g16", self._dict_int(rec, "g", 0) * 257)
        b16 = self._dict_int(rec, "b16", self._dict_int(rec, "b", 0) * 257)
        w16 = self._dict_int(rec, "w16", self._dict_int(rec, "w", 0) * 257)
        if mode == "blend8":
            r = upper_r
            g = upper_g
            b = upper_b
            w = upper_w
            r16 = upper_r * 257
            g16 = upper_g * 257
            b16 = upper_b * 257
            w16 = upper_w * 257
        else:
            r = self._dict_int(rec, "r", self._q16_to_u8(r16))
            g = self._dict_int(rec, "g", self._q16_to_u8(g16))
            b = self._dict_int(rec, "b", self._q16_to_u8(b16))
            w = self._dict_int(rec, "w", self._q16_to_u8(w16))
        return MeasurementPlanRow(name=str(rec.get("name", f"state_{len(self.measurement_rows):04d}")), r=r, g=g, b=b, w=w, bfi_r=self._dict_int(rec, "bfi_r", 0), bfi_g=self._dict_int(rec, "bfi_g", 0), bfi_b=self._dict_int(rec, "bfi_b", 0), bfi_w=self._dict_int(rec, "bfi_w", 0), repeats=max(1, self._dict_int(rec, "repeats", 1)), lower_r=lower_r, lower_g=lower_g, lower_b=lower_b, lower_w=lower_w, upper_r=upper_r, upper_g=upper_g, upper_b=upper_b, upper_w=upper_w, r16=r16, g16=g16, b16=b16, w16=w16, use_fill16=(mode == "fill16"), mode=mode)

    def _import_plan_csv_path(self, path: str | Path, *, confirm_replace: bool = True) -> bool:
        path = Path(path)
        if self.measurement_rows and confirm_replace and not messagebox.askyesno("Replace plan", "Replace the current plan and clear any saved resume progress?"):
            return False
        self._clear_plan_rows()
        self._reset_resume_state()
        imported = 0
        imported_true16 = 0
        imported_legacy = 0
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            required_legacy = ["name", "r", "g", "b", "w", "bfi_r", "bfi_g", "bfi_b", "bfi_w", "repeats"]
            required_blend8 = ["name", "lower_r", "lower_g", "lower_b", "lower_w", "upper_r", "upper_g", "upper_b", "upper_w"]
            required_true16 = ["name", "r16", "g16", "b16", "w16"]
            has_supported = any(all(key in fieldnames for key in req) for req in [required_legacy, required_blend8, required_true16]) or ("mode" in fieldnames)
            if not has_supported:
                messagebox.showerror("Import failed", "Unsupported CSV schema.\n\nAccepted schemas:\n1) Legacy fill8\n2) Raw temporal blend8 with lower_*/upper_* columns\n3) True16 fill16")
                return False
            for rec in reader:
                try:
                    row = self._row_from_record(rec)
                    self.add_plan_row(row)
                    imported += 1
                    if row.normalized_mode() == "fill16":
                        imported_true16 += 1
                    else:
                        imported_legacy += 1
                except Exception as exc:
                    self.log_queue.put(f"[plan] skipped bad row during import: {exc}")
        if imported_true16 > 0:
            self.use_fill16_var.set(True)
        self.plan_source_path = path
        self.log_queue.put(f"[plan] imported {imported} entries from {path} (legacy/blend8={imported_legacy}, fill16={imported_true16})")
        return True

    def _resolve_plan_csv_for_report(self, report_path: Path, plan_source_csv: str) -> Path | None:
        plan_source_csv = plan_source_csv.strip()
        if plan_source_csv:
            candidate = Path(plan_source_csv)
            if candidate.exists():
                return candidate
        initialdir = str(report_path.parent)
        initialfile = Path(plan_source_csv).name if plan_source_csv else ""
        prompt = "Select the original plan CSV to resume from this progress report."
        if plan_source_csv:
            prompt += f"\n\nSaved path:\n{plan_source_csv}"
        messagebox.showinfo("Locate plan CSV", prompt)
        selected = filedialog.askopenfilename(initialdir=initialdir, initialfile=initialfile, filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        return Path(selected) if selected else None

    def import_plan_csv(self):
        path = filedialog.askopenfilename(initialdir=str(self.capture_dir), filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        self._import_plan_csv_path(path, confirm_replace=True)

    def highlight_plan_index(self, idx: int):
        children = self.tree.get_children()
        if 0 <= idx < len(children):
            iid = children[idx]
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)

    def _render_current_state(self):
        self.send_fill()
        time.sleep(self.settle_delay_var.get())
        self.commit()
        time.sleep(self.settle_delay_var.get())

    def _render_plan_row(self, row: MeasurementPlanRow):
        self.device.send_frame(KIND_CAL_REQ, self._build_fill_payload(row))
        time.sleep(self.settle_delay_var.get())
        self.device.send_frame(KIND_CAL_REQ, bytes([OP_COMMIT]))
        time.sleep(self.settle_delay_var.get())

    def _run_measurement(self):
        return self.argyll.run_spotread(self.argyll_cmd_var.get().strip(), timeout_s=float(self.timeout_var.get()), send_trigger_newline=bool(self.send_newline_var.get()), cleanup_first=bool(self.cleanup_first_var.get()))

    def measure_once(self):
        def worker():
            try:
                self._render_current_state()
                result = self._run_measurement()
                self.last_measurement = result
                self.measurement_text.set(f"last measurement: Y={result.get('Y')} x={result.get('x')} y={result.get('y')}")
                out = {"ts": time.time(), "render": {"mode": self.manual_mode_var.get(), "r": self.r_var.get(), "g": self.g_var.get(), "b": self.b_var.get(), "w": self.w_var.get(), "lower_r": self.lower_r_var.get(), "lower_g": self.lower_g_var.get(), "lower_b": self.lower_b_var.get(), "lower_w": self.lower_w_var.get(), "r16": self.r16_var.get(), "g16": self.g16_var.get(), "b16": self.b16_var.get(), "w16": self.w16_var.get(), "bfi_r": self.bfi_r_var.get(), "bfi_g": self.bfi_g_var.get(), "bfi_b": self.bfi_b_var.get(), "bfi_w": self.bfi_w_var.get(), "use_fill16": self.use_fill16_var.get(), "phase_mode": self.phase_mode_var.get(), "phase": self.phase_var.get()}, "measurement": result}
                path = self.capture_dir / f"single_measure_{int(time.time())}.json"
                path.write_text(json.dumps(out, indent=2), encoding="utf-8")
                self.log_queue.put(f"[measure] wrote {path}")
            except Exception as exc:
                self.log_queue.put(f"[measure] error: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _step_offset(self, row_index: int, repeat_index: int) -> int:
        done = 0
        for idx, row in enumerate(self.measurement_rows):
            repeats = max(1, row.repeats)
            if idx < row_index:
                done += repeats
            elif idx == row_index:
                done += max(0, repeat_index)
                break
        return done

    def _wait_if_paused(self):
        while self.plan_pause_event.is_set() and not self.plan_stop_event.is_set():
            time.sleep(0.1)

    def _progress_payload(self, **kwargs):
        return {"app": APP_TITLE, "updated_ts": time.time(), "capture_csv": str(kwargs["capture_csv"]), "row_count": len(self.measurement_rows), "total_steps": kwargs["total_steps"], "completed_steps": kwargs["completed_steps"], "status": kwargs["status"], "solver_mode": kwargs["solver_mode"], "next_row_index": kwargs["next_row_index"], "next_repeat_index": kwargs["next_repeat_index"], "plan_source_csv": str(self.plan_source_path) if self.plan_source_path else ""}

    def _write_progress_report(self, report_path: Path, **kwargs):
        report_path.write_text(json.dumps(self._progress_payload(**kwargs), indent=2), encoding="utf-8")
        self.plan_report_path = report_path
        self.resume_report_text.set(f"resume: {report_path.name}")

    def load_progress_report(self):
        path = filedialog.askopenfilename(initialdir=str(self.capture_dir), filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        report_path = Path(path)
        data = json.loads(report_path.read_text(encoding="utf-8"))
        plan_rows = data.get("plan_rows") or []
        if plan_rows:
            self._clear_plan_rows()
            self._reset_resume_state()
            for rec in plan_rows:
                self.add_plan_row(self._row_from_record(rec))
        elif not self.measurement_rows:
            plan_source_csv = str(data.get("plan_source_csv", "") or "").strip()
            plan_path = self._resolve_plan_csv_for_report(report_path, plan_source_csv)
            if plan_path is None:
                self.log_queue.put(f"[plan] report load cancelled for {path}: no plan CSV selected")
                return
            if not self._import_plan_csv_path(plan_path, confirm_replace=False):
                return
        status = str(data.get("status", "")).strip().lower()
        next_row_index = int(data.get("next_row_index", 0))
        next_repeat_index = int(data.get("next_repeat_index", 0))
        if status == "completed":
            next_row_index = 0
            next_repeat_index = 0
        self.resume_row_var.set(next_row_index)
        self.resume_repeat_var.set(next_repeat_index)
        capture_csv = data.get("capture_csv")
        self.resume_capture_path = Path(capture_csv) if capture_csv else None
        self.plan_use_solver_var.set(bool(int(data.get("solver_mode", 0))))
        plan_source_csv = str(data.get("plan_source_csv", "") or "").strip()
        if plan_source_csv:
            self.plan_source_path = Path(plan_source_csv)
        self.plan_report_path = report_path
        self.resume_report_text.set(f"resume: {report_path.name}")
        self.log_queue.put(f"[plan] loaded progress report {path}")

    def toggle_pause_plan(self):
        if not self.running_plan:
            return
        if self.plan_pause_event.is_set():
            self.plan_pause_event.clear()
            self.log_queue.put("[plan] resumed")
        else:
            self.plan_pause_event.set()
            self.log_queue.put("[plan] paused")

    def stop_plan(self):
        if not self.running_plan:
            return
        self.plan_stop_event.set()
        self.plan_pause_event.clear()
        self.log_queue.put("[plan] stop requested")

    def run_plan(self):
        if not self.measurement_rows:
            messagebox.showinfo("Plan", "No plan rows added yet.")
            return
        if self.running_plan:
            messagebox.showinfo("Plan", "A plan is already running.")
            return
        if not self.device.is_connected():
            messagebox.showerror("Plan", "Connect the Teensy serial device first.")
            return

        def worker():
            self.running_plan = True
            self.plan_pause_event.clear()
            self.plan_stop_event.clear()
            plan_has_advanced = any(row.normalized_mode() != "fill8" for row in self.measurement_rows)
            timestamp = int(time.time())
            capture_path = self.resume_capture_path or (self.capture_dir / (f"plan_capture_advanced_{timestamp}.csv" if plan_has_advanced else f"plan_capture_{timestamp}.csv"))
            report_path = self.plan_report_path or capture_path.with_suffix(".progress.json")
            start_row = max(0, int(self.resume_row_var.get()))
            start_repeat = max(0, int(self.resume_repeat_var.get()))
            if start_row >= len(self.measurement_rows):
                self.log_queue.put(f"[plan] resume row {start_row} is outside current plan; restarting from row 0")
                start_row = 0
                start_repeat = 0
                capture_path = self.capture_dir / (f"plan_capture_advanced_{timestamp}.csv" if plan_has_advanced else f"plan_capture_{timestamp}.csv")
                report_path = capture_path.with_suffix(".progress.json")
                self.resume_capture_path = None
                self.plan_report_path = None
                self.resume_row_var.set(0)
                self.resume_repeat_var.set(0)
            solver_mode = 1 if self.plan_use_solver_var.get() else 0
            total_steps = sum(max(1, row.repeats) for row in self.measurement_rows)
            if start_repeat >= max(1, self.measurement_rows[start_row].repeats):
                self.log_queue.put(f"[plan] resume repeat {start_repeat} is outside row {start_row}; restarting that row")
                start_repeat = 0
                self.resume_repeat_var.set(0)
            completed_steps = self._step_offset(start_row, start_repeat)
            next_row_index = start_row
            next_repeat_index = start_repeat
            stopped = False
            try:
                self.log_queue.put(f"[plan] setting solver mode = {solver_mode} before plan run")
                self.device.send_frame(KIND_CAL_REQ, bytes([OP_SET_SOLVER_ENABLED, solver_mode]))
                time.sleep(self.settle_delay_var.get())

                capture_exists = capture_path.exists()
                file_mode = "a" if capture_exists and completed_steps > 0 else "w"
                with capture_path.open(file_mode, newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if file_mode == "w":
                        writer.writerow(["name", "mode", "use_fill16", "r", "g", "b", "w", "lower_r", "lower_g", "lower_b", "lower_w", "upper_r", "upper_g", "upper_b", "upper_w", "r16", "g16", "b16", "w16", "bfi_r", "bfi_g", "bfi_b", "bfi_w", "repeat_index", "solver_mode", "ok", "returncode", "elapsed_s", "timed_out", "X", "Y", "Z", "x", "y", "stdout", "stderr"])
                    start_ts = time.time()
                    for idx, row in enumerate(self.measurement_rows):
                        if idx < start_row:
                            continue
                        self._wait_if_paused()
                        if self.plan_stop_event.is_set():
                            stopped = True
                            next_row_index = idx
                            next_repeat_index = start_repeat if idx == start_row else 0
                            break
                        self.root.after(0, lambda i=idx: self.highlight_plan_index(i))
                        self.root.after(0, lambda r=row: self.set_preview_values(r.r, r.g, r.b, r.w, r.bfi_r, r.bfi_g, r.bfi_b, r.bfi_w, r16=r.r16, g16=r.g16, b16=r.b16, w16=r.w16, mode=r.normalized_mode(), lower_r=r.lower_r, lower_g=r.lower_g, lower_b=r.lower_b, lower_w=r.lower_w))
                        self._render_plan_row(row)
                        repeat_start = start_repeat if idx == start_row else 0
                        for rep in range(repeat_start, max(1, row.repeats)):
                            self._wait_if_paused()
                            if self.plan_stop_event.is_set():
                                stopped = True
                                next_row_index = idx
                                next_repeat_index = rep
                                break
                            self._write_progress_report(report_path, capture_csv=capture_path, total_steps=total_steps, completed_steps=completed_steps, status="running", solver_mode=solver_mode, next_row_index=idx, next_repeat_index=rep)
                            result = self._run_measurement()
                            self.last_measurement = result
                            self.root.after(0, lambda res=result: self.measurement_text.set(f"last measurement: Y={res.get('Y')} x={res.get('x')} y={res.get('y')}"))
                            writer.writerow([row.name, row.normalized_mode(), int(row.normalized_mode() == "fill16"), row.r, row.g, row.b, row.w, row.lower_r, row.lower_g, row.lower_b, row.lower_w, row.upper_r, row.upper_g, row.upper_b, row.upper_w, row.r16, row.g16, row.b16, row.w16, row.bfi_r, row.bfi_g, row.bfi_b, row.bfi_w, rep, solver_mode, result.get("ok"), result.get("returncode"), result.get("elapsed_s"), result.get("timed_out"), result.get("X"), result.get("Y"), result.get("Z"), result.get("x"), result.get("y"), result.get("stdout", ""), result.get("stderr", "")])
                            f.flush()
                            completed_steps += 1
                            next_repeat_index = rep + 1
                            next_row_index = idx
                            if next_repeat_index >= max(1, row.repeats):
                                next_row_index = idx + 1
                                next_repeat_index = 0
                            processed_steps = max(1, completed_steps - self._step_offset(start_row, start_repeat))
                            elapsed = time.time() - start_ts
                            eta = (elapsed / processed_steps) * (total_steps - completed_steps)
                            self.log_queue.put(f"[plan] {completed_steps}/{total_steps} complete, eta ~ {eta/60.0:.1f} min")
                            self._write_progress_report(report_path, capture_csv=capture_path, total_steps=total_steps, completed_steps=completed_steps, status="running", solver_mode=solver_mode, next_row_index=next_row_index, next_repeat_index=next_repeat_index)
                        if stopped:
                            break
                        start_repeat = 0
                final_status = "stopped" if stopped else "completed"
                self._write_progress_report(report_path, capture_csv=capture_path, total_steps=total_steps, completed_steps=completed_steps, status=final_status, solver_mode=solver_mode, next_row_index=next_row_index, next_repeat_index=next_repeat_index)
                self.resume_capture_path = capture_path
                self.plan_report_path = report_path
                self.resume_row_var.set(next_row_index)
                self.resume_repeat_var.set(next_repeat_index)
                self.log_queue.put(f"[plan] wrote {capture_path}")
                self.log_queue.put(f"[plan] progress report {report_path} ({final_status})")
            finally:
                self.running_plan = False

        threading.Thread(target=worker, daemon=True).start()

    def save_plan_csv(self):
        if not self.measurement_rows:
            messagebox.showinfo("Plan", "No plan rows to save.")
            return
        path = filedialog.asksaveasfilename(initialdir=str(self.capture_dir), defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=GENERIC_PLAN_FIELDS)
            writer.writeheader()
            for row in self.measurement_rows:
                writer.writerow(row.to_dict())
        self.log_queue.put(f"[plan] saved {path}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()