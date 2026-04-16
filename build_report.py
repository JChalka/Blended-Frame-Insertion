"""
build_report.py — PlatformIO post-build hook + standalone report generator.

As a PIO extra_script (post:build_report.py in platformio.ini):
    Registers a post-link action.  After each environment links its
    firmware.elf, teensy_size is run on it and BUILD_REPORT.md is
    regenerated from the accumulated results in .pio/build/size_results.json.

Standalone:
    python build_report.py              # scan .pio/build/*/firmware.elf
    python build_report.py --badge      # include shields.io badge
    python build_report.py --json       # raw JSON to stdout
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# __file__ is not defined when loaded as a SCons extra_script.
# Defer path resolution — PIO hook uses env["PROJECT_DIR"], standalone uses __file__.
try:
    _THIS_DIR = Path(__file__).resolve().parent
except NameError:
    _THIS_DIR = None  # set later from env["PROJECT_DIR"]


def _project_dir():
    """Return project root as a Path, works in both PIO and standalone contexts."""
    if _THIS_DIR is not None:
        return _THIS_DIR
    # Fallback: should have been set by _pio_setup()
    return Path.cwd()


def _build_dir():
    return _project_dir() / ".pio" / "build"


def _results_json():
    return _build_dir() / "size_results.json"


def _report_path():
    return _project_dir() / "BUILD_REPORT.md"

# Preferred env order (matches [platformio] default_envs)
ENV_ORDER = [
    "HyperTeensy", "Calibration", "FrameworkDemo", "RGB16InputDemo",
    "ColorCalibrationABDemo", "PrecomputeDemo", "rgbwNoExtractionDemo",
    "True16RGBWGradientDemo", "TemporalFastLEDDemo", "PackedBFIMapDemo",
    "CubeLUT3DDemo",
]

# Board metadata for summary line.
# Keys are PlatformIO board IDs; values are human-readable descriptions.
BOARD_INFO = {
    "teensy40": "Teensy 4.0 (IMXRT1062) \u2014 1984 KB Flash, 512 KB RAM1, 512 KB RAM2",
    "teensy41": "Teensy 4.1 (IMXRT1062) \u2014 7936 KB Flash, 512 KB RAM1, 512 KB RAM2, PSRAM + QSPI pads",
    "esp32-s3-devkitc-1": "ESP32-S3 DevKitC-1 \u2014 8 MB Flash, 512 KB SRAM, PSRAM",
    "esp32-p4-function-ev-board": "ESP32-P4 Function EV Board \u2014 16 MB Flash, 768 KB SRAM, PSRAM",
}


# ── teensy_size helpers ─────────────────────────────────────────────────────

def _find_teensy_size_standalone() -> str:
    home = Path(os.environ.get("USERPROFILE", os.environ.get("HOME", "")))
    for candidate in [
        home / ".platformio" / "packages" / "tool-teensy" / "teensy_size.exe",
        home / ".platformio" / "packages" / "tool-teensy" / "teensy_size",
    ]:
        if candidate.exists():
            return str(candidate)
    return "teensy_size"


def _run_teensy_size(exe: str, elf_path: str) -> dict:
    try:
        proc = subprocess.run(
            [exe, elf_path],
            capture_output=True, text=True, timeout=15,
        )
        output = proc.stdout + "\n" + proc.stderr
    except Exception:
        return {}

    info = {}
    for line in output.splitlines():
        if "FLASH:" in line:
            m = re.search(r"code:(\d+),\s*data:(\d+),\s*headers:(\d+)", line)
            if m:
                info["flash_code"] = int(m.group(1))
                info["flash_data"] = int(m.group(2))
                info["flash_headers"] = int(m.group(3))
                info["flash_total"] = info["flash_code"] + info["flash_data"] + info["flash_headers"]
            mf = re.search(r"free for files:(\d+)", line)
            if mf:
                info["flash_free"] = int(mf.group(1))
        elif "RAM1:" in line:
            m = re.search(r"variables:(\d+),\s*code:(\d+)", line)
            if m:
                info["ram1_vars"] = int(m.group(1))
                info["ram1_code"] = int(m.group(2))
            mf = re.search(r"free for local variables:(\d+)", line)
            if mf:
                info["ram1_free"] = int(mf.group(1))
        elif "RAM2:" in line:
            m = re.search(r"variables:(\d+)", line)
            if m:
                info["ram2_vars"] = int(m.group(1))
            mf = re.search(r"free for malloc/new:(\d+)", line)
            if mf:
                info["ram2_free"] = int(mf.group(1))
    if info:
        info["ram_total"] = info.get("ram1_vars", 0) + info.get("ram1_code", 0) + info.get("ram2_vars", 0)
    return info


# ── JSON accumulator ────────────────────────────────────────────────────────

def _load_results() -> dict:
    rj = _results_json()
    if rj.exists():
        try:
            return json.loads(rj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_results(results: dict):
    rj = _results_json()
    rj.parent.mkdir(parents=True, exist_ok=True)
    rj.write_text(json.dumps(results, indent=2), encoding="utf-8")


# ── Markdown report ─────────────────────────────────────────────────────────

def _fmt_kb(val) -> str:
    if not val:
        return "-"
    return f"{val / 1024:.1f} KB"


def generate_report(results: dict, show_badge: bool = False) -> str:
    ordered = [e for e in ENV_ORDER if e in results]
    ordered += [e for e in sorted(results) if e not in ordered]

    lines = ["# TemporalBFI Build Report\n"]

    if not results:
        lines.append("_No build data yet.  Run `pio run` to build and auto-generate._\n")
        return "\n".join(lines)

    passed = sum(1 for r in results.values() if r.get("status") == "SUCCESS")
    total = len(results)
    lines.append(f"**{passed}/{total}** environments built successfully.\n")

    if show_badge:
        color = "brightgreen" if passed == total else "red"
        lines.append(f"![build](https://img.shields.io/badge/build-{passed}%2F{total}-{color})\n")

    lines.append("| Environment | Status | Flash | Flash Free | RAM1 | RAM1 Free | RAM2 | RAM2 Free |")
    lines.append("|-------------|--------|-------|------------|------|-----------|------|-----------|")

    for name in ordered:
        r = results[name]
        status = r.get("status", "?")
        status_cell = f"**{status}**" if status == "FAILED" else status
        ram1_used = (r.get('ram1_vars') or 0) + (r.get('ram1_code') or 0)
        lines.append(
            f"| {name} | {status_cell} "
            f"| {_fmt_kb(r.get('flash_total'))} "
            f"| {_fmt_kb(r.get('flash_free'))} "
            f"| {_fmt_kb(ram1_used)} "
            f"| {_fmt_kb(r.get('ram1_free'))} "
            f"| {_fmt_kb(r.get('ram2_vars'))} "
            f"| {_fmt_kb(r.get('ram2_free'))} |"
        )

    lines.append("")

    # Build a dynamic target summary from boards seen in build results.
    boards_seen = {}
    for name in ordered:
        r = results[name]
        bid = r.get("board", "")
        if bid:
            boards_seen.setdefault(bid, []).append(name)
    if boards_seen:
        for bid, envs in boards_seen.items():
            desc = BOARD_INFO.get(bid, bid)
            lines.append(f"Target: **{desc}**<br>Environments: {', '.join(envs)}")
            lines.append("")
    else:
        lines.append("Target: _(board info unavailable \u2014 rebuild to populate)_")

    lines.append("")
    return "\n".join(lines)


def _write_report(results: dict, badge: bool = False):
    report = generate_report(results, show_badge=badge)
    _report_path().write_text(report, encoding="utf-8")


# ── PlatformIO extra_script entry point ─────────────────────────────────────

def _pio_post_build(target, source, env):
    """Called by SCons after a successful firmware link."""
    env_name = env["PIOENV"]
    elf_path = str(target[0])

    tool_dir = env.PioPlatform().get_package_dir("tool-teensy") or ""
    exe_name = "teensy_size.exe" if sys.platform == "win32" else "teensy_size"
    teensy_size_exe = os.path.join(tool_dir, exe_name)
    if not os.path.isfile(teensy_size_exe):
        teensy_size_exe = _find_teensy_size_standalone()

    sizes = _run_teensy_size(teensy_size_exe, elf_path)
    sizes["status"] = "SUCCESS"
    sizes["board"] = env.BoardConfig().id

    results = _load_results()
    results[env_name] = sizes
    _save_results(results)
    _write_report(results)


try:
    Import("env")  # type: ignore[name-defined]   # noqa: F821
    _THIS_DIR = Path(env["PROJECT_DIR"])  # type: ignore[name-defined]   # noqa: F821
    env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", _pio_post_build)  # type: ignore[name-defined]   # noqa: F821
except NameError:
    pass  # not running inside PlatformIO — fall through to __main__


# ── Standalone CLI ──────────────────────────────────────────────────────────

def _scan_and_report(badge: bool = False, as_json: bool = False):
    """Scan .pio/build/*/firmware.elf without rebuilding."""
    teensy_size_exe = _find_teensy_size_standalone()
    results = {}

    for elf in sorted(_build_dir().glob("*/firmware.elf")):
        env_name = elf.parent.name
        sizes = _run_teensy_size(teensy_size_exe, str(elf))
        sizes["status"] = "SUCCESS" if sizes else "UNKNOWN"
        results[env_name] = sizes

    if not results:
        print("No firmware.elf files found in .pio/build/ — run `pio run` first.", file=sys.stderr)
        return

    _save_results(results)

    if as_json:
        print(json.dumps(results, indent=2))
    else:
        report = generate_report(results, show_badge=badge)
        print(report)
        _write_report(results, badge)
        print(f"\nReport written to {_report_path()}", file=sys.stderr)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate BUILD_REPORT.md from the last PIO build artifacts.")
    parser.add_argument("--badge", action="store_true", help="Include shields.io badge")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of Markdown")
    args = parser.parse_args()
    _scan_and_report(badge=args.badge, as_json=args.json)
