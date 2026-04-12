#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

CHANNELS = ["R", "G", "B", "W"]
LADDER_SUFFIX = "_temporal_ladder"
DEFAULT_CAPTURE_GLOBS = ["plan_capture_*.csv"]
DEFAULT_PRUNED_CAPTURE_GLOBS = ["plan_capture_outliers_pruned*.csv"]
DEFAULT_TARGET_PLAN_GLOBS = ["plan_capture_advanced_*.csv"]
DEFAULT_INTERPOLATED_CAPTURE_GLOBS = ["plan_capture_interpolated*.csv"]
DEFAULT_CAPTURE_SUMMARY_PRUNE_PASSES = 4
CHANNEL_INDEX = {channel: idx for idx, channel in enumerate(CHANNELS)}
DEFAULT_SPILL_DIR = Path(os.environ.get("TEMPORAL_LADDER_TUNING_SPILL_DIR", "./temporal_ladder_tuning"))
DEFAULT_INTERPOLATED_CAPTURE_DIR = DEFAULT_SPILL_DIR / "interpolated_captures"
DEFAULT_COMBINED_CAPTURE_DIR = DEFAULT_SPILL_DIR / "combined_captures"
CAPTURE_METRIC_FIELDS = ["X", "Y", "Z"]
CAPTURE_AVERAGE_FIELDS = ["X", "Y", "Z", "x", "y", "elapsed_s"]
INTERPOLATED_CAPTURE_FIELDS = [
    "name", "mode", "use_fill16", "r", "g", "b", "w",
    "lower_r", "lower_g", "lower_b", "lower_w",
    "upper_r", "upper_g", "upper_b", "upper_w",
    "r16", "g16", "b16", "w16",
    "bfi_r", "bfi_g", "bfi_b", "bfi_w",
    "lower_r16", "lower_g16", "lower_b16", "lower_w16",
    "upper_r16", "upper_g16", "upper_b16", "upper_w16",
    "high_count_r", "high_count_g", "high_count_b", "high_count_w",
    "cycle_length", "repeat_index", "solver_mode", "ok", "returncode", "elapsed_s", "timed_out",
    "X", "Y", "Z", "x", "y",
]


def _merge_capture_fieldnames(existing: list[str] | None, incoming: list[str] | None) -> list[str] | None:
    if incoming is None:
        return existing

    merged: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name and name not in seen:
            seen.add(name)
            merged.append(name)

    combined = list(existing or []) + list(incoming or [])
    for field in INTERPOLATED_CAPTURE_FIELDS:
        if field in combined:
            add(field)
    for field in combined:
        add(field)
    return merged


@dataclass
class LadderRow:
    channel: str
    mode: str
    lower_value: int
    upper_value: int
    value: int
    bfi: int
    estimated_output: float
    output_q16: int
    normalized_output: float
    source_path: str = ""
    row_index: int = 0
    flags: list[str] = field(default_factory=list)
    recommended_action: str = ""
    original_estimated_output: float = 0.0
    original_output_q16: int = 0

    def key(self) -> tuple[str, str, int, int, int]:
        return (self.channel, self.mode, self.lower_value, self.upper_value, self.bfi)

    @property
    def span(self) -> int:
        return self.upper_value - self.lower_value


@dataclass
class MeasurementStats:
    channel: str
    mode: str
    lower_value: int
    upper_value: int
    bfi: int
    median_x: float
    median_y: float
    median_X: float
    median_Y: float
    samples: int
    max_xy_radius: float

    def key(self) -> tuple[str, str, int, int, int]:
        return (self.channel, self.mode, self.lower_value, self.upper_value, self.bfi)


@dataclass
class Finding:
    channel: str
    mode: str
    lower_value: int
    upper_value: int
    value: int
    bfi: int
    output_q16: int
    estimated_output: float
    pass_name: str
    detail: str
    severity: float
    recommended_action: str

    def state_key(self) -> tuple[str, str, int, int, int]:
        return (self.channel, self.mode, self.lower_value, self.upper_value, self.bfi)


@dataclass
class AnalysisResult:
    rows_by_channel: dict[str, list[LadderRow]]
    findings: list[Finding]
    measurement_stats: dict[tuple[str, str, int, int, int], MeasurementStats]


@dataclass
class CaptureStateSummary:
    channel: str
    mode: str
    lower_value: int
    upper_value: int
    value: int
    bfi: int
    repeats: int = 0
    sample_rows: int = 0

    def key(self) -> tuple[str, str, int, int, int]:
        return (self.channel, self.mode, self.lower_value, self.upper_value, self.bfi)


@dataclass
class CaptureMeasurementSummary:
    channel: str
    mode: str
    lower_value: int
    upper_value: int
    bfi: int
    samples: int
    repeats: int
    median_X: float
    median_Y: float
    median_Z: float
    template_row: dict[str, Any]

    def key(self) -> tuple[str, str, int, int, int]:
        return (self.channel, self.mode, self.lower_value, self.upper_value, self.bfi)

    @property
    def span(self) -> int:
        return self.upper_value - self.lower_value


@dataclass
class CaptureFilterStats:
    files_scanned: int = 0
    rows_seen: int = 0
    rows_kept: int = 0
    rows_pruned: int = 0
    rows_before_averaging: int = 0
    states_averaged: int = 0
    states_pruned: int = 0
    chunk_files_written: int = 0
    chunk_paths: list[Path] = field(default_factory=list)


@dataclass
class InterpolatedCaptureStats:
    source_files_scanned: int = 0
    source_rows_seen: int = 0
    source_rows_loaded: int = 0
    source_states_repaired: int = 0
    requested_states: int = 0
    states_interpolated: int = 0
    states_already_present: int = 0
    states_unresolved: int = 0
    states_clamped: int = 0
    rows_written: int = 0
    chunk_files_written: int = 0
    chunk_paths: list[Path] = field(default_factory=list)
    unresolved_states: list[tuple[str, str, int, int, int]] = field(default_factory=list)


@dataclass
class CombinedCaptureStats:
    source_files_scanned: int = 0
    rows_seen: int = 0
    states_repaired: int = 0
    rows_retuned: int = 0
    rows_written: int = 0
    chunk_files_written: int = 0
    chunk_paths: list[Path] = field(default_factory=list)


@dataclass
class OutputPaths:
    report_out: Path
    recapture_out: Path | None
    filtered_capture_out: Path | None
    out_dir: Path | None
    spill_dir: Path
    redirected: list[str] = field(default_factory=list)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_mode(mode: Any, default: str = "blend8") -> str:
    normalized = str(mode or default).strip().lower()
    if normalized in {"fill8", "blend8", "fill16", "blend16"}:
        return normalized
    return default


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_c_drive_path(path: Path | None) -> bool:
    if path is None:
        return False
    return str(path.drive).strip().lower() == "c:"


def _prepare_spill_dir(spill_dir: Path) -> Path:
    spill_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = str(spill_dir)
    os.environ["TEMP"] = str(spill_dir)
    os.environ["TMPDIR"] = str(spill_dir)
    return spill_dir


def _redirect_output_path(path: Path | None, spill_dir: Path, category: str) -> tuple[Path | None, str | None]:
    if path is None:
        return None, None
    if not _is_c_drive_path(path):
        return path, None

    category_dir = spill_dir / category
    if path.suffix:
        redirected = category_dir / path.name
    else:
        redirected = category_dir / path.name
    return redirected, f"Redirected {path} -> {redirected} to avoid C: drive exhaustion"


def resolve_output_paths(args: argparse.Namespace, include_out_dir: bool) -> OutputPaths:
    spill_dir = _prepare_spill_dir(Path(args.spill_dir))
    redirected: list[str] = []

    report_out, note = _redirect_output_path(Path(args.report_out), spill_dir, "reports")
    if note:
        redirected.append(note)

    recapture_out = None
    if args.recapture_out:
        recapture_out, note = _redirect_output_path(Path(args.recapture_out), spill_dir, "plans")
        if note:
            redirected.append(note)

    filtered_capture_out = None
    if args.filtered_capture_out:
        filtered_capture_out, note = _redirect_output_path(Path(args.filtered_capture_out), spill_dir, "captures")
        if note:
            redirected.append(note)
        # auto-derive recapture plan path from filtered capture path when not explicit
        if recapture_out is None:
            plans_dir = spill_dir / "plans"
            plans_dir.mkdir(parents=True, exist_ok=True)
            recapture_out = plans_dir / (
                filtered_capture_out.stem + "_recapture_plan" + (filtered_capture_out.suffix or ".csv")
            )

    out_dir = None
    if include_out_dir and getattr(args, "out_dir", None):
        out_dir, note = _redirect_output_path(Path(args.out_dir), spill_dir, "ladders")
        if note:
            redirected.append(note)

    return OutputPaths(
        report_out=report_out,
        recapture_out=recapture_out,
        filtered_capture_out=filtered_capture_out,
        out_dir=out_dir,
        spill_dir=spill_dir,
        redirected=redirected,
    )


def _load_ladder_rows(path: Path, channel: str) -> list[LadderRow]:
    if path.suffix.lower() == ".json":
        raw_rows = json.loads(path.read_text(encoding="utf-8"))
    else:
        with path.open("r", encoding="utf-8", newline="") as handle:
            raw_rows = list(csv.DictReader(handle))

    rows: list[LadderRow] = []
    for index, raw in enumerate(raw_rows):
        lower_value = _safe_int(raw.get("lower_value", 0))
        upper_value = _safe_int(raw.get("upper_value", raw.get("value", 0)))
        value = _safe_int(raw.get("value", upper_value))
        mode = str(raw.get("mode", "fill8") or "fill8")
        normalized = _safe_float(raw.get("normalized_output", 0.0))
        estimated_output = _safe_float(raw.get("estimated_output", 0.0))
        output_q16 = _safe_int(raw.get("output_q16", round(normalized * 65535.0)))
        row = LadderRow(
            channel=channel,
            mode=mode,
            lower_value=lower_value,
            upper_value=upper_value,
            value=value,
            bfi=_safe_int(raw.get("bfi", 0)),
            estimated_output=estimated_output,
            output_q16=output_q16,
            normalized_output=normalized if normalized else (output_q16 / 65535.0),
            source_path=str(path),
            row_index=index,
            original_estimated_output=estimated_output,
            original_output_q16=output_q16,
        )
        rows.append(row)
    return rows


def load_ladders(lut_dir: Path, channels: list[str]) -> dict[str, list[LadderRow]]:
    rows_by_channel: dict[str, list[LadderRow]] = {}
    for channel in channels:
        stem = f"{channel.lower()}{LADDER_SUFFIX}"
        json_path = lut_dir / f"{stem}.json"
        csv_path = lut_dir / f"{stem}.csv"
        source_path = json_path if json_path.exists() else csv_path
        if not source_path.exists():
            raise FileNotFoundError(f"Could not find ladder for channel {channel} under {lut_dir}")
        rows_by_channel[channel] = _load_ladder_rows(source_path, channel)
    return rows_by_channel


def _median(values: list[float], default: float = 0.0) -> float:
    return float(median(values)) if values else default


def load_measurement_stats(path: Path | None) -> dict[tuple[str, str, int, int, int], MeasurementStats]:
    if path is None or not path.exists():
        return {}

    grouped: dict[tuple[str, str, int, int, int], list[dict[str, float]]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            key = (
                str(raw.get("channel", "")).upper(),
                str(raw.get("mode", "fill8") or "fill8"),
                _safe_int(raw.get("lower_value", 0)),
                _safe_int(raw.get("upper_value", raw.get("value", 0))),
                _safe_int(raw.get("bfi", 0)),
            )
            grouped[key].append(
                {
                    "X": _safe_float(raw.get("X", 0.0)),
                    "Y": _safe_float(raw.get("Y", 0.0)),
                    "x": _safe_float(raw.get("x", 0.0)),
                    "y": _safe_float(raw.get("y", 0.0)),
                }
            )

    stats: dict[tuple[str, str, int, int, int], MeasurementStats] = {}
    for key, samples in grouped.items():
        xs = [sample["x"] for sample in samples]
        ys = [sample["y"] for sample in samples]
        x_med = _median(xs)
        y_med = _median(ys)
        max_radius = max((math.dist((sample["x"], sample["y"]), (x_med, y_med)) for sample in samples), default=0.0)
        stats[key] = MeasurementStats(
            channel=key[0],
            mode=key[1],
            lower_value=key[2],
            upper_value=key[3],
            bfi=key[4],
            median_x=x_med,
            median_y=y_med,
            median_X=_median([sample["X"] for sample in samples]),
            median_Y=_median([sample["Y"] for sample in samples]),
            samples=len(samples),
            max_xy_radius=max_radius,
        )
    return stats


def _local_expected_q16(rows: list[LadderRow], idx: int, axis_value_getter) -> float:
    current_axis = axis_value_getter(rows[idx])
    neighbors: list[tuple[float, float]] = []
    if idx - 1 >= 0:
        neighbors.append((float(axis_value_getter(rows[idx - 1])), float(rows[idx - 1].output_q16)))
    if idx + 1 < len(rows):
        neighbors.append((float(axis_value_getter(rows[idx + 1])), float(rows[idx + 1].output_q16)))
    if not neighbors:
        return float(rows[idx].output_q16)
    if len(neighbors) == 1:
        return neighbors[0][1]

    (x0, y0), (x1, y1) = neighbors
    if math.isclose(x0, x1):
        return (y0 + y1) * 0.5
    t = (current_axis - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def _residual_threshold_q16(expected_q16: float, absolute_floor_q16: int, relative_ratio: float) -> float:
    return max(float(absolute_floor_q16), abs(float(expected_q16)) * float(relative_ratio))


def _select_suspect(rows: list[LadderRow], idx_a: int, idx_b: int, axis_value_getter) -> int:
    dev_a = abs(float(rows[idx_a].output_q16) - _local_expected_q16(rows, idx_a, axis_value_getter))
    dev_b = abs(float(rows[idx_b].output_q16) - _local_expected_q16(rows, idx_b, axis_value_getter))
    if dev_b > dev_a:
        return idx_b
    if dev_a > dev_b:
        return idx_a
    return idx_b


def _append_finding(findings: list[Finding], row: LadderRow, pass_name: str, detail: str, severity: float, recommended_action: str) -> None:
    if pass_name not in row.flags:
        row.flags.append(pass_name)
    if not row.recommended_action or recommended_action == "recapture":
        row.recommended_action = recommended_action
    findings.append(
        Finding(
            channel=row.channel,
            mode=row.mode,
            lower_value=row.lower_value,
            upper_value=row.upper_value,
            value=row.value,
            bfi=row.bfi,
            output_q16=row.output_q16,
            estimated_output=row.estimated_output,
            pass_name=pass_name,
            detail=detail,
            severity=severity,
            recommended_action=recommended_action,
        )
    )


def _run_primary_upper_pass(rows_by_channel: dict[str, list[LadderRow]], findings: list[Finding], tolerance_q16: int) -> None:
    for rows in rows_by_channel.values():
        groups: dict[tuple[int, int], list[LadderRow]] = defaultdict(list)
        for row in rows:
            groups[(row.lower_value, row.bfi)].append(row)
        for (lower_value, bfi), group in groups.items():
            group.sort(key=lambda row: (row.upper_value, row.value, row.row_index))
            for idx in range(1, len(group)):
                prev_row = group[idx - 1]
                curr_row = group[idx]
                if curr_row.output_q16 + tolerance_q16 >= prev_row.output_q16:
                    continue
                suspect_idx = _select_suspect(group, idx - 1, idx, lambda row: row.upper_value)
                suspect = group[suspect_idx]
                detail = (
                    f"Within lower={lower_value} and bfi={bfi}, upper={curr_row.upper_value} produced {curr_row.output_q16} "
                    f"after upper={prev_row.upper_value} produced {prev_row.output_q16}."
                )
                _append_finding(findings, suspect, "upper_monotonic", detail, prev_row.output_q16 - curr_row.output_q16, "fix")


def _run_bfi_pass(rows_by_channel: dict[str, list[LadderRow]], findings: list[Finding], tolerance_q16: int) -> None:
    for rows in rows_by_channel.values():
        groups: dict[tuple[int, int], list[LadderRow]] = defaultdict(list)
        for row in rows:
            groups[(row.lower_value, row.upper_value)].append(row)
        for (lower_value, upper_value), group in groups.items():
            group.sort(key=lambda row: (row.bfi, row.row_index))
            for idx in range(1, len(group)):
                lower_bfi_row = group[idx - 1]
                higher_bfi_row = group[idx]
                if higher_bfi_row.output_q16 <= lower_bfi_row.output_q16 + tolerance_q16:
                    continue
                suspect_idx = _select_suspect(group, idx - 1, idx, lambda row: row.bfi)
                suspect = group[suspect_idx]
                detail = (
                    f"Within lower={lower_value}, upper={upper_value}, bfi={higher_bfi_row.bfi} produced {higher_bfi_row.output_q16} "
                    f"which exceeded bfi={lower_bfi_row.bfi} at {lower_bfi_row.output_q16}."
                )
                _append_finding(findings, suspect, "bfi_monotonic", detail, higher_bfi_row.output_q16 - lower_bfi_row.output_q16, "fix")


def _run_lower_floor_pass(rows_by_channel: dict[str, list[LadderRow]], findings: list[Finding], tolerance_q16: int) -> None:
    for rows in rows_by_channel.values():
        groups: dict[tuple[int, int], list[LadderRow]] = defaultdict(list)
        for row in rows:
            if row.span <= 0:
                continue
            groups[(row.span, row.bfi)].append(row)
        for (span, bfi), group in groups.items():
            group.sort(key=lambda row: (row.lower_value, row.upper_value, row.row_index))
            for idx in range(1, len(group)):
                prev_row = group[idx - 1]
                curr_row = group[idx]
                if curr_row.output_q16 + tolerance_q16 >= prev_row.output_q16:
                    continue
                suspect_idx = _select_suspect(group, idx - 1, idx, lambda row: row.lower_value)
                suspect = group[suspect_idx]
                detail = (
                    f"For span={span} and bfi={bfi}, lower={curr_row.lower_value}/upper={curr_row.upper_value} produced {curr_row.output_q16} "
                    f"after lower={prev_row.lower_value}/upper={prev_row.upper_value} produced {prev_row.output_q16}."
                )
                _append_finding(findings, suspect, "lower_floor_monotonic", detail, prev_row.output_q16 - curr_row.output_q16, "fix")


def _run_upper_residual_pass(
    rows_by_channel: dict[str, list[LadderRow]],
    findings: list[Finding],
    absolute_floor_q16: int,
    relative_ratio: float,
) -> None:
    for rows in rows_by_channel.values():
        groups: dict[tuple[int, int], list[LadderRow]] = defaultdict(list)
        for row in rows:
            groups[(row.lower_value, row.bfi)].append(row)
        for (lower_value, bfi), group in groups.items():
            group.sort(key=lambda row: (row.upper_value, row.value, row.row_index))
            if len(group) < 3:
                continue
            for idx in range(1, len(group) - 1):
                row = group[idx]
                expected_q16 = _local_expected_q16(group, idx, lambda current: current.upper_value)
                residual_q16 = abs(float(row.output_q16) - expected_q16)
                threshold_q16 = _residual_threshold_q16(expected_q16, absolute_floor_q16, relative_ratio)
                if residual_q16 <= threshold_q16:
                    continue
                detail = (
                    f"Within lower={lower_value} and bfi={bfi}, upper={row.upper_value} produced {row.output_q16} "
                    f"but the local slope predicts {round(expected_q16)} (|delta|={round(residual_q16)} > {round(threshold_q16)})."
                )
                _append_finding(findings, row, "upper_residual", detail, residual_q16, "recapture")


def _find_active_channel_from_record(rec: dict[str, Any]) -> str | None:
    name = str(rec.get("name", "") or "").strip()
    if name:
        prefix = name.split("_", 1)[0].strip().upper()
        if prefix in CHANNELS:
            return prefix

    ranked = []
    for channel in CHANNELS:
        lower_value = _safe_int(rec.get(f"lower_{channel.lower()}", 0))
        upper_value = _safe_int(rec.get(f"upper_{channel.lower()}", rec.get(channel.lower(), 0)))
        bfi_value = _safe_int(rec.get(f"bfi_{channel.lower()}", 0))
        ranked.append((upper_value + lower_value + (bfi_value * 1000), channel))

    ranked.sort(reverse=True)
    if ranked and ranked[0][0] > 0:
        return ranked[0][1]
    return None


def _capture_state_from_record(rec: dict[str, Any]) -> tuple[str, str, int, int, int] | None:
    channel = _find_active_channel_from_record(rec)
    if channel is None:
        return None
    channel_key = channel.lower()
    mode = _normalize_mode(rec.get("mode", "blend8"), default="blend8")
    lower_value = _safe_int(rec.get(f"lower_{channel_key}", 0))
    upper_value = _safe_int(rec.get(f"upper_{channel_key}", rec.get(channel_key, 0)))
    bfi_value = _safe_int(rec.get(f"bfi_{channel_key}", 0))
    return (channel, mode, lower_value, upper_value, bfi_value)


def _capture_row_sort_key(rec: dict[str, Any]) -> tuple[int, int, int, int, int, int, str]:
    state = _capture_state_from_record(rec)
    if state is None:
        name = str(rec.get("name", "") or "")
        return (len(CHANNELS), 0, 0, 0, 0, _safe_int(rec.get("repeat_index", 0), 0), name)

    channel, mode, lower_value, upper_value, bfi_value = state
    mode_rank = 0 if mode == "fill8" else 1
    repeat_index = _safe_int(rec.get("repeat_index", 0), 0)
    name = str(rec.get("name", "") or "")
    return (CHANNEL_INDEX[channel], lower_value, bfi_value, mode_rank, upper_value, repeat_index, name)


def summarize_capture_states(capture_dir: Path, input_globs: list[str] | None = None) -> dict[tuple[str, str, int, int, int], CaptureStateSummary]:
    patterns = list(input_globs or DEFAULT_CAPTURE_GLOBS)
    summaries: dict[tuple[str, str, int, int, int], CaptureStateSummary] = {}
    for pattern in patterns:
        for path in sorted(capture_dir.glob(pattern)):
            with path.open("r", newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                for rec in reader:
                    state = _capture_state_from_record(rec)
                    if state is None:
                        continue
                    summary = summaries.get(state)
                    if summary is None:
                        summary = CaptureStateSummary(
                            channel=state[0],
                            mode=state[1],
                            lower_value=state[2],
                            upper_value=state[3],
                            value=state[3],
                            bfi=state[4],
                        )
                        summaries[state] = summary
                    summary.sample_rows += 1
                    repeat_index = _safe_int(rec.get("repeat_index", -1), -1)
                    if repeat_index >= 0:
                        summary.repeats = max(summary.repeats, repeat_index + 1)
    return summaries


def _build_blend8_plan_row(state: tuple[str, str, int, int, int], repeats: int) -> dict[str, Any]:
    channel, mode, lower_value, upper_value, bfi = state
    idx = CHANNEL_INDEX[channel]
    upper = [0, 0, 0, 0]
    lower = [0, 0, 0, 0]
    bfi_values = [0, 0, 0, 0]
    upper[idx] = upper_value
    lower[idx] = lower_value
    bfi_values[idx] = bfi
    row_mode = mode if mode in {"fill8", "blend8"} else "blend8"
    return {
        "name": f"{channel}_floor{lower_value:03d}_v{upper_value:03d}_bfi{bfi}",
        "mode": row_mode,
        "r": upper[0],
        "g": upper[1],
        "b": upper[2],
        "w": upper[3],
        "lower_r": lower[0],
        "lower_g": lower[1],
        "lower_b": lower[2],
        "lower_w": lower[3],
        "upper_r": upper[0],
        "upper_g": upper[1],
        "upper_b": upper[2],
        "upper_w": upper[3],
        "bfi_r": bfi_values[0],
        "bfi_g": bfi_values[1],
        "bfi_b": bfi_values[2],
        "bfi_w": bfi_values[3],
        "repeats": max(1, int(repeats)),
    }


def write_blend8_recapture_plan(
    path: Path,
    analysis: AnalysisResult,
    capture_state_summaries: dict[tuple[str, str, int, int, int], CaptureStateSummary] | None = None,
    default_repeats: int = 4,
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    state_keys = sorted({finding.state_key() for finding in analysis.findings})
    fieldnames = [
        "name", "mode", "r", "g", "b", "w",
        "lower_r", "lower_g", "lower_b", "lower_w",
        "upper_r", "upper_g", "upper_b", "upper_w",
        "bfi_r", "bfi_g", "bfi_b", "bfi_w", "repeats",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for state in state_keys:
            repeats = default_repeats
            if capture_state_summaries is not None and state in capture_state_summaries:
                repeats = capture_state_summaries[state].repeats or default_repeats
            writer.writerow(_build_blend8_plan_row(state, repeats))
    return len(state_keys)


def _chunk_output_path(base_path: Path, chunk_index: int) -> Path:
    suffix = base_path.suffix or ".csv"
    stem = base_path.stem if base_path.suffix else base_path.name
    return base_path.with_name(f"{stem}_part{chunk_index:03d}{suffix}")


def write_filtered_capture_csv(
    capture_dir: Path,
    out_path: Path,
    flagged_states: set[tuple[str, str, int, int, int]],
    chunk_rows: int,
    input_globs: list[str] | None = None,
) -> CaptureFilterStats:
    patterns = list(input_globs or DEFAULT_CAPTURE_GLOBS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stats = CaptureFilterStats(states_pruned=len(flagged_states))
    fieldnames: list[str] | None = None
    capture_paths: list[Path] = []
    chunk_rows = max(1, int(chunk_rows))
    chunk_handle = None
    writer = None
    rows_in_chunk = 0

    for pattern in patterns:
        capture_paths.extend(sorted(capture_dir.glob(pattern)))

    # -- Phase 1: collect all rows and discover fieldnames --
    all_rows: list[tuple[dict[str, Any], str]] = []  # (rec, source_file)
    for path in capture_paths:
        stats.files_scanned += 1
        with path.open("r", newline="", encoding="utf-8-sig") as in_handle:
            reader = csv.DictReader(in_handle)
            fieldnames = _merge_capture_fieldnames(fieldnames, reader.fieldnames)
            if reader.fieldnames is None:
                continue
            for rec in reader:
                stats.rows_seen += 1
                # skip fully empty rows or rows with only empty keys
                cleaned = {k: v for k, v in rec.items() if k}
                if not cleaned or all(v in (None, "") for v in cleaned.values()):
                    continue
                all_rows.append((cleaned, path.name))

    if fieldnames is not None and "source_capture_file" not in fieldnames:
        fieldnames.append("source_capture_file")
    if fieldnames is not None and "averaged_sample_count" not in fieldnames:
        fieldnames.append("averaged_sample_count")

    # -- Phase 2: group by state and average repeats --
    state_groups: dict[tuple[str, str, int, int, int] | None, list[tuple[dict[str, Any], str]]] = defaultdict(list)
    for rec, source in all_rows:
        state = _capture_state_from_record(rec)
        state_groups[state].append((rec, source))

    averaged_rows: list[dict[str, Any]] = []
    stats.rows_before_averaging = len(all_rows)

    for state, group in state_groups.items():
        if state is None:
            # rows without a parseable state pass through individually
            for rec, source in group:
                row_out = dict(rec)
                row_out["source_capture_file"] = source
                row_out["averaged_sample_count"] = "1"
                averaged_rows.append(row_out)
            continue

        if state in flagged_states:
            stats.rows_pruned += len(group)
            continue

        # only average rows marked ok with valid metrics
        ok_rows = [
            (rec, src) for rec, src in group
            if _parse_bool(rec.get("ok"), default=True)
            and not any(rec.get(m) in (None, "") for m in CAPTURE_METRIC_FIELDS)
        ]
        if not ok_rows:
            # no valid rows — pass through the first one un-averaged
            rec, source = group[0]
            row_out = dict(rec)
            row_out["source_capture_file"] = source
            row_out["averaged_sample_count"] = "0"
            averaged_rows.append(row_out)
            continue

        if len(ok_rows) > 1:
            stats.states_averaged += 1

        # build averaged row from the first ok row as template
        template, first_source = ok_rows[0]
        row_out = dict(template)
        sample_count = len(ok_rows)
        for avg_field in CAPTURE_AVERAGE_FIELDS:
            values = [_safe_float(r.get(avg_field, 0.0)) for r, _ in ok_rows if r.get(avg_field) not in (None, "")]
            if values:
                row_out[avg_field] = f"{sum(values) / len(values):.6f}"
        sources = sorted({src for _, src in ok_rows})
        row_out["source_capture_file"] = ";".join(sources)
        row_out["averaged_sample_count"] = str(sample_count)
        row_out["repeat_index"] = "0"
        averaged_rows.append(row_out)

    # sort by state for deterministic output
    averaged_rows.sort(key=_capture_row_sort_key)

    # -- Phase 3: write chunks --
    def open_next_chunk() -> None:
        nonlocal chunk_handle, writer, rows_in_chunk
        if fieldnames is None:
            raise ValueError("fieldnames must be initialized before opening a chunk")
        if chunk_handle is not None:
            chunk_handle.close()
        chunk_path = _chunk_output_path(out_path, stats.chunk_files_written + 1)
        chunk_path.parent.mkdir(parents=True, exist_ok=True)
        chunk_handle = chunk_path.open("w", encoding="utf-8", newline="")
        writer = csv.DictWriter(chunk_handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        rows_in_chunk = 0
        stats.chunk_files_written += 1
        stats.chunk_paths.append(chunk_path)

    try:
        for row_out in averaged_rows:
            if writer is None or rows_in_chunk >= chunk_rows:
                open_next_chunk()
            writer.writerow(row_out)
            rows_in_chunk += 1
            stats.rows_kept += 1
        if writer is None and fieldnames is not None:
            open_next_chunk()
    finally:
        if chunk_handle is not None:
            chunk_handle.close()

    return stats


def summarize_capture_measurements(
    capture_dir: Path,
    input_globs: list[str] | None = None,
) -> tuple[dict[tuple[str, str, int, int, int], CaptureMeasurementSummary], InterpolatedCaptureStats]:
    patterns = list(input_globs or DEFAULT_PRUNED_CAPTURE_GLOBS)
    grouped: dict[tuple[str, str, int, int, int], dict[str, Any]] = {}
    stats = InterpolatedCaptureStats()

    for pattern in patterns:
        for path in sorted(capture_dir.glob(pattern)):
            stats.source_files_scanned += 1
            with path.open("r", newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                for rec in reader:
                    stats.source_rows_seen += 1
                    if not _parse_bool(rec.get("ok"), default=False):
                        continue
                    if any(rec.get(metric) in (None, "") for metric in CAPTURE_METRIC_FIELDS):
                        continue
                    state = _capture_state_from_record(rec)
                    if state is None:
                        continue
                    bucket = grouped.get(state)
                    if bucket is None:
                        bucket = {
                            "channel": state[0],
                            "mode": state[1],
                            "lower_value": state[2],
                            "upper_value": state[3],
                            "bfi": state[4],
                            "template_row": dict(rec),
                            "X": [],
                            "Y": [],
                            "Z": [],
                            "repeats": 0,
                        }
                        grouped[state] = bucket
                    bucket["X"].append(_safe_float(rec.get("X", 0.0)))
                    bucket["Y"].append(_safe_float(rec.get("Y", 0.0)))
                    bucket["Z"].append(_safe_float(rec.get("Z", 0.0)))
                    repeat_index = _safe_int(rec.get("repeat_index", -1), -1)
                    if repeat_index >= 0:
                        bucket["repeats"] = max(bucket["repeats"], repeat_index + 1)
                    stats.source_rows_loaded += 1

    summaries: dict[tuple[str, str, int, int, int], CaptureMeasurementSummary] = {}
    for state, bucket in grouped.items():
        summaries[state] = CaptureMeasurementSummary(
            channel=bucket["channel"],
            mode=bucket["mode"],
            lower_value=bucket["lower_value"],
            upper_value=bucket["upper_value"],
            bfi=bucket["bfi"],
            samples=len(bucket["Y"]),
            repeats=max(1, int(bucket["repeats"] or 1)),
            median_X=_median(bucket["X"]),
            median_Y=_median(bucket["Y"]),
            median_Z=_median(bucket["Z"]),
            template_row=bucket["template_row"],
        )
    return summaries, stats


def summarize_capture_measurement_rows(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str, int, int, int], CaptureMeasurementSummary]:
    grouped: dict[tuple[str, str, int, int, int], dict[str, Any]] = {}

    for rec in rows:
        if not _parse_bool(rec.get("ok"), default=False):
            continue
        if any(rec.get(metric) in (None, "") for metric in CAPTURE_METRIC_FIELDS):
            continue
        state = _capture_state_from_record(rec)
        if state is None:
            continue
        bucket = grouped.get(state)
        if bucket is None:
            bucket = {
                "channel": state[0],
                "mode": state[1],
                "lower_value": state[2],
                "upper_value": state[3],
                "bfi": state[4],
                "template_row": dict(rec),
                "X": [],
                "Y": [],
                "Z": [],
                "repeats": 0,
            }
            grouped[state] = bucket
        bucket["X"].append(_safe_float(rec.get("X", 0.0)))
        bucket["Y"].append(_safe_float(rec.get("Y", 0.0)))
        bucket["Z"].append(_safe_float(rec.get("Z", 0.0)))
        repeat_index = _safe_int(rec.get("repeat_index", -1), -1)
        if repeat_index >= 0:
            bucket["repeats"] = max(bucket["repeats"], repeat_index + 1)

    summaries: dict[tuple[str, str, int, int, int], CaptureMeasurementSummary] = {}
    for state, bucket in grouped.items():
        summaries[state] = CaptureMeasurementSummary(
            channel=bucket["channel"],
            mode=bucket["mode"],
            lower_value=bucket["lower_value"],
            upper_value=bucket["upper_value"],
            bfi=bucket["bfi"],
            samples=len(bucket["Y"]),
            repeats=max(1, int(bucket["repeats"] or 1)),
            median_X=_median(bucket["X"]),
            median_Y=_median(bucket["Y"]),
            median_Z=_median(bucket["Z"]),
            template_row=bucket["template_row"],
        )
    return summaries


def _build_measurement_indexes(
    summaries: dict[tuple[str, str, int, int, int], CaptureMeasurementSummary],
) -> tuple[
    dict[tuple[str, str, int, int], list[CaptureMeasurementSummary]],
    dict[tuple[str, str, int, int], list[CaptureMeasurementSummary]],
    dict[tuple[str, str, int, int], list[CaptureMeasurementSummary]],
    dict[tuple[str, str], list[CaptureMeasurementSummary]],
]:
    by_lower_bfi: dict[tuple[str, str, int, int], list[CaptureMeasurementSummary]] = defaultdict(list)
    by_lower_upper: dict[tuple[str, str, int, int], list[CaptureMeasurementSummary]] = defaultdict(list)
    by_span_bfi: dict[tuple[str, str, int, int], list[CaptureMeasurementSummary]] = defaultdict(list)
    by_channel_mode: dict[tuple[str, str], list[CaptureMeasurementSummary]] = defaultdict(list)
    for summary in summaries.values():
        by_lower_bfi[(summary.channel, summary.mode, summary.lower_value, summary.bfi)].append(summary)
        by_lower_upper[(summary.channel, summary.mode, summary.lower_value, summary.upper_value)].append(summary)
        by_span_bfi[(summary.channel, summary.mode, summary.span, summary.bfi)].append(summary)
        by_channel_mode[(summary.channel, summary.mode)].append(summary)

    for group in by_lower_bfi.values():
        group.sort(key=lambda item: (item.upper_value, item.samples))
    for group in by_lower_upper.values():
        group.sort(key=lambda item: (item.bfi, item.samples))
    for group in by_span_bfi.values():
        group.sort(key=lambda item: (item.lower_value, item.samples))
    for group in by_channel_mode.values():
        group.sort(key=lambda item: (item.lower_value, item.upper_value, item.bfi))

    return by_lower_bfi, by_lower_upper, by_span_bfi, by_channel_mode


def _measurement_value(summary: CaptureMeasurementSummary, metric: str) -> float:
    if metric == "X":
        return summary.median_X
    if metric == "Y":
        return summary.median_Y
    if metric == "Z":
        return summary.median_Z
    raise ValueError(f"Unsupported metric: {metric}")


def _state_sort_key(state: tuple[str, str, int, int, int]) -> tuple[int, int, int, int, int]:
    channel, mode, lower_value, upper_value, bfi_value = state
    mode_rank = 0 if mode == "fill8" else 1
    return (CHANNEL_INDEX.get(channel, len(CHANNELS)), lower_value, bfi_value, mode_rank, upper_value)


def _summary_state(summary: CaptureMeasurementSummary) -> tuple[str, str, int, int, int]:
    return summary.key()


def _build_summary_constraint_indexes(
    summaries: dict[tuple[str, str, int, int, int], CaptureMeasurementSummary],
) -> tuple[
    dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    dict[tuple[str, int], float],
    dict[tuple[str, int], float],
]:
    by_lower_bfi: dict[tuple[str, int, int], list[CaptureMeasurementSummary]] = defaultdict(list)
    by_lower_upper: dict[tuple[str, int, int], list[CaptureMeasurementSummary]] = defaultdict(list)
    by_span_bfi: dict[tuple[str, int, int], list[CaptureMeasurementSummary]] = defaultdict(list)
    by_upper_bfi: dict[tuple[str, int, int], list[CaptureMeasurementSummary]] = defaultdict(list)
    fill8_levels: dict[tuple[str, int], float] = {}
    same_upper_max: dict[tuple[str, int], float] = {}

    for summary in summaries.values():
        by_lower_bfi[(summary.channel, summary.lower_value, summary.bfi)].append(summary)
        by_lower_upper[(summary.channel, summary.lower_value, summary.upper_value)].append(summary)
        if summary.span > 0:
            by_span_bfi[(summary.channel, summary.span, summary.bfi)].append(summary)
        by_upper_bfi[(summary.channel, summary.upper_value, summary.bfi)].append(summary)
        same_upper_key = (summary.channel, summary.upper_value)
        same_upper_max[same_upper_key] = max(same_upper_max.get(same_upper_key, 0.0), float(summary.median_Y))
        if summary.mode == "fill8" and summary.lower_value == 0 and summary.bfi == 0:
            key = (summary.channel, summary.upper_value)
            fill8_levels[key] = max(fill8_levels.get(key, 0.0), float(summary.median_Y))

    for group in by_lower_bfi.values():
        group.sort(key=lambda item: (item.upper_value, item.mode != "fill8", item.samples))
    for group in by_lower_upper.values():
        group.sort(key=lambda item: (item.bfi, item.mode != "fill8", item.samples))
    for group in by_span_bfi.values():
        group.sort(key=lambda item: (item.lower_value, item.mode != "fill8", item.samples))
    for group in by_upper_bfi.values():
        group.sort(key=lambda item: (item.lower_value, item.mode != "fill8", item.samples))

    return by_lower_bfi, by_lower_upper, by_span_bfi, by_upper_bfi, fill8_levels, same_upper_max


def _nearest_monotonic_neighbors(
    group: list[CaptureMeasurementSummary],
    target_state: tuple[str, str, int, int, int],
    axis_getter,
    target_axis: int,
) -> tuple[CaptureMeasurementSummary | None, CaptureMeasurementSummary | None]:
    previous_summary: CaptureMeasurementSummary | None = None
    next_summary: CaptureMeasurementSummary | None = None
    for summary in group:
        if _summary_state(summary) == target_state:
            continue
        axis_value = int(axis_getter(summary))
        if axis_value <= target_axis:
            if previous_summary is None or int(axis_getter(previous_summary)) < axis_value:
                previous_summary = summary
        if axis_value >= target_axis:
            if next_summary is None or int(axis_getter(next_summary)) > axis_value:
                next_summary = summary
    return previous_summary, next_summary


def _compute_measurement_y_bounds(
    target_state: tuple[str, str, int, int, int],
    by_lower_bfi: dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    by_lower_upper: dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    by_span_bfi: dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    fill8_levels: dict[tuple[str, int], float],
    same_upper_max: dict[tuple[str, int], float],
) -> tuple[float, float]:
    channel, mode, lower_value, upper_value, bfi = target_state
    lower_bound = 0.0
    upper_bound = float("inf")

    if mode == "fill8" and lower_value == 0 and bfi == 0:
        same_upper_peak = same_upper_max.get((channel, upper_value))
        if same_upper_peak is not None:
            lower_bound = max(lower_bound, float(same_upper_peak))

    floor_anchor = fill8_levels.get((channel, lower_value))
    if floor_anchor is not None:
        lower_bound = max(lower_bound, float(floor_anchor))

    ceiling_anchor = fill8_levels.get((channel, upper_value))
    if ceiling_anchor is not None and not (mode == "fill8" and lower_value == 0 and bfi == 0):
        upper_bound = min(upper_bound, float(ceiling_anchor))

    prev_upper, next_upper = _nearest_monotonic_neighbors(
        by_lower_bfi.get((channel, lower_value, bfi), []),
        target_state,
        lambda item: item.upper_value,
        upper_value,
    )
    if prev_upper is not None:
        lower_bound = max(lower_bound, float(prev_upper.median_Y))
    if next_upper is not None:
        upper_bound = min(upper_bound, float(next_upper.median_Y))

    prev_bfi, next_bfi = _nearest_monotonic_neighbors(
        by_lower_upper.get((channel, lower_value, upper_value), []),
        target_state,
        lambda item: item.bfi,
        bfi,
    )
    if prev_bfi is not None:
        upper_bound = min(upper_bound, float(prev_bfi.median_Y))
    if next_bfi is not None:
        lower_bound = max(lower_bound, float(next_bfi.median_Y))

    span = upper_value - lower_value
    if span > 0:
        prev_lower, next_lower = _nearest_monotonic_neighbors(
            by_span_bfi.get((channel, span, bfi), []),
            target_state,
            lambda item: item.lower_value,
            lower_value,
        )
        if prev_lower is not None:
            lower_bound = max(lower_bound, float(prev_lower.median_Y))
        if next_lower is not None:
            upper_bound = min(upper_bound, float(next_lower.median_Y))

    return lower_bound, upper_bound


def _scale_xyz_to_target_y(xyz: tuple[float, float, float], target_y: float) -> tuple[float, float, float]:
    X, Y, Z = xyz
    target_y = max(0.0, float(target_y))
    if math.isclose(float(Y), target_y, rel_tol=1e-9, abs_tol=1e-9):
        return (float(X), float(Y), float(Z))
    if Y <= 0.0:
        return (0.0, target_y, 0.0)
    scale = target_y / float(Y)
    return (max(0.0, float(X) * scale), target_y, max(0.0, float(Z) * scale))


def _clamp_xyz_to_y_bounds(xyz: tuple[float, float, float], lower_bound: float, upper_bound: float) -> tuple[tuple[float, float, float], bool]:
    target_y = float(xyz[1])
    if math.isfinite(upper_bound):
        target_y = min(target_y, float(upper_bound))
    target_y = max(target_y, float(lower_bound))
    if math.isfinite(upper_bound) and lower_bound > upper_bound:
        target_y = (float(lower_bound) + float(upper_bound)) * 0.5
    adjusted = not math.isclose(float(xyz[1]), target_y, rel_tol=1e-9, abs_tol=1e-9)
    return _scale_xyz_to_target_y(xyz, target_y), adjusted


def _repair_summary_xyz_to_constraints(
    summary: CaptureMeasurementSummary,
    by_lower_bfi: dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    by_lower_upper: dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    by_span_bfi: dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    fill8_levels: dict[tuple[str, int], float],
    same_upper_max: dict[tuple[str, int], float],
) -> bool:
    lower_bound, upper_bound = _compute_measurement_y_bounds(summary.key(), by_lower_bfi, by_lower_upper, by_span_bfi, fill8_levels, same_upper_max)
    repaired_xyz, changed = _clamp_xyz_to_y_bounds((summary.median_X, summary.median_Y, summary.median_Z), lower_bound, upper_bound)
    if not changed:
        return False
    summary.median_X = repaired_xyz[0]
    summary.median_Y = repaired_xyz[1]
    summary.median_Z = repaired_xyz[2]
    return True


def _repair_measurement_summaries(
    summaries: dict[tuple[str, str, int, int, int], CaptureMeasurementSummary],
    max_passes: int = 4,
) -> tuple[set[tuple[str, str, int, int, int]], tuple[
    dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    dict[tuple[str, int], float],
    dict[tuple[str, int], float],
]]:
    repaired_states: set[tuple[str, str, int, int, int]] = set()
    constraint_indexes = _build_summary_constraint_indexes(summaries)
    ordered_states = sorted(summaries.keys(), key=_state_sort_key)
    for _ in range(max(1, int(max_passes))):
        changed_any = False
        by_lower_bfi, by_lower_upper, by_span_bfi, _by_upper_bfi, fill8_levels, same_upper_max = constraint_indexes
        for state in ordered_states:
            summary = summaries[state]
            if _repair_summary_xyz_to_constraints(summary, by_lower_bfi, by_lower_upper, by_span_bfi, fill8_levels, same_upper_max):
                repaired_states.add(state)
                changed_any = True
        if not changed_any:
            break
        constraint_indexes = _build_summary_constraint_indexes(summaries)
    return repaired_states, constraint_indexes


def _build_capture_summary_from_plan_row(
    state: tuple[str, str, int, int, int],
    plan_row: dict[str, Any],
    xyz: tuple[float, float, float],
) -> CaptureMeasurementSummary:
    repeats = max(1, _safe_int(plan_row.get("repeats", 1), 1))
    return CaptureMeasurementSummary(
        channel=state[0],
        mode=state[1],
        lower_value=state[2],
        upper_value=state[3],
        bfi=state[4],
        samples=1,
        repeats=repeats,
        median_X=float(xyz[0]),
        median_Y=float(xyz[1]),
        median_Z=float(xyz[2]),
        template_row=dict(plan_row),
    )


def _insert_summary_sorted(group: list[CaptureMeasurementSummary], summary: CaptureMeasurementSummary, key_getter) -> None:
    key = key_getter(summary)
    insert_at = len(group)
    for idx, existing in enumerate(group):
        existing_key = key_getter(existing)
        if key < existing_key:
            insert_at = idx
            break
        if key == existing_key and summary.samples < existing.samples:
            insert_at = idx
            break
    group.insert(insert_at, summary)


def _register_summary_for_interpolation(
    summary: CaptureMeasurementSummary,
    summaries: dict[tuple[str, str, int, int, int], CaptureMeasurementSummary],
    by_lower_bfi: dict[tuple[str, str, int, int], list[CaptureMeasurementSummary]],
    by_lower_upper: dict[tuple[str, str, int, int], list[CaptureMeasurementSummary]],
    by_span_bfi: dict[tuple[str, str, int, int], list[CaptureMeasurementSummary]],
    by_channel_mode: dict[tuple[str, str], list[CaptureMeasurementSummary]],
    constraint_by_lower_bfi: dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    constraint_by_lower_upper: dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    constraint_by_span_bfi: dict[tuple[str, int, int], list[CaptureMeasurementSummary]],
    fill8_levels: dict[tuple[str, int], float],
    same_upper_max: dict[tuple[str, int], float],
) -> None:
    state = summary.key()
    summaries[state] = summary
    _insert_summary_sorted(
        by_lower_bfi[(summary.channel, summary.mode, summary.lower_value, summary.bfi)],
        summary,
        lambda item: (item.upper_value, item.samples),
    )
    _insert_summary_sorted(
        by_lower_upper[(summary.channel, summary.mode, summary.lower_value, summary.upper_value)],
        summary,
        lambda item: (item.bfi, item.samples),
    )
    _insert_summary_sorted(
        by_span_bfi[(summary.channel, summary.mode, summary.span, summary.bfi)],
        summary,
        lambda item: (item.lower_value, item.samples),
    )
    _insert_summary_sorted(
        by_channel_mode[(summary.channel, summary.mode)],
        summary,
        lambda item: (item.lower_value, item.upper_value, item.bfi),
    )
    _insert_summary_sorted(
        constraint_by_lower_bfi[(summary.channel, summary.lower_value, summary.bfi)],
        summary,
        lambda item: (item.upper_value, item.mode != "fill8", item.samples),
    )
    _insert_summary_sorted(
        constraint_by_lower_upper[(summary.channel, summary.lower_value, summary.upper_value)],
        summary,
        lambda item: (item.bfi, item.mode != "fill8", item.samples),
    )
    if summary.span > 0:
        _insert_summary_sorted(
            constraint_by_span_bfi[(summary.channel, summary.span, summary.bfi)],
            summary,
            lambda item: (item.lower_value, item.mode != "fill8", item.samples),
        )
    same_upper_key = (summary.channel, summary.upper_value)
    same_upper_max[same_upper_key] = max(same_upper_max.get(same_upper_key, 0.0), float(summary.median_Y))
    if summary.mode == "fill8" and summary.lower_value == 0 and summary.bfi == 0:
        fill8_key = (summary.channel, summary.upper_value)
        fill8_levels[fill8_key] = max(fill8_levels.get(fill8_key, 0.0), float(summary.median_Y))


def _apply_summary_xyz_to_capture_row(rec: dict[str, Any], summary: CaptureMeasurementSummary) -> bool:
    current_xyz = (
        _safe_float(rec.get("X", 0.0)),
        _safe_float(rec.get("Y", 0.0)),
        _safe_float(rec.get("Z", 0.0)),
    )
    target_xyz = (float(summary.median_X), float(summary.median_Y), float(summary.median_Z))
    changed = any(
        not math.isclose(current_xyz[idx], target_xyz[idx], rel_tol=1e-9, abs_tol=1e-9)
        for idx in range(3)
    )
    if not changed:
        return False
    x, y = _xyz_to_xy(*target_xyz)
    rec["X"] = target_xyz[0]
    rec["Y"] = target_xyz[1]
    rec["Z"] = target_xyz[2]
    if "x" in rec:
        rec["x"] = x
    if "y" in rec:
        rec["y"] = y
    return True


def _interpolate_axis_metric(
    summaries: list[CaptureMeasurementSummary],
    axis_getter,
    metric: str,
    target_axis: int,
) -> float | None:
    if not summaries:
        return None
    grouped: dict[int, list[float]] = defaultdict(list)
    for summary in summaries:
        grouped[int(axis_getter(summary))].append(_measurement_value(summary, metric))
    points = sorted((axis, _median(values)) for axis, values in grouped.items())
    if not points:
        return None
    if len(points) == 1:
        return points[0][1]
    for axis, value in points:
        if axis == target_axis:
            return value
    for idx in range(1, len(points)):
        left_axis, left_value = points[idx - 1]
        right_axis, right_value = points[idx]
        if left_axis <= target_axis <= right_axis:
            if left_axis == right_axis:
                return (left_value + right_value) * 0.5
            t = (float(target_axis) - float(left_axis)) / float(right_axis - left_axis)
            return left_value + t * (right_value - left_value)
    if target_axis < points[0][0]:
        return points[0][1]
    return points[-1][1]


def _fallback_inverse_distance_metric(
    summaries: list[CaptureMeasurementSummary],
    target_state: tuple[str, str, int, int, int],
    metric: str,
) -> float | None:
    if not summaries:
        return None
    target_lower = target_state[2]
    target_upper = target_state[3]
    target_bfi = target_state[4]
    ranked: list[tuple[float, float]] = []
    for summary in summaries:
        distance = (
            abs(summary.lower_value - target_lower)
            + abs(summary.upper_value - target_upper)
            + (abs(summary.bfi - target_bfi) * 96)
        )
        ranked.append((float(distance), _measurement_value(summary, metric)))
    ranked.sort(key=lambda item: item[0])
    weighted_total = 0.0
    weight_sum = 0.0
    for distance, value in ranked[:6]:
        weight = 1.0 / max(1.0, distance)
        weighted_total += value * weight
        weight_sum += weight
    if weight_sum <= 0.0:
        return None
    return weighted_total / weight_sum


def _predict_xyz_for_state(
    target_state: tuple[str, str, int, int, int],
    by_lower_bfi: dict[tuple[str, str, int, int], list[CaptureMeasurementSummary]],
    by_lower_upper: dict[tuple[str, str, int, int], list[CaptureMeasurementSummary]],
    by_span_bfi: dict[tuple[str, str, int, int], list[CaptureMeasurementSummary]],
    by_channel_mode: dict[tuple[str, str], list[CaptureMeasurementSummary]],
) -> tuple[float, float, float] | None:
    channel, mode, lower_value, upper_value, bfi = target_state
    span = upper_value - lower_value
    xyz: list[float] = []

    for metric in CAPTURE_METRIC_FIELDS:
        predictions: list[float] = []

        same_upper_group = by_lower_bfi.get((channel, mode, lower_value, bfi), [])
        pred = _interpolate_axis_metric(same_upper_group, lambda item: item.upper_value, metric, upper_value)
        if pred is not None:
            predictions.append(pred)

        same_lower_group = by_span_bfi.get((channel, mode, span, bfi), [])
        pred = _interpolate_axis_metric(same_lower_group, lambda item: item.lower_value, metric, lower_value)
        if pred is not None:
            predictions.append(pred)

        same_bfi_group = by_lower_upper.get((channel, mode, lower_value, upper_value), [])
        pred = _interpolate_axis_metric(same_bfi_group, lambda item: item.bfi, metric, bfi)
        if pred is not None:
            predictions.append(pred)

        if not predictions:
            pred = _fallback_inverse_distance_metric(by_channel_mode.get((channel, mode), []), target_state, metric)
            if pred is not None:
                predictions.append(pred)

        if not predictions:
            return None

        xyz.append(max(0.0, _median(predictions)))

    return (xyz[0], xyz[1], xyz[2])


def _xyz_to_xy(X: float, Y: float, Z: float) -> tuple[float, float]:
    total = float(X) + float(Y) + float(Z)
    if total <= 0.0:
        return 0.0, 0.0
    return float(X) / total, float(Y) / total


def _u8_to_q16(value: Any) -> int:
    return max(0, min(255, _safe_int(value, 0))) * 257


def _build_interpolated_capture_row(
    plan_row: dict[str, Any],
    xyz: tuple[float, float, float],
    repeat_index: int,
) -> dict[str, Any]:
    mode = _normalize_mode(plan_row.get("mode", "blend8"), default="blend8")
    use_fill16 = 1 if mode in {"fill16", "blend16"} or _parse_bool(plan_row.get("use_fill16"), default=False) else 0

    r = _safe_int(plan_row.get("r", 0))
    g = _safe_int(plan_row.get("g", 0))
    b = _safe_int(plan_row.get("b", 0))
    w = _safe_int(plan_row.get("w", 0))
    lower_r = _safe_int(plan_row.get("lower_r", 0))
    lower_g = _safe_int(plan_row.get("lower_g", 0))
    lower_b = _safe_int(plan_row.get("lower_b", 0))
    lower_w = _safe_int(plan_row.get("lower_w", 0))
    upper_r = _safe_int(plan_row.get("upper_r", r))
    upper_g = _safe_int(plan_row.get("upper_g", g))
    upper_b = _safe_int(plan_row.get("upper_b", b))
    upper_w = _safe_int(plan_row.get("upper_w", w))
    bfi_r = _safe_int(plan_row.get("bfi_r", 0))
    bfi_g = _safe_int(plan_row.get("bfi_g", 0))
    bfi_b = _safe_int(plan_row.get("bfi_b", 0))
    bfi_w = _safe_int(plan_row.get("bfi_w", 0))
    high_count_r = _safe_int(plan_row.get("high_count_r", 0))
    high_count_g = _safe_int(plan_row.get("high_count_g", 0))
    high_count_b = _safe_int(plan_row.get("high_count_b", 0))
    high_count_w = _safe_int(plan_row.get("high_count_w", 0))
    cycle_length = max(1, _safe_int(plan_row.get("cycle_length", 5), 5))
    solver_mode = _safe_int(plan_row.get("solver_mode", 0))

    X, Y, Z = xyz
    x, y = _xyz_to_xy(X, Y, Z)

    return {
        "name": str(plan_row.get("name", "interpolated_state")),
        "mode": mode,
        "use_fill16": use_fill16,
        "r": r,
        "g": g,
        "b": b,
        "w": w,
        "lower_r": lower_r,
        "lower_g": lower_g,
        "lower_b": lower_b,
        "lower_w": lower_w,
        "upper_r": upper_r,
        "upper_g": upper_g,
        "upper_b": upper_b,
        "upper_w": upper_w,
        "r16": _u8_to_q16(r),
        "g16": _u8_to_q16(g),
        "b16": _u8_to_q16(b),
        "w16": _u8_to_q16(w),
        "bfi_r": bfi_r,
        "bfi_g": bfi_g,
        "bfi_b": bfi_b,
        "bfi_w": bfi_w,
        "lower_r16": _u8_to_q16(lower_r),
        "lower_g16": _u8_to_q16(lower_g),
        "lower_b16": _u8_to_q16(lower_b),
        "lower_w16": _u8_to_q16(lower_w),
        "upper_r16": _u8_to_q16(upper_r),
        "upper_g16": _u8_to_q16(upper_g),
        "upper_b16": _u8_to_q16(upper_b),
        "upper_w16": _u8_to_q16(upper_w),
        "high_count_r": high_count_r,
        "high_count_g": high_count_g,
        "high_count_b": high_count_b,
        "high_count_w": high_count_w,
        "cycle_length": cycle_length,
        "repeat_index": max(0, int(repeat_index)),
        "solver_mode": solver_mode,
        "ok": True,
        "returncode": 0,
        "elapsed_s": 0.0,
        "timed_out": False,
        "X": X,
        "Y": Y,
        "Z": Z,
        "x": x,
        "y": y,
    }


def _ensure_chunk_output_is_new(base_path: Path) -> None:
    suffix = base_path.suffix or ".csv"
    stem = base_path.stem if base_path.suffix else base_path.name
    existing = sorted(base_path.parent.glob(f"{stem}_part*{suffix}"))
    if base_path.exists() or existing:
        joined = ", ".join(str(path) for path in existing[:3])
        raise FileExistsError(f"Refusing to overwrite existing interpolated capture output set at {base_path}. Existing chunks: {joined}")


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.resolve().relative_to(other.resolve())
        return True
    except ValueError:
        return False


def _validate_interpolated_output_path(capture_dir: Path, out_path: Path) -> None:
    capture_dir_resolved = capture_dir.resolve()
    out_parent_resolved = out_path.parent.resolve()
    if out_parent_resolved == capture_dir_resolved or _is_relative_to(out_parent_resolved, capture_dir_resolved):
        raise ValueError(
            "Interpolated capture output must be written outside the pruned capture source directory. "
            f"Capture dir: {capture_dir_resolved} Output dir: {out_parent_resolved}"
        )


def _validate_combined_output_path(pruned_capture_dir: Path, interpolated_capture_dir: Path, out_path: Path) -> None:
    out_parent_resolved = out_path.parent.resolve()
    pruned_resolved = pruned_capture_dir.resolve()
    interpolated_resolved = interpolated_capture_dir.resolve()
    if out_parent_resolved == pruned_resolved or _is_relative_to(out_parent_resolved, pruned_resolved):
        raise ValueError(
            "Combined capture output must be written outside the pruned capture directory. "
            f"Pruned dir: {pruned_resolved} Output dir: {out_parent_resolved}"
        )
    if out_parent_resolved == interpolated_resolved or _is_relative_to(out_parent_resolved, interpolated_resolved):
        raise ValueError(
            "Combined capture output must be written outside the interpolated capture directory. "
            f"Interpolated dir: {interpolated_resolved} Output dir: {out_parent_resolved}"
        )


def _resolve_target_plan_paths(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    if getattr(args, "missing_plan", None):
        paths.append(Path(args.missing_plan))
    target_plan_dir = getattr(args, "target_plan_dir", None)
    if target_plan_dir:
        root = Path(target_plan_dir)
        for pattern in list(getattr(args, "target_plan_globs", None) or DEFAULT_TARGET_PLAN_GLOBS):
            paths.extend(sorted(root.glob(pattern)))

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(path)

    if not deduped:
        raise ValueError("Provide --missing-plan or --target-plan-dir so interpolation knows the full desired state set")
    return deduped


def _infer_repeats_from_code(value: int, bfi: int) -> int:
    est = (int(value) / 255.0) / (int(bfi) + 1)
    if est > 0.5:
        return 1
    if est > 0.15:
        return 2
    if est > 0.03:
        return 4
    return 8


def _infer_repeats_from_blend(value: int, floor: int, bfi: int) -> int:
    avg = ((int(value) + int(floor) * int(bfi)) / max(1, int(bfi) + 1)) / 255.0
    if avg > 0.5:
        return 1
    if avg > 0.15:
        return 2
    if avg > 0.03:
        return 4
    return 8


def _build_dense_fill8_plan_row(channel: str, value: int) -> dict[str, Any]:
    idx = CHANNEL_INDEX[channel]
    upper = [0, 0, 0, 0]
    upper[idx] = int(value)
    return {
        "name": f"{channel}_v{value:03d}_bfi0",
        "mode": "fill8",
        "r": upper[0],
        "g": upper[1],
        "b": upper[2],
        "w": upper[3],
        "lower_r": 0,
        "lower_g": 0,
        "lower_b": 0,
        "lower_w": 0,
        "upper_r": upper[0],
        "upper_g": upper[1],
        "upper_b": upper[2],
        "upper_w": upper[3],
        "bfi_r": 0,
        "bfi_g": 0,
        "bfi_b": 0,
        "bfi_w": 0,
        "repeats": _infer_repeats_from_code(value, 0),
    }


def _build_dense_blend8_plan_row(channel: str, lower_value: int, upper_value: int, bfi: int) -> dict[str, Any]:
    idx = CHANNEL_INDEX[channel]
    lower = [0, 0, 0, 0]
    upper = [0, 0, 0, 0]
    bfi_values = [0, 0, 0, 0]
    lower[idx] = int(lower_value)
    upper[idx] = int(upper_value)
    bfi_values[idx] = int(bfi)
    return {
        "name": f"{channel}_floor{lower_value:03d}_v{upper_value:03d}_bfi{bfi}",
        "mode": "blend8",
        "r": upper[0],
        "g": upper[1],
        "b": upper[2],
        "w": upper[3],
        "lower_r": lower[0],
        "lower_g": lower[1],
        "lower_b": lower[2],
        "lower_w": lower[3],
        "upper_r": upper[0],
        "upper_g": upper[1],
        "upper_b": upper[2],
        "upper_w": upper[3],
        "bfi_r": bfi_values[0],
        "bfi_g": bfi_values[1],
        "bfi_b": bfi_values[2],
        "bfi_w": bfi_values[3],
        "repeats": _infer_repeats_from_blend(upper_value, lower_value, bfi),
    }


def _build_dense_state_rows(channels: list[str], max_bfi: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for channel in channels:
        for value in range(256):
            rows.append(_build_dense_fill8_plan_row(channel, value))
        for lower_value in range(255):
            for upper_value in range(lower_value + 1, 256):
                for bfi in range(1, max_bfi + 1):
                    rows.append(_build_dense_blend8_plan_row(channel, lower_value, upper_value, bfi))
    rows.sort(key=_capture_row_sort_key)
    return rows


def _target_row_output_repeat_index(plan_row: dict[str, Any]) -> int:
    explicit_repeat = plan_row.get("repeat_index")
    if explicit_repeat not in (None, ""):
        return max(0, _safe_int(explicit_repeat, 0))
    return 0


def write_interpolated_capture_csvs(
    capture_dir: Path,
    out_path: Path,
    chunk_rows: int,
    input_globs: list[str] | None = None,
    target_plan_rows: list[dict[str, Any]] | None = None,
    target_plan_paths: list[Path] | None = None,
) -> InterpolatedCaptureStats:
    summaries, stats = summarize_capture_measurements(capture_dir, input_globs=input_globs)
    repaired_states, constraint_indexes = _repair_measurement_summaries(summaries)
    stats.source_states_repaired = len(repaired_states)
    by_lower_bfi, by_lower_upper, by_span_bfi, by_channel_mode = _build_measurement_indexes(summaries)
    constraint_by_lower_bfi, constraint_by_lower_upper, constraint_by_span_bfi, _constraint_by_upper_bfi, fill8_levels, same_upper_max = constraint_indexes
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_chunk_output_is_new(out_path)
    chunk_rows = max(1, int(chunk_rows))
    chunk_handle = None
    writer = None
    rows_in_chunk = 0
    emitted_states: set[tuple[str, str, int, int, int]] = set()

    def open_next_chunk() -> None:
        nonlocal chunk_handle, writer, rows_in_chunk
        if chunk_handle is not None:
            chunk_handle.close()
        chunk_path = _chunk_output_path(out_path, stats.chunk_files_written + 1)
        chunk_handle = chunk_path.open("w", encoding="utf-8", newline="")
        writer = csv.DictWriter(chunk_handle, fieldnames=INTERPOLATED_CAPTURE_FIELDS)
        writer.writeheader()
        rows_in_chunk = 0
        stats.chunk_files_written += 1
        stats.chunk_paths.append(chunk_path)

    try:
        def emit_plan_row(plan_row: dict[str, Any]) -> None:
            nonlocal writer, rows_in_chunk
            state = _capture_state_from_record(plan_row)
            if state is None:
                return
            if state in emitted_states:
                return
            stats.requested_states += 1
            if state in summaries:
                stats.states_already_present += 1
                emitted_states.add(state)
                return
            predicted_xyz = _predict_xyz_for_state(state, by_lower_bfi, by_lower_upper, by_span_bfi, by_channel_mode)
            if predicted_xyz is None:
                stats.states_unresolved += 1
                stats.unresolved_states.append(state)
                emitted_states.add(state)
                return
            lower_bound, upper_bound = _compute_measurement_y_bounds(
                state,
                constraint_by_lower_bfi,
                constraint_by_lower_upper,
                constraint_by_span_bfi,
                fill8_levels,
                same_upper_max,
            )
            predicted_xyz, changed = _clamp_xyz_to_y_bounds(predicted_xyz, lower_bound, upper_bound)
            if changed:
                stats.states_clamped += 1
            stats.states_interpolated += 1
            if writer is None or rows_in_chunk >= chunk_rows:
                open_next_chunk()
            writer.writerow(_build_interpolated_capture_row(plan_row, predicted_xyz, _target_row_output_repeat_index(plan_row)))
            rows_in_chunk += 1
            stats.rows_written += 1
            synthetic_summary = _build_capture_summary_from_plan_row(state, plan_row, predicted_xyz)
            _register_summary_for_interpolation(
                synthetic_summary,
                summaries,
                by_lower_bfi,
                by_lower_upper,
                by_span_bfi,
                by_channel_mode,
                constraint_by_lower_bfi,
                constraint_by_lower_upper,
                constraint_by_span_bfi,
                fill8_levels,
                same_upper_max,
            )
            emitted_states.add(state)

        if target_plan_rows is not None:
            for plan_row in target_plan_rows:
                emit_plan_row(plan_row)
        elif target_plan_paths is not None:
            for target_plan_path in target_plan_paths:
                with target_plan_path.open("r", newline="", encoding="utf-8-sig") as handle:
                    reader = csv.DictReader(handle)
                    for plan_row in reader:
                        emit_plan_row(plan_row)
        else:
            raise ValueError("target_plan_rows or target_plan_paths is required")
    finally:
        if chunk_handle is not None:
            chunk_handle.close()

    return stats


def write_combined_capture_csvs(
    pruned_capture_dir: Path,
    interpolated_capture_dir: Path,
    out_path: Path,
    chunk_rows: int,
    pruned_globs: list[str] | None = None,
    interpolated_globs: list[str] | None = None,
) -> CombinedCaptureStats:
    stats = CombinedCaptureStats()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_chunk_output_is_new(out_path)
    chunk_rows = max(1, int(chunk_rows))

    rows: list[dict[str, Any]] = []
    fieldnames: list[str] | None = None

    def collect_from_dir(root: Path, patterns: list[str]) -> None:
        nonlocal fieldnames
        for pattern in patterns:
            for path in sorted(root.glob(pattern)):
                stats.source_files_scanned += 1
                with path.open("r", newline="", encoding="utf-8-sig") as handle:
                    reader = csv.DictReader(handle)
                    if reader.fieldnames is None:
                        continue
                    fieldnames = _merge_capture_fieldnames(fieldnames, reader.fieldnames)
                    for rec in reader:
                        stats.rows_seen += 1
                        rows.append(dict(rec))

    collect_from_dir(pruned_capture_dir, list(pruned_globs or DEFAULT_PRUNED_CAPTURE_GLOBS))
    collect_from_dir(interpolated_capture_dir, list(interpolated_globs or DEFAULT_INTERPOLATED_CAPTURE_GLOBS))

    if fieldnames is None:
        raise ValueError("No capture rows were found to combine")

    summaries = summarize_capture_measurement_rows(rows)
    repaired_states, _constraint_indexes = _repair_measurement_summaries(summaries)
    stats.states_repaired = len(repaired_states)
    if repaired_states:
        for rec in rows:
            state = _capture_state_from_record(rec)
            if state is None or state not in repaired_states:
                continue
            summary = summaries.get(state)
            if summary is None:
                continue
            if _apply_summary_xyz_to_capture_row(rec, summary):
                stats.rows_retuned += 1

    rows.sort(key=_capture_row_sort_key)

    chunk_handle = None
    writer = None
    rows_in_chunk = 0

    def open_next_chunk() -> None:
        nonlocal chunk_handle, writer, rows_in_chunk
        if chunk_handle is not None:
            chunk_handle.close()
        chunk_path = _chunk_output_path(out_path, stats.chunk_files_written + 1)
        chunk_handle = chunk_path.open("w", encoding="utf-8", newline="")
        writer = csv.DictWriter(chunk_handle, fieldnames=fieldnames)
        writer.writeheader()
        rows_in_chunk = 0
        stats.chunk_files_written += 1
        stats.chunk_paths.append(chunk_path)

    try:
        for rec in rows:
            if writer is None or rows_in_chunk >= chunk_rows:
                open_next_chunk()
            writer.writerow(rec)
            rows_in_chunk += 1
            stats.rows_written += 1
    finally:
        if chunk_handle is not None:
            chunk_handle.close()

    return stats


def _run_xy_drift_pass(
    rows_by_channel: dict[str, list[LadderRow]],
    measurement_stats: dict[tuple[str, str, int, int, int], MeasurementStats],
    findings: list[Finding],
    xy_drift_threshold: float,
    xy_spread_threshold: float,
    min_xy_samples: int,
) -> None:
    if not measurement_stats:
        return

    channel_centers: dict[str, tuple[float, float]] = {}
    for channel in CHANNELS:
        channel_rows = [stats for stats in measurement_stats.values() if stats.channel == channel]
        if not channel_rows:
            continue
        channel_centers[channel] = (
            _median([stats.median_x for stats in channel_rows]),
            _median([stats.median_y for stats in channel_rows]),
        )

    for rows in rows_by_channel.values():
        for row in rows:
            stats = measurement_stats.get(row.key())
            if stats is None or stats.samples < min_xy_samples:
                continue
            center = channel_centers.get(row.channel)
            if center is None:
                continue
            radius = math.dist((stats.median_x, stats.median_y), center)
            if radius > xy_drift_threshold:
                detail = (
                    f"Median chromaticity drifted to x={stats.median_x:.6f}, y={stats.median_y:.6f}; "
                    f"channel baseline is x={center[0]:.6f}, y={center[1]:.6f}."
                )
                _append_finding(findings, row, "xy_drift", detail, radius, "recapture")
            if stats.max_xy_radius > xy_spread_threshold:
                detail = (
                    f"Per-state XY sample spread reached {stats.max_xy_radius:.6f} across {stats.samples} samples, "
                    f"which matches the intermittent white-flash hardware bug pattern."
                )
                _append_finding(findings, row, "xy_spread", detail, stats.max_xy_radius, "recapture")


def analyze_ladders(
    lut_dir: Path,
    channels: list[str],
    measurement_xy_path: Path | None,
    monotonic_tolerance_q16: int,
    bfi_tolerance_q16: int,
    lower_floor_tolerance_q16: int,
    upper_residual_floor_q16: int,
    upper_residual_ratio: float,
    xy_drift_threshold: float,
    xy_spread_threshold: float,
    min_xy_samples: int,
    capture_dir: Path | None = None,
    capture_input_globs: list[str] | None = None,
) -> AnalysisResult:
    rows_by_channel = load_ladders(lut_dir, channels)
    measurement_stats = load_measurement_stats(measurement_xy_path)
    findings: list[Finding] = []

    _run_primary_upper_pass(rows_by_channel, findings, monotonic_tolerance_q16)
    _run_bfi_pass(rows_by_channel, findings, bfi_tolerance_q16)
    _run_lower_floor_pass(rows_by_channel, findings, lower_floor_tolerance_q16)
    _run_upper_residual_pass(rows_by_channel, findings, upper_residual_floor_q16, upper_residual_ratio)
    _run_xy_drift_pass(rows_by_channel, measurement_stats, findings, xy_drift_threshold, xy_spread_threshold, min_xy_samples)

    if capture_dir is not None:
        findings.extend(
            _find_capture_summary_outliers(
                capture_dir=capture_dir,
                channels=channels,
                input_globs=capture_input_globs,
                monotonic_tolerance_q16=monotonic_tolerance_q16,
                bfi_tolerance_q16=bfi_tolerance_q16,
                lower_floor_tolerance_q16=lower_floor_tolerance_q16,
                upper_residual_floor_q16=upper_residual_floor_q16,
                upper_residual_ratio=upper_residual_ratio,
            )
        )

    return AnalysisResult(rows_by_channel=rows_by_channel, findings=findings, measurement_stats=measurement_stats)


def _build_constraint_maps(rows: list[LadderRow]) -> tuple[dict[tuple[str, str, int, int, int], list[int]], dict[tuple[str, str, int, int, int], list[int]]]:
    preds: dict[tuple[str, str, int, int, int], list[int]] = defaultdict(list)
    succs: dict[tuple[str, str, int, int, int], list[int]] = defaultdict(list)

    by_lower_bfi: dict[tuple[int, int], list[LadderRow]] = defaultdict(list)
    by_lower_upper: dict[tuple[int, int], list[LadderRow]] = defaultdict(list)
    by_span_bfi: dict[tuple[int, int], list[LadderRow]] = defaultdict(list)
    for row in rows:
        by_lower_bfi[(row.lower_value, row.bfi)].append(row)
        by_lower_upper[(row.lower_value, row.upper_value)].append(row)
        if row.span > 0:
            by_span_bfi[(row.span, row.bfi)].append(row)

    for group in by_lower_bfi.values():
        group.sort(key=lambda row: (row.upper_value, row.row_index))
        for idx in range(1, len(group)):
            a = group[idx - 1].key()
            b = group[idx].key()
            preds[b].append(group[idx - 1].output_q16)
            succs[a].append(group[idx].output_q16)

    for group in by_lower_upper.values():
        group.sort(key=lambda row: (row.bfi, row.row_index))
        for idx in range(1, len(group)):
            lower_bfi_key = group[idx].key()
            higher_rank_key = group[idx - 1].key()
            preds[higher_rank_key].append(group[idx].output_q16)
            succs[lower_bfi_key].append(group[idx - 1].output_q16)

    for group in by_span_bfi.values():
        group.sort(key=lambda row: (row.lower_value, row.row_index))
        for idx in range(1, len(group)):
            a = group[idx - 1].key()
            b = group[idx].key()
            preds[b].append(group[idx - 1].output_q16)
            succs[a].append(group[idx].output_q16)

    return preds, succs


def _build_group_indexes(rows: list[LadderRow]) -> tuple[
    dict[tuple[int, int], list[LadderRow]],
    dict[tuple[int, int], list[LadderRow]],
    dict[tuple[int, int], list[LadderRow]],
]:
    by_lower_bfi: dict[tuple[int, int], list[LadderRow]] = defaultdict(list)
    by_lower_upper: dict[tuple[int, int], list[LadderRow]] = defaultdict(list)
    by_span_bfi: dict[tuple[int, int], list[LadderRow]] = defaultdict(list)
    for row in rows:
        by_lower_bfi[(row.lower_value, row.bfi)].append(row)
        by_lower_upper[(row.lower_value, row.upper_value)].append(row)
        if row.span > 0:
            by_span_bfi[(row.span, row.bfi)].append(row)

    for group in by_lower_bfi.values():
        group.sort(key=lambda row: (row.upper_value, row.row_index))
    for group in by_lower_upper.values():
        group.sort(key=lambda row: (row.bfi, row.row_index))
    for group in by_span_bfi.values():
        group.sort(key=lambda row: (row.lower_value, row.row_index))

    return by_lower_bfi, by_lower_upper, by_span_bfi


def _local_predictions_for_row(
    row: LadderRow,
    by_lower_bfi: dict[tuple[int, int], list[LadderRow]],
    by_lower_upper: dict[tuple[int, int], list[LadderRow]],
    by_span_bfi: dict[tuple[int, int], list[LadderRow]],
) -> list[float]:
    predictions: list[float] = []

    upper_group = by_lower_bfi.get((row.lower_value, row.bfi), [])
    if row in upper_group:
        predictions.append(_local_expected_q16(upper_group, upper_group.index(row), lambda current: current.upper_value))

    bfi_group = by_lower_upper.get((row.lower_value, row.upper_value), [])
    if row in bfi_group:
        predictions.append(_local_expected_q16(bfi_group, bfi_group.index(row), lambda current: current.bfi))

    lower_group = by_span_bfi.get((row.span, row.bfi), [])
    if row in lower_group:
        predictions.append(_local_expected_q16(lower_group, lower_group.index(row), lambda current: current.lower_value))

    return predictions


def _repair_flagged_rows(rows_by_channel: dict[str, list[LadderRow]]) -> None:
    for channel, rows in rows_by_channel.items():
        _ = channel
        preds, succs = _build_constraint_maps(rows)
        by_lower_bfi, by_lower_upper, by_span_bfi = _build_group_indexes(rows)
        peak_est = max((row.original_estimated_output for row in rows), default=0.0)
        peak_q16 = max((row.original_output_q16 for row in rows), default=0)
        est_per_q16 = (peak_est / peak_q16) if peak_est > 0.0 and peak_q16 > 0 else 0.0

        row_lookup = {row.key(): row for row in rows}
        for row in rows:
            if not row.flags:
                continue
            lower_bound = max(preds.get(row.key(), [0])) if preds.get(row.key()) else 0
            upper_bound = min(succs.get(row.key(), [65535])) if succs.get(row.key()) else 65535
            local_predictions = _local_predictions_for_row(row, by_lower_bfi, by_lower_upper, by_span_bfi)
            predicted = round(_median(local_predictions, float(row.output_q16)))
            if lower_bound > upper_bound:
                repaired_q16 = round((lower_bound + upper_bound) * 0.5)
            else:
                repaired_q16 = min(max(predicted, lower_bound), upper_bound)
            repaired_q16 = max(0, min(65535, repaired_q16))
            row.output_q16 = repaired_q16
            row.normalized_output = repaired_q16 / 65535.0
            if est_per_q16 > 0.0:
                row.estimated_output = repaired_q16 * est_per_q16
            row.recommended_action = row.recommended_action or "fix"
            row_lookup[row.key()] = row


def _prune_flagged_rows(rows_by_channel: dict[str, list[LadderRow]]) -> dict[str, list[LadderRow]]:
    return {
        channel: [row for row in rows if not row.flags]
        for channel, rows in rows_by_channel.items()
    }


def _rows_to_jsonable(rows: list[LadderRow]) -> list[dict[str, Any]]:
    return [
        {
            "mode": row.mode,
            "lower_value": row.lower_value,
            "upper_value": row.upper_value,
            "value": row.value,
            "bfi": row.bfi,
            "estimated_output": row.estimated_output,
            "output_q16": row.output_q16,
            "normalized_output": row.normalized_output,
        }
        for row in rows
    ]


def _capture_summary_is_anchor(summary: CaptureMeasurementSummary) -> bool:
    return summary.mode == "fill8" and summary.lower_value == 0 and summary.bfi == 0


def _capture_summary_output_q16(summary: CaptureMeasurementSummary, channel_peaks: dict[str, float]) -> int:
    channel_peak = channel_peaks.get(summary.channel, 0.0)
    if channel_peak <= 0.0:
        return 0
    return max(0, min(65535, round((float(summary.median_Y) / channel_peak) * 65535.0)))


def _local_expected_summary_q16(
    group: list[CaptureMeasurementSummary],
    idx: int,
    axis_value_getter,
    channel_peaks: dict[str, float],
) -> float:
    current_axis = axis_value_getter(group[idx])
    neighbors: list[tuple[float, float]] = []
    if idx - 1 >= 0:
        neighbors.append((float(axis_value_getter(group[idx - 1])), float(_capture_summary_output_q16(group[idx - 1], channel_peaks))))
    if idx + 1 < len(group):
        neighbors.append((float(axis_value_getter(group[idx + 1])), float(_capture_summary_output_q16(group[idx + 1], channel_peaks))))
    current_q16 = float(_capture_summary_output_q16(group[idx], channel_peaks))
    if not neighbors:
        return current_q16
    if len(neighbors) == 1:
        return neighbors[0][1]
    (x0, y0), (x1, y1) = neighbors
    if math.isclose(x0, x1):
        return (y0 + y1) * 0.5
    t = (current_axis - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def _select_capture_summary_suspect(
    group: list[CaptureMeasurementSummary],
    idx_a: int,
    idx_b: int,
    axis_value_getter,
    channel_peaks: dict[str, float],
) -> int:
    summary_a = group[idx_a]
    summary_b = group[idx_b]
    anchor_a = _capture_summary_is_anchor(summary_a)
    anchor_b = _capture_summary_is_anchor(summary_b)
    if anchor_a and not anchor_b:
        return idx_b
    if anchor_b and not anchor_a:
        return idx_a
    dev_a = abs(float(_capture_summary_output_q16(summary_a, channel_peaks)) - _local_expected_summary_q16(group, idx_a, axis_value_getter, channel_peaks))
    dev_b = abs(float(_capture_summary_output_q16(summary_b, channel_peaks)) - _local_expected_summary_q16(group, idx_b, axis_value_getter, channel_peaks))
    if dev_b > dev_a:
        return idx_b
    if dev_a > dev_b:
        return idx_a
    if summary_b.samples < summary_a.samples:
        return idx_b
    if summary_a.samples < summary_b.samples:
        return idx_a
    return idx_b


def _append_capture_summary_finding(
    findings: list[Finding],
    summary: CaptureMeasurementSummary,
    channel_peaks: dict[str, float],
    pass_name: str,
    detail: str,
    severity: float,
    allow_anchor: bool = False,
) -> None:
    if _capture_summary_is_anchor(summary) and not allow_anchor:
        return
    findings.append(
        Finding(
            channel=summary.channel,
            mode=summary.mode,
            lower_value=summary.lower_value,
            upper_value=summary.upper_value,
            value=summary.upper_value,
            bfi=summary.bfi,
            output_q16=_capture_summary_output_q16(summary, channel_peaks),
            estimated_output=float(summary.median_Y),
            pass_name=pass_name,
            detail=detail,
            severity=float(severity),
            recommended_action="prune",
        )
    )


def _find_capture_summary_outliers(
    capture_dir: Path,
    channels: list[str],
    input_globs: list[str] | None,
    monotonic_tolerance_q16: int,
    bfi_tolerance_q16: int,
    lower_floor_tolerance_q16: int,
    upper_residual_floor_q16: int,
    upper_residual_ratio: float,
    max_passes: int = DEFAULT_CAPTURE_SUMMARY_PRUNE_PASSES,
) -> list[Finding]:
    summaries, _stats = summarize_capture_measurements(capture_dir, input_globs=list(input_globs or DEFAULT_CAPTURE_GLOBS))
    allowed_channels = set(channels)
    working = {
        state: summary
        for state, summary in summaries.items()
        if summary.channel in allowed_channels
    }

    all_findings: list[Finding] = []
    seen_states: set[tuple[str, str, int, int, int]] = set()

    for pass_num in range(max(1, max_passes)):
        channel_peaks: dict[str, float] = {channel: 0.0 for channel in channels}
        for summary in working.values():
            channel_peaks[summary.channel] = max(channel_peaks.get(summary.channel, 0.0), float(summary.median_Y))

        tolerance_by_channel = {
            channel: (channel_peaks.get(channel, 0.0) * float(monotonic_tolerance_q16) / 65535.0) if channel_peaks.get(channel, 0.0) > 0.0 else 0.0
            for channel in channels
        }
        bfi_tolerance_by_channel = {
            channel: (channel_peaks.get(channel, 0.0) * float(bfi_tolerance_q16) / 65535.0) if channel_peaks.get(channel, 0.0) > 0.0 else 0.0
            for channel in channels
        }
        lower_floor_tolerance_by_channel = {
            channel: (channel_peaks.get(channel, 0.0) * float(lower_floor_tolerance_q16) / 65535.0) if channel_peaks.get(channel, 0.0) > 0.0 else 0.0
            for channel in channels
        }

        pass_findings: list[Finding] = []

        def append_once(summary: CaptureMeasurementSummary, pass_name: str, detail: str, severity: float, allow_anchor: bool = False) -> None:
            state = summary.key()
            if state in seen_states:
                return
            _append_capture_summary_finding(pass_findings, summary, channel_peaks, pass_name, detail, severity, allow_anchor=allow_anchor)
            if allow_anchor or not _capture_summary_is_anchor(summary):
                seen_states.add(state)

        by_lower_bfi, by_lower_upper, by_span_bfi, by_upper_bfi, fill8_levels, _same_upper_max = _build_summary_constraint_indexes(working)

        by_same_upper: dict[tuple[str, int], list[CaptureMeasurementSummary]] = defaultdict(list)
        for summary in working.values():
            by_same_upper[(summary.channel, summary.upper_value)].append(summary)

        fill8_anchor_families: dict[str, list[CaptureMeasurementSummary]] = defaultdict(list)
        for summary in working.values():
            if _capture_summary_is_anchor(summary):
                fill8_anchor_families[summary.channel].append(summary)

        for channel, group in fill8_anchor_families.items():
            group.sort(key=lambda item: item.upper_value)
            if len(group) < 3:
                continue
            for idx in range(1, len(group) - 1):
                summary = group[idx]
                expected_q16 = _local_expected_summary_q16(group, idx, lambda item: item.upper_value, channel_peaks)
                residual_q16 = abs(float(_capture_summary_output_q16(summary, channel_peaks)) - expected_q16)
                threshold_q16 = _residual_threshold_q16(expected_q16, int(upper_residual_floor_q16), float(upper_residual_ratio))
                if residual_q16 <= threshold_q16:
                    continue
                detail = (
                    f"Fill8 anchor family residual failed for channel={channel}, upper={summary.upper_value}: "
                    f"Y={float(summary.median_Y):.6f} deviated from local family expectation q16={round(expected_q16)} "
                    f"by {round(residual_q16)} q16."
                )
                append_once(summary, "capture_fill8_residual", detail, residual_q16, allow_anchor=True)

        for (channel, upper_value), group in by_same_upper.items():
            ceiling_y = fill8_levels.get((channel, upper_value))
            if ceiling_y is None:
                continue
            tolerance_y = tolerance_by_channel.get(channel, 0.0)
            for summary in group:
                if _capture_summary_is_anchor(summary):
                    continue
                if float(summary.median_Y) <= float(ceiling_y) + tolerance_y:
                    continue
                detail = (
                    f"Raw capture state exceeded the fill8 ceiling for channel={channel}, upper={upper_value}: "
                    f"state Y={float(summary.median_Y):.6f} vs fill8 ceiling {float(ceiling_y):.6f}."
                )
                append_once(summary, "capture_same_upper_ceiling", detail, float(summary.median_Y) - float(ceiling_y))

        for (channel, lower_value, bfi), group in by_lower_bfi.items():
            tolerance_y = tolerance_by_channel.get(channel, 0.0)
            for idx in range(1, len(group)):
                prev_summary = group[idx - 1]
                curr_summary = group[idx]
                if float(curr_summary.median_Y) + tolerance_y >= float(prev_summary.median_Y):
                    continue
                suspect = group[_select_capture_summary_suspect(group, idx - 1, idx, lambda item: item.upper_value, channel_peaks)]
                detail = (
                    f"Raw capture upper monotonicity failed for channel={channel}, lower={lower_value}, bfi={bfi}: "
                    f"upper={curr_summary.upper_value} produced Y={float(curr_summary.median_Y):.6f} after "
                    f"upper={prev_summary.upper_value} produced Y={float(prev_summary.median_Y):.6f}."
                )
                append_once(suspect, "capture_upper_monotonic", detail, float(prev_summary.median_Y) - float(curr_summary.median_Y))

        for (channel, lower_value, upper_value), group in by_lower_upper.items():
            tolerance_y = bfi_tolerance_by_channel.get(channel, 0.0)
            for idx in range(1, len(group)):
                lower_bfi_summary = group[idx - 1]
                higher_bfi_summary = group[idx]
                if float(higher_bfi_summary.median_Y) <= float(lower_bfi_summary.median_Y) + tolerance_y:
                    continue
                suspect = higher_bfi_summary
                if _capture_summary_is_anchor(higher_bfi_summary):
                    suspect = lower_bfi_summary
                detail = (
                    f"Raw capture BFI monotonicity failed for channel={channel}, lower={lower_value}, upper={upper_value}: "
                    f"bfi={higher_bfi_summary.bfi} produced Y={float(higher_bfi_summary.median_Y):.6f} which exceeded "
                    f"bfi={lower_bfi_summary.bfi} at Y={float(lower_bfi_summary.median_Y):.6f}."
                )
                append_once(suspect, "capture_bfi_monotonic", detail, float(higher_bfi_summary.median_Y) - float(lower_bfi_summary.median_Y))

        for (channel, span, bfi), group in by_span_bfi.items():
            tolerance_y = lower_floor_tolerance_by_channel.get(channel, 0.0)
            for idx in range(1, len(group)):
                prev_summary = group[idx - 1]
                curr_summary = group[idx]
                if float(curr_summary.median_Y) + tolerance_y >= float(prev_summary.median_Y):
                    continue
                suspect = group[_select_capture_summary_suspect(group, idx - 1, idx, lambda item: item.lower_value, channel_peaks)]
                detail = (
                    f"Raw capture lower-floor monotonicity failed for channel={channel}, span={span}, bfi={bfi}: "
                    f"lower={curr_summary.lower_value}/upper={curr_summary.upper_value} produced Y={float(curr_summary.median_Y):.6f} after "
                    f"lower={prev_summary.lower_value}/upper={prev_summary.upper_value} produced Y={float(prev_summary.median_Y):.6f}."
                )
                append_once(suspect, "capture_lower_floor_monotonic", detail, float(prev_summary.median_Y) - float(curr_summary.median_Y))

        # Cross-floor monotonicity: for fixed (channel, upper_value, bfi),
        # increasing lower_value must increase output.
        for (channel, upper_value, bfi), group in by_upper_bfi.items():
            tolerance_y = lower_floor_tolerance_by_channel.get(channel, 0.0)
            for idx in range(1, len(group)):
                prev_summary = group[idx - 1]
                curr_summary = group[idx]
                if float(curr_summary.median_Y) + tolerance_y >= float(prev_summary.median_Y):
                    continue
                suspect = group[_select_capture_summary_suspect(group, idx - 1, idx, lambda item: item.lower_value, channel_peaks)]
                detail = (
                    f"Raw capture cross-floor monotonicity failed for channel={channel}, upper={upper_value}, bfi={bfi}: "
                    f"lower={curr_summary.lower_value} produced Y={float(curr_summary.median_Y):.6f} after "
                    f"lower={prev_summary.lower_value} produced Y={float(prev_summary.median_Y):.6f}."
                )
                append_once(suspect, "capture_cross_floor_monotonic", detail, float(prev_summary.median_Y) - float(curr_summary.median_Y))

        if not pass_findings:
            break

        all_findings.extend(pass_findings)
        for finding in pass_findings:
            working.pop(finding.state_key(), None)

    return all_findings


def _capture_prune_state_keys(findings: list[Finding]) -> set[tuple[str, str, int, int, int]]:
    capture_states = {
        finding.state_key()
        for finding in findings
        if finding.pass_name.startswith("capture_") or finding.recommended_action == "prune"
    }
    if capture_states:
        return capture_states
    return {finding.state_key() for finding in findings}


def analyze_raw_captures(
    capture_dir: Path,
    channels: list[str],
    monotonic_tolerance_q16: int,
    bfi_tolerance_q16: int,
    lower_floor_tolerance_q16: int,
    upper_residual_floor_q16: int,
    upper_residual_ratio: float,
    capture_input_globs: list[str] | None = None,
) -> AnalysisResult:
    findings = _find_capture_summary_outliers(
        capture_dir=capture_dir,
        channels=channels,
        input_globs=capture_input_globs,
        monotonic_tolerance_q16=monotonic_tolerance_q16,
        bfi_tolerance_q16=bfi_tolerance_q16,
        lower_floor_tolerance_q16=lower_floor_tolerance_q16,
        upper_residual_floor_q16=upper_residual_floor_q16,
        upper_residual_ratio=upper_residual_ratio,
    )
    return AnalysisResult(rows_by_channel={}, findings=findings, measurement_stats={})


def _write_channel_ladder(out_dir: Path, channel: str, rows: list[LadderRow]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{channel.lower()}{LADDER_SUFFIX}"
    json_path = out_dir / f"{stem}.json"
    csv_path = out_dir / f"{stem}.csv"
    payload = _rows_to_jsonable(rows)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["mode", "lower_value", "upper_value", "value", "bfi", "estimated_output", "output_q16", "normalized_output"],
        )
        writer.writeheader()
        writer.writerows(payload)


def _write_report(report_path: Path, analysis: AnalysisResult, action: str) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    grouped_counts: dict[str, int] = defaultdict(int)
    channel_counts: dict[str, int] = defaultdict(int)
    for finding in analysis.findings:
        grouped_counts[finding.pass_name] += 1
        channel_counts[finding.channel] += 1
    unique_states = {finding.state_key() for finding in analysis.findings}
    payload = {
        "action": action,
        "summary": {
            "total_findings": len(analysis.findings),
            "unique_flagged_states": len(unique_states),
            "findings_by_pass": dict(sorted(grouped_counts.items())),
            "findings_by_channel": dict(sorted(channel_counts.items())),
        },
        "findings": [
            {
                "channel": finding.channel,
                "mode": finding.mode,
                "lower_value": finding.lower_value,
                "upper_value": finding.upper_value,
                "value": finding.value,
                "bfi": finding.bfi,
                "output_q16": finding.output_q16,
                "estimated_output": finding.estimated_output,
                "pass": finding.pass_name,
                "detail": finding.detail,
                "severity": finding.severity,
                "recommended_action": finding.recommended_action,
            }
            for finding in analysis.findings
        ],
    }
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_recapture_csv(path: Path, analysis: AnalysisResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state_map: dict[tuple[str, str, int, int, int], dict[str, Any]] = {}
    for finding in analysis.findings:
        key = finding.state_key()
        entry = state_map.setdefault(
            key,
            {
                "channel": finding.channel,
                "mode": finding.mode,
                "lower_value": finding.lower_value,
                "upper_value": finding.upper_value,
                "value": finding.value,
                "bfi": finding.bfi,
                "passes": [],
                "recommended_action": finding.recommended_action,
                "details": [],
            },
        )
        entry["passes"].append(finding.pass_name)
        entry["details"].append(finding.detail)
        if finding.recommended_action == "recapture":
            entry["recommended_action"] = "recapture"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["channel", "mode", "lower_value", "upper_value", "value", "bfi", "passes", "recommended_action", "details"],
        )
        writer.writeheader()
        for entry in sorted(state_map.values(), key=lambda item: (item["channel"], item["lower_value"], item["upper_value"], item["bfi"])):
            writer.writerow(
                {
                    **entry,
                    "passes": ";".join(sorted(set(entry["passes"]))),
                    "details": " | ".join(entry["details"]),
                }
            )


def _resolve_channels(args_channels: list[str] | None) -> list[str]:
    if not args_channels or args_channels == ["ALL"]:
        return CHANNELS[:]
    resolved = [channel.upper() for channel in args_channels]
    for channel in resolved:
        if channel not in CHANNELS:
            raise ValueError(f"Unsupported channel: {channel}")
    return resolved


def _default_measurement_xy(lut_dir: Path) -> Path | None:
    candidate = lut_dir / "all_measurement_xy_points.csv"
    return candidate if candidate.exists() else None


def cmd_analyze(args: argparse.Namespace) -> int:
    resolved = resolve_output_paths(args, include_out_dir=False)
    channels = _resolve_channels(args.channels)
    capture_analysis = None
    if args.capture_dir:
        capture_analysis = analyze_raw_captures(
            capture_dir=Path(args.capture_dir),
            channels=channels,
            monotonic_tolerance_q16=args.monotonic_tolerance_q16,
            bfi_tolerance_q16=args.bfi_tolerance_q16,
            lower_floor_tolerance_q16=args.lower_floor_tolerance_q16,
            upper_residual_floor_q16=args.upper_residual_floor_q16,
            upper_residual_ratio=args.upper_residual_ratio,
        )

    capture_only_mode = capture_analysis is not None and (resolved.filtered_capture_out is not None or resolved.recapture_out is not None)
    if capture_only_mode:
        analysis = capture_analysis
    else:
        if not args.lut_dir:
            raise ValueError("--lut-dir is required for ladder analysis; omit ladder analysis outputs or provide --capture-dir with --filtered-capture-out/--recapture-out for raw-capture pruning.")
        measurement_xy = Path(args.measurement_xy) if args.measurement_xy else _default_measurement_xy(Path(args.lut_dir))
        analysis = analyze_ladders(
            lut_dir=Path(args.lut_dir),
            channels=channels,
            measurement_xy_path=measurement_xy,
            monotonic_tolerance_q16=args.monotonic_tolerance_q16,
            bfi_tolerance_q16=args.bfi_tolerance_q16,
            lower_floor_tolerance_q16=args.lower_floor_tolerance_q16,
            upper_residual_floor_q16=args.upper_residual_floor_q16,
            upper_residual_ratio=args.upper_residual_ratio,
            xy_drift_threshold=args.xy_drift_threshold,
            xy_spread_threshold=args.xy_spread_threshold,
            min_xy_samples=args.min_xy_samples,
        )
    _write_report(resolved.report_out, analysis, "analyze")
    capture_state_summaries = None
    if args.capture_dir:
        capture_state_summaries = summarize_capture_states(Path(args.capture_dir))
    if resolved.recapture_out is not None:
        write_blend8_recapture_plan(resolved.recapture_out, analysis, capture_state_summaries=capture_state_summaries, default_repeats=args.default_recapture_repeats)
    filter_stats = None
    if resolved.filtered_capture_out is not None and args.capture_dir:
        filter_stats = write_filtered_capture_csv(
            Path(args.capture_dir),
            resolved.filtered_capture_out,
            _capture_prune_state_keys(analysis.findings),
            chunk_rows=args.filtered_capture_chunk_rows,
        )
    for note in resolved.redirected:
        print(note)
    print(f"Spill/temp dir: {resolved.spill_dir}")
    if capture_only_mode:
        print(f"Analyzed {len(capture_state_summaries or {})} raw capture states.")
    else:
        print(f"Analyzed {sum(len(rows) for rows in analysis.rows_by_channel.values())} ladder rows.")
    print(f"Flagged {len(analysis.findings)} findings across {len(channels)} channel(s).")
    print(f"Report written to: {resolved.report_out}")
    if resolved.recapture_out is not None:
        print(f"Recapture plan written to: {resolved.recapture_out}")
    if filter_stats is not None:
        print(
            f"Filtered capture CSV chunks written: {filter_stats.chunk_files_written} files, "
            f"{filter_stats.rows_kept} kept rows, {filter_stats.rows_pruned} pruned rows."
        )
        if filter_stats.states_averaged > 0:
            print(f"Averaged {filter_stats.states_averaged} states from {filter_stats.rows_before_averaging} input rows.")
        print(f"Filtered capture chunk base: {resolved.filtered_capture_out}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    resolved = resolve_output_paths(args, include_out_dir=True)
    channels = _resolve_channels(args.channels)
    if not args.lut_dir:
        raise ValueError("--lut-dir is required for apply.")
    measurement_xy = Path(args.measurement_xy) if args.measurement_xy else _default_measurement_xy(Path(args.lut_dir))
    analysis = analyze_ladders(
        lut_dir=Path(args.lut_dir),
        channels=channels,
        measurement_xy_path=measurement_xy,
        monotonic_tolerance_q16=args.monotonic_tolerance_q16,
        bfi_tolerance_q16=args.bfi_tolerance_q16,
        lower_floor_tolerance_q16=args.lower_floor_tolerance_q16,
        upper_residual_floor_q16=args.upper_residual_floor_q16,
        upper_residual_ratio=args.upper_residual_ratio,
        xy_drift_threshold=args.xy_drift_threshold,
        xy_spread_threshold=args.xy_spread_threshold,
        min_xy_samples=args.min_xy_samples,
    )
    capture_analysis = None
    if args.capture_dir:
        capture_analysis = analyze_raw_captures(
            capture_dir=Path(args.capture_dir),
            channels=channels,
            monotonic_tolerance_q16=args.monotonic_tolerance_q16,
            bfi_tolerance_q16=args.bfi_tolerance_q16,
            lower_floor_tolerance_q16=args.lower_floor_tolerance_q16,
            upper_residual_floor_q16=args.upper_residual_floor_q16,
            upper_residual_ratio=args.upper_residual_ratio,
        )

    if args.action == "fix":
        _repair_flagged_rows(analysis.rows_by_channel)
        tuned_rows = analysis.rows_by_channel
    elif args.action == "prune":
        tuned_rows = _prune_flagged_rows(analysis.rows_by_channel)
    else:
        tuned_rows = analysis.rows_by_channel

    if resolved.out_dir is None:
        raise ValueError("Output directory is required for apply")
    for channel, rows in tuned_rows.items():
        _write_channel_ladder(resolved.out_dir, channel, rows)

    _write_report(resolved.report_out, analysis, args.action)
    capture_state_summaries = None
    if args.capture_dir:
        capture_state_summaries = summarize_capture_states(Path(args.capture_dir))
    if resolved.recapture_out is not None:
        write_blend8_recapture_plan(
            resolved.recapture_out,
            capture_analysis or analysis,
            capture_state_summaries=capture_state_summaries,
            default_repeats=args.default_recapture_repeats,
        )
    filter_stats = None
    if resolved.filtered_capture_out is not None and args.capture_dir:
        filter_stats = write_filtered_capture_csv(
            Path(args.capture_dir),
            resolved.filtered_capture_out,
            _capture_prune_state_keys((capture_analysis or analysis).findings),
            chunk_rows=args.filtered_capture_chunk_rows,
        )
    for note in resolved.redirected:
        print(note)
    print(f"Spill/temp dir: {resolved.spill_dir}")
    print(f"Applied '{args.action}' to {len(channels)} channel(s).")
    print(f"Output written to: {resolved.out_dir}")
    print(f"Report written to: {resolved.report_out}")
    if resolved.recapture_out is not None:
        print(f"Recapture plan written to: {resolved.recapture_out}")
    if filter_stats is not None:
        print(
            f"Filtered capture CSV chunks written: {filter_stats.chunk_files_written} files, "
            f"{filter_stats.rows_kept} kept rows, {filter_stats.rows_pruned} pruned rows."
        )
        if filter_stats.states_averaged > 0:
            print(f"Averaged {filter_stats.states_averaged} states from {filter_stats.rows_before_averaging} input rows.")
        print(f"Filtered capture chunk base: {resolved.filtered_capture_out}")
    return 0


def cmd_interpolate_captures(args: argparse.Namespace) -> int:
    capture_dir = Path(args.capture_dir)
    out_path = Path(args.interpolated_capture_out)
    _validate_interpolated_output_path(capture_dir, out_path)
    channels = _resolve_channels(args.channels)
    target_plan_rows = _build_dense_state_rows(channels, args.max_bfi)
    target_plan_paths = None
    if args.target_plan_dir or args.missing_plan:
        target_plan_paths = _resolve_target_plan_paths(args)
        target_plan_rows = None
    stats = write_interpolated_capture_csvs(
        capture_dir=capture_dir,
        out_path=out_path,
        chunk_rows=args.interpolated_capture_chunk_rows,
        input_globs=args.capture_input_globs,
        target_plan_rows=target_plan_rows,
        target_plan_paths=target_plan_paths,
    )
    print(f"Interpolated capture source dir: {capture_dir}")
    if target_plan_paths is not None:
        print(f"Target plan files: {len(target_plan_paths)}")
    else:
        print(f"Target dense channels: {', '.join(channels)} max_bfi={args.max_bfi}")
    print(f"Source files scanned: {stats.source_files_scanned}")
    print(f"Source rows loaded: {stats.source_rows_loaded}")
    print(f"Source states repaired: {stats.source_states_repaired}")
    print(f"Requested missing states: {stats.requested_states}")
    print(f"States interpolated: {stats.states_interpolated}")
    print(f"States already present: {stats.states_already_present}")
    print(f"States unresolved: {stats.states_unresolved}")
    print(f"States clamped to monotonic bounds: {stats.states_clamped}")
    print(f"Interpolated capture rows written: {stats.rows_written}")
    print(f"Interpolated capture chunks written: {stats.chunk_files_written}")
    print(f"Interpolated capture chunk base: {out_path}")
    if stats.unresolved_states:
        preview = ", ".join(str(state) for state in stats.unresolved_states[:5])
        print(f"Unresolved state preview: {preview}")
    return 0


def cmd_combine_captures(args: argparse.Namespace) -> int:
    pruned_capture_dir = Path(args.pruned_capture_dir)
    interpolated_capture_dir = Path(args.interpolated_capture_dir)
    out_path = Path(args.combined_capture_out)
    _validate_combined_output_path(pruned_capture_dir, interpolated_capture_dir, out_path)
    stats = write_combined_capture_csvs(
        pruned_capture_dir=pruned_capture_dir,
        interpolated_capture_dir=interpolated_capture_dir,
        out_path=out_path,
        chunk_rows=args.combined_capture_chunk_rows,
        pruned_globs=args.pruned_capture_globs,
        interpolated_globs=args.interpolated_capture_globs,
    )
    print(f"Pruned capture dir: {pruned_capture_dir}")
    print(f"Interpolated capture dir: {interpolated_capture_dir}")
    print(f"Source files scanned: {stats.source_files_scanned}")
    print(f"Rows seen: {stats.rows_seen}")
    print(f"States repaired to monotonic bounds: {stats.states_repaired}")
    print(f"Rows retuned from repaired states: {stats.rows_retuned}")
    print(f"Rows written: {stats.rows_written}")
    print(f"Combined capture chunks written: {stats.chunk_files_written}")
    print(f"Combined capture chunk base: {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze and repair temporal ladder outliers for v15 LUT outputs.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_common_arguments(target: argparse.ArgumentParser) -> None:
        target.add_argument("--lut-dir", help="Directory containing *_temporal_ladder.json/csv outputs")
        target.add_argument("--channels", nargs="*", default=["ALL"], help="Channels to process: R G B W or ALL")
        target.add_argument("--capture-dir", help="Directory containing raw plan_capture_*.csv files for filtered export and recapture planning")
        target.add_argument("--measurement-xy", help="Optional all_measurement_xy_points.csv path for drift checks")
        target.add_argument("--monotonic-tolerance-q16", type=int, default=8)
        target.add_argument("--bfi-tolerance-q16", type=int, default=8)
        target.add_argument("--lower-floor-tolerance-q16", type=int, default=8)
        target.add_argument("--upper-residual-floor-q16", type=int, default=96)
        target.add_argument("--upper-residual-ratio", type=float, default=0.015)
        target.add_argument("--xy-drift-threshold", type=float, default=0.010)
        target.add_argument("--xy-spread-threshold", type=float, default=0.0035)
        target.add_argument("--min-xy-samples", type=int, default=2)
        target.add_argument("--report-out", required=True)
        target.add_argument("--recapture-out", help="Host-GUI-compatible blend8 recapture plan CSV output path")
        target.add_argument("--filtered-capture-out", help="Base CSV output path for chunked filtered capture exports containing all original rows except flagged outlier states")
        target.add_argument("--filtered-capture-chunk-rows", type=int, default=100000, help="Maximum kept rows per filtered capture chunk CSV")
        target.add_argument("--default-recapture-repeats", type=int, default=4)
        target.add_argument("--spill-dir", default=str(DEFAULT_SPILL_DIR), help="Directory for temp/spill files and automatic output redirection when paths point at C:")

    analyze = sub.add_parser("analyze", help="Analyze ladders and emit an outlier report")
    add_common_arguments(analyze)
    analyze.set_defaults(func=cmd_analyze)

    apply = sub.add_parser("apply", help="Apply prune/fix actions to ladder outputs")
    add_common_arguments(apply)
    apply.add_argument("--action", choices=["report", "prune", "fix"], default="fix")
    apply.add_argument("--out-dir", required=True)
    apply.set_defaults(func=cmd_apply)

    interpolate = sub.add_parser("interpolate-captures", help="Interpolate missing capture states from pruned capture chunks")
    interpolate.add_argument("--capture-dir", required=True, help="Directory containing pruned plan_capture_outliers_pruned*.csv chunk files")
    interpolate.add_argument("--capture-input-globs", nargs="*", default=DEFAULT_PRUNED_CAPTURE_GLOBS, help="Glob patterns for source pruned capture chunks")
    interpolate.add_argument("--channels", nargs="*", default=["ALL"], help="Channels to synthesize in dense mode: R G B W or ALL")
    interpolate.add_argument("--max-bfi", type=int, default=4, help="Maximum BFI level to synthesize in dense mode")
    interpolate.add_argument("--missing-plan", help="Optional single target plan CSV. Pass the original plan_capture_advanced_*.csv to synthesize every state missing from the pruned captures; passing a recapture plan only synthesizes that smaller flagged subset")
    interpolate.add_argument("--target-plan-dir", help="Directory containing original capture-plan or capture-report CSVs to expand against as the desired full state set")
    interpolate.add_argument("--target-plan-globs", nargs="*", default=DEFAULT_TARGET_PLAN_GLOBS, help="Glob patterns used with --target-plan-dir to collect the full desired state set")
    interpolate.add_argument("--interpolated-capture-out", default=str(DEFAULT_INTERPOLATED_CAPTURE_DIR / "plan_capture_interpolated.csv"), help="Base CSV output path for chunked interpolated capture reports. Must be outside --capture-dir so synthetic data cannot mix with pruned measured captures")
    interpolate.add_argument("--interpolated-capture-chunk-rows", type=int, default=50000, help="Maximum interpolated capture rows per output chunk CSV")
    interpolate.set_defaults(func=cmd_interpolate_captures)

    combine = sub.add_parser("combine-captures", help="Combine pruned measured captures and interpolated captures into a sorted merged export")
    combine.add_argument("--pruned-capture-dir", required=True, help="Directory containing pruned measured capture CSV chunks")
    combine.add_argument("--pruned-capture-globs", nargs="*", default=DEFAULT_PRUNED_CAPTURE_GLOBS, help="Glob patterns for pruned measured capture CSV chunks")
    combine.add_argument("--interpolated-capture-dir", required=True, help="Directory containing interpolated capture CSV chunks")
    combine.add_argument("--interpolated-capture-globs", nargs="*", default=DEFAULT_INTERPOLATED_CAPTURE_GLOBS, help="Glob patterns for interpolated capture CSV chunks")
    combine.add_argument("--combined-capture-out", default=str(DEFAULT_COMBINED_CAPTURE_DIR / "plan_capture_combined.csv"), help="Base CSV output path for chunked combined capture exports. Must be outside both source directories")
    combine.add_argument("--combined-capture-chunk-rows", type=int, default=50000, help="Maximum rows per combined capture output chunk CSV")
    combine.set_defaults(func=cmd_combine_captures)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
