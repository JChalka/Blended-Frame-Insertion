#!/usr/bin/env python3
"""generate_dual_channel_fills.py

Generates a focused patch plan targeting the six dual-channel emitter families
that are sparsely represented in the existing 40k-capture dataset:

    rg  (yellow/amber region)     rb  (magenta — most sparse)
    gb  (cyan region)             rw  gw  bw  (single+white)

Strategy per pair
-----------------
  Equal ramp:
    Both channels step together from dark to full (pure diagonal of the plane).
    e.g. rg → (128,128)  (512,512)  ... (65535,65535)

  Fix-A / ramp-B:
    Channel A is held at each of N_ANCHOR levels while channel B sweeps the full
    ramp.  Covers all the off-diagonal "horizontal" lines.

  Fix-B / ramp-A:
    Symmetric: channel B held, channel A sweeps.  "Vertical" lines.

Patch count estimate (before dedup):
    15 equal + 2 × (7 anchors × 15 ramp) = 15 + 210 = 225 per pair
    6 pairs → ~1 350 unique patches

Output
------
    patch_plans/patch_plan_dual_channel_fills.csv
    (same schema as v6: name, mode, use_fill16, r16, g16, b16, w16)
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = SCRIPT_DIR / "patch_plans" / "patch_plan_dual_channel_fills.csv"

# ---------------------------------------------------------------------------
# Ramp levels — 15 log-ish steps covering full True16 range (0–65535).
# ---------------------------------------------------------------------------
RAMP_LEVELS: tuple[int, ...] = (
    128, 512, 1024, 2048, 4096,
    8192, 12288, 16384, 20480, 24576,
    32768, 40960, 49152, 57344, 65535,
)

# Fixed anchor values (subset of ramp levels — held constant while other sweeps).
ANCHOR_LEVELS: tuple[int, ...] = (
    128, 1024, 4096, 12288, 24576, 40960, 65535,
)

# ---------------------------------------------------------------------------
# Dual-channel pair definitions
# Each entry: (family_tag, ch_a_idx, ch_b_idx)
# Channels: 0=R 1=G 2=B 3=W
# ---------------------------------------------------------------------------
DUAL_PAIRS: tuple[tuple[str, int, int], ...] = (
    ("rg", 0, 1),   # yellow / amber / olive
    ("rb", 0, 2),   # magenta (most sparse — needs most help)
    ("gb", 1, 2),   # cyan
    ("rw", 0, 3),   # red + white
    ("gw", 1, 3),   # green + white
    ("bw", 2, 3),   # blue + white
)


class PatchPlanBuilder:
    """Deduplicating patch accumulator — same interface as v6."""

    def __init__(self) -> None:
        self.rows: list[dict[str, int | str]] = []
        self._seen: set[tuple[int, int, int, int]] = set()
        self.counts: dict[str, int] = {}

    def add(self, name: str, r16: int, g16: int, b16: int, w16: int, category: str) -> None:
        key = (
            max(0, min(65535, int(r16))),
            max(0, min(65535, int(g16))),
            max(0, min(65535, int(b16))),
            max(0, min(65535, int(w16))),
        )
        if key in self._seen:
            return
        self._seen.add(key)
        self.rows.append({
            "name": name,
            "r16": key[0], "g16": key[1], "b16": key[2], "w16": key[3],
        })
        self.counts[category] = self.counts.get(category, 0) + 1


def _make_drive(ch_a: int, val_a: int, ch_b: int, val_b: int) -> tuple[int, int, int, int]:
    """Build (r16, g16, b16, w16) from two channel indices and their values."""
    drive = [0, 0, 0, 0]
    drive[ch_a] = val_a
    drive[ch_b] = val_b
    return tuple(drive)  # type: ignore[return-value]


def add_dual_channel_ramps(builder: PatchPlanBuilder) -> None:
    for fam, ch_a, ch_b in DUAL_PAIRS:
        ch_names = ("r", "g", "b", "w")
        a_name = ch_names[ch_a]
        b_name = ch_names[ch_b]

        # --- Equal ramp: both channels at the same value ----------------------
        for v in RAMP_LEVELS:
            drive = _make_drive(ch_a, v, ch_b, v)
            builder.add(
                f"dual_{fam}_equal_{v:05d}",
                *drive,
                f"dual_{fam}_equal",
            )

        # --- Fix A, ramp B ----------------------------------------------------
        for anchor in ANCHOR_LEVELS:
            for ramp in RAMP_LEVELS:
                drive = _make_drive(ch_a, anchor, ch_b, ramp)
                builder.add(
                    f"dual_{fam}_{a_name}fix{anchor:05d}_{b_name}ramp{ramp:05d}",
                    *drive,
                    f"dual_{fam}_{a_name}fix_ramp{b_name}",
                )

        # --- Fix B, ramp A ----------------------------------------------------
        for anchor in ANCHOR_LEVELS:
            for ramp in RAMP_LEVELS:
                drive = _make_drive(ch_a, ramp, ch_b, anchor)
                builder.add(
                    f"dual_{fam}_{b_name}fix{anchor:05d}_{a_name}ramp{ramp:05d}",
                    *drive,
                    f"dual_{fam}_{b_name}fix_ramp{a_name}",
                )


def write_csv(path: Path, rows: list[dict[str, int | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["name", "mode", "use_fill16", "r16", "g16", "b16", "w16"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "name":       row["name"],
                "mode":       "fill16",
                "use_fill16": 1,
                "r16":        row["r16"],
                "g16":        row["g16"],
                "b16":        row["b16"],
                "w16":        row["w16"],
            })


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT,
                   help="Output CSV path (default: patch_plans/patch_plan_dual_channel_fills.csv)")
    p.add_argument("--extra-anchors", type=int, nargs="+", default=[],
                   metavar="N",
                   help="Additional fixed-anchor values to add (e.g. --extra-anchors 6144 16384)")
    p.add_argument("--extra-ramps", type=int, nargs="+", default=[],
                   metavar="N",
                   help="Additional ramp values to add (e.g. --extra-ramps 3072 6144)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Allow caller to inject extra levels without editing constants.
    global RAMP_LEVELS, ANCHOR_LEVELS
    if args.extra_ramps:
        RAMP_LEVELS = tuple(sorted(set(RAMP_LEVELS) | set(args.extra_ramps)))
    if args.extra_anchors:
        ANCHOR_LEVELS = tuple(sorted(set(ANCHOR_LEVELS) | set(args.extra_anchors)))

    builder = PatchPlanBuilder()
    add_dual_channel_ramps(builder)
    write_csv(args.out, builder.rows)

    total = len(builder.rows)
    print(f"Wrote {total} unique patches → {args.out}")
    print()
    print("Category breakdown:")
    for cat, cnt in sorted(builder.counts.items()):
        print(f"  {cat:<40}  {cnt:>5}")


if __name__ == "__main__":
    main()
