#!/usr/bin/env python3
"""
cube_to_header.py — Convert a standard .cube 3D LUT file to:
  1. A CubeLUT3D-compatible binary file (4-byte header + interleaved uint16 LE)
  2. A C++ PROGMEM header suitable for direct inclusion in Arduino/Teensy sketches

Supports RGB (.cube with 3 components) and RGBW (4 components, non-standard).
Output values are Q16 (0–65535) scaled from the .cube 0.0–1.0 float range.

Usage:
  python cube_to_header.py input.cube -o output           # writes output.bin + output.h
  python cube_to_header.py input.cube --binary-only       # binary only
  python cube_to_header.py input.cube --header-only       # header only
  python cube_to_header.py input.cube --name my_cube_lut  # custom C identifier prefix
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


def parse_cube_file(path: Path) -> tuple[int, int, list[list[float]]]:
    """Parse a .cube file and return (grid_size, channels, data).

    data is a flat list of grid³ entries, each a list of C floats.
    Entries are in file order: B varies fastest, then G, then R (standard
    Iridas .cube ordering).
    """
    grid_size = 0
    domain_min = None
    domain_max = None
    data: list[list[float]] = []

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            upper = line.upper()
            if upper.startswith("TITLE"):
                continue
            if upper.startswith("DOMAIN_MIN"):
                domain_min = [float(x) for x in line.split()[1:]]
                continue
            if upper.startswith("DOMAIN_MAX"):
                domain_max = [float(x) for x in line.split()[1:]]
                continue
            if upper.startswith("LUT_3D_SIZE"):
                grid_size = int(line.split()[1])
                continue
            # Skip any other keyword lines
            if upper.startswith("LUT_") or any(
                upper.startswith(k)
                for k in ("FORMAT", "INPUTRANGE", "TYPE", "CHANNELS")
            ):
                continue

            # Data line — should be space/tab-separated floats
            parts = line.split()
            try:
                vals = [float(x) for x in parts]
            except ValueError:
                continue
            if len(vals) < 3:
                continue
            data.append(vals)

    if grid_size == 0:
        raise ValueError("No LUT_3D_SIZE found in .cube file")
    if not data:
        raise ValueError("No data entries found in .cube file")

    channels = len(data[0])
    expected = grid_size ** 3
    if len(data) != expected:
        raise ValueError(
            f"Expected {expected} entries for grid {grid_size}, got {len(data)}"
        )
    if channels not in (3, 4):
        raise ValueError(f"Unsupported channel count {channels} (expected 3 or 4)")

    # Apply domain scaling if non-standard
    if domain_min is None:
        domain_min = [0.0] * channels
    if domain_max is None:
        domain_max = [1.0] * channels

    for entry in data:
        for c in range(channels):
            lo, hi = domain_min[c], domain_max[c]
            span = hi - lo
            if span > 0:
                entry[c] = (entry[c] - lo) / span
            entry[c] = max(0.0, min(1.0, entry[c]))

    return grid_size, channels, data


def cube_to_r_major(grid_size: int, channels: int, data: list[list[float]]) -> list[list[float]]:
    """Re-order from .cube B-fastest order to CubeLUT3D R-major order.

    .cube standard:  index = b + g*N + r*N²   (B fastest)
    CubeLUT3D:       index = r*N² + g*N + b    (R fastest / R-major)

    These happen to be the same linear order, so no reordering is needed.
    """
    # .cube ordering is: for r in range(N): for g in range(N): for b in range(N)
    # which gives index = r*N*N + g*N + b — same as CubeLUT3D.
    return data


def quantize_q16(data: list[list[float]], channels: int) -> list[int]:
    """Convert 0.0–1.0 float entries to Q16 uint16 values, interleaved."""
    result: list[int] = []
    for entry in data:
        for c in range(channels):
            val = round(entry[c] * 65535.0)
            result.append(max(0, min(65535, val)))
    return result


def write_binary(path: Path, grid_size: int, channels: int, q16_data: list[int]) -> None:
    """Write CubeLUT3D binary format: 4-byte header + uint16 LE payload."""
    with path.open("wb") as f:
        f.write(struct.pack("<HH", grid_size, channels))
        for val in q16_data:
            f.write(struct.pack("<H", val))
    print(f"  Binary: {path}  ({path.stat().st_size:,} bytes)")


def write_header(
    path: Path,
    grid_size: int,
    channels: int,
    q16_data: list[int],
    prefix: str,
) -> None:
    """Write a C++ PROGMEM header with the interleaved cube data."""
    entry_count = grid_size ** 3
    total_u16 = entry_count * channels
    guard = f"{prefix.upper()}_H"

    ch_label = "RGBW" if channels == 4 else "RGB"

    lines: list[str] = [
        f"// Auto-generated by cube_to_header.py",
        f"// CubeLUT3D-compatible interleaved {ch_label} cube, Q16 values.",
        f"// Grid: {grid_size}x{grid_size}x{grid_size}, Channels: {channels}",
        f"// Index: (r*N*N + g*N + b) * {channels} + ch",
        f"//",
        f"// Load with CubeLUT3D::attach() after copying from PROGMEM,",
        f"// or use CubeLUT3D::loadFromFileBuffer() with the binary header prepended.",
        "",
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        "#include <stdint.h>",
        "",
        "#ifdef __AVR__",
        "  #include <avr/pgmspace.h>",
        "#elif defined(ESP32) || defined(ESP8266)",
        "  #include <pgmspace.h>",
        "#elif !defined(PROGMEM)",
        "  #define PROGMEM",
        "#endif",
        "",
        f"static const uint16_t {prefix}_GRID_SIZE = {grid_size};",
        f"static const uint8_t  {prefix}_CHANNELS  = {channels};",
        f"static const uint32_t {prefix}_ENTRY_COUNT = {entry_count};",
        f"static const uint32_t {prefix}_DATA_LEN = {total_u16};",
        "",
        f"// Interleaved {ch_label} data: {total_u16} uint16 values ({total_u16 * 2:,} bytes)",
        f"static const uint16_t {prefix}_DATA[{total_u16}] PROGMEM = {{",
    ]

    # Format data rows — 8 values per line for readability
    row_parts: list[str] = []
    for i in range(0, total_u16, 8):
        chunk = q16_data[i : i + 8]
        row_parts.append("    " + ", ".join(str(v) for v in chunk) + ",")
    if row_parts:
        # Remove trailing comma on last line
        row_parts[-1] = row_parts[-1].rstrip(",")
    lines.extend(row_parts)

    lines.extend([
        "};",
        "",
        f"// 4-byte binary file header for CubeLUT3D::loadFromFileBuffer()",
        f"static const uint8_t {prefix}_FILE_HEADER[4] PROGMEM = {{",
        f"    {grid_size & 0xFF}, {(grid_size >> 8) & 0xFF}, "
        f"{channels & 0xFF}, {(channels >> 8) & 0xFF}",
        "};",
        "",
        f"#endif  // {guard}",
        "",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Header: {path}  ({len(lines)} lines)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert .cube 3D LUT to CubeLUT3D binary and/or C++ PROGMEM header."
    )
    parser.add_argument("input", type=Path, help="Input .cube file")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output base path (no extension). Defaults to input stem."
    )
    parser.add_argument(
        "--name", type=str, default=None,
        help="C identifier prefix for the header (default: derived from filename)"
    )
    parser.add_argument(
        "--binary-only", action="store_true",
        help="Write only the .bin file"
    )
    parser.add_argument(
        "--header-only", action="store_true",
        help="Write only the .h file"
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    base = args.output or args.input.with_suffix("")
    prefix = args.name or base.stem.replace("-", "_").replace(" ", "_").upper()

    print(f"Parsing: {args.input}")
    grid_size, channels, data = parse_cube_file(args.input)
    ch_label = "RGBW" if channels == 4 else "RGB"
    print(f"  Grid: {grid_size}, Channels: {channels} ({ch_label}), "
          f"Entries: {grid_size**3}")

    data = cube_to_r_major(grid_size, channels, data)
    q16_data = quantize_q16(data, channels)

    if not args.header_only:
        write_binary(base.with_suffix(".bin"), grid_size, channels, q16_data)
    if not args.binary_only:
        write_header(base.with_suffix(".h"), grid_size, channels, q16_data, prefix)

    print("Done.")


if __name__ == "__main__":
    main()
