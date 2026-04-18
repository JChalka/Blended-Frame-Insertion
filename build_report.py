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
    "4d_systems_esp32s3_gen4_r8n16": "ESP32-S3 (N16R8) \u2014 16 MB Flash, 320 KB SRAM, 8 MB PSRAM",
}

# Platforms whose boards use the ESP-IDF / esptool size output format.
ESP_PLATFORMS = {"espressif32"}



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


# ── ESP32 size helpers (IDF memory map + PIO summary) ───────────────────────

def _parse_esp32_size_output(output: str) -> dict:
    """Parse the ESP-IDF ``idf_size.py`` / PIO memory table and summary lines.

    Recognises both the detailed ``Memory Type Usage Summary`` table
    (with rows like ``│ Flash Code │ 708290 │ …``), the compact
    PIO summary (``RAM:   [====      ]  35.1% (used 114916 …)``), and the
    ``xtensa-esp-elf-size -A`` section table (``section  size  addr``).
    """
    info: dict = {"arch": "esp32"}

    # ── xtensa-esp-elf-size -A section table ─────────────────────────────
    #   .iram0.text   12345   0x40080000
    #   .dram0.data   6789    0x3ffb0000
    #   .flash.text   456789  0x400d0000
    #   .dram0.bss    2345    ...
    section_re = re.compile(r"^\s*(\.\S+)\s+(\d+)\s+(\d+)", re.MULTILINE)
    section_map = {}
    for m_s in section_re.finditer(output):
        name = m_s.group(1)
        size = int(m_s.group(2))
        if size > 0:
            section_map[name] = size
    if section_map:
        flash_text = section_map.get(".flash.text", 0)
        flash_rodata = section_map.get(".flash.rodata", 0)
        iram_text = section_map.get(".iram0.text", 0) + section_map.get(".iram0.vectors", 0)
        dram_data = section_map.get(".dram0.data", 0)
        dram_bss = section_map.get(".dram0.bss", 0)
        noinit = section_map.get(".noinit", 0)
        info.setdefault("flash_code", flash_text + iram_text)
        info.setdefault("flash_data", flash_rodata + dram_data)
        info.setdefault("iram_used", iram_text)
        info.setdefault("diram_used", dram_data + dram_bss)
        ram_used = iram_text + dram_data + dram_bss + noinit
        info.setdefault("ram_used", ram_used)

    # ── Detailed IDF table rows ──────────────────────────────────────────
    #   │ Flash Code          │       708290 │     │  …
    #   │    .text            │       708290 │     │  …
    row_re = re.compile(
        r"\│\s*(?P<section>[^│]+?)\s*\│\s*(?P<used>\d+)\s*\│\s*(?P<pct>[^│]*)\│\s*(?P<remain>[^│]*)\│\s*(?P<total>[^│]*)\│"
    )
    for line in output.splitlines():
        m = row_re.search(line)
        if not m:
            continue
        section = m.group("section").strip()
        used = int(m.group("used"))
        remain_s = m.group("remain").strip()
        total_s = m.group("total").strip()
        remain = int(remain_s) if remain_s.isdigit() else None
        total = int(total_s) if total_s.isdigit() else None

        if section == "Flash Code":
            info["flash_code"] = used
        elif section == "Flash Data":
            info["flash_data"] = used
        elif section == "IRAM":
            info["iram_used"] = used
            if remain is not None:
                info["iram_free"] = remain
            if total is not None:
                info["iram_total"] = total
        elif section == "DIRAM":
            info["diram_used"] = used
            if remain is not None:
                info["diram_free"] = remain
            if total is not None:
                info["diram_total"] = total
        elif section == "RTC FAST":
            info["rtc_used"] = used
            if remain is not None:
                info["rtc_free"] = remain

    # ── "Total image size:" line ─────────────────────────────────────────
    m = re.search(r"Total image size:\s*(\d+)\s*bytes", output)
    if m:
        info["image_size"] = int(m.group(1))

    # ── PIO compact summary lines ────────────────────────────────────────
    #   RAM:   [====      ]  35.1% (used 114916 bytes from 327680 bytes)
    #   Flash: [==        ]  17.1% (used 1077800 bytes from 6291456 bytes)
    for line in output.splitlines():
        m_pio = re.match(
            r"\s*(RAM|Flash):\s*\[.*?\]\s*([\d.]+)%\s*\(used\s+(\d+)\s+bytes\s+from\s+(\d+)\s+bytes\)",
            line,
        )
        if not m_pio:
            continue
        kind = m_pio.group(1)
        used = int(m_pio.group(3))
        total = int(m_pio.group(4))
        if kind == "RAM":
            info.setdefault("ram_used", used)
            info.setdefault("ram_total", total)
            info["ram_free"] = total - used
        else:
            info.setdefault("flash_used", used)
            info.setdefault("flash_total", total)
            info["flash_free"] = total - used

    # Synthesise flash_used from code + data if table was parsed but PIO summary wasn't.
    if "flash_used" not in info and "flash_code" in info:
        info["flash_used"] = info.get("flash_code", 0) + info.get("flash_data", 0)

    return info if len(info) > 1 else {}


def _run_esp32_size(env) -> dict:
    """Extract ESP32 memory usage from the build environment.

    Strategy (in order):
    1. Run ``esp_idf_size`` (as a Python module) on the ``.map`` file for the
       detailed IDF memory-region table (Flash Code / IRAM / DIRAM …).
    2. Run ``xtensa-esp-elf-size -A`` via the toolchain package for basic
       section sizes.
    3. Fall back to PIO's ``SIZECHECKCMD``/``SIZEPRINTCMD`` env vars.

    The compact PIO summary (``RAM: … / Flash: …``) is always attempted
    as a supplement by executing SIZECHECKCMD.
    """
    build_dir = env.subst("$BUILD_DIR")
    progname = env.subst("${PROGNAME}")
    elf_path = os.path.join(build_dir, progname + ".elf")
    map_path = os.path.join(build_dir, progname + ".map")

    result: dict = {}

    # ── Try esp_idf_size as a Python module on the .map file ────────────
    if os.path.isfile(map_path):
        for cmd in [
            [sys.executable, "-m", "esp_idf_size", "--format", "text", map_path],
            [sys.executable, "-m", "idf_size", "--format", "text", map_path],
        ]:
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=30,
                )
                parsed = _parse_esp32_size_output(proc.stdout + "\n" + proc.stderr)
                if parsed and len(parsed) > 1:
                    result = parsed
                    break
            except Exception:
                continue

    # ── Try xtensa-esp-elf-size from the toolchain package ──────────────
    if len(result) <= 1 and os.path.isfile(elf_path):
        try:
            toolchain_dir = env.PioPlatform().get_package_dir("toolchain-xtensa-esp-elf") or ""
            exe_name = "xtensa-esp-elf-size.exe" if sys.platform == "win32" else "xtensa-esp-elf-size"
            size_exe = os.path.join(toolchain_dir, "bin", exe_name)
            if os.path.isfile(size_exe):
                proc = subprocess.run(
                    [size_exe, "-A", elf_path],
                    capture_output=True, text=True, timeout=15,
                )
                parsed = _parse_esp32_size_output(proc.stdout + "\n" + proc.stderr)
                if parsed and len(parsed) > 1:
                    result = parsed
        except Exception:
            pass

    # ── Try PIO's SIZECHECKCMD / SIZEPRINTCMD as a supplement ───────────
    for key in ("SIZECHECKCMD", "SIZEPRINTCMD"):
        try:
            raw = env.get(key)
            if not raw:
                continue
            # SCons stores these as action lists; flatten to a string.
            cmd_str = raw if isinstance(raw, str) else env.subst(str(raw))
            if cmd_str:
                proc = subprocess.run(
                    cmd_str, capture_output=True, text=True, timeout=30, shell=True,
                )
                parsed = _parse_esp32_size_output(proc.stdout + "\n" + proc.stderr)
                if parsed and len(parsed) > 1:
                    # Merge: keep existing detailed data, add PIO summary data.
                    for k, v in parsed.items():
                        result.setdefault(k, v)
                    break
        except Exception:
            continue

    # ── Supplement with board memory totals from PIO board config ───────
    try:
        board_cfg = env.BoardConfig()
        flash_total = int(board_cfg.get("upload.maximum_size", 0))
        ram_total = int(board_cfg.get("upload.maximum_ram_size", 0))
        if flash_total > 0:
            result.setdefault("flash_total", flash_total)
        if ram_total > 0:
            result.setdefault("ram_total", ram_total)
    except Exception:
        pass

    return result


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

    # Partition results by architecture.
    teensy_envs = [e for e in ordered if results[e].get("arch") != "esp32"]
    esp32_envs = [e for e in ordered if results[e].get("arch") == "esp32"]

    # ── Teensy table ─────────────────────────────────────────────────────
    if teensy_envs:
        lines.append("## Teensy (IMXRT1062)\n")
        lines.append("| Environment | Status | Flash | Flash Free | RAM1 | RAM1 Free | RAM2 | RAM2 Free |")
        lines.append("|-------------|--------|-------|------------|------|-----------|------|-----------|")

        for name in teensy_envs:
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

    # ── ESP32 table ──────────────────────────────────────────────────────
    if esp32_envs:
        lines.append("## ESP32\n")
        lines.append("| Environment | Status | Flash Code | Flash Data | Flash Used | Flash Free | RAM (DIRAM) | DIRAM Free | IRAM | IRAM Free | Image |")
        lines.append("|-------------|--------|------------|------------|------------|------------|-------------|------------|------|-----------|-------|")

        for name in esp32_envs:
            r = results[name]
            status = r.get("status", "?")
            status_cell = f"**{status}**" if status == "FAILED" else status
            # flash_used: prefer PIO compact summary, else sum code+data.
            flash_used = r.get("flash_used")
            if not flash_used and (r.get("flash_code") or r.get("flash_data")):
                flash_used = (r.get("flash_code") or 0) + (r.get("flash_data") or 0)
            # flash_free: prefer parsed, else compute from total.
            flash_free = r.get("flash_free")
            if not flash_free and flash_used and r.get("flash_total"):
                flash_free = r["flash_total"] - flash_used
            # diram_used: prefer parsed, else ram_used as proxy.
            diram_used = r.get("diram_used") or r.get("ram_used")
            diram_free = r.get("diram_free")
            if not diram_free and diram_used and r.get("ram_total"):
                diram_free = r["ram_total"] - diram_used
            lines.append(
                f"| {name} | {status_cell} "
                f"| {_fmt_kb(r.get('flash_code'))} "
                f"| {_fmt_kb(r.get('flash_data'))} "
                f"| {_fmt_kb(flash_used)} "
                f"| {_fmt_kb(flash_free)} "
                f"| {_fmt_kb(diram_used)} "
                f"| {_fmt_kb(diram_free)} "
                f"| {_fmt_kb(r.get('iram_used'))} "
                f"| {_fmt_kb(r.get('iram_free'))} "
                f"| {_fmt_kb(r.get('image_size'))} |"
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
    board_id = env.BoardConfig().id
    platform_name = env.PioPlatform().name  # e.g. "espressif32", "teensy"

    print(f"[build_report] hook fired: env={env_name} platform={platform_name} board={board_id} elf={elf_path}")

    if platform_name in ESP_PLATFORMS:
        sizes = _run_esp32_size(env)
        sizes.setdefault("arch", "esp32")
        print(f"[build_report] ESP32 sizes: {sizes}")
    else:
        tool_dir = env.PioPlatform().get_package_dir("tool-teensy") or ""
        exe_name = "teensy_size.exe" if sys.platform == "win32" else "teensy_size"
        teensy_size_exe = os.path.join(tool_dir, exe_name)
        if not os.path.isfile(teensy_size_exe):
            teensy_size_exe = _find_teensy_size_standalone()
        sizes = _run_teensy_size(teensy_size_exe, elf_path)

    sizes["status"] = "SUCCESS"
    sizes["board"] = board_id

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

def _scan_esp32_elf(elf_path: Path) -> dict:
    """Try ``esp_idf_size`` on the ``.map`` file, or ``xtensa-esp-elf-size``
    on the ELF (standalone mode)."""
    map_path = elf_path.with_suffix(".map")

    # Try esp_idf_size on the .map file first (the IDF tool expects .map).
    if map_path.exists():
        for cmd in [
            [sys.executable, "-m", "esp_idf_size", "--format", "text", str(map_path)],
            [sys.executable, "-m", "idf_size", "--format", "text", str(map_path)],
        ]:
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                parsed = _parse_esp32_size_output(proc.stdout + "\n" + proc.stderr)
                if parsed and len(parsed) > 1:
                    return parsed
            except Exception:
                continue

    # Fallback: try xtensa-esp-elf-size -A on the ELF.
    for name in ["xtensa-esp-elf-size", "xtensa-esp-elf-size.exe"]:
        try:
            proc = subprocess.run(
                [name, "-A", str(elf_path)],
                capture_output=True, text=True, timeout=15,
            )
            parsed = _parse_esp32_size_output(proc.stdout + "\n" + proc.stderr)
            if parsed and len(parsed) > 1:
                return parsed
        except (FileNotFoundError, Exception):
            continue

    return {"arch": "esp32"}


def _scan_and_report(badge: bool = False, as_json: bool = False):
    """Scan .pio/build/*/firmware.elf without rebuilding."""
    teensy_size_exe = _find_teensy_size_standalone()
    results = {}

    for elf in sorted(_build_dir().glob("*/firmware.elf")):
        env_name = elf.parent.name

        # Try to detect architecture from build artifacts.
        sdkconfig = elf.parent / "sdkconfig"
        map_file = elf.parent / "firmware.map"
        is_esp = sdkconfig.exists() or (
            map_file.exists() and "xtensa" in map_file.read_text(errors="ignore")[:2048]
        )

        if is_esp:
            # Attempt esp_idf_size / idf_size.py for the detailed table.
            sizes = _scan_esp32_elf(elf)
        else:
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
