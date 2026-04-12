#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, html, json, math, re
from bisect import bisect_left
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

CHANNELS = ["R", "G", "B", "W"]
SOLVER_CHANNEL_ORDER = ["G", "R", "B", "W"]
TRUE16_DEFAULT_INPUT_GLOBS = [
    "plan_capture_true16_*.csv",
    "plan_capture_mixed_*.csv",
    "plan_capture_*.csv",
]
PATCH_PRESETS = {
    "quick": {
        "grays": [32, 64, 128, 192, 255],
        "primaries": [64, 128, 192, 255],
        "mixed": [(255,255,0,0), (0,255,255,0), (255,0,255,0), (255,128,64,0), (64,64,64,0)],
        "repeats": 1,
    },
    "balanced": {
        "grays": [16, 32, 64, 96, 128, 160, 192, 224, 255],
        "primaries": [32, 64, 96, 128, 160, 192, 224, 255],
        "mixed": [(255,255,0,0), (0,255,255,0), (255,0,255,0), (255,128,64,0), (255,200,160,0), (96,96,96,0), (192,192,192,0)],
        "repeats": 2,
    },
    "fine": {
        "grays": [8,16,24,32,48,64,80,96,112,128,144,160,176,192,208,224,240,255],
        "primaries": [16,32,48,64,80,96,112,128,144,160,176,192,208,224,240,255],
        "mixed": [(255,255,0,0), (0,255,255,0), (255,0,255,0), (255,128,64,0), (255,200,160,0), (128,96,64,0), (96,96,96,0), (160,160,160,0), (224,224,224,0)],
        "repeats": 2,
    },
    "warm-guard": {
        "grays": [8, 12, 16, 24, 32, 48, 64, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 240, 255],
        "primaries": [24, 40, 56, 72, 96, 128, 160, 192, 224, 255],
        "mixed": [
            (255, 235, 180, 0), (255, 220, 140, 0), (255, 200, 96, 0),
            (240, 180, 80, 0), (224, 170, 96, 0), (192, 150, 96, 0),
            (160, 140, 120, 0), (128, 118, 108, 0), (96, 90, 84, 0),
            (255, 255, 192, 0), (224, 220, 192, 0), (192, 188, 176, 0),
            (255, 210, 160, 32), (224, 180, 140, 24), (192, 152, 120, 16),
            (255, 255, 0, 0), (255, 192, 0, 0), (255, 160, 64, 0),
        ],
        "repeats": 3,
    },
    "neutral-focus": {
        "grays": [4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 240, 255],
        "primaries": [32, 64, 96, 128, 160, 192, 224, 255],
        "mixed": [
            (64, 64, 64, 0), (64, 62, 60, 0), (64, 60, 56, 0),
            (96, 96, 96, 0), (96, 92, 88, 0), (96, 88, 80, 0),
            (128, 128, 128, 0), (128, 124, 120, 0), (128, 120, 112, 0),
            (192, 192, 192, 0), (192, 188, 176, 0), (192, 180, 160, 0),
            (224, 220, 210, 0), (255, 248, 232, 0),
            (128, 128, 128, 32), (192, 192, 192, 48), (224, 224, 224, 64),
        ],
        "repeats": 3,
    },
    "super-fine": {
        "grays": [2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32, 40, 48, 56, 64, 72, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 240, 248, 255],
        "primaries": [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 240, 255],
        "mixed": [
            (255, 245, 220, 0), (255, 235, 180, 0), (255, 220, 140, 0), (255, 200, 96, 0),
            (240, 180, 80, 0), (224, 170, 96, 0), (192, 152, 120, 0), (160, 140, 120, 0),
            (128, 118, 108, 0), (96, 90, 84, 0), (64, 62, 60, 0), (64, 60, 56, 0),
            (96, 92, 88, 0), (96, 88, 80, 0), (128, 124, 120, 0), (128, 120, 112, 0),
            (192, 188, 176, 0), (192, 180, 160, 0), (224, 220, 210, 0), (255, 248, 232, 0),
            (255, 255, 0, 0), (255, 192, 0, 0), (255, 160, 64, 0), (0, 255, 255, 0),
            (255, 0, 255, 0), (64, 128, 255, 0), (64, 200, 160, 0), (220, 120, 255, 0),
            (255, 210, 160, 32), (224, 180, 140, 24), (192, 152, 120, 16), (160, 160, 160, 24),
            (192, 192, 192, 48), (224, 224, 224, 64), (255, 255, 224, 48), (255, 240, 224, 64),
        ],
        "repeats": 3,
    },
    "super-fine-plus": {
        "grays": [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 48, 56, 64, 72, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 240, 248, 255],
        "primaries": [4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56, 64, 72, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 240, 248, 255],
        "mixed": [
            (255, 248, 232, 0), (255, 245, 220, 0), (255, 235, 180, 0), (255, 220, 140, 0),
            (255, 210, 128, 0), (255, 200, 96, 0), (255, 184, 72, 0), (240, 180, 80, 0),
            (224, 170, 96, 0), (208, 160, 104, 0), (192, 152, 120, 0), (176, 144, 120, 0),
            (160, 140, 120, 0), (128, 118, 108, 0), (96, 90, 84, 0), (64, 62, 60, 0),
            (64, 60, 56, 0), (96, 92, 88, 0), (96, 88, 80, 0), (128, 124, 120, 0),
            (128, 120, 112, 0), (160, 156, 148, 0), (192, 188, 176, 0), (192, 180, 160, 0),
            (224, 220, 210, 0), (255, 255, 0, 0), (255, 224, 0, 0), (255, 192, 0, 0),
            (255, 160, 64, 0), (255, 128, 0, 0), (255, 96, 32, 0), (0, 255, 255, 0),
            (255, 0, 255, 0), (64, 128, 255, 0), (64, 200, 160, 0), (220, 120, 255, 0),
            (255, 210, 160, 32), (224, 180, 140, 24), (192, 152, 120, 16), (160, 160, 160, 24),
            (192, 192, 192, 48), (224, 224, 224, 64), (255, 255, 224, 48), (255, 240, 224, 64),
            (255, 255, 255, 96),
        ],
        "repeats": 4,
    },
}

# Alias for users who prefer the shorter preset name.
PATCH_PRESETS["ultra"] = PATCH_PRESETS["super-fine"]
PATCH_PRESETS["ultra-plus"] = PATCH_PRESETS["super-fine-plus"]

MIXING_PRESETS = {
    "legacy": {
        "neutral_threshold_q16": 4096,
        "white_weight_q16": 65535,
        "rgb_weight_q16": 65535,
    },
    "balanced": {
        "neutral_threshold_q16": 3072,
        "white_weight_q16": 57344,
        "rgb_weight_q16": 65535,
    },
    "warm-guard": {
        "neutral_threshold_q16": 2304,
        "white_weight_q16": 49152,
        "rgb_weight_q16": 65535,
    },
    "warm-guard-strong": {
        "neutral_threshold_q16": 1536,
        "white_weight_q16": 40960,
        "rgb_weight_q16": 65535,
    },
}

PLAN_PRESET_OPTIONS = ["custom", "targeted-16bit"]

def dense_code_set():
    codes = set()
    for v in range(0, 64, 1): codes.add(v)
    for v in range(64, 128, 2): codes.add(v)
    for v in range(128, 192, 4): codes.add(v)
    for v in range(192, 256, 8): codes.add(v)
    codes.add(255)
    return sorted(codes)

def uniform_code_set(step: int):
    step = max(1, int(step))
    codes = list(range(0, 256, step))
    if 255 not in codes:
        codes.append(255)
    return sorted(set(codes))

def code_set_for_step(step: int):
    return dense_code_set() if int(step) <= 0 else uniform_code_set(step)

def infer_repeats_from_code(value: int, bfi: int) -> int:
    est = (value / 255.0) / (bfi + 1)
    if est > 0.5: return 1
    if est > 0.15: return 2
    if est > 0.03: return 4
    return 8

def infer_repeats_from_blend(value: int, floor: int, bfi: int) -> int:
    avg = ((int(value) + int(floor) * int(bfi)) / max(1, int(bfi) + 1)) / 255.0
    if avg > 0.5: return 1
    if avg > 0.15: return 2
    if avg > 0.03: return 4
    return 8

def infer_targeted_repeats_from_code(value: int, bfi: int) -> int:
    est = (value / 255.0) / (bfi + 1)
    if est > 0.15: return 1
    if est > 0.03: return 2
    return 4

def infer_targeted_repeats_from_blend(value: int, floor: int, bfi: int) -> int:
    avg = ((int(value) + int(floor) * int(bfi)) / max(1, int(bfi) + 1)) / 255.0
    if avg > 0.15: return 1
    if avg > 0.03: return 2
    return 4

def targeted16_upper_code_set():
    codes = set()
    for v in range(0, 128, 1): codes.add(v)
    for v in range(128, 192, 2): codes.add(v)
    for v in range(192, 256, 2): codes.add(v)
    codes.add(255)
    return sorted(codes)

def targeted16_floor_code_set():
    return [0, *range(1, 33, 1), *range(36, 129, 4), *range(136, 257, 8)]

def write_plan(channel: str, out_csv: Path, max_bfi: int = 4, step: int = 0):
    codes = code_set_for_step(step)
    rows = []
    chs = CHANNELS if channel == "ALL" else [channel]
    for ch in chs:
        for bfi in range(max_bfi + 1):
            for v in codes:
                r = g = b = w = 0
                if ch == "R": r = v
                elif ch == "G": g = v
                elif ch == "B": b = v
                elif ch == "W": w = v
                rows.append({
                    "name": f"{ch}_v{v:03d}_bfi{bfi}",
                    "r": r, "g": g, "b": b, "w": w,
                    "bfi_r": bfi if ch == "R" else 0,
                    "bfi_g": bfi if ch == "G" else 0,
                    "bfi_b": bfi if ch == "B" else 0,
                    "bfi_w": bfi if ch == "W" else 0,
                    "repeats": infer_repeats_from_code(v, bfi),
                })
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name","r","g","b","w","bfi_r","bfi_g","bfi_b","bfi_w","repeats"])
        w.writeheader(); w.writerows(rows)
    return rows

def write_temporal_blend_plan(channel: str, out_csv: Path, max_bfi: int = 4, step: int = 0, floor_step: int | None = None):
    upper_codes = code_set_for_step(step)
    floor_codes = code_set_for_step(step if floor_step is None else floor_step)
    floor_codes = [v for v in floor_codes if 0 <= int(v) < 255]
    rows = []
    chs = CHANNELS if channel == "ALL" else [channel]

    for v in upper_codes:
        for ch in chs:
            r = g = b = w = 0
            if ch == "R": r = v
            elif ch == "G": g = v
            elif ch == "B": b = v
            elif ch == "W": w = v
            rows.append({
                "name": f"{ch}_v{v:03d}_bfi0",
                "mode": "fill8",
                "r": r, "g": g, "b": b, "w": w,
                "lower_r": 0, "lower_g": 0, "lower_b": 0, "lower_w": 0,
                "upper_r": r, "upper_g": g, "upper_b": b, "upper_w": w,
                "bfi_r": 0, "bfi_g": 0, "bfi_b": 0, "bfi_w": 0,
                "repeats": infer_repeats_from_code(v, 0),
            })

    for floor in floor_codes:
        for v in upper_codes:
            if int(v) <= int(floor):
                continue
            for ch in chs:
                for bfi in range(1, max_bfi + 1):
                    lower_r = lower_g = lower_b = lower_w = 0
                    upper_r = upper_g = upper_b = upper_w = 0
                    bfi_r = bfi_g = bfi_b = bfi_w = 0
                    if ch == "R":
                        lower_r = floor; upper_r = v; bfi_r = bfi
                    elif ch == "G":
                        lower_g = floor; upper_g = v; bfi_g = bfi
                    elif ch == "B":
                        lower_b = floor; upper_b = v; bfi_b = bfi
                    elif ch == "W":
                        lower_w = floor; upper_w = v; bfi_w = bfi
                    rows.append({
                        "name": f"{ch}_floor{floor:03d}_v{v:03d}_bfi{bfi}",
                        "mode": "blend8",
                        "r": upper_r,
                        "g": upper_g,
                        "b": upper_b,
                        "w": upper_w,
                        "lower_r": lower_r,
                        "lower_g": lower_g,
                        "lower_b": lower_b,
                        "lower_w": lower_w,
                        "upper_r": upper_r,
                        "upper_g": upper_g,
                        "upper_b": upper_b,
                        "upper_w": upper_w,
                        "bfi_r": bfi_r,
                        "bfi_g": bfi_g,
                        "bfi_b": bfi_b,
                        "bfi_w": bfi_w,
                        "repeats": infer_repeats_from_blend(v, floor, bfi),
                    })

    fieldnames = [
        "name", "mode", "r", "g", "b", "w",
        "lower_r", "lower_g", "lower_b", "lower_w",
        "upper_r", "upper_g", "upper_b", "upper_w",
        "bfi_r", "bfi_g", "bfi_b", "bfi_w", "repeats",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader(); w.writerows(rows)
    return rows

def write_temporal_blend_plan_targeted16(channel: str, out_csv: Path, max_bfi: int = 4):
    upper_codes = targeted16_upper_code_set()
    floor_codes = targeted16_floor_code_set()
    rows = []
    chs = CHANNELS if channel == "ALL" else [channel]

    for v in range(256):
        for ch in chs:
            r = g = b = w = 0
            if ch == "R": r = v
            elif ch == "G": g = v
            elif ch == "B": b = v
            elif ch == "W": w = v
            rows.append({
                "name": f"{ch}_v{v:03d}_bfi0",
                "mode": "fill8",
                "r": r, "g": g, "b": b, "w": w,
                "lower_r": 0, "lower_g": 0, "lower_b": 0, "lower_w": 0,
                "upper_r": r, "upper_g": g, "upper_b": b, "upper_w": w,
                "bfi_r": 0, "bfi_g": 0, "bfi_b": 0, "bfi_w": 0,
                "repeats": infer_targeted_repeats_from_code(v, 0),
            })

    for floor in floor_codes:
        candidate_uppers = list(range(max(1, int(floor) + 1), 256)) if int(floor) == 0 else [v for v in upper_codes if int(v) > int(floor)]
        for v in candidate_uppers:
            for ch in chs:
                for bfi in range(1, max_bfi + 1):
                    lower_r = lower_g = lower_b = lower_w = 0
                    upper_r = upper_g = upper_b = upper_w = 0
                    bfi_r = bfi_g = bfi_b = bfi_w = 0
                    if ch == "R":
                        lower_r = floor; upper_r = v; bfi_r = bfi
                    elif ch == "G":
                        lower_g = floor; upper_g = v; bfi_g = bfi
                    elif ch == "B":
                        lower_b = floor; upper_b = v; bfi_b = bfi
                    elif ch == "W":
                        lower_w = floor; upper_w = v; bfi_w = bfi
                    rows.append({
                        "name": f"{ch}_floor{floor:03d}_v{v:03d}_bfi{bfi}",
                        "mode": "blend8",
                        "r": upper_r,
                        "g": upper_g,
                        "b": upper_b,
                        "w": upper_w,
                        "lower_r": lower_r,
                        "lower_g": lower_g,
                        "lower_b": lower_b,
                        "lower_w": lower_w,
                        "upper_r": upper_r,
                        "upper_g": upper_g,
                        "upper_b": upper_b,
                        "upper_w": upper_w,
                        "bfi_r": bfi_r,
                        "bfi_g": bfi_g,
                        "bfi_b": bfi_b,
                        "bfi_w": bfi_w,
                        "repeats": infer_targeted_repeats_from_blend(v, floor, bfi),
                    })

    fieldnames = [
        "name", "mode", "r", "g", "b", "w",
        "lower_r", "lower_g", "lower_b", "lower_w",
        "upper_r", "upper_g", "upper_b", "upper_w",
        "bfi_r", "bfi_g", "bfi_b", "bfi_w", "repeats",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader(); w.writerows(rows)
    return rows

def identify_channel_from_render(render: dict):
    vals = {ch: int(render.get(ch.lower(), 0)) for ch in CHANNELS}
    bfis = {ch: int(render.get(f"bfi_{ch.lower()}", 0)) for ch in CHANNELS}
    active = [(ch, vals[ch], bfis[ch]) for ch in CHANNELS if vals[ch] > 0]
    return active[0] if len(active) == 1 else None


def _row_int(rec, key, default=0):
    value = rec.get(key, default)
    if value in (None, ""):
        return int(default)
    return int(value)


def _normalize_raw_capture_mode(rec: dict, default_mode: str = "fill8"):
    mode = str(rec.get("mode", default_mode)).strip().lower()
    if mode in {"fill8", "blend8", "fill16", "blend16"}:
        return mode
    if any(str(rec.get(field, "")).strip() for field in ["lower_r", "lower_g", "lower_b", "lower_w", "upper_r", "upper_g", "upper_b", "upper_w"]):
        return "blend8"
    return default_mode


def _extract_single_channel_temporal_state(rec: dict, default_mode: str = "fill8"):
    mode = _normalize_raw_capture_mode(rec, default_mode=default_mode)
    if mode in {"fill16", "blend16"}:
        return None

    upper = {ch: _row_int(rec, f"upper_{ch.lower()}", _row_int(rec, ch.lower(), 0)) for ch in CHANNELS}
    lower = {ch: _row_int(rec, f"lower_{ch.lower()}", 0) for ch in CHANNELS}
    bfis = {ch: _row_int(rec, f"bfi_{ch.lower()}", 0) for ch in CHANNELS}

    active = [ch for ch in CHANNELS if upper[ch] > 0 or lower[ch] > 0 or bfis[ch] > 0]
    if len(active) != 1:
        return None

    ch = active[0]
    normalized_mode = "blend8" if (mode == "blend8" or lower[ch] > 0) else "fill8"
    return {
        "channel": ch,
        "mode": normalized_mode,
        "lower_value": int(lower[ch]),
        "upper_value": int(upper[ch]),
        "value": int(upper[ch]),
        "bfi": int(bfis[ch]),
    }

def load_json_measurements(path: Path):
    items = []
    for p in sorted(path.glob("single_measure_*.json")):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            render = obj.get("render", {})
            meas = obj.get("measurement", {})
            ident = _extract_single_channel_temporal_state(render, default_mode=str(render.get("mode", "fill8") or "fill8"))
            if ident is None or meas.get("Y") is None:
                continue
            items.append({
                "file": p.name,
                "channel": ident["channel"],
                "mode": ident["mode"],
                "value": int(ident["value"]),
                "lower_value": int(ident["lower_value"]),
                "upper_value": int(ident["upper_value"]),
                "bfi": int(ident["bfi"]),
                "Y": float(meas["Y"]), "X": meas.get("X"), "x": meas.get("x"), "y": meas.get("y")
            })
        except Exception:
            continue
    return items

def load_plan_capture_csvs(path: Path):
    items = []
    for p in sorted(path.glob("plan_capture_*.csv")):
        try:
            with open(p, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if str(row.get("ok", "")).strip() != "True" or row.get("Y") in (None, ""):
                        continue
                    ident = _extract_single_channel_temporal_state(row, default_mode="fill8")
                    if ident is None:
                        continue
                    items.append({
                        "file": p.name,
                        "channel": ident["channel"],
                        "mode": ident["mode"],
                        "value": int(ident["value"]),
                        "lower_value": int(ident["lower_value"]),
                        "upper_value": int(ident["upper_value"]),
                        "bfi": int(ident["bfi"]),
                        "Y": float(row["Y"]),
                        "X": float(row["X"]) if row.get("X") not in (None, "") else None,
                        "x": float(row["x"]) if row.get("x") not in (None, "") else None,
                        "y": float(row["y"]) if row.get("y") not in (None, "") else None
                    })
        except Exception:
            continue
    return items

def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None

def interpolate_256(points_by_value: dict[int, float]):
    if not points_by_value:
        return [0.0] * 256
    known = sorted((int(k), float(v)) for k, v in points_by_value.items())
    lut = [0.0] * 256
    for i in range(len(known) - 1):
        x0, y0 = known[i]
        x1, y1 = known[i + 1]
        lut[x0] = y0
        if x1 > x0:
            for x in range(x0 + 1, x1):
                t = (x - x0) / (x1 - x0)
                lut[x] = y0 * (1 - t) + y1 * t
    first_x, first_y = known[0]
    for x in range(0, first_x + 1):
        lut[x] = first_y
    last_x, last_y = known[-1]
    for x in range(last_x, 256):
        lut[x] = last_y
    return lut

def dedupe_ladder_states(ladder):
    ladder = sorted(
        ladder,
        key=lambda e: (
            e["output_q16"],
            e["bfi"],
            int(e.get("lower_value", 0)),
            int(e.get("upper_value", e.get("value", 0))),
            e["value"],
        ),
    )
    deduped = []
    for e in ladder:
        if deduped and e["output_q16"] == deduped[-1]["output_q16"]:
            if e["bfi"] < deduped[-1]["bfi"]:
                deduped[-1] = e
        else:
            deduped.append(e)
    return deduped


def _ensure_explicit_black_ladder_state(ladder):
    if any(int(entry.get("output_q16", 0)) <= 0 for entry in ladder):
        return list(ladder)
    black_entry = {
        "mode": "fill8",
        "lower_value": 0,
        "upper_value": 0,
        "value": 0,
        "bfi": 0,
        "estimated_output": 0.0,
        "output_q16": 0,
        "normalized_output": 0.0,
    }
    return [black_entry, *list(ladder)]

def build_monotonic_ladder(deduped_ladder):
    mono = []
    last_q16 = -1
    for e in deduped_ladder:
        q16 = int(e["output_q16"])
        if q16 <= last_q16:
            continue
        norm = float(e.get("normalized_output", q16 / 65535.0))
        mono.append({
            "rank": len(mono),
            "mode": str(e.get("mode", "fill8")),
            "lower_value": int(e.get("lower_value", 0)),
            "upper_value": int(e.get("upper_value", e.get("value", 0))),
            "value": int(e["value"]),
            "bfi": int(e["bfi"]),
            "output_q16": q16,
            "normalized_output": norm,
            "delta_q16_from_prev": 0 if not mono else (q16 - mono[-1]["output_q16"]),
        })
        last_q16 = q16
    return mono

def build_luts(measure_dir: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = load_json_measurements(measure_dir) + load_plan_capture_csvs(measure_dir)
    grouped = defaultdict(list)
    for r in rows:
        grouped[(
            r["channel"],
            str(r.get("mode", "fill8")),
            int(r.get("lower_value", 0)),
            int(r.get("upper_value", r.get("value", 0))),
            int(r["bfi"]),
        )].append(r["Y"])

    summary = {"channels": {}, "sources": {"total_rows": len(rows)}}
    point_rows = []
    xy_point_rows = []

    for r in rows:
        x = r.get("x")
        y = r.get("y")
        Y = r.get("Y")
        if x is None or y is None or Y is None:
            continue
        lower_value = int(r.get("lower_value", 0))
        upper_value = int(r.get("upper_value", r.get("value", 0)))
        mode = "blend8" if str(r.get("mode", "fill8")).lower() == "blend8" or lower_value > 0 else "fill8"
        xy_point_rows.append({
            "channel": str(r["channel"]),
            "mode": mode,
            "lower_value": lower_value,
            "upper_value": upper_value,
            "value": upper_value,
            "bfi": int(r["bfi"]),
            "X": float(r.get("X")) if r.get("X") is not None else "",
            "Y": float(Y),
            "x": float(x),
            "y": float(y),
        })

    for ch in CHANNELS:
        raw_est = defaultdict(list)
        ladder = []
        for (channel, mode, lower_value, upper_value, bfi), ys in grouped.items():
            if channel != ch:
                continue
            y_avg = mean(ys)
            if y_avg is None:
                continue
            mode = "blend8" if str(mode).lower() == "blend8" or int(lower_value) > 0 else "fill8"
            value = int(upper_value)
            y_est = None
            if mode == "fill8" and int(lower_value) == 0:
                y_est = y_avg * (bfi + 1)
                raw_est[value].append(y_est)
            point_rows.append({
                "channel": ch,
                "mode": mode,
                "lower_value": int(lower_value),
                "upper_value": int(upper_value),
                "value": value,
                "bfi": bfi,
                "y_measured_avg": y_avg,
                "y_est_nobfi": y_est,
                "samples": len(ys),
            })
            ladder.append({
                "mode": mode,
                "lower_value": int(lower_value),
                "upper_value": int(upper_value),
                "value": int(value),
                "bfi": int(bfi),
                "estimated_output": float(y_avg),
            })

        value_est = {}
        for value, vals in raw_est.items():
            vals = sorted(vals)
            value_est[int(value)] = float(vals[len(vals)//2] if len(vals) >= 3 else (sum(vals)/len(vals)))

        if not ladder:
            summary["channels"][ch] = {
                "points": 0,
                "measured_state_points": 0,
                "preview_value_points": 0,
                "nonzero_points": 0,
                "max_estimated_nobfi_Y": None,
                "ladder_states": 0,
                "monotonic_states": 0,
            }
            continue

        max_y = max([float(e["estimated_output"]) for e in ladder] + [0.0]) or 1.0
        preview_points = {}
        preview_grouped = defaultdict(list)
        for entry in ladder:
            preview_grouped[int(entry["value"])].append(float(entry["estimated_output"]))
        for value, vals in preview_grouped.items():
            preview_points[int(value)] = max(vals)

        normalized = {v: y / max_y for v, y in preview_points.items()}
        lut256 = interpolate_256(normalized) if normalized else [0.0] * 256

        for entry in ladder:
            entry["output_q16"] = max(0, min(65535, round((entry["estimated_output"] / max_y) * 65535.0)))
            entry["normalized_output"] = entry["output_q16"] / 65535.0

        deduped = dedupe_ladder_states(ladder)
        deduped = _ensure_explicit_black_ladder_state(deduped)
        monotonic = build_monotonic_ladder(deduped)

        summary["channels"][ch] = {
            "points": len(ladder),
            "measured_state_points": len(ladder),
            "max_estimated_nobfi_Y": max_y,
            "nonzero_points": sum(1 for y in lut256 if y > 0),
            "ladder_states": len(ladder),
            "monotonic_states": len(monotonic),
        }

        with open(out_dir / f"{ch.lower()}_measured_points.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["plotted_value", "value", "bfi", "mode", "lower_value", "upper_value", "normalized_output"],
            )
            w.writeheader()
            for entry in ladder:
                w.writerow({
                    "plotted_value": float(entry["value"]) + (float(entry["bfi"]) * 0.35),
                    "value": int(entry["value"]),
                    "bfi": int(entry["bfi"]),
                    "mode": str(entry.get("mode", "fill8")),
                    "lower_value": int(entry.get("lower_value", 0)),
                    "upper_value": int(entry.get("upper_value", entry.get("value", 0))),
                    "normalized_output": float(entry["normalized_output"]),
                })

        with open(out_dir / f"{ch.lower()}_lut256.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["value", "normalized_output"])
            for i, y in enumerate(lut256):
                w.writerow([i, y])
        (out_dir / f"{ch.lower()}_lut256.json").write_text(json.dumps(lut256, indent=2), encoding="utf-8")

        with open(out_dir / f"{ch.lower()}_temporal_ladder.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["mode", "lower_value", "upper_value", "value", "bfi", "estimated_output", "output_q16", "normalized_output"],
            )
            w.writeheader()
            w.writerows(deduped)
        (out_dir / f"{ch.lower()}_temporal_ladder.json").write_text(json.dumps(deduped, indent=2), encoding="utf-8")

        with open(out_dir / f"{ch.lower()}_monotonic_ladder.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["rank", "mode", "lower_value", "upper_value", "value", "bfi", "output_q16", "normalized_output", "delta_q16_from_prev"],
            )
            w.writeheader()
            w.writerows(monotonic)
        (out_dir / f"{ch.lower()}_monotonic_ladder.json").write_text(json.dumps(monotonic, indent=2), encoding="utf-8")

    with open(out_dir / "all_measurement_points.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["channel", "mode", "lower_value", "upper_value", "value", "bfi", "y_measured_avg", "y_est_nobfi", "samples"],
        )
        w.writeheader()
        w.writerows(point_rows)

    with open(out_dir / "all_measurement_xy_points.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["channel", "mode", "lower_value", "upper_value", "value", "bfi", "X", "Y", "x", "y"],
        )
        w.writeheader()
        w.writerows(xy_point_rows)

    (out_dir / "lut_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

def export_runtime_json(lut_dir: Path, out_path: Path):
    data = {"format": "TemporalBFI_LUT256_v1", "channels": {}}
    for ch in CHANNELS:
        p = lut_dir / f"{ch.lower()}_lut256.json"
        if p.exists():
            data["channels"][ch] = json.loads(p.read_text(encoding="utf-8"))
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def export_runtime_header(lut_dir: Path, out_path: Path):
    lines = ["// Auto-generated runtime LUT header", "#pragma once", "", "namespace TemporalBFIRuntimeLUT {"]
    for ch in CHANNELS:
        p = lut_dir / f"{ch.lower()}_lut256.json"
        if not p.exists():
            continue
        arr = json.loads(p.read_text(encoding="utf-8"))
        q16 = [max(0, min(65535, round(float(v) * 65535.0))) for v in arr]
        lines.append(f"static const uint16_t LUT_{ch}[256] = {{")
        for i in range(0, 256, 8):
            lines.append("    " + ", ".join(str(v) for v in q16[i:i+8]) + ",")
        lines.append("};\n")
    lines.append("} // namespace TemporalBFIRuntimeLUT\n")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _decimate_ladder(entries, max_entries):
    """Decimate a monotonic ladder to at most *max_entries* using Q16 bucket
    selection.

    Strategy:
      1. All fill8 anchors (bfi == 0) are preserved unconditionally — these are
         the 0..255 reference ceilings.
      2. Remaining budget is distributed across equal-width Q16 buckets among
         the blend states (bfi > 0).  Within each bucket the entry with the
         highest BFI (then highest value) is kept — higher BFI states give
         finer temporal resolution.
      3. The output is sorted by ascending output_q16.
    """
    if not entries or len(entries) <= max_entries:
        return entries

    anchors = [e for e in entries if int(e.get("bfi", 0)) == 0]
    blend   = [e for e in entries if int(e.get("bfi", 0)) != 0]

    # If anchors alone exceed the budget, uniformly sample them (unlikely).
    if len(anchors) >= max_entries:
        step = len(anchors) / max_entries
        sampled = [anchors[int(i * step)] for i in range(max_entries)]
        # guarantee first & last
        sampled[0]  = anchors[0]
        sampled[-1] = anchors[-1]
        sampled.sort(key=lambda e: (int(e["output_q16"]), int(e.get("value", 0))))
        return sampled

    remaining_budget = max_entries - len(anchors)

    if remaining_budget <= 0 or not blend:
        anchors.sort(key=lambda e: (int(e["output_q16"]), int(e.get("value", 0))))
        return anchors

    # Bucket blend entries by Q16.
    q16_max = 65535
    bucket_width = max(1, (q16_max + 1) // remaining_budget)
    buckets: dict[int, list] = {}
    for e in blend:
        b = int(e["output_q16"]) // bucket_width
        buckets.setdefault(b, []).append(e)

    # From each bucket, keep the entry with highest BFI then highest value.
    selected = []
    for b in sorted(buckets.keys()):
        best = max(buckets[b], key=lambda e: (int(e["bfi"]), int(e.get("value", 0))))
        selected.append(best)

    # If still over budget, uniformly subsample.
    if len(selected) > remaining_budget:
        step = len(selected) / remaining_budget
        selected = [selected[int(i * step)] for i in range(remaining_budget)]

    result = anchors + selected
    result.sort(key=lambda e: (int(e["output_q16"]), int(e.get("value", 0)), int(e.get("bfi", 0))))
    return result


def export_solver_header(lut_dir: Path, out_path: Path, max_bfi: int = 4, max_entries: int | None = None):
    lines = [
        "// Auto-generated temporal ladder solver header",
        "#pragma once", "", '#include <TemporalBFI.h>', "",
        "namespace TemporalBFIRuntimeLUT {",
        f"static const uint8_t MAX_BFI = {max_bfi};", ""
    ]
    for ch in CHANNELS:
        p_mono = lut_dir / f"{ch.lower()}_monotonic_ladder.json"
        p_full = lut_dir / f"{ch.lower()}_temporal_ladder.json"
        p = p_mono if p_mono.exists() else p_full
        if not p.exists():
            lines.append(f"static const TemporalBFI::LadderEntry* LADDER_{ch} = nullptr;")
            lines.append(f"static const uint16_t LADDER_{ch}_COUNT = 0;\n")
            continue
        arr = json.loads(p.read_text(encoding="utf-8"))
        if max_entries is not None:
            arr = _decimate_ladder(arr, max_entries)
        lower_values = [int(e.get("lower_value", 0)) for e in arr]
        upper_values = [int(e.get("upper_value", e.get("value", 0))) for e in arr]
        lines.append(f"static const TemporalBFI::LadderEntry LADDER_{ch}[] PROGMEM = {{")
        for e in arr:
            lines.append(f"    {{{int(e['output_q16'])}, {int(e['value'])}, {int(e['bfi'])}}},")
        lines.append("};")
        lines.append(f"static const uint8_t LADDER_{ch}_LOWER[] PROGMEM = {{")
        for i in range(0, len(lower_values), 32):
            lines.append("    " + ", ".join(str(v) for v in lower_values[i:i+32]) + ",")
        lines.append("};")
        lines.append(f"static const uint8_t LADDER_{ch}_UPPER[] PROGMEM = {{")
        for i in range(0, len(upper_values), 32):
            lines.append("    " + ", ".join(str(v) for v in upper_values[i:i+32]) + ",")
        lines.append("};")
        lines.append(f"static const uint16_t LADDER_{ch}_COUNT = sizeof(LADDER_{ch}) / sizeof(LADDER_{ch}[0]);\n")
    lines.append("} // namespace TemporalBFIRuntimeLUT\n")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _parse_named_u16_arrays(text: str):
    pat = re.compile(
        r"static\s+const\s+uint16_t\s+([A-Za-z_][A-Za-z0-9_]*)\s*\[(\d+)\]\s*(?:PROGMEM\s*)?=\s*\{(.*?)\};",
        re.S,
    )
    arrays = {}
    for name, _size_str, body in pat.findall(text):
        values = [int(v) for v in re.findall(r"\d+", body)]
        arrays[name] = [max(0, min(65535, int(v))) for v in values]
    return arrays


def _try_load_calibration_profile_8to16(arrays, required_max_bfi: int):
    profiles = {}
    per_bfi = {}

    for color in CHANNELS:
        key = f"LUT_{color}_8_TO_16"
        if key not in arrays or len(arrays[key]) != 256:
            return None
        profiles[color] = arrays[key]

        bfi_tables = {}
        for bfi in range(int(required_max_bfi) + 1):
            bfi_key = f"LUT_{color}_BFI{bfi}_8_TO_16"
            if bfi_key not in arrays or len(arrays[bfi_key]) != 256:
                return None
            bfi_tables[bfi] = arrays[bfi_key]
        per_bfi[color] = bfi_tables

    return {
        "mode": "legacy_8to16",
        "profiles": profiles,
        "per_bfi": per_bfi,
    }


def _try_load_calibration_profile_true16(arrays, text: str):
    luts = {}
    lengths = set()

    for color in CHANNELS:
        key = f"LUT_{color}_16_TO_16"
        if key not in arrays:
            return None
        arr = arrays[key]
        if len(arr) < 2:
            raise ValueError(f"Calibration table {key} must contain at least 2 entries")
        luts[color] = arr
        lengths.add(len(arr))

    if len(lengths) != 1:
        raise ValueError("True16 calibration LUT tables must all have the same length")

    lut_size = int(next(iter(lengths)))
    m = re.search(r"static\s+const\s+uint16_t\s+LUT_SIZE\s*=\s*(\d+)\s*;", text)
    if m is not None:
        declared_size = int(m.group(1))
        if declared_size >= 2:
            lut_size = min(lut_size, declared_size)
    if lut_size < 2:
        raise ValueError("True16 calibration LUT size must be >= 2")

    return {
        "mode": "true16_input_q16",
        "true16_luts": {ch: luts[ch][:lut_size] for ch in CHANNELS},
        "true16_lut_size": lut_size,
    }


def _load_calibration_for_solver_precompute(calibration_header: Path, required_max_bfi: int):
    text = calibration_header.read_text(encoding="utf-8")
    arrays = _parse_named_u16_arrays(text)

    legacy = _try_load_calibration_profile_8to16(arrays, required_max_bfi=required_max_bfi)
    if legacy is not None:
        return legacy

    true16 = _try_load_calibration_profile_true16(arrays, text)
    if true16 is not None:
        return true16

    raise ValueError(
        "Missing required calibration tables. Expected either legacy LUT_*_8_TO_16/LUT_*_BFIx_8_TO_16 "
        "or True16 LUT_*_16_TO_16 tables."
    )


def _load_runtime_solver_ladders(solver_header: Path):
    text = solver_header.read_text(encoding="utf-8")

    max_bfi_match = re.search(r"static const uint8_t MAX_BFI\s*=\s*(\d+)\s*;", text)
    if not max_bfi_match:
        raise ValueError("Could not parse MAX_BFI from solver header")
    max_bfi = int(max_bfi_match.group(1))

    array_pat = re.compile(r"static const TemporalBFI::LadderEntry LADDER_([RGBW])\[\]\s*=\s*\{(.*?)\};", re.S)
    entry_pat = re.compile(r"\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\}")
    u8_array_pat = re.compile(r"static const uint8_t LADDER_([RGBW])_(LOWER|UPPER)\[\]\s*=\s*\{(.*?)\};", re.S)

    ladders_by_color = {}
    for color, body in array_pat.findall(text):
        entries = []
        for output_q16, value, bfi in entry_pat.findall(body):
            entries.append(
                {
                    "output_q16": max(0, min(65535, int(output_q16))),
                    "value": max(0, min(255, int(value))),
                    "bfi": max(0, int(bfi)),
                }
            )
        ladders_by_color[color] = entries

    ladder_bounds = {}
    for color, bound_name, body in u8_array_pat.findall(text):
        values = [max(0, min(255, int(v))) for v in re.findall(r"\d+", body)]
        ladder_bounds.setdefault(color, {})[bound_name.lower()] = values

    for color in CHANNELS:
        if color not in ladders_by_color:
            raise ValueError(f"Missing LADDER_{color} in solver header")
        if not ladders_by_color[color]:
            raise ValueError(f"LADDER_{color} has no entries")
        bounds = ladder_bounds.get(color, {})
        lower_values = bounds.get("lower", [0] * len(ladders_by_color[color]))
        upper_values = bounds.get("upper", [int(e["value"]) for e in ladders_by_color[color]])
        if len(lower_values) != len(ladders_by_color[color]):
            raise ValueError(f"LADDER_{color}_LOWER length mismatch")
        if len(upper_values) != len(ladders_by_color[color]):
            raise ValueError(f"LADDER_{color}_UPPER length mismatch")
        for idx, entry in enumerate(ladders_by_color[color]):
            entry["lower_value"] = int(lower_values[idx])
            entry["upper_value"] = int(upper_values[idx])
            entry["mode"] = "blend8" if int(lower_values[idx]) > 0 else "fill8"

    return {
        "max_bfi": max_bfi,
        "ladders": [ladders_by_color[color] for color in SOLVER_CHANNEL_ORDER],
    }


def _derive_solver_lut_size_from_runtime_ladders(runtime_ladders):
    derived = max((len(channel_ladder) for channel_ladder in runtime_ladders), default=0)
    if derived < 2:
        raise ValueError("Runtime solver ladders must contain at least 2 entries to derive solver LUT size")
    return int(derived)


def _derive_transfer_bucket_count_from_lut_dir(lut_dir: Path):
    derived = max((len(load_monotonic_ladder(lut_dir, ch)) for ch in CHANNELS), default=0)
    if derived < 2:
        raise ValueError("Runtime LUT directory must contain at least 2 monotonic ladder entries to derive transfer bucket count")
    return int(derived)


def _default_solver_policy(max_bfi: int):
    return {
        "min_error_q16": 64,
        "relative_error_divisor": 24,
        "min_value_ratio_numerator": 3,
        "min_value_ratio_denominator": 8,
        "low_end_protect_threshold": 48,
        "low_end_max_drop": 10,
        "max_bfi": int(max_bfi),
        "prefer_higher_bfi": True,
        "preferred_min_bfi": 0,
        "highlight_bypass_start": 240,
    }


def _allowed_error_q16(target_q16: int, policy):
    rel = int(target_q16) // int(policy["relative_error_divisor"]) if int(policy["relative_error_divisor"]) > 0 else 0
    return rel if rel > int(policy["min_error_q16"]) else int(policy["min_error_q16"])


def _passes_resolution_guard(input8_approx: int, candidate_value: int, policy):
    if int(input8_approx) == 0:
        return int(candidate_value) == 0

    min_allowed_by_ratio = (int(input8_approx) * int(policy["min_value_ratio_numerator"])) // int(policy["min_value_ratio_denominator"])
    if int(candidate_value) < int(min_allowed_by_ratio):
        return False

    if int(input8_approx) <= int(policy["low_end_protect_threshold"]):
        min_allowed_low = int(input8_approx) - int(policy["low_end_max_drop"])
        if min_allowed_low < 0:
            min_allowed_low = 0
        if int(candidate_value) < int(min_allowed_low):
            return False

    return True


def _passes_baseline_policy(input8_approx: int, candidate_bfi: int, policy):
    if int(candidate_bfi) > int(policy["max_bfi"]):
        return False
    if int(policy["preferred_min_bfi"]) == 0:
        return True
    if int(input8_approx) >= int(policy["highlight_bypass_start"]):
        return True
    return int(candidate_bfi) >= int(policy["preferred_min_bfi"])


def _passes_solve_constraints(candidate_bfi: int, constraints, policy):
    if int(candidate_bfi) > int(policy["max_bfi"]):
        return False
    if int(candidate_bfi) < int(constraints["min_bfi"]):
        return False
    if int(candidate_bfi) > int(constraints["max_bfi"]):
        return False
    return True


def _apply_constraints_to_target_q16(target_q16: int, constraints):
    scaled = (int(target_q16) * int(constraints["target_scale_q16"]) + 32767) // 65535
    if scaled > int(constraints["max_target_q16"]):
        scaled = int(constraints["max_target_q16"])
    if scaled > 65535:
        scaled = 65535
    return int(scaled)


def _calibrate_input_q16_for_solver(q16: int, solver_channel: int, calibration):
    clamped_q16 = int(max(0, min(65535, int(q16))))
    if str(calibration.get("mode", "legacy_8to16")) != "true16_input_q16":
        return clamped_q16

    if int(solver_channel) < 0 or int(solver_channel) >= len(SOLVER_CHANNEL_ORDER):
        return clamped_q16

    color = SOLVER_CHANNEL_ORDER[int(solver_channel)]
    lut = calibration.get("true16_luts", {}).get(color)
    if not lut:
        return clamped_q16

    lut_size = len(lut)
    if lut_size < 2:
        return clamped_q16

    idx = (clamped_q16 * (lut_size - 1) + 32767) // 65535
    if idx < 0:
        idx = 0
    if idx >= lut_size:
        idx = lut_size - 1
    return int(lut[idx])


def _prepare_solver_channel_entries(channel_ladder, color, calibration):
    entries = []
    entries_by_bfi = defaultdict(list)
    use_legacy_candidates = str(calibration.get("mode", "legacy_8to16")) == "legacy_8to16"
    bfi_tables = calibration.get("per_bfi", {}).get(color, {}) if use_legacy_candidates else {}
    max_bfi_key = max(int(k) for k in bfi_tables.keys()) if bfi_tables else 0

    for idx, e in enumerate(channel_ladder):
        bfi = int(e["bfi"])
        value = int(e["value"])
        if use_legacy_candidates:
            table = bfi_tables.get(bfi, bfi_tables[max_bfi_key])
            candidate_q16_legacy = int(table[value])
        else:
            candidate_q16_legacy = int(e["output_q16"])
        prepared = {
            "output_q16": int(e["output_q16"]),
            "value": value,
            "lower_value": int(e.get("lower_value", 0)),
            "upper_value": int(e.get("upper_value", value)),
            "mode": str(e.get("mode", "fill8")),
            "bfi": bfi,
            "ladder_index": idx,
            "candidate_q16_legacy": candidate_q16_legacy,
        }
        entries.append(prepared)
        entries_by_bfi[bfi].append(prepared)

    return entries, entries_by_bfi


def _candidate_q16(entry, use_legacy_candidates):
    if use_legacy_candidates:
        return int(entry["candidate_q16_legacy"])
    return int(entry["output_q16"])


def _solve_state_from_q16_internal(
    target_q16: int,
    input8_approx: int,
    channel_entries,
    policy,
    constraints=None,
    use_legacy_candidates=True,
    constrained_entries=None,
):
    out = {
        "value": 0,
        "bfi": 0,
        "output_q16": 0,
        "ladder_index": 0,
    }
    if int(target_q16) <= 0 or int(input8_approx) <= 0 or not channel_entries:
        return out

    entries = constrained_entries if (constraints is not None and constrained_entries) else channel_entries
    tolerance = _allowed_error_q16(int(target_q16), policy)
    prefer_higher_bfi = bool(constraints["prefer_higher_bfi"]) if constraints is not None else bool(policy["prefer_higher_bfi"])

    best_entry = None
    best_err = 0xFFFF

    for e in entries:
        if int(e["value"]) == 0:
            continue

        if constraints is not None:
            if not _passes_solve_constraints(int(e["bfi"]), constraints, policy):
                continue
        else:
            if not _passes_baseline_policy(int(input8_approx), int(e["bfi"]), policy):
                continue

        if not _passes_resolution_guard(int(input8_approx), int(e["value"]), policy):
            continue

        candidate_q16 = _candidate_q16(e, use_legacy_candidates)
        err = abs(int(candidate_q16) - int(target_q16))
        if err > tolerance:
            continue

        if best_entry is None:
            best_entry = e
            best_err = err
            continue

        if err < best_err:
            best_entry = e
            best_err = err
            continue
        if err > best_err:
            continue

        best_q16 = _candidate_q16(best_entry, use_legacy_candidates)
        if prefer_higher_bfi:
            if int(e["bfi"]) > int(best_entry["bfi"]):
                best_entry = e
                best_err = err
                continue
            if int(e["bfi"]) < int(best_entry["bfi"]):
                continue

        if int(e["value"]) > int(best_entry["value"]):
            best_entry = e
            best_err = err
            continue

        if int(candidate_q16) > int(best_q16):
            best_entry = e
            best_err = err

    if best_entry is not None:
        out["value"] = int(best_entry["value"])
        out["bfi"] = int(best_entry["bfi"])
        out["output_q16"] = int(_candidate_q16(best_entry, use_legacy_candidates))
        out["ladder_index"] = int(best_entry["ladder_index"])
        return out

    found_floor = False
    best_floor_q16 = 0
    best_entry = None

    for e in entries:
        if constraints is not None:
            if not _passes_solve_constraints(int(e["bfi"]), constraints, policy):
                continue
        else:
            if not _passes_baseline_policy(int(input8_approx), int(e["bfi"]), policy):
                continue

        if not _passes_resolution_guard(int(input8_approx), int(e["value"]), policy):
            continue

        candidate_q16 = _candidate_q16(e, use_legacy_candidates)
        if int(candidate_q16) > int(target_q16):
            continue

        if not found_floor or int(candidate_q16) > int(best_floor_q16):
            found_floor = True
            best_floor_q16 = int(candidate_q16)
            best_entry = e
            continue

        if int(candidate_q16) == int(best_floor_q16):
            if prefer_higher_bfi:
                if int(e["bfi"]) > int(best_entry["bfi"]):
                    best_entry = e
                    continue
                if int(e["bfi"]) < int(best_entry["bfi"]):
                    continue
            if int(e["value"]) > int(best_entry["value"]):
                best_entry = e

    if found_floor and best_entry is not None:
        out["value"] = int(best_entry["value"])
        out["bfi"] = int(best_entry["bfi"])
        out["output_q16"] = int(_candidate_q16(best_entry, use_legacy_candidates))
        out["ladder_index"] = int(best_entry["ladder_index"])
        return out

    nearest_err = 0xFFFFFFFF
    best_entry = None

    for e in entries:
        if constraints is not None:
            if not _passes_solve_constraints(int(e["bfi"]), constraints, policy):
                continue
        else:
            if int(e["bfi"]) > int(policy["max_bfi"]):
                continue

        candidate_q16 = _candidate_q16(e, use_legacy_candidates)
        err = abs(int(candidate_q16) - int(target_q16))
        if best_entry is None or err < nearest_err:
            nearest_err = err
            best_entry = e
            continue
        if err > nearest_err:
            continue

        if prefer_higher_bfi:
            if int(e["bfi"]) > int(best_entry["bfi"]):
                best_entry = e
                continue
            if int(e["bfi"]) < int(best_entry["bfi"]):
                continue
        if int(e["value"]) > int(best_entry["value"]):
            best_entry = e

    if best_entry is None:
        best_entry = channel_entries[0]

    out["value"] = int(best_entry["value"])
    out["bfi"] = int(best_entry["bfi"])
    out["output_q16"] = int(_candidate_q16(best_entry, use_legacy_candidates))
    out["ladder_index"] = int(best_entry["ladder_index"])
    return out


def _encode_state_from16(q16: int, channel_entries, policy, calibration, solver_channel: int):
    if int(q16) <= 0:
        return {"value": 0, "bfi": 0, "output_q16": 0, "ladder_index": 0}

    target_q16 = _calibrate_input_q16_for_solver(int(q16), int(solver_channel), calibration)
    input8_approx = (target_q16 * 255 + 32767) // 65535
    if input8_approx == 0:
        input8_approx = 1
    use_legacy_candidates = str(calibration.get("mode", "legacy_8to16")) == "legacy_8to16"
    return _solve_state_from_q16_internal(
        target_q16,
        input8_approx,
        channel_entries,
        policy,
        constraints=None,
        use_legacy_candidates=use_legacy_candidates,
    )


def _encode_state_from16_constrained(
    q16: int,
    channel_entries,
    policy,
    constraints,
    calibration,
    solver_channel: int,
    constrained_entries=None,
):
    if int(q16) <= 0:
        return {"value": 0, "bfi": 0, "output_q16": 0, "ladder_index": 0}

    target_q16 = _apply_constraints_to_target_q16(int(q16), constraints)
    target_q16 = _calibrate_input_q16_for_solver(int(target_q16), int(solver_channel), calibration)
    input8_approx = (target_q16 * 255 + 32767) // 65535
    if input8_approx == 0 and target_q16 != 0:
        input8_approx = 1
    use_legacy_candidates = str(calibration.get("mode", "legacy_8to16")) == "legacy_8to16"

    return _solve_state_from_q16_internal(
        target_q16,
        input8_approx,
        channel_entries,
        policy,
        constraints=constraints,
        use_legacy_candidates=use_legacy_candidates,
        constrained_entries=constrained_entries,
    )


def _build_solver_precomputed_tables(runtime_ladders, calibration, policy, solver_fixed_bfi_levels: int, solver_lut_size: int | None = None):
    fixed_levels = int(solver_fixed_bfi_levels)
    if fixed_levels < 1:
        raise ValueError("solver_fixed_bfi_levels must be >= 1")

    if solver_lut_size is None:
        resolved_solver_lut_size = _derive_solver_lut_size_from_runtime_ladders(runtime_ladders)
    else:
        resolved_solver_lut_size = int(solver_lut_size)
        if resolved_solver_lut_size < 2:
            raise ValueError("solver_lut_size must be >= 2")

    prepared_entries = []
    prepared_entries_by_bfi = []
    for solver_channel, color in enumerate(SOLVER_CHANNEL_ORDER):
        entries, by_bfi = _prepare_solver_channel_entries(
            runtime_ladders[solver_channel],
            color,
            calibration,
        )
        prepared_entries.append(entries)
        prepared_entries_by_bfi.append(by_bfi)

    solver_value_lut = [[0] * resolved_solver_lut_size for _ in range(4)]
    solver_bfi_lut = [[0] * resolved_solver_lut_size for _ in range(4)]
    solver_output_q16_lut = [[0] * resolved_solver_lut_size for _ in range(4)]

    for ch in range(4):
        for i in range(resolved_solver_lut_size):
            q16 = (int(i) * 65535) // int(resolved_solver_lut_size - 1)
            state = _encode_state_from16(
                q16,
                prepared_entries[ch],
                policy,
                calibration,
                solver_channel=ch,
            )
            solver_value_lut[ch][i] = int(state["value"])
            solver_bfi_lut[ch][i] = int(state["bfi"])
            solver_output_q16_lut[ch][i] = int(state["output_q16"])
        solver_value_lut[ch][0] = 0
        solver_bfi_lut[ch][0] = 0

    solver_resolved_value_lut = [[[0] * resolved_solver_lut_size for _ in range(fixed_levels)] for _ in range(4)]
    solver_resolved_bfi_lut = [[[0] * resolved_solver_lut_size for _ in range(fixed_levels)] for _ in range(4)]

    solver_lower_floor_value_lut = [[[0] * resolved_solver_lut_size for _ in range(fixed_levels)] for _ in range(4)]

    for ch in range(4):
        for fixed_bfi in range(fixed_levels):
            constraints = {
                "min_bfi": int(fixed_bfi),
                "max_bfi": int(fixed_bfi),
                "prefer_higher_bfi": True,
                "target_scale_q16": 65535,
                "max_target_q16": 65535,
            }
            constrained_entries = prepared_entries_by_bfi[ch].get(int(fixed_bfi), None)
            for i in range(resolved_solver_lut_size):
                target_q16 = int(solver_output_q16_lut[ch][i])
                state = _encode_state_from16_constrained(
                    target_q16,
                    prepared_entries[ch],
                    policy,
                    constraints,
                    calibration,
                    solver_channel=ch,
                    constrained_entries=constrained_entries,
                )
                solver_resolved_value_lut[ch][fixed_bfi][i] = int(state["value"])
                solver_resolved_bfi_lut[ch][fixed_bfi][i] = int(state["bfi"])
                solver_lower_floor_value_lut[ch][fixed_bfi][i] = int(state.get("lower_value", state["value"]))

    solver_legal_output_q16_for_value_bfi = [[[0] * 256 for _ in range(fixed_levels)] for _ in range(4)]

    for ch in range(4):
        ladder = runtime_ladders[ch]
        for e in ladder:
            bfi = int(e["bfi"])
            if bfi >= fixed_levels:
                continue
            solver_legal_output_q16_for_value_bfi[ch][bfi][int(e["value"])] = int(e["output_q16"])

    solver_dither_lower_value_lut = [[[0] * resolved_solver_lut_size for _ in range(fixed_levels)] for _ in range(4)]
    solver_dither_upper_value_lut = [[[0] * resolved_solver_lut_size for _ in range(fixed_levels)] for _ in range(4)]
    solver_dither_upper_blend8_lut = [[[0] * resolved_solver_lut_size for _ in range(fixed_levels)] for _ in range(4)]

    for ch in range(4):
        for fixed_bfi in range(fixed_levels):
            solver_legal_output_q16_for_value_bfi[ch][fixed_bfi][0] = 0

            for i in range(resolved_solver_lut_size):
                target_q16 = int(solver_output_q16_lut[ch][i])
                resolved_value = int(solver_resolved_value_lut[ch][fixed_bfi][i])

                lower_value = int(resolved_value)
                upper_value = int(resolved_value)
                lower_q16 = int(solver_legal_output_q16_for_value_bfi[ch][fixed_bfi][resolved_value])
                upper_q16 = int(lower_q16)

                have_lower = (resolved_value == 0) or (lower_q16 != 0)
                have_upper = bool(have_lower)

                for candidate_value in range(256):
                    candidate_q16 = int(solver_legal_output_q16_for_value_bfi[ch][fixed_bfi][candidate_value])
                    if candidate_value != 0 and candidate_q16 == 0:
                        continue

                    if candidate_q16 <= target_q16:
                        if (not have_lower) or (candidate_q16 > lower_q16) or (
                            candidate_q16 == lower_q16 and candidate_value > lower_value
                        ):
                            lower_q16 = int(candidate_q16)
                            lower_value = int(candidate_value)
                            have_lower = True

                    if candidate_q16 >= target_q16:
                        if (not have_upper) or (candidate_q16 < upper_q16) or (
                            candidate_q16 == upper_q16 and candidate_value < upper_value
                        ):
                            upper_q16 = int(candidate_q16)
                            upper_value = int(candidate_value)
                            have_upper = True

                if (not have_lower) and have_upper:
                    lower_q16 = int(upper_q16)
                    lower_value = int(upper_value)
                    have_lower = True

                if (not have_upper) and have_lower:
                    upper_q16 = int(lower_q16)
                    upper_value = int(lower_value)
                    have_upper = True

                if (not have_lower) and (not have_upper):
                    lower_q16 = 0
                    upper_q16 = 0
                    lower_value = int(resolved_value)
                    upper_value = int(resolved_value)

                blend8 = 0
                if upper_value != lower_value and upper_q16 > lower_q16:
                    span_q16 = int(upper_q16 - lower_q16)
                    offset_q16 = int(target_q16 - lower_q16)
                    blend8 = (offset_q16 * 255 + (span_q16 >> 1)) // span_q16
                elif upper_value != lower_value and target_q16 >= upper_q16:
                    blend8 = 255

                solver_dither_lower_value_lut[ch][fixed_bfi][i] = int(lower_value)
                solver_dither_upper_value_lut[ch][fixed_bfi][i] = int(upper_value)
                solver_dither_upper_blend8_lut[ch][fixed_bfi][i] = int(max(0, min(255, blend8)))

    return {
        "solverLUTSize": int(resolved_solver_lut_size),
        "solverBFILUT": solver_bfi_lut,
        "solverValueLUT": solver_value_lut,
        "solverOutputQ16LUT": solver_output_q16_lut,
        "solverResolvedValueForFixedBfiLUT": solver_resolved_value_lut,
        "solverResolvedBfiForFixedBfiLUT": solver_resolved_bfi_lut,
        "solverLowerFloorValueForFixedBfiLUT": solver_lower_floor_value_lut,
        "solverDitherLowerValueForFixedBfiLUT": solver_dither_lower_value_lut,
        "solverDitherUpperValueForFixedBfiLUT": solver_dither_upper_value_lut,
        "solverDitherUpperBlend8ForFixedBfiLUT": solver_dither_upper_blend8_lut,
    }


def _append_cpp_u8_2d(lines, name, table):
    width = len(table[0]) if table else 0
    if width < 1 or any(len(row) != width for row in table):
        raise ValueError(f"{name} must be a rectangular 2D table")
    lines.append(f"static const uint8_t {name}[4][{width}] PROGMEM = {{")
    for ch in range(4):
        lines.append("  {")
        for i in range(0, width, 16):
            chunk = table[ch][i:i+16]
            lines.append("    " + ", ".join(str(int(v)) for v in chunk) + ",")
        lines.append("  },")
    lines.append("};")
    lines.append("")


def _append_cpp_u16_2d(lines, name, table):
    width = len(table[0]) if table else 0
    if width < 1 or any(len(row) != width for row in table):
        raise ValueError(f"{name} must be a rectangular 2D table")
    lines.append(f"static const uint16_t {name}[4][{width}] PROGMEM = {{")
    for ch in range(4):
        lines.append("  {")
        for i in range(0, width, 12):
            chunk = table[ch][i:i+12]
            lines.append("    " + ", ".join(str(int(v)) for v in chunk) + ",")
        lines.append("  },")
    lines.append("};")
    lines.append("")


def _append_cpp_u8_3d(lines, name, table, fixed_levels):
    width = len(table[0][0]) if table and table[0] else 0
    if width < 1:
        raise ValueError(f"{name} must contain at least one LUT entry")
    if any(len(channel_table) != int(fixed_levels) for channel_table in table):
        raise ValueError(f"{name} fixed-level depth mismatch")
    if any(len(level_table) != width for channel_table in table for level_table in channel_table):
        raise ValueError(f"{name} must be a rectangular 3D table")
    lines.append(f"static const uint8_t {name}[4][{int(fixed_levels)}][{width}] PROGMEM = {{")
    for ch in range(4):
        lines.append("  {")
        for bfi in range(int(fixed_levels)):
            lines.append("    {")
            for i in range(0, width, 16):
                chunk = table[ch][bfi][i:i+16]
                lines.append("      " + ", ".join(str(int(v)) for v in chunk) + ",")
            lines.append("    },")
        lines.append("  },")
    lines.append("};")
    lines.append("")


def export_precomputed_solver_luts_header(
    solver_header: Path,
    calibration_header: Path,
    out_path: Path,
    max_bfi: int | None = None,
    solver_fixed_bfi_levels: int | None = None,
    solver_lut_size: int | None = None,
    min_error_q16: int = 64,
    relative_error_divisor: int = 24,
    min_value_ratio_numerator: int = 3,
    min_value_ratio_denominator: int = 8,
    low_end_protect_threshold: int = 48,
    low_end_max_drop: int = 10,
    prefer_higher_bfi: bool = True,
    preferred_min_bfi: int = 0,
    highlight_bypass_start: int = 240,
):
    runtime = _load_runtime_solver_ladders(solver_header)
    solver_header_max_bfi = int(runtime["max_bfi"])

    if max_bfi is None:
        effective_max_bfi = int(solver_header_max_bfi)
    else:
        effective_max_bfi = int(max_bfi)
        if effective_max_bfi > solver_header_max_bfi:
            raise ValueError(f"Requested max_bfi={effective_max_bfi} exceeds solver header MAX_BFI={solver_header_max_bfi}")
        if effective_max_bfi < 0:
            raise ValueError("max_bfi must be >= 0")

    if solver_fixed_bfi_levels is None:
        fixed_levels = int(effective_max_bfi + 1)
    else:
        fixed_levels = int(solver_fixed_bfi_levels)

    if fixed_levels < 1:
        raise ValueError("solver_fixed_bfi_levels must be >= 1")
    if fixed_levels > (solver_header_max_bfi + 1):
        raise ValueError(
            f"solver_fixed_bfi_levels={fixed_levels} exceeds supported range from solver header ({solver_header_max_bfi + 1})"
        )

    calibration = _load_calibration_for_solver_precompute(calibration_header, required_max_bfi=solver_header_max_bfi)
    calibration_mode = str(calibration.get("mode", "legacy_8to16"))

    policy = _default_solver_policy(effective_max_bfi)
    policy["min_error_q16"] = int(min_error_q16)
    policy["relative_error_divisor"] = int(relative_error_divisor)
    policy["min_value_ratio_numerator"] = int(min_value_ratio_numerator)
    policy["min_value_ratio_denominator"] = int(min_value_ratio_denominator)
    policy["low_end_protect_threshold"] = int(low_end_protect_threshold)
    policy["low_end_max_drop"] = int(low_end_max_drop)
    policy["prefer_higher_bfi"] = bool(prefer_higher_bfi)
    policy["preferred_min_bfi"] = int(preferred_min_bfi)
    policy["highlight_bypass_start"] = int(highlight_bypass_start)

    derived_solver_lut_size = _derive_solver_lut_size_from_runtime_ladders(runtime["ladders"])
    if solver_lut_size is None:
        effective_solver_lut_size = int(derived_solver_lut_size)
    else:
        effective_solver_lut_size = int(solver_lut_size)
        if effective_solver_lut_size < int(derived_solver_lut_size):
            raise ValueError(
                f"solver_lut_size={effective_solver_lut_size} is smaller than derived ladder count {derived_solver_lut_size}"
            )

    tables = _build_solver_precomputed_tables(
        runtime_ladders=runtime["ladders"],
        calibration=calibration,
        policy=policy,
        solver_fixed_bfi_levels=fixed_levels,
        solver_lut_size=effective_solver_lut_size,
    )

    lines = [
        "// Auto-generated precomputed solver LUT header (v14)",
        "// Channel index order matches solver runtime: 0=G, 1=R, 2=B, 3=W",
        f"// Calibration mode: {calibration_mode}",
        "#pragma once",
        "#include <Arduino.h>",
        "#define TEMPORAL_BFI_PRECOMPUTED_HAS_LUT_SIZE 1",
        "#define TEMPORAL_BFI_PRECOMPUTED_HAS_FLOOR_LUT 1",
        "",
        "namespace TemporalBFIPrecomputedSolverLUTs {",
        f"static constexpr uint8_t MAX_BFI = {effective_max_bfi};",
        f"static constexpr uint8_t SOLVER_FIXED_BFI_LEVELS = {fixed_levels};",
        f"static constexpr uint32_t SOLVER_LUT_SIZE = {int(tables['solverLUTSize'])};",
        "",
    ]

    _append_cpp_u8_2d(lines, "solverBFILUT", tables["solverBFILUT"])
    _append_cpp_u8_2d(lines, "solverValueLUT", tables["solverValueLUT"])
    _append_cpp_u16_2d(lines, "solverOutputQ16LUT", tables["solverOutputQ16LUT"])
    _append_cpp_u8_3d(
        lines,
        "solverResolvedValueForFixedBfiLUT",
        tables["solverResolvedValueForFixedBfiLUT"],
        fixed_levels,
    )
    _append_cpp_u8_3d(
        lines,
        "solverResolvedBfiForFixedBfiLUT",
        tables["solverResolvedBfiForFixedBfiLUT"],
        fixed_levels,
    )
    _append_cpp_u8_3d(
        lines,
        "solverLowerFloorValueForFixedBfiLUT",
        tables["solverLowerFloorValueForFixedBfiLUT"],
        fixed_levels,
    )
    _append_cpp_u8_3d(
        lines,
        "solverDitherLowerValueForFixedBfiLUT",
        tables["solverDitherLowerValueForFixedBfiLUT"],
        fixed_levels,
    )
    _append_cpp_u8_3d(
        lines,
        "solverDitherUpperValueForFixedBfiLUT",
        tables["solverDitherUpperValueForFixedBfiLUT"],
        fixed_levels,
    )
    _append_cpp_u8_3d(
        lines,
        "solverDitherUpperBlend8ForFixedBfiLUT",
        tables["solverDitherUpperBlend8ForFixedBfiLUT"],
        fixed_levels,
    )

    lines.append("} // namespace TemporalBFIPrecomputedSolverLUTs")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "out": str(out_path),
        "solver_header": str(solver_header),
        "calibration_header": str(calibration_header),
        "max_bfi": int(effective_max_bfi),
        "solver_fixed_bfi_levels": int(fixed_levels),
        "solver_lut_size": int(tables["solverLUTSize"]),
        "derived_solver_lut_size": int(derived_solver_lut_size),
        "policy": policy,
        "calibration_mode": calibration_mode,
    }

def _active_channels(r, g, b, w):
    vals = {"R": r, "G": g, "B": b, "W": w}
    return [ch for ch in CHANNELS if vals[ch] > 0]


def _build_secondary_ramp_mixed_codes():
    ramp = [8, 16, 24, 32, 48, 64, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 240, 255]
    mixes = []
    for v in ramp:
        half = max(1, int(round(v * 0.50)))
        quarter = max(1, int(round(v * 0.25)))
        warm_g = max(1, int(round(v * 0.85)))
        warm_b = max(1, int(round(v * 0.65)))
        w_bias = int(round(v * 0.16))
        mixes += [
            (v, half, 0, 0),
            (v, quarter, quarter, 0),
            (half, v, quarter, 0),
            (quarter, half, v, 0),
            (quarter, v, v, 0),
            (v, warm_g, warm_b, w_bias),
        ]

    # Preserve ordering while dropping accidental duplicates.
    unique = []
    seen = set()
    for mix in mixes:
        if mix in seen:
            continue
        seen.add(mix)
        unique.append(mix)
    return unique


GENERIC_PLAN_FIELDS = [
    "name",
    "mode",
    "repeats",
    "r",
    "g",
    "b",
    "w",
    "r16",
    "g16",
    "b16",
    "w16",
    "bfi_r",
    "bfi_g",
    "bfi_b",
    "bfi_w",
    "lower_r16",
    "lower_g16",
    "lower_b16",
    "lower_w16",
    "upper_r16",
    "upper_g16",
    "upper_b16",
    "upper_w16",
    "high_count_r",
    "high_count_g",
    "high_count_b",
    "high_count_w",
    "cycle_length",
    "use_fill16",
]


TEMPORAL_BLEND_PAIR_ANCHORS = {
    "quick": [0, 16, 32, 48, 64, 96, 128, 160, 192, 224, 255],
    "medium": [0, 8, 16, 24, 32, 48, 64, 80, 96, 112, 128, 160, 192, 224, 255],
    "fine": dense_code_set(),
    "ultra": list(range(256)),
}

TEMPORAL_BLEND_MIX_TEMPLATES = [
    ("neutral_rgb", (1.0, 1.0, 1.0, 0.0)),
    ("neutral_rgbw025", (1.0, 1.0, 1.0, 0.25)),
    ("neutral_rgbw050", (1.0, 1.0, 1.0, 0.50)),
    ("warm_rgbw015", (1.0, 0.85, 0.65, 0.15)),
    ("amber_rgbw020", (1.0, 0.78, 0.20, 0.20)),
    ("gold_rgbw010", (1.0, 0.92, 0.25, 0.10)),
    ("skin_light_rgbw012", (1.0, 0.76, 0.60, 0.12)),
    ("skin_deep_rgbw008", (0.72, 0.46, 0.34, 0.08)),
    ("brown_tan_rgbw010", (0.68, 0.50, 0.28, 0.10)),
    ("cool_rgbw015", (0.70, 0.82, 1.0, 0.15)),
    ("cyan_rgbw010", (0.25, 0.88, 1.0, 0.10)),
    ("magenta_rgbw010", (0.92, 0.30, 1.0, 0.10)),
    ("highsat_red", (1.0, 0.10, 0.10, 0.0)),
    ("highsat_green", (0.10, 1.0, 0.18, 0.0)),
    ("highsat_blue", (0.16, 0.24, 1.0, 0.0)),
    ("highsat_yellow", (1.0, 0.92, 0.10, 0.0)),
]


def _clamp_q16(value):
    return max(0, min(65535, int(value)))


def _u8_to_q16(value_u8):
    value_u8 = max(0, min(255, int(value_u8)))
    return int(value_u8 * 257)


def _blend_template_values(level_u8, scales):
    return tuple(_u8_to_q16(round(level_u8 * scale)) for scale in scales)


def _append_generic_fill16_row(rows, name, values, repeats, cycle_length=5):
    rows.append(
        {
            "name": name,
            "mode": "fill16",
            "repeats": int(repeats),
            "r": int((values[0] * 255 + 32767) // 65535),
            "g": int((values[1] * 255 + 32767) // 65535),
            "b": int((values[2] * 255 + 32767) // 65535),
            "w": int((values[3] * 255 + 32767) // 65535),
            "r16": int(values[0]),
            "g16": int(values[1]),
            "b16": int(values[2]),
            "w16": int(values[3]),
            "bfi_r": 0,
            "bfi_g": 0,
            "bfi_b": 0,
            "bfi_w": 0,
            "cycle_length": int(cycle_length),
            "use_fill16": 1,
        }
    )


def _append_generic_blend_row(rows, name, lower_values, upper_values, high_counts, cycle_length, repeats):
    rows.append(
        {
            "name": name,
            "mode": "blend16",
            "repeats": int(repeats),
            "r": int((upper_values[0] * 255 + 32767) // 65535),
            "g": int((upper_values[1] * 255 + 32767) // 65535),
            "b": int((upper_values[2] * 255 + 32767) // 65535),
            "w": int((upper_values[3] * 255 + 32767) // 65535),
            "r16": int(upper_values[0]),
            "g16": int(upper_values[1]),
            "b16": int(upper_values[2]),
            "w16": int(upper_values[3]),
            "bfi_r": 0,
            "bfi_g": 0,
            "bfi_b": 0,
            "bfi_w": 0,
            "lower_r16": int(lower_values[0]),
            "lower_g16": int(lower_values[1]),
            "lower_b16": int(lower_values[2]),
            "lower_w16": int(lower_values[3]),
            "upper_r16": int(upper_values[0]),
            "upper_g16": int(upper_values[1]),
            "upper_b16": int(upper_values[2]),
            "upper_w16": int(upper_values[3]),
            "high_count_r": int(high_counts[0]),
            "high_count_g": int(high_counts[1]),
            "high_count_b": int(high_counts[2]),
            "high_count_w": int(high_counts[3]),
            "cycle_length": int(cycle_length),
            "use_fill16": 1,
        }
    )

def write_patch_plan(
    out_csv: Path,
    preset: str,
    max_bfi: int = 4,
    include_grays: bool = True,
    include_mixed: bool = True,
    include_secondary_ramp: bool = False,
    repeats_override=None,
):
    cfg = PATCH_PRESETS[preset]
    repeats = int(cfg["repeats"])
    if repeats_override is not None:
        repeats = max(1, int(repeats_override))

    secondary_mixed = _build_secondary_ramp_mixed_codes() if include_secondary_ramp else []
    rows = []
    for bfi in range(max_bfi + 1):
        rows.append({
            "name": f"BLACK_bfi{bfi}",
            "r": 0,
            "g": 0,
            "b": 0,
            "w": 0,
            "bfi_r": 0,
            "bfi_g": 0,
            "bfi_b": 0,
            "bfi_w": 0,
            "repeats": repeats,
        })
        for v in cfg["primaries"]:
            rows += [
                {"name": f"R_bfi{bfi}_{v}", "r": v, "g": 0, "b": 0, "w": 0, "bfi_r": bfi, "bfi_g": 0, "bfi_b": 0, "bfi_w": 0, "repeats": repeats},
                {"name": f"G_bfi{bfi}_{v}", "r": 0, "g": v, "b": 0, "w": 0, "bfi_r": 0, "bfi_g": bfi, "bfi_b": 0, "bfi_w": 0, "repeats": repeats},
                {"name": f"B_bfi{bfi}_{v}", "r": 0, "g": 0, "b": v, "w": 0, "bfi_r": 0, "bfi_g": 0, "bfi_b": bfi, "bfi_w": 0, "repeats": repeats},
                {"name": f"W_bfi{bfi}_{v}", "r": 0, "g": 0, "b": 0, "w": v, "bfi_r": 0, "bfi_g": 0, "bfi_b": 0, "bfi_w": bfi, "repeats": repeats},
            ]
        if include_grays:
            for v in cfg["grays"]:
                rows += [
                    {"name": f"GRAY_RGB_bfi{bfi}_{v}", "r": v, "g": v, "b": v, "w": 0, "bfi_r": bfi, "bfi_g": bfi, "bfi_b": bfi, "bfi_w": 0, "repeats": repeats},
                    {"name": f"GRAY_RGBW_bfi{bfi}_{v}", "r": v, "g": v, "b": v, "w": v, "bfi_r": bfi, "bfi_g": bfi, "bfi_b": bfi, "bfi_w": bfi, "repeats": repeats},
                ]
        if include_mixed:
            for idx, (r,g,b,w) in enumerate(cfg["mixed"]):
                act = _active_channels(r, g, b, w)
                rows.append({
                    "name": f"MIX_bfi{bfi}_{idx}",
                    "r": r, "g": g, "b": b, "w": w,
                    "bfi_r": bfi if "R" in act else 0,
                    "bfi_g": bfi if "G" in act else 0,
                    "bfi_b": bfi if "B" in act else 0,
                    "bfi_w": bfi if "W" in act else 0,
                    "repeats": repeats
                })
            for idx, (r,g,b,w) in enumerate(secondary_mixed):
                act = _active_channels(r, g, b, w)
                rows.append({
                    "name": f"SEC_MIX_bfi{bfi}_{idx}",
                    "r": r, "g": g, "b": b, "w": w,
                    "bfi_r": bfi if "R" in act else 0,
                    "bfi_g": bfi if "G" in act else 0,
                    "bfi_b": bfi if "B" in act else 0,
                    "bfi_w": bfi if "W" in act else 0,
                    "repeats": repeats,
                })
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["name","r","g","b","w","bfi_r","bfi_g","bfi_b","bfi_w","repeats"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return rows

def write_patch_plan_true16(
    out_csv: Path,
    density: str = "medium",
    include_gray_ramp: bool = True,
    include_primary_ramps: bool = True,
    include_mid_colors: bool = True,
    include_white_protection_mixes: bool = True,
    repeats_override=None,
):
    """
    Generate a True16 (Q16 / 16-bit) patch plan for solver-driven calibration.
    No BFI variation—the solver decides BFI at runtime from a single 16-bit input.

    Density options:
      - "quick":    ~200 samples total (large stepping)
      - "medium":   ~500 samples total (balanced)
      - "fine":     ~1000 samples total (dense)
      - "ultra":    ~2000 samples total (very dense)
    """
    density = str(density).lower()
    repeats = 1 if repeats_override is None else max(1, int(repeats_override))
    samples_per_section = {
        "quick": 50,
        "medium": 120,
        "fine": 250,
        "ultra": 500,
    }.get(density, 120)
    protection_sample_count = {
        "quick": 4,
        "medium": 6,
        "fine": 8,
        "ultra": 10,
    }.get(density, 6)

    rows = []
    row_idx = 0

    def append_row(name, r16, g16, b16, w16):
        nonlocal row_idx
        row_idx += 1
        rows.append({
            "name": str(name),
            "r16": int(r16),
            "g16": int(g16),
            "b16": int(b16),
            "w16": int(w16),
            "repeats": int(repeats),
        })

    def sweep_q16(start_q16, end_q16, count):
        points = []
        for i in range(count):
            alpha = i / max(1, count - 1) if count > 1 else 0
            q16 = int(start_q16 + (end_q16 - start_q16) * alpha)
            points.append(q16)
        return points

    if include_gray_ramp:
        gray_samples = sweep_q16(0, 65535, samples_per_section)
        for q16 in gray_samples:
            append_row(f"gray_q16_{q16:05d}", q16, q16, q16, 0)

    if include_primary_ramps:
        for ch_name in ["R", "G", "B", "W"]:
            samples = sweep_q16(0, 65535, samples_per_section // 2)
            for q16 in samples:
                append_row(
                    f"{ch_name}_q16_{q16:05d}",
                    q16 if ch_name == "R" else 0,
                    q16 if ch_name == "G" else 0,
                    q16 if ch_name == "B" else 0,
                    q16 if ch_name == "W" else 0,
                )

    if include_mid_colors:
        mid_points = [int(65535 * p) for p in [0.25, 0.5, 0.75]]
        for r_frac in [0.3, 0.6, 1.0]:
            for g_frac in [0.3, 0.6, 1.0]:
                for b_frac in [0.3, 0.6, 1.0]:
                    if r_frac == g_frac == b_frac:
                        continue
                    for mid in mid_points:
                        append_row(
                            f"color_r{r_frac:.1f}_g{g_frac:.1f}_b{b_frac:.1f}_{mid:05d}",
                            int(mid * r_frac),
                            int(mid * g_frac),
                            int(mid * b_frac),
                            0,
                        )

    if include_white_protection_mixes:
        protection_levels = sweep_q16(int(65535 * 0.08), 65535, protection_sample_count)
        for q16 in protection_levels:
            append_row(
                f"neutral_rgbw025_{q16:05d}",
                q16,
                q16,
                q16,
                int(round(q16 * 0.25)),
            )
            append_row(
                f"neutral_rgbw050_{q16:05d}",
                q16,
                q16,
                q16,
                int(round(q16 * 0.50)),
            )
            append_row(
                f"warm_rgbw015_{q16:05d}",
                q16,
                int(round(q16 * 0.85)),
                int(round(q16 * 0.65)),
                int(round(q16 * 0.15)),
            )
            append_row(
                f"amber_rgbw020_{q16:05d}",
                q16,
                int(round(q16 * 0.78)),
                int(round(q16 * 0.20)),
                int(round(q16 * 0.20)),
            )
            append_row(
                f"cool_rgbw015_{q16:05d}",
                int(round(q16 * 0.70)),
                int(round(q16 * 0.82)),
                q16,
                int(round(q16 * 0.15)),
            )

    has_named_black = any(str(row.get("name", "")).upper().startswith("BLACK") for row in rows)
    if not has_named_black:
        append_row("BLACK_q16_00000", 0, 0, 0, 0)

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "r16", "g16", "b16", "w16", "repeats"])
        w.writeheader()
        w.writerows(rows)
    return rows


def write_patch_plan_temporal_blend(
    out_csv: Path,
    density: str = "medium",
    cycle_length: int = 5,
    include_gray_ramp: bool = True,
    include_primary_pairs: bool = True,
    include_mixed_pairs: bool = True,
    repeats_override=None,
):
    density = str(density).lower()
    pair_anchors = TEMPORAL_BLEND_PAIR_ANCHORS.get(density, TEMPORAL_BLEND_PAIR_ANCHORS["medium"])
    raw_values = list(range(256))
    cycle_length = max(2, int(cycle_length))
    repeats = 1 if repeats_override is None else max(1, int(repeats_override))
    rows = []

    _append_generic_fill16_row(rows, "BLACK_v000", (0, 0, 0, 0), repeats, cycle_length=cycle_length)

    if include_primary_pairs:
        for ch_idx, ch_name in enumerate(["R", "G", "B", "W"]):
            for raw_value in raw_values:
                values = [0, 0, 0, 0]
                values[ch_idx] = _u8_to_q16(raw_value)
                _append_generic_fill16_row(rows, f"{ch_name}_v{raw_value:03d}", tuple(values), repeats, cycle_length=cycle_length)
            for lo_idx, low in enumerate(pair_anchors[:-1]):
                for high in pair_anchors[lo_idx + 1 :]:
                    for high_count in range(1, cycle_length):
                        lower = [0, 0, 0, 0]
                        upper = [0, 0, 0, 0]
                        counts = [0, 0, 0, 0]
                        lower[ch_idx] = _u8_to_q16(low)
                        upper[ch_idx] = _u8_to_q16(high)
                        counts[ch_idx] = high_count
                        _append_generic_blend_row(
                            rows,
                            f"{ch_name}_blend_lo{low:03d}_hi{high:03d}_h{high_count}of{cycle_length}",
                            tuple(lower),
                            tuple(upper),
                            tuple(counts),
                            cycle_length,
                            repeats,
                        )

    if include_gray_ramp:
        for raw_value in raw_values:
            q16_value = _u8_to_q16(raw_value)
            _append_generic_fill16_row(rows, f"gray_v{raw_value:03d}", (q16_value, q16_value, q16_value, 0), repeats, cycle_length=cycle_length)
        for lo_idx, low in enumerate(pair_anchors[:-1]):
            for high in pair_anchors[lo_idx + 1 :]:
                for high_count in range(1, cycle_length):
                    low_q16 = _u8_to_q16(low)
                    high_q16 = _u8_to_q16(high)
                    _append_generic_blend_row(
                        rows,
                        f"gray_blend_lo{low:03d}_hi{high:03d}_h{high_count}of{cycle_length}",
                        (low_q16, low_q16, low_q16, 0),
                        (high_q16, high_q16, high_q16, 0),
                        (high_count, high_count, high_count, 0),
                        cycle_length,
                        repeats,
                    )

    if include_mixed_pairs:
        for template_name, scales in TEMPORAL_BLEND_MIX_TEMPLATES:
            for raw_value in pair_anchors:
                _append_generic_fill16_row(rows, f"{template_name}_v{raw_value:03d}", _blend_template_values(raw_value, scales), repeats, cycle_length=cycle_length)
            for lo_idx, low in enumerate(pair_anchors[:-1]):
                for high in pair_anchors[lo_idx + 1 :]:
                    lower = _blend_template_values(low, scales)
                    upper = _blend_template_values(high, scales)
                    active_counts = tuple(c if upper[idx] > lower[idx] else 0 for idx, c in enumerate([1, 1, 1, 1]))
                    for high_count in range(1, cycle_length):
                        counts = tuple(high_count if active_counts[idx] else 0 for idx in range(4))
                        _append_generic_blend_row(
                            rows,
                            f"{template_name}_blend_lo{low:03d}_hi{high:03d}_h{high_count}of{cycle_length}",
                            lower,
                            upper,
                            counts,
                            cycle_length,
                            repeats,
                        )

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=GENERIC_PLAN_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows

def load_patch_measurements(measure_dir: Path):
    rows = []
    for p in sorted(measure_dir.glob("plan_capture_*.csv")):
        try:
            with open(p, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if str(row.get("ok", "")).strip() != "True":
                        continue
                    if row.get("Y") in (None, ""):
                        continue
                    rows.append({
                        "file": p.name,
                        "name": row.get("name", ""),
                        "mode": _normalize_raw_capture_mode(row, default_mode="fill8"),
                        "r": int(row.get("r", 0)),
                        "g": int(row.get("g", 0)),
                        "b": int(row.get("b", 0)),
                        "w": int(row.get("w", 0)),
                        "lower_r": int(row.get("lower_r", 0) or 0),
                        "lower_g": int(row.get("lower_g", 0) or 0),
                        "lower_b": int(row.get("lower_b", 0) or 0),
                        "lower_w": int(row.get("lower_w", 0) or 0),
                        "upper_r": int(row.get("upper_r", row.get("r", 0)) or 0),
                        "upper_g": int(row.get("upper_g", row.get("g", 0)) or 0),
                        "upper_b": int(row.get("upper_b", row.get("b", 0)) or 0),
                        "upper_w": int(row.get("upper_w", row.get("w", 0)) or 0),
                        "bfi_r": int(row.get("bfi_r", 0)),
                        "bfi_g": int(row.get("bfi_g", 0)),
                        "bfi_b": int(row.get("bfi_b", 0)),
                        "bfi_w": int(row.get("bfi_w", 0)),
                        "Y": float(row["Y"]),
                        "x": float(row["x"]) if row.get("x") not in (None, "") else None,
                        "y": float(row["y"]) if row.get("y") not in (None, "") else None,
                    })
        except Exception:
            continue
    return rows

def load_patch_measurements_true16(measure_dir: Path, input_globs=None):
    """Load measurements from True16 plan captures with tolerant schema handling."""
    patterns = list(input_globs or TRUE16_DEFAULT_INPUT_GLOBS)
    paths = []
    for pattern in patterns:
        paths.extend(sorted(measure_dir.glob(pattern)))
    paths = _dedupe_paths(paths)

    stats = {
        "source_patterns": patterns,
        "files_matched": [p.name for p in paths],
        "files_scanned": len(paths),
        "rows_seen": 0,
        "rows_loaded": 0,
        "rows_skipped_not_ok": 0,
        "rows_skipped_missing_y": 0,
        "rows_skipped_missing_q16": 0,
        "rows_skipped_fill16_false": 0,
        "rows_skipped_parse_error": 0,
    }
    rows = []

    for p in paths:
        try:
            with open(p, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fieldnames = set(reader.fieldnames or [])
                has_use_fill16 = "use_fill16" in fieldnames
                for row in reader:
                    stats["rows_seen"] += 1
                    if not _parse_bool(row.get("ok", None), default=False):
                        stats["rows_skipped_not_ok"] += 1
                        continue
                    if row.get("Y") in (None, ""):
                        stats["rows_skipped_missing_y"] += 1
                        continue
                    if not all(k in row for k in ("r16", "g16", "b16", "w16")):
                        stats["rows_skipped_missing_q16"] += 1
                        continue

                    default_fill16 = "true16" in p.stem.lower()
                    use_fill16 = _parse_bool(row.get("use_fill16"), default=default_fill16)
                    if has_use_fill16 and not use_fill16:
                        stats["rows_skipped_fill16_false"] += 1
                        continue

                    try:
                        mode = str(row.get("mode", "fill16")).strip().lower()
                        rows.append({
                            "file": p.name,
                            "name": row.get("name", ""),
                            "mode": mode if mode in {"fill16", "blend16"} else ("blend16" if any(str(row.get(k, "")).strip() for k in ("lower_r16", "lower_g16", "lower_b16", "lower_w16", "upper_r16", "upper_g16", "upper_b16", "upper_w16")) else "fill16"),
                            "use_fill16": bool(use_fill16),
                            "repeat_index": int(row.get("repeat_index", 0)) if row.get("repeat_index") not in (None, "") else 0,
                            "solver_mode": int(row.get("solver_mode", 0)) if row.get("solver_mode") not in (None, "") else 0,
                            "r16": int(row.get("r16", 0)),
                            "g16": int(row.get("g16", 0)),
                            "b16": int(row.get("b16", 0)),
                            "w16": int(row.get("w16", 0)),
                            "lower_r16": int(row.get("lower_r16", 0) or 0),
                            "lower_g16": int(row.get("lower_g16", 0) or 0),
                            "lower_b16": int(row.get("lower_b16", 0) or 0),
                            "lower_w16": int(row.get("lower_w16", 0) or 0),
                            "upper_r16": int(row.get("upper_r16", row.get("r16", 0)) or 0),
                            "upper_g16": int(row.get("upper_g16", row.get("g16", 0)) or 0),
                            "upper_b16": int(row.get("upper_b16", row.get("b16", 0)) or 0),
                            "upper_w16": int(row.get("upper_w16", row.get("w16", 0)) or 0),
                            "blend_r_count": int(row.get("blend_r_count", 0) or 0),
                            "blend_g_count": int(row.get("blend_g_count", 0) or 0),
                            "blend_b_count": int(row.get("blend_b_count", 0) or 0),
                            "blend_w_count": int(row.get("blend_w_count", 0) or 0),
                            "cycle_length": int(row.get("cycle_length", 0) or 0),
                            "Y": float(row["Y"]),
                            "X": float(row["X"]) if row.get("X") not in (None, "") else None,
                            "x": float(row["x"]) if row.get("x") not in (None, "") else None,
                            "y": float(row["y"]) if row.get("y") not in (None, "") else None,
                        })
                        stats["rows_loaded"] += 1
                    except Exception:
                        stats["rows_skipped_parse_error"] += 1
        except Exception:
            continue

    return rows, stats

def _interp_from_zero(known_norm):
    lut = [0] * 256
    if not known_norm:
        return [round(i * 257) for i in range(256)]
    known = sorted((int(v), float(y)) for v, y in known_norm.items())
    lut[0] = 0
    first_x, first_y = known[0]
    if first_x == 0:
        lut[0] = round(first_y * 65535.0)
    else:
        for x in range(1, first_x + 1):
            t = x / first_x
            lut[x] = round((first_y * t) * 65535.0)
    for i in range(len(known) - 1):
        x0, y0 = known[i]
        x1, y1 = known[i + 1]
        lut[x0] = round(y0 * 65535.0)
        if x1 > x0:
            for x in range(x0 + 1, x1):
                t = (x - x0) / (x1 - x0)
                lut[x] = round((y0 * (1 - t) + y1 * t) * 65535.0)
    last_x, last_y = known[-1]
    for x in range(last_x, 256):
        lut[x] = round(last_y * 65535.0)
    lut[0] = 0
    return lut


def _clamp_u16(value):
    return max(0, min(65535, int(value)))


def _quantile(values, q):
    if not values:
        return None
    v = sorted(float(x) for x in values)
    if len(v) == 1:
        return v[0]
    q = max(0.0, min(1.0, float(q)))
    pos = (len(v) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return v[lo]
    t = pos - lo
    return v[lo] * (1.0 - t) + v[hi] * t


def _to_float_or_none(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _describe_black_samples(samples):
    if not samples:
        return {
            "sample_count": 0,
            "p10_y": None,
            "median_y": None,
            "p90_y": None,
        }
    return {
        "sample_count": int(len(samples)),
        "p10_y": float(_quantile(samples, 0.10)),
        "median_y": float(_quantile(samples, 0.50)),
        "p90_y": float(_quantile(samples, 0.90)),
    }


def _estimate_black_level_8bit(measurements, low_code_max=8):
    explicit_black = []
    low_signal = []

    low_code_max = max(0, int(low_code_max))
    for row in measurements:
        y = float(row.get("Y", 0.0))
        r = int(row.get("r", 0))
        g = int(row.get("g", 0))
        b = int(row.get("b", 0))
        w = int(row.get("w", 0))
        if r == 0 and g == 0 and b == 0 and w == 0:
            explicit_black.append(y)
            continue

        active = [v for v in (r, g, b, w) if v > 0]
        if len(active) == 1 and active[0] <= low_code_max:
            low_signal.append(y)

    if explicit_black:
        level = _quantile(explicit_black, 0.50)
        stats = {
            "source": "explicit-black-rows",
            "low_code_max": int(low_code_max),
            **_describe_black_samples(explicit_black),
            "fallback_sample_count": int(len(low_signal)),
        }
        return max(0.0, float(level or 0.0)), stats

    if low_signal:
        level = _quantile(low_signal, 0.10)
        stats = {
            "source": "low-signal-p10",
            "low_code_max": int(low_code_max),
            **_describe_black_samples(low_signal),
            "fallback_sample_count": 0,
        }
        return max(0.0, float(level or 0.0)), stats

    return 0.0, {
        "source": "none",
        "low_code_max": int(low_code_max),
        "sample_count": 0,
        "p10_y": None,
        "median_y": None,
        "p90_y": None,
        "fallback_sample_count": 0,
    }


def _estimate_black_level_true16(measurements, low_q16_max=2048):
    ambient = _estimate_true16_ambient_profile(measurements, low_q16_max=low_q16_max)
    global_floor = float(ambient.get("global", {}).get("Y", 0.0) or 0.0)
    stats = dict(ambient.get("stats", {}))
    return max(0.0, global_floor), stats


def _xyz_quantile(samples, q=0.5):
    if not samples:
        return None
    xs = [float(v[0]) for v in samples]
    ys = [float(v[1]) for v in samples]
    zs = [float(v[2]) for v in samples]
    return (
        float(_quantile(xs, q) or 0.0),
        float(_quantile(ys, q) or 0.0),
        float(_quantile(zs, q) or 0.0),
    )


def _channel_hint_from_black_name(name):
    text = str(name or "").strip().upper()
    match = re.match(r"^([RGBW])(?:_|\b)", text)
    if match is None:
        return None
    ch = match.group(1)
    return ch if ch in CHANNELS else None


def _measurement_row_xyz_raw(row):
    X = _to_float_or_none(row.get("X"))
    Y = _to_float_or_none(row.get("Y"))
    Z = _to_float_or_none(row.get("Z"))
    if X is not None and Y is not None and Z is not None:
        return (max(0.0, float(X)), max(0.0, float(Y)), max(0.0, float(Z)))

    x = _to_float_or_none(row.get("x"))
    y = _to_float_or_none(row.get("y"))
    Y = 0.0 if Y is None else float(Y)
    return _xyy_to_xyz(x, y, Y)


def _estimate_true16_ambient_profile(measurements, low_q16_max=2048):
    explicit_black_y = []
    explicit_black_xyz = []
    per_channel_black_y = {ch: [] for ch in CHANNELS}
    per_channel_black_xyz = {ch: [] for ch in CHANNELS}
    low_signal = []

    low_q16_max = max(0, int(low_q16_max))
    for row in measurements:
        y = max(0.0, float(row.get("Y", 0.0)))
        xyz = _measurement_row_xyz_raw(row)
        r = int(row.get("r16", 0))
        g = int(row.get("g16", 0))
        b = int(row.get("b16", 0))
        w = int(row.get("w16", 0))

        if r == 0 and g == 0 and b == 0 and w == 0:
            explicit_black_y.append(y)
            if xyz is not None:
                explicit_black_xyz.append(xyz)
            ch_hint = _channel_hint_from_black_name(row.get("name", ""))
            if ch_hint is not None:
                per_channel_black_y[ch_hint].append(y)
                if xyz is not None:
                    per_channel_black_xyz[ch_hint].append(xyz)
            continue

        active = [v for v in (r, g, b, w) if v > 0]
        if len(active) == 1 and active[0] <= low_q16_max:
            low_signal.append(y)

    if explicit_black_y:
        global_y = max(0.0, float(_quantile(explicit_black_y, 0.50) or 0.0))
        global_xyz_tuple = _xyz_quantile(explicit_black_xyz, q=0.50)
        global_xyz = [float(v) for v in global_xyz_tuple] if global_xyz_tuple is not None else None
        stats = {
            "source": "explicit-black-rows",
            "low_q16_max": int(low_q16_max),
            **_describe_black_samples(explicit_black_y),
            "fallback_sample_count": int(len(low_signal)),
        }
    elif low_signal:
        global_y = max(0.0, float(_quantile(low_signal, 0.10) or 0.0))
        global_xyz = None
        stats = {
            "source": "low-signal-p10",
            "low_q16_max": int(low_q16_max),
            **_describe_black_samples(low_signal),
            "fallback_sample_count": 0,
        }
    else:
        global_y = 0.0
        global_xyz = None
        stats = {
            "source": "none",
            "low_q16_max": int(low_q16_max),
            "sample_count": 0,
            "p10_y": None,
            "median_y": None,
            "p90_y": None,
            "fallback_sample_count": 0,
        }

    per_channel = {}
    for ch in CHANNELS:
        y_samples = per_channel_black_y[ch]
        xyz_samples = per_channel_black_xyz[ch]
        ch_y = max(0.0, float(_quantile(y_samples, 0.50) or global_y)) if y_samples else float(global_y)

        if xyz_samples:
            xyz_tuple = _xyz_quantile(xyz_samples, q=0.50)
            ch_xyz = [float(v) for v in xyz_tuple] if xyz_tuple is not None else None
            source = "explicit-black-channel"
        elif global_xyz is not None:
            ch_xyz = [float(v) for v in global_xyz]
            source = "global"
        else:
            ch_xyz = None
            source = "y-only"

        per_channel[ch] = {
            "Y": float(ch_y),
            "xyz": ch_xyz,
            "source": source,
            "sample_count": int(len(y_samples)),
        }

    return {
        "enabled": True,
        "global": {
            "Y": float(global_y),
            "xyz": [float(v) for v in global_xyz] if global_xyz is not None else None,
            "sample_count": int(len(explicit_black_y)),
        },
        "per_channel": per_channel,
        "stats": stats,
    }


def _build_target_q16_table(entry_count, target="linear", gamma=2.2):
    entry_count = max(2, int(entry_count))
    target = str(target or "linear").strip().lower()
    gamma = max(0.05, float(gamma))
    out = [0] * entry_count
    span = float(entry_count - 1)
    for i in range(entry_count):
        x = float(i) / span
        if target == "gamma":
            y = x ** gamma
        else:
            y = x
        out[i] = _clamp_u16(round(_clamp01(y) * 65535.0))
    out[0] = 0
    return out


def _blend_true16_tables(table_a, table_b, blend):
    if not table_a or not table_b:
        return list(table_a or table_b or [0])
    n = min(len(table_a), len(table_b))
    blend = max(0.0, min(1.0, float(blend)))
    out = [0] * n
    last = 0
    for i in range(n):
        q = int(round((1.0 - blend) * float(table_a[i]) + blend * float(table_b[i])))
        q = _clamp_u16(q)
        if q < last:
            q = last
        out[i] = q
        last = q
    out[0] = 0
    out[-1] = 65535
    return out


def _build_density_preserving_target_lut(measured_response_lut, gamma=1.85, gamma_blend=0.24, linear_floor_blend=0.08):
    if not measured_response_lut:
        return [0]
    n = max(2, int(len(measured_response_lut)))
    measured = [_clamp_u16(int(v)) for v in measured_response_lut[:n]]
    measured[0] = 0
    measured[-1] = 65535
    gamma_target = _build_target_q16_table(n, target="gamma", gamma=gamma)
    blended = _blend_true16_tables(measured, gamma_target, gamma_blend)
    if linear_floor_blend > 0.0:
        linear_target = _build_target_q16_table(n, target="linear", gamma=1.0)
        blended = _blend_true16_tables(blended, linear_target, linear_floor_blend)
    blended[0] = 0
    blended[-1] = 65535
    return blended


def _parse_bool(value, default=False):
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off", ""):
        return False
    return bool(default)


def _dedupe_paths(paths):
    out = []
    seen = set()
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _trim_sorted_values(values, trim_fraction):
    trim_fraction = max(0.0, min(0.45, float(trim_fraction)))
    if len(values) < 3 or trim_fraction <= 0.0:
        return list(values), 0
    trim_count = int(math.floor(len(values) * trim_fraction))
    if trim_count <= 0 or (len(values) - (trim_count * 2)) < 1:
        return list(values), 0
    return list(values[trim_count:len(values) - trim_count]), trim_count * 2


def _robust_aggregate(values, method="median", trim_fraction=0.1, outlier_sigma=3.5):
    data = sorted(float(v) for v in values if v is not None)
    if not data:
        return None, {"sample_count": 0, "used_sample_count": 0, "outliers_dropped": 0, "trimmed_dropped": 0}

    filtered = list(data)
    outliers_dropped = 0
    if float(outlier_sigma) > 0.0 and len(filtered) >= 4:
        center = _quantile(filtered, 0.5)
        abs_dev = [abs(v - center) for v in filtered]
        mad = _quantile(abs_dev, 0.5)
        if mad is not None and mad > 1e-12:
            robust_sigma = 1.4826 * mad
            threshold = float(outlier_sigma) * robust_sigma
            clipped = [v for v in filtered if abs(v - center) <= threshold]
            if clipped:
                outliers_dropped = len(filtered) - len(clipped)
                filtered = clipped

    trimmed_dropped = 0
    if method == "trimmed":
        filtered, trimmed_dropped = _trim_sorted_values(sorted(filtered), trim_fraction)
        if not filtered:
            filtered = list(data)
            trimmed_dropped = 0

    if method == "mean":
        value = sum(filtered) / len(filtered)
    elif method == "trimmed":
        value = sum(filtered) / len(filtered)
    else:
        value = _quantile(filtered, 0.5)

    return value, {
        "sample_count": len(data),
        "used_sample_count": len(filtered),
        "outliers_dropped": int(outliers_dropped),
        "trimmed_dropped": int(trimmed_dropped),
        "raw_min": float(data[0]),
        "raw_max": float(data[-1]),
        "raw_median": float(_quantile(data, 0.5)),
    }


def _true16_active_channels(row):
    return [(ch, int(row.get(f"{ch.lower()}16", 0))) for ch in CHANNELS if int(row.get(f"{ch.lower()}16", 0)) > 0]


def _derive_true16_capture_lut_size(measure_dir: Path, input_globs=None):
    measurements, _stats = load_patch_measurements_true16(measure_dir, input_globs=input_globs)
    unique_inputs = {ch: set() for ch in CHANNELS}

    for row in measurements:
        active = _true16_active_channels(row)
        if len(active) != 1:
            continue
        ch_name, input_q16 = active[0]
        unique_inputs[ch_name].add(int(input_q16))

    derived = max((len(values) for values in unique_inputs.values()), default=0)
    if derived < 2:
        return 4096
    return int(derived)


def _derive_true16_header_lut_size(
    transfer_curve_header: Path | None = None,
    solver_header: Path | None = None,
):
    header_sizes = {}

    if transfer_curve_header is not None:
        transfer_model = load_transfer_curve_header(Path(transfer_curve_header))
        transfer_bucket_count = int(transfer_model.get("bucket_count") or 0)
        if transfer_bucket_count < 2:
            raise ValueError("Transfer curve header bucket_count must be >= 2")
        header_sizes["transfer_curve_header"] = transfer_bucket_count

    if solver_header is not None:
        runtime = _load_runtime_solver_ladders(Path(solver_header))
        solver_lut_size = _derive_solver_lut_size_from_runtime_ladders(runtime["ladders"])
        header_sizes["solver_header"] = int(solver_lut_size)

    if not header_sizes:
        return None

    resolved_sizes = set(header_sizes.values())
    if len(resolved_sizes) != 1:
        details = ", ".join(f"{name}={size}" for name, size in header_sizes.items())
        raise ValueError(f"Auto True16 LUT size is ambiguous across supplied headers: {details}")

    return int(next(iter(resolved_sizes)))


def _resolve_true16_lut_size(
    measure_dir: Path,
    lut_size: int,
    input_globs=None,
    transfer_curve_header: Path | None = None,
    solver_header: Path | None = None,
):
    requested_lut_size = int(lut_size)
    if requested_lut_size > 0:
        if requested_lut_size < 2:
            raise ValueError("lut_size must be >= 2")
        return requested_lut_size
    header_lut_size = _derive_true16_header_lut_size(
        transfer_curve_header=transfer_curve_header,
        solver_header=solver_header,
    )
    if header_lut_size is not None:
        return int(header_lut_size)
    return _derive_true16_capture_lut_size(measure_dir, input_globs=input_globs)


def _classify_true16_patch(row, neutral_tolerance_q16=2048):
    vals = {ch: int(row.get(f"{ch.lower()}16", 0)) for ch in CHANNELS}
    active = [(ch, vals[ch]) for ch in CHANNELS if vals[ch] > 0]
    if not active:
        return "black"
    if len(active) == 1:
        return "single"

    rgb_vals = [vals[ch] for ch in ("R", "G", "B") if vals[ch] > 0]
    has_w = vals["W"] > 0
    if len(rgb_vals) == 3 and (max(rgb_vals) - min(rgb_vals)) <= int(neutral_tolerance_q16):
        return "gray_rgbw" if has_w else "gray_rgb"
    if has_w:
        return "mixed_with_w"
    return "mixed_rgb"


def _true16_named_patch_groups(row):
    name = str(row.get("name", "")).strip().lower()
    vals = {ch: int(row.get(f"{ch.lower()}16", 0) or 0) for ch in CHANNELS}
    r = vals["R"]; g = vals["G"]; b = vals["B"]; w = vals["W"]
    rgb_active = [ch for ch in ("R", "G", "B") if vals[ch] > 0]
    active = [ch for ch in CHANNELS if vals[ch] > 0]
    rgb_vals = [vals[ch] for ch in ("R", "G", "B") if vals[ch] > 0]
    peak = max(vals.values()) if vals else 0
    rgb_peak = max(rgb_vals) if rgb_vals else 0
    rgb_min = min(rgb_vals) if rgb_vals else 0
    rgb_span = (rgb_peak - rgb_min) if rgb_vals else 0
    chroma = (float(rgb_span) / max(1.0, float(rgb_peak))) if rgb_peak > 0 else 0.0

    groups = []

    import re

    is_rgbw = (w > 0 and len(rgb_active) > 0)
    is_two_rgb = (len(rgb_active) == 2 and w <= 0)
    is_three_rgb = (len(rgb_active) >= 3 and w <= 0)

    rg_ratio = (float(g) / float(r)) if r > 0 else 0.0
    gr_ratio = (float(r) / float(g)) if g > 0 else 0.0
    gb_ratio = (float(g) / float(b)) if b > 0 else 0.0
    bg_ratio = (float(b) / float(g)) if g > 0 else 0.0
    wb_ratio = (float(w) / float(max(1, rgb_peak))) if rgb_peak > 0 else 0.0

    # --- Explicit name buckets first ---
    if name.startswith("warm_rgbw"):
        groups += ["warm_rgbw", "warm_like_rgbw", "warm_corridor"]
    elif name.startswith("amber_rgbw"):
        groups += ["amber_rgbw", "warm_like_rgbw", "warm_corridor", "yellow_corridor"]
    elif name.startswith("neutral_rgbw"):
        groups += ["neutral_rgbw", "near_neutral_tint"]
    elif name.startswith("cool_rgbw"):
        groups += ["cool_rgbw", "cool_corridor"]

    # Broader name-based coverage for new rgbw families.
    if is_rgbw:
        if re.search(
            r"(neutral|gray|grey|greytint|graytint|softwhite|offwhite|whitegray|graywhite|greywhite|gray_rgbw|grey_rgbw|gray_rgb_white|grey_rgb_white|neutral_rgb_white).*rgbw|rgbw.*(neutral|gray|grey|softwhite|offwhite|whitegray|graywhite|greywhite)",
            name,
        ):
            groups += ["neutral_rgbw", "near_neutral_tint"]
        if re.search(r"(warm|peach|salmon|tan|amber|orange|gold).*rgbw|rgbw.*(warm|peach|salmon|tan|amber|orange|gold)", name):
            groups += ["warm_like_rgbw"]
        if re.search(r"(cool|cyan|teal|mint|blue).*rgbw|rgbw.*(cool|cyan|teal|mint|blue)", name):
            groups += ["cool_rgbw", "cool_corridor"]
        if re.search(r"(amber|orange|gold|yelloworange|brightyo|supersatyo)", name):
            groups += ["amber_rgbw", "warm_like_rgbw"]
        if re.search(r"(warm|peach|salmon|tan)", name):
            groups += ["warm_rgbw", "warm_like_rgbw"]

    # RGB-only topology groups
    if is_two_rgb:
        groups.append("two_channel_rgb")
    elif is_three_rgb:
        groups.append("three_channel_rgb")

    # White-support topology groups
    if is_rgbw:
        groups.append("mixed_with_w_family")
        if w >= max(1, rgb_peak):
            groups.append("white_heavy_mix")
        elif w >= int(0.55 * max(1, rgb_peak)):
            groups.append("white_support_mix")

    # Luma families
    if peak > 0:
        if peak <= 12000:
            groups.append("low_luma_family")
        elif peak <= 42000:
            groups.append("mid_luma_family")
        else:
            groups.append("high_luma_family")
        if peak >= 56000:
            groups.append("near_peak_family")

    # Color-shape families
    if rgb_vals:
        if chroma <= 0.18 and rgb_peak > 0:
            groups.append("near_neutral_tint")
        elif chroma <= 0.45:
            groups.append("pastel_like")
        elif chroma >= 0.72 and rgb_peak >= 28000:
            groups.append("saturated_family")
        if chroma >= 0.82 and rgb_peak >= 52000:
            groups.append("neon_edge")

        # Yellow/orange split: avoid dumping all RG into yellow.
        if r > 0 and g > 0 and b == 0:
            if rg_ratio >= 0.88:
                groups.append("yellow_corridor")
            else:
                groups.append("warm_corridor")

        # Warm/cool require an actual lead rather than weak ordering.
        if r > 0 and r >= 1.12 * max(g, b if b > 0 else 0):
            groups.append("warm_corridor")
        elif b > 0 and b >= 1.12 * max(g, r if r > 0 else 0):
            groups.append("cool_corridor")

        # RGBW-specific neutral/warm/cool inference for broader coverage.
        if is_rgbw:
            # Strongly neutral RGB base with added W.
            if len(rgb_active) == 3 and (
                chroma <= 0.20 or
                rgb_span <= 4500 or
                (wb_ratio >= 0.12 and chroma <= 0.24)
            ):
                groups += ["neutral_rgbw", "near_neutral_tint"]

            # Warm RGBW: R-led or amber-led with meaningful W support.
            if (
                (r > 0 and g > 0 and r >= g and g >= b) and
                (r >= 1.08 * max(g, b if b > 0 else 0) or (r > 0 and g > 0 and b == 0 and rg_ratio < 0.88)) and
                wb_ratio >= 0.10
            ):
                groups += ["warm_rgbw", "warm_like_rgbw"]

            # Amber-like RGBW: warm RG/B mix that is close to yellow-orange rather than true yellow.
            if (
                r > 0 and g > 0 and
                r >= g and
                rg_ratio >= 0.55 and rg_ratio <= 0.90 and
                (b == 0 or b <= 0.35 * g) and
                wb_ratio >= 0.08
            ):
                groups += ["amber_rgbw", "warm_like_rgbw"]

            # Cool RGBW: B-led or cyan/teal-led with meaningful W support.
            if (
                (b > 0 and g > 0 and b >= g and g >= r) and
                (b >= 1.08 * max(g, r if r > 0 else 0) or (b > 0 and g > 0 and r == 0 and gb_ratio >= 0.75)) and
                wb_ratio >= 0.10
            ):
                groups += ["cool_rgbw"]

    # Brown/tan profile
    if re.search(r"brown(_|\b)|mahogany|umber|chestnut|tan(_|\b)|taupe|camel", name):
        groups += ["brown_corridor", "warm_corridor"]

    # Neutral-with-white aliases that do not necessarily include explicit rgbw tokens.
    if is_rgbw and re.search(r"(gray|grey|neutral|softwhite|offwhite|whitegray|graywhite|greywhite)", name):
        groups += ["neutral_rgbw", "near_neutral_tint"]

    # Yellow/orange families by explicit name
    if re.search(r"yelloworange(_|\b)", name):
        groups += ["amber_rgbw", "warm_like_rgbw", "warm_corridor"]
    if re.search(r"brightyo(_|\b)|supersatyo(_|\b)", name):
        groups += ["amber_rgbw", "warm_like_rgbw", "yellow_corridor", "saturated_family"]

    seen = set()
    out = []
    for group_name in groups:
        if group_name and group_name not in seen:
            seen.add(group_name)
            out.append(group_name)
    return out


def _isotonic_regression_nondecreasing(values, weights=None):
    if not values:
        return []

    n = len(values)
    vals = [max(0.0, min(1.0, float(v))) for v in values]
    if weights is None:
        wts = [1.0] * n
    else:
        wts = [max(1e-9, float(w)) for w in weights]

    # Pool Adjacent Violators Algorithm (PAVA): O(n), monotonic least-squares fit.
    starts = []
    ends = []
    sums_w = []
    sums_wv = []

    for i in range(n):
        starts.append(i)
        ends.append(i)
        sums_w.append(wts[i])
        sums_wv.append(wts[i] * vals[i])

        while len(starts) >= 2:
            j = len(starts) - 1
            prev_mean = sums_wv[j - 1] / sums_w[j - 1]
            cur_mean = sums_wv[j] / sums_w[j]
            if prev_mean <= cur_mean:
                break

            starts[j - 1] = starts[j - 1]
            ends[j - 1] = ends[j]
            sums_w[j - 1] = sums_w[j - 1] + sums_w[j]
            sums_wv[j - 1] = sums_wv[j - 1] + sums_wv[j]

            starts.pop()
            ends.pop()
            sums_w.pop()
            sums_wv.pop()

    out = [0.0] * n
    for start, end, sw, swv in zip(starts, ends, sums_w, sums_wv):
        mean_v = max(0.0, min(1.0, float(swv / sw)))
        for i in range(int(start), int(end) + 1):
            out[i] = mean_v

    # Guard against tiny floating-point inversions after expansion.
    for i in range(1, n):
        if out[i] < out[i - 1]:
            out[i] = out[i - 1]
    return out


def _monotonicize_norm_points(points_by_q16):
    out = {}
    keys = sorted(points_by_q16)
    raw_values = [max(0.0, min(1.0, float(points_by_q16[q16]))) for q16 in keys]
    smoothed = _isotonic_regression_nondecreasing(raw_values)
    adjustments = 0
    for q16, raw, fit in zip(keys, raw_values, smoothed):
        if abs(float(raw) - float(fit)) > 1e-9:
            adjustments += 1
        out[int(q16)] = float(fit)
    return out, adjustments


def _interpolate_true16_lut(points_by_q16, lut_size):
    lut_size = max(2, int(lut_size))
    if not points_by_q16:
        return [int(round(i * 65535.0 / (lut_size - 1))) for i in range(lut_size)]

    known_inputs = sorted(int(v) for v in points_by_q16)
    known_outputs = [float(points_by_q16[v]) for v in known_inputs]
    lut = []
    for i in range(lut_size):
        idx_q16 = int(round(i * 65535.0 / (lut_size - 1)))
        pos = bisect_left(known_inputs, idx_q16)
        if pos <= 0:
            first_x = known_inputs[0]
            first_y = known_outputs[0]
            if first_x <= 0:
                norm_y = first_y
            else:
                norm_y = first_y * (float(idx_q16) / float(first_x))
        elif pos >= len(known_inputs):
            norm_y = known_outputs[-1]
        else:
            x0 = known_inputs[pos - 1]
            x1 = known_inputs[pos]
            y0 = known_outputs[pos - 1]
            y1 = known_outputs[pos]
            if x1 <= x0:
                norm_y = y1
            else:
                alpha = float(idx_q16 - x0) / float(x1 - x0)
                norm_y = y0 * (1.0 - alpha) + y1 * alpha
        lut.append(_clamp_u16(round(max(0.0, min(1.0, norm_y)) * 65535.0)))
    lut[0] = 0
    return lut


def _lut_value_q16(input_q16, lut):
    if not lut:
        return 0
    idx = int(round((float(_clamp_u16(input_q16)) * float(len(lut) - 1)) / 65535.0))
    idx = max(0, min(len(lut) - 1, idx))
    return int(lut[idx])


def _lut_output_y(channel, input_q16, luts, summary):
    if int(input_q16) <= 0:
        return 0.0
    max_y = float(summary[channel].get("max_y") or 0.0)
    if max_y <= 0.0:
        return 0.0
    return (float(_lut_value_q16(input_q16, luts[channel])) / 65535.0) * max_y


def _shape_true16_lut(src, scale=1.0, gamma=1.0):
    scale = max(0.0, float(scale))
    gamma = max(0.05, float(gamma))
    out = [0] * len(src)
    last = 0
    for i, value in enumerate(src):
        if i == 0:
            out[i] = 0
            continue
        norm = max(0.0, min(1.0, float(value) / 65535.0))
        norm = math.pow(norm, gamma)
        norm = max(0.0, min(1.0, norm * scale))
        q16 = _clamp_u16(round(norm * 65535.0))
        if q16 < last:
            q16 = last
        out[i] = q16
        last = q16
    return out


def _invert_true16_response_lut(measured_response_lut, target_output_lut):
    """Convert a measured input->output response LUT into a correction LUT.

    measured_response_lut: input_q16 -> measured_output_q16 (normalized to [0, 65535])
    target_output_lut: desired_output_q16 for each input bucket
    returns: input_q16 command LUT that best achieves the desired output
    """
    if not measured_response_lut or not target_output_lut:
        return [0]

    n = max(2, int(len(measured_response_lut)))
    # Ensure monotonic response before inversion to avoid local reversals from noise.
    monotonic_measured = []
    last = 0
    for v in measured_response_lut:
        q = _clamp_u16(int(v))
        if q < last:
            q = last
        monotonic_measured.append(q)
        last = q

    input_axis = [int(round(i * 65535.0 / float(n - 1))) for i in range(n)]

    corrected = [0] * int(len(target_output_lut))
    last_out = 0
    for i, desired_q16 in enumerate(target_output_lut):
        if i == 0:
            corrected[i] = 0
            continue

        desired = _clamp_u16(int(desired_q16))
        pos = bisect_left(monotonic_measured, desired)

        if pos <= 0:
            y0 = monotonic_measured[0]
            x0 = input_axis[0]
            if y0 <= 0:
                q_in = x0
            else:
                q_in = int(round((float(desired) / float(y0)) * float(x0)))
        elif pos >= n:
            q_in = 65535
        else:
            y0 = monotonic_measured[pos - 1]
            y1 = monotonic_measured[pos]
            x0 = input_axis[pos - 1]
            x1 = input_axis[pos]
            if y1 <= y0:
                q_in = x1
            else:
                alpha = float(desired - y0) / float(y1 - y0)
                q_in = int(round(x0 * (1.0 - alpha) + x1 * alpha))

        q_in = _clamp_u16(q_in)
        if q_in < last_out:
            q_in = last_out
        corrected[i] = q_in
        last_out = q_in

    corrected[0] = 0
    return corrected


def _regularize_true16_command_lut(command_lut, max_step_q16=None):
    """Regularize inverse-LUT cliffs caused by flat/jumpy measured responses.

    The inverse of a measured response with long plateaus is not unique and can
    create large one-step command jumps. This pass constrains adjacent command
    deltas while preserving monotonicity and endpoint dynamic range.
    """
    if not command_lut:
        return [], {"max_step_q16": 0, "raw_max_step_q16": 0, "regularized_max_step_q16": 0, "step_clamps": 0}

    n = len(command_lut)
    out = [_clamp_u16(int(v)) for v in command_lut]
    if n == 1:
        return out, {"max_step_q16": 0, "raw_max_step_q16": 0, "regularized_max_step_q16": 0, "step_clamps": 0}

    nominal_step_q16 = max(1, int(round(65535.0 / float(n - 1))))
    if max_step_q16 is None:
        # Default allows steep regions but blocks pathological cliffs.
        max_step_q16 = max(64, nominal_step_q16 * 32)
    max_step_q16 = max(1, int(max_step_q16))

    raw_max_step = 0
    for i in range(1, n):
        step = out[i] - out[i - 1]
        if step > raw_max_step:
            raw_max_step = int(step)

    out[0] = 0
    out[-1] = 65535

    step_clamps = 0
    for i in range(1, n):
        lo = out[i - 1]
        hi = min(65535, out[i - 1] + max_step_q16)
        v = out[i]
        if v < lo:
            v = lo
            step_clamps += 1
        if v > hi:
            v = hi
            step_clamps += 1
        out[i] = v

    # Ensure each earlier sample can still reach the fixed endpoint with bounded steps.
    out[-1] = 65535
    for i in range(n - 2, -1, -1):
        min_allowed = max(0, out[i + 1] - max_step_q16)
        if out[i] < min_allowed:
            out[i] = min_allowed
            step_clamps += 1
        if out[i] > out[i + 1]:
            out[i] = out[i + 1]
            step_clamps += 1

    out[0] = 0
    out[-1] = 65535

    reg_max_step = 0
    for i in range(1, n):
        step = out[i] - out[i - 1]
        if step > reg_max_step:
            reg_max_step = int(step)

    return out, {
        "max_step_q16": int(max_step_q16),
        "raw_max_step_q16": int(raw_max_step),
        "regularized_max_step_q16": int(reg_max_step),
        "step_clamps": int(step_clamps),
    }


def _density_regularize_true16_command_lut(command_lut, floor_strength=0.18, smoothing_passes=2):
    """Reduce long duplicate runs without forcing a harsh linearized midrange.

    This blends the inverse LUT toward a very gentle monotonic reference ramp,
    then re-monotonicizes and preserves endpoints. The intent is to recover code
    density in plateau-heavy regions while staying visually close to the measured
    response instead of pushing toward a hard linear remap.
    """
    if not command_lut:
        return [], {"applied": False, "floor_strength": 0.0, "smoothing_passes": 0, "duplicate_steps_before": 0, "duplicate_steps_after": 0}

    n = len(command_lut)
    out = [_clamp_u16(int(v)) for v in command_lut]
    if n <= 2:
        return out, {"applied": False, "floor_strength": 0.0, "smoothing_passes": 0, "duplicate_steps_before": 0, "duplicate_steps_after": 0}

    floor_strength = max(0.0, min(0.50, float(floor_strength)))
    smoothing_passes = max(0, int(smoothing_passes))
    before_dupes = sum(1 for i in range(1, n) if out[i] <= out[i - 1])

    ref = [int(round(i * 65535.0 / float(n - 1))) for i in range(n)]
    blended = []
    for i in range(n):
        q = int(round((1.0 - floor_strength) * float(out[i]) + floor_strength * float(ref[i])))
        blended.append(_clamp_u16(q))

    if smoothing_passes > 0:
        for _ in range(smoothing_passes):
            smoothed = list(blended)
            for i in range(1, n - 1):
                smoothed[i] = _clamp_u16(int(round((blended[i - 1] + 2 * blended[i] + blended[i + 1]) / 4.0)))
            blended = smoothed

    fitted = _isotonic_regression_nondecreasing([float(v) / 65535.0 for v in blended])
    out2 = [_clamp_u16(int(round(max(0.0, min(1.0, float(v))) * 65535.0))) for v in fitted]
    out2[0] = 0
    out2[-1] = 65535

    after_dupes = sum(1 for i in range(1, n) if out2[i] <= out2[i - 1])
    return out2, {
        "applied": bool(floor_strength > 0.0 or smoothing_passes > 0),
        "floor_strength": float(floor_strength),
        "smoothing_passes": int(smoothing_passes),
        "duplicate_steps_before": int(before_dupes),
        "duplicate_steps_after": int(after_dupes),
    }




def _identity_true16_lut(entry_count):
    entry_count = max(2, int(entry_count))
    return [int(round(i * 65535.0 / max(1, (entry_count - 1)))) for i in range(entry_count)]


def _smooth_true16_series(series, passes=1):
    vals = [float(v) for v in series]
    if not vals:
        return []
    for _ in range(max(0, int(passes))):
        out = vals[:]
        for i in range(len(vals)):
            total = vals[i] * 2.0
            weight = 2.0
            if i > 0:
                total += vals[i - 1]
                weight += 1.0
            if i + 1 < len(vals):
                total += vals[i + 1]
                weight += 1.0
            out[i] = total / weight
        vals = out
    return vals


def _normalize_true16_steps(steps, min_step, max_step, target_sum, iterations=8):
    vals = [float(max(0.0, s)) for s in steps]
    if not vals:
        return []
    min_step = float(max(0.0, min_step))
    max_step = float(max(min_step, max_step))
    target_sum = float(max(0.0, target_sum))
    for _ in range(max(1, int(iterations))):
        vals = [max(min_step, min(max_step, s)) for s in vals]
        cur = sum(vals)
        if cur <= 1e-12:
            break
        scale = target_sum / cur
        vals = [s * scale for s in vals]
    vals = [max(min_step, min(max_step, s)) for s in vals]
    cur = sum(vals)
    if cur > 1e-12:
        vals = [s * (target_sum / cur) for s in vals]
    return vals


def _redistribute_true16_command_lut(command_lut, min_step_factor=0.35, max_step_factor=2.75, smoothing_passes=3):
    if not command_lut:
        return []
    src = [_clamp_u16(int(v)) for v in command_lut]
    if len(src) <= 2:
        return src
    steps = [max(0.0, float(src[i + 1] - src[i])) for i in range(len(src) - 1)]
    avg_step = 65535.0 / max(1, len(steps))
    min_step = avg_step * max(0.0, float(min_step_factor))
    max_step = avg_step * max(float(min_step_factor), float(max_step_factor))
    smoothed = _smooth_true16_series(steps, passes=smoothing_passes)
    norm_steps = _normalize_true16_steps(smoothed, min_step=min_step, max_step=max_step, target_sum=65535.0)
    out = [0] * len(src)
    acc = 0.0
    for i, step in enumerate(norm_steps, start=1):
        acc += float(step)
        out[i] = _clamp_u16(int(round(acc)))
    out[0] = 0
    out[-1] = 65535
    for i in range(1, len(out)):
        if out[i] < out[i - 1]:
            out[i] = out[i - 1]
    return out


def _delta_preserve_true16_command_lut(raw_inverse_lut, measured_response_lut, target_output_lut, strength=0.38, max_delta_ratio=0.10, smoothing_passes=3, midtone_bias=0.40):
    if not raw_inverse_lut:
        return [], {"applied": False, "strength": 0.0, "max_delta_ratio": 0.0, "smoothing_passes": 0}

    n = len(raw_inverse_lut)
    identity = _identity_true16_lut(n)
    measured = [_clamp_u16(int(v)) for v in (measured_response_lut or identity)[:n]]
    if len(measured) < n:
        measured = measured + identity[len(measured):]
    target = [_clamp_u16(int(v)) for v in (target_output_lut or identity)[:n]]
    if len(target) < n:
        target = target + identity[len(target):]

    strength = max(0.0, min(1.0, float(strength)))
    max_delta_ratio = max(0.0, min(0.35, float(max_delta_ratio)))
    smoothing_passes = max(0, int(smoothing_passes))
    midtone_bias = max(0.0, min(1.0, float(midtone_bias)))

    blended = [0.0] * n
    raw_deltas = []
    applied_deltas = []
    for i in range(n):
        x = float(i) / float(max(1, n - 1))
        mid = 1.0 - abs(2.0 * x - 1.0)
        error_norm = abs(float(target[i]) - float(measured[i])) / 65535.0
        local_strength = strength * (0.30 + 0.70 * math.sqrt(max(0.0, error_norm)))
        local_strength *= (1.0 + midtone_bias * mid)
        local_strength = max(0.0, min(1.0, local_strength))

        local_cap = 65535.0 * max_delta_ratio * (0.55 + 0.45 * mid)
        raw_delta = float(raw_inverse_lut[i]) - float(identity[i])
        delta = max(-local_cap, min(local_cap, raw_delta * local_strength))
        blended[i] = float(identity[i]) + delta
        raw_deltas.append(abs(raw_delta))
        applied_deltas.append(abs(delta))

    blended = _smooth_true16_series(blended, passes=smoothing_passes)
    fitted = _isotonic_regression_nondecreasing([max(0.0, min(1.0, v / 65535.0)) for v in blended])
    out = [_clamp_u16(int(round(max(0.0, min(1.0, float(v))) * 65535.0))) for v in fitted]
    out[0] = 0
    out[-1] = 65535

    return out, {
        "applied": True,
        "strength": float(strength),
        "max_delta_ratio": float(max_delta_ratio),
        "smoothing_passes": int(smoothing_passes),
        "midtone_bias": float(midtone_bias),
        "mean_raw_delta_q16": float(sum(raw_deltas) / len(raw_deltas)) if raw_deltas else 0.0,
        "mean_applied_delta_q16": float(sum(applied_deltas) / len(applied_deltas)) if applied_deltas else 0.0,
        "max_applied_delta_q16": float(max(applied_deltas) if applied_deltas else 0.0),
    }

def _summarize_error_series(abs_errors, signed_errors):
    if not abs_errors:
        return {
            "count": 0,
            "mae_y": None,
            "rmse_y": None,
            "max_abs_y": None,
            "p95_abs_y": None,
            "mean_signed_y_error": None,
            "p95_overprediction_y": None,
            "p95_underprediction_y": None,
        }
    mae = sum(abs_errors) / len(abs_errors)
    rmse = math.sqrt(sum((v * v) for v in abs_errors) / len(abs_errors))
    return {
        "count": len(abs_errors),
        "mae_y": float(mae),
        "rmse_y": float(rmse),
        "max_abs_y": float(max(abs_errors)),
        "p95_abs_y": float(_quantile(abs_errors, 0.95)),
        "mean_signed_y_error": float(sum(signed_errors) / len(signed_errors)),
        "p95_overprediction_y": float(_quantile([max(0.0, v) for v in signed_errors], 0.95)),
        "p95_underprediction_y": float(_quantile([max(0.0, -v) for v in signed_errors], 0.95)),
    }


def _append_true16_chroma_metrics(group_summary, xy_errors, saturation_ratios, saturation_deficits):
    if not xy_errors or not saturation_ratios or not saturation_deficits:
        return group_summary

    group_summary["mean_xy_error"] = float(sum(xy_errors) / len(xy_errors))
    group_summary["p95_xy_error"] = float(_quantile(xy_errors, 0.95))
    group_summary["max_xy_error"] = float(max(xy_errors))
    group_summary["mean_saturation_ratio"] = float(sum(saturation_ratios) / len(saturation_ratios))
    group_summary["min_saturation_ratio"] = float(min(saturation_ratios))
    group_summary["max_saturation_ratio"] = float(max(saturation_ratios))
    group_summary["mean_saturation_deficit"] = float(sum(saturation_deficits) / len(saturation_deficits))
    group_summary["p95_saturation_deficit"] = float(_quantile(saturation_deficits, 0.95))
    group_summary["max_saturation_deficit"] = float(max(saturation_deficits))
    return group_summary


def _true16_group_metric(qa_groups, group_name, metric_name, default=0.0):
    group = qa_groups.get(group_name, {}) if isinstance(qa_groups, dict) else {}
    value = group.get(metric_name)
    if value is None:
        return float(default)
    try:
        return float(value)
    except Exception:
        return float(default)


def _true16_global_fit_objective(
    qa,
    per_channel_scales=None,
    shared_gamma=1.0,
    peak_preserve_strength=0.0,
):
    groups = qa.get("groups", {}) if isinstance(qa, dict) else {}

    overall_mae = _true16_group_metric(groups, "overall", "mae_y")
    overall_signed = _true16_group_metric(groups, "overall", "mean_signed_y_error")
    mixed_with_w_mae = _true16_group_metric(groups, "mixed_with_w", "mae_y")
    mixed_with_w_signed = _true16_group_metric(groups, "mixed_with_w", "mean_signed_y_error")
    gray_rgbw_mae = _true16_group_metric(groups, "gray_rgbw", "mae_y")
    mixed_rgb_mae = _true16_group_metric(groups, "mixed_rgb", "mae_y")
    warm_like_xy_error = _true16_group_metric(groups, "warm_like_rgbw", "mean_xy_error")
    warm_like_sat_deficit = _true16_group_metric(groups, "warm_like_rgbw", "p95_saturation_deficit")

    # Bias toward reducing W-active mixed patch over/under prediction while
    # keeping overall luminance error bounded. Warm/yellow RGBW rows also get a
    # chroma-preservation term so washed-out yellows are visible to the fitter.
    objective = (
        overall_mae
        + 0.85 * mixed_with_w_mae
        + 1.50 * abs(mixed_with_w_signed)
        + 0.40 * gray_rgbw_mae
        + 0.35 * abs(overall_signed)
        + 0.15 * mixed_rgb_mae
        + 2200.0 * warm_like_xy_error
        + 95.0 * warm_like_sat_deficit
    )

    # Keep global fit from over-compressing channel tops. This preserves runtime
    # headroom while still allowing mid-level correction from mixed-patch data.
    scale_targets = {"R": 0.88, "G": 0.88, "B": 0.88, "W": 0.76}
    scales = {}
    for ch in CHANNELS:
        if isinstance(per_channel_scales, dict):
            scales[ch] = float(per_channel_scales.get(ch, 1.0))
        else:
            scales[ch] = 1.0

    peak_preserve_strength = max(0.0, float(peak_preserve_strength))
    peak_penalty = 0.0
    gamma_penalty = 0.0
    if peak_preserve_strength > 0.0:
        for ch, target in scale_targets.items():
            deficit = max(0.0, float(target) - float(scales.get(ch, 1.0)))
            peak_penalty += 650.0 * (deficit * deficit)

        avg_scale = sum(float(scales[ch]) for ch in CHANNELS) / float(len(CHANNELS))
        avg_deficit = max(0.0, 0.82 - avg_scale)
        peak_penalty += 900.0 * (avg_deficit * avg_deficit)

        gamma_penalty = 22.0 * (float(shared_gamma) - 1.0) ** 2

        penalty_scale = float(peak_preserve_strength)
        peak_penalty *= penalty_scale
        gamma_penalty *= penalty_scale

    objective += peak_penalty + gamma_penalty

    return float(objective), {
        "overall_mae": float(overall_mae),
        "overall_signed": float(overall_signed),
        "mixed_with_w_mae": float(mixed_with_w_mae),
        "mixed_with_w_signed": float(mixed_with_w_signed),
        "gray_rgbw_mae": float(gray_rgbw_mae),
        "mixed_rgb_mae": float(mixed_rgb_mae),
        "warm_like_xy_error": float(warm_like_xy_error),
        "warm_like_sat_deficit": float(warm_like_sat_deficit),
        "peak_penalty": float(peak_penalty),
        "gamma_penalty": float(gamma_penalty),
        "peak_preserve_strength": float(peak_preserve_strength),
        "scales": {ch: float(scales[ch]) for ch in CHANNELS},
        "shared_gamma": float(shared_gamma),
    }


def _shape_true16_luts_with_global_params(base_luts, per_channel_scales, shared_gamma):
    out = {}
    gamma = max(0.80, min(1.35, float(shared_gamma)))
    for ch in CHANNELS:
        scale = max(0.55, min(1.20, float(per_channel_scales.get(ch, 1.0))))
        out[ch] = _shape_true16_lut(base_luts[ch], scale=scale, gamma=gamma)
    return out


def optimize_true16_global_mixed_fit(
    measurements,
    base_luts,
    measured_model_luts,
    summary,
    neutral_tolerance_q16=2048,
    black_level_y=0.0,
    ambient_profile=None,
    enabled=True,
    profile_target="linear",
    max_iterations=5,
    peak_preserve_strength=0.0,
):
    result = {
        "enabled": bool(enabled),
        "applied": False,
        "reason": "",
        "max_iterations": int(max(1, int(max_iterations))),
        "iterations_run": 0,
        "mixed_row_count": 0,
        "gamma": 1.0,
        "scales": {ch: 1.0 for ch in CHANNELS},
        "baseline_objective": None,
        "optimized_objective": None,
        "baseline_metrics": {},
        "optimized_metrics": {},
        "peak_preserve_strength": float(max(0.0, float(peak_preserve_strength))),
    }

    if not enabled:
        result["reason"] = "disabled"
        return {ch: list(base_luts[ch]) for ch in CHANNELS}, result

    if str(profile_target or "").strip().lower() == "legacy-measured":
        result["reason"] = "skipped-for-legacy-measured"
        return {ch: list(base_luts[ch]) for ch in CHANNELS}, result

    mixed_classes = {"mixed_with_w", "gray_rgbw", "mixed_rgb", "gray_rgb"}
    mixed_row_count = 0
    for row in measurements:
        row_class = _classify_true16_patch(row, neutral_tolerance_q16=neutral_tolerance_q16)
        if row_class in mixed_classes:
            mixed_row_count += 1

    result["mixed_row_count"] = int(mixed_row_count)
    if mixed_row_count < 8:
        result["reason"] = "insufficient-mixed-rows"
        return {ch: list(base_luts[ch]) for ch in CHANNELS}, result

    working_luts = {ch: list(base_luts[ch]) for ch in CHANNELS}
    scales = {ch: 1.0 for ch in CHANNELS}
    shared_gamma = 1.0

    baseline_qa = build_true16_calibration_qa(
        measurements,
        working_luts,
        summary,
        measured_model_luts=measured_model_luts,
        neutral_tolerance_q16=neutral_tolerance_q16,
        black_level_y=black_level_y,
        ambient_profile=ambient_profile,
    )
    best_objective, best_metrics = _true16_global_fit_objective(
        baseline_qa,
        per_channel_scales=scales,
        shared_gamma=shared_gamma,
        peak_preserve_strength=peak_preserve_strength,
    )

    result["baseline_objective"] = float(best_objective)
    result["optimized_objective"] = float(best_objective)
    result["baseline_metrics"] = dict(best_metrics)
    result["optimized_metrics"] = dict(best_metrics)

    # Coarse seed search reduces sensitivity to coordinate-descent local minima.
    seed_rgb_values = [0.70, 0.75, 0.80, 0.85, 0.90, 1.00]
    seed_w_values = [0.60, 0.65, 0.70, 0.75, 0.80, 0.90, 1.00]
    seed_gamma_values = [1.00, 1.10, 1.20]
    for rgb_seed in seed_rgb_values:
        for w_seed in seed_w_values:
            for gamma_seed in seed_gamma_values:
                seed_scales = {
                    "R": float(rgb_seed),
                    "G": float(rgb_seed),
                    "B": float(rgb_seed),
                    "W": float(w_seed),
                }
                seed_luts = _shape_true16_luts_with_global_params(
                    base_luts,
                    seed_scales,
                    gamma_seed,
                )
                qa = build_true16_calibration_qa(
                    measurements,
                    seed_luts,
                    summary,
                    measured_model_luts=measured_model_luts,
                    neutral_tolerance_q16=neutral_tolerance_q16,
                    black_level_y=black_level_y,
                    ambient_profile=ambient_profile,
                )
                objective, metrics = _true16_global_fit_objective(
                    qa,
                    per_channel_scales=seed_scales,
                    shared_gamma=gamma_seed,
                    peak_preserve_strength=peak_preserve_strength,
                )
                if objective < (best_objective - 1e-9):
                    best_objective = float(objective)
                    best_metrics = dict(metrics)
                    working_luts = seed_luts
                    shared_gamma = float(gamma_seed)
                    scales = dict(seed_scales)

    scale_step = 0.10
    gamma_step = 0.08

    max_iterations = max(1, int(max_iterations))
    for iteration in range(max_iterations):
        result["iterations_run"] = int(iteration + 1)
        improved = False

        for knob in ["R", "G", "B", "W", "gamma"]:
            current = shared_gamma if knob == "gamma" else scales[knob]
            step = gamma_step if knob == "gamma" else scale_step
            candidates = [
                current - step,
                current - (0.5 * step),
                current,
                current + (0.5 * step),
                current + step,
            ]

            local_best_obj = best_objective
            local_best_value = current
            local_best_luts = working_luts
            local_best_metrics = best_metrics

            for candidate in candidates:
                if knob == "gamma":
                    cand_gamma = max(0.80, min(1.35, float(candidate)))
                    cand_scales = dict(scales)
                else:
                    cand_gamma = float(shared_gamma)
                    cand_scales = dict(scales)
                    cand_scales[knob] = max(0.55, min(1.20, float(candidate)))

                candidate_luts = _shape_true16_luts_with_global_params(
                    base_luts,
                    cand_scales,
                    cand_gamma,
                )
                qa = build_true16_calibration_qa(
                    measurements,
                    candidate_luts,
                    summary,
                    measured_model_luts=measured_model_luts,
                    neutral_tolerance_q16=neutral_tolerance_q16,
                    black_level_y=black_level_y,
                    ambient_profile=ambient_profile,
                )
                objective, metrics = _true16_global_fit_objective(
                    qa,
                    per_channel_scales=cand_scales,
                    shared_gamma=cand_gamma,
                    peak_preserve_strength=peak_preserve_strength,
                )
                if objective < (local_best_obj - 1e-9):
                    local_best_obj = float(objective)
                    local_best_value = float(cand_gamma if knob == "gamma" else cand_scales[knob])
                    local_best_luts = candidate_luts
                    local_best_metrics = metrics

            if local_best_obj < (best_objective - 1e-9):
                best_objective = float(local_best_obj)
                best_metrics = dict(local_best_metrics)
                working_luts = local_best_luts
                if knob == "gamma":
                    shared_gamma = float(local_best_value)
                else:
                    scales[knob] = float(local_best_value)
                improved = True

        scale_step = max(0.015, scale_step * 0.60)
        gamma_step = max(0.012, gamma_step * 0.60)
        if not improved:
            break

    result["gamma"] = float(shared_gamma)
    result["scales"] = {ch: float(scales[ch]) for ch in CHANNELS}
    result["optimized_objective"] = float(best_objective)
    result["optimized_metrics"] = dict(best_metrics)

    baseline_objective = float(result.get("baseline_objective") or 0.0)
    if best_objective < (baseline_objective - 1e-9):
        result["applied"] = True
        result["reason"] = "optimized"
    else:
        result["applied"] = False
        result["reason"] = "no-improvement"
        working_luts = {ch: list(base_luts[ch]) for ch in CHANNELS}

    return working_luts, result


def resolve_mixing_config(
    mixing_profile,
    neutral_threshold_q16=None,
    white_weight_q16=None,
    rgb_weight_q16=None,
):
    base = dict(MIXING_PRESETS[mixing_profile])
    if neutral_threshold_q16 is not None:
        base["neutral_threshold_q16"] = _clamp_u16(neutral_threshold_q16)
    if white_weight_q16 is not None:
        base["white_weight_q16"] = _clamp_u16(white_weight_q16)
    if rgb_weight_q16 is not None:
        base["rgb_weight_q16"] = _clamp_u16(rgb_weight_q16)
    return base


def estimate_white_scale_from_gray_pairs(
    measurements,
    max_bfi=4,
    target_ratio=1.35,
    min_code=24,
    black_level_y=0.0,
):
    rgb = defaultdict(list)
    rgbw = defaultdict(list)

    black_level_y = max(0.0, float(black_level_y))

    for row in measurements:
        r = int(row.get("r", 0))
        g = int(row.get("g", 0))
        b = int(row.get("b", 0))
        w = int(row.get("w", 0))
        if r <= 0 or g <= 0 or b <= 0:
            continue
        if not (r == g == b):
            continue
        if r < int(min_code):
            continue

        bfi_r = int(row.get("bfi_r", 0))
        bfi_g = int(row.get("bfi_g", 0))
        bfi_b = int(row.get("bfi_b", 0))
        bfi_w = int(row.get("bfi_w", 0))
        if not (bfi_r == bfi_g == bfi_b):
            continue
        bfi = bfi_r
        if bfi < 0 or bfi > int(max_bfi):
            continue

        y = max(0.0, float(row.get("Y", 0.0)) - black_level_y)
        key = (bfi, r)
        if w == 0 and bfi_w == 0:
            rgb[key].append(y)
        elif w == r and bfi_w == bfi:
            rgbw[key].append(y)

    ratios = []
    for key in sorted(set(rgb.keys()) & set(rgbw.keys())):
        y_rgb = mean(rgb[key])
        y_rgbw = mean(rgbw[key])
        if y_rgb is None or y_rgbw is None or y_rgb <= 0.0:
            continue
        ratios.append(float(y_rgbw / y_rgb))

    if not ratios:
        return 1.0, {
            "pair_count": 0,
            "target_ratio": float(target_ratio),
            "median_ratio": None,
            "recommended_scale": 1.0,
            "min_code": int(min_code),
        }

    median_ratio = _quantile(ratios, 0.5)
    if median_ratio is None or median_ratio <= 0.0:
        suggested = 1.0
    else:
        suggested = float(target_ratio) / median_ratio

    # Auto-scaling is intentionally attenuation-oriented to protect warm hues.
    suggested = max(0.5, min(1.0, suggested))
    return suggested, {
        "pair_count": len(ratios),
        "target_ratio": float(target_ratio),
        "median_ratio": float(median_ratio),
        "p10_ratio": float(_quantile(ratios, 0.10)),
        "p90_ratio": float(_quantile(ratios, 0.90)),
        "recommended_scale": float(suggested),
        "min_code": int(min_code),
    }


def apply_white_table_shape(profile_tables, per_bfi_tables, white_scale=1.0, white_gamma=1.0):
    white_scale = max(0.0, float(white_scale))
    white_gamma = max(0.05, float(white_gamma))

    shaped_profile = {ch: list(profile_tables[ch]) for ch in CHANNELS}
    shaped_per_bfi = {
        ch: {int(bfi): list(vals) for bfi, vals in per_bfi_tables[ch].items()}
        for ch in CHANNELS
    }

    def _shape_table(src):
        out = [0] * len(src)
        last = 0
        for i, q in enumerate(src):
            if i == 0:
                out[i] = 0
                continue
            y = max(0.0, min(1.0, float(q) / 65535.0))
            y = math.pow(y, white_gamma)
            y = max(0.0, min(1.0, y * white_scale))
            q_out = int(round(y * 65535.0))
            if q_out < last:
                q_out = last
            out[i] = q_out
            last = q_out
        out[0] = 0
        return out

    shaped_profile["W"] = _shape_table(shaped_profile["W"])
    for bfi in list(shaped_per_bfi["W"].keys()):
        shaped_per_bfi["W"][bfi] = _shape_table(shaped_per_bfi["W"][bfi])

    return shaped_profile, shaped_per_bfi, {
        "white_channel_scale": float(white_scale),
        "white_channel_gamma": float(white_gamma),
    }

def build_channel_tables(measurements, max_bfi: int = 4, profile_source_bfi: int = 0):
    return build_channel_tables_with_correction(
        measurements,
        max_bfi=max_bfi,
        profile_source_bfi=profile_source_bfi,
        profile_target="linear",
        profile_target_gamma=2.2,
        enable_black_level_compensation=True,
        black_level_y=None,
    )


def build_channel_tables_with_correction(
    measurements,
    max_bfi: int = 4,
    profile_source_bfi: int = 0,
    profile_target: str = "perceptual-density",
    profile_target_gamma: float = 2.2,
    enable_black_level_compensation: bool = True,
    black_level_y=None,
):
    grouped = {(ch, bfi): {} for ch in CHANNELS for bfi in range(max_bfi + 1)}
    channel_max_y = {ch: 0.0 for ch in CHANNELS}
    channel_max_raw_y = {ch: 0.0 for ch in CHANNELS}

    if enable_black_level_compensation:
        if black_level_y is None:
            black_level_y, black_stats = _estimate_black_level_8bit(measurements)
        else:
            black_level_y = max(0.0, float(black_level_y))
            black_stats = {
                "source": "fixed",
                "sample_count": 0,
                "p10_y": None,
                "median_y": None,
                "p90_y": None,
                "fallback_sample_count": 0,
                "fixed_black_level_y": float(black_level_y),
            }
    else:
        black_level_y = 0.0
        black_stats = {
            "source": "disabled",
            "sample_count": 0,
            "p10_y": None,
            "median_y": None,
            "p90_y": None,
            "fallback_sample_count": 0,
        }

    profile_target = str(profile_target or "linear").strip().lower()
    if profile_target not in ("legacy-measured", "linear", "gamma", "perceptual-density", "delta-preserving"):
        profile_target = "linear"

    for row in measurements:
        active = [(ch, row[ch.lower()], row[f"bfi_{ch.lower()}"]) for ch in CHANNELS if row[ch.lower()] > 0]
        if len(active) != 1:
            continue
        ch, value, bfi = active[0]
        if bfi > max_bfi:
            continue

        y_raw = float(row["Y"])
        y_signal = max(0.0, y_raw - black_level_y)

        grouped[(ch, bfi)].setdefault(int(value), []).append(float(y_signal))
        channel_max_y[ch] = max(channel_max_y[ch], float(y_signal))
        channel_max_raw_y[ch] = max(channel_max_raw_y[ch], float(y_raw))

    per_bfi_tables = {ch: {} for ch in CHANNELS}
    summary = {
        ch: {
            "mode": "measured",
            "max_y": channel_max_y[ch],
            "max_y_raw": channel_max_raw_y[ch],
            "bfi": {},
        }
        for ch in CHANNELS
    }

    for ch in CHANNELS:
        max_y = channel_max_y[ch] if channel_max_y[ch] > 0 else 1.0
        for bfi in range(max_bfi + 1):
            pts = grouped[(ch, bfi)]
            if not pts:
                per_bfi_tables[ch][bfi] = [round(i * 257) for i in range(256)]
                summary[ch]["bfi"][str(bfi)] = {"points": 0, "mode": "fallback-linear", "first_nonzero_input": 1}
                continue
            avg = {v: sum(vals) / len(vals) for v, vals in pts.items()}
            known_norm = {int(v): float(y) / max_y for v, y in avg.items()}
            lut = _interp_from_zero(known_norm)
            per_bfi_tables[ch][bfi] = lut
            sorted_keys = sorted(known_norm.keys())
            first_nonzero_input = min((k for k in sorted_keys if k > 0), default=0)
            summary[ch]["bfi"][str(bfi)] = {
                "points": len(sorted_keys),
                "mode": "measured",
                "first_nonzero_input": first_nonzero_input,
                "first_nonzero_q16": lut[first_nonzero_input] if first_nonzero_input < 256 else 0,
            }

    profile_tables = {}
    if profile_target == "legacy-measured":
        for ch in CHANNELS:
            profile_tables[ch] = per_bfi_tables[ch].get(profile_source_bfi, [round(i * 257) for i in range(256)])
            profile_tables[ch][0] = 0
    else:
        target_table = _build_target_q16_table(
            256,
            target="gamma" if profile_target == "gamma" else "linear",
            gamma=profile_target_gamma,
        )
        for ch in CHANNELS:
            profile_tables[ch] = list(target_table)

    summary["_global"] = {
        "black_level_enabled": bool(enable_black_level_compensation),
        "black_level_y": float(black_level_y),
        "black_level": black_stats,
        "profile_target": profile_target,
        "profile_target_gamma": float(max(0.05, float(profile_target_gamma))),
        "profile_source_bfi": int(profile_source_bfi),
    }

    return profile_tables, per_bfi_tables, summary

def build_channel_tables_true16(
    measurements,
    lut_size: int = 4096,
    aggregation: str = "median",
    trim_fraction: float = 0.1,
    outlier_sigma: float = 3.5,
    enforce_monotonic: bool = True,
    enable_black_level_compensation: bool = True,
    black_level_y=None,
):
    """Build robust 16->16 LUT tables from True16 measurements."""
    measured_inputs = {ch: defaultdict(list) for ch in CHANNELS}
    point_stats = {ch: {} for ch in CHANNELS}
    summary = {ch: {"mode": "measured", "max_y": 0.0, "max_y_raw": 0.0, "points": 0} for ch in CHANNELS}
    luts = {ch: [] for ch in CHANNELS}

    if enable_black_level_compensation:
        if black_level_y is None:
            ambient_profile = _estimate_true16_ambient_profile(measurements)
            black_level_y = float(ambient_profile.get("global", {}).get("Y", 0.0) or 0.0)
            black_stats = dict(ambient_profile.get("stats", {}))
        else:
            black_level_y = max(0.0, float(black_level_y))
            black_stats = {
                "source": "fixed",
                "sample_count": 0,
                "p10_y": None,
                "median_y": None,
                "p90_y": None,
                "fallback_sample_count": 0,
                "fixed_black_level_y": float(black_level_y),
            }
            ambient_profile = {
                "enabled": True,
                "global": {
                    "Y": float(black_level_y),
                    "xyz": None,
                    "sample_count": 0,
                },
                "per_channel": {
                    ch: {
                        "Y": float(black_level_y),
                        "xyz": None,
                        "source": "fixed",
                        "sample_count": 0,
                    }
                    for ch in CHANNELS
                },
                "stats": dict(black_stats),
            }
    else:
        black_level_y = 0.0
        black_stats = {
            "source": "disabled",
            "sample_count": 0,
            "p10_y": None,
            "median_y": None,
            "p90_y": None,
            "fallback_sample_count": 0,
        }
        ambient_profile = {
            "enabled": False,
            "global": {
                "Y": 0.0,
                "xyz": None,
                "sample_count": 0,
            },
            "per_channel": {
                ch: {
                    "Y": 0.0,
                    "xyz": None,
                    "source": "disabled",
                    "sample_count": 0,
                }
                for ch in CHANNELS
            },
            "stats": dict(black_stats),
        }

    for row in measurements:
        active = _true16_active_channels(row)
        if len(active) != 1:
            continue
        ch_name, input_q16 = active[0]
        y_raw = float(row.get("Y", 0.0))

        compensated_xyz = _measurement_row_xyz(row, ambient_profile=ambient_profile, channel_hint=ch_name)
        if compensated_xyz is not None:
            y_signal = max(0.0, float(compensated_xyz[1]))
        else:
            per_ch_floor = _ambient_profile_y(ambient_profile, channel_hint=ch_name, default=black_level_y)
            y_signal = max(0.0, y_raw - per_ch_floor)

        measured_inputs[ch_name][int(input_q16)].append(y_signal)
        summary[ch_name]["max_y_raw"] = max(float(summary[ch_name].get("max_y_raw", 0.0)), y_raw)

    for ch in CHANNELS:
        pts = measured_inputs[ch]
        if not pts:
            luts[ch] = [int(round(i * 65535.0 / max(1, (lut_size - 1)))) for i in range(lut_size)]
            summary[ch] = {
                "mode": "fallback-linear",
                "max_y": 0.0,
                "max_y_raw": float(summary[ch].get("max_y_raw", 0.0)),
                "points": 0,
                "samples": 0,
                "used_samples": 0,
                "outliers_dropped": 0,
                "trimmed_dropped": 0,
                "largest_gap_q16": 65535,
                "median_gap_q16": 65535,
                "first_nonzero_input_q16": 0,
                "last_input_q16": 0,
                "monotonic_adjustments": 0,
            }
            continue

        aggregated_y = {}
        for q16, yvals in sorted(pts.items()):
            agg_y, agg_stats = _robust_aggregate(yvals, method=aggregation, trim_fraction=trim_fraction, outlier_sigma=outlier_sigma)
            if agg_y is None:
                continue
            aggregated_y[int(q16)] = float(agg_y)
            point_stats[ch][int(q16)] = agg_stats

        if not aggregated_y:
            luts[ch] = [int(round(i * 65535.0 / max(1, (lut_size - 1)))) for i in range(lut_size)]
            summary[ch]["mode"] = "fallback-linear"
            summary[ch]["points"] = 0
            continue

        max_y = max(aggregated_y.values()) or 1.0
        known_norm = {q16: float(y) / max_y for q16, y in aggregated_y.items()}
        monotonic_adjustments = 0
        if enforce_monotonic:
            known_norm, monotonic_adjustments = _monotonicize_norm_points(known_norm)

        luts[ch] = _interpolate_true16_lut(known_norm, lut_size=lut_size)
        sorted_inputs = sorted(known_norm.keys())
        gaps = [b - a for a, b in zip(sorted_inputs, sorted_inputs[1:])]

        summary[ch] = {
            "mode": "measured",
            "max_y": float(max_y),
            "max_y_raw": float(summary[ch].get("max_y_raw", 0.0)),
            "points": len(sorted_inputs),
            "samples": int(sum(stats.get("sample_count", 0) for stats in point_stats[ch].values())),
            "used_samples": int(sum(stats.get("used_sample_count", 0) for stats in point_stats[ch].values())),
            "outliers_dropped": int(sum(stats.get("outliers_dropped", 0) for stats in point_stats[ch].values())),
            "trimmed_dropped": int(sum(stats.get("trimmed_dropped", 0) for stats in point_stats[ch].values())),
            "largest_gap_q16": int(max(gaps) if gaps else 65535),
            "median_gap_q16": int(round(_quantile(gaps, 0.5))) if gaps else 65535,
            "first_nonzero_input_q16": int(min((q for q in sorted_inputs if q > 0), default=0)),
            "last_input_q16": int(sorted_inputs[-1]),
            "monotonic_adjustments": int(monotonic_adjustments),
        }

    summary["_global"] = {
        "black_level_enabled": bool(enable_black_level_compensation),
        "black_level_y": float(black_level_y),
        "black_level": black_stats,
        "ambient_profile": ambient_profile,
    }

    return luts, summary, measured_inputs


def estimate_true16_white_scale_from_mixed_rows(
    measurements,
    luts,
    summary,
    neutral_tolerance_q16=2048,
    black_level_y=0.0,
    ambient_profile=None,
):
    numerator = 0.0
    denominator = 0.0
    pair_count = 0
    neutral_pair_count = 0
    black_level_y = max(0.0, float(black_level_y))

    for row in measurements:
        row_class = _classify_true16_patch(row, neutral_tolerance_q16=neutral_tolerance_q16)
        if row_class not in ("gray_rgbw", "mixed_with_w"):
            continue
        predicted_w = _lut_output_y("W", int(row.get("w16", 0)), luts, summary)
        if predicted_w <= 0.0:
            continue
        predicted_rgb = sum(_lut_output_y(ch, int(row.get(f"{ch.lower()}16", 0)), luts, summary) for ch in ("R", "G", "B"))
        measured_xyz = _measurement_row_xyz(row, ambient_profile=ambient_profile)
        if measured_xyz is not None:
            measured_y = max(0.0, float(measured_xyz[1]))
        else:
            measured_y = max(0.0, float(row.get("Y", 0.0)) - black_level_y)
        weight = 2.0 if row_class == "gray_rgbw" else 1.0
        numerator += weight * (measured_y - predicted_rgb) * predicted_w
        denominator += weight * predicted_w * predicted_w
        pair_count += 1
        if row_class == "gray_rgbw":
            neutral_pair_count += 1

    if denominator <= 0.0:
        return 1.0, {
            "pair_count": 0,
            "neutral_pair_count": 0,
            "recommended_scale": 1.0,
        }

    recommended = numerator / denominator
    recommended = max(0.25, min(1.0, float(recommended)))
    return recommended, {
        "pair_count": int(pair_count),
        "neutral_pair_count": int(neutral_pair_count),
        "recommended_scale": float(recommended),
    }


def build_true16_calibration_qa(
    measurements,
    luts,
    summary,
    measured_model_luts=None,
    neutral_tolerance_q16=2048,
    black_level_y=0.0,
    ambient_profile=None,
):
    grouped_abs = defaultdict(list)
    grouped_signed = defaultdict(list)
    grouped_xy = defaultdict(list)
    grouped_sat_ratio = defaultdict(list)
    grouped_sat_deficit = defaultdict(list)
    worst_over = []
    worst_under = []
    black_level_y = max(0.0, float(black_level_y))
    channel_xy_basis = None
    if measured_model_luts is not None:
        channel_xy_basis = _estimate_true16_channel_xy_basis(measurements, ambient_profile=ambient_profile)

    for row in measurements:
        row_class = _classify_true16_patch(row, neutral_tolerance_q16=neutral_tolerance_q16)
        if row_class == "black":
            continue

        corrected_inputs = {
            ch: (_lut_value_q16(int(row.get(f"{ch.lower()}16", 0)), luts.get(ch, [])) if int(row.get(f"{ch.lower()}16", 0)) > 0 else 0)
            for ch in CHANNELS
        }
        if measured_model_luts is not None:
            predicted_y = 0.0
            for ch in CHANNELS:
                predicted_y += _lut_output_y(ch, corrected_inputs[ch], measured_model_luts, summary)
        else:
            predicted_y = 0.0
            for ch in CHANNELS:
                predicted_y += _lut_output_y(ch, int(row.get(f"{ch.lower()}16", 0)), luts, summary)

        active = _true16_active_channels(row)
        channel_hint = active[0][0] if len(active) == 1 else None
        measured_xyz = _measurement_row_xyz(row, ambient_profile=ambient_profile, channel_hint=channel_hint)
        if measured_xyz is not None:
            measured_y = max(0.0, float(measured_xyz[1]))
        else:
            measured_y = max(0.0, float(row.get("Y", 0.0)) - black_level_y)

        signed_error = predicted_y - measured_y
        abs_error = abs(signed_error)

        grouped_abs[row_class].append(abs_error)
        grouped_signed[row_class].append(signed_error)
        grouped_abs["overall"].append(abs_error)
        grouped_signed["overall"].append(signed_error)

        named_groups = _true16_named_patch_groups(row)
        for group_name in named_groups:
            grouped_abs[group_name].append(abs_error)
            grouped_signed[group_name].append(signed_error)

        if measured_model_luts is not None and measured_xyz is not None and channel_xy_basis is not None and named_groups:
            predicted_xyz = _predict_true16_xyz_from_model_inputs(corrected_inputs, measured_model_luts, summary, channel_xy_basis)
            measured_xy = _xyz_to_xy(measured_xyz[0], measured_xyz[1], measured_xyz[2])
            predicted_xy = _xyz_to_xy(predicted_xyz[0], predicted_xyz[1], predicted_xyz[2])
            if _is_valid_xy(measured_xy[0], measured_xy[1]) and _is_valid_xy(predicted_xy[0], predicted_xy[1]):
                xy_error = math.sqrt((float(predicted_xy[0]) - float(measured_xy[0])) ** 2 + (float(predicted_xy[1]) - float(measured_xy[1])) ** 2)
                measured_sat = math.sqrt((float(measured_xy[0]) - 0.3127) ** 2 + (float(measured_xy[1]) - 0.3290) ** 2)
                predicted_sat = math.sqrt((float(predicted_xy[0]) - 0.3127) ** 2 + (float(predicted_xy[1]) - 0.3290) ** 2)
                sat_ratio = (float(predicted_sat) / float(measured_sat)) if measured_sat > 1e-9 else 1.0
                sat_deficit = max(0.0, 1.0 - float(sat_ratio))
                for group_name in named_groups:
                    grouped_xy[group_name].append(float(xy_error))
                    grouped_sat_ratio[group_name].append(float(sat_ratio))
                    grouped_sat_deficit[group_name].append(float(sat_deficit))

        sample = {
            "file": row.get("file", ""),
            "name": row.get("name", ""),
            "class": row_class,
            "predicted_y": float(predicted_y),
            "measured_y": float(measured_y),
            "signed_error_y": float(signed_error),
            "abs_error_y": float(abs_error),
            "r16": int(row.get("r16", 0)),
            "g16": int(row.get("g16", 0)),
            "b16": int(row.get("b16", 0)),
            "w16": int(row.get("w16", 0)),
        }
        if signed_error >= 0.0:
            worst_over.append(sample)
        else:
            worst_under.append(sample)

    worst_over = sorted(worst_over, key=lambda item: item["signed_error_y"], reverse=True)[:12]
    worst_under = sorted(worst_under, key=lambda item: item["signed_error_y"])[:12]
    groups = {
        group: _summarize_error_series(grouped_abs[group], grouped_signed[group])
        for group in sorted(grouped_abs.keys())
    }
    for group_name in list(groups.keys()):
        _append_true16_chroma_metrics(
            groups[group_name],
            grouped_xy.get(group_name, []),
            grouped_sat_ratio.get(group_name, []),
            grouped_sat_deficit.get(group_name, []),
        )
    return {
        "groups": groups,
        "worst_overprediction": worst_over,
        "worst_underprediction": worst_under,
    }


def build_true16_transfer_aware_qa(
    measurements,
    calibration_luts,
    measured_model_luts,
    target_luts,
    summary,
    transfer_curve,
    neutral_tolerance_q16=2048,
    ambient_profile=None,
):
    if not transfer_curve:
        return None

    grouped_abs = defaultdict(list)
    grouped_signed = defaultdict(list)
    grouped_xy = defaultdict(list)
    grouped_sat_ratio = defaultdict(list)
    grouped_sat_deficit = defaultdict(list)
    named_counts = defaultdict(int)
    worst_over = []
    worst_under = []
    channel_basis = _estimate_true16_channel_xy_basis(measurements, ambient_profile=ambient_profile)

    for row in measurements:
        row_class = _classify_true16_patch(row, neutral_tolerance_q16=neutral_tolerance_q16)
        if row_class == "black":
            continue

        requested_inputs = {ch: _clamp_u16(int(row.get(f"{ch.lower()}16", 0))) for ch in CHANNELS}
        transferred_inputs = _apply_transfer_curve_inputs_q16(requested_inputs, transfer_curve)
        predicted_xyz, corrected_inputs = _predict_true16_xyz_after_calibration_from_inputs(
            transferred_inputs,
            calibration_luts,
            measured_model_luts,
            summary,
            channel_basis,
        )
        target_xyz = _predict_true16_target_xyz_from_inputs(
            transferred_inputs,
            target_luts,
            summary,
            channel_basis,
        )

        predicted_y = float(predicted_xyz[1]) if predicted_xyz is not None else 0.0
        target_y = float(target_xyz[1]) if target_xyz is not None else 0.0
        signed_error = predicted_y - target_y
        abs_error = abs(signed_error)

        grouped_abs[row_class].append(abs_error)
        grouped_signed[row_class].append(signed_error)
        grouped_abs["overall"].append(abs_error)
        grouped_signed["overall"].append(signed_error)

        named_groups = _true16_named_patch_groups(row)
        for group_name in set(named_groups):
            named_counts[group_name] += 1
        for group_name in named_groups:
            grouped_abs[group_name].append(abs_error)
            grouped_signed[group_name].append(signed_error)

        target_xy = _xyz_to_xy(target_xyz[0], target_xyz[1], target_xyz[2]) if target_xyz is not None else (None, None)
        predicted_xy = _xyz_to_xy(predicted_xyz[0], predicted_xyz[1], predicted_xyz[2]) if predicted_xyz is not None else (None, None)
        if _is_valid_xy(target_xy[0], target_xy[1]) and _is_valid_xy(predicted_xy[0], predicted_xy[1]):
            xy_error = math.sqrt((float(predicted_xy[0]) - float(target_xy[0])) ** 2 + (float(predicted_xy[1]) - float(target_xy[1])) ** 2)
            target_sat = math.sqrt((float(target_xy[0]) - 0.3127) ** 2 + (float(target_xy[1]) - 0.3290) ** 2)
            predicted_sat = math.sqrt((float(predicted_xy[0]) - 0.3127) ** 2 + (float(predicted_xy[1]) - 0.3290) ** 2)
            sat_ratio = (float(predicted_sat) / float(target_sat)) if target_sat > 1e-9 else 1.0
            sat_deficit = max(0.0, 1.0 - float(sat_ratio))

            grouped_xy[row_class].append(float(xy_error))
            grouped_sat_ratio[row_class].append(float(sat_ratio))
            grouped_sat_deficit[row_class].append(float(sat_deficit))
            grouped_xy["overall"].append(float(xy_error))
            grouped_sat_ratio["overall"].append(float(sat_ratio))
            grouped_sat_deficit["overall"].append(float(sat_deficit))
            for group_name in named_groups:
                grouped_xy[group_name].append(float(xy_error))
                grouped_sat_ratio[group_name].append(float(sat_ratio))
                grouped_sat_deficit[group_name].append(float(sat_deficit))

        sample = {
            "file": row.get("file", ""),
            "name": row.get("name", ""),
            "class": row_class,
            "target_y": float(target_y),
            "predicted_y": float(predicted_y),
            "signed_error_y": float(signed_error),
            "abs_error_y": float(abs_error),
            "r16": int(row.get("r16", 0)),
            "g16": int(row.get("g16", 0)),
            "b16": int(row.get("b16", 0)),
            "w16": int(row.get("w16", 0)),
            "transfer_r16": int(transferred_inputs.get("R", 0)),
            "transfer_g16": int(transferred_inputs.get("G", 0)),
            "transfer_b16": int(transferred_inputs.get("B", 0)),
            "transfer_w16": int(transferred_inputs.get("W", 0)),
            "corrected_r16": int(corrected_inputs.get("R", 0)),
            "corrected_g16": int(corrected_inputs.get("G", 0)),
            "corrected_b16": int(corrected_inputs.get("B", 0)),
            "corrected_w16": int(corrected_inputs.get("W", 0)),
        }
        if signed_error >= 0.0:
            worst_over.append(sample)
        else:
            worst_under.append(sample)

    worst_over = sorted(worst_over, key=lambda item: item["signed_error_y"], reverse=True)[:12]
    worst_under = sorted(worst_under, key=lambda item: item["signed_error_y"])[:12]
    groups = {
        group: _summarize_error_series(grouped_abs[group], grouped_signed[group])
        for group in sorted(grouped_abs.keys())
    }
    for group_name in list(groups.keys()):
        _append_true16_chroma_metrics(
            groups[group_name],
            grouped_xy.get(group_name, []),
            grouped_sat_ratio.get(group_name, []),
            grouped_sat_deficit.get(group_name, []),
        )

    return {
        "groups": groups,
        "worst_overprediction": worst_over,
        "worst_underprediction": worst_under,
    }


def _is_valid_xy(x, y):
        if x is None or y is None:
                return False
        try:
                xf = float(x)
                yf = float(y)
        except Exception:
                return False
        return xf >= 0.0 and yf > 1e-9 and (xf + yf) < 1.0


def _xyy_to_xyz(x, y, luma_y):
        if not _is_valid_xy(x, y):
                return None
        xf = float(x)
        yf = float(y)
        Y = max(0.0, float(luma_y))
        X = (xf / yf) * Y
        Z = ((1.0 - xf - yf) / yf) * Y
        return (float(X), float(Y), float(Z))


def _xyz_to_xy(X, Y, Z):
        total = float(X) + float(Y) + float(Z)
        if total <= 1e-12:
                return (None, None)
        return (float(X) / total, float(Y) / total)


def _srgb_encode(linear):
        v = max(0.0, float(linear))
        if v <= 0.0031308:
                return 12.92 * v
        return 1.055 * (v ** (1.0 / 2.4)) - 0.055


def _xyz_to_srgb8(X, Y, Z, white_luma=1.0):
        scale = max(1e-9, float(white_luma))
        xn = float(X) / scale
        yn = float(Y) / scale
        zn = float(Z) / scale

        r_lin = 3.2406 * xn - 1.5372 * yn - 0.4986 * zn
        g_lin = -0.9689 * xn + 1.8758 * yn + 0.0415 * zn
        b_lin = 0.0557 * xn - 0.2040 * yn + 1.0570 * zn

        r = _clamp01(_srgb_encode(r_lin))
        g = _clamp01(_srgb_encode(g_lin))
        b = _clamp01(_srgb_encode(b_lin))
        return (
                int(round(r * 255.0)),
                int(round(g * 255.0)),
                int(round(b * 255.0)),
        )


def _rgb_hex(rgb):
        r, g, b = rgb
        return f"#{int(r):02X}{int(g):02X}{int(b):02X}"


def _fmt(value, digits=4):
    if value is None:
        return "n/a"
    return f"{float(value):.{int(digits)}f}"


def _describe_xyz_color(xyz, reference_luma):
    if xyz is None:
        return {
            "hex": "#303030",
            "rgb_text": "n/a",
            "xyz_text": "n/a",
            "xy_text": "n/a",
            "swatch_class": "swatch swatch-missing",
        }

    rgb = _xyz_to_srgb8(xyz[0], xyz[1], xyz[2], white_luma=reference_luma)
    rgb_hex = _rgb_hex(rgb)
    xy = _xyz_to_xy(xyz[0], xyz[1], xyz[2])
    return {
        "hex": rgb_hex,
        "rgb_text": f"{rgb[0]}/{rgb[1]}/{rgb[2]} {rgb_hex}",
        "xyz_text": f"{_fmt(xyz[0], digits=3)}/{_fmt(xyz[1], digits=3)}/{_fmt(xyz[2], digits=3)}",
        "xy_text": f"{_fmt(xy[0], digits=4)}/{_fmt(xy[1], digits=4)}",
        "swatch_class": "swatch",
    }


def _render_truncated_cell(value, cell_class):
    safe = html.escape(str(value))
    return f"<td class=\"{cell_class}\"><span class=\"cell-cut\" title=\"{safe}\">{safe}</span></td>"


def _render_report_color_cell(desc):
    tooltip = html.escape(f"RGB {desc['rgb_text']} | XYZ {desc['xyz_text']} | xy {desc['xy_text']}")
    return (
        "<td class=\"color-cell\">"
        f"<div class=\"{desc['swatch_class']}\" style=\"--swatch:{desc['hex']};\" title=\"{tooltip}\"></div>"
        f"<div class=\"metric mono compact\">RGB {html.escape(desc['rgb_text'])}</div>"
        f"<div class=\"metric mono compact\">XYZ {html.escape(desc['xyz_text'])}</div>"
        f"<div class=\"metric mono compact\">xy {html.escape(desc['xy_text'])}</div>"
        "</td>"
    )


def _build_calibration_color_report_html(
    title,
    generated_utc,
    header_label,
    row_count,
    profile_target,
    reference_luma,
    class_options_html,
    table_header_html,
    rows_html,
    tip_text,
    normalization_subject="displayed/measured/post-calibrated",
    transfer_header_label=None,
):
    html_text = """<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>__TITLE__</title>
<style>
:root {
  --bg0: #f4efe7;
  --bg1: #dce8e4;
  --card: #ffffffd9;
  --ink: #1e2a2f;
  --muted: #5d6b71;
  --line: #c9d5d6;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Aptos", "Trebuchet MS", "Segoe UI", sans-serif;
  color: var(--ink);
  background:
    radial-gradient(1200px 700px at 10% -10%, #f7d7b8 0%, transparent 65%),
    radial-gradient(1000px 700px at 100% 0%, #c8e7df 0%, transparent 62%),
    linear-gradient(180deg, var(--bg0), var(--bg1));
  min-height: 100vh;
}
.wrap {
    max-width: 1760px;
  margin: 0 auto;
  padding: 18px;
}
.hero {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 16px;
  backdrop-filter: blur(4px);
  box-shadow: 0 10px 30px #0f22310f;
}
h1 {
  margin: 0 0 8px;
  font-family: "Bahnschrift", "Aptos", sans-serif;
  letter-spacing: 0.02em;
  font-size: 1.32rem;
}
.meta {
  color: var(--muted);
  font-size: 0.92rem;
  line-height: 1.35;
}
.meta strong { color: var(--ink); }
.controls {
  display: grid;
  grid-template-columns: 1fr 220px;
  gap: 10px;
  margin-top: 12px;
}
input, select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 9px 10px;
  font: inherit;
  background: #fffffff0;
}
.table-wrap {
  margin-top: 14px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  overflow: auto;
  scrollbar-gutter: stable both-edges;
  box-shadow: 0 10px 30px #0f22310f;
}
.table-pad {
  min-width: max-content;
    padding-right: 24px;
    padding-left: 4px;
  padding-bottom: 12px;
}
table {
  width: max-content;
  min-width: 1400px;
  border-collapse: collapse;
}
th, td {
  padding: 7px 8px;
  border-bottom: 1px solid #e4ecec;
  vertical-align: top;
  font-size: 0.8rem;
  white-space: nowrap;
}
th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: linear-gradient(180deg, #eff7f6, #e8f2f0);
  text-align: left;
  font-family: "Bahnschrift", "Aptos", sans-serif;
  color: #264047;
}
tr:hover td {
  background: #f4f9f8;
}
tbody tr:last-child td {
  border-bottom: 0;
}
.mono {
  font-family: "Consolas", "Cascadia Mono", monospace;
}
.metric {
  color: #22363b;
  line-height: 1.28;
}
.compact {
  font-size: 0.74rem;
  line-height: 1.2;
}
.cell-cut {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.c-file { width: 210px; }
.c-patch { width: 170px; }
.c-class { width: 105px; }
.c-code { width: 136px; }
.c-file .cell-cut { width: 210px; }
.c-patch .cell-cut { width: 170px; }
.c-class .cell-cut { width: 105px; }
.color-cell {
  min-width: 196px;
  max-width: 220px;
}
.swatch {
  width: 100%;
  max-width: none;
  height: 24px;
  margin-bottom: 4px;
  border-radius: 8px;
  border: 1px solid #00000033;
  background: var(--swatch);
  box-shadow: inset 0 0 0 1px #ffffff33;
}
.swatch-missing {
  background:
    linear-gradient(45deg, #727272 25%, #5d5d5d 25%, #5d5d5d 50%, #727272 50%, #727272 75%, #5d5d5d 75%, #5d5d5d 100%);
  background-size: 14px 14px;
}
.foot {
  margin-top: 10px;
  color: var(--muted);
  font-size: 0.82rem;
}
@media (max-width: 980px) {
  .controls { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<div class=\"wrap\">
  <section class=\"hero\">
    <h1>__TITLE__</h1>
    <div class=\"meta\">
      <div><strong>Generated:</strong> __GENERATED__</div>
      <div><strong>Calibration header:</strong> __HEADER_PATH__</div>
    __TRANSFER_META__
      <div><strong>Capture rows:</strong> __ROW_COUNT__ | <strong>Profile target:</strong> __PROFILE_TARGET__ | <strong>Display normalization Y:</strong> __REF_LUMA__</div>
    <div>Swatches are rendered from XYZ -> sRGB and normalized by the brightest __NORMALIZATION_SUBJECT__ Y in this report.</div>
            <div>Each color column includes RGB, XYZ, and xy values directly under the swatch.</div>
    </div>
    <div class=\"controls\">
      <input id=\"nameFilter\" type=\"text\" placeholder=\"Filter by file, patch name, class, or code text...\">
      <select id=\"classFilter\">__CLASS_OPTIONS__</select>
    </div>
  </section>

  <div class=\"table-wrap\">
    <div class=\"table-pad\">
      <table id=\"rowsTable\">
        <thead>
          <tr>__TABLE_HEADERS__</tr>
        </thead>
        <tbody>
          __ROWS__
        </tbody>
      </table>
    </div>
  </div>

  <div class=\"foot\">__TIP__</div>
</div>

<script>
(function () {
  const nameFilter = document.getElementById('nameFilter');
  const classFilter = document.getElementById('classFilter');
  const table = document.getElementById('rowsTable');
  const rows = Array.from(table.querySelectorAll('tbody tr'));

  function applyFilters() {
    const needle = (nameFilter.value || '').toLowerCase().trim();
    const selectedClass = classFilter.value;
    for (const row of rows) {
      const hay = row.textContent.toLowerCase();
      const rowClass = row.getAttribute('data-class') || '';
      const classOk = selectedClass === 'all' || rowClass === selectedClass;
      const textOk = !needle || hay.includes(needle);
      row.style.display = classOk && textOk ? '' : 'none';
    }
  }

  nameFilter.addEventListener('input', applyFilters);
  classFilter.addEventListener('change', applyFilters);
})();
</script>
</body>
</html>
"""

    html_text = html_text.replace("__TITLE__", html.escape(str(title)))
    html_text = html_text.replace("__GENERATED__", html.escape(str(generated_utc)))
    html_text = html_text.replace("__HEADER_PATH__", html.escape(str(header_label)))
    transfer_meta = ""
    if transfer_header_label:
        transfer_meta = f"<div><strong>Transfer header:</strong> {html.escape(str(transfer_header_label))}</div>"
    html_text = html_text.replace("__TRANSFER_META__", transfer_meta)
    html_text = html_text.replace("__ROW_COUNT__", str(int(row_count)))
    html_text = html_text.replace("__PROFILE_TARGET__", html.escape(str(profile_target)))
    html_text = html_text.replace("__REF_LUMA__", html.escape(_fmt(reference_luma, digits=5)))
    html_text = html_text.replace("__NORMALIZATION_SUBJECT__", html.escape(str(normalization_subject)))
    html_text = html_text.replace("__CLASS_OPTIONS__", str(class_options_html))
    html_text = html_text.replace("__TABLE_HEADERS__", str(table_header_html))
    html_text = html_text.replace("__ROWS__", str(rows_html))
    html_text = html_text.replace("__TIP__", html.escape(str(tip_text)))
    return html_text


def _active_channels_8bit(row):
    return [(ch, int(row.get(ch.lower(), 0))) for ch in CHANNELS if int(row.get(ch.lower(), 0)) > 0]


def _classify_8bit_patch(row, neutral_tolerance_code=8):
    vals = {ch: int(row.get(ch.lower(), 0)) for ch in CHANNELS}
    active = [(ch, vals[ch]) for ch in CHANNELS if vals[ch] > 0]
    if not active:
        return "black"
    if len(active) == 1:
        return "single"

    rgb_vals = [vals[ch] for ch in ("R", "G", "B") if vals[ch] > 0]
    has_w = vals["W"] > 0
    if len(rgb_vals) == 3 and (max(rgb_vals) - min(rgb_vals)) <= int(neutral_tolerance_code):
        return "gray_rgbw" if has_w else "gray_rgb"
    if has_w:
        return "mixed_with_w"
    return "mixed_rgb"


def _estimate_8bit_channel_xy_basis(measurements, high_signal_fraction=0.2):
    fallback = {
        "R": (0.6400, 0.3300),
        "G": (0.3000, 0.6000),
        "B": (0.1500, 0.0600),
        "W": (0.3127, 0.3290),
    }
    per_channel = {ch: [] for ch in CHANNELS}
    for row in measurements:
        active = _active_channels_8bit(row)
        if len(active) != 1:
            continue
        ch_name, _input_code = active[0]
        x = row.get("x")
        y = row.get("y")
        if not _is_valid_xy(x, y):
            continue
        y_luma = max(0.0, float(row.get("Y", 0.0)))
        per_channel[ch_name].append((y_luma, float(x), float(y)))

    out = {}
    for ch in CHANNELS:
        samples = per_channel[ch]
        if not samples:
            out[ch] = {
                "x": float(fallback[ch][0]),
                "y": float(fallback[ch][1]),
                "source": "fallback",
                "sample_count": 0,
            }
            continue

        max_y = max((s[0] for s in samples), default=0.0)
        threshold = max_y * max(0.0, min(1.0, float(high_signal_fraction)))
        strong = [s for s in samples if s[0] >= threshold]
        use = strong if strong else samples

        weight_sum = sum(max(1e-6, s[0]) for s in use)
        if weight_sum <= 0.0:
            out[ch] = {
                "x": float(fallback[ch][0]),
                "y": float(fallback[ch][1]),
                "source": "fallback",
                "sample_count": int(len(use)),
            }
            continue

        x_avg = sum(float(s[1]) * max(1e-6, s[0]) for s in use) / weight_sum
        y_avg = sum(float(s[2]) * max(1e-6, s[0]) for s in use) / weight_sum
        if not _is_valid_xy(x_avg, y_avg):
            x_avg, y_avg = fallback[ch]
            source = "fallback"
        else:
            source = "measured"
        out[ch] = {
            "x": float(x_avg),
            "y": float(y_avg),
            "source": source,
            "sample_count": int(len(use)),
        }
    return out


def _clamp_u8(value):
    return max(0, min(255, int(value)))


def _lut_output_y_8bit(channel, input_code, bfi, per_bfi_tables, summary):
    table = per_bfi_tables.get(channel, {}).get(int(bfi))
    if table is None:
        table = per_bfi_tables.get(channel, {}).get(0)
    if not table:
        return 0.0

    max_y = float(summary.get(channel, {}).get("max_y") or 0.0)
    if max_y <= 0.0:
        return 0.0
    idx = _clamp_u8(input_code)
    return (float(_clamp_u16(table[idx])) / 65535.0) * max_y


def _predict_8bit_row_xyz(row, profile_tables, per_bfi_tables, summary, channel_xy_basis, apply_calibration=False):
    model_codes = {}
    total_X = 0.0
    total_Y = 0.0
    total_Z = 0.0

    for ch in CHANNELS:
        requested_code = _clamp_u8(int(row.get(ch.lower(), 0)))
        model_code = requested_code
        if apply_calibration:
            table = profile_tables.get(ch, [])
            if table:
                corrected_q16 = _clamp_u16(table[requested_code])
                model_code = _clamp_u8(int(round(float(corrected_q16) / 257.0)))
        model_codes[ch] = int(model_code)

        bfi = int(row.get(f"bfi_{ch.lower()}", 0))
        channel_luma = _lut_output_y_8bit(ch, model_code, bfi, per_bfi_tables, summary)
        basis = channel_xy_basis.get(ch, {"x": 0.3127, "y": 0.3290})
        channel_xyz = _xyy_to_xyz(basis.get("x"), basis.get("y"), channel_luma)
        if channel_xyz is None:
            continue
        total_X += float(channel_xyz[0])
        total_Y += float(channel_xyz[1])
        total_Z += float(channel_xyz[2])

    return (float(total_X), float(total_Y), float(total_Z)), model_codes


def _resolve_8bit_web_report_path(out_path: Path, web_report_out: Path | None):
    if web_report_out is not None:
        return Path(web_report_out)
    return out_path.with_name(f"{out_path.stem}_web_report.html")


def export_8bit_calibration_web_report(
    out_path: Path,
    measurements,
    profile_tables,
    per_bfi_tables,
    summary,
    raw_per_bfi_tables=None,
    calibration_header_path: Path | None = None,
):
    rows = []
    max_luma = 0.0
    channel_basis = _estimate_8bit_channel_xy_basis(measurements)
    pre_cal_tables = raw_per_bfi_tables if raw_per_bfi_tables is not None else per_bfi_tables

    for idx, row in enumerate(measurements, start=1):
        measured_xyz = _measurement_row_xyz(row)
        displayed_xyz, _displayed_model_codes = _predict_8bit_row_xyz(
            row,
            profile_tables,
            pre_cal_tables,
            summary,
            channel_basis,
            apply_calibration=False,
        )
        calibrated_xyz, calibrated_model_codes = _predict_8bit_row_xyz(
            row,
            profile_tables,
            per_bfi_tables,
            summary,
            channel_basis,
            apply_calibration=True,
        )

        measured_y = measured_xyz[1] if measured_xyz is not None else 0.0
        max_luma = max(max_luma, float(displayed_xyz[1]), float(calibrated_xyz[1]), float(measured_y))

        rows.append(
            {
                "index": int(idx),
                "file": str(row.get("file", "")),
                "name": str(row.get("name", "")),
                "class": _classify_8bit_patch(row),
                "requested": {ch: _clamp_u8(row.get(ch.lower(), 0)) for ch in CHANNELS},
                "bfi": {ch: int(row.get(f"bfi_{ch.lower()}", 0)) for ch in CHANNELS},
                "calibrated_codes": calibrated_model_codes,
                "displayed_xyz": displayed_xyz,
                "measured_xyz": measured_xyz,
                "calibrated_xyz": calibrated_xyz,
            }
        )

    reference_luma = max(1e-6, max_luma)
    row_html = []
    for row in rows:
        displayed_desc = _describe_xyz_color(row["displayed_xyz"], reference_luma)
        measured_desc = _describe_xyz_color(row["measured_xyz"], reference_luma)
        calibrated_desc = _describe_xyz_color(row["calibrated_xyz"], reference_luma)

        requested_txt = "/".join(str(row["requested"][ch]) for ch in CHANNELS)
        bfi_txt = "/".join(str(row["bfi"][ch]) for ch in CHANNELS)
        calibrated_txt = "/".join(str(row["calibrated_codes"][ch]) for ch in CHANNELS)

        row_html.append(
            "".join(
                [
                    f"<tr data-class=\"{html.escape(row['class'])}\">",
                    f"<td>{row['index']}</td>",
                    _render_truncated_cell(row["file"], "c-file"),
                    _render_truncated_cell(row["name"], "c-patch"),
                    _render_truncated_cell(row["class"], "c-class"),
                    f"<td class=\"mono c-code\">{html.escape(requested_txt)}</td>",
                    f"<td class=\"mono c-code\">{html.escape(bfi_txt)}</td>",
                    f"<td class=\"mono c-code\">{html.escape(calibrated_txt)}</td>",
                    _render_report_color_cell(displayed_desc),
                    _render_report_color_cell(measured_desc),
                    _render_report_color_cell(calibrated_desc),
                    "</tr>",
                ]
            )
        )

    classes = sorted({row["class"] for row in rows})
    class_options = ["<option value=\"all\">all</option>"]
    for row_class in classes:
        class_options.append(f"<option value=\"{html.escape(row_class)}\">{html.escape(row_class)}</option>")

    global_summary = summary.get("_global", {})
    profile_target = str(global_summary.get("profile_target", "linear"))
    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    header_label = str(calibration_header_path) if calibration_header_path is not None else "n/a"
    table_header_html = "".join(
        [
            "<th>#</th>",
            "<th class=\"c-file\">File</th>",
            "<th class=\"c-patch\">Patch</th>",
            "<th class=\"c-class\">Class</th>",
            "<th class=\"c-code\">Req 8b R/G/B/W</th>",
            "<th class=\"c-code\">BFI R/G/B/W</th>",
            "<th class=\"c-code\">Cal 8b R/G/B/W</th>",
            "<th class=\"color-cell\">Displayed</th>",
            "<th class=\"color-cell\">Measured</th>",
            "<th class=\"color-cell\">Post-Cal</th>",
        ]
    )

    html_doc = _build_calibration_color_report_html(
        title="8-bit Calibration Color Sanity Report",
        generated_utc=generated_utc,
        header_label=header_label,
        row_count=len(rows),
        profile_target=profile_target,
        reference_luma=reference_luma,
        class_options_html="".join(class_options),
        table_header_html=table_header_html,
        rows_html="\n".join(row_html),
        tip_text="Use displayed/measured/post-cal swatches to quickly sanity-check changes before flashing.",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")


def _estimate_true16_channel_xy_basis(measurements, high_signal_fraction=0.2, ambient_profile=None):
    fallback = {
        "R": (0.6400, 0.3300),
        "G": (0.3000, 0.6000),
        "B": (0.1500, 0.0600),
        "W": (0.3127, 0.3290),
    }
    per_channel = {ch: [] for ch in CHANNELS}
    for row in measurements:
        active = _true16_active_channels(row)
        if len(active) != 1:
            continue
        ch_name, _input_q16 = active[0]

        compensated_xyz = _measurement_row_xyz(row, ambient_profile=ambient_profile, channel_hint=ch_name)
        if compensated_xyz is None:
            continue

        x, y = _xyz_to_xy(compensated_xyz[0], compensated_xyz[1], compensated_xyz[2])
        if not _is_valid_xy(x, y):
            continue

        y_luma = max(0.0, float(compensated_xyz[1]))
        per_channel[ch_name].append((y_luma, float(x), float(y)))

    out = {}
    for ch in CHANNELS:
        samples = per_channel[ch]
        if not samples:
            out[ch] = {
                "x": float(fallback[ch][0]),
                "y": float(fallback[ch][1]),
                "source": "fallback",
                "sample_count": 0,
            }
            continue

        max_y = max((s[0] for s in samples), default=0.0)
        threshold = max_y * max(0.0, min(1.0, float(high_signal_fraction)))
        strong = [s for s in samples if s[0] >= threshold]
        use = strong if strong else samples

        weight_sum = sum(max(1e-6, s[0]) for s in use)
        if weight_sum <= 0.0:
            out[ch] = {
                "x": float(fallback[ch][0]),
                "y": float(fallback[ch][1]),
                "source": "fallback",
                "sample_count": int(len(use)),
            }
            continue

        x_avg = sum(float(s[1]) * max(1e-6, s[0]) for s in use) / weight_sum
        y_avg = sum(float(s[2]) * max(1e-6, s[0]) for s in use) / weight_sum
        if not _is_valid_xy(x_avg, y_avg):
            x_avg, y_avg = fallback[ch]
            source = "fallback"
        else:
            source = "measured"
        out[ch] = {
            "x": float(x_avg),
            "y": float(y_avg),
            "source": source,
            "sample_count": int(len(use)),
        }
    return out

def _ambient_profile_y(ambient_profile, channel_hint=None, default=0.0):
    base = max(0.0, float(default or 0.0))
    if not ambient_profile:
        return base

    if channel_hint in CHANNELS:
        value = ambient_profile.get("per_channel", {}).get(channel_hint, {}).get("Y")
        if value is not None:
            return max(0.0, float(value))

    value = ambient_profile.get("global", {}).get("Y")
    if value is not None:
        return max(0.0, float(value))
    return base


def _ambient_profile_xyz(ambient_profile, channel_hint=None):
    if not ambient_profile:
        return None

    if channel_hint in CHANNELS:
        values = ambient_profile.get("per_channel", {}).get(channel_hint, {}).get("xyz")
        if isinstance(values, (list, tuple)) and len(values) == 3:
            return (
                max(0.0, float(values[0])),
                max(0.0, float(values[1])),
                max(0.0, float(values[2])),
            )

    values = ambient_profile.get("global", {}).get("xyz")
    if isinstance(values, (list, tuple)) and len(values) == 3:
        return (
            max(0.0, float(values[0])),
            max(0.0, float(values[1])),
            max(0.0, float(values[2])),
        )
    return None


def _measurement_row_xyz_with_ambient(row, ambient_profile=None, channel_hint=None):
    raw_xyz = _measurement_row_xyz_raw(row)
    if raw_xyz is None:
        return None

    ambient_xyz = _ambient_profile_xyz(ambient_profile, channel_hint=channel_hint)
    if ambient_xyz is not None:
        return (
            max(0.0, float(raw_xyz[0]) - float(ambient_xyz[0])),
            max(0.0, float(raw_xyz[1]) - float(ambient_xyz[1])),
            max(0.0, float(raw_xyz[2]) - float(ambient_xyz[2])),
        )

    ambient_y = _ambient_profile_y(ambient_profile, channel_hint=channel_hint, default=0.0)
    if ambient_y <= 0.0:
        return (float(raw_xyz[0]), float(raw_xyz[1]), float(raw_xyz[2]))

    raw_y = max(0.0, float(raw_xyz[1]))
    if raw_y <= 1e-12:
        return (0.0, 0.0, 0.0)

    signal_y = max(0.0, raw_y - ambient_y)
    scale = signal_y / raw_y if raw_y > 0.0 else 0.0
    return (
        max(0.0, float(raw_xyz[0]) * scale),
        max(0.0, float(signal_y)),
        max(0.0, float(raw_xyz[2]) * scale),
    )


def _measurement_row_xyz(row, ambient_profile=None, channel_hint=None):
    return _measurement_row_xyz_with_ambient(row, ambient_profile=ambient_profile, channel_hint=channel_hint)


def _predict_true16_xyz_from_model_inputs(model_inputs_q16, measured_model_luts, summary, channel_xy_basis):
    total_X = 0.0
    total_Y = 0.0
    total_Z = 0.0
    for ch in CHANNELS:
        input_q16 = _clamp_u16(int(model_inputs_q16.get(ch, 0)))
        channel_luma = _lut_output_y(ch, input_q16, measured_model_luts, summary)
        basis = channel_xy_basis.get(ch, {"x": 0.3127, "y": 0.3290})
        channel_xyz = _xyy_to_xyz(basis.get("x"), basis.get("y"), channel_luma)
        if channel_xyz is None:
            continue
        total_X += float(channel_xyz[0])
        total_Y += float(channel_xyz[1])
        total_Z += float(channel_xyz[2])
    return (float(total_X), float(total_Y), float(total_Z))


def _correct_true16_inputs(model_inputs_q16, calibration_luts):
    corrected_inputs = {}
    for ch in CHANNELS:
        requested_q16 = _clamp_u16(int(model_inputs_q16.get(ch, 0)))
        corrected_inputs[ch] = int(_lut_value_q16(requested_q16, calibration_luts.get(ch, []))) if requested_q16 > 0 else 0
    return corrected_inputs


def _predict_true16_xyz_after_calibration_from_inputs(model_inputs_q16, calibration_luts, measured_model_luts, summary, channel_xy_basis):
    corrected_inputs = _correct_true16_inputs(model_inputs_q16, calibration_luts)
    xyz = _predict_true16_xyz_from_model_inputs(corrected_inputs, measured_model_luts, summary, channel_xy_basis)
    return xyz, corrected_inputs


def _predict_true16_target_xyz_from_inputs(model_inputs_q16, target_luts, summary, channel_xy_basis):
    total_X = 0.0
    total_Y = 0.0
    total_Z = 0.0
    for ch in CHANNELS:
        input_q16 = _clamp_u16(int(model_inputs_q16.get(ch, 0)))
        target_q16 = _lut_value_q16(input_q16, target_luts.get(ch, [])) if input_q16 > 0 else 0
        max_y = float(summary.get(ch, {}).get("max_y") or 0.0)
        if max_y <= 0.0:
            continue
        channel_luma = (float(target_q16) / 65535.0) * max_y
        basis = channel_xy_basis.get(ch, {"x": 0.3127, "y": 0.3290})
        channel_xyz = _xyy_to_xyz(basis.get("x"), basis.get("y"), channel_luma)
        if channel_xyz is None:
            continue
        total_X += float(channel_xyz[0])
        total_Y += float(channel_xyz[1])
        total_Z += float(channel_xyz[2])
    return (float(total_X), float(total_Y), float(total_Z))


def _predict_true16_row_xyz_after_calibration(row, calibration_luts, measured_model_luts, summary, channel_xy_basis):
    requested_inputs = {ch: _clamp_u16(int(row.get(f"{ch.lower()}16", 0))) for ch in CHANNELS}
    return _predict_true16_xyz_after_calibration_from_inputs(
        requested_inputs,
        calibration_luts,
        measured_model_luts,
        summary,
        channel_xy_basis,
    )


def _parse_transfer_curve_header_text(header_text, source_label="header"):
    bucket_match = re.search(r"static const uint16_t BUCKET_COUNT\s*=\s*(\d+)\s*;", header_text)
    bucket_count = int(bucket_match.group(1)) if bucket_match else None

    tables = {}
    lower_tables = {}
    upper_tables = {}
    for ch in CHANNELS:
        array_match = re.search(
            rf"static const uint16_t TARGET_{ch}\[(\d+)\]\s*=\s*\{{(.*?)\}};",
            header_text,
            re.S,
        )
        if not array_match:
            raise ValueError(f"Missing TARGET_{ch} array in transfer curve header")

        array_len = int(array_match.group(1))
        values = [int(v) for v in re.findall(r"\d+", array_match.group(2))]
        if len(values) != array_len:
            raise ValueError(f"TARGET_{ch} length mismatch: expected {array_len}, found {len(values)}")

        if bucket_count is None:
            bucket_count = int(array_len)
        elif int(array_len) != int(bucket_count):
            raise ValueError(f"TARGET_{ch} length {array_len} does not match BUCKET_COUNT {bucket_count}")

        tables[ch] = [int(_clamp_u16(v)) for v in values]

        lower_match = re.search(
            rf"static const uint8_t LOWER_{ch}\[(\d+)\]\s*=\s*\{{(.*?)\}};",
            header_text,
            re.S,
        )
        if lower_match:
            lower_values = [int(v) for v in re.findall(r"\d+", lower_match.group(2))]
            if len(lower_values) != int(lower_match.group(1)):
                raise ValueError(f"LOWER_{ch} length mismatch")
            lower_tables[ch] = [max(0, min(255, int(v))) for v in lower_values]

        upper_match = re.search(
            rf"static const uint8_t UPPER_{ch}\[(\d+)\]\s*=\s*\{{(.*?)\}};",
            header_text,
            re.S,
        )
        if upper_match:
            upper_values = [int(v) for v in re.findall(r"\d+", upper_match.group(2))]
            if len(upper_values) != int(upper_match.group(1)):
                raise ValueError(f"UPPER_{ch} length mismatch")
            upper_tables[ch] = [max(0, min(255, int(v))) for v in upper_values]

    return {
        "enabled": True,
        "source": str(source_label),
        "bucket_count": int(bucket_count or 0),
        "tables": tables,
        "lower_tables": lower_tables,
        "upper_tables": upper_tables,
    }


def load_transfer_curve_header(path: Path):
    path = Path(path)
    header_text = path.read_text(encoding="utf-8", errors="ignore")
    model = _parse_transfer_curve_header_text(header_text, source_label=str(path))
    model["header_path"] = str(path)
    return model


def _transfer_curve_value_q16(input_q16, transfer_curve, channel):
    if not transfer_curve:
        return _clamp_u16(input_q16)
    tables = transfer_curve.get("tables", {}) if isinstance(transfer_curve, dict) else {}
    table = tables.get(channel)
    if not table:
        return _clamp_u16(input_q16)
    return int(_lut_value_q16(input_q16, table))


def _apply_transfer_curve_inputs_q16(model_inputs_q16, transfer_curve):
    return {
        ch: _transfer_curve_value_q16(int(model_inputs_q16.get(ch, 0)), transfer_curve, ch)
        for ch in CHANNELS
    }


def _resolve_true16_web_report_path(out_path: Path, web_report_out: Path | None):
    if web_report_out is not None:
        return Path(web_report_out)
    return out_path.with_name(f"{out_path.stem}_web_report.html")


def export_true16_calibration_web_report(out_path: Path, artifacts, calibration_header_path: Path | None = None):
    measurements = list(artifacts.get("measurements", []))
    calibration_luts = artifacts.get("luts", {})
    measured_model_luts = artifacts.get("measured_model_luts", {})
    summary = artifacts.get("summary", {})
    transfer_curve_model = artifacts.get("transfer_curve_model")
    settings = artifacts.get("settings", {})
    neutral_tol = int(settings.get("neutral_tolerance_q16", 2048))
    ambient_profile = artifacts.get("ambient_profile")
    if ambient_profile is None:
        ambient_profile = summary.get("_global", {}).get("ambient_profile")

    channel_basis = _estimate_true16_channel_xy_basis(measurements, ambient_profile=ambient_profile)
    rows = []
    max_luma = 0.0

    for idx, row in enumerate(measurements, start=1):
        requested_inputs = {ch: _clamp_u16(int(row.get(f"{ch.lower()}16", 0))) for ch in CHANNELS}
        displayed_xyz = _predict_true16_xyz_from_model_inputs(requested_inputs, measured_model_luts, summary, channel_basis)
        active = _true16_active_channels(row)
        channel_hint = active[0][0] if len(active) == 1 else None
        measured_xyz = _measurement_row_xyz(row, ambient_profile=ambient_profile, channel_hint=channel_hint)
        calibrated_xyz, corrected_inputs = _predict_true16_row_xyz_after_calibration(
            row,
            calibration_luts,
            measured_model_luts,
            summary,
            channel_basis,
        )
        transferred_inputs = None
        transfer_corrected_inputs = None
        transfer_calibrated_xyz = None
        if transfer_curve_model:
            transferred_inputs = _apply_transfer_curve_inputs_q16(requested_inputs, transfer_curve_model)
            transfer_calibrated_xyz, transfer_corrected_inputs = _predict_true16_xyz_after_calibration_from_inputs(
                transferred_inputs,
                calibration_luts,
                measured_model_luts,
                summary,
                channel_basis,
            )

        measured_y = measured_xyz[1] if measured_xyz is not None else 0.0
        max_luma = max(max_luma, float(displayed_xyz[1]), float(calibrated_xyz[1]), float(measured_y))
        if transfer_calibrated_xyz is not None:
            max_luma = max(max_luma, float(transfer_calibrated_xyz[1]))

        rows.append(
            {
                "index": int(idx),
                "file": str(row.get("file", "")),
                "name": str(row.get("name", "")),
                "class": _classify_true16_patch(row, neutral_tolerance_q16=neutral_tol),
                "requested": requested_inputs,
                "corrected": corrected_inputs,
                "displayed_xyz": displayed_xyz,
                "measured_xyz": measured_xyz,
                "calibrated_xyz": calibrated_xyz,
                "transfer_requested": transferred_inputs,
                "transfer_corrected": transfer_corrected_inputs,
                "transfer_calibrated_xyz": transfer_calibrated_xyz,
            }
        )

    reference_luma = max(1e-6, max_luma)
    row_html = []
    for row in rows:
        displayed_desc = _describe_xyz_color(row["displayed_xyz"], reference_luma)
        measured_desc = _describe_xyz_color(row["measured_xyz"], reference_luma)
        calibrated_desc = _describe_xyz_color(row["calibrated_xyz"], reference_luma)
        transfer_desc = _describe_xyz_color(row["transfer_calibrated_xyz"], reference_luma) if row.get("transfer_calibrated_xyz") is not None else None

        requested_txt = "/".join(str(row["requested"][ch]) for ch in CHANNELS)
        corrected_txt = "/".join(str(row["corrected"][ch]) for ch in CHANNELS)
        transfer_requested_txt = "/".join(str(row["transfer_requested"][ch]) for ch in CHANNELS) if row.get("transfer_requested") else ""
        transfer_corrected_txt = "/".join(str(row["transfer_corrected"][ch]) for ch in CHANNELS) if row.get("transfer_corrected") else ""

        row_html.append(
            "".join(
                [
                    f"<tr data-class=\"{html.escape(row['class'])}\">",
                    f"<td>{row['index']}</td>",
                    _render_truncated_cell(row["file"], "c-file"),
                    _render_truncated_cell(row["name"], "c-patch"),
                    _render_truncated_cell(row["class"], "c-class"),
                    f"<td class=\"mono c-code\">{html.escape(requested_txt)}</td>",
                    f"<td class=\"mono c-code\">{html.escape(corrected_txt)}</td>",
                    (f"<td class=\"mono c-code\">{html.escape(transfer_requested_txt)}</td>" if row.get("transfer_requested") else ""),
                    (f"<td class=\"mono c-code\">{html.escape(transfer_corrected_txt)}</td>" if row.get("transfer_corrected") else ""),
                    _render_report_color_cell(displayed_desc),
                    _render_report_color_cell(measured_desc),
                    _render_report_color_cell(calibrated_desc),
                    (_render_report_color_cell(transfer_desc) if transfer_desc is not None else ""),
                    "</tr>",
                ]
            )
        )

    classes = sorted({row["class"] for row in rows})
    class_options = ["<option value=\"all\">all</option>"]
    for row_class in classes:
        class_options.append(f"<option value=\"{html.escape(row_class)}\">{html.escape(row_class)}</option>")

    profile_target = str(summary.get("_global", {}).get("profile_target", settings.get("profile_target", "linear")))
    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    header_label = str(calibration_header_path) if calibration_header_path is not None else "n/a"
    table_header_html = "".join(
        [
            "<th>#</th>",
            "<th class=\"c-file\">File</th>",
            "<th class=\"c-patch\">Patch</th>",
            "<th class=\"c-class\">Class</th>",
            "<th class=\"c-code\">Req q16 R/G/B/W</th>",
            "<th class=\"c-code\">Cal q16 R/G/B/W</th>",
            ("<th class=\"c-code\">Curve q16 R/G/B/W</th>" if transfer_curve_model else ""),
            ("<th class=\"c-code\">Curve+Cal q16 R/G/B/W</th>" if transfer_curve_model else ""),
            "<th class=\"color-cell\">Displayed</th>",
            "<th class=\"color-cell\">Measured</th>",
            "<th class=\"color-cell\">Post-Cal</th>",
            ("<th class=\"color-cell\">Post-Curve+Cal</th>" if transfer_curve_model else ""),
        ]
    )

    html_doc = _build_calibration_color_report_html(
        title="True16 Calibration Color Sanity Report",
        generated_utc=generated_utc,
        header_label=header_label,
        transfer_header_label=(transfer_curve_model or {}).get("header_path") if transfer_curve_model else None,
        row_count=len(rows),
        profile_target=profile_target,
        reference_luma=reference_luma,
        class_options_html="".join(class_options),
        table_header_html=table_header_html,
        rows_html="\n".join(row_html),
        tip_text=(
            "Use displayed/measured/post-cal/post-curve swatches to quickly sanity-check runtime behavior before flashing."
            if transfer_curve_model else
            "Use displayed/measured/post-cal swatches to quickly sanity-check changes before flashing."
        ),
        normalization_subject=(
            "displayed/measured/post-calibrated/post-curve-calibrated"
            if transfer_curve_model else
            "displayed/measured/post-calibrated"
        ),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")




def _solve_small_linear_system(matrix, rhs):
    n = len(matrix)
    if n == 0:
        return []
    aug = []
    for i in range(n):
        row = [float(v) for v in matrix[i]] + [float(rhs[i])]
        aug.append(row)
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            continue
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        pv = aug[col][col]
        for j in range(col, n + 1):
            aug[col][j] /= pv
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            if abs(factor) < 1e-12:
                continue
            for j in range(col, n + 1):
                aug[r][j] -= factor * aug[col][j]
    return [float(aug[i][n]) for i in range(n)]


def _invert_true16_measured_luma_to_input_q16(channel, desired_luma, measured_model_luts, summary):
    max_y = float(summary.get(channel, {}).get('max_y') or 0.0)
    if max_y <= 0.0:
        return 0
    target_norm = max(0.0, min(1.0, float(desired_luma) / max_y))
    target_q16 = int(round(target_norm * 65535.0))
    lut = [int(v) for v in measured_model_luts.get(channel, [])]
    if not lut:
        return target_q16
    pos = bisect_left(lut, target_q16)
    if pos <= 0:
        return 0
    if pos >= len(lut):
        return 65535
    lo = lut[pos - 1]
    hi = lut[pos]
    if abs(hi - target_q16) < abs(target_q16 - lo):
        idx = pos
    else:
        idx = pos - 1
    return _clamp_u16(round((idx * 65535.0) / max(1, (len(lut) - 1))))



def _rebalance_true16_target_lumas(row, named_groups, corrected_inputs, solved_target_lumas, measured_model_luts, summary):
    """
    Preserve total solved luminance but gently rebalance channel shares in warm / magenta regions.
    This is intentionally bounded: it does NOT replace the solver, it only redistributes
    solved RGB/W energy when the current methodology is known to drift.
    """
    vals = {ch: int(row.get(f"{ch.lower()}16", 0) or 0) for ch in CHANNELS}
    rgb_active = [ch for ch in ("R", "G", "B") if vals[ch] > 0]
    if not rgb_active:
        return dict(solved_target_lumas)

    out = {ch: float(v) for ch, v in solved_target_lumas.items()}
    current_lumas = {
        ch: float(_lut_output_y(ch, int(corrected_inputs.get(ch, 0)), measured_model_luts, summary))
        for ch in rgb_active
    }

    cur_rgb_total = sum(current_lumas.values())
    solved_rgb_total = sum(float(out.get(ch, 0.0)) for ch in rgb_active)
    if solved_rgb_total <= 1e-9 or cur_rgb_total <= 1e-9:
        return out

    # Build a requested RGB luminance ratio from the currently calibrated per-channel lumas,
    # then bias it slightly depending on known failure regions.
    rgb_weights = {ch: max(1e-9, current_lumas[ch]) for ch in rgb_active}

    is_warm = any(g in named_groups for g in ("yellow_corridor", "amber_rgbw", "warm_corridor", "warm_like_rgbw", "warm_rgbw"))
    is_amber = ("amber_rgbw" in named_groups) or ("yellow_corridor" in named_groups and vals["R"] >= int(0.90 * max(1, vals["G"])))
    is_true_yellow = ("yellow_corridor" in named_groups and vals["G"] > int(1.06 * max(1, vals["R"])) and vals["B"] == 0)
    is_white_supported = any(g in named_groups for g in ("white_support_mix", "white_heavy_mix"))
    is_magenta = vals["R"] > 0 and vals["B"] > 0 and vals["G"] < int(0.20 * max(vals["R"], vals["B"], 1))

    if is_warm:
        if "R" in rgb_weights:
            rgb_weights["R"] *= 1.10 if is_amber else 1.06
        if "G" in rgb_weights:
            rgb_weights["G"] *= 0.94 if is_true_yellow else 0.97

    if is_magenta:
        if "R" in rgb_weights:
            rgb_weights["R"] *= 1.10
        if "B" in rgb_weights:
            rgb_weights["B"] *= 0.96

    weight_sum = sum(rgb_weights.values())
    if weight_sum <= 1e-9:
        return out

    # Optionally pull a little luminance back out of W for warm chromatic mixes and
    # give it back to RGB using the rebalanced hue-preserving weights.
    w_take = 0.0
    if is_warm and is_white_supported:
        rgb_peak = max(vals[ch] for ch in rgb_active) if rgb_active else 0
        rgb_min = min(vals[ch] for ch in rgb_active) if rgb_active else 0
        chroma = ((rgb_peak - rgb_min) / max(1.0, float(rgb_peak))) if rgb_peak > 0 else 0.0
        if chroma > 0.08 and "W" in out and out["W"] > 0.0:
            w_take = 0.12 * float(out["W"])
            out["W"] = max(0.0, float(out["W"]) - w_take)

    target_rgb_total = solved_rgb_total + w_take
    for ch in rgb_active:
        out[ch] = target_rgb_total * (rgb_weights[ch] / weight_sum)

    return out


def _fit_true16_mixed_patch_channel_lumas(corrected_inputs, measured_xyz, measured_model_luts, summary, channel_xy_basis, ridge=0.14):
    active = [ch for ch in CHANNELS if int(corrected_inputs.get(ch, 0)) > 0 and float(summary.get(ch, {}).get('max_y') or 0.0) > 0.0]
    if not active:
        return {}
    current_lumas = []
    unit_xyz_cols = []
    max_lumas = []
    for ch in active:
        current_luma = _lut_output_y(ch, int(corrected_inputs.get(ch, 0)), measured_model_luts, summary)
        basis = channel_xy_basis.get(ch, {'x': 0.3127, 'y': 0.3290})
        unit_xyz = _xyy_to_xyz(basis.get('x'), basis.get('y'), 1.0)
        if unit_xyz is None:
            unit_xyz = (0.0, 1.0, 0.0)
        unit_xyz_cols.append((float(unit_xyz[0]), float(unit_xyz[1]), float(unit_xyz[2])))
        current_lumas.append(float(current_luma))
        max_lumas.append(float(summary.get(ch, {}).get('max_y') or 0.0))

    mX, mY, mZ = (float(measured_xyz[0]), float(measured_xyz[1]), float(measured_xyz[2]))
    n = len(active)
    ata = [[0.0] * n for _ in range(n)]
    atb = [0.0] * n
    for i in range(n):
        xi = unit_xyz_cols[i]
        atb[i] = xi[0] * mX + xi[1] * mY + xi[2] * mZ + ridge * current_lumas[i]
        for j in range(n):
            xj = unit_xyz_cols[j]
            ata[i][j] = xi[0] * xj[0] + xi[1] * xj[1] + xi[2] * xj[2]
        ata[i][i] += ridge

    solved = _solve_small_linear_system(ata, atb)
    out = {}
    for ch, cur, limit, val in zip(active, current_lumas, max_lumas, solved):
        if not math.isfinite(val):
            val = cur
        val = max(0.0, min(float(limit), float(val)))
        out[ch] = float(val)
    return out


def _mixed_patch_weight(row, row_class, named_groups, neutral_tolerance_q16, neutral_protection_strength, warm_priority, gamut_edge_restraint):
    vals = {ch: int(row.get(f'{ch.lower()}16', 0)) for ch in CHANNELS}
    rgb = [vals[ch] for ch in ('R', 'G', 'B') if vals[ch] > 0]
    rgb_span = (max(rgb) - min(rgb)) if rgb else 0
    rgb_peak = max(rgb) if rgb else 0
    chroma = (float(rgb_span) / max(1.0, float(rgb_peak))) if rgb_peak > 0 else 0.0
    neutral_factor = 1.0 + float(neutral_protection_strength) * max(0.0, 1.0 - chroma)
    if row_class in ('gray_rgb', 'gray_rgbw'):
        base = 1.25
    elif row_class == 'mixed_rgb':
        base = 1.0
    elif row_class == 'mixed_with_w':
        base = 0.92
    else:
        base = 0.75

    if 'warm_like_rgbw' in named_groups or 'warm_corridor' in named_groups or 'yellow_corridor' in named_groups:
        base *= (1.0 + 0.18 * float(warm_priority))
    if 'amber_rgbw' in named_groups or 'warm_rgbw' in named_groups:
        base *= 1.06
    if 'pastel_like' in named_groups:
        base *= (1.0 + 0.18 * float(neutral_protection_strength))
    if 'near_neutral_tint' in named_groups:
        base *= (1.0 + 0.28 * float(neutral_protection_strength))
    if 'white_heavy_mix' in named_groups:
        base *= 1.10
    elif 'white_support_mix' in named_groups:
        base *= 1.05
    if 'two_channel_rgb' in named_groups:
        base *= 1.05
    elif 'three_channel_rgb' in named_groups:
        base *= 1.08

    edge = max((vals[ch] / 65535.0) for ch in CHANNELS)
    edge_penalty = max(0.0, edge - 0.82) / 0.18 if edge > 0.82 else 0.0
    edge_restraint = 1.0 - float(gamut_edge_restraint) * edge_penalty
    if 'neon_edge' in named_groups:
        edge_restraint *= max(0.40, 1.0 - 0.60 * float(gamut_edge_restraint))
    elif 'saturated_family' in named_groups:
        edge_restraint *= max(0.55, 1.0 - 0.35 * float(gamut_edge_restraint))
    edge_restraint = max(0.35, min(1.05, edge_restraint))

    if row_class in ('gray_rgb', 'gray_rgbw'):
        neutral_factor = max(neutral_factor, 1.15)
    return float(base * neutral_factor * edge_restraint)


def _smooth_sparse_delta_field(delta_field, weight_field, passes=6):
    n = len(delta_field)
    if n == 0:
        return []
    values = [float(delta_field[i]) / float(weight_field[i]) if weight_field[i] > 1e-9 else 0.0 for i in range(n)]
    weights = [float(weight_field[i]) for i in range(n)]
    for _ in range(max(0, int(passes))):
        out = values[:]
        for i in range(n):
            total = values[i] * max(weights[i], 1.0)
            wsum = max(weights[i], 1.0)
            if i > 0:
                total += values[i - 1] * max(weights[i - 1], 0.5)
                wsum += max(weights[i - 1], 0.5)
            if i + 1 < n:
                total += values[i + 1] * max(weights[i + 1], 0.5)
                wsum += max(weights[i + 1], 0.5)
            if i > 1:
                total += values[i - 2] * 0.25
                wsum += 0.25
            if i + 2 < n:
                total += values[i + 2] * 0.25
                wsum += 0.25
            out[i] = total / wsum if wsum > 1e-9 else values[i]
        values = out
    return values


def apply_true16_mixed_patch_correction(
    measurements,
    backbone_luts,
    measured_model_luts,
    summary,
    neutral_tolerance_q16=2048,
    ambient_profile=None,
    enabled=True,
    strength=0.65,
    backbone_lock_strength=0.55,
    locality_width=24,
    neutral_protection_strength=0.75,
    warm_priority=0.35,
    gamut_edge_restraint=0.45,
    ridge=0.14,
):
    result = {
        'enabled': bool(enabled),
        'applied': False,
        'rows_considered': 0,
        'rows_used': 0,
        'row_class_counts': {},
        'strength': float(max(0.0, float(strength))),
        'backbone_lock_strength': float(max(0.0, float(backbone_lock_strength))),
        'locality_width': int(max(2, int(locality_width))),
        'neutral_protection_strength': float(max(0.0, float(neutral_protection_strength))),
        'warm_priority': float(max(0.0, float(warm_priority))),
        'gamut_edge_restraint': float(max(0.0, float(gamut_edge_restraint))),
        'per_channel': {ch: {'points_touched': 0, 'max_abs_delta_q16': 0, 'mean_abs_delta_q16': 0.0} for ch in CHANNELS},
    }
    if not enabled or float(strength) <= 0.0:
        result['reason'] = 'disabled'
        return {ch: list(backbone_luts[ch]) for ch in CHANNELS}, result

    channel_xy_basis = _estimate_true16_channel_xy_basis(measurements, ambient_profile=ambient_profile)
    n = len(next(iter(backbone_luts.values()))) if backbone_luts else 0
    if n <= 1:
        result['reason'] = 'empty-backbone'
        return {ch: list(backbone_luts[ch]) for ch in CHANNELS}, result

    delta_sum = {ch: [0.0] * n for ch in CHANNELS}
    delta_wt = {ch: [0.0] * n for ch in CHANNELS}
    class_counts = defaultdict(int)
    named_counts = defaultdict(int)
    loc_width = max(2, int(locality_width))

    for row in measurements:
        row_class = _classify_true16_patch(row, neutral_tolerance_q16=neutral_tolerance_q16)
        if row_class in ('black', 'single'):
            continue
        result['rows_considered'] += 1
        class_counts[row_class] += 1
        measured_xyz = _measurement_row_xyz(row, ambient_profile=ambient_profile)
        if measured_xyz is None:
            continue
        requested_inputs = {ch: _clamp_u16(int(row.get(f'{ch.lower()}16', 0))) for ch in CHANNELS}
        corrected_inputs = _correct_true16_inputs(requested_inputs, backbone_luts)
        if sum(1 for ch in CHANNELS if corrected_inputs[ch] > 0) < 2:
            continue
        target_lumas = _fit_true16_mixed_patch_channel_lumas(
            corrected_inputs,
            measured_xyz,
            measured_model_luts,
            summary,
            channel_xy_basis,
            ridge=max(0.01, float(ridge)),
        )
        if not target_lumas:
            continue
        named_groups = _true16_named_patch_groups(row)
        for group_name in set(named_groups):
            named_counts[group_name] += 1

        target_lumas = _rebalance_true16_target_lumas(
            row,
            named_groups,
            corrected_inputs,
            target_lumas,
            measured_model_luts,
            summary,
        )

        patch_weight = _mixed_patch_weight(
            row,
            row_class,
            named_groups,
            neutral_tolerance_q16,
            neutral_protection_strength,
            warm_priority,
            gamut_edge_restraint,
        )
        used_here = False
        for ch, target_luma in target_lumas.items():
            req_q16 = int(requested_inputs.get(ch, 0))
            if req_q16 <= 0:
                continue
            cur_q16 = int(corrected_inputs.get(ch, 0))
            desired_q16 = _invert_true16_measured_luma_to_input_q16(ch, target_luma, measured_model_luts, summary)
            delta_q16 = float(desired_q16 - cur_q16)
            max_dev = max(512.0, 0.10 * 65535.0)
            delta_q16 = max(-max_dev, min(max_dev, delta_q16))
            if abs(delta_q16) < 1.0:
                continue
            used_here = True
            idx = int(round((req_q16 * (n - 1)) / 65535.0))
            for offset in range(-loc_width, loc_width + 1):
                j = idx + offset
                if j < 0 or j >= n:
                    continue
                alpha = 1.0 - (abs(offset) / float(loc_width + 1))
                if alpha <= 0.0:
                    continue
                w = patch_weight * alpha * alpha
                delta_sum[ch][j] += delta_q16 * w
                delta_wt[ch][j] += w
        if used_here:
            result['rows_used'] += 1

    result['row_class_counts'] = {k: int(v) for k, v in sorted(class_counts.items())}
    result['named_group_counts'] = {k: int(v) for k, v in sorted(named_counts.items())}
    if result['rows_used'] <= 0:
        result['reason'] = 'no-usable-mixed-rows'
        return {ch: list(backbone_luts[ch]) for ch in CHANNELS}, result

    out_luts = {}
    for ch in CHANNELS:
        backbone = [int(v) for v in backbone_luts[ch]]
        sparse = _smooth_sparse_delta_field(delta_sum[ch], delta_wt[ch], passes=6)
        corrected = list(backbone)
        abs_deltas = []
        for i in range(n):
            norm_pos = i / float(max(1, n - 1))
            edge_lock = max(0.0, 1.0 - 4.0 * norm_pos * (1.0 - norm_pos))
            lock = min(0.95, max(0.0, float(backbone_lock_strength) * (0.55 + 0.45 * edge_lock)))
            applied_delta = float(strength) * float(sparse[i]) * (1.0 - lock)
            max_dev_here = max(384.0, 0.075 * 65535.0)
            applied_delta = max(-max_dev_here, min(max_dev_here, applied_delta))
            v = int(round(backbone[i] + applied_delta))
            corrected[i] = _clamp_u16(v)
            abs_deltas.append(abs(applied_delta))
        corrected[0] = 0
        corrected[-1] = 65535
        for i in range(1, n):
            if corrected[i] < corrected[i - 1]:
                corrected[i] = corrected[i - 1]
        corrected = _redistribute_true16_command_lut(corrected, min_step_factor=0.28, max_step_factor=2.60, smoothing_passes=2)
        corrected[0] = 0
        corrected[-1] = 65535
        for i in range(1, n):
            if corrected[i] < corrected[i - 1]:
                corrected[i] = corrected[i - 1]
        out_luts[ch] = corrected
        touched = sum(1 for w in delta_wt[ch] if w > 1e-9)
        result['per_channel'][ch] = {
            'points_touched': int(touched),
            'max_abs_delta_q16': int(round(max(abs_deltas) if abs_deltas else 0.0)),
            'mean_abs_delta_q16': float(sum(abs_deltas) / len(abs_deltas)) if abs_deltas else 0.0,
        }
    result['applied'] = True
    return out_luts, result

def compute_true16_calibration_artifacts(
    measure_dir: Path,
    lut_size: int = 4096,
    input_globs=None,
    aggregation: str = "median",
    trim_fraction: float = 0.1,
    outlier_sigma: float = 3.5,
    enforce_monotonic: bool = True,
    white_channel_scale: float = 1.0,
    white_channel_gamma: float = 1.0,
    auto_white_scale: bool = False,
    neutral_tolerance_q16: int = 2048,
    profile_target: str = "perceptual-density",
    profile_target_gamma: float = 2.2,
    enable_black_level_compensation: bool = True,
    black_level_y=None,
    enable_inverse_regularization: bool = True,
    inverse_max_step_q16=None,
    enable_mixed_patch_correction: bool = True,
    mixed_correction_strength: float = 0.65,
    mixed_backbone_lock_strength: float = 0.55,
    mixed_locality_width: int = 24,
    mixed_neutral_protection_strength: float = 0.75,
    mixed_warm_priority: float = 0.35,
    mixed_gamut_edge_restraint: float = 0.45,
    enable_global_mixed_fit: bool = False,
    global_mixed_fit_max_iterations: int = 5,
    global_mixed_fit_peak_preserve_strength: float = 0.0,
    transfer_curve_header: Path | None = None,
):
    measurements, loader_stats = load_patch_measurements_true16(measure_dir, input_globs=input_globs)
    measured_model_luts, summary, measured_inputs = build_channel_tables_true16(
        measurements,
        lut_size=lut_size,
        aggregation=aggregation,
        trim_fraction=trim_fraction,
        outlier_sigma=outlier_sigma,
        enforce_monotonic=enforce_monotonic,
        enable_black_level_compensation=enable_black_level_compensation,
        black_level_y=black_level_y,
    )

    global_summary = summary.get("_global", {})
    black_level_effective = float(global_summary.get("black_level_y", 0.0))
    ambient_profile = global_summary.get("ambient_profile")

    profile_target = str(profile_target or "linear").strip().lower()
    if profile_target not in ("legacy-measured", "linear", "gamma", "perceptual-density", "delta-preserving"):
        profile_target = "linear"

    if profile_target == "legacy-measured":
        target_luts = {ch: list(measured_model_luts[ch]) for ch in CHANNELS}
    elif profile_target == "perceptual-density":
        target_luts = {
            ch: _build_density_preserving_target_lut(
                measured_model_luts[ch],
                gamma=max(1.10, min(2.40, float(profile_target_gamma))),
                gamma_blend=0.24,
                linear_floor_blend=0.08,
            )
            for ch in CHANNELS
        }
    elif profile_target == "delta-preserving":
        target_luts = {
            ch: _build_density_preserving_target_lut(
                measured_model_luts[ch],
                gamma=max(1.0, min(2.20, float(profile_target_gamma))),
                gamma_blend=0.16,
                linear_floor_blend=0.04,
            )
            for ch in CHANNELS
        }
    else:
        curve = "gamma" if profile_target == "gamma" else "linear"
        target_table = _build_target_q16_table(lut_size, target=curve, gamma=profile_target_gamma)
        target_luts = {ch: list(target_table) for ch in CHANNELS}

    transfer_curve_model = None
    transfer_curve_meta = {
        "enabled": False,
        "header_path": None,
        "bucket_count": 0,
    }
    if transfer_curve_header is not None:
        transfer_curve_model = load_transfer_curve_header(Path(transfer_curve_header))
        transfer_curve_meta = {
            "enabled": True,
            "header_path": str(Path(transfer_curve_header)),
            "bucket_count": int(transfer_curve_model.get("bucket_count", 0)),
        }

    raw_inverse_luts = {
        ch: _invert_true16_response_lut(measured_model_luts[ch], target_luts[ch])
        for ch in CHANNELS
    }

    luts = {}
    inverse_regularization_stats = {}
    for ch in CHANNELS:
        if enable_inverse_regularization:
            reg_lut, reg_stats = _regularize_true16_command_lut(
                raw_inverse_luts[ch],
                max_step_q16=inverse_max_step_q16,
            )
            density_floor = 0.18 if profile_target in ("perceptual-density", "delta-preserving") else 0.0
            density_lut, density_stats = _density_regularize_true16_command_lut(
                reg_lut,
                floor_strength=density_floor,
                smoothing_passes=2 if profile_target in ("perceptual-density", "delta-preserving") else 0,
            )
            if profile_target == "delta-preserving":
                delta_lut, delta_stats = _delta_preserve_true16_command_lut(
                    density_lut,
                    measured_model_luts[ch],
                    target_luts[ch],
                    strength=0.38,
                    max_delta_ratio=0.10,
                    smoothing_passes=3,
                    midtone_bias=0.40,
                )
                luts[ch] = delta_lut
            else:
                delta_stats = {"applied": False, "strength": 0.0, "max_delta_ratio": 0.0, "smoothing_passes": 0, "midtone_bias": 0.0}
                luts[ch] = density_lut
            inverse_regularization_stats[ch] = {
                "applied": True,
                **reg_stats,
                "density_regularization": density_stats,
                "delta_preservation": delta_stats,
            }
        else:
            luts[ch] = list(raw_inverse_luts[ch])
            raw_steps = [luts[ch][i + 1] - luts[ch][i] for i in range(len(luts[ch]) - 1)]
            inverse_regularization_stats[ch] = {
                "applied": False,
                "max_step_q16": int(inverse_max_step_q16) if inverse_max_step_q16 is not None else None,
                "raw_max_step_q16": int(max(raw_steps) if raw_steps else 0),
                "regularized_max_step_q16": int(max(raw_steps) if raw_steps else 0),
                "step_clamps": 0,
                "density_regularization": {"applied": False, "floor_strength": 0.0, "smoothing_passes": 0, "duplicate_steps_before": 0, "duplicate_steps_after": 0},
                "delta_preservation": {"applied": False, "strength": 0.0, "max_delta_ratio": 0.0, "smoothing_passes": 0, "midtone_bias": 0.0},
            }

    requested_white_scale = max(0.0, float(white_channel_scale))
    recommended_white_scale, white_scale_stats = estimate_true16_white_scale_from_mixed_rows(
        measurements,
        luts,
        summary,
        neutral_tolerance_q16=neutral_tolerance_q16,
        black_level_y=black_level_effective,
        ambient_profile=ambient_profile,
    )
    effective_white_scale = requested_white_scale * (recommended_white_scale if auto_white_scale else 1.0)

    luts["W"] = _shape_true16_lut(luts["W"], scale=effective_white_scale, gamma=white_channel_gamma)

    white_shape = {
        "requested_white_scale": float(requested_white_scale),
        "effective_white_scale": float(effective_white_scale),
        "white_channel_gamma": float(max(0.05, float(white_channel_gamma))),
        "auto_white_scale_enabled": bool(auto_white_scale),
        "recommended_white_scale": float(recommended_white_scale),
        **white_scale_stats,
    }
    summary["W"]["white_shape"] = dict(white_shape)

    backbone_qa = build_true16_calibration_qa(
        measurements,
        luts,
        summary,
        measured_model_luts=measured_model_luts,
        neutral_tolerance_q16=neutral_tolerance_q16,
        black_level_y=black_level_effective,
        ambient_profile=ambient_profile,
    )

    luts, mixed_patch_correction = apply_true16_mixed_patch_correction(
        measurements,
        luts,
        measured_model_luts,
        summary,
        neutral_tolerance_q16=neutral_tolerance_q16,
        ambient_profile=ambient_profile,
        enabled=bool(enable_mixed_patch_correction),
        strength=mixed_correction_strength,
        backbone_lock_strength=mixed_backbone_lock_strength,
        locality_width=mixed_locality_width,
        neutral_protection_strength=mixed_neutral_protection_strength,
        warm_priority=mixed_warm_priority,
        gamut_edge_restraint=mixed_gamut_edge_restraint,
    )

    luts, global_mixed_fit = optimize_true16_global_mixed_fit(
        measurements,
        luts,
        measured_model_luts,
        summary,
        neutral_tolerance_q16=neutral_tolerance_q16,
        black_level_y=black_level_effective,
        ambient_profile=ambient_profile,
        enabled=bool(enable_global_mixed_fit),
        profile_target=profile_target,
        max_iterations=global_mixed_fit_max_iterations,
        peak_preserve_strength=global_mixed_fit_peak_preserve_strength,
    )

    white_shape["global_mixed_fit_applied"] = bool(global_mixed_fit.get("applied", False))
    white_shape["global_mixed_fit_gamma"] = float(global_mixed_fit.get("gamma", 1.0))
    for ch in CHANNELS:
        white_shape[f"global_mixed_fit_scale_{ch.lower()}"] = float(global_mixed_fit.get("scales", {}).get(ch, 1.0))

    qa = build_true16_calibration_qa(
        measurements,
        luts,
        summary,
        measured_model_luts=measured_model_luts,
        neutral_tolerance_q16=neutral_tolerance_q16,
        black_level_y=black_level_effective,
        ambient_profile=ambient_profile,
    )
    post_transfer_qa = build_true16_transfer_aware_qa(
        measurements,
        luts,
        measured_model_luts,
        target_luts,
        summary,
        transfer_curve_model,
        neutral_tolerance_q16=neutral_tolerance_q16,
        ambient_profile=ambient_profile,
    ) if transfer_curve_model is not None else None

    backbone_single_rows = int(sum(int(summary.get(ch, {}).get("used_samples", 0)) for ch in CHANNELS))
    mixed_rows_used = int(mixed_patch_correction.get("rows_used", 0))
    mixed_rows_considered = int(mixed_patch_correction.get("rows_considered", 0))
    white_shape_pairs = int(white_shape.get("pair_count", 0))
    total_measurements = int(len(measurements))
    backbone_and_mixed_union = min(total_measurements, backbone_single_rows + mixed_rows_used)
    qa_only_rows = max(0, total_measurements - backbone_and_mixed_union)
    row_usage = {
        "total_measurements": total_measurements,
        "used_for_backbone_single_channel": backbone_single_rows,
        "considered_for_mixed_correction": mixed_rows_considered,
        "used_for_mixed_correction": mixed_rows_used,
        "used_for_white_shaping_pairs": white_shape_pairs,
        "estimated_qa_only_or_indirect": qa_only_rows,
        "mixed_row_class_counts": dict(mixed_patch_correction.get("row_class_counts", {})),
        "mixed_named_group_counts": dict(mixed_patch_correction.get("named_group_counts", {})),
    }

    family_before_after = {}
    before_groups = dict((backbone_qa or {}).get("groups", {}))
    after_groups = dict((qa or {}).get("groups", {}))
    for group_name in sorted(set(before_groups.keys()) | set(after_groups.keys())):
        before_group = before_groups.get(group_name, {}) or {}
        after_group = after_groups.get(group_name, {}) or {}
        before_abs = before_group.get("mean_abs_y_error")
        after_abs = after_group.get("mean_abs_y_error")
        before_signed = before_group.get("mean_signed_y_error")
        after_signed = after_group.get("mean_signed_y_error")
        entry = {
            "sample_count_before": int(before_group.get("count", 0) or 0),
            "sample_count_after": int(after_group.get("count", 0) or 0),
            "before_mean_abs_y_error": float(before_abs) if before_abs is not None else None,
            "after_mean_abs_y_error": float(after_abs) if after_abs is not None else None,
            "before_mean_signed_y_error": float(before_signed) if before_signed is not None else None,
            "after_mean_signed_y_error": float(after_signed) if after_signed is not None else None,
            "delta_mean_abs_y_error": (float(after_abs) - float(before_abs)) if before_abs is not None and after_abs is not None else None,
            "delta_mean_signed_y_error": (float(after_signed) - float(before_signed)) if before_signed is not None and after_signed is not None else None,
        }
        family_before_after[group_name] = entry

    summary.setdefault("_global", {})["profile_target"] = profile_target
    summary.setdefault("_global", {})["profile_target_gamma"] = float(max(0.05, float(profile_target_gamma)))
    summary.setdefault("_global", {})["black_level_enabled"] = bool(enable_black_level_compensation)
    summary.setdefault("_global", {})["inverse_regularization_enabled"] = bool(enable_inverse_regularization)
    summary.setdefault("_global", {})["inverse_max_step_q16"] = int(inverse_max_step_q16) if inverse_max_step_q16 is not None else None
    summary.setdefault("_global", {})["ambient_compensation_enabled"] = bool((ambient_profile or {}).get("enabled", False))
    summary.setdefault("_global", {})["mixed_patch_correction"] = dict(mixed_patch_correction)
    summary.setdefault("_global", {})["global_mixed_fit"] = dict(global_mixed_fit)
    summary.setdefault("_global", {})["transfer_curve"] = dict(transfer_curve_meta)
    summary.setdefault("_global", {})["row_usage"] = dict(row_usage)
    summary.setdefault("_global", {})["backbone_qa"] = backbone_qa
    summary.setdefault("_global", {})["before_after_family_error"] = dict(family_before_after)

    warnings = []
    for ch in CHANNELS:
        if summary[ch].get("mode") == "fallback-linear":
            warnings.append(f"{ch}: no single-channel True16 measurements found; using fallback linear LUT")
            continue
        if int(summary[ch].get("points", 0)) < 8:
            warnings.append(f"{ch}: sparse sampling ({summary[ch]['points']} points) may produce unstable LUTs")
        if int(summary[ch].get("largest_gap_q16", 0)) > 8192:
            warnings.append(f"{ch}: largest input gap is {summary[ch]['largest_gap_q16']} q16; low-end detail may be underfit")
    mixed_with_w = qa["groups"].get("mixed_with_w", {})
    if white_shape.get("pair_count", 0) <= 0:
        warnings.append("No W-active mixed patches were found; automatic white blowout protection can only recommend scaling once RGB+W captures exist")
    elif mixed_with_w.get("mean_signed_y_error") is not None and mixed_with_w["mean_signed_y_error"] > 0.0:
        warnings.append("W-active mixed patches are, on average, brighter than measured predictions; consider enabling --auto-white-scale or reducing --white-channel-scale")
    if profile_target == "legacy-measured":
        warnings.append("Profile target is legacy-measured; this mode preserves captured transfer behavior for compatibility checks and is not intended for perceptual reshaping")
    if profile_target == "linear":
        if not bool(global_mixed_fit.get("applied", False)):
            warnings.append("Profile target is linear; mid-level codes may be lifted versus measured response. Enable global mixed fit or use --profile-target perceptual-density if you need better code density without a hard linear remap")
        else:
            warnings.append("Profile target is linear with global mixed fit enabled; verify grayscale and W-active mixed patches on hardware before flashing")
    if profile_target == "perceptual-density":
        warnings.append("Profile target is perceptual-density; verify that duplicate runs and mid-tone spacing improve on hardware versus legacy-measured before finalizing")
    if bool(mixed_patch_correction.get("enabled", False)) and not bool(mixed_patch_correction.get("applied", False)):
        warnings.append("Mixed-patch correction was enabled but no usable mixed rows influenced the final LUT; verify that your capture set contains valid mixed patches with XYZ measurements")
    if post_transfer_qa is not None:
        warm_transfer = post_transfer_qa.get("groups", {}).get("warm_like_rgbw", {})
        if warm_transfer.get("mean_saturation_ratio") is not None and float(warm_transfer.get("mean_saturation_ratio")) < 0.90:
            warnings.append("Post-transfer warm-like RGBW patches are desaturating after calibration; inspect post-curve report columns or try a different transfer curve")
        if warm_transfer.get("mean_saturation_ratio") is not None and float(warm_transfer.get("mean_saturation_ratio")) > 1.10:
            warnings.append("Post-transfer warm-like RGBW patches are oversaturating after calibration; inspect post-curve report columns or soften the transfer curve if highlights look too hot")

    return {
        "format": "TemporalBFI_True16Calibration_v2_1",
        "measurement_count": len(measurements),
        "measurements": measurements,
        "loader": loader_stats,
        "summary": summary,
        "ambient_profile": ambient_profile,
        "measured_model_luts": measured_model_luts,
        "luts": luts,
        "qa": qa,
        "backbone_qa": backbone_qa,
        "post_transfer_qa": post_transfer_qa,
        "transfer_curve": transfer_curve_meta,
        "transfer_curve_model": transfer_curve_model,
        "white_shape": white_shape,
        "row_usage": row_usage,
        "before_after_family_error": family_before_after,
        "mixed_patch_correction": mixed_patch_correction,
        "inverse_regularization": inverse_regularization_stats,
        "warnings": warnings,
        "settings": {
            "lut_size": int(lut_size),
            "input_globs": list(input_globs or TRUE16_DEFAULT_INPUT_GLOBS),
            "aggregation": aggregation,
            "trim_fraction": float(trim_fraction),
            "outlier_sigma": float(outlier_sigma),
            "enforce_monotonic": bool(enforce_monotonic),
            "neutral_tolerance_q16": int(neutral_tolerance_q16),
            "profile_target": profile_target,
            "profile_target_gamma": float(max(0.05, float(profile_target_gamma))),
            "black_level_enabled": bool(enable_black_level_compensation),
            "black_level_y": float(black_level_effective),
            "ambient_compensation_enabled": bool((ambient_profile or {}).get("enabled", False)),
            "inverse_regularization_enabled": bool(enable_inverse_regularization),
            "inverse_max_step_q16": int(inverse_max_step_q16) if inverse_max_step_q16 is not None else None,
            "mixed_patch_correction_enabled": bool(enable_mixed_patch_correction),
            "mixed_correction_strength": float(max(0.0, float(mixed_correction_strength))),
            "mixed_backbone_lock_strength": float(max(0.0, float(mixed_backbone_lock_strength))),
            "mixed_locality_width": int(max(2, int(mixed_locality_width))),
            "mixed_neutral_protection_strength": float(max(0.0, float(mixed_neutral_protection_strength))),
            "mixed_warm_priority": float(max(0.0, float(mixed_warm_priority))),
            "mixed_gamut_edge_restraint": float(max(0.0, float(mixed_gamut_edge_restraint))),
            "global_mixed_fit_enabled": bool(enable_global_mixed_fit),
            "global_mixed_fit_max_iterations": int(max(1, int(global_mixed_fit_max_iterations))),
            "global_mixed_fit_peak_preserve_strength": float(max(0.0, float(global_mixed_fit_peak_preserve_strength))),
            "transfer_curve_header": str(Path(transfer_curve_header)) if transfer_curve_header is not None else None,
        },
    }


def export_true16_calibration_report(out_path: Path, artifacts):
    report = {
        "format": "TemporalBFI_True16CalibrationReport_v1",
        "measurement_count": artifacts["measurement_count"],
        "loader": artifacts["loader"],
        "summary": artifacts["summary"],
        "ambient_profile": artifacts.get("ambient_profile"),
        "transfer_curve": artifacts.get("transfer_curve"),
        "white_shape": artifacts["white_shape"],
        "mixed_patch_correction": artifacts.get("mixed_patch_correction"),
        "qa": artifacts["qa"],
        "post_transfer_qa": artifacts.get("post_transfer_qa"),
        "warnings": artifacts["warnings"],
        "settings": artifacts["settings"],
    }
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def export_calibration_true16_header(
    measure_dir: Path,
    out_path: Path,
    lut_size: int = 4096,
    input_globs=None,
    aggregation: str = "median",
    trim_fraction: float = 0.1,
    outlier_sigma: float = 3.5,
    enforce_monotonic: bool = True,
    white_channel_scale: float = 1.0,
    white_channel_gamma: float = 1.0,
    auto_white_scale: bool = False,
    neutral_tolerance_q16: int = 2048,
    profile_target: str = "perceptual-density",
    profile_target_gamma: float = 2.2,
    enable_black_level_compensation: bool = True,
    black_level_y=None,
    enable_inverse_regularization: bool = True,
    inverse_max_step_q16=None,
    enable_mixed_patch_correction: bool = True,
    mixed_correction_strength: float = 0.65,
    mixed_backbone_lock_strength: float = 0.55,
    mixed_locality_width: int = 24,
    mixed_neutral_protection_strength: float = 0.75,
    mixed_warm_priority: float = 0.35,
    mixed_gamut_edge_restraint: float = 0.45,
    enable_global_mixed_fit: bool = False,
    global_mixed_fit_max_iterations: int = 5,
    global_mixed_fit_peak_preserve_strength: float = 0.0,
    transfer_curve_header: Path | None = None,
    qa_report_out: Path | None = None,
    web_report_out: Path | None = None,
    generate_web_report: bool = True,
):
    """Export a True16 calibration header with robust fitting and optional QA report."""
    resolved_lut_size = _resolve_true16_lut_size(
        measure_dir,
        lut_size,
        input_globs=input_globs,
        transfer_curve_header=transfer_curve_header,
    )
    artifacts = compute_true16_calibration_artifacts(
        measure_dir,
        lut_size=resolved_lut_size,
        input_globs=input_globs,
        aggregation=aggregation,
        trim_fraction=trim_fraction,
        outlier_sigma=outlier_sigma,
        enforce_monotonic=enforce_monotonic,
        white_channel_scale=white_channel_scale,
        white_channel_gamma=white_channel_gamma,
        auto_white_scale=auto_white_scale,
        neutral_tolerance_q16=neutral_tolerance_q16,
        profile_target=profile_target,
        profile_target_gamma=profile_target_gamma,
        enable_black_level_compensation=enable_black_level_compensation,
        black_level_y=black_level_y,
        enable_inverse_regularization=enable_inverse_regularization,
        inverse_max_step_q16=inverse_max_step_q16,
        enable_mixed_patch_correction=enable_mixed_patch_correction,
        mixed_correction_strength=mixed_correction_strength,
        mixed_backbone_lock_strength=mixed_backbone_lock_strength,
        mixed_locality_width=mixed_locality_width,
        mixed_neutral_protection_strength=mixed_neutral_protection_strength,
        mixed_warm_priority=mixed_warm_priority,
        mixed_gamut_edge_restraint=mixed_gamut_edge_restraint,
        enable_global_mixed_fit=enable_global_mixed_fit,
        global_mixed_fit_max_iterations=global_mixed_fit_max_iterations,
        global_mixed_fit_peak_preserve_strength=global_mixed_fit_peak_preserve_strength,
        transfer_curve_header=transfer_curve_header,
    )
    luts = artifacts["luts"]
    summary = artifacts["summary"]
    white_shape = artifacts["white_shape"]
    if qa_report_out is not None:
        export_true16_calibration_report(qa_report_out, artifacts)

    web_report_path = None
    if bool(generate_web_report):
        web_report_path = _resolve_true16_web_report_path(out_path, web_report_out)
        export_true16_calibration_web_report(web_report_path, artifacts, calibration_header_path=out_path)

    lines = [
        "// Auto-generated True16 calibration header v14",
        "// 16-bit Q16 input -> 16-bit Q16 output LUTs for solver-driven calibration",
        "// Built with robust aggregation, optional outlier rejection, and optional W shaping",
        "#pragma once",
        '#include <TemporalBFI.h>',
        "",
        "namespace TemporalBFICalibrationTrue16 {",
        "",
    ]

    for ch in CHANNELS:
        lut = luts[ch]
        lines.append(f"static const uint16_t LUT_{ch}_16_TO_16[{len(lut)}] = {{")
        for i in range(0, len(lut), 8):
            chunk = lut[i:i+8]
            lines.append("    " + ", ".join(str(v) for v in chunk) + ",")
        lines.append("};\n")

    lines += [
        "// LUT statistics and configuration",
        f"static const uint16_t LUT_SIZE = {resolved_lut_size};",
        f"static const uint16_t WHITE_SHAPE_SCALE_Q16 = {int(round(float(white_shape['effective_white_scale']) * 65535.0))};",
        f"static const uint16_t WHITE_SHAPE_GAMMA_X1000 = {int(round(float(white_shape['white_channel_gamma']) * 1000.0))};",
        f"static const uint8_t WHITE_AUTO_SCALE_ENABLED = {1 if white_shape['auto_white_scale_enabled'] else 0};",
        f"static const uint16_t WHITE_AUTO_RECOMMENDED_SCALE_Q16 = {int(round(float(white_shape['recommended_white_scale']) * 65535.0))};",
        f"static const uint16_t WHITE_AUTO_PAIR_COUNT = {int(white_shape.get('pair_count') or 0)};",
        "",
    ]

    for ch in CHANNELS:
        summary_ch = summary[ch]
        lines.append(f"// Channel {ch}")
        lines.append(f"static const uint32_t {ch}_MAX_Y_X1000 = {int(round(summary_ch['max_y'] * 1000))};")
        lines.append(f"static const uint16_t {ch}_MEASUREMENT_POINTS = {summary_ch['points']};")
        lines.append(f"static const uint16_t {ch}_SAMPLE_COUNT = {int(summary_ch.get('samples', 0))};")
        lines.append(f"static const uint16_t {ch}_LARGEST_GAP_Q16 = {int(summary_ch.get('largest_gap_q16', 0))};")
        lines.append("")

    global_summary = summary.get("_global", {})
    lines += [
        "// Global fit metadata",
        f"static const uint32_t BLACK_LEVEL_Y_X1000 = {int(round(float(global_summary.get('black_level_y', 0.0)) * 1000.0))};",
        f"static const uint8_t BLACK_LEVEL_COMPENSATION_ENABLED = {1 if global_summary.get('black_level_enabled', False) else 0};",
        f"static const uint16_t PROFILE_TARGET_GAMMA_X1000 = {int(round(float(global_summary.get('profile_target_gamma', 2.2)) * 1000.0))};",
        f"static constexpr const char* PROFILE_TARGET_MODE = \"{str(global_summary.get('profile_target', 'linear'))}\";",
        "",
    ]

    global_fit = global_summary.get("global_mixed_fit", {})
    mixed_patch_correction = global_summary.get("mixed_patch_correction", {})
    lines += [
        "// Mixed-patch correction metadata",
        f"static const uint8_t MIXED_PATCH_CORRECTION_ENABLED = {1 if mixed_patch_correction.get('enabled', False) else 0};",
        f"static const uint8_t MIXED_PATCH_CORRECTION_APPLIED = {1 if mixed_patch_correction.get('applied', False) else 0};",
        f"static const uint16_t MIXED_PATCH_CORRECTION_STRENGTH_X1000 = {int(round(float(mixed_patch_correction.get('strength', 0.0)) * 1000.0))};",
        f"static const uint16_t MIXED_PATCH_CORRECTION_ROWS_USED = {int(mixed_patch_correction.get('rows_used', 0))};",
        "",
        "// Optional global mixed-patch fit metadata",
        f"static const uint8_t GLOBAL_MIXED_FIT_ENABLED = {1 if global_fit.get('enabled', False) else 0};",
        f"static const uint8_t GLOBAL_MIXED_FIT_APPLIED = {1 if global_fit.get('applied', False) else 0};",
        f"static const uint16_t GLOBAL_MIXED_FIT_PEAK_PRESERVE_STRENGTH_X1000 = {int(round(float(global_fit.get('peak_preserve_strength', 0.0)) * 1000.0))};",
        f"static const uint16_t GLOBAL_MIXED_FIT_GAMMA_X1000 = {int(round(float(global_fit.get('gamma', 1.0)) * 1000.0))};",
        f"static const uint16_t GLOBAL_MIXED_FIT_SCALE_R_Q16 = {int(round(float(global_fit.get('scales', {}).get('R', 1.0)) * 65535.0))};",
        f"static const uint16_t GLOBAL_MIXED_FIT_SCALE_G_Q16 = {int(round(float(global_fit.get('scales', {}).get('G', 1.0)) * 65535.0))};",
        f"static const uint16_t GLOBAL_MIXED_FIT_SCALE_B_Q16 = {int(round(float(global_fit.get('scales', {}).get('B', 1.0)) * 65535.0))};",
        f"static const uint16_t GLOBAL_MIXED_FIT_SCALE_W_Q16 = {int(round(float(global_fit.get('scales', {}).get('W', 1.0)) * 65535.0))};",
        "",
    ]

    lines += [
        "// Combined accessor for runtime use",
        "struct True16LUTSet {",
        "    static const uint16_t* lutForChannel(uint8_t channel) {",
        "        switch (channel) {",
        "            case 0: return LUT_G_16_TO_16;",
        "            case 1: return LUT_R_16_TO_16;",
        "            case 2: return LUT_B_16_TO_16;",
        "            default: return LUT_W_16_TO_16;",
        "        }",
        "    }",
        "    static constexpr size_t lutSize() { return LUT_SIZE; }",
        "};",
        "",
        "} // namespace TemporalBFICalibrationTrue16",
        "",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return web_report_path


def analyze_calibration_true16(
    measure_dir: Path,
    out_path: Path,
    lut_size: int = 4096,
    input_globs=None,
    aggregation: str = "median",
    trim_fraction: float = 0.1,
    outlier_sigma: float = 3.5,
    enforce_monotonic: bool = True,
    white_channel_scale: float = 1.0,
    white_channel_gamma: float = 1.0,
    auto_white_scale: bool = False,
    neutral_tolerance_q16: int = 2048,
    profile_target: str = "perceptual-density",
    profile_target_gamma: float = 2.2,
    enable_black_level_compensation: bool = True,
    black_level_y=None,
    enable_inverse_regularization: bool = True,
    inverse_max_step_q16=None,
    enable_mixed_patch_correction: bool = True,
    mixed_correction_strength: float = 0.65,
    mixed_backbone_lock_strength: float = 0.55,
    mixed_locality_width: int = 24,
    mixed_neutral_protection_strength: float = 0.75,
    mixed_warm_priority: float = 0.35,
    mixed_gamut_edge_restraint: float = 0.45,
    enable_global_mixed_fit: bool = False,
    global_mixed_fit_max_iterations: int = 5,
    global_mixed_fit_peak_preserve_strength: float = 0.0,
    transfer_curve_header: Path | None = None,
):
    resolved_lut_size = _resolve_true16_lut_size(
        measure_dir,
        lut_size,
        input_globs=input_globs,
        transfer_curve_header=transfer_curve_header,
    )
    artifacts = compute_true16_calibration_artifacts(
        measure_dir,
        lut_size=resolved_lut_size,
        input_globs=input_globs,
        aggregation=aggregation,
        trim_fraction=trim_fraction,
        outlier_sigma=outlier_sigma,
        enforce_monotonic=enforce_monotonic,
        white_channel_scale=white_channel_scale,
        white_channel_gamma=white_channel_gamma,
        auto_white_scale=auto_white_scale,
        neutral_tolerance_q16=neutral_tolerance_q16,
        profile_target=profile_target,
        profile_target_gamma=profile_target_gamma,
        enable_black_level_compensation=enable_black_level_compensation,
        black_level_y=black_level_y,
        enable_inverse_regularization=enable_inverse_regularization,
        inverse_max_step_q16=inverse_max_step_q16,
        enable_mixed_patch_correction=enable_mixed_patch_correction,
        mixed_correction_strength=mixed_correction_strength,
        mixed_backbone_lock_strength=mixed_backbone_lock_strength,
        mixed_locality_width=mixed_locality_width,
        mixed_neutral_protection_strength=mixed_neutral_protection_strength,
        mixed_warm_priority=mixed_warm_priority,
        mixed_gamut_edge_restraint=mixed_gamut_edge_restraint,
        enable_global_mixed_fit=enable_global_mixed_fit,
        global_mixed_fit_max_iterations=global_mixed_fit_max_iterations,
        global_mixed_fit_peak_preserve_strength=global_mixed_fit_peak_preserve_strength,
        transfer_curve_header=transfer_curve_header,
    )
    export_true16_calibration_report(out_path, artifacts)
    return artifacts

def export_calibration_json(
    measure_dir: Path,
    out_path: Path,
    white_policy: str,
    max_bfi: int = 4,
    profile_source_bfi: int = 0,
    mixing_profile: str = "balanced",
    neutral_threshold_q16=None,
    white_weight_q16=None,
    rgb_weight_q16=None,
    white_channel_scale: float = 1.0,
    white_channel_gamma: float = 1.0,
    auto_white_scale: bool = False,
    auto_white_target_ratio: float = 1.35,
    auto_white_min_code: int = 24,
    profile_target: str = "perceptual-density",
    profile_target_gamma: float = 2.2,
    enable_black_level_compensation: bool = True,
    black_level_y=None,
):
    measurements = load_patch_measurements(measure_dir)
    profile_tables, per_bfi_tables, summary = build_channel_tables_with_correction(
        measurements,
        max_bfi=max_bfi,
        profile_source_bfi=profile_source_bfi,
        profile_target=profile_target,
        profile_target_gamma=profile_target_gamma,
        enable_black_level_compensation=enable_black_level_compensation,
        black_level_y=black_level_y,
    )

    global_summary = summary.get("_global", {})
    black_level_effective = float(global_summary.get("black_level_y", 0.0))

    mixing_cfg = resolve_mixing_config(
        mixing_profile,
        neutral_threshold_q16=neutral_threshold_q16,
        white_weight_q16=white_weight_q16,
        rgb_weight_q16=rgb_weight_q16,
    )

    requested_white_scale = max(0.0, float(white_channel_scale))
    effective_white_scale = requested_white_scale
    auto_white_stats = {
        "enabled": bool(auto_white_scale),
        "target_ratio": float(auto_white_target_ratio),
        "min_code": int(auto_white_min_code),
        "pair_count": 0,
        "recommended_scale": 1.0,
    }
    if auto_white_scale:
        recommended_scale, auto_white_stats = estimate_white_scale_from_gray_pairs(
            measurements,
            max_bfi=max_bfi,
            target_ratio=auto_white_target_ratio,
            min_code=auto_white_min_code,
            black_level_y=black_level_effective,
        )
        effective_white_scale *= recommended_scale
    auto_white_stats["enabled"] = bool(auto_white_scale)

    profile_tables, per_bfi_tables, shape_stats = apply_white_table_shape(
        profile_tables,
        per_bfi_tables,
        white_scale=effective_white_scale,
        white_gamma=white_channel_gamma,
    )
    shape_stats["requested_white_scale"] = float(requested_white_scale)
    shape_stats["effective_white_scale"] = float(effective_white_scale)

    out = {
        "format": "TemporalBFI_Calibration_v4",
        "white_policy": white_policy,
        "mixing_profile": mixing_profile,
        "mixing_config": mixing_cfg,
        "profile_source_bfi": profile_source_bfi,
        "profile_target": str(global_summary.get("profile_target", profile_target)),
        "profile_target_gamma": float(global_summary.get("profile_target_gamma", profile_target_gamma)),
        "black_level": {
            "enabled": bool(global_summary.get("black_level_enabled", enable_black_level_compensation)),
            "y": float(black_level_effective),
            **dict(global_summary.get("black_level", {})),
        },
        "white_table_shape": shape_stats,
        "auto_white_scale": auto_white_stats,
        "tables_8_to_16_profile": profile_tables,
        "tables_8_to_16_per_bfi": {
            ch: {str(bfi): per_bfi_tables[ch][bfi] for bfi in range(max_bfi + 1)}
            for ch in CHANNELS
        },
        "summary": summary,
        "measurement_count": len(measurements),
    }
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")


def export_calibration_header(
    measure_dir: Path,
    out_path: Path,
    white_policy: str,
    max_bfi: int = 4,
    profile_source_bfi: int = 0,
    mixing_profile: str = "balanced",
    neutral_threshold_q16=None,
    white_weight_q16=None,
    rgb_weight_q16=None,
    white_channel_scale: float = 1.0,
    white_channel_gamma: float = 1.0,
    auto_white_scale: bool = False,
    auto_white_target_ratio: float = 1.35,
    auto_white_min_code: int = 24,
    profile_target: str = "perceptual-density",
    profile_target_gamma: float = 2.2,
    enable_black_level_compensation: bool = True,
    black_level_y=None,
    web_report_out: Path | None = None,
    generate_web_report: bool = True,
):
    measurements = load_patch_measurements(measure_dir)
    profile_tables, per_bfi_tables, summary = build_channel_tables_with_correction(
        measurements,
        max_bfi=max_bfi,
        profile_source_bfi=profile_source_bfi,
        profile_target=profile_target,
        profile_target_gamma=profile_target_gamma,
        enable_black_level_compensation=enable_black_level_compensation,
        black_level_y=black_level_y,
    )

    # Keep a copy of the measured pre-cal model so the web report can show
    # "displayed" (before calibration) versus post-calibrated predictions.
    raw_per_bfi_tables = {
        ch: {int(bfi): list(vals) for bfi, vals in per_bfi_tables[ch].items()}
        for ch in CHANNELS
    }

    global_summary = summary.get("_global", {})
    black_level_effective = float(global_summary.get("black_level_y", 0.0))

    mixing_cfg = resolve_mixing_config(
        mixing_profile,
        neutral_threshold_q16=neutral_threshold_q16,
        white_weight_q16=white_weight_q16,
        rgb_weight_q16=rgb_weight_q16,
    )

    requested_white_scale = max(0.0, float(white_channel_scale))
    effective_white_scale = requested_white_scale
    auto_white_stats = {
        "enabled": bool(auto_white_scale),
        "target_ratio": float(auto_white_target_ratio),
        "min_code": int(auto_white_min_code),
        "pair_count": 0,
        "recommended_scale": 1.0,
    }
    if auto_white_scale:
        recommended_scale, auto_white_stats = estimate_white_scale_from_gray_pairs(
            measurements,
            max_bfi=max_bfi,
            target_ratio=auto_white_target_ratio,
            min_code=auto_white_min_code,
            black_level_y=black_level_effective,
        )
        effective_white_scale *= recommended_scale
    auto_white_stats["enabled"] = bool(auto_white_scale)

    profile_tables, per_bfi_tables, shape_stats = apply_white_table_shape(
        profile_tables,
        per_bfi_tables,
        white_scale=effective_white_scale,
        white_gamma=white_channel_gamma,
    )
    shape_stats["requested_white_scale"] = float(requested_white_scale)
    shape_stats["effective_white_scale"] = float(effective_white_scale)

    policy_enum = {
        "disabled": "TemporalBFI::WhitePolicy::Disabled",
        "near-neutral": "TemporalBFI::WhitePolicy::NearNeutralOnly",
        "always": "TemporalBFI::WhitePolicy::AlwaysAllowed",
        "white-priority": "TemporalBFI::WhitePolicy::WhitePriority",
        "measured-optimal": "TemporalBFI::WhitePolicy::MeasuredOptimal",
    }[white_policy]
    lines = [
        "// Auto-generated calibration header v14",
        "// profile LUTs encode corrected targets, while per-BFI tables encode measured output",
        "// white channel shaping and mixing profile are embedded below",
        "#pragma once",
        '#include <TemporalBFI.h>',
        "",
        "namespace TemporalBFICalibration {",
    ]
    for ch in CHANNELS:
        arr = profile_tables[ch]
        lines.append(f"static const uint16_t LUT_{ch}_8_TO_16[256] = {{")
        for i in range(0, 256, 8):
            lines.append("    " + ", ".join(str(v) for v in arr[i:i+8]) + ",")
        lines.append("};\n")
    for ch in CHANNELS:
        for bfi in range(max_bfi + 1):
            arr = per_bfi_tables[ch][bfi]
            lines.append(f"static const uint16_t LUT_{ch}_BFI{bfi}_8_TO_16[256] = {{")
            for i in range(0, 256, 8):
                lines.append("    " + ", ".join(str(v) for v in arr[i:i+8]) + ",")
            lines.append("};\n")
    lines += [
        f"static const uint16_t MIX_NEUTRAL_THRESHOLD_Q16 = {mixing_cfg['neutral_threshold_q16']};",
        f"static const uint16_t MIX_WHITE_WEIGHT_Q16 = {mixing_cfg['white_weight_q16']};",
        f"static const uint16_t MIX_RGB_WEIGHT_Q16 = {mixing_cfg['rgb_weight_q16']};",
        f"static const uint16_t WHITE_SHAPE_SCALE_Q16 = {int(round(shape_stats['effective_white_scale'] * 65535.0))};",
        f"static const uint16_t WHITE_SHAPE_GAMMA_X1000 = {int(round(shape_stats['white_channel_gamma'] * 1000.0))};",
        f"static const uint8_t WHITE_AUTO_SCALE_ENABLED = {1 if auto_white_scale else 0};",
        f"static const uint16_t WHITE_AUTO_TARGET_RATIO_X1000 = {int(round(float(auto_white_target_ratio) * 1000.0))};",
        f"static const uint16_t WHITE_AUTO_PAIR_COUNT = {int(auto_white_stats.get('pair_count') or 0)};",
        f"static const uint8_t PROFILE_SOURCE_BFI = {profile_source_bfi};",
        f"static const uint16_t BLACK_LEVEL_Y_X1000 = {int(round(black_level_effective * 1000.0))};",
        f"static const uint8_t BLACK_LEVEL_COMPENSATION_ENABLED = {1 if global_summary.get('black_level_enabled', False) else 0};",
        f"static const uint16_t PROFILE_TARGET_GAMMA_X1000 = {int(round(float(global_summary.get('profile_target_gamma', profile_target_gamma)) * 1000.0))};",
        f"static constexpr const char* PROFILE_TARGET_MODE = \"{str(global_summary.get('profile_target', profile_target))}\";",
        "static const TemporalBFI::CalibrationProfile PROFILE = {",
        "    nullptr, nullptr, nullptr, nullptr,",
        "    LUT_R_8_TO_16, LUT_G_8_TO_16, LUT_B_8_TO_16, LUT_W_8_TO_16,",
        f"    {{{policy_enum}, MIX_NEUTRAL_THRESHOLD_Q16, MIX_WHITE_WEIGHT_Q16, MIX_RGB_WEIGHT_Q16}},",
        "};",
        "} // namespace TemporalBFICalibration",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")

    web_report_path = None
    if bool(generate_web_report):
        web_report_path = _resolve_8bit_web_report_path(out_path, web_report_out)
        export_8bit_calibration_web_report(
            web_report_path,
            measurements,
            profile_tables,
            per_bfi_tables,
            summary,
            raw_per_bfi_tables=raw_per_bfi_tables,
            calibration_header_path=out_path,
        )

    return web_report_path

def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)

def _pq_eotf_norm(x: float) -> float:
    # SMPTE ST 2084 PQ EOTF, normalized so 1.0 corresponds to 10,000 nits.
    m1 = 2610.0 / 16384.0
    m2 = 2523.0 / 32.0
    c1 = 3424.0 / 4096.0
    c2 = 2413.0 / 128.0
    c3 = 2392.0 / 128.0

    x = _clamp01(x)
    if x <= 0.0:
        return 0.0

    power = x ** (1.0 / m2)
    numerator = max(power - c1, 0.0)
    denominator = c2 - c3 * power
    if denominator <= 0.0:
        return 1.0
    return _clamp01((numerator / denominator) ** (1.0 / m1))

def _hlg_eotf_norm(x: float) -> float:
    # ARIB STD-B67 / Rec.2100 HLG inverse OETF to normalized relative light.
    a = 0.17883277
    b = 0.28466892
    c = 0.55991073

    x = _clamp01(x)
    if x <= 0.5:
        return _clamp01((x * x) / 3.0)
    return _clamp01((math.exp((x - c) / a) + b) / 12.0)

def _bt1886_eotf_norm(x: float, black_level: float = 0.001) -> float:
    # Approximate BT.1886 with a fixed normalized black level, then renormalize
    # back to 0..1 so the generated curve still maps exact black to 0.
    gamma = 2.4
    white_level = 1.0
    black_level = min(max(float(black_level), 0.0), white_level * 0.25)
    x = _clamp01(x)

    if black_level <= 0.0:
        return _clamp01(x ** gamma)

    white_root = white_level ** (1.0 / gamma)
    black_root = black_level ** (1.0 / gamma)
    denominator = white_root - black_root
    if denominator <= 0.0:
        return _clamp01(x ** gamma)

    a = denominator ** gamma
    b = black_root / denominator
    luminance = a * ((x + b) ** gamma)
    normalized = (luminance - black_level) / (white_level - black_level)
    return _clamp01(normalized)

def apply_transfer_curve_norm(
    x: float,
    curve: str = "gamma",
    gamma: float = 2.2,
    shadow_lift: float = 0.0,
    shoulder: float = 0.0):
    x = _clamp01(float(x))
    gamma = max(0.05, float(gamma))
    shadow_lift = _clamp01(float(shadow_lift))
    shoulder = _clamp01(float(shoulder))

    if curve == "linear":
        y = x
    elif curve == "gamma":
        y = x ** gamma
    elif curve == "pq":
        y = _pq_eotf_norm(x)
    elif curve == "hlg":
        y = _hlg_eotf_norm(x)
    elif curve == "bt1886":
        y = _bt1886_eotf_norm(x)
    elif curve == "srgb-ish":
        # Approximate perceptual shaping for experimentation.
        if x <= 0.04045:
            y = x / 12.92
        else:
            y = ((x + 0.055) / 1.055) ** 2.4
    elif curve == "toe-gamma":
        # Soft toe before gamma shaping.
        toe = x * x * (3.0 - 2.0 * x)
        y = toe ** gamma
    else:
        y = x ** gamma

    # Shadow lift mixes in sqrt(y), which brightens low end.
    if shadow_lift > 0.0:
        y = (1.0 - shadow_lift) * y + shadow_lift * math.sqrt(max(0.0, y))

    # Shoulder compresses highlights downward without changing black point.
    if shoulder > 0.0:
        y = 1.0 - ((1.0 - y) ** (1.0 / (1.0 + shoulder)))

    return _clamp01(y)

def _build_transfer_curve_config(
    curve: str = "gamma",
    gamma: float = 2.2,
    shadow_lift: float = 0.0,
    shoulder: float = 0.0,
):
    return {
        "type": str(curve),
        "gamma": float(max(0.05, float(gamma))),
        "shadow_lift": float(_clamp01(float(shadow_lift))),
        "shoulder": float(_clamp01(float(shoulder))),
    }

def _resolve_transfer_channel_configs(
    curve: str = "gamma",
    gamma: float = 2.2,
    shadow_lift: float = 0.0,
    shoulder: float = 0.0,
    channel_configs: dict | None = None,
):
    shared = _build_transfer_curve_config(
        curve=curve,
        gamma=gamma,
        shadow_lift=shadow_lift,
        shoulder=shoulder,
    )
    resolved = {}
    for ch in CHANNELS:
        override = dict((channel_configs or {}).get(ch, {}))
        resolved[ch] = _build_transfer_curve_config(
            curve=override.get("curve", shared["type"]),
            gamma=override.get("gamma", shared["gamma"]),
            shadow_lift=override.get("shadow_lift", shared["shadow_lift"]),
            shoulder=override.get("shoulder", shared["shoulder"]),
        )
    return shared, resolved

def load_monotonic_ladder(lut_dir: Path, channel: str):
    p = lut_dir / f"{channel.lower()}_monotonic_ladder.json"
    if not p.exists():
        return []
    try:
        arr = json.loads(p.read_text(encoding="utf-8"))
        return sorted(arr, key=lambda e: int(e["output_q16"]))
    except Exception:
        return []


def _load_transfer_lut_summary(lut_dir: Path):
    summary_path = Path(lut_dir) / "lut_summary.json"
    if not summary_path.exists():
        return {}
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_transfer_peak_metadata(lut_dir: Path, peak_nits_override: float | None = None):
    override = None if peak_nits_override is None else float(peak_nits_override)
    channel_peaks = {}
    summary = _load_transfer_lut_summary(lut_dir)

    for ch in CHANNELS:
        raw_peak = ((summary or {}).get("channels", {}).get(ch, {}) or {}).get("max_estimated_nobfi_Y")
        try:
            peak = float(raw_peak)
        except Exception:
            peak = 0.0
        if peak > 0.0:
            channel_peaks[ch] = peak

    if override is not None and override > 0.0:
        reference_peak_nits = float(override)
        reference_source = "override"
    elif channel_peaks:
        reference_peak_nits = max(float(v) for v in channel_peaks.values())
        reference_source = "lut_summary"
    else:
        reference_peak_nits = 100.0
        reference_source = "fallback"

    if reference_peak_nits <= 0.0:
        reference_peak_nits = 100.0
        reference_source = "fallback"

    filled_channel_peaks = {
        ch: float(channel_peaks.get(ch, reference_peak_nits))
        for ch in CHANNELS
    }
    brightest_channel = max(filled_channel_peaks, key=lambda ch: float(filled_channel_peaks[ch])) if filled_channel_peaks else "W"

    return {
        "reference_peak_nits": float(reference_peak_nits),
        "reference_peak_source": str(reference_source),
        "brightest_channel": str(brightest_channel),
        "channel_peak_nits": filled_channel_peaks,
    }


def _resolve_transfer_nit_cap_metadata(reference_peak_nits: float, nit_cap: float | None = None):
    requested_nit_cap = None if nit_cap is None else float(nit_cap)
    reference_peak_nits = float(reference_peak_nits)

    if requested_nit_cap is None or requested_nit_cap <= 0.0 or reference_peak_nits <= 0.0:
        return {
            "enabled": False,
            "requested_nits": None,
            "effective_nits": None,
            "normalized_limit": 1.0,
        }

    effective_nits = min(float(requested_nit_cap), float(reference_peak_nits))
    normalized_limit = _clamp01(float(effective_nits) / float(reference_peak_nits))
    return {
        "enabled": True,
        "requested_nits": float(requested_nit_cap),
        "effective_nits": float(effective_nits),
        "normalized_limit": float(normalized_limit),
    }

def choose_monotonic_state(monotonic, target_q16: int, selection: str = "floor"):
    if not monotonic:
        return {"value": 0, "bfi": 0, "output_q16": 0}
    target_q16 = int(max(0, min(65535, target_q16)))
    if target_q16 <= 0:
        return {"value": 0, "bfi": 0, "output_q16": 0, "lower_value": 0, "upper_value": 0}
    if selection == "nearest":
        return min(monotonic, key=lambda e: abs(int(e["output_q16"]) - target_q16))
    # default floor selection
    best = monotonic[0]
    for e in monotonic:
        if int(e["output_q16"]) <= target_q16:
            best = e
        else:
            break
    return best

def build_transfer_curve_preview(
    lut_dir: Path,
    bucket_count: int = 4096,
    curve: str = "gamma",
    gamma: float = 2.2,
    shadow_lift: float = 0.0,
    shoulder: float = 0.0,
    selection: str = "floor",
    channel_configs: dict | None = None,
    peak_nits_override: float | None = None,
    nit_cap: float | None = None):
    requested_bucket_count = int(bucket_count)
    if requested_bucket_count > 0:
        bucket_count = max(2, requested_bucket_count)
    else:
        bucket_count = _derive_transfer_bucket_count_from_lut_dir(lut_dir)
    shared_curve, resolved_channel_curves = _resolve_transfer_channel_configs(
        curve=curve,
        gamma=gamma,
        shadow_lift=shadow_lift,
        shoulder=shoulder,
        channel_configs=channel_configs,
    )
    peak_meta = _resolve_transfer_peak_metadata(lut_dir, peak_nits_override=peak_nits_override)
    nit_cap_meta = _resolve_transfer_nit_cap_metadata(
        peak_meta["reference_peak_nits"],
        nit_cap=nit_cap,
    )
    out = {
        "format": "TemporalBFI_TransferCurve_v1",
        "curve": {
            "type": shared_curve["type"],
            "gamma": float(shared_curve["gamma"]),
            "shadow_lift": float(shared_curve["shadow_lift"]),
            "shoulder": float(shared_curve["shoulder"]),
            "selection": selection,
            "per_channel_enabled": bool(channel_configs),
            "channels": resolved_channel_curves,
            "peak_nits_override": float(peak_nits_override) if peak_nits_override is not None and float(peak_nits_override) > 0.0 else None,
            "reference_peak_nits": float(peak_meta["reference_peak_nits"]),
            "reference_peak_source": str(peak_meta["reference_peak_source"]),
            "brightest_channel": str(peak_meta["brightest_channel"]),
            "nit_cap": dict(nit_cap_meta),
        },
        "bucket_count": bucket_count,
        "channel_peak_nits": dict(peak_meta["channel_peak_nits"]),
        "channels": {},
    }

    for ch in CHANNELS:
        mono = load_monotonic_ladder(lut_dir, ch)
        curve_cfg = resolved_channel_curves[ch]
        channel_peak_nits = float(peak_meta["channel_peak_nits"].get(ch, peak_meta["reference_peak_nits"]))
        target_q16 = []
        achieved_q16 = []
        lower_values = []
        upper_values = []
        values = []
        bfis = []
        for i in range(bucket_count):
            x = i / (bucket_count - 1)
            y = apply_transfer_curve_norm(
                x,
                curve=curve_cfg["type"],
                gamma=curve_cfg["gamma"],
                shadow_lift=curve_cfg["shadow_lift"],
                shoulder=curve_cfg["shoulder"],
            )
            if nit_cap_meta["enabled"]:
                y = float(y) * float(nit_cap_meta["normalized_limit"])
            tq16 = int(round(y * 65535.0))
            state = choose_monotonic_state(mono, tq16, selection=selection)
            target_q16.append(tq16)
            achieved_q16.append(int(state.get("output_q16", 0)))
            lower_values.append(int(state.get("lower_value", 0)))
            upper_values.append(int(state.get("upper_value", state.get("value", 0))))
            values.append(int(state.get("value", state.get("upper_value", 0))))
            bfis.append(int(state.get("bfi", 0)))
        out["channels"][ch] = {
            "curve": dict(curve_cfg),
            "peak_nits": float(channel_peak_nits),
            "target_q16": target_q16,
            "achieved_q16": achieved_q16,
            "lower_value": lower_values,
            "upper_value": upper_values,
            "value": values,
            "bfi": bfis,
        }
    return out

def export_transfer_json(
    lut_dir: Path,
    out_path: Path,
    bucket_count: int = 4096,
    curve: str = "gamma",
    gamma: float = 2.2,
    shadow_lift: float = 0.0,
    shoulder: float = 0.0,
    selection: str = "floor",
    channel_configs: dict | None = None,
    peak_nits_override: float | None = None,
    nit_cap: float | None = None):
    data = build_transfer_curve_preview(
        lut_dir, bucket_count=bucket_count, curve=curve, gamma=gamma,
        shadow_lift=shadow_lift, shoulder=shoulder, selection=selection,
        channel_configs=channel_configs,
        peak_nits_override=peak_nits_override,
        nit_cap=nit_cap,
    )
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def export_transfer_header(
    lut_dir: Path,
    out_path: Path,
    bucket_count: int = 4096,
    curve: str = "gamma",
    gamma: float = 2.2,
    shadow_lift: float = 0.0,
    shoulder: float = 0.0,
    selection: str = "floor",
    channel_configs: dict | None = None,
    peak_nits_override: float | None = None,
    nit_cap: float | None = None):
    data = build_transfer_curve_preview(
        lut_dir, bucket_count=bucket_count, curve=curve, gamma=gamma,
        shadow_lift=shadow_lift, shoulder=shoulder, selection=selection,
        channel_configs=channel_configs,
        peak_nits_override=peak_nits_override,
        nit_cap=nit_cap,
    )
    resolved_bucket_count = int(data["bucket_count"])
    curve_meta = dict(data.get("curve", {}))
    nit_cap_meta = dict(curve_meta.get("nit_cap", {}))
    lines = [
        "// Auto-generated transfer curve preview header v12",
        "#pragma once",
        "",
        "namespace TemporalBFITransferCurve {",
        f"static const uint16_t BUCKET_COUNT = {resolved_bucket_count};",
        f"static constexpr float REFERENCE_PEAK_NITS = {float(curve_meta.get('reference_peak_nits', 0.0)):.6f}f;",
        f"static constexpr const char* REFERENCE_PEAK_SOURCE = \"{str(curve_meta.get('reference_peak_source', 'unknown'))}\";",
        f"static constexpr const char* BRIGHTEST_CHANNEL = \"{str(curve_meta.get('brightest_channel', 'W'))}\";",
        f"static const uint8_t NIT_CAP_ENABLED = {1 if nit_cap_meta.get('enabled', False) else 0};",
        f"static constexpr float REQUESTED_NIT_CAP = {float(nit_cap_meta.get('requested_nits') or 0.0):.6f}f;",
        f"static constexpr float EFFECTIVE_NIT_CAP = {float(nit_cap_meta.get('effective_nits') or 0.0):.6f}f;",
        f"static constexpr float NIT_CAP_NORMALIZED_LIMIT = {float(nit_cap_meta.get('normalized_limit', 1.0)):.9f}f;",
        "",
    ]
    for ch in CHANNELS:
        lines.append(f"static constexpr float PEAK_NITS_{ch} = {float(data.get('channel_peak_nits', {}).get(ch, 0.0)):.6f}f;")
    lines.append("")
    for ch in CHANNELS:
        chd = data["channels"][ch]
        lines.append(f"static const uint16_t TARGET_{ch}[{resolved_bucket_count}] = {{")
        for i in range(0, resolved_bucket_count, 16):
            lines.append("    " + ", ".join(str(v) for v in chd["target_q16"][i:i+16]) + ",")
        lines.append("};\n")
        lines.append(f"static const uint16_t ACHIEVED_{ch}[{resolved_bucket_count}] = {{")
        for i in range(0, resolved_bucket_count, 16):
            lines.append("    " + ", ".join(str(v) for v in chd["achieved_q16"][i:i+16]) + ",")
        lines.append("};\n")
        lines.append(f"static const uint8_t VALUE_{ch}[{resolved_bucket_count}] = {{")
        for i in range(0, resolved_bucket_count, 32):
            lines.append("    " + ", ".join(str(v) for v in chd["value"][i:i+32]) + ",")
        lines.append("};\n")
        lines.append(f"static const uint8_t LOWER_{ch}[{resolved_bucket_count}] = {{")
        for i in range(0, resolved_bucket_count, 32):
            lines.append("    " + ", ".join(str(v) for v in chd["lower_value"][i:i+32]) + ",")
        lines.append("};\n")
        lines.append(f"static const uint8_t UPPER_{ch}[{resolved_bucket_count}] = {{")
        for i in range(0, resolved_bucket_count, 32):
            lines.append("    " + ", ".join(str(v) for v in chd["upper_value"][i:i+32]) + ",")
        lines.append("};\n")
        lines.append(f"static const uint8_t BFI_{ch}[{resolved_bucket_count}] = {{")
        for i in range(0, resolved_bucket_count, 32):
            lines.append("    " + ", ".join(str(v) for v in chd["bfi"][i:i+32]) + ",")
        lines.append("};\n")
    lines.append("} // namespace TemporalBFITransferCurve\n")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _add_transfer_curve_parser_args(parser):
    parser.add_argument("--lut-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--bucket-count", type=int, default=4096, help="Transfer bucket count; use 0 to derive from the monotonic ladder density")
    parser.add_argument("--curve", choices=["linear", "gamma", "pq", "hlg", "bt1886", "srgb-ish", "toe-gamma"], default="gamma")
    parser.add_argument("--gamma", type=float, default=2.2, help="Used by gamma and toe-gamma curves only")
    parser.add_argument("--shadow-lift", type=float, default=0.0)
    parser.add_argument("--shoulder", type=float, default=0.0)
    parser.add_argument("--peak-nits-override", type=float, help="Optional absolute reference peak in nits. When omitted, the brightest measured channel from lut_summary.json is used")
    parser.add_argument("--nit-cap", type=float, help="Optional absolute nit cap referenced to the brightest measured channel peak. Bucket count remains unchanged")
    parser.add_argument("--selection", choices=["floor", "nearest"], default="floor")
    for ch in CHANNELS:
        suffix = ch.lower()
        parser.add_argument(f"--curve-{suffix}", dest=f"curve_{suffix}", choices=["linear", "gamma", "pq", "hlg", "bt1886", "srgb-ish", "toe-gamma"])
        parser.add_argument(f"--gamma-{suffix}", dest=f"gamma_{suffix}", type=float)
        parser.add_argument(f"--shadow-lift-{suffix}", dest=f"shadow_lift_{suffix}", type=float)
        parser.add_argument(f"--shoulder-{suffix}", dest=f"shoulder_{suffix}", type=float)


def _collect_transfer_channel_cli_overrides(args):
    channel_configs = {}
    for ch in CHANNELS:
        suffix = ch.lower()
        curve = getattr(args, f"curve_{suffix}", None)
        gamma = getattr(args, f"gamma_{suffix}", None)
        shadow_lift = getattr(args, f"shadow_lift_{suffix}", None)
        shoulder = getattr(args, f"shoulder_{suffix}", None)
        if curve is None and gamma is None and shadow_lift is None and shoulder is None:
            continue
        cfg = {}
        if curve is not None:
            cfg["curve"] = curve
        if gamma is not None:
            cfg["gamma"] = gamma
        if shadow_lift is not None:
            cfg["shadow_lift"] = shadow_lift
        if shoulder is not None:
            cfg["shoulder"] = shoulder
        channel_configs[ch] = cfg
    return channel_configs or None



def _normalize_weights(raw: dict[str, float]):
    total = sum(max(0.0, float(raw.get(ch, 0.0))) for ch in CHANNELS)
    if total <= 0.0:
        floats = {ch: 0.0 for ch in CHANNELS}
        q16 = {ch: 0 for ch in CHANNELS}
        return floats, q16
    floats = {ch: max(0.0, float(raw.get(ch, 0.0))) / total for ch in CHANNELS}
    q16 = {ch: int(round(floats[ch] * 65535.0)) for ch in CHANNELS}
    # force exact sum to 65535
    diff = 65535 - sum(q16.values())
    if diff != 0:
        # adjust the strongest contributor so we preserve ordering as much as possible
        target = max(CHANNELS, key=lambda ch: floats[ch])
        q16[target] = max(0, q16[target] + diff)
    return floats, q16


def compute_luma_weights(measure_dir: Path, method: str = "average", bfi_source: str = "all"):
    measurements = load_patch_measurements(measure_dir)
    channel_values = {ch: [] for ch in CHANNELS}
    used_rows = []

    bfi_filter = None if str(bfi_source).lower() == "all" else int(bfi_source)

    for row in measurements:
        active = [(ch, row[ch.lower()], row[f"bfi_{ch.lower()}"]) for ch in CHANNELS if row[ch.lower()] > 0]
        if len(active) != 1:
            continue
        ch, value, bfi = active[0]
        if bfi_filter is not None and int(bfi) != bfi_filter:
            continue
        y = float(row["Y"])
        channel_values[ch].append(y)
        used_rows.append({"channel": ch, "value": int(value), "bfi": int(bfi), "Y": y, "name": row.get("name", "")})

    raw = {}
    stats = {}
    for ch in CHANNELS:
        vals = sorted(channel_values[ch])
        if not vals:
            raw[ch] = 0.0
            stats[ch] = {"samples": 0, "method_value": 0.0, "min_Y": None, "max_Y": None, "avg_Y": None, "median_Y": None}
            continue
        if method == "max":
            m = vals[-1]
        elif method == "median":
            m = vals[len(vals)//2]
        else:
            m = sum(vals) / len(vals)
        raw[ch] = float(m)
        stats[ch] = {
            "samples": len(vals),
            "method_value": float(m),
            "min_Y": float(vals[0]),
            "max_Y": float(vals[-1]),
            "avg_Y": float(sum(vals) / len(vals)),
            "median_Y": float(vals[len(vals)//2]),
        }

    floats, q16 = _normalize_weights(raw)
    return {
        "format": "TemporalBFI_LumaWeights_v1",
        "method": method,
        "bfi_source": bfi_source,
        "raw": raw,
        "normalized_float": floats,
        "normalized_q16": q16,
        "stats": stats,
        "measurement_count": len(used_rows),
    }


def export_luma_weights_json(measure_dir: Path, out_path: Path, method: str = "average", bfi_source: str = "all"):
    data = compute_luma_weights(measure_dir, method=method, bfi_source=bfi_source)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def export_luma_weights_header(measure_dir: Path, out_path: Path, method: str = "average", bfi_source: str = "all"):
    data = compute_luma_weights(measure_dir, method=method, bfi_source=bfi_source)
    f = data["normalized_float"]
    q = data["normalized_q16"]
    lines = [
        "// Auto-generated luma weights header v12",
        "#pragma once",
        "",
        "namespace TemporalBFILumaWeights {",
        f"static constexpr const char* METHOD = \"{data['method']}\";",
        f"static constexpr const char* BFI_SOURCE = \"{data['bfi_source']}\";",
        "",
        f"static constexpr float lumaWeightR = {f['R']:.9f}f;",
        f"static constexpr float lumaWeightG = {f['G']:.9f}f;",
        f"static constexpr float lumaWeightB = {f['B']:.9f}f;",
        f"static constexpr float lumaWeightW = {f['W']:.9f}f;",
        "",
        f"static constexpr uint16_t lumaWeightR_Q16 = {q['R']};",
        f"static constexpr uint16_t lumaWeightG_Q16 = {q['G']};",
        f"static constexpr uint16_t lumaWeightB_Q16 = {q['B']};",
        f"static constexpr uint16_t lumaWeightW_Q16 = {q['W']};",
        "",
        "// Example usage:",
        "// uint32_t Y = r * lumaWeightR_Q16 + g * lumaWeightG_Q16 + b * lumaWeightB_Q16 + w * lumaWeightW_Q16;",
        "} // namespace TemporalBFILumaWeights",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser(
        description="Temporal LUT + patch calibration + transfer curve + luma weights tool v14"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_plan = sub.add_parser("plan")
    ap_plan.add_argument("--channel", choices=CHANNELS + ["ALL"], required=True)
    ap_plan.add_argument("--out", required=True)
    ap_plan.add_argument("--max-bfi", type=int, default=4)
    ap_plan.add_argument("--step", type=int, default=0)
    ap_plan.add_argument(
        "--mode",
        choices=["bfi", "temporal-blend"],
        default="bfi",
        help="Raw ladder capture mode: black-frame insertion or temporal blending with a non-black floor",
    )
    ap_plan.add_argument(
        "--floor-step",
        type=int,
        help="Optional floor-code spacing for temporal-blend mode. Defaults to --step when omitted.",
    )
    ap_plan.add_argument(
        "--preset",
        choices=PLAN_PRESET_OPTIONS,
        default="custom",
        help="Optional measurement-plan preset. targeted-16bit is tuned for temporal-blend capture density without step=1 explosion.",
    )

    ap_build = sub.add_parser("build")
    ap_build.add_argument("--measure-dir", required=True)
    ap_build.add_argument("--out-dir", required=True)

    ap_export_json = sub.add_parser("export-runtime-json")
    ap_export_json.add_argument("--lut-dir", required=True)
    ap_export_json.add_argument("--out", required=True)

    ap_export_hdr = sub.add_parser("export-runtime-header")
    ap_export_hdr.add_argument("--lut-dir", required=True)
    ap_export_hdr.add_argument("--out", required=True)

    ap_export_solver = sub.add_parser("export-solver-header")
    ap_export_solver.add_argument("--lut-dir", required=True)
    ap_export_solver.add_argument("--out", required=True)
    ap_export_solver.add_argument("--max-bfi", type=int, default=4)
    ap_export_solver.add_argument("--max-entries", type=int, default=None,
                                  help="Max ladder entries per channel (e.g. 4096 for 12-bit); omit for full ladder")

    ap_export_solver_precomputed = sub.add_parser("export-precomputed-solver-luts-header")
    ap_export_solver_precomputed.add_argument("--solver-header", required=True)
    ap_export_solver_precomputed.add_argument("--calibration-header", required=True)
    ap_export_solver_precomputed.add_argument("--out", required=True)
    ap_export_solver_precomputed.add_argument("--max-bfi", type=int)
    ap_export_solver_precomputed.add_argument("--solver-fixed-bfi-levels", type=int)
    ap_export_solver_precomputed.add_argument("--solver-lut-size", type=int, default=0, help="Precomputed solver LUT size; use 0 to derive from the solver ladder counts")
    ap_export_solver_precomputed.add_argument("--min-error-q16", type=int, default=64)
    ap_export_solver_precomputed.add_argument("--relative-error-divisor", type=int, default=24)
    ap_export_solver_precomputed.add_argument("--min-value-ratio-numerator", type=int, default=3)
    ap_export_solver_precomputed.add_argument("--min-value-ratio-denominator", type=int, default=8)
    ap_export_solver_precomputed.add_argument("--low-end-protect-threshold", type=int, default=48)
    ap_export_solver_precomputed.add_argument("--low-end-max-drop", type=int, default=10)
    ap_export_solver_precomputed.add_argument("--disable-prefer-higher-bfi", action="store_true")
    ap_export_solver_precomputed.add_argument("--preferred-min-bfi", type=int, default=0)
    ap_export_solver_precomputed.add_argument("--highlight-bypass-start", type=int, default=240)

    ap_patch = sub.add_parser("patch-plan")
    ap_patch.add_argument("--preset", choices=sorted(PATCH_PRESETS.keys()), required=True)
    ap_patch.add_argument("--out", required=True)
    ap_patch.add_argument("--max-bfi", type=int, default=4)
    ap_patch.add_argument("--no-grays", action="store_true")
    ap_patch.add_argument("--no-mixed", action="store_true")
    ap_patch.add_argument(
        "--include-secondary-ramp",
        action="store_true",
        help="Add a dense secondary mixed-color ramp sweep on top of the preset.",
    )
    ap_patch.add_argument(
        "--repeats",
        type=int,
        help="Override repeats count for each patch row (must be >= 1).",
    )

    ap_cal_json = sub.add_parser("export-calibration-json")
    ap_cal_json.add_argument("--measure-dir", required=True)
    ap_cal_json.add_argument("--out", required=True)
    ap_cal_json.add_argument("--max-bfi", type=int, default=4)
    ap_cal_json.add_argument("--profile-source-bfi", type=int, default=0)
    ap_cal_json.add_argument(
        "--white-policy",
        choices=["disabled", "near-neutral", "always", "white-priority", "measured-optimal"],
        default="near-neutral",
    )
    ap_cal_json.add_argument("--mixing-profile", choices=sorted(MIXING_PRESETS.keys()), default="balanced")
    ap_cal_json.add_argument("--neutral-threshold-q16", type=int)
    ap_cal_json.add_argument("--white-weight-q16", type=int)
    ap_cal_json.add_argument("--rgb-weight-q16", type=int)
    ap_cal_json.add_argument("--white-channel-scale", type=float, default=1.0)
    ap_cal_json.add_argument("--white-channel-gamma", type=float, default=1.0)
    ap_cal_json.add_argument("--auto-white-scale", action="store_true")
    ap_cal_json.add_argument("--auto-white-target-ratio", type=float, default=1.35)
    ap_cal_json.add_argument("--auto-white-min-code", type=int, default=24)
    ap_cal_json.add_argument(
        "--profile-target",
        choices=["legacy-measured", "linear", "gamma", "perceptual-density", "delta-preserving"],
        default="delta-preserving",
        help="Target curve for profile LUTs (perceptual-density is a measured-preserving, density-safer mode; legacy-measured preserves old behavior)",
    )
    ap_cal_json.add_argument("--profile-target-gamma", type=float, default=2.2)
    ap_cal_json.add_argument("--disable-black-level-compensation", action="store_true")
    ap_cal_json.add_argument("--black-level-y", type=float)

    ap_cal_hdr = sub.add_parser("export-calibration-header")
    ap_cal_hdr.add_argument("--measure-dir", required=True)
    ap_cal_hdr.add_argument("--out", required=True)
    ap_cal_hdr.add_argument("--max-bfi", type=int, default=4)
    ap_cal_hdr.add_argument("--profile-source-bfi", type=int, default=0)
    ap_cal_hdr.add_argument(
        "--white-policy",
        choices=["disabled", "near-neutral", "always", "white-priority", "measured-optimal"],
        default="near-neutral",
    )
    ap_cal_hdr.add_argument("--mixing-profile", choices=sorted(MIXING_PRESETS.keys()), default="balanced")
    ap_cal_hdr.add_argument("--neutral-threshold-q16", type=int)
    ap_cal_hdr.add_argument("--white-weight-q16", type=int)
    ap_cal_hdr.add_argument("--rgb-weight-q16", type=int)
    ap_cal_hdr.add_argument("--white-channel-scale", type=float, default=1.0)
    ap_cal_hdr.add_argument("--white-channel-gamma", type=float, default=1.0)
    ap_cal_hdr.add_argument("--auto-white-scale", action="store_true")
    ap_cal_hdr.add_argument("--auto-white-target-ratio", type=float, default=1.35)
    ap_cal_hdr.add_argument("--auto-white-min-code", type=int, default=24)
    ap_cal_hdr.add_argument(
        "--profile-target",
        choices=["legacy-measured", "linear", "gamma", "perceptual-density"],
        default="perceptual-density",
        help="Target curve for profile LUTs (perceptual-density is a measured-preserving, density-safer mode; legacy-measured preserves old behavior)",
    )
    ap_cal_hdr.add_argument("--profile-target-gamma", type=float, default=2.2)
    ap_cal_hdr.add_argument("--disable-black-level-compensation", action="store_true")
    ap_cal_hdr.add_argument("--black-level-y", type=float)
    ap_cal_hdr.add_argument(
        "--web-report",
        help="Optional HTML color report path (default: <out>_web_report.html)",
    )
    ap_cal_hdr.add_argument(
        "--no-web-report",
        action="store_true",
        help="Skip HTML color sanity report generation",
    )

    ap_patch_true16 = sub.add_parser("patch-plan-true16")
    ap_patch_true16.add_argument("--out", required=True)
    ap_patch_true16.add_argument(
        "--density",
        choices=["quick", "medium", "fine", "ultra"],
        default="medium",
        help="Sample density for Q16 sweeps (quick ~200, medium ~500, fine ~1000, ultra ~2000 samples)",
    )
    ap_patch_true16.add_argument(
        "--no-gray-ramp",
        action="store_true",
        help="Skip neutral RGB gray ramp samples",
    )
    ap_patch_true16.add_argument(
        "--no-primary-ramps",
        action="store_true",
        help="Skip individual R, G, B, W ramps",
    )
    ap_patch_true16.add_argument(
        "--no-mid-colors",
        action="store_true",
        help="Skip mid-level color combination samples",
    )
    ap_patch_true16.add_argument(
        "--no-white-protection-mixes",
        action="store_true",
        help="Skip RGB+W neutral and warm protection samples used to detect white blowout",
    )
    ap_patch_true16.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Repeat count to stamp into each True16 patch row (must be >= 1)",
    )

    ap_patch_temporal_blend = sub.add_parser("patch-plan-temporal-blend")
    ap_patch_temporal_blend.add_argument("--out", required=True)
    ap_patch_temporal_blend.add_argument(
        "--density",
        choices=["quick", "medium", "fine", "ultra"],
        default="medium",
        help="Anchor density for lower/high blend endpoints",
    )
    ap_patch_temporal_blend.add_argument("--cycle-length", type=int, default=5)
    ap_patch_temporal_blend.add_argument("--no-gray-ramp", action="store_true")
    ap_patch_temporal_blend.add_argument("--no-primary-pairs", action="store_true")
    ap_patch_temporal_blend.add_argument("--no-mixed-pairs", action="store_true")
    ap_patch_temporal_blend.add_argument("--repeats", type=int, default=1)

    ap_cal_true16_hdr = sub.add_parser("export-calibration-true16-header")
    ap_cal_true16_hdr.add_argument("--measure-dir", required=True)
    ap_cal_true16_hdr.add_argument("--out", required=True)
    ap_cal_true16_hdr.add_argument(
        "--lut-size",
        type=int,
        default=4096,
        help="Size of 16->16 LUT tables; use 0 to derive from the captured single-channel input density",
    )
    ap_cal_true16_hdr.add_argument(
        "--input-glob",
        dest="input_globs",
        action="append",
        help="Optional glob(s) for capture CSV selection. Can be repeated.",
    )
    ap_cal_true16_hdr.add_argument(
        "--aggregate",
        choices=["mean", "median", "trimmed"],
        default="median",
        help="Aggregation mode for repeated samples at the same input",
    )
    ap_cal_true16_hdr.add_argument("--trim-fraction", type=float, default=0.1)
    ap_cal_true16_hdr.add_argument("--outlier-sigma", type=float, default=3.5)
    ap_cal_true16_hdr.add_argument("--disable-monotonic", action="store_true")
    ap_cal_true16_hdr.add_argument("--white-channel-scale", type=float, default=1.0)
    ap_cal_true16_hdr.add_argument("--white-channel-gamma", type=float, default=1.0)
    ap_cal_true16_hdr.add_argument("--auto-white-scale", action="store_true")
    ap_cal_true16_hdr.add_argument("--neutral-tolerance-q16", type=int, default=2048)
    ap_cal_true16_hdr.add_argument(
        "--profile-target",
        choices=["legacy-measured", "linear", "gamma", "perceptual-density", "delta-preserving"],
        default="delta-preserving",
        help="Target curve for Q16 calibration LUTs (delta-preserving keeps the LUT anchored near identity before mixed-patch correction)",
    )
    ap_cal_true16_hdr.add_argument("--profile-target-gamma", type=float, default=2.2)
    ap_cal_true16_hdr.add_argument("--disable-black-level-compensation", action="store_true")
    ap_cal_true16_hdr.add_argument("--black-level-y", type=float)
    ap_cal_true16_hdr.add_argument("--disable-inverse-regularization", action="store_true")
    ap_cal_true16_hdr.add_argument(
        "--inverse-max-step-q16",
        type=int,
        help="Optional max per-index command step for inverse LUT regularization",
    )
    ap_cal_true16_hdr.add_argument("--disable-mixed-patch-correction", action="store_true")
    ap_cal_true16_hdr.add_argument("--mixed-correction-strength", type=float, default=0.65)
    ap_cal_true16_hdr.add_argument("--mixed-backbone-lock-strength", type=float, default=0.55)
    ap_cal_true16_hdr.add_argument("--mixed-locality-width", type=int, default=24)
    ap_cal_true16_hdr.add_argument("--mixed-neutral-protection-strength", type=float, default=0.75)
    ap_cal_true16_hdr.add_argument("--mixed-warm-priority", type=float, default=0.35)
    ap_cal_true16_hdr.add_argument("--mixed-gamut-edge-restraint", type=float, default=0.45)
    ap_cal_true16_hdr.add_argument(
        "--disable-global-mixed-fit",
        action="store_true",
        help="Disable post-inversion global mixed-patch fit (keeps strictly pre-fit LUT shaping)",
    )
    ap_cal_true16_hdr.add_argument(
        "--global-mixed-fit-max-iterations",
        type=int,
        default=5,
        help="Coordinate-descent iteration budget for global mixed-patch fit",
    )
    ap_cal_true16_hdr.add_argument(
        "--global-mixed-fit-peak-preserve-strength",
        type=float,
        default=0.0,
        help="Optional soft penalty strength to preserve high-end channel scale during global mixed-patch fit",
    )
    ap_cal_true16_hdr.add_argument(
        "--transfer-curve-header",
        help="Optional transfer-curve header to compute additional post-curve runtime QA/reporting",
    )
    ap_cal_true16_hdr.add_argument(
        "--qa-report",
        help="Optional JSON report path with fit quality, mixed-patch residuals, and warnings",
    )
    ap_cal_true16_hdr.add_argument(
        "--web-report",
        help="Optional HTML color report path (default: <out>_web_report.html)",
    )
    ap_cal_true16_hdr.add_argument(
        "--no-web-report",
        action="store_true",
        help="Skip HTML color sanity report generation",
    )

    ap_cal_true16_report = sub.add_parser("analyze-calibration-true16")
    ap_cal_true16_report.add_argument("--measure-dir", required=True)
    ap_cal_true16_report.add_argument("--out", required=True)
    ap_cal_true16_report.add_argument("--lut-size", type=int, default=4096, help="Size of 16->16 LUT tables; use 0 to derive from the captured single-channel input density")
    ap_cal_true16_report.add_argument(
        "--input-glob",
        dest="input_globs",
        action="append",
        help="Optional glob(s) for capture CSV selection. Can be repeated.",
    )
    ap_cal_true16_report.add_argument(
        "--aggregate",
        choices=["mean", "median", "trimmed"],
        default="median",
    )
    ap_cal_true16_report.add_argument("--trim-fraction", type=float, default=0.1)
    ap_cal_true16_report.add_argument("--outlier-sigma", type=float, default=3.5)
    ap_cal_true16_report.add_argument("--disable-monotonic", action="store_true")
    ap_cal_true16_report.add_argument("--white-channel-scale", type=float, default=1.0)
    ap_cal_true16_report.add_argument("--white-channel-gamma", type=float, default=1.0)
    ap_cal_true16_report.add_argument("--auto-white-scale", action="store_true")
    ap_cal_true16_report.add_argument("--neutral-tolerance-q16", type=int, default=2048)
    ap_cal_true16_report.add_argument(
        "--profile-target",
        choices=["legacy-measured", "linear", "gamma", "perceptual-density"],
        default="perceptual-density",
    )
    ap_cal_true16_report.add_argument("--profile-target-gamma", type=float, default=2.2)
    ap_cal_true16_report.add_argument("--disable-black-level-compensation", action="store_true")
    ap_cal_true16_report.add_argument("--black-level-y", type=float)
    ap_cal_true16_report.add_argument("--disable-inverse-regularization", action="store_true")
    ap_cal_true16_report.add_argument(
        "--inverse-max-step-q16",
        type=int,
        help="Optional max per-index command step for inverse LUT regularization",
    )
    ap_cal_true16_report.add_argument("--disable-mixed-patch-correction", action="store_true")
    ap_cal_true16_report.add_argument("--mixed-correction-strength", type=float, default=0.65)
    ap_cal_true16_report.add_argument("--mixed-backbone-lock-strength", type=float, default=0.55)
    ap_cal_true16_report.add_argument("--mixed-locality-width", type=int, default=24)
    ap_cal_true16_report.add_argument("--mixed-neutral-protection-strength", type=float, default=0.75)
    ap_cal_true16_report.add_argument("--mixed-warm-priority", type=float, default=0.35)
    ap_cal_true16_report.add_argument("--mixed-gamut-edge-restraint", type=float, default=0.45)
    ap_cal_true16_report.add_argument(
        "--disable-global-mixed-fit",
        action="store_true",
        help="Disable post-inversion global mixed-patch fit",
    )
    ap_cal_true16_report.add_argument(
        "--global-mixed-fit-max-iterations",
        type=int,
        default=5,
        help="Coordinate-descent iteration budget for global mixed-patch fit",
    )
    ap_cal_true16_report.add_argument(
        "--global-mixed-fit-peak-preserve-strength",
        type=float,
        default=0.0,
        help="Optional soft penalty strength to preserve high-end channel scale during global mixed-patch fit",
    )
    ap_cal_true16_report.add_argument(
        "--transfer-curve-header",
        help="Optional transfer-curve header to compute additional post-curve runtime QA/reporting",
    )

    ap_transfer_json = sub.add_parser("export-transfer-json")
    _add_transfer_curve_parser_args(ap_transfer_json)

    ap_transfer_hdr = sub.add_parser("export-transfer-header")
    _add_transfer_curve_parser_args(ap_transfer_hdr)

    ap_luma_json = sub.add_parser("export-luma-weights-json")
    ap_luma_json.add_argument("--measure-dir", required=True)
    ap_luma_json.add_argument("--out", required=True)
    ap_luma_json.add_argument("--method", choices=["average", "max", "median"], default="average")
    ap_luma_json.add_argument("--bfi-source", default="all")

    ap_luma_hdr = sub.add_parser("export-luma-weights-header")
    ap_luma_hdr.add_argument("--measure-dir", required=True)
    ap_luma_hdr.add_argument("--out", required=True)
    ap_luma_hdr.add_argument("--method", choices=["average", "max", "median"], default="average")
    ap_luma_hdr.add_argument("--bfi-source", default="all")

    args = ap.parse_args()

    if args.cmd == "plan":
        if args.mode == "temporal-blend":
            if args.preset == "targeted-16bit":
                rows = write_temporal_blend_plan_targeted16(
                    args.channel,
                    Path(args.out),
                    max_bfi=args.max_bfi,
                )
            else:
                rows = write_temporal_blend_plan(
                    args.channel,
                    Path(args.out),
                    max_bfi=args.max_bfi,
                    step=args.step,
                    floor_step=args.floor_step,
                )
        else:
            rows = write_plan(args.channel, Path(args.out), max_bfi=args.max_bfi, step=args.step)
        print(json.dumps({"ok": True, "rows": len(rows), "out": args.out, "step": args.step, "mode": args.mode, "floor_step": args.floor_step, "preset": args.preset}, indent=2))
    elif args.cmd == "build":
        print(json.dumps(build_luts(Path(args.measure_dir), Path(args.out_dir)), indent=2))
    elif args.cmd == "export-runtime-json":
        export_runtime_json(Path(args.lut_dir), Path(args.out))
        print(json.dumps({"ok": True, "out": args.out}, indent=2))
    elif args.cmd == "export-runtime-header":
        export_runtime_header(Path(args.lut_dir), Path(args.out))
        print(json.dumps({"ok": True, "out": args.out}, indent=2))
    elif args.cmd == "export-solver-header":
        export_solver_header(Path(args.lut_dir), Path(args.out), args.max_bfi,
                            max_entries=args.max_entries)
        print(json.dumps({"ok": True, "out": args.out}, indent=2))
    elif args.cmd == "export-precomputed-solver-luts-header":
        result = export_precomputed_solver_luts_header(
            Path(args.solver_header),
            Path(args.calibration_header),
            Path(args.out),
            max_bfi=args.max_bfi,
            solver_fixed_bfi_levels=args.solver_fixed_bfi_levels,
            solver_lut_size=args.solver_lut_size if args.solver_lut_size and args.solver_lut_size > 0 else None,
            min_error_q16=args.min_error_q16,
            relative_error_divisor=args.relative_error_divisor,
            min_value_ratio_numerator=args.min_value_ratio_numerator,
            min_value_ratio_denominator=args.min_value_ratio_denominator,
            low_end_protect_threshold=args.low_end_protect_threshold,
            low_end_max_drop=args.low_end_max_drop,
            prefer_higher_bfi=not args.disable_prefer_higher_bfi,
            preferred_min_bfi=args.preferred_min_bfi,
            highlight_bypass_start=args.highlight_bypass_start,
        )
        print(json.dumps({"ok": True, **result}, indent=2))
    elif args.cmd == "patch-plan":
        if args.repeats is not None and args.repeats < 1:
            ap.error("--repeats must be >= 1")
        rows = write_patch_plan(
            Path(args.out),
            args.preset,
            max_bfi=args.max_bfi,
            include_grays=not args.no_grays,
            include_mixed=not args.no_mixed,
            include_secondary_ramp=args.include_secondary_ramp,
            repeats_override=args.repeats,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "rows": len(rows),
                    "preset": args.preset,
                    "max_bfi": args.max_bfi,
                    "include_secondary_ramp": bool(args.include_secondary_ramp),
                    "repeats": int(args.repeats) if args.repeats is not None else PATCH_PRESETS[args.preset]["repeats"],
                    "out": args.out,
                },
                indent=2,
            )
        )
    elif args.cmd == "export-calibration-json":
        export_calibration_json(
            Path(args.measure_dir),
            Path(args.out),
            args.white_policy,
            max_bfi=args.max_bfi,
            profile_source_bfi=args.profile_source_bfi,
            mixing_profile=args.mixing_profile,
            neutral_threshold_q16=args.neutral_threshold_q16,
            white_weight_q16=args.white_weight_q16,
            rgb_weight_q16=args.rgb_weight_q16,
            white_channel_scale=args.white_channel_scale,
            white_channel_gamma=args.white_channel_gamma,
            auto_white_scale=args.auto_white_scale,
            auto_white_target_ratio=args.auto_white_target_ratio,
            auto_white_min_code=args.auto_white_min_code,
            profile_target=args.profile_target,
            profile_target_gamma=args.profile_target_gamma,
            enable_black_level_compensation=not args.disable_black_level_compensation,
            black_level_y=args.black_level_y,
        )
        print(json.dumps({"ok": True, "out": args.out}, indent=2))
    elif args.cmd == "export-calibration-header":
        web_report_path = export_calibration_header(
            Path(args.measure_dir),
            Path(args.out),
            args.white_policy,
            max_bfi=args.max_bfi,
            profile_source_bfi=args.profile_source_bfi,
            mixing_profile=args.mixing_profile,
            neutral_threshold_q16=args.neutral_threshold_q16,
            white_weight_q16=args.white_weight_q16,
            rgb_weight_q16=args.rgb_weight_q16,
            white_channel_scale=args.white_channel_scale,
            white_channel_gamma=args.white_channel_gamma,
            auto_white_scale=args.auto_white_scale,
            auto_white_target_ratio=args.auto_white_target_ratio,
            auto_white_min_code=args.auto_white_min_code,
            profile_target=args.profile_target,
            profile_target_gamma=args.profile_target_gamma,
            enable_black_level_compensation=not args.disable_black_level_compensation,
            black_level_y=args.black_level_y,
            web_report_out=Path(args.web_report) if args.web_report else None,
            generate_web_report=not args.no_web_report,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "out": args.out,
                    "web_report": str(web_report_path) if web_report_path is not None else None,
                },
                indent=2,
            )
        )
    elif args.cmd == "patch-plan-true16":
        if args.repeats < 1:
            ap.error("--repeats must be >= 1")
        rows = write_patch_plan_true16(
            Path(args.out),
            density=args.density,
            include_gray_ramp=not args.no_gray_ramp,
            include_primary_ramps=not args.no_primary_ramps,
            include_mid_colors=not args.no_mid_colors,
            include_white_protection_mixes=not args.no_white_protection_mixes,
            repeats_override=args.repeats,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "rows": len(rows),
                    "density": args.density,
                    "repeats": int(args.repeats),
                    "include_white_protection_mixes": not args.no_white_protection_mixes,
                    "out": args.out,
                },
                indent=2,
            )
        )
    elif args.cmd == "patch-plan-temporal-blend":
        if args.repeats < 1:
            ap.error("--repeats must be >= 1")
        if args.cycle_length < 2:
            ap.error("--cycle-length must be >= 2")
        rows = write_patch_plan_temporal_blend(
            Path(args.out),
            density=args.density,
            cycle_length=args.cycle_length,
            include_gray_ramp=not args.no_gray_ramp,
            include_primary_pairs=not args.no_primary_pairs,
            include_mixed_pairs=not args.no_mixed_pairs,
            repeats_override=args.repeats,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "rows": len(rows),
                    "density": args.density,
                    "cycle_length": args.cycle_length,
                    "repeats": int(args.repeats),
                    "out": args.out,
                },
                indent=2,
            )
        )
    elif args.cmd == "export-calibration-true16-header":
        if args.inverse_max_step_q16 is not None and args.inverse_max_step_q16 < 1:
            ap.error("--inverse-max-step-q16 must be >= 1")
        if args.global_mixed_fit_max_iterations is not None and args.global_mixed_fit_max_iterations < 1:
            ap.error("--global-mixed-fit-max-iterations must be >= 1")
        if args.global_mixed_fit_peak_preserve_strength is not None and args.global_mixed_fit_peak_preserve_strength < 0.0:
            ap.error("--global-mixed-fit-peak-preserve-strength must be >= 0")
        resolved_lut_size = _resolve_true16_lut_size(
            Path(args.measure_dir),
            args.lut_size,
            input_globs=args.input_globs,
            transfer_curve_header=Path(args.transfer_curve_header) if args.transfer_curve_header else None,
        )
        web_report_path = export_calibration_true16_header(
            Path(args.measure_dir),
            Path(args.out),
            lut_size=resolved_lut_size,
            input_globs=args.input_globs,
            aggregation=args.aggregate,
            trim_fraction=args.trim_fraction,
            outlier_sigma=args.outlier_sigma,
            enforce_monotonic=not args.disable_monotonic,
            white_channel_scale=args.white_channel_scale,
            white_channel_gamma=args.white_channel_gamma,
            auto_white_scale=args.auto_white_scale,
            neutral_tolerance_q16=args.neutral_tolerance_q16,
            profile_target=args.profile_target,
            profile_target_gamma=args.profile_target_gamma,
            enable_black_level_compensation=not args.disable_black_level_compensation,
            black_level_y=args.black_level_y,
            enable_inverse_regularization=not args.disable_inverse_regularization,
            inverse_max_step_q16=args.inverse_max_step_q16,
            enable_mixed_patch_correction=not args.disable_mixed_patch_correction,
            mixed_correction_strength=args.mixed_correction_strength,
            mixed_backbone_lock_strength=args.mixed_backbone_lock_strength,
            mixed_locality_width=args.mixed_locality_width,
            mixed_neutral_protection_strength=args.mixed_neutral_protection_strength,
            mixed_warm_priority=args.mixed_warm_priority,
            mixed_gamut_edge_restraint=args.mixed_gamut_edge_restraint,
            enable_global_mixed_fit=not args.disable_global_mixed_fit,
            global_mixed_fit_max_iterations=args.global_mixed_fit_max_iterations,
            global_mixed_fit_peak_preserve_strength=args.global_mixed_fit_peak_preserve_strength,
            transfer_curve_header=Path(args.transfer_curve_header) if args.transfer_curve_header else None,
            qa_report_out=Path(args.qa_report) if args.qa_report else None,
            web_report_out=Path(args.web_report) if args.web_report else None,
            generate_web_report=not args.no_web_report,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "out": args.out,
                    "lut_size": int(resolved_lut_size),
                    "aggregate": args.aggregate,
                    "qa_report": args.qa_report,
                    "web_report": str(web_report_path) if web_report_path is not None else None,
                },
                indent=2,
            )
        )
    elif args.cmd == "analyze-calibration-true16":
        if args.inverse_max_step_q16 is not None and args.inverse_max_step_q16 < 1:
            ap.error("--inverse-max-step-q16 must be >= 1")
        if args.global_mixed_fit_max_iterations is not None and args.global_mixed_fit_max_iterations < 1:
            ap.error("--global-mixed-fit-max-iterations must be >= 1")
        if args.global_mixed_fit_peak_preserve_strength is not None and args.global_mixed_fit_peak_preserve_strength < 0.0:
            ap.error("--global-mixed-fit-peak-preserve-strength must be >= 0")
        artifacts = analyze_calibration_true16(
            Path(args.measure_dir),
            Path(args.out),
            lut_size=args.lut_size,
            input_globs=args.input_globs,
            aggregation=args.aggregate,
            trim_fraction=args.trim_fraction,
            outlier_sigma=args.outlier_sigma,
            enforce_monotonic=not args.disable_monotonic,
            white_channel_scale=args.white_channel_scale,
            white_channel_gamma=args.white_channel_gamma,
            auto_white_scale=args.auto_white_scale,
            neutral_tolerance_q16=args.neutral_tolerance_q16,
            profile_target=args.profile_target,
            profile_target_gamma=args.profile_target_gamma,
            enable_black_level_compensation=not args.disable_black_level_compensation,
            black_level_y=args.black_level_y,
            enable_inverse_regularization=not args.disable_inverse_regularization,
            inverse_max_step_q16=args.inverse_max_step_q16,
            enable_mixed_patch_correction=not args.disable_mixed_patch_correction,
            mixed_correction_strength=args.mixed_correction_strength,
            mixed_backbone_lock_strength=args.mixed_backbone_lock_strength,
            mixed_locality_width=args.mixed_locality_width,
            mixed_neutral_protection_strength=args.mixed_neutral_protection_strength,
            mixed_warm_priority=args.mixed_warm_priority,
            mixed_gamut_edge_restraint=args.mixed_gamut_edge_restraint,
            enable_global_mixed_fit=not args.disable_global_mixed_fit,
            global_mixed_fit_max_iterations=args.global_mixed_fit_max_iterations,
            global_mixed_fit_peak_preserve_strength=args.global_mixed_fit_peak_preserve_strength,
            transfer_curve_header=Path(args.transfer_curve_header) if args.transfer_curve_header else None,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "out": args.out,
                    "measurement_count": artifacts["measurement_count"],
                    "warnings": artifacts["warnings"],
                },
                indent=2,
            )
        )
    elif args.cmd == "export-transfer-json":
        channel_configs = _collect_transfer_channel_cli_overrides(args)
        export_transfer_json(
            Path(args.lut_dir),
            Path(args.out),
            bucket_count=args.bucket_count,
            curve=args.curve,
            gamma=args.gamma,
            shadow_lift=args.shadow_lift,
            shoulder=args.shoulder,
            selection=args.selection,
            channel_configs=channel_configs,
            peak_nits_override=args.peak_nits_override,
            nit_cap=args.nit_cap,
        )
        print(json.dumps({"ok": True, "out": args.out}, indent=2))
    elif args.cmd == "export-transfer-header":
        channel_configs = _collect_transfer_channel_cli_overrides(args)
        export_transfer_header(
            Path(args.lut_dir),
            Path(args.out),
            bucket_count=args.bucket_count,
            curve=args.curve,
            gamma=args.gamma,
            shadow_lift=args.shadow_lift,
            shoulder=args.shoulder,
            selection=args.selection,
            channel_configs=channel_configs,
            peak_nits_override=args.peak_nits_override,
            nit_cap=args.nit_cap,
        )
        print(json.dumps({"ok": True, "out": args.out}, indent=2))
    elif args.cmd == "export-luma-weights-json":
        export_luma_weights_json(
            Path(args.measure_dir), Path(args.out), method=args.method, bfi_source=args.bfi_source
        )
        print(json.dumps({"ok": True, "out": args.out}, indent=2))
    elif args.cmd == "export-luma-weights-header":
        export_luma_weights_header(
            Path(args.measure_dir), Path(args.out), method=args.method, bfi_source=args.bfi_source
        )
        print(json.dumps({"ok": True, "out": args.out}, indent=2))


if __name__ == "__main__":
    main()
