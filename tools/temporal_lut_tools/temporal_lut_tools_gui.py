#!/usr/bin/env python3
from __future__ import annotations
import csv, json, subprocess, sys, threading, re, math
from pathlib import Path
import random
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.image as mpimg
from matplotlib.patches import Rectangle

APP_TITLE = "Temporal LUT Tools GUI"
CHANNELS = ["R", "G", "B", "W"]
CONFIG_NAME = "temporal_lut_tools_gui_config.json"
TRANSFER_CURVE_OPTIONS = ["linear", "gamma", "pq", "hlg", "bt1886", "srgb-ish", "toe-gamma"]
PLAN_PRESET_OPTIONS = ["custom", "targeted-16bit"]
CIE_GAMUT_OVERLAYS = {
    "srgb": {
        "label": "sRGB / Rec.709",
        "color": "#ff6b6b",
        "points": ((0.640, 0.330), (0.300, 0.600), (0.150, 0.060)),
    },
    "adobe-rgb": {
        "label": "Adobe RGB",
        "color": "#ffb347",
        "points": ((0.640, 0.330), (0.210, 0.710), (0.150, 0.060)),
    },
    "display-p3": {
        "label": "Display P3",
        "color": "#5ec962",
        "points": ((0.680, 0.320), (0.265, 0.690), (0.150, 0.060)),
    },
    "bt2020": {
        "label": "BT.2020",
        "color": "#4dabf7",
        "points": ((0.708, 0.292), (0.170, 0.797), (0.131, 0.046)),
    },
}
CIE_WHITE_POINTS = {
    "d65": {"label": "D65", "color": "#ffffff", "edge": "#111111", "xy": (0.3127, 0.3290)},
    "d50": {"label": "D50", "color": "#ffe8a3", "edge": "#111111", "xy": (0.3457, 0.3585)},
    "dci": {"label": "DCI", "color": "#ffd166", "edge": "#111111", "xy": (0.3140, 0.3510)},
}

PATCH_PRESET_OPTIONS = ["quick", "balanced", "fine", "warm-guard", "neutral-focus", "super-fine", "ultra", "super-fine-plus", "ultra-plus"]
TRUE16_DENSITY_OPTIONS = ["quick", "medium", "fine", "ultra"]
TRUE16_AGGREGATE_OPTIONS = ["median", "mean", "trimmed"]
HIGH_RES_EXPORT_SIZE_OPTIONS = [0, 256, 512, 1024, 2048, 4096, 8192, 16384, 32767, 65535]
PROFILE_TARGET_OPTIONS = ["delta-preserving", "perceptual-density", "linear", "gamma", "legacy-measured"]
WHITE_POLICY_OPTIONS = ["disabled", "near-neutral", "always", "white-priority", "measured-optimal"]
MIXING_PROFILE_OPTIONS = ["legacy", "balanced", "warm-guard", "warm-guard-strong"]
MIXING_PROFILE_DEFAULTS = {
    "legacy": {"neutral_threshold_q16": 4096, "white_weight_q16": 65535, "rgb_weight_q16": 65535},
    "balanced": {"neutral_threshold_q16": 3072, "white_weight_q16": 57344, "rgb_weight_q16": 65535},
    "warm-guard": {"neutral_threshold_q16": 2304, "white_weight_q16": 49152, "rgb_weight_q16": 65535},
    "warm-guard-strong": {"neutral_threshold_q16": 1536, "white_weight_q16": 40960, "rgb_weight_q16": 65535},
}

SWATCH_PREVIEW_COLORS = [
    ("Amber", (255, 190, 64)),
    ("Warm Gold", (255, 215, 96)),
    ("Soft Orange", (255, 165, 92)),
    ("Skin Warm", (224, 176, 136)),
    ("Warm Gray", (176, 160, 144)),
    ("Neutral Gray", (176, 176, 176)),
    ("Cool Gray", (160, 170, 184)),
    ("Pale Yellow", (255, 244, 180)),
    ("Cyan", (96, 220, 255)),
    ("Magenta", (236, 132, 255)),
    ("Green", (128, 224, 120)),
    ("Deep Blue", (96, 128, 255)),
]

PREVIEW_LADDER_PLOT_MAX_POINTS = 12000
PREVIEW_MONOTONIC_PLOT_MAX_POINTS = 12000
PREVIEW_CIE_SAMPLE_MAX_POINTS = 800
PREVIEW_CAPTURE_SCAN_ROW_BATCH = 12000
PREVIEW_SINGLE_MEASURE_BATCH = 128
PREVIEW_PLOT_BATCH_POINTS = 10000
PREVIEW_CIE_PLOT_BATCH_POINTS = 8000


def parse_header_arrays(header_text: str):
    arrays = {}
    pat = re.compile(r"static const uint16_t (LUT_[A-Z](?:_BFI\d+)?_(?:8_TO_16|16_TO_16))\[(\d+)\] = \{(.*?)\};", re.S)
    for name, size_str, body in pat.findall(header_text):
        nums = [int(x) for x in re.findall(r"\d+", body)]
        expected = int(size_str)
        if len(nums) == expected:
            arrays[name] = nums
    return arrays


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1480x1040")
        self.script_dir = Path(__file__).resolve().parent
        self.tool_path = self.script_dir / "temporal_lut_tools.py"
        self.cie_bg_path = self.script_dir / "cie1931_reference.png"
        self.config_path = self.script_dir / CONFIG_NAME
        self.default_measure_dir = self.script_dir / "temporal_calibration_captures"
        self.default_calmeasure_dir = self.script_dir / "temporal_patch_captures"
        self.default_output_dir = self.script_dir / "temporal_lut_outputs"
        self.default_export_dir = self.script_dir / "temporal_solver_exports"
        self.project_root_dir = self.script_dir.parents[2] if len(self.script_dir.parents) >= 3 else self.script_dir
        self.default_firmware_solver_header = self.project_root_dir / "lib" / "TemporalBFI" / "src" / "temporal_runtime_solver_header.h"
        self.default_firmware_calibration_header = self.project_root_dir / "lib" / "TemporalBFI" / "src" / "calibration_profile_finenearneutral.h"

        cfg = self._load_config()
        self.plan_channel_var = tk.StringVar(value=cfg.get("plan_channel", "W"))
        self.plan_max_bfi_var = tk.IntVar(value=int(cfg.get("plan_max_bfi", 4)))
        self.plan_step_var = tk.IntVar(value=int(cfg.get("plan_step", 0)))
        self.plan_mode_var = tk.StringVar(value=cfg.get("plan_mode", "black-frame-insertion"))
        self.plan_floor_step_var = tk.IntVar(value=int(cfg.get("plan_floor_step", 0)))
        self.plan_preset_var = tk.StringVar(value=cfg.get("plan_preset", "custom"))
        self.plan_out_var = tk.StringVar(value=cfg.get("plan_out", str((self.script_dir / "measurement_plan_w.csv").resolve())))
        self.measure_dir_var = tk.StringVar(value=cfg.get("measure_dir", str(self.default_measure_dir.resolve())))
        self.build_out_dir_var = tk.StringVar(value=cfg.get("build_out_dir", str(self.default_output_dir.resolve())))
        self.export_out_var = tk.StringVar(value=cfg.get("export_out", str(self.default_export_dir.resolve())))
        self.solver_header_out_var = tk.StringVar(value=cfg.get("solver_header_out", str((self.default_export_dir / "temporal_runtime_solver_header.h").resolve())))
        self.precomputed_solver_source_header_var = tk.StringVar(
            value=cfg.get(
                "precomputed_solver_source_header",
                cfg.get("solver_header_out", str((self.default_export_dir / "temporal_runtime_solver_header.h").resolve())),
            )
        )
        self.precomputed_calibration_header_var = tk.StringVar(
            value=cfg.get(
                "precomputed_calibration_header",
                cfg.get("calibration_header_out", str(self.default_firmware_calibration_header.resolve())),
            )
        )
        self.precomputed_solver_out_var = tk.StringVar(
            value=cfg.get("precomputed_solver_out", str((self.default_export_dir / "solver_precomputed_luts.h").resolve()))
        )
        self.precomputed_solver_lut_size_var = tk.IntVar(value=int(cfg.get("precomputed_solver_lut_size", 0)))
        self.precomputed_solver_channels_var = tk.StringVar(value=cfg.get("precomputed_solver_channels", "rgbw"))
        self.summary_text = tk.StringVar(value="No LUT build run yet.")
        self.refresh_status_var = tk.StringVar(value="Preview idle.")
        self.refresh_progress_var = tk.DoubleVar(value=0.0)
        self.preview_channel_var = tk.StringVar(value=cfg.get("preview_channel", "W"))

        self.calmeasure_dir_var = tk.StringVar(value=cfg.get("calmeasure_dir", str(self.default_calmeasure_dir.resolve())))
        self.true16_calmeasure_dir_var = tk.StringVar(
            value=cfg.get("true16_calmeasure_dir", cfg.get("calmeasure_dir", str(self.default_calmeasure_dir.resolve())))
        )
        self.patch_preset_var = tk.StringVar(value=cfg.get("patch_preset", "balanced"))
        self.patch_max_bfi_var = tk.IntVar(value=int(cfg.get("patch_max_bfi", 4)))
        self.patch_plan_out_var = tk.StringVar(value=cfg.get("patch_plan_out", str((self.script_dir / "patch_plan.csv").resolve())))
        self.true16_density_var = tk.StringVar(value=cfg.get("true16_density", "fine"))
        self.true16_plan_repeats_var = tk.IntVar(value=int(cfg.get("true16_plan_repeats", 1)))
        self.true16_include_gray_var = tk.BooleanVar(value=bool(cfg.get("true16_include_gray", True)))
        self.true16_include_primary_var = tk.BooleanVar(value=bool(cfg.get("true16_include_primary", True)))
        self.true16_include_mid_var = tk.BooleanVar(value=bool(cfg.get("true16_include_mid", True)))
        self.true16_include_white_protection_var = tk.BooleanVar(value=bool(cfg.get("true16_include_white_protection", True)))
        self.true16_patch_plan_out_var = tk.StringVar(value=cfg.get("true16_patch_plan_out", str((self.script_dir / "patch_plan_true16.csv").resolve())))
        self.true16_header_out_var = tk.StringVar(value=cfg.get("true16_header_out", str((self.default_export_dir / "calibration_profile_true16.h").resolve())))
        self.true16_lut_size_var = tk.IntVar(value=int(cfg.get("true16_lut_size", 4096)))
        self.true16_aggregate_var = tk.StringVar(value=cfg.get("true16_aggregate", "median"))
        self.true16_trim_fraction_var = tk.DoubleVar(value=float(cfg.get("true16_trim_fraction", 0.1)))
        self.true16_outlier_sigma_var = tk.DoubleVar(value=float(cfg.get("true16_outlier_sigma", 3.5)))
        self.true16_enforce_monotonic_var = tk.BooleanVar(value=bool(cfg.get("true16_enforce_monotonic", True)))
        self.true16_inverse_regularization_var = tk.BooleanVar(value=bool(cfg.get("true16_inverse_regularization", True)))
        self.true16_inverse_max_step_q16_var = tk.StringVar(value=str(cfg.get("true16_inverse_max_step_q16", "")))
        self.true16_global_mixed_fit_var = tk.BooleanVar(value=bool(cfg.get("true16_global_mixed_fit", False)))
        self.true16_global_mixed_fit_max_iterations_var = tk.IntVar(value=int(cfg.get("true16_global_mixed_fit_max_iterations", 5)))
        self.true16_global_mixed_fit_peak_preserve_strength_var = tk.DoubleVar(value=float(cfg.get("true16_global_mixed_fit_peak_preserve_strength", 0.0)))
        self.true16_enable_mixed_patch_correction_var = tk.BooleanVar(value=bool(cfg.get("true16_enable_mixed_patch_correction", True)))
        self.true16_mixed_correction_strength_var = tk.DoubleVar(value=float(cfg.get("true16_mixed_correction_strength", 0.65)))
        self.true16_mixed_backbone_lock_strength_var = tk.DoubleVar(value=float(cfg.get("true16_mixed_backbone_lock_strength", 0.55)))
        self.true16_mixed_locality_width_var = tk.IntVar(value=int(cfg.get("true16_mixed_locality_width", 24)))
        self.true16_mixed_neutral_protection_strength_var = tk.DoubleVar(value=float(cfg.get("true16_mixed_neutral_protection_strength", 0.75)))
        self.true16_mixed_warm_priority_var = tk.DoubleVar(value=float(cfg.get("true16_mixed_warm_priority", 0.35)))
        self.true16_mixed_gamut_edge_restraint_var = tk.DoubleVar(value=float(cfg.get("true16_mixed_gamut_edge_restraint", 0.45)))
        self.true16_neutral_tolerance_q16_var = tk.IntVar(value=int(cfg.get("true16_neutral_tolerance_q16", 2048)))
        self.true16_input_globs_var = tk.StringVar(value=cfg.get("true16_input_globs", ""))
        self.true16_qa_report_out_var = tk.StringVar(value=cfg.get("true16_qa_report_out", str((self.default_export_dir / "calibration_profile_true16_report.json").resolve())))
        self.true16_use_transfer_curve_header_var = tk.BooleanVar(value=bool(cfg.get("true16_use_transfer_curve_header", False)))
        self.true16_transfer_curve_header_var = tk.StringVar(value=cfg.get("true16_transfer_curve_header", cfg.get("transfer_export_header", str((self.default_export_dir / "transfer_curve_preview.h").resolve()))))
        self.true16_controls_expanded_var = tk.BooleanVar(value=bool(cfg.get("true16_controls_expanded", False)))
        self.calibration_header_out_var = tk.StringVar(value=cfg.get("calibration_header_out", str((self.default_export_dir / "calibration_profile.h").resolve())))
        self.calibration_json_out_var = tk.StringVar(value=cfg.get("calibration_json_out", str((self.default_export_dir / "calibration_profile.json").resolve())))
        self.profile_source_bfi_var = tk.IntVar(value=int(cfg.get("profile_source_bfi", 0)))
        self.white_policy_var = tk.StringVar(value=cfg.get("white_policy", "near-neutral"))
        self.mixing_profile_var = tk.StringVar(value=cfg.get("mixing_profile", "balanced"))
        self.neutral_threshold_q16_var = tk.StringVar(value=str(cfg.get("neutral_threshold_q16", "")))
        self.white_weight_q16_var = tk.StringVar(value=str(cfg.get("white_weight_q16", "")))
        self.rgb_weight_q16_var = tk.StringVar(value=str(cfg.get("rgb_weight_q16", "")))
        self.white_channel_scale_var = tk.DoubleVar(value=float(cfg.get("white_channel_scale", 1.0)))
        self.white_channel_gamma_var = tk.DoubleVar(value=float(cfg.get("white_channel_gamma", 1.0)))
        self.auto_white_scale_var = tk.BooleanVar(value=bool(cfg.get("auto_white_scale", False)))
        self.auto_white_target_ratio_var = tk.DoubleVar(value=float(cfg.get("auto_white_target_ratio", 1.35)))
        self.auto_white_min_code_var = tk.IntVar(value=int(cfg.get("auto_white_min_code", 24)))
        self.profile_target_var = tk.StringVar(value=cfg.get("profile_target", "delta-preserving"))
        self.profile_target_gamma_var = tk.DoubleVar(value=float(cfg.get("profile_target_gamma", 1.0)))
        self.black_level_compensation_var = tk.BooleanVar(value=bool(cfg.get("black_level_compensation", True)))
        self.black_level_y_var = tk.StringVar(value=str(cfg.get("black_level_y", "")))

        self.transfer_curve_var = tk.StringVar(value=cfg.get("transfer_curve", "gamma"))
        self.transfer_gamma_var = tk.DoubleVar(value=float(cfg.get("transfer_gamma", 2.2)))
        self.transfer_shadow_lift_var = tk.DoubleVar(value=float(cfg.get("transfer_shadow_lift", 0.0)))
        self.transfer_shoulder_var = tk.DoubleVar(value=float(cfg.get("transfer_shoulder", 0.0)))
        self.transfer_bucket_count_var = tk.IntVar(value=int(cfg.get("transfer_bucket_count", 4096)))
        self.transfer_selection_var = tk.StringVar(value=cfg.get("transfer_selection", "floor"))
        self.transfer_peak_nits_override_var = tk.StringVar(value=str(cfg.get("transfer_peak_nits_override", "")))
        self.transfer_nit_cap_var = tk.StringVar(value=str(cfg.get("transfer_nit_cap", "")))
        self.transfer_exclude_white_var = tk.BooleanVar(value=bool(cfg.get("transfer_exclude_white", False)))
        self.transfer_per_channel_var = tk.BooleanVar(value=bool(cfg.get("transfer_per_channel", False)))
        self.transfer_channel_curve_vars = {
            ch: tk.StringVar(value=cfg.get(f"transfer_curve_{ch}", self.transfer_curve_var.get()))
            for ch in CHANNELS
        }
        self.transfer_channel_gamma_vars = {
            ch: tk.DoubleVar(value=float(cfg.get(f"transfer_gamma_{ch}", self.transfer_gamma_var.get())))
            for ch in CHANNELS
        }
        self.transfer_channel_shadow_lift_vars = {
            ch: tk.DoubleVar(value=float(cfg.get(f"transfer_shadow_lift_{ch}", self.transfer_shadow_lift_var.get())))
            for ch in CHANNELS
        }
        self.transfer_channel_shoulder_vars = {
            ch: tk.DoubleVar(value=float(cfg.get(f"transfer_shoulder_{ch}", self.transfer_shoulder_var.get())))
            for ch in CHANNELS
        }
        self.transfer_export_json_var = tk.StringVar(value=cfg.get("transfer_export_json", str((self.default_export_dir / "transfer_curve_preview.json").resolve())))
        self.transfer_export_header_var = tk.StringVar(value=cfg.get("transfer_export_header", str((self.default_export_dir / "transfer_curve_preview.h").resolve())))
        self.transfer_curve_note_var = tk.StringVar(value="")
        self.cie_overlay_vars = {
            key: tk.BooleanVar(value=bool(cfg.get(f"cie_overlay_{key}", key == "srgb")))
            for key in CIE_GAMUT_OVERLAYS
        }
        self.cie_show_white_points_var = tk.BooleanVar(value=bool(cfg.get("cie_show_white_points", True)))

        self.luma_method_var = tk.StringVar(value=cfg.get("luma_method", "average"))
        self.luma_bfi_source_var = tk.StringVar(value=cfg.get("luma_bfi_source", "all"))
        self.luma_export_json_var = tk.StringVar(value=cfg.get("luma_export_json", str((self.default_export_dir / "luma_weights.json").resolve())))
        self.luma_export_header_var = tk.StringVar(value=cfg.get("luma_export_header", str((self.default_export_dir / "luma_weights.h").resolve())))
        self.busy = False
        self._preview_refresh_token = 0
        self._preview_refresh_state = None
        self._preview_json_cache = {}
        self._preview_output_xy_cache = {}
        self._preview_capture_scan_cache = {}

        self.build_ui()
        self.transfer_curve_var.trace_add("write", self._update_transfer_curve_controls)
        self.transfer_per_channel_var.trace_add("write", self._update_transfer_curve_controls)
        for ch in CHANNELS:
            self.transfer_channel_curve_vars[ch].trace_add("write", self._update_transfer_curve_controls)
        self._update_transfer_curve_controls()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(120, self.refresh_calibration_visuals)

    def _load_config(self):
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_config(self):
        cfg = {
            "plan_channel": self.plan_channel_var.get(),
            "plan_max_bfi": self.plan_max_bfi_var.get(),
            "plan_step": self.plan_step_var.get(),
            "plan_mode": self.plan_mode_var.get(),
            "plan_floor_step": self.plan_floor_step_var.get(),
            "plan_preset": self.plan_preset_var.get(),
            "plan_out": self.plan_out_var.get(),
            "measure_dir": self.measure_dir_var.get(),
            "build_out_dir": self.build_out_dir_var.get(),
            "export_out": self.export_out_var.get(),
            "solver_header_out": self.solver_header_out_var.get(),
            "precomputed_solver_source_header": self.precomputed_solver_source_header_var.get(),
            "precomputed_calibration_header": self.precomputed_calibration_header_var.get(),
            "precomputed_solver_out": self.precomputed_solver_out_var.get(),
            "precomputed_solver_lut_size": self.precomputed_solver_lut_size_var.get(),
            "precomputed_solver_channels": self.precomputed_solver_channels_var.get(),
            "preview_channel": self.preview_channel_var.get(),
            "calmeasure_dir": self.calmeasure_dir_var.get(),
            "true16_calmeasure_dir": self.true16_calmeasure_dir_var.get(),
            "patch_preset": self.patch_preset_var.get(),
            "patch_max_bfi": self.patch_max_bfi_var.get(),
            "patch_plan_out": self.patch_plan_out_var.get(),
            "true16_density": self.true16_density_var.get(),
            "true16_plan_repeats": self.true16_plan_repeats_var.get(),
            "true16_include_gray": bool(self.true16_include_gray_var.get()),
            "true16_include_primary": bool(self.true16_include_primary_var.get()),
            "true16_include_mid": bool(self.true16_include_mid_var.get()),
            "true16_include_white_protection": bool(self.true16_include_white_protection_var.get()),
            "true16_patch_plan_out": self.true16_patch_plan_out_var.get(),
            "true16_header_out": self.true16_header_out_var.get(),
            "true16_lut_size": self.true16_lut_size_var.get(),
            "true16_aggregate": self.true16_aggregate_var.get(),
            "true16_trim_fraction": self.true16_trim_fraction_var.get(),
            "true16_outlier_sigma": self.true16_outlier_sigma_var.get(),
            "true16_enforce_monotonic": bool(self.true16_enforce_monotonic_var.get()),
            "true16_inverse_regularization": bool(self.true16_inverse_regularization_var.get()),
            "true16_inverse_max_step_q16": self.true16_inverse_max_step_q16_var.get(),
            "true16_global_mixed_fit": bool(self.true16_global_mixed_fit_var.get()),
            "true16_global_mixed_fit_max_iterations": self.true16_global_mixed_fit_max_iterations_var.get(),
            "true16_global_mixed_fit_peak_preserve_strength": self.true16_global_mixed_fit_peak_preserve_strength_var.get(),
            "true16_enable_mixed_patch_correction": bool(self.true16_enable_mixed_patch_correction_var.get()),
            "true16_mixed_correction_strength": self.true16_mixed_correction_strength_var.get(),
            "true16_mixed_backbone_lock_strength": self.true16_mixed_backbone_lock_strength_var.get(),
            "true16_mixed_locality_width": self.true16_mixed_locality_width_var.get(),
            "true16_mixed_neutral_protection_strength": self.true16_mixed_neutral_protection_strength_var.get(),
            "true16_mixed_warm_priority": self.true16_mixed_warm_priority_var.get(),
            "true16_mixed_gamut_edge_restraint": self.true16_mixed_gamut_edge_restraint_var.get(),
            "true16_neutral_tolerance_q16": self.true16_neutral_tolerance_q16_var.get(),
            "true16_input_globs": self.true16_input_globs_var.get(),
            "true16_qa_report_out": self.true16_qa_report_out_var.get(),
            "true16_use_transfer_curve_header": bool(self.true16_use_transfer_curve_header_var.get()),
            "true16_transfer_curve_header": self.true16_transfer_curve_header_var.get(),
            "true16_controls_expanded": bool(self.true16_controls_expanded_var.get()),
            "calibration_header_out": self.calibration_header_out_var.get(),
            "calibration_json_out": self.calibration_json_out_var.get(),
            "profile_source_bfi": self.profile_source_bfi_var.get(),
            "white_policy": self.white_policy_var.get(),
            "mixing_profile": self.mixing_profile_var.get(),
            "neutral_threshold_q16": self.neutral_threshold_q16_var.get(),
            "white_weight_q16": self.white_weight_q16_var.get(),
            "rgb_weight_q16": self.rgb_weight_q16_var.get(),
            "white_channel_scale": self.white_channel_scale_var.get(),
            "white_channel_gamma": self.white_channel_gamma_var.get(),
            "auto_white_scale": bool(self.auto_white_scale_var.get()),
            "auto_white_target_ratio": self.auto_white_target_ratio_var.get(),
            "auto_white_min_code": self.auto_white_min_code_var.get(),
            "profile_target": self.profile_target_var.get(),
            "profile_target_gamma": self.profile_target_gamma_var.get(),
            "black_level_compensation": bool(self.black_level_compensation_var.get()),
            "black_level_y": self.black_level_y_var.get(),

            "transfer_curve": self.transfer_curve_var.get(),
            "transfer_gamma": self.transfer_gamma_var.get(),
            "transfer_shadow_lift": self.transfer_shadow_lift_var.get(),
            "transfer_shoulder": self.transfer_shoulder_var.get(),
            "transfer_bucket_count": self.transfer_bucket_count_var.get(),
            "transfer_selection": self.transfer_selection_var.get(),
            "transfer_peak_nits_override": self.transfer_peak_nits_override_var.get(),
            "transfer_nit_cap": self.transfer_nit_cap_var.get(),
            "transfer_exclude_white": bool(self.transfer_exclude_white_var.get()),
            "transfer_per_channel": bool(self.transfer_per_channel_var.get()),
            "transfer_export_json": self.transfer_export_json_var.get(),
            "transfer_export_header": self.transfer_export_header_var.get(),
            "luma_method": self.luma_method_var.get(),
            "luma_bfi_source": self.luma_bfi_source_var.get(),
            "luma_export_json": self.luma_export_json_var.get(),
            "luma_export_header": self.luma_export_header_var.get(),
        }
        for key, var in self.cie_overlay_vars.items():
            cfg[f"cie_overlay_{key}"] = bool(var.get())
        cfg["cie_show_white_points"] = bool(self.cie_show_white_points_var.get())
        for ch in CHANNELS:
            cfg[f"transfer_curve_{ch}"] = self.transfer_channel_curve_vars[ch].get()
            cfg[f"transfer_gamma_{ch}"] = self.transfer_channel_gamma_vars[ch].get()
            cfg[f"transfer_shadow_lift_{ch}"] = self.transfer_channel_shadow_lift_vars[ch].get()
            cfg[f"transfer_shoulder_{ch}"] = self.transfer_channel_shoulder_vars[ch].get()
        self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def on_close(self):
        self._save_config()
        self.root.destroy()

    def build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="Temporal LUT Tools", font=("", 16, "bold")).pack(anchor="w", pady=(0, 10))
        refresh_status = ttk.Frame(main)
        refresh_status.pack(fill="x", pady=(0, 10))
        ttk.Label(refresh_status, text="Preview refresh").pack(side="left")
        ttk.Label(refresh_status, textvariable=self.refresh_status_var).pack(side="left", padx=(10, 12))
        ttk.Progressbar(refresh_status, variable=self.refresh_progress_var, maximum=100.0).pack(side="left", fill="x", expand=True)
        tabs = ttk.Notebook(main)
        tabs.pack(fill="both", expand=True)
        tool_tab = ttk.Frame(tabs)
        cal_tab = ttk.Frame(tabs)
        viz_tab = ttk.Frame(tabs)
        tabs.add(tool_tab, text="Tool Section")
        tabs.add(cal_tab, text="Calibration Section")
        tabs.add(viz_tab, text="Visualization")
        self._build_plan_frame(tool_tab)
        self._build_build_frame(tool_tab)
        self._build_export_frame(tool_tab)
        self._build_patch_calibration_frame(cal_tab)
        self._build_log_frame(tool_tab)
        self._build_visualization_frame(viz_tab)

    def _build_plan_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="1) Generate Measurement Plan")
        frame.pack(fill="x", pady=(0, 12))
        row1 = ttk.Frame(frame); row1.pack(fill="x", padx=8, pady=8)
        ttk.Label(row1, text="Channel").pack(side="left")
        ttk.Combobox(row1, textvariable=self.plan_channel_var, values=CHANNELS + ["ALL"], state="readonly", width=6).pack(side="left", padx=(6,16))
        ttk.Label(row1, text="Mode").pack(side="left")
        ttk.Combobox(row1, textvariable=self.plan_mode_var, values=["black-frame-insertion", "temporal-blend"], state="readonly", width=16).pack(side="left", padx=(6,16))
        ttk.Label(row1, text="Max BFI").pack(side="left")
        ttk.Spinbox(row1, from_=0, to=8, textvariable=self.plan_max_bfi_var, width=6).pack(side="left", padx=(6,16))
        ttk.Label(row1, text="Preset").pack(side="left")
        ttk.Combobox(row1, textvariable=self.plan_preset_var, values=PLAN_PRESET_OPTIONS, state="readonly", width=16).pack(side="left", padx=(6,16))
        ttk.Label(row1, text="Upper step").pack(side="left")
        ttk.Spinbox(row1, from_=0, to=64, textvariable=self.plan_step_var, width=6).pack(side="left", padx=(6,16))
        ttk.Label(row1, text="Floor step").pack(side="left")
        ttk.Spinbox(row1, from_=0, to=64, textvariable=self.plan_floor_step_var, width=6).pack(side="left", padx=(6,16))
        ttk.Button(row1, text="Default filename", command=self.set_default_plan_filename).pack(side="left")
        row2 = ttk.Frame(frame); row2.pack(fill="x", padx=8, pady=(0,8))
        ttk.Label(row2, text="Plan CSV").pack(side="left")
        ttk.Entry(row2, textvariable=self.plan_out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row2, text="Browse...", command=self.choose_plan_out).pack(side="left")
        row3 = ttk.Frame(frame); row3.pack(fill="x", padx=8, pady=(0,8))
        ttk.Button(row3, text="Generate Plan CSV", command=self.generate_plan).pack(side="left")
        ttk.Label(row3, text="Preset custom uses the step controls. targeted-16bit targets about 190k total captures for ALL, keeps a full floor-0 sweep, and halves dark repeats.").pack(side="left", padx=10)

    def _build_build_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="2) Build LUTs From Captures")
        frame.pack(fill="x", pady=(0,12))
        row1 = ttk.Frame(frame); row1.pack(fill="x", padx=8, pady=8)
        ttk.Label(row1, text="Measurement dir").pack(side="left")
        ttk.Entry(row1, textvariable=self.measure_dir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row1, text="Browse...", command=self.choose_measure_dir).pack(side="left")
        
        row2 = ttk.Frame(frame); row2.pack(fill="x", padx=8, pady=(0,8))
        ttk.Label(row2, text="LUT output dir").pack(side="left")
        ttk.Entry(row2, textvariable=self.build_out_dir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row2, text="Browse...", command=self.choose_build_out_dir).pack(side="left")
        
        row3 = ttk.Frame(frame); row3.pack(fill="x", padx=8, pady=(0,8))
        ttk.Button(row3, text="Build LUTs", command=self.build_luts).pack(side="left")
        ttk.Button(row3, text="Load summary", command=self.load_summary).pack(side="left", padx=8)
        ttk.Button(row3, text="Open output folder", command=self.open_output_folder).pack(side="left", padx=8)
        ttk.Label(row3, textvariable=self.summary_text).pack(side="left", padx=10)

    def _build_export_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="3) Export Runtime / Solver Data")
        frame.pack(fill="x", pady=(0,12))
        row1 = ttk.Frame(frame); row1.pack(fill="x", padx=8, pady=8)
        ttk.Label(row1, text="Export dir").pack(side="left")
        ttk.Entry(row1, textvariable=self.export_out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row1, text="Browse...", command=self.choose_export_out_dir).pack(side="left")
        row2 = ttk.Frame(frame); row2.pack(fill="x", padx=8, pady=(0,8))
        ttk.Button(row2, text="Export runtime JSON", command=self.export_runtime_json).pack(side="left")
        ttk.Button(row2, text="Export runtime C header", command=self.export_runtime_header).pack(side="left", padx=8)
        row3 = ttk.Frame(frame); row3.pack(fill="x", padx=8, pady=(0,8))
        ttk.Label(row3, text="Solver header").pack(side="left")
        ttk.Entry(row3, textvariable=self.solver_header_out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row3, text="Browse...", command=self.choose_solver_header_out).pack(side="left")
        ttk.Button(row3, text="Export solver header", command=self.export_solver_header).pack(side="left", padx=8)

        row3b = ttk.Frame(frame); row3b.pack(fill="x", padx=8, pady=(0,8))
        ttk.Label(row3b, text="Solver source header").pack(side="left")
        ttk.Entry(row3b, textvariable=self.precomputed_solver_source_header_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row3b, text="Browse...", command=self.choose_precomputed_solver_source_header).pack(side="left")

        row3c = ttk.Frame(frame); row3c.pack(fill="x", padx=8, pady=(0,8))
        ttk.Label(row3c, text="Calibration header").pack(side="left")
        ttk.Entry(row3c, textvariable=self.precomputed_calibration_header_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row3c, text="Browse...", command=self.choose_precomputed_calibration_header).pack(side="left")

        row3d = ttk.Frame(frame); row3d.pack(fill="x", padx=8, pady=(0,8))
        ttk.Label(row3d, text="Solver LUT size (0=auto)").pack(side="left")
        ttk.Combobox(row3d, textvariable=self.precomputed_solver_lut_size_var, values=HIGH_RES_EXPORT_SIZE_OPTIONS, state="readonly", width=8).pack(side="left", padx=6)
        ttk.Label(row3d, text="Derived mode follows solver ladder counts.").pack(side="left", padx=(12, 0))
        ttk.Label(row3d, text="Channels").pack(side="left", padx=(16, 0))
        ttk.Combobox(row3d, textvariable=self.precomputed_solver_channels_var, values=["rgbw", "rgb", "G", "R", "B", "W"], state="readonly", width=6).pack(side="left", padx=6)

        row3e = ttk.Frame(frame); row3e.pack(fill="x", padx=8, pady=(0,8))
        ttk.Label(row3e, text="Precomputed solver LUT header").pack(side="left")
        ttk.Entry(row3e, textvariable=self.precomputed_solver_out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row3e, text="Browse...", command=self.choose_precomputed_solver_out).pack(side="left")
        ttk.Button(row3e, text="Export precomputed solver LUTs", command=self.export_precomputed_solver_luts_header).pack(side="left", padx=8)

        row4 = ttk.Frame(frame); row4.pack(fill="x", padx=8, pady=(0,8))
        ttk.Label(row4, text="Transfer JSON").pack(side="left")
        ttk.Entry(row4, textvariable=self.transfer_export_json_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row4, text="Browse...", command=self.choose_transfer_json_out).pack(side="left")
        ttk.Button(row4, text="Export transfer JSON", command=self.export_transfer_json).pack(side="left", padx=8)
        row5 = ttk.Frame(frame); row5.pack(fill="x", padx=8, pady=(0,8))
        ttk.Label(row5, text="Transfer header").pack(side="left")
        ttk.Entry(row5, textvariable=self.transfer_export_header_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row5, text="Browse...", command=self.choose_transfer_header_out).pack(side="left")
        ttk.Button(row5, text="Export transfer header", command=self.export_transfer_header).pack(side="left", padx=8)

        row6 = ttk.Frame(frame); row6.pack(fill="x", padx=8, pady=(0,8))
        ttk.Label(row6, text="Luma method").pack(side="left")
        ttk.Combobox(row6, textvariable=self.luma_method_var, values=["average","max","median"], state="readonly", width=10).pack(side="left", padx=6)
        ttk.Label(row6, text="BFI source").pack(side="left")
        ttk.Combobox(row6, textvariable=self.luma_bfi_source_var, values=["all",0,1,2,3,4,5,6,7,8], state="readonly", width=8).pack(side="left", padx=6)
        ttk.Label(row6, text="Luma JSON").pack(side="left", padx=(12,0))
        ttk.Entry(row6, textvariable=self.luma_export_json_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row6, text="Browse...", command=self.choose_luma_json_out).pack(side="left")
        ttk.Button(row6, text="Export luma JSON", command=self.export_luma_weights_json).pack(side="left", padx=8)
        row7 = ttk.Frame(frame); row7.pack(fill="x", padx=8, pady=(0,8))
        ttk.Label(row7, text="Luma header").pack(side="left")
        ttk.Entry(row7, textvariable=self.luma_export_header_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row7, text="Browse...", command=self.choose_luma_header_out).pack(side="left")
        ttk.Button(row7, text="Export luma header", command=self.export_luma_weights_header).pack(side="left", padx=8)

    def _build_patch_calibration_frame(self, parent):
        # --- Deprecation banner ---------------------------------------------------
        banner = ttk.Frame(parent)
        banner.pack(fill="x", pady=(4, 0))
        banner_label = tk.Label(
            banner,
            text=(
                "\u26A0  rgbw_lut_builder is now the preferred tool for calibration header exports.  "
                "This tab will eventually be removed from this GUI."
            ),
            bg="#fff3cd", fg="#856404", font=("Segoe UI", 10, "bold"),
            anchor="w", padx=10, pady=6,
        )
        banner_label.pack(fill="x", padx=8)
        # --------------------------------------------------------------------------

        source_frame = ttk.LabelFrame(parent, text="Calibration Capture Source")
        source_frame.pack(fill="x", pady=(0, 10))
        source_row = ttk.Frame(source_frame)
        source_row.pack(fill="x", padx=8, pady=8)
        ttk.Label(source_row, text="Patch capture dir").pack(side="left")
        ttk.Entry(source_row, textvariable=self.calmeasure_dir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(source_row, text="Browse...", command=self.choose_calmeasure_dir).pack(side="left")

        source_row_true16 = ttk.Frame(source_frame)
        source_row_true16.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(source_row_true16, text="True16 capture dir").pack(side="left")
        ttk.Entry(source_row_true16, textvariable=self.true16_calmeasure_dir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(source_row_true16, text="Browse...", command=self.choose_true16_calmeasure_dir).pack(side="left")

        body = ttk.PanedWindow(parent, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(0, 12))

        controls = ttk.LabelFrame(body, text="Patch Calibration Controls")
        preview = ttk.LabelFrame(body, text="How It Will Look")
        body.add(controls, weight=3)
        body.add(preview, weight=5)

        row1 = ttk.Frame(controls); row1.pack(fill="x", padx=8, pady=8)
        ttk.Label(row1, text="Preset").pack(side="left")
        ttk.Combobox(row1, textvariable=self.patch_preset_var, values=PATCH_PRESET_OPTIONS, state="readonly", width=14).pack(side="left", padx=6)
        ttk.Label(row1, text="Max BFI").pack(side="left", padx=(12, 0))
        ttk.Spinbox(row1, from_=0, to=8, textvariable=self.patch_max_bfi_var, width=6).pack(side="left", padx=6)
        ttk.Label(row1, text="Patch plan CSV").pack(side="left", padx=(12, 0))
        ttk.Entry(row1, textvariable=self.patch_plan_out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row1, text="Browse...", command=self.choose_patch_plan_out).pack(side="left")
        ttk.Button(row1, text="Generate patch plan", command=self.generate_patch_plan).pack(side="left", padx=8)

        row1b_toggle = ttk.Frame(controls); row1b_toggle.pack(fill="x", padx=8, pady=(0, 8))
        self.true16_toggle_button = ttk.Button(row1b_toggle, text="", command=self.toggle_true16_controls, width=22)
        self.true16_toggle_button.pack(side="left")
        ttk.Label(row1b_toggle, text="Collapse this section when True16 capture/export is not in use.").pack(side="left", padx=(12, 0))

        self.true16_controls_container = ttk.Frame(controls)

        row1b = ttk.Frame(self.true16_controls_container); row1b.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(row1b, text="True16 density").pack(side="left")
        ttk.Combobox(row1b, textvariable=self.true16_density_var, values=TRUE16_DENSITY_OPTIONS, state="readonly", width=10).pack(side="left", padx=6)
        ttk.Label(row1b, text="Repeats").pack(side="left", padx=(12, 0))
        ttk.Spinbox(row1b, from_=1, to=32, textvariable=self.true16_plan_repeats_var, width=6).pack(side="left", padx=6)
        ttk.Checkbutton(row1b, text="Gray ramp", variable=self.true16_include_gray_var).pack(side="left", padx=(12, 0))
        ttk.Checkbutton(row1b, text="Primary ramps", variable=self.true16_include_primary_var).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(row1b, text="Mid colors", variable=self.true16_include_mid_var).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(row1b, text="White-protection mixes", variable=self.true16_include_white_protection_var).pack(side="left", padx=(8, 0))
        ttk.Label(row1b, text="True16 plan CSV").pack(side="left", padx=(12, 0))
        ttk.Entry(row1b, textvariable=self.true16_patch_plan_out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row1b, text="Browse...", command=self.choose_true16_patch_plan_out).pack(side="left")
        ttk.Button(row1b, text="Generate True16 plan", command=self.generate_patch_plan_true16).pack(side="left", padx=8)

        row3b = ttk.Frame(self.true16_controls_container); row3b.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(row3b, text="True16 header").pack(side="left")
        ttk.Entry(row3b, textvariable=self.true16_header_out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row3b, text="Browse...", command=self.choose_true16_header_out).pack(side="left")
        ttk.Label(row3b, text="LUT size (0=auto)").pack(side="left", padx=(12, 0))
        ttk.Combobox(row3b, textvariable=self.true16_lut_size_var, values=HIGH_RES_EXPORT_SIZE_OPTIONS, state="readonly", width=8).pack(side="left", padx=6)
        ttk.Button(row3b, text="Export True16 header", command=self.export_calibration_true16_header).pack(side="left", padx=8)

        row3c = ttk.Frame(self.true16_controls_container); row3c.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(row3c, text="Aggregate").pack(side="left")
        ttk.Combobox(row3c, textvariable=self.true16_aggregate_var, values=TRUE16_AGGREGATE_OPTIONS, state="readonly", width=10).pack(side="left", padx=6)
        ttk.Label(row3c, text="Trim fraction").pack(side="left", padx=(12, 0))
        ttk.Entry(row3c, textvariable=self.true16_trim_fraction_var, width=8).pack(side="left", padx=6)
        ttk.Label(row3c, text="Outlier sigma").pack(side="left", padx=(12, 0))
        ttk.Entry(row3c, textvariable=self.true16_outlier_sigma_var, width=8).pack(side="left", padx=6)
        ttk.Checkbutton(row3c, text="Enforce monotonic", variable=self.true16_enforce_monotonic_var).pack(side="left", padx=(12, 0))

        row3d = ttk.Frame(self.true16_controls_container); row3d.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Checkbutton(row3d, text="Inverse regularization", variable=self.true16_inverse_regularization_var).pack(side="left")
        ttk.Label(row3d, text="Inverse max step Q16").pack(side="left", padx=(12, 0))
        ttk.Entry(row3d, textvariable=self.true16_inverse_max_step_q16_var, width=8).pack(side="left", padx=6)
        ttk.Checkbutton(row3d, text="Global mixed fit", variable=self.true16_global_mixed_fit_var).pack(side="left", padx=(12, 0))
        ttk.Label(row3d, text="Fit iterations").pack(side="left", padx=(12, 0))
        ttk.Spinbox(row3d, from_=1, to=32, textvariable=self.true16_global_mixed_fit_max_iterations_var, width=6).pack(side="left", padx=6)
        ttk.Label(row3d, text="Peak preserve").pack(side="left", padx=(12, 0))
        ttk.Entry(row3d, textvariable=self.true16_global_mixed_fit_peak_preserve_strength_var, width=8).pack(side="left", padx=6)

        row3e = ttk.Frame(self.true16_controls_container); row3e.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Checkbutton(row3e, text="Mixed patch correction", variable=self.true16_enable_mixed_patch_correction_var).pack(side="left")
        ttk.Label(row3e, text="Strength").pack(side="left", padx=(12, 0))
        ttk.Entry(row3e, textvariable=self.true16_mixed_correction_strength_var, width=6).pack(side="left", padx=6)
        ttk.Label(row3e, text="Backbone lock").pack(side="left", padx=(12, 0))
        ttk.Entry(row3e, textvariable=self.true16_mixed_backbone_lock_strength_var, width=6).pack(side="left", padx=6)
        ttk.Label(row3e, text="Locality").pack(side="left", padx=(12, 0))
        ttk.Entry(row3e, textvariable=self.true16_mixed_locality_width_var, width=6).pack(side="left", padx=6)
        ttk.Label(row3e, text="Neutral protect").pack(side="left", padx=(12, 0))
        ttk.Entry(row3e, textvariable=self.true16_mixed_neutral_protection_strength_var, width=6).pack(side="left", padx=6)
        ttk.Label(row3e, text="Warm priority").pack(side="left", padx=(12, 0))
        ttk.Entry(row3e, textvariable=self.true16_mixed_warm_priority_var, width=6).pack(side="left", padx=6)
        ttk.Label(row3e, text="Edge restraint").pack(side="left", padx=(12, 0))
        ttk.Entry(row3e, textvariable=self.true16_mixed_gamut_edge_restraint_var, width=6).pack(side="left", padx=6)

        row3ea = ttk.Frame(self.true16_controls_container); row3ea.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(row3ea, text="Neutral tol Q16").pack(side="left")
        ttk.Entry(row3ea, textvariable=self.true16_neutral_tolerance_q16_var, width=8).pack(side="left", padx=6)
        ttk.Label(row3ea, text="Input globs").pack(side="left", padx=(12, 0))
        ttk.Entry(row3ea, textvariable=self.true16_input_globs_var).pack(side="left", fill="x", expand=True, padx=6)

        row3f = ttk.Frame(self.true16_controls_container); row3f.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(row3f, text="QA report JSON").pack(side="left")
        ttk.Entry(row3f, textvariable=self.true16_qa_report_out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row3f, text="Browse...", command=self.choose_true16_qa_report_out).pack(side="left")
        ttk.Button(row3f, text="Analyze True16", command=self.analyze_calibration_true16).pack(side="left", padx=8)

        row3g = ttk.Frame(self.true16_controls_container); row3g.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Checkbutton(row3g, text="Use transfer header for post-curve QA", variable=self.true16_use_transfer_curve_header_var).pack(side="left")
        ttk.Entry(row3g, textvariable=self.true16_transfer_curve_header_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row3g, text="Browse...", command=self.choose_true16_transfer_curve_header).pack(side="left")

        row3h = ttk.Frame(self.true16_controls_container); row3h.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(
            row3h,
            text="True16 input globs accept comma/semicolon/newline; leave empty for built-in defaults. Peak preserve 0.0 keeps the current recommended baseline; mixed-patch correction controls now tune the main True16 correction pass directly. QA JSON/HTML reports are automatically coupled to the True16 header output directory. Enable a transfer header when you want post-curve runtime QA in the reports.",
        ).pack(side="left")

        self._set_true16_controls_visible(bool(self.true16_controls_expanded_var.get()))

        row4 = ttk.Frame(controls); row4.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(row4, text="Profile source BFI").pack(side="left")
        ttk.Spinbox(row4, from_=0, to=8, textvariable=self.profile_source_bfi_var, width=6).pack(side="left", padx=6)
        ttk.Label(row4, text="White policy").pack(side="left", padx=(12, 0))
        ttk.Combobox(row4, textvariable=self.white_policy_var, values=WHITE_POLICY_OPTIONS, state="readonly", width=18).pack(side="left", padx=6)
        ttk.Label(row4, text="Mixing profile").pack(side="left", padx=(12, 0))
        ttk.Combobox(row4, textvariable=self.mixing_profile_var, values=MIXING_PROFILE_OPTIONS, state="readonly", width=16).pack(side="left", padx=6)

        row5 = ttk.Frame(controls); row5.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(row5, text="Neutral threshold Q16").pack(side="left")
        ttk.Entry(row5, textvariable=self.neutral_threshold_q16_var, width=10).pack(side="left", padx=6)
        ttk.Label(row5, text="White weight Q16").pack(side="left", padx=(12, 0))
        ttk.Entry(row5, textvariable=self.white_weight_q16_var, width=10).pack(side="left", padx=6)
        ttk.Label(row5, text="RGB weight Q16").pack(side="left", padx=(12, 0))
        ttk.Entry(row5, textvariable=self.rgb_weight_q16_var, width=10).pack(side="left", padx=6)
        ttk.Label(row5, text="(leave blank for mixing-profile defaults)").pack(side="left", padx=(12, 0))

        row5b = ttk.Frame(controls); row5b.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(row5b, text="Calibration target").pack(side="left")
        ttk.Combobox(row5b, textvariable=self.profile_target_var, values=PROFILE_TARGET_OPTIONS, state="readonly", width=16).pack(side="left", padx=6)
        ttk.Label(row5b, text="Target gamma").pack(side="left", padx=(12, 0))
        ttk.Entry(row5b, textvariable=self.profile_target_gamma_var, width=8).pack(side="left", padx=6)
        ttk.Checkbutton(row5b, text="Black-level compensation", variable=self.black_level_compensation_var).pack(side="left", padx=(12, 0))
        ttk.Label(row5b, text="Black Y override").pack(side="left", padx=(12, 0))
        ttk.Entry(row5b, textvariable=self.black_level_y_var, width=10).pack(side="left", padx=6)

        row6 = ttk.Frame(controls); row6.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(row6, text="White scale").pack(side="left")
        ttk.Entry(row6, textvariable=self.white_channel_scale_var, width=8).pack(side="left", padx=6)
        ttk.Label(row6, text="White gamma").pack(side="left", padx=(12, 0))
        ttk.Entry(row6, textvariable=self.white_channel_gamma_var, width=8).pack(side="left", padx=6)
        ttk.Checkbutton(row6, text="Auto white scale", variable=self.auto_white_scale_var).pack(side="left", padx=(12, 0))
        ttk.Label(row6, text="Target ratio").pack(side="left", padx=(10, 0))
        ttk.Entry(row6, textvariable=self.auto_white_target_ratio_var, width=8).pack(side="left", padx=6)
        ttk.Label(row6, text="Min code").pack(side="left", padx=(10, 0))
        ttk.Entry(row6, textvariable=self.auto_white_min_code_var, width=6).pack(side="left", padx=6)
        ttk.Button(row6, text="Refresh visuals", command=self.refresh_calibration_visuals).pack(side="left", padx=(12, 0))

        preview_tabs = ttk.Notebook(preview)
        preview_tabs.pack(fill="both", expand=True, padx=8, pady=8)

        mix_tab = ttk.Frame(preview_tabs)
        swatch_tab = ttk.Frame(preview_tabs)
        lut_tab = ttk.Frame(preview_tabs)
        notes_tab = ttk.Frame(preview_tabs)
        preview_tabs.add(mix_tab, text="Warm/White Preview")
        preview_tabs.add(swatch_tab, text="Swatch Strip")
        preview_tabs.add(lut_tab, text="White LUT Shape")
        preview_tabs.add(notes_tab, text="Calibration Notes")

        self.figure_calmix = Figure(figsize=(7, 6), dpi=100)
        self.ax_calmix_top = self.figure_calmix.add_subplot(211)
        self.ax_calmix_bottom = self.figure_calmix.add_subplot(212)
        self.canvas_calmix = FigureCanvasTkAgg(self.figure_calmix, master=mix_tab)
        self.canvas_calmix.get_tk_widget().pack(fill="both", expand=True)

        self.figure_calshape = Figure(figsize=(7, 5), dpi=100)
        self.ax_calshape = self.figure_calshape.add_subplot(111)
        self.canvas_calshape = FigureCanvasTkAgg(self.figure_calshape, master=lut_tab)
        self.canvas_calshape.get_tk_widget().pack(fill="both", expand=True)

        self.figure_swatch = Figure(figsize=(7, 3.6), dpi=100)
        self.ax_swatch = self.figure_swatch.add_subplot(111)
        self.canvas_swatch = FigureCanvasTkAgg(self.figure_swatch, master=swatch_tab)
        self.canvas_swatch.get_tk_widget().pack(fill="both", expand=True)

        self.cal_preview_text = tk.Text(notes_tab, wrap="word")
        self.cal_preview_text.pack(fill="both", expand=True)

    def _parse_optional_int(self, value):
        s = str(value).strip()
        if not s:
            return None
        try:
            return int(s)
        except Exception:
            return None

    def _parse_optional_float(self, value):
        s = str(value).strip()
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    def _clamp_u16(self, value):
        return max(0, min(65535, int(value)))

    def _safe_float(self, variable, default):
        try:
            return float(variable.get())
        except Exception:
            return float(default)

    def _safe_int(self, variable, default):
        try:
            return int(variable.get())
        except Exception:
            return int(default)

    def toggle_true16_controls(self):
        self._set_true16_controls_visible(not bool(self.true16_controls_expanded_var.get()))

    def _set_true16_controls_visible(self, expanded):
        expanded = bool(expanded)
        self.true16_controls_expanded_var.set(expanded)

        if not hasattr(self, "true16_controls_container") or not hasattr(self, "true16_toggle_button"):
            return

        if expanded:
            if not self.true16_controls_container.winfo_manager():
                self.true16_controls_container.pack(fill="x", padx=0, pady=(0, 8))
            self.true16_toggle_button.configure(text="Hide True16 Controls")
        else:
            if self.true16_controls_container.winfo_manager():
                self.true16_controls_container.pack_forget()
            self.true16_toggle_button.configure(text="Show True16 Controls")

    def _collect_calibration_ui_settings(self):
        profile = self.mixing_profile_var.get()
        defaults = MIXING_PROFILE_DEFAULTS.get(profile, MIXING_PROFILE_DEFAULTS["balanced"])

        neutral_override = self._parse_optional_int(self.neutral_threshold_q16_var.get())
        white_override = self._parse_optional_int(self.white_weight_q16_var.get())
        rgb_override = self._parse_optional_int(self.rgb_weight_q16_var.get())

        neutral_q16 = self._clamp_u16(neutral_override if neutral_override is not None else defaults["neutral_threshold_q16"])
        white_weight_q16 = self._clamp_u16(white_override if white_override is not None else defaults["white_weight_q16"])
        rgb_weight_q16 = self._clamp_u16(rgb_override if rgb_override is not None else defaults["rgb_weight_q16"])

        white_scale = max(0.0, self._safe_float(self.white_channel_scale_var, 1.0))
        white_gamma = max(0.05, self._safe_float(self.white_channel_gamma_var, 1.0))
        target_ratio = max(0.2, self._safe_float(self.auto_white_target_ratio_var, 1.35))
        min_code = max(1, self._safe_int(self.auto_white_min_code_var, 24))

        return {
            "mixing_profile": profile,
            "neutral_threshold_q16": neutral_q16,
            "white_weight_q16": white_weight_q16,
            "rgb_weight_q16": rgb_weight_q16,
            "white_channel_scale": white_scale,
            "white_channel_gamma": white_gamma,
            "auto_white_scale": bool(self.auto_white_scale_var.get()),
            "auto_white_target_ratio": target_ratio,
            "auto_white_min_code": min_code,
        }

    def _estimate_auto_white_scale_preview(self, measure_dir, max_bfi, target_ratio, min_code):
        rgb = {}
        rgbw = {}

        for csv_path in sorted(Path(measure_dir).glob("plan_capture_*.csv")):
            try:
                with open(csv_path, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if str(row.get("ok", "")).strip() != "True" or row.get("Y") in (None, ""):
                            continue
                        r = int(row.get("r", 0))
                        g = int(row.get("g", 0))
                        b = int(row.get("b", 0))
                        w = int(row.get("w", 0))
                        if r <= 0 or not (r == g == b) or r < int(min_code):
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

                        key = (bfi, r)
                        y = float(row.get("Y", 0.0))
                        if w == 0 and bfi_w == 0:
                            rgb.setdefault(key, []).append(y)
                        elif w == r and bfi_w == bfi:
                            rgbw.setdefault(key, []).append(y)
            except Exception as exc:
                self.log_line(f"Failed reading {csv_path.name}: {exc}")

        ratios = []
        for key in sorted(set(rgb.keys()) & set(rgbw.keys())):
            rgb_vals = rgb[key]
            rgbw_vals = rgbw[key]
            if not rgb_vals or not rgbw_vals:
                continue
            y_rgb = sum(rgb_vals) / len(rgb_vals)
            y_rgbw = sum(rgbw_vals) / len(rgbw_vals)
            if y_rgb > 0.0:
                ratios.append(y_rgbw / y_rgb)

        if not ratios:
            return 1.0, {"pair_count": 0, "median_ratio": None, "recommended_scale": 1.0}

        ratios = sorted(ratios)
        mid = len(ratios) // 2
        median = ratios[mid] if len(ratios) % 2 == 1 else (ratios[mid - 1] + ratios[mid]) * 0.5
        recommended = (float(target_ratio) / median) if median > 0.0 else 1.0
        recommended = max(0.5, min(1.0, recommended))
        return recommended, {
            "pair_count": len(ratios),
            "median_ratio": median,
            "recommended_scale": recommended,
        }

    def _apply_white_policy_preview(self, r, g, b, w, white_policy, mixing):
        r = max(0.0, min(1.0, float(r)))
        g = max(0.0, min(1.0, float(g)))
        b = max(0.0, min(1.0, float(b)))
        w = max(0.0, min(1.0, float(w)))

        if white_policy == "disabled":
            return r, g, b, 0.0

        min_rgb = min(r, g, b)
        max_rgb = max(r, g, b)
        delta = max_rgb - min_rgb
        neutral_thresh = float(mixing["neutral_threshold_q16"]) / 65535.0
        near_neutral = delta <= neutral_thresh

        if white_policy == "near-neutral" and not near_neutral:
            return r, g, b, 0.0

        move_to_white = (white_policy == "white-priority") or (white_policy == "measured-optimal" and near_neutral)
        if move_to_white:
            white_weight = float(mixing["white_weight_q16"]) / 65535.0
            moved = min_rgb * white_weight
            r = max(0.0, r - min(r, moved))
            g = max(0.0, g - min(g, moved))
            b = max(0.0, b - min(b, moved))
            w = min(1.0, w + moved)

        return r, g, b, w

    def _shape_white_for_preview(self, w_norm, gamma, effective_scale):
        w_norm = self._clamp01(w_norm)
        return self._clamp01((w_norm ** max(0.05, float(gamma))) * max(0.0, float(effective_scale)))

    def _simulate_swatch_after_rgb(self, rgb8, white_policy, settings, effective_scale):
        in_r = self._clamp01(rgb8[0] / 255.0)
        in_g = self._clamp01(rgb8[1] / 255.0)
        in_b = self._clamp01(rgb8[2] / 255.0)

        r2, g2, b2, w2 = self._apply_white_policy_preview(in_r, in_g, in_b, 0.0, white_policy, settings)

        rgb_weight = self._clamp01(float(settings["rgb_weight_q16"]) / 65535.0)
        r2 *= rgb_weight
        g2 *= rgb_weight
        b2 *= rgb_weight

        w2 = self._shape_white_for_preview(w2, settings["white_channel_gamma"], effective_scale)

        # Approximate visual result: white emitter contributes equally to displayed RGB luminance.
        out_r = self._clamp01(r2 + w2)
        out_g = self._clamp01(g2 + w2)
        out_b = self._clamp01(b2 + w2)
        return (out_r, out_g, out_b)

    def refresh_calibration_visuals(self):
        if not hasattr(self, "ax_calmix_top"):
            return

        settings = self._collect_calibration_ui_settings()
        policy = self.white_policy_var.get()
        max_bfi = self._safe_int(self.patch_max_bfi_var, 4)

        auto_stats = {"pair_count": 0, "median_ratio": None, "recommended_scale": 1.0}
        effective_scale = settings["white_channel_scale"]
        if settings["auto_white_scale"]:
            auto_scale, auto_stats = self._estimate_auto_white_scale_preview(
                self.calmeasure_dir_var.get(),
                max_bfi,
                settings["auto_white_target_ratio"],
                settings["auto_white_min_code"],
            )
            effective_scale *= auto_scale

        x = [i / 100.0 for i in range(101)]
        out_r = []
        out_g = []
        out_b = []
        out_w = []
        white_share = []
        chroma_keep = []

        for t in x:
            in_r = 1.0
            in_g = 0.35 + (0.65 * t)
            in_b = 0.05 + (0.95 * t)

            r2, g2, b2, w2 = self._apply_white_policy_preview(in_r, in_g, in_b, 0.0, policy, settings)
            out_r.append(r2)
            out_g.append(g2)
            out_b.append(b2)
            out_w.append(w2)

            total = r2 + g2 + b2 + w2
            white_share.append((w2 / total) if total > 1e-9 else 0.0)

            chroma_in = max(in_r, in_g, in_b) - min(in_r, in_g, in_b)
            chroma_out = max(r2, g2, b2) - min(r2, g2, b2)
            chroma_keep.append((chroma_out / chroma_in) if chroma_in > 1e-9 else 1.0)

        self.ax_calmix_top.clear()
        self.ax_calmix_bottom.clear()

        self.ax_calmix_top.plot(x, out_r, label="R out")
        self.ax_calmix_top.plot(x, out_g, label="G out")
        self.ax_calmix_top.plot(x, out_b, label="B out")
        self.ax_calmix_top.plot(x, out_w, label="W out")
        self.ax_calmix_top.set_title(f"Warm-to-neutral sweep ({policy}, {settings['mixing_profile']})")
        self.ax_calmix_top.set_ylabel("Normalized channel")
        self.ax_calmix_top.grid(True, alpha=0.3)
        self.ax_calmix_top.legend(loc="best")

        self.ax_calmix_bottom.plot(x, white_share, label="white share")
        self.ax_calmix_bottom.plot(x, chroma_keep, label="chroma retained")
        self.ax_calmix_bottom.set_xlabel("Warm -> Neutral blend")
        self.ax_calmix_bottom.set_ylabel("Ratio")
        self.ax_calmix_bottom.set_ylim(0.0, 1.05)
        self.ax_calmix_bottom.grid(True, alpha=0.3)
        self.ax_calmix_bottom.legend(loc="best")
        self.figure_calmix.tight_layout()
        self.canvas_calmix.draw()

        x_codes = list(range(256))
        linear = [i / 255.0 for i in x_codes]
        shaped = []
        prev = 0.0
        gamma = settings["white_channel_gamma"]
        for y in linear:
            shaped_y = max(0.0, min(1.0, (y ** gamma) * effective_scale))
            if shaped_y < prev:
                shaped_y = prev
            shaped.append(shaped_y)
            prev = shaped_y

        self.ax_calshape.clear()
        self.ax_calshape.plot(x_codes, [v * 65535.0 for v in linear], label="linear W LUT")
        self.ax_calshape.plot(x_codes, [v * 65535.0 for v in shaped], label="shaped W LUT")
        self.ax_calshape.set_title("White LUT shape preview")
        self.ax_calshape.set_xlabel("Input code")
        self.ax_calshape.set_ylabel("Output Q16")
        self.ax_calshape.grid(True, alpha=0.3)
        self.ax_calshape.legend(loc="best")
        self.figure_calshape.tight_layout()
        self.canvas_calshape.draw()

        warm_swatch_chroma = []
        warm_swatch_luma = []
        if hasattr(self, "ax_swatch"):
            self.ax_swatch.clear()
            swatch_count = len(SWATCH_PREVIEW_COLORS)
            self.ax_swatch.set_xlim(0.0, float(max(1, swatch_count)))
            self.ax_swatch.set_ylim(0.0, 2.15)
            self.ax_swatch.set_title(f"White policy off (top) vs '{policy}' (bottom)  —  {settings['mixing_profile']}")
            self.ax_swatch.set_xticks([])
            self.ax_swatch.set_yticks([])
            for spine in self.ax_swatch.spines.values():
                spine.set_visible(False)

            for idx, (label, rgb8) in enumerate(SWATCH_PREVIEW_COLORS):
                # "before" = same inputs but white policy forced off (disabled)
                # so both rows react when you change settings, clearly showing the effect.
                before_rgb = self._simulate_swatch_after_rgb(rgb8, "disabled", settings, effective_scale)
                after_rgb = self._simulate_swatch_after_rgb(rgb8, policy, settings, effective_scale)
                x0 = float(idx) + 0.03
                width = 0.94
                self.ax_swatch.add_patch(Rectangle((x0, 1.12), width, 0.82, facecolor=before_rgb, edgecolor="#111111", linewidth=0.35))
                self.ax_swatch.add_patch(Rectangle((x0, 0.18), width, 0.82, facecolor=after_rgb, edgecolor="#111111", linewidth=0.35))
                if idx % 2 == 0 or idx == (swatch_count - 1):
                    self.ax_swatch.text(x0 + (width * 0.5), 0.03, label, ha="center", va="bottom", fontsize=6, rotation=45)

                if idx < 5:
                    chroma_before = max(before_rgb) - min(before_rgb)
                    chroma_after = max(after_rgb) - min(after_rgb)
                    chroma_ratio = (chroma_after / chroma_before) if chroma_before > 1e-9 else 1.0
                    warm_swatch_chroma.append(chroma_ratio)

                    luma_before = (0.2126 * before_rgb[0]) + (0.7152 * before_rgb[1]) + (0.0722 * before_rgb[2])
                    luma_after = (0.2126 * after_rgb[0]) + (0.7152 * after_rgb[1]) + (0.0722 * after_rgb[2])
                    warm_swatch_luma.append((luma_after / luma_before) if luma_before > 1e-9 else 1.0)

            self.ax_swatch.text(0.01, 0.97, "policy off (top)", transform=self.ax_swatch.transAxes, ha="left", va="top", fontsize=8)
            self.ax_swatch.text(0.01, 0.50, f"policy: {policy} (bottom)", transform=self.ax_swatch.transAxes, ha="left", va="top", fontsize=8)
            self.figure_swatch.tight_layout()
            self.canvas_swatch.draw()

        warm_swatch_chroma_avg = sum(warm_swatch_chroma) / len(warm_swatch_chroma) if warm_swatch_chroma else 1.0
        warm_swatch_luma_avg = sum(warm_swatch_luma) / len(warm_swatch_luma) if warm_swatch_luma else 1.0

        warm_idx = int(0.35 * (len(x) - 1))
        warm_share = white_share[warm_idx]
        warm_chroma = chroma_keep[warm_idx]

        self.cal_preview_text.delete("1.0", "end")
        lines = [
            "Calibration Preview Summary",
            "===========================",
            f"Patch preset: {self.patch_preset_var.get()}",
            f"Policy: {policy}",
            f"Mixing profile: {settings['mixing_profile']}",
            f"neutral_threshold_q16: {settings['neutral_threshold_q16']}",
            f"white_weight_q16: {settings['white_weight_q16']}",
            f"rgb_weight_q16: {settings['rgb_weight_q16']}",
            "",
            f"white_channel_scale requested: {settings['white_channel_scale']:.3f}",
            f"white_channel_scale effective: {effective_scale:.3f}",
            f"white_channel_gamma: {settings['white_channel_gamma']:.3f}",
            f"auto_white_scale enabled: {settings['auto_white_scale']}",
            f"auto pair count: {auto_stats['pair_count']}",
            f"auto median RGBW/RGB ratio: {auto_stats['median_ratio']}",
            f"auto recommended scale: {auto_stats['recommended_scale']:.3f}",
            "",
            "Warm-tone indicators (around amber region):",
            f"white share: {warm_share:.3f}",
            f"chroma retained: {warm_chroma:.3f}",
            f"swatch warm chroma retained (avg): {warm_swatch_chroma_avg:.3f}",
            f"swatch warm luma gain (avg): {warm_swatch_luma_avg:.3f}",
        ]
        if warm_share > 0.35:
            lines.append("Hint: warm region still white-heavy; reduce white scale or white weight.")
        if warm_chroma < 0.70:
            lines.append("Hint: chroma is dropping; lower white weight or tighten neutral threshold.")
        if warm_swatch_luma_avg > 1.12:
            lines.append("Hint: warm swatches are brightening; trim white scale or lower white weight.")
        self.cal_preview_text.insert("end", "\n".join(lines))

    def _build_log_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Log")
        frame.pack(fill="both", expand=True)
        self.log = tk.Text(frame, wrap="word", height=12)
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_visualization_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="5) Preview / Summary")
        frame.pack(fill="both", expand=True, pady=(0,12))
        top = ttk.Frame(frame); top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text="Preview channel").pack(side="left")
        ttk.Combobox(top, textvariable=self.preview_channel_var, values=CHANNELS, state="readonly", width=6).pack(side="left", padx=6)
        ttk.Button(top, text="Refresh preview", command=self.refresh_preview).pack(side="left", padx=(0,20))
        body = ttk.PanedWindow(frame, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0,8))
        left = ttk.Frame(body); body.add(left, weight=4)
        notebook = ttk.Notebook(left); notebook.pack(fill="both", expand=True)
        curve_tab = ttk.Frame(notebook); notebook.add(curve_tab, text="LUT Curve")
        self.figure_curve = Figure(figsize=(7,5), dpi=100)
        self.ax_curve = self.figure_curve.add_subplot(111)
        self.canvas_curve = FigureCanvasTkAgg(self.figure_curve, master=curve_tab)
        self.canvas_curve.get_tk_widget().pack(fill="both", expand=True)
        cie_tab = ttk.Frame(notebook); notebook.add(cie_tab, text="CIE xy Chart")
        cie_top = ttk.Frame(cie_tab)
        cie_top.pack(fill="x", padx=8, pady=(8, 0))
        ttk.Label(cie_top, text="Overlay spaces").pack(side="left")
        for key, spec in CIE_GAMUT_OVERLAYS.items():
            ttk.Checkbutton(cie_top, text=spec["label"], variable=self.cie_overlay_vars[key], command=self.refresh_preview).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(cie_top, text="White points", variable=self.cie_show_white_points_var, command=self.refresh_preview).pack(side="left", padx=(12, 0))
        cie_body = ttk.PanedWindow(cie_tab, orient="horizontal")
        cie_body.pack(fill="both", expand=True)
        cie_info_frame = ttk.Frame(cie_body)
        cie_plot_frame = ttk.Frame(cie_body)
        cie_body.add(cie_info_frame, weight=2)
        cie_body.add(cie_plot_frame, weight=5)
        self.cie_info_text = tk.Text(cie_info_frame, wrap="word", width=38)
        self.cie_info_text.pack(fill="both", expand=True, padx=(8, 4), pady=8)
        self.figure_cie = Figure(figsize=(7,5), dpi=100)
        self.ax_cie = self.figure_cie.add_subplot(111)
        self.canvas_cie = FigureCanvasTkAgg(self.figure_cie, master=cie_plot_frame)
        self.canvas_cie.get_tk_widget().pack(fill="both", expand=True, padx=(4, 8), pady=8)
        density_tab = ttk.Frame(notebook); notebook.add(density_tab, text="Ladder Density")
        self.figure_density = Figure(figsize=(7,5), dpi=100)
        self.ax_density = self.figure_density.add_subplot(111)
        self.canvas_density = FigureCanvasTkAgg(self.figure_density, master=density_tab)
        self.canvas_density.get_tk_widget().pack(fill="both", expand=True)
        mono_tab = ttk.Frame(notebook); notebook.add(mono_tab, text="Monotonic Ladder")
        self.figure_mono = Figure(figsize=(7,5), dpi=100)
        self.ax_mono = self.figure_mono.add_subplot(111)
        self.canvas_mono = FigureCanvasTkAgg(self.figure_mono, master=mono_tab)
        self.canvas_mono.get_tk_widget().pack(fill="both", expand=True)

        transfer_tab = ttk.Frame(notebook); notebook.add(transfer_tab, text="Transfer Curve")
        transfer_top = ttk.Frame(transfer_tab); transfer_top.pack(fill="x", padx=8, pady=8)
        ttk.Label(transfer_top, text="Curve").pack(side="left")
        ttk.Combobox(transfer_top, textvariable=self.transfer_curve_var, values=TRANSFER_CURVE_OPTIONS, state="readonly", width=10).pack(side="left", padx=6)
        ttk.Label(transfer_top, text="Gamma").pack(side="left")
        self.transfer_gamma_entry = ttk.Entry(transfer_top, textvariable=self.transfer_gamma_var, width=8)
        self.transfer_gamma_entry.pack(side="left", padx=6)
        ttk.Label(transfer_top, text="Shadow lift").pack(side="left")
        ttk.Entry(transfer_top, textvariable=self.transfer_shadow_lift_var, width=8).pack(side="left", padx=6)
        ttk.Label(transfer_top, text="Shoulder").pack(side="left")
        ttk.Entry(transfer_top, textvariable=self.transfer_shoulder_var, width=8).pack(side="left", padx=6)
        ttk.Label(transfer_top, text="Buckets (0=auto)").pack(side="left")
        ttk.Combobox(transfer_top, textvariable=self.transfer_bucket_count_var, values=HIGH_RES_EXPORT_SIZE_OPTIONS, state="readonly", width=8).pack(side="left", padx=6)
        ttk.Label(transfer_top, text="Selection").pack(side="left")
        ttk.Combobox(transfer_top, textvariable=self.transfer_selection_var, values=["floor","nearest"], state="readonly", width=8).pack(side="left", padx=6)
        ttk.Button(transfer_top, text="Refresh transfer", command=self.refresh_transfer_curve).pack(side="left", padx=10)

        transfer_meta = ttk.Frame(transfer_tab)
        transfer_meta.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Checkbutton(transfer_meta, text="Per-channel transfer tuning", variable=self.transfer_per_channel_var).pack(side="left")
        ttk.Label(transfer_meta, text="Peak nits override").pack(side="left", padx=(16, 0))
        ttk.Entry(transfer_meta, textvariable=self.transfer_peak_nits_override_var, width=10).pack(side="left", padx=6)
        ttk.Label(transfer_meta, text="Nit cap").pack(side="left", padx=(16, 0))
        ttk.Entry(transfer_meta, textvariable=self.transfer_nit_cap_var, width=10).pack(side="left", padx=6)
        ttk.Checkbutton(transfer_meta, text="Exclude white", variable=self.transfer_exclude_white_var).pack(side="left", padx=(16, 0))
        ttk.Label(transfer_meta, text="Leave blank to use full measured peak.").pack(side="left", padx=(6, 0))

        self.transfer_channel_controls = ttk.LabelFrame(transfer_tab, text="Per-Channel Transfer Settings")
        for ch in CHANNELS:
            row = ttk.Frame(self.transfer_channel_controls)
            row.pack(fill="x", padx=8, pady=4)
            ttk.Label(row, text=ch, width=3).pack(side="left")
            ttk.Label(row, text="Curve").pack(side="left")
            ttk.Combobox(row, textvariable=self.transfer_channel_curve_vars[ch], values=TRANSFER_CURVE_OPTIONS, state="readonly", width=10).pack(side="left", padx=6)
            ttk.Label(row, text="Gamma").pack(side="left")
            gamma_entry = ttk.Entry(row, textvariable=self.transfer_channel_gamma_vars[ch], width=8)
            gamma_entry.pack(side="left", padx=6)
            self.__dict__[f"transfer_gamma_entry_{ch}"] = gamma_entry
            ttk.Label(row, text="Shadow lift").pack(side="left")
            ttk.Entry(row, textvariable=self.transfer_channel_shadow_lift_vars[ch], width=8).pack(side="left", padx=6)
            ttk.Label(row, text="Shoulder").pack(side="left")
            ttk.Entry(row, textvariable=self.transfer_channel_shoulder_vars[ch], width=8).pack(side="left", padx=6)

        transfer_export_row = ttk.Frame(transfer_tab)
        transfer_export_row.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Label(transfer_export_row, text="Transfer header").pack(side="left")
        ttk.Entry(transfer_export_row, textvariable=self.transfer_export_header_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(transfer_export_row, text="Browse...", command=self.choose_transfer_header_out).pack(side="left")
        ttk.Button(transfer_export_row, text="Export transfer header", command=self.export_transfer_header).pack(side="left", padx=8)

        ttk.Label(transfer_tab, textvariable=self.transfer_curve_note_var).pack(anchor="w", padx=10, pady=(0, 4))
        self.figure_transfer = Figure(figsize=(7,7), dpi=100)
        self.ax_transfer_top = self.figure_transfer.add_subplot(311)
        self.ax_transfer_mid = self.figure_transfer.add_subplot(312)
        self.ax_transfer_bottom = self.figure_transfer.add_subplot(313)
        self.canvas_transfer = FigureCanvasTkAgg(self.figure_transfer, master=transfer_tab)
        self.canvas_transfer.get_tk_widget().pack(fill="both", expand=True)

        luma_tab = ttk.Frame(notebook); notebook.add(luma_tab, text="Luma Weights")
        luma_top = ttk.Frame(luma_tab); luma_top.pack(fill="x", padx=8, pady=8)
        ttk.Label(luma_top, text="Method").pack(side="left")
        ttk.Combobox(luma_top, textvariable=self.luma_method_var, values=["average","max","median"], state="readonly", width=10).pack(side="left", padx=6)
        ttk.Label(luma_top, text="BFI source").pack(side="left")
        ttk.Combobox(luma_top, textvariable=self.luma_bfi_source_var, values=["all",0,1,2,3,4,5,6,7,8], state="readonly", width=8).pack(side="left", padx=6)
        ttk.Button(luma_top, text="Refresh luma", command=self.refresh_luma_weights).pack(side="left", padx=10)
        luma_split = ttk.PanedWindow(luma_tab, orient="horizontal")
        luma_split.pack(fill="both", expand=True)
        luma_left = ttk.Frame(luma_split)
        luma_right = ttk.Frame(luma_split)
        luma_split.add(luma_left, weight=3)
        luma_split.add(luma_right, weight=2)
        self.figure_luma = Figure(figsize=(7,5), dpi=100)
        self.ax_luma = self.figure_luma.add_subplot(111)
        self.canvas_luma = FigureCanvasTkAgg(self.figure_luma, master=luma_left)
        self.canvas_luma.get_tk_widget().pack(fill="both", expand=True)
        self.luma_text = tk.Text(luma_right, wrap="word")
        self.luma_text.pack(fill="both", expand=True)
        ladder_tab = ttk.Frame(notebook); notebook.add(ladder_tab, text="Temporal Ladder")
        self.ladder_text = tk.Text(ladder_tab, wrap="none")
        self.ladder_text.pack(fill="both", expand=True)
        right = ttk.Frame(body); body.add(right, weight=2)
        self.summary_box = tk.Text(right, wrap="word", width=48)
        self.summary_box.pack(fill="both", expand=True)

    def log_line(self, t):
        self.log.insert("end", t + "\n")
        self.log.see("end")
        self.root.update_idletasks()

    def set_busy(self, busy):
        self.busy = busy

    def _set_refresh_progress(self, token, message, fraction):
        if token != self._preview_refresh_token:
            return
        self.refresh_status_var.set(str(message))
        self.refresh_progress_var.set(max(0.0, min(100.0, float(fraction) * 100.0)))
        self.root.update_idletasks()

    def _clear_refresh_progress(self, message="Preview idle."):
        self.refresh_status_var.set(str(message))
        self.refresh_progress_var.set(0.0)
        self.root.update_idletasks()

    def set_default_plan_filename(self):
        channel = self.plan_channel_var.get().lower()
        if self.plan_preset_var.get() != "custom":
            suffix = self.plan_preset_var.get()
        else:
            dense = self.plan_step_var.get() <= 0
            suffix = "dense" if dense else f"step{self.plan_step_var.get()}"
        name = f"measurement_plan_rgbw_{suffix}.csv" if channel == "all" else f"measurement_plan_{channel}_{suffix}.csv"
        self.plan_out_var.set(str((self.script_dir / name).resolve()))


    def choose_transfer_json_out(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")])
        if path:
            self.transfer_export_json_var.set(path)

    def choose_transfer_header_out(self):
        path = filedialog.asksaveasfilename(defaultextension=".h", filetypes=[("Header Files", "*.h"), ("All Files", "*.*")])
        if path:
            self.transfer_export_header_var.set(path)


    def choose_luma_json_out(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")])
        if path:
            self.luma_export_json_var.set(path)

    def choose_luma_header_out(self):
        path = filedialog.asksaveasfilename(defaultextension=".h", filetypes=[("Header Files", "*.h"), ("All Files", "*.*")])
        if path:
            self.luma_export_header_var.set(path)

    def choose_plan_out(self):
        p = filedialog.asksaveasfilename(initialdir=str(self.script_dir), defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if p: self.plan_out_var.set(p)
    def choose_measure_dir(self):
        p = filedialog.askdirectory(initialdir=self.measure_dir_var.get() or str(self.script_dir))
        if p: self.measure_dir_var.set(p)
    def choose_build_out_dir(self):
        p = filedialog.askdirectory(initialdir=self.build_out_dir_var.get() or str(self.script_dir))
        if p: self.build_out_dir_var.set(p)
    def choose_export_out_dir(self):
        p = filedialog.askdirectory(initialdir=self.export_out_var.get() or str(self.script_dir))
        if p: self.export_out_var.set(p)
    def choose_solver_header_out(self):
        p = filedialog.asksaveasfilename(initialdir=str(self.export_out_var.get() or self.default_export_dir), defaultextension=".h", filetypes=[("Header files", "*.h"), ("All files", "*.*")])
        if p: self.solver_header_out_var.set(p)
    def choose_precomputed_solver_source_header(self):
        p = filedialog.askopenfilename(filetypes=[("Header files", "*.h"), ("All files", "*.*")])
        if p: self.precomputed_solver_source_header_var.set(p)
    def choose_precomputed_calibration_header(self):
        p = filedialog.askopenfilename(filetypes=[("Header files", "*.h"), ("All files", "*.*")])
        if p: self.precomputed_calibration_header_var.set(p)
    def choose_precomputed_solver_out(self):
        p = filedialog.asksaveasfilename(initialdir=str(self.export_out_var.get() or self.default_export_dir), defaultextension=".h", filetypes=[("Header files", "*.h"), ("All files", "*.*")])
        if p: self.precomputed_solver_out_var.set(p)
    def choose_calmeasure_dir(self):
        p = filedialog.askdirectory(initialdir=self.calmeasure_dir_var.get() or str(self.script_dir))
        if p: self.calmeasure_dir_var.set(p)
    def choose_true16_calmeasure_dir(self):
        p = filedialog.askdirectory(initialdir=self.true16_calmeasure_dir_var.get() or str(self.script_dir))
        if p: self.true16_calmeasure_dir_var.set(p)
    def choose_patch_plan_out(self):
        p = filedialog.asksaveasfilename(initialdir=str(self.script_dir), defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if p: self.patch_plan_out_var.set(p)
    def choose_true16_patch_plan_out(self):
        p = filedialog.asksaveasfilename(initialdir=str(self.script_dir), defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if p: self.true16_patch_plan_out_var.set(p)
    def choose_true16_header_out(self):
        p = filedialog.asksaveasfilename(initialdir=str(self.export_out_var.get() or self.default_export_dir), defaultextension=".h", filetypes=[("Header files", "*.h"), ("All files", "*.*")])
        if p:
            self.true16_header_out_var.set(p)
            self._sync_true16_report_path_to_header(Path(p).expanduser())

    def _sync_true16_report_path_to_header(self, header_path):
        header_path = Path(header_path).expanduser()
        if header_path.suffix:
            report_path = header_path.with_name(f"{header_path.stem}_report.json")
        else:
            report_path = header_path.with_name(f"{header_path.name}_report.json")
        self.true16_qa_report_out_var.set(str(report_path))
        return report_path

    def choose_true16_qa_report_out(self):
        p = filedialog.asksaveasfilename(initialdir=str(self.export_out_var.get() or self.default_export_dir), defaultextension=".json", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if p: self.true16_qa_report_out_var.set(p)
    def choose_true16_transfer_curve_header(self):
        p = filedialog.askopenfilename(filetypes=[("Header files", "*.h"), ("All files", "*.*")])
        if p: self.true16_transfer_curve_header_var.set(p)

    def open_output_folder(self):
        path = Path(self.build_out_dir_var.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Open folder failed", str(exc))

    def run_subprocess(self, args, on_success=None):
        self._save_config()
        if self.busy:
            messagebox.showinfo("Busy", "A task is already running.")
            return
        def worker():
            self.root.after(0, lambda: self.set_busy(True))
            self.root.after(0, lambda: self.log_line("Running: " + " ".join(args)))
            try:
                proc = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(self.script_dir),
                )
                # Stream stderr lines live (progress messages).
                stderr_lines = []
                for line in proc.stderr:
                    line = line.rstrip("\n\r")
                    if line:
                        stderr_lines.append(line)
                        self.root.after(0, lambda l=line: self.log_line(l))
                stdout = proc.stdout.read().strip()
                proc.wait()
                stderr = "\n".join(stderr_lines)
                def finish():
                    if stdout: self.log_line(stdout)
                    self.log_line(f"Exit code: {proc.returncode}")
                    self.set_busy(False)
                    if proc.returncode == 0 and on_success:
                        on_success(stdout)
                    elif proc.returncode != 0:
                        messagebox.showerror("Command failed", stderr or stdout or f"Exit code {proc.returncode}")
                self.root.after(0, finish)
            except Exception as exc:
                self.root.after(0, lambda: self.set_busy(False))
                self.root.after(0, lambda: messagebox.showerror("Run failed", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def generate_plan(self):
        ch = self.plan_channel_var.get()
        if ch == "ALL" and not messagebox.askyesno("Long capture warning", "Generating an ALL-channel plan will take a long time to capture.\nContinue?"):
            return
        out_path = Path(self.plan_out_var.get()).expanduser(); out_path.parent.mkdir(parents=True, exist_ok=True)
        args = [
            sys.executable, str(self.tool_path), "plan",
            "--channel", ch,
            "--out", str(out_path),
            "--max-bfi", str(self.plan_max_bfi_var.get()),
            "--step", str(self.plan_step_var.get()),
            "--mode", self.plan_mode_var.get(),
            "--preset", self.plan_preset_var.get(),
        ]
        if self.plan_mode_var.get() == "temporal-blend":
            args += ["--floor-step", str(self.plan_floor_step_var.get())]
        self.run_subprocess(args, on_success=lambda _s: messagebox.showinfo("Plan generated", f"Measurement plan written to:\n{out_path}"))

    def build_luts(self):
        measure_dir = Path(self.measure_dir_var.get()).expanduser(); out_dir = Path(self.build_out_dir_var.get()).expanduser(); out_dir.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, str(self.tool_path), "build", "--measure-dir", str(measure_dir), "--out-dir", str(out_dir)]
        def success(_):
            self.load_summary(); self.refresh_preview(); messagebox.showinfo("LUT build complete", f"LUT outputs written to:\n{out_dir}")
        self.run_subprocess(args, on_success=success)

    def generate_patch_plan(self):
        out_path = Path(self.patch_plan_out_var.get()).expanduser(); out_path.parent.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, str(self.tool_path), "patch-plan", "--preset", self.patch_preset_var.get(), "--out", str(out_path), "--max-bfi", str(self.patch_max_bfi_var.get())]
        self.run_subprocess(args, on_success=lambda _s: messagebox.showinfo("Patch plan generated", f"Patch plan written to:\n{out_path}"))

    def _parse_true16_input_globs(self):
        raw = str(self.true16_input_globs_var.get() or "").strip()
        if not raw:
            return []
        return [g.strip() for g in re.split(r"[,;\n]+", raw) if g.strip()]

    def _append_true16_common_fit_args(self, args, include_qa_report=False):
        args += ["--aggregate", self.true16_aggregate_var.get()]
        args += ["--trim-fraction", str(self._safe_float(self.true16_trim_fraction_var, 0.1))]
        args += ["--outlier-sigma", str(self._safe_float(self.true16_outlier_sigma_var, 3.5))]
        if not bool(self.true16_enforce_monotonic_var.get()):
            args.append("--disable-monotonic")

        if not bool(self.true16_inverse_regularization_var.get()):
            args.append("--disable-inverse-regularization")
        inverse_max_step = self._parse_optional_int(self.true16_inverse_max_step_q16_var.get())
        if inverse_max_step is not None:
            args += ["--inverse-max-step-q16", str(max(1, int(inverse_max_step)))]

        if not bool(self.true16_enable_mixed_patch_correction_var.get()):
            args.append("--disable-mixed-patch-correction")
        args += [
            "--mixed-correction-strength", str(max(0.0, self._safe_float(self.true16_mixed_correction_strength_var, 0.65))),
            "--mixed-backbone-lock-strength", str(max(0.0, self._safe_float(self.true16_mixed_backbone_lock_strength_var, 0.55))),
            "--mixed-locality-width", str(max(1, self._safe_int(self.true16_mixed_locality_width_var, 24))),
            "--mixed-neutral-protection-strength", str(max(0.0, self._safe_float(self.true16_mixed_neutral_protection_strength_var, 0.75))),
            "--mixed-warm-priority", str(max(0.0, self._safe_float(self.true16_mixed_warm_priority_var, 0.35))),
            "--mixed-gamut-edge-restraint", str(max(0.0, self._safe_float(self.true16_mixed_gamut_edge_restraint_var, 0.45))),
        ]
        if not bool(self.true16_global_mixed_fit_var.get()):
            args.append("--disable-global-mixed-fit")
        args += ["--global-mixed-fit-max-iterations", str(max(1, self._safe_int(self.true16_global_mixed_fit_max_iterations_var, 5)))]
        args += [
            "--global-mixed-fit-peak-preserve-strength",
            str(max(0.0, self._safe_float(self.true16_global_mixed_fit_peak_preserve_strength_var, 0.0))),
        ]

        args += ["--white-channel-scale", str(max(0.0, self._safe_float(self.white_channel_scale_var, 1.0)))]
        args += ["--white-channel-gamma", str(max(0.05, self._safe_float(self.white_channel_gamma_var, 1.0)))]
        if bool(self.auto_white_scale_var.get()):
            args.append("--auto-white-scale")

        neutral_tol = max(0, self._safe_int(self.true16_neutral_tolerance_q16_var, 2048))
        args += ["--neutral-tolerance-q16", str(neutral_tol)]

        self._append_correction_args(args)

        for glob_pattern in self._parse_true16_input_globs():
            args += ["--input-glob", glob_pattern]

        if bool(self.true16_use_transfer_curve_header_var.get()):
            transfer_header = str(self.true16_transfer_curve_header_var.get() or "").strip()
            if transfer_header:
                args += ["--transfer-curve-header", transfer_header]

        if include_qa_report:
            qa_report_out = str(self.true16_qa_report_out_var.get() or "").strip()
            if qa_report_out:
                args += ["--qa-report", qa_report_out]

    def _append_correction_args(self, args):
        target_mode = str(self.profile_target_var.get() or "delta-preserving").strip() or "delta-preserving"
        args += ["--profile-target", target_mode]
        args += ["--profile-target-gamma", str(max(0.05, self._safe_float(self.profile_target_gamma_var, 2.2)))]

        if not bool(self.black_level_compensation_var.get()):
            args.append("--disable-black-level-compensation")

        black_override = self._parse_optional_float(self.black_level_y_var.get())
        if black_override is not None:
            args += ["--black-level-y", str(max(0.0, float(black_override)))]

    def generate_patch_plan_true16(self):
        out_path = Path(self.true16_patch_plan_out_var.get()).expanduser(); out_path.parent.mkdir(parents=True, exist_ok=True)
        args = [
            sys.executable, str(self.tool_path), "patch-plan-true16",
            "--out", str(out_path),
            "--density", self.true16_density_var.get(),
            "--repeats", str(max(1, self._safe_int(self.true16_plan_repeats_var, 1))),
        ]
        if not bool(self.true16_include_gray_var.get()):
            args.append("--no-gray-ramp")
        if not bool(self.true16_include_primary_var.get()):
            args.append("--no-primary-ramps")
        if not bool(self.true16_include_mid_var.get()):
            args.append("--no-mid-colors")
        if not bool(self.true16_include_white_protection_var.get()):
            args.append("--no-white-protection-mixes")
        self.run_subprocess(args, on_success=lambda _s: messagebox.showinfo("True16 patch plan generated", f"True16 patch plan written to:\n{out_path}"))

    # NOTE: Legacy 8→16 export-calibration-header / export-calibration-json CLI
    # subcommands remain available via temporal_lut_tools.py; the GUI buttons were
    # removed in favour of rgbw_lut_builder which is the preferred calibration path.

    def export_calibration_true16_header(self):
        out_path = Path(self.true16_header_out_var.get()).expanduser(); out_path.parent.mkdir(parents=True, exist_ok=True)
        qa_report_path = self._sync_true16_report_path_to_header(out_path)
        qa_report_out = str(qa_report_path)
        Path(qa_report_out).expanduser().parent.mkdir(parents=True, exist_ok=True)
        args = [
            sys.executable, str(self.tool_path), "export-calibration-true16-header",
            "--measure-dir", str(Path(self.true16_calmeasure_dir_var.get()).expanduser()),
            "--out", str(out_path),
            "--lut-size", str(self.true16_lut_size_var.get()),
        ]
        self._append_true16_common_fit_args(args, include_qa_report=True)

        def on_success(stdout_text):
            web_report = None
            try:
                payload = json.loads(stdout_text or "{}")
                web_report = payload.get("web_report")
            except Exception:
                web_report = None

            msg = f"True16 calibration header written to:\n{out_path}"
            if qa_report_out:
                msg += f"\n\nQA report JSON:\n{Path(qa_report_out).expanduser()}"
            if web_report:
                msg += f"\n\nHTML color sanity report:\n{Path(str(web_report)).expanduser()}"
            messagebox.showinfo("Exported", msg)

        self.run_subprocess(args, on_success=on_success)

    def analyze_calibration_true16(self):
        header_raw = str(self.true16_header_out_var.get() or "").strip()
        if header_raw:
            report_path = self._sync_true16_report_path_to_header(Path(header_raw).expanduser())
        else:
            report_raw = str(self.true16_qa_report_out_var.get() or "").strip()
            if not report_raw:
                messagebox.showerror("Missing header path", "Select a True16 header output path so the QA report can be coupled to the same directory.")
                return
            report_path = Path(report_raw).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        args = [
            sys.executable, str(self.tool_path), "analyze-calibration-true16",
            "--measure-dir", str(Path(self.true16_calmeasure_dir_var.get()).expanduser()),
            "--out", str(report_path),
            "--lut-size", str(self.true16_lut_size_var.get()),
        ]
        self._append_true16_common_fit_args(args, include_qa_report=False)
        self.run_subprocess(args, on_success=lambda _s: messagebox.showinfo("Analysis complete", f"True16 calibration report written to:\n{report_path}"))

    def load_summary(self):
        out_dir = Path(self.build_out_dir_var.get()).expanduser()
        summary_path = out_dir / "lut_summary.json"
        self.summary_box.delete("1.0", "end")
        if not summary_path.exists():
            self.summary_box.insert("end", f"Summary not found:\n{summary_path}")
            self.summary_text.set("No summary loaded")
            return
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        parts = []; pretty = []
        for ch in CHANNELS:
            entry = summary.get("channels", {}).get(ch, {})
            parts.append(f"{ch}:{entry.get('points', 0)}")
            pretty.append(
                f"{ch}\n"
                f"  measured_state_points: {entry.get('measured_state_points', entry.get('points', 0))}\n"
                f"  ladder_states: {entry.get('ladder_states', 0)}\n"
                f"  monotonic_states: {entry.get('monotonic_states', 0)}\n"
                f"  nonzero_points: {entry.get('nonzero_points', 0)}\n"
                f"  max_estimated_nobfi_Y: {entry.get('max_estimated_nobfi_Y')}\n"
            )
        self.summary_text.set("Measured states " + ", ".join(parts))
        self.summary_box.insert("end", "\n".join(pretty))

    def _load_curve_csv(self, path):
        xs, ys = [], []
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            x_key = "plotted_value" if "plotted_value" in fields else ("value" if "value" in fields else fields[0])
            y_key = "normalized_output" if "normalized_output" in fields else ("estimated_nobfi_normalized" if "estimated_nobfi_normalized" in fields else fields[1])
            for row in reader:
                xs.append(float(row[x_key])); ys.append(float(row[y_key]))
        return xs, ys

    def _path_cache_key(self, path):
        p = Path(path)
        if not p.exists():
            return None
        stat = p.stat()
        return (str(p.resolve()), int(stat.st_mtime_ns), int(stat.st_size))

    def _measure_dir_cache_key(self, measure_dir):
        measure_dir = Path(measure_dir)
        entries = []
        for pattern in ("single_measure_*.json", "plan_capture_*.csv"):
            for path in sorted(measure_dir.glob(pattern)):
                try:
                    stat = path.stat()
                    entries.append((path.name, int(stat.st_mtime_ns), int(stat.st_size)))
                except OSError:
                    continue
        return (str(measure_dir.resolve()), tuple(entries))

    def _load_cached_json(self, path):
        key = self._path_cache_key(path)
        if key is None:
            return None
        cached = self._preview_json_cache.get(key)
        if cached is not None:
            return cached
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self._preview_json_cache = {key: data, **{k: v for k, v in self._preview_json_cache.items() if k[0] != key[0]}}
        return data

    def _sample_evenly(self, values, max_points):
        if max_points <= 0 or len(values) <= max_points:
            return values
        if max_points == 1:
            return [values[0]]
        last_index = len(values) - 1
        step = last_index / float(max_points - 1)
        sampled = []
        seen = set()
        for idx in range(max_points):
            pos = int(round(idx * step))
            pos = max(0, min(last_index, pos))
            if pos in seen:
                continue
            seen.add(pos)
            sampled.append(values[pos])
        if sampled[-1] is not values[-1]:
            sampled[-1] = values[-1]
        return sampled

    def _new_preview_capture_bucket(self):
        return {"points": [], "count": 0, "sum_x": 0.0, "sum_y": 0.0}

    def _append_preview_capture_point(self, bucket, x_val, y_val, y_luma):
        bucket["count"] += 1
        bucket["sum_x"] += float(x_val)
        bucket["sum_y"] += float(y_val)
        point = {"x": float(x_val), "y": float(y_val), "Y": float(y_luma)}
        points = bucket["points"]
        if len(points) < PREVIEW_CIE_SAMPLE_MAX_POINTS:
            points.append(point)
            return
        replace_index = random.randint(0, bucket["count"] - 1)
        if replace_index < PREVIEW_CIE_SAMPLE_MAX_POINTS:
            points[replace_index] = point

    def _load_json_list(self, path):
        if not path.exists():
            return []
        data = self._load_cached_json(path)
        return data if isinstance(data, list) else []

    def _load_output_xy_points(self, out_dir, channel_filter=None):
        path = Path(out_dir) / "all_measurement_xy_points.csv"
        if not path.exists():
            return []
        cache_key = self._path_cache_key(path)
        if cache_key in self._preview_output_xy_cache:
            pts = self._preview_output_xy_cache[cache_key]
        else:
            pts = []
            try:
                with open(path, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        channel = str(row.get("channel", "")).upper().strip()
                        if channel not in CHANNELS:
                            continue
                        if row.get("x") in (None, "") or row.get("y") in (None, "") or row.get("Y") in (None, ""):
                            continue
                        pts.append({
                            "x": float(row["x"]),
                            "y": float(row["y"]),
                            "Y": float(row["Y"]),
                            "channel": channel,
                        })
            except Exception as exc:
                self.log_line(f"Failed to load output xy points: {exc}")
                return []
            self._preview_output_xy_cache = {cache_key: pts, **{k: v for k, v in self._preview_output_xy_cache.items() if k[0] != cache_key[0]}}
        if not channel_filter:
            return pts
        return [point for point in pts if point["channel"] == channel_filter]

    def _load_output_xy_preview_buckets(self, out_dir):
        path = Path(out_dir) / "all_measurement_xy_points.csv"
        if not path.exists():
            return None
        cache_key = self._path_cache_key(path)
        cached = self._preview_output_xy_cache.get(("preview", cache_key))
        if cached is not None:
            return cached

        buckets = {channel: self._new_preview_capture_bucket() for channel in CHANNELS}
        try:
            with open(path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    channel = str(row.get("channel", "")).upper().strip()
                    if channel not in CHANNELS:
                        continue
                    if row.get("x") in (None, "") or row.get("y") in (None, "") or row.get("Y") in (None, ""):
                        continue
                    self._append_preview_capture_point(
                        buckets[channel],
                        float(row["x"]),
                        float(row["y"]),
                        float(row["Y"]),
                    )
        except Exception as exc:
            self.log_line(f"Failed to load output xy preview points: {exc}")
            return None

        self._preview_output_xy_cache[("preview", cache_key)] = buckets
        return buckets

    def _begin_capture_preview_scan(self, state):
        state["capture_preview"] = {channel: self._new_preview_capture_bucket() for channel in CHANNELS}
        state["capture_scan"] = {
            "single_paths": sorted(Path(state["measure_dir"]).glob("single_measure_*.json")),
            "single_index": 0,
            "csv_paths": sorted(Path(state["measure_dir"]).glob("plan_capture_*.csv")),
            "csv_index": 0,
            "csv_handle": None,
            "csv_reader": None,
        }

    def _extract_preview_json_point(self, obj):
        render = obj.get("render", {})
        meas = obj.get("measurement", {})
        x_val = meas.get("x")
        y_val = meas.get("y")
        y_luma = meas.get("Y")
        if x_val is None or y_val is None or y_luma is None:
            return None
        upper = {ch: int(render.get(f"upper_{ch.lower()}", render.get(ch.lower(), 0)) or 0) for ch in CHANNELS}
        lower = {ch: int(render.get(f"lower_{ch.lower()}", 0) or 0) for ch in CHANNELS}
        bfis = {ch: int(render.get(f"bfi_{ch.lower()}", 0) or 0) for ch in CHANNELS}
        active = [ch for ch in CHANNELS if upper[ch] > 0 or lower[ch] > 0 or bfis[ch] > 0]
        if len(active) != 1:
            return None
        return active[0], float(x_val), float(y_val), float(y_luma)

    def _extract_preview_csv_point(self, row):
        if str(row.get("ok", "")).strip() != "True":
            return None
        if row.get("x") in (None, "") or row.get("y") in (None, "") or row.get("Y") in (None, ""):
            return None
        upper = {ch: int(row.get(f"upper_{ch.lower()}", row.get(ch.lower(), 0)) or 0) for ch in CHANNELS}
        lower = {ch: int(row.get(f"lower_{ch.lower()}", 0) or 0) for ch in CHANNELS}
        bfis = {ch: int(row.get(f"bfi_{ch.lower()}", 0) or 0) for ch in CHANNELS}
        active = [ch for ch in CHANNELS if upper[ch] > 0 or lower[ch] > 0 or bfis[ch] > 0]
        if len(active) != 1:
            return None
        return active[0], float(row["x"]), float(row["y"]), float(row["Y"])

    def _preview_capture_scan_step(self, token):
        if token != self._preview_refresh_token:
            return
        state = self._preview_refresh_state
        if not state:
            return
        scan = state["capture_scan"]
        processed = 0
        while processed < PREVIEW_CAPTURE_SCAN_ROW_BATCH:
            if scan["single_index"] < len(scan["single_paths"]):
                limit = min(len(scan["single_paths"]), scan["single_index"] + PREVIEW_SINGLE_MEASURE_BATCH)
                while scan["single_index"] < limit:
                    path = scan["single_paths"][scan["single_index"]]
                    scan["single_index"] += 1
                    processed += 1
                    try:
                        point = self._extract_preview_json_point(json.loads(path.read_text(encoding="utf-8")))
                    except Exception:
                        point = None
                    if point is None:
                        continue
                    channel, x_val, y_val, y_luma = point
                    self._append_preview_capture_point(state["capture_preview"][channel], x_val, y_val, y_luma)
                continue
            if scan["csv_handle"] is None:
                if scan["csv_index"] >= len(scan["csv_paths"]):
                    break
                try:
                    scan["csv_handle"] = open(scan["csv_paths"][scan["csv_index"]], "r", newline="", encoding="utf-8")
                    scan["csv_reader"] = csv.DictReader(scan["csv_handle"])
                except Exception as exc:
                    self.log_line(f"Failed to open capture CSV: {exc}")
                    scan["csv_index"] += 1
                    scan["csv_handle"] = None
                    scan["csv_reader"] = None
                    continue
            try:
                row = next(scan["csv_reader"])
            except StopIteration:
                scan["csv_handle"].close()
                scan["csv_handle"] = None
                scan["csv_reader"] = None
                scan["csv_index"] += 1
                continue
            except Exception as exc:
                self.log_line(f"Failed while reading capture CSV: {exc}")
                scan["csv_handle"].close()
                scan["csv_handle"] = None
                scan["csv_reader"] = None
                scan["csv_index"] += 1
                continue
            processed += 1
            point = self._extract_preview_csv_point(row)
            if point is None:
                continue
            channel, x_val, y_val, y_luma = point
            self._append_preview_capture_point(state["capture_preview"][channel], x_val, y_val, y_luma)

        finished = (
            scan["single_index"] >= len(scan["single_paths"]) and
            scan["csv_index"] >= len(scan["csv_paths"]) and
            scan["csv_handle"] is None
        )
        total_scan_items = max(1, len(scan["single_paths"]) + len(scan["csv_paths"]))
        completed_items = min(total_scan_items, scan["single_index"] + scan["csv_index"])
        self._set_refresh_progress(
            token,
            f"Refreshing {state['channel']} preview: scanning capture fallback {completed_items}/{total_scan_items}",
            0.32 + (0.16 * (completed_items / float(total_scan_items))),
        )
        if finished:
            cache_key = state["capture_preview_cache_key"]
            self._preview_capture_scan_cache = {
                cache_key: state["capture_preview"],
                **{k: v for k, v in self._preview_capture_scan_cache.items() if k[0] != cache_key[0]},
            }
            self.root.after(1, lambda: self._refresh_preview_render_cie(token))
            return
        self.root.after(1, lambda: self._preview_capture_scan_step(token))

    def _draw_cie_gamut_overlays(self):
        for key, spec in CIE_GAMUT_OVERLAYS.items():
            if not bool(self.cie_overlay_vars[key].get()):
                continue
            points = list(spec["points"])
            poly_x = [pt[0] for pt in points] + [points[0][0]]
            poly_y = [pt[1] for pt in points] + [points[0][1]]
            self.ax_cie.fill(
                poly_x,
                poly_y,
                color=spec["color"],
                alpha=0.08,
                linewidth=0.0,
                zorder=2,
            )
            self.ax_cie.plot(
                poly_x,
                poly_y,
                color=spec["color"],
                linewidth=1.6,
                linestyle="--",
                alpha=0.95,
                label=spec["label"],
                zorder=4,
            )
            centroid_x = sum(pt[0] for pt in points) / 3.0
            centroid_y = sum(pt[1] for pt in points) / 3.0
            self.ax_cie.text(
                centroid_x,
                centroid_y,
                spec["label"],
                color=spec["color"],
                fontsize=8,
                ha="center",
                va="center",
                alpha=0.9,
                zorder=5,
                bbox={"facecolor": (1.0, 1.0, 1.0, 0.45), "edgecolor": "none", "pad": 1.5},
            )

    def _draw_measured_white_crosshair(self, white_xy):
        x, y = white_xy
        self.ax_cie.axvline(x=x, color="#222222", linewidth=1.0, linestyle=":", alpha=0.7, zorder=6)
        self.ax_cie.axhline(y=y, color="#222222", linewidth=1.0, linestyle=":", alpha=0.7, zorder=6)
        self.ax_cie.scatter(
            [x],
            [y],
            s=90,
            color="#ffffff",
            edgecolors="#111111",
            linewidths=1.2,
            marker="+",
            zorder=12,
            label="Measured white",
        )
        self.ax_cie.text(
            x + 0.01,
            y - 0.012,
            f"W Δ target ref",
            fontsize=8,
            color="#111111",
            ha="left",
            va="top",
            zorder=12,
            bbox={"facecolor": (1.0, 1.0, 1.0, 0.55), "edgecolor": "none", "pad": 1.2},
        )

    def _draw_cie_white_points(self):
        if not bool(self.cie_show_white_points_var.get()):
            return
        for spec in CIE_WHITE_POINTS.values():
            x, y = spec["xy"]
            self.ax_cie.scatter(
                [x],
                [y],
                s=64,
                color=spec["color"],
                edgecolors=spec["edge"],
                linewidths=1.0,
                marker="X",
                alpha=0.95,
                zorder=7,
                label=spec["label"],
            )
            self.ax_cie.text(
                x + 0.008,
                y + 0.008,
                spec["label"],
                fontsize=8,
                color=spec["edge"],
                ha="left",
                va="bottom",
                zorder=8,
                bbox={"facecolor": (1.0, 1.0, 1.0, 0.5), "edgecolor": "none", "pad": 1.2},
            )

    def _polygon_area(self, points):
        if len(points) < 3:
            return 0.0
        area = 0.0
        for idx, (x1, y1) in enumerate(points):
            x2, y2 = points[(idx + 1) % len(points)]
            area += (x1 * y2) - (x2 * y1)
        return abs(area) * 0.5

    def _inside_half_plane(self, point, edge_start, edge_end):
        return ((edge_end[0] - edge_start[0]) * (point[1] - edge_start[1])) - ((edge_end[1] - edge_start[1]) * (point[0] - edge_start[0])) >= -1e-9

    def _segment_intersection(self, p1, p2, q1, q2):
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = q1
        x4, y4 = q2
        denominator = ((x1 - x2) * (y3 - y4)) - ((y1 - y2) * (x3 - x4))
        if abs(denominator) < 1e-12:
            return p2
        det1 = (x1 * y2) - (y1 * x2)
        det2 = (x3 * y4) - (y3 * x4)
        x = ((det1 * (x3 - x4)) - ((x1 - x2) * det2)) / denominator
        y = ((det1 * (y3 - y4)) - ((y1 - y2) * det2)) / denominator
        return (x, y)

    def _clip_polygon(self, subject, clip_polygon):
        output = list(subject)
        if len(output) < 3:
            return []
        clip_area_sign = 0.0
        for idx, (x1, y1) in enumerate(clip_polygon):
            x2, y2 = clip_polygon[(idx + 1) % len(clip_polygon)]
            clip_area_sign += (x1 * y2) - (x2 * y1)
        clip_points = list(clip_polygon)
        if clip_area_sign < 0.0:
            clip_points = list(reversed(clip_points))

        for idx, clip_end in enumerate(clip_points):
            clip_start = clip_points[idx - 1]
            input_list = output
            output = []
            if not input_list:
                break
            s = input_list[-1]
            for e in input_list:
                e_inside = self._inside_half_plane(e, clip_start, clip_end)
                s_inside = self._inside_half_plane(s, clip_start, clip_end)
                if e_inside:
                    if not s_inside:
                        output.append(self._segment_intersection(s, e, clip_start, clip_end))
                    output.append(e)
                elif s_inside:
                    output.append(self._segment_intersection(s, e, clip_start, clip_end))
                s = e
        return output

    def _distance_xy(self, p1, p2):
        return math.sqrt(((p1[0] - p2[0]) ** 2) + ((p1[1] - p2[1]) ** 2))

    def _format_xy(self, point):
        return f"({point[0]:.4f}, {point[1]:.4f})"

    def _format_cie_coverage_stats(self, centroids):
        if not all(ch in centroids for ch in ("R", "G", "B")):
            return []
        measured = [centroids["R"], centroids["G"], centroids["B"]]
        measured_area = self._polygon_area(measured)
        lines = [f"Measured RGB area: {measured_area:.4f} xy^2"]
        for key, spec in CIE_GAMUT_OVERLAYS.items():
            if not bool(self.cie_overlay_vars[key].get()):
                continue
            reference = list(spec["points"])
            reference_area = self._polygon_area(reference)
            if reference_area <= 0.0:
                continue
            intersection = self._clip_polygon(measured, reference)
            intersection_area = self._polygon_area(intersection)
            relative_area_pct = (measured_area / reference_area) * 100.0
            inside_reference_pct = (intersection_area / reference_area) * 100.0
            inside_measured_pct = (intersection_area / measured_area) * 100.0 if measured_area > 0.0 else 0.0
            ref_r, ref_g, ref_b = reference
            delta_r = self._distance_xy(centroids["R"], ref_r)
            delta_g = self._distance_xy(centroids["G"], ref_g)
            delta_b = self._distance_xy(centroids["B"], ref_b)
            lines.append(f"{spec['label']}")
            lines.append(f"  inside ref gamut: {inside_reference_pct:.1f}%")
            lines.append(f"  relative area: {relative_area_pct:.1f}%")
            lines.append(f"  measured inside ref: {inside_measured_pct:.1f}%")
            lines.append(f"  primary deltas: R {delta_r:.4f}, G {delta_g:.4f}, B {delta_b:.4f}")
        return lines

    def _update_cie_info_panel(self, centroids):
        if not hasattr(self, "cie_info_text"):
            return
        lines = ["CIE Coverage Summary", "====================", ""]
        for ch in CHANNELS:
            if ch in centroids:
                lines.append(f"{ch} centroid: {self._format_xy(centroids[ch])}")
        if all(ch in centroids for ch in ("R", "G", "B")):
            measured = [centroids["R"], centroids["G"], centroids["B"]]
            measured_area = self._polygon_area(measured)
            lines += ["", f"Measured RGB triangle area: {measured_area:.4f} xy^2"]
        if "W" in centroids:
            lines += ["", "White point distances:"]
            d65_xy = CIE_WHITE_POINTS["d65"]["xy"]
            delta_x = centroids["W"][0] - d65_xy[0]
            delta_y = centroids["W"][1] - d65_xy[1]
            delta_xy = self._distance_xy(centroids["W"], d65_xy)
            lines.append(f"  W -> D65 Δx: {delta_x:+.4f}")
            lines.append(f"  W -> D65 Δy: {delta_y:+.4f}")
            lines.append(f"  W -> D65 Δxy: {delta_xy:.4f}")
            for spec in CIE_WHITE_POINTS.values():
                delta = self._distance_xy(centroids["W"], spec["xy"])
                lines.append(f"  W -> {spec['label']}: {delta:.4f}")
        coverage_lines = self._format_cie_coverage_stats(centroids)
        if coverage_lines:
            lines += [""] + coverage_lines
        elif not centroids:
            lines += ["No centroid data available yet."]
        self.cie_info_text.delete("1.0", "end")
        self.cie_info_text.insert("end", "\n".join(lines))

    def _load_capture_xy_points(self, measure_dir, channel_filter=None):
        pts = []
        for p in sorted(Path(measure_dir).glob("single_measure_*.json")):
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
                render = obj.get("render", {}); meas = obj.get("measurement", {})
                x = meas.get("x"); y = meas.get("y"); Y = meas.get("Y")
                if x is None or y is None or Y is None: continue
                upper = {ch: int(render.get(f"upper_{ch.lower()}", render.get(ch.lower(), 0)) or 0) for ch in CHANNELS}
                lower = {ch: int(render.get(f"lower_{ch.lower()}", 0) or 0) for ch in CHANNELS}
                bfis = {ch: int(render.get(f"bfi_{ch.lower()}", 0) or 0) for ch in CHANNELS}
                active = [ch for ch in CHANNELS if upper[ch] > 0 or lower[ch] > 0 or bfis[ch] > 0]
                if len(active) != 1: continue
                ch = active[0]
                if channel_filter and ch != channel_filter: continue
                pts.append({"x": float(x), "y": float(y), "Y": float(Y), "channel": ch})
            except Exception:
                pass
        for p in sorted(Path(measure_dir).glob("plan_capture_*.csv")):
            try:
                with open(p, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if str(row.get("ok", "")).strip() != "True": continue
                        if row.get("x") in (None, "") or row.get("y") in (None, "") or row.get("Y") in (None, ""): continue
                        upper = {ch: int(row.get(f"upper_{ch.lower()}", row.get(ch.lower(), 0)) or 0) for ch in CHANNELS}
                        lower = {ch: int(row.get(f"lower_{ch.lower()}", 0) or 0) for ch in CHANNELS}
                        bfis = {ch: int(row.get(f"bfi_{ch.lower()}", 0) or 0) for ch in CHANNELS}
                        active = [ch for ch in CHANNELS if upper[ch] > 0 or lower[ch] > 0 or bfis[ch] > 0]
                        if len(active) != 1: continue
                        ch = active[0]
                        if channel_filter and ch != channel_filter: continue
                        pts.append({"x": float(row["x"]), "y": float(row["y"]), "Y": float(row["Y"]), "channel": ch})
            except Exception:
                pass
        return pts

    def refresh_preview(self):
        self._save_config()
        self._preview_refresh_token += 1
        token = self._preview_refresh_token
        out_dir = Path(self.build_out_dir_var.get()).expanduser()
        measure_dir = Path(self.measure_dir_var.get()).expanduser()
        channel = self.preview_channel_var.get().upper()
        self._preview_refresh_state = {
            "token": token,
            "out_dir": out_dir,
            "measure_dir": measure_dir,
            "channel": channel,
            "capture_preview_cache_key": self._measure_dir_cache_key(measure_dir),
        }
        self.ladder_text.delete("1.0", "end")
        self.ladder_text.insert("end", f"Refreshing preview for {channel}...\n")
        self._set_refresh_progress(token, f"Refreshing {channel} preview: starting", 0.02)
        self.root.after(1, lambda: self._refresh_preview_load_phase(token))

    def _refresh_preview_load_phase(self, token):
        if token != self._preview_refresh_token:
            return
        state = self._preview_refresh_state
        channel_lower = state["channel"].lower()
        out_dir = state["out_dir"]
        state["lut_path"] = out_dir / f"{channel_lower}_lut256.csv"
        state["points_path"] = out_dir / f"{channel_lower}_measured_points.csv"
        state["ladder_path"] = out_dir / f"{channel_lower}_temporal_ladder.json"
        state["mono_path"] = out_dir / f"{channel_lower}_monotonic_ladder.json"
        state["ladder"] = self._load_json_list(state["ladder_path"])
        state["monotonic"] = self._load_json_list(state["mono_path"])
        self._set_refresh_progress(
            token,
            f"Refreshing {state['channel']} preview: loaded ladder data ({len(state['ladder'])} ladder, {len(state['monotonic'])} monotonic)",
            0.08,
        )
        self._refresh_preview_render_curve(token)

    def _refresh_preview_render_curve(self, token):
        if token != self._preview_refresh_token:
            return
        state = self._preview_refresh_state
        self.ax_curve.clear()
        plotted = False
        if state["lut_path"].exists():
            try:
                xs, ys = self._load_curve_csv(state["lut_path"])
                self.ax_curve.plot(xs, ys, label="lut256")
                plotted = True
            except Exception as exc:
                self.log_line(f"Failed to load LUT curve: {exc}")
        if state["points_path"].exists():
            try:
                xs, ys = self._load_curve_csv(state["points_path"])
                self.ax_curve.scatter(xs, ys, label="measured points", s=16)
                plotted = True
            except Exception as exc:
                self.log_line(f"Failed to load measured points: {exc}")
        self.ax_curve.set_title(f"{state['channel']} channel curve")
        self.ax_curve.set_xlabel("value")
        self.ax_curve.set_ylabel("normalized output")
        self.ax_curve.grid(True)
        state["curve_has_plotted"] = plotted
        self.canvas_curve.draw_idle()
        if not state["ladder"]:
            if plotted:
                self.ax_curve.legend()
                self.canvas_curve.draw_idle()
            self.root.after(1, lambda: self._refresh_preview_prepare_cie_phase(token))
            return
        self._set_refresh_progress(token, f"Refreshing {state['channel']} preview: curve 0/{len(state['ladder'])}", 0.08)
        self.root.after(1, lambda: self._refresh_preview_render_curve_batches(token, 0))

    def _refresh_preview_render_curve_batches(self, token, offset):
        if token != self._preview_refresh_token:
            return
        state = self._preview_refresh_state
        ladder = state["ladder"]
        batch = ladder[offset:offset + PREVIEW_PLOT_BATCH_POINTS]
        if batch:
            xs = [float(entry["value"]) + (float(entry["bfi"]) * 0.35) for entry in batch]
            ys = [float(entry.get("normalized_output", float(entry["output_q16"]) / 65535.0)) for entry in batch]
            self.ax_curve.scatter(xs, ys, label=("ladder states" if offset == 0 else None), s=10, alpha=0.25, color="tab:orange")
            state["curve_has_plotted"] = True
            self.canvas_curve.draw_idle()
        completed = min(len(ladder), offset + len(batch))
        fraction = 0.08 + (0.24 * (completed / float(max(1, len(ladder)))))
        self._set_refresh_progress(token, f"Refreshing {state['channel']} preview: curve {completed}/{len(ladder)}", fraction)
        if completed < len(ladder):
            self.root.after(1, lambda: self._refresh_preview_render_curve_batches(token, completed))
            return
        if state.get("curve_has_plotted"):
            self.ax_curve.legend()
            self.canvas_curve.draw_idle()
        self.root.after(1, lambda: self._refresh_preview_prepare_cie_phase(token))

    def _refresh_preview_prepare_cie_phase(self, token):
        if token != self._preview_refresh_token:
            return
        self.ax_cie.clear()
        self.ax_cie.set_title("CIE 1931 xy preview")
        self.ax_cie.set_xlabel("x")
        self.ax_cie.set_ylabel("y")
        self.ax_cie.set_xlim(0.0, 0.8)
        self.ax_cie.set_ylim(0.0, 0.9)
        if self.cie_bg_path.exists():
            try:
                img = mpimg.imread(self.cie_bg_path)
                self.ax_cie.imshow(img, extent=(0.0, 0.8, 0.0, 0.9), origin="lower")
            except Exception as exc:
                self.log_line(f"Failed to load CIE background: {exc}")
        self.ax_cie.set_aspect("equal", adjustable="box")
        self.ax_cie.grid(True, alpha=0.25)
        self._draw_cie_gamut_overlays()
        self._draw_cie_white_points()
        state = self._preview_refresh_state
        output_preview = self._load_output_xy_preview_buckets(state["out_dir"])
        if output_preview:
            state["cie_points_by_channel"] = {channel: list(output_preview[channel]["points"]) for channel in CHANNELS}
            state["cie_centroids"] = {
                channel: (bucket["sum_x"] / bucket["count"], bucket["sum_y"] / bucket["count"])
                for channel, bucket in output_preview.items()
                if int(bucket["count"]) > 0
            }
            state["cie_total_points"] = sum(len(points) for points in state["cie_points_by_channel"].values())
            self._set_refresh_progress(
                token,
                f"Refreshing {state['channel']} preview: CIE representative sample 0/{state['cie_total_points']}",
                0.32,
            )
            self.root.after(1, lambda: self._refresh_preview_render_cie(token, 0, 0))
            return
        cached_preview = self._preview_capture_scan_cache.get(state["capture_preview_cache_key"])
        if cached_preview is not None:
            state["capture_preview"] = cached_preview
            state["cie_points_by_channel"] = {channel: list(cached_preview[channel]["points"]) for channel in CHANNELS}
            state["cie_centroids"] = {
                channel: (bucket["sum_x"] / bucket["count"], bucket["sum_y"] / bucket["count"])
                for channel, bucket in cached_preview.items()
                if int(bucket["count"]) > 0
            }
            state["cie_total_points"] = sum(len(points) for points in state["cie_points_by_channel"].values())
            self._set_refresh_progress(
                token,
                f"Refreshing {state['channel']} preview: CIE representative sample 0/{state['cie_total_points']}",
                0.48,
            )
            self.root.after(1, lambda: self._refresh_preview_render_cie(token, 0, 0))
            return
        self._begin_capture_preview_scan(state)
        self.root.after(1, lambda: self._preview_capture_scan_step(token))

    def _refresh_preview_render_cie(self, token, channel_index, offset):
        if token != self._preview_refresh_token:
            return
        state = self._preview_refresh_state
        colors = {"R": "#ff0000fc", "G": "#00ff00", "B": "#0066f5", "W": "#ffffff"}
        total_points = max(1, int(state.get("cie_total_points", 0)))
        rendered_points = int(state.get("cie_rendered_points", 0))
        if channel_index >= len(CHANNELS):
            centroids = state.get("cie_centroids", {})
            if "W" in centroids:
                self._draw_measured_white_crosshair(centroids["W"])
            if all(channel in centroids for channel in ["R", "G", "B"]):
                tri_x = [centroids["R"][0], centroids["G"][0], centroids["B"][0], centroids["R"][0]]
                tri_y = [centroids["R"][1], centroids["G"][1], centroids["B"][1], centroids["R"][1]]
                self.ax_cie.plot(tri_x, tri_y, color="black", linewidth=2, label="LED gamut")
            self._update_cie_info_panel(centroids)
            if centroids:
                self.ax_cie.legend()
            self.canvas_cie.draw_idle()
            self.root.after(1, lambda: self._refresh_preview_render_density(token))
            return

        channel = CHANNELS[channel_index]
        points = (state.get("cie_points_by_channel") or {}).get(channel, [])
        if not points:
            self.root.after(1, lambda: self._refresh_preview_render_cie(token, channel_index + 1, 0))
            return

        batch = points[offset:offset + PREVIEW_CIE_PLOT_BATCH_POINTS]
        xs = [point["x"] for point in batch]
        ys = [point["y"] for point in batch]
        sizes = [max(10.0, min(80.0, float(point["Y"]) / 10.0)) for point in batch]
        self.ax_cie.scatter(
            xs,
            ys,
            s=sizes,
            color=colors[channel],
            label=(f"{channel} captures" if offset == 0 else None),
            alpha=0.85,
            linewidths=0.0,
            marker="o",
            zorder=6,
        )
        rendered_points += len(batch)
        state["cie_rendered_points"] = rendered_points
        fraction = 0.32 + (0.36 * (rendered_points / float(total_points)))
        self._set_refresh_progress(token, f"Refreshing {state['channel']} preview: CIE {rendered_points}/{total_points}", fraction)
        self.canvas_cie.draw_idle()
        completed = offset + len(batch)
        if completed < len(points):
            self.root.after(1, lambda: self._refresh_preview_render_cie(token, channel_index, completed))
            return

        centroids = state.get("cie_centroids", {})
        if channel in centroids:
            cx, cy = centroids[channel]
            self.ax_cie.scatter([cx], [cy], s=120, color=colors[channel], edgecolors="black", linewidths=1.2, marker="o", zorder=10)
            self.ax_cie.text(
                cx + 0.01,
                cy + 0.01,
                f"{channel} {cx:.3f}, {cy:.3f}",
                fontsize=8,
                color=("#111111" if channel == "W" else colors[channel]),
                ha="left",
                va="bottom",
                zorder=11,
                bbox={"facecolor": (1.0, 1.0, 1.0, 0.55), "edgecolor": "none", "pad": 1.2},
            )
        self.canvas_cie.draw_idle()
        self.root.after(1, lambda: self._refresh_preview_render_cie(token, channel_index + 1, 0))

    def _refresh_preview_render_density(self, token):
        if token != self._preview_refresh_token:
            return
        state = self._preview_refresh_state
        self.figure_density.clear()
        self.ax_density = self.figure_density.add_subplot(111)
        self.ax_density.set_title(f"{state['channel']} ladder density")
        self.ax_density.set_xlabel("value")
        self.ax_density.set_ylabel("normalized output")
        self.ax_density.grid(True, alpha=0.25)
        state["density_rendered"] = 0
        state["density_total"] = len(state["ladder"])
        state["density_max_bfi"] = max([int(entry.get("bfi", 0)) for entry in state["ladder"]], default=0)
        if not state["ladder"]:
            self.figure_density.tight_layout()
            self.canvas_density.draw_idle()
            self.root.after(1, lambda: self._refresh_preview_render_monotonic(token))
            return
        self.root.after(1, lambda: self._refresh_preview_render_density_batches(token, 0))

    def _refresh_preview_render_density_batches(self, token, offset):
        if token != self._preview_refresh_token:
            return
        state = self._preview_refresh_state
        ladder = state["ladder"]
        batch = ladder[offset:offset + PREVIEW_PLOT_BATCH_POINTS]
        if batch:
            xs = [float(entry["value"]) for entry in batch]
            ys = [float(entry.get("normalized_output", float(entry["output_q16"]) / 65535.0)) for entry in batch]
            cs = [int(entry["bfi"]) for entry in batch]
            scatter = self.ax_density.scatter(xs, ys, c=cs, cmap="plasma", vmin=0, vmax=max(1, state["density_max_bfi"]), s=16, alpha=0.8)
            if offset == 0:
                colorbar = self.figure_density.colorbar(scatter, ax=self.ax_density)
                colorbar.set_label("BFI")
            self.figure_density.tight_layout()
            self.canvas_density.draw_idle()
        completed = min(len(ladder), offset + len(batch))
        fraction = 0.68 + (0.16 * (completed / float(max(1, len(ladder)))))
        self._set_refresh_progress(token, f"Refreshing {state['channel']} preview: density {completed}/{len(ladder)}", fraction)
        if completed < len(ladder):
            self.root.after(1, lambda: self._refresh_preview_render_density_batches(token, completed))
            return
        self.root.after(1, lambda: self._refresh_preview_render_monotonic(token))

    def _refresh_preview_render_monotonic(self, token):
        if token != self._preview_refresh_token:
            return
        state = self._preview_refresh_state
        monotonic = state["monotonic"]
        self.figure_mono.clear()
        self.ax_mono = self.figure_mono.add_subplot(111)
        self.ax_mono.set_title(f"{state['channel']} monotonic ladder")
        self.ax_mono.set_xlabel("ladder rank")
        self.ax_mono.set_ylabel("normalized output")
        self.ax_mono.grid(True, alpha=0.25)
        if not monotonic:
            self.figure_mono.tight_layout()
            self.canvas_mono.draw_idle()
            self._refresh_preview_update_ladder_text(token)
            self.root.after(1, lambda: self._refresh_preview_finish(token))
            return
        state["mono_max_bfi"] = max([int(entry.get("bfi", 0)) for entry in monotonic], default=0)
        self.root.after(1, lambda: self._refresh_preview_render_monotonic_batches(token, 0))

    def _refresh_preview_render_monotonic_batches(self, token, offset):
        if token != self._preview_refresh_token:
            return
        state = self._preview_refresh_state
        monotonic = state["monotonic"]
        batch = monotonic[offset:offset + PREVIEW_PLOT_BATCH_POINTS]
        if batch:
            xs = [int(entry["rank"]) for entry in batch]
            ys = [float(entry["normalized_output"]) for entry in batch]
            cs = [int(entry["bfi"]) for entry in batch]
            scatter = self.ax_mono.scatter(xs, ys, c=cs, cmap="plasma", vmin=0, vmax=max(1, state["mono_max_bfi"]), s=18, alpha=0.85)
            if offset == 0:
                colorbar = self.figure_mono.colorbar(scatter, ax=self.ax_mono)
                colorbar.set_label("BFI")
            self.figure_mono.tight_layout()
            self.canvas_mono.draw_idle()
        completed = min(len(monotonic), offset + len(batch))
        fraction = 0.84 + (0.10 * (completed / float(max(1, len(monotonic)))))
        self._set_refresh_progress(token, f"Refreshing {state['channel']} preview: monotonic {completed}/{len(monotonic)}", fraction)
        if completed < len(monotonic):
            self.root.after(1, lambda: self._refresh_preview_render_monotonic_batches(token, completed))
            return
        self._refresh_preview_update_ladder_text(token)
        self.root.after(1, lambda: self._refresh_preview_finish(token))

    def _refresh_preview_update_ladder_text(self, token):
        if token != self._preview_refresh_token:
            return
        state = self._preview_refresh_state
        monotonic = state["monotonic"]
        self.ladder_text.delete("1.0", "end")
        if monotonic:
            self.ladder_text.insert("end", "rank\tlower\tupper\tvalue\tbfi\toutput_q16\tnorm\tdelta\n")
            for entry in monotonic[:400]:
                self.ladder_text.insert(
                    "end",
                    f"{entry['rank']}\t{entry.get('lower_value', 0)}\t{entry.get('upper_value', entry.get('value', 0))}\t{entry['value']}\t{entry['bfi']}\t{entry['output_q16']}\t{entry['normalized_output']:.6f}\t{entry['delta_q16_from_prev']}\n",
                )
            if len(monotonic) > 400:
                self.ladder_text.insert("end", f"... ({len(monotonic)} monotonic states total)\n")
        elif state["ladder"]:
            self.ladder_text.insert("end", "lower\tupper\tvalue\tbfi\toutput_q16\tnorm\n")
            for entry in state["ladder"][:300]:
                norm = entry.get("normalized_output", float(entry["output_q16"]) / 65535.0)
                self.ladder_text.insert(
                    "end",
                    f"{entry.get('lower_value', 0)}\t{entry.get('upper_value', entry.get('value', 0))}\t{entry['value']}\t{entry['bfi']}\t{entry['output_q16']}\t{norm:.6f}\n",
                )
        else:
            self.ladder_text.insert("end", f"No ladder found:\n{state['ladder_path']}")

    def _refresh_preview_finish(self, token):
        if token != self._preview_refresh_token:
            return
        self.root.after(1, lambda: self._refresh_preview_finish_visuals(token))

    def _refresh_preview_finish_visuals(self, token):
        if token != self._preview_refresh_token:
            return
        self._set_refresh_progress(token, f"Refreshing {self.preview_channel_var.get().upper()} preview: calibration visuals", 0.97)
        self.refresh_calibration_visuals()
        self.root.after(1, lambda: self._refresh_preview_finish_transfer(token))

    def _refresh_preview_finish_transfer(self, token):
        if token != self._preview_refresh_token:
            return
        self._set_refresh_progress(token, f"Refreshing {self.preview_channel_var.get().upper()} preview: transfer curve", 0.985)
        self.refresh_transfer_curve()
        self.root.after(1, lambda: self._refresh_preview_finish_luma(token))

    def _refresh_preview_finish_luma(self, token):
        if token != self._preview_refresh_token:
            return
        self.refresh_luma_weights()
        self._set_refresh_progress(token, f"Preview refresh complete for {self.preview_channel_var.get().upper()}", 1.0)
        self.log_line(f"Preview refresh complete for {self.preview_channel_var.get().upper()}.")

    def _load_header_arrays(self, path_str):
        if not path_str: return {}
        p = Path(path_str)
        if not p.exists(): return {}
        return parse_header_arrays(p.read_text(encoding="utf-8", errors="ignore"))

    def _clamp01(self, x):
        x = float(x)
        return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)

    def _pq_eotf_norm(self, x):
        m1 = 2610.0 / 16384.0
        m2 = 2523.0 / 32.0
        c1 = 3424.0 / 4096.0
        c2 = 2413.0 / 128.0
        c3 = 2392.0 / 128.0

        x = self._clamp01(x)
        if x <= 0.0:
            return 0.0

        power = x ** (1.0 / m2)
        numerator = max(power - c1, 0.0)
        denominator = c2 - c3 * power
        if denominator <= 0.0:
            return 1.0
        return self._clamp01((numerator / denominator) ** (1.0 / m1))

    def _hlg_eotf_norm(self, x):
        a = 0.17883277
        b = 0.28466892
        c = 0.55991073

        x = self._clamp01(x)
        if x <= 0.5:
            return self._clamp01((x * x) / 3.0)
        return self._clamp01((math.exp((x - c) / a) + b) / 12.0)

    def _bt1886_eotf_norm(self, x, black_level=0.001):
        gamma = 2.4
        white_level = 1.0
        black_level = min(max(float(black_level), 0.0), white_level * 0.25)
        x = self._clamp01(x)

        if black_level <= 0.0:
            return self._clamp01(x ** gamma)

        white_root = white_level ** (1.0 / gamma)
        black_root = black_level ** (1.0 / gamma)
        denominator = white_root - black_root
        if denominator <= 0.0:
            return self._clamp01(x ** gamma)

        a = denominator ** gamma
        b = black_root / denominator
        luminance = a * ((x + b) ** gamma)
        normalized = (luminance - black_level) / (white_level - black_level)
        return self._clamp01(normalized)

    def _transfer_curve_uses_gamma(self, curve):
        return str(curve) in {"gamma", "toe-gamma"}

    def _get_transfer_curve_config(self, channel=None):
        if bool(self.transfer_per_channel_var.get()) and channel in CHANNELS:
            return {
                "curve": self.transfer_channel_curve_vars[channel].get(),
                "gamma": max(0.05, float(self.transfer_channel_gamma_vars[channel].get())),
                "shadow_lift": self._clamp01(self.transfer_channel_shadow_lift_vars[channel].get()),
                "shoulder": self._clamp01(self.transfer_channel_shoulder_vars[channel].get()),
            }
        return {
            "curve": self.transfer_curve_var.get(),
            "gamma": max(0.05, float(self.transfer_gamma_var.get())),
            "shadow_lift": self._clamp01(self.transfer_shadow_lift_var.get()),
            "shoulder": self._clamp01(self.transfer_shoulder_var.get()),
        }

    def _collect_transfer_channel_overrides(self):
        if not bool(self.transfer_per_channel_var.get()):
            return {}
        return {
            ch: self._get_transfer_curve_config(ch)
            for ch in CHANNELS
        }

    def _resolve_transfer_bucket_count(self):
        requested = max(0, int(self.transfer_bucket_count_var.get()))
        if requested >= 2:
            return requested
        derived = 2
        for ch in CHANNELS:
            derived = max(derived, len(self._load_monotonic_ladder_preview(ch)))
        return derived

    def _append_transfer_curve_args(self, args):
        args += [
            "--bucket-count", str(self.transfer_bucket_count_var.get()),
            "--curve", self.transfer_curve_var.get(),
            "--gamma", str(self.transfer_gamma_var.get()),
            "--shadow-lift", str(self.transfer_shadow_lift_var.get()),
            "--shoulder", str(self.transfer_shoulder_var.get()),
            "--selection", self.transfer_selection_var.get(),
        ]
        peak_nits_override = self._parse_optional_float(self.transfer_peak_nits_override_var.get())
        if peak_nits_override is not None and float(peak_nits_override) > 0.0:
            args += ["--peak-nits-override", str(float(peak_nits_override))]
        transfer_nit_cap = self._parse_optional_float(self.transfer_nit_cap_var.get())
        if transfer_nit_cap is not None and float(transfer_nit_cap) > 0.0:
            args += ["--nit-cap", str(float(transfer_nit_cap))]
        if bool(self.transfer_exclude_white_var.get()):
            args += ["--exclude-white"]
        if bool(self.transfer_per_channel_var.get()):
            for ch in CHANNELS:
                suffix = ch.lower()
                cfg = self._get_transfer_curve_config(ch)
                args += [f"--curve-{suffix}", cfg["curve"]]
                args += [f"--gamma-{suffix}", str(cfg["gamma"])]
                args += [f"--shadow-lift-{suffix}", str(cfg["shadow_lift"])]
                args += [f"--shoulder-{suffix}", str(cfg["shoulder"])]

    def _update_transfer_curve_controls(self, *_args):
        curve = self.transfer_curve_var.get()
        gamma_active = self._transfer_curve_uses_gamma(curve)
        note = "Gamma only affects Gamma and Toe Gamma."

        if curve == "pq":
            note = "PQ uses ST 2084. Gamma is ignored for this preset."
        elif curve == "hlg":
            note = "HLG uses the normalized Rec.2100 / ARIB STD-B67 curve. Gamma is ignored for this preset."
        elif curve == "bt1886":
            note = "BT.1886 uses a normalized black-compensated preset. Gamma is ignored for this preset."
        elif curve == "linear":
            note = "Linear maps input directly to output. Gamma is ignored for this preset."
        elif curve == "srgb-ish":
            note = "sRGB-ish uses its piecewise transfer approximation. Gamma is ignored for this preset."

        self.transfer_curve_note_var.set(note)
        if hasattr(self, "transfer_gamma_entry"):
            self.transfer_gamma_entry.configure(state=("normal" if gamma_active else "disabled"))
        if hasattr(self, "transfer_channel_controls"):
            if bool(self.transfer_per_channel_var.get()):
                self.transfer_channel_controls.pack(fill="x", padx=8, pady=(0, 4), before=self.canvas_transfer.get_tk_widget())
            else:
                self.transfer_channel_controls.pack_forget()
        for ch in CHANNELS:
            gamma_entry = getattr(self, f"transfer_gamma_entry_{ch}", None)
            if gamma_entry is not None:
                channel_curve = self.transfer_channel_curve_vars[ch].get()
                gamma_entry.configure(state=("normal" if self._transfer_curve_uses_gamma(channel_curve) else "disabled"))

    def _apply_transfer_curve_norm(self, x):
        cfg = self._get_transfer_curve_config(self.preview_channel_var.get())
        x = self._clamp01(x)
        curve = cfg["curve"]
        gamma = cfg["gamma"]
        shadow_lift = cfg["shadow_lift"]
        shoulder = cfg["shoulder"]

        if curve == "linear":
            y = x
        elif curve == "gamma":
            y = x ** gamma
        elif curve == "pq":
            y = self._pq_eotf_norm(x)
        elif curve == "hlg":
            y = self._hlg_eotf_norm(x)
        elif curve == "bt1886":
            y = self._bt1886_eotf_norm(x)
        elif curve == "srgb-ish":
            if x <= 0.04045:
                y = x / 12.92
            else:
                y = ((x + 0.055) / 1.055) ** 2.4
        elif curve == "toe-gamma":
            toe = x * x * (3.0 - 2.0 * x)
            y = toe ** gamma
        else:
            y = x ** gamma

        if shadow_lift > 0.0:
            y = (1.0 - shadow_lift) * y + shadow_lift * math.sqrt(max(0.0, y))
        if shoulder > 0.0:
            y = 1.0 - ((1.0 - y) ** (1.0 / (1.0 + shoulder)))
        return self._clamp01(y)

    def _load_monotonic_ladder_preview(self, channel):
        p = Path(self.build_out_dir_var.get()).expanduser() / f"{channel.lower()}_monotonic_ladder.json"
        if not p.exists():
            return []
        try:
            arr = self._load_cached_json(p)
            return sorted(arr, key=lambda e: int(e["output_q16"]))
        except Exception as exc:
            self.log_line(f"Failed to load monotonic ladder: {exc}")
            return []

    def _load_lut_summary_preview(self):
        summary_path = Path(self.build_out_dir_var.get()).expanduser() / "lut_summary.json"
        if not summary_path.exists():
            return {}
        try:
            data = self._load_cached_json(summary_path)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            self.log_line(f"Failed to load LUT summary: {exc}")
            return {}

    def _estimate_peak_nits_from_measurements(self, channel):
        channel = str(channel or "").upper()
        measure_dir = Path(self.measure_dir_var.get()).expanduser()
        peak_nits = None

        for p in sorted(measure_dir.glob("single_measure_*.json")):
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
                render = obj.get("render", {})
                measurement = obj.get("measurement", {})
                y_val = measurement.get("Y")
                if y_val in (None, ""):
                    continue
                vals = {ch: int(render.get(ch.lower(), 0)) for ch in CHANNELS}
                bfis = {ch: int(render.get(f"bfi_{ch.lower()}", 0)) for ch in CHANNELS}
                active = [(ch, vals[ch], bfis[ch]) for ch in CHANNELS if vals[ch] > 0]
                if len(active) != 1:
                    continue
                active_channel, _value, bfi = active[0]
                if active_channel != channel:
                    continue
                estimated_nits = float(y_val) * float(int(bfi) + 1)
                if peak_nits is None or estimated_nits > peak_nits:
                    peak_nits = estimated_nits
            except Exception:
                continue

        for p in sorted(measure_dir.glob("plan_capture_*.csv")):
            try:
                with open(p, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if str(row.get("ok", "")).strip() != "True" or row.get("Y") in (None, ""):
                            continue
                        vals = {ch: int(row.get(ch.lower(), 0)) for ch in CHANNELS}
                        bfis = {ch: int(row.get(f"bfi_{ch.lower()}", 0)) for ch in CHANNELS}
                        active = [(ch, vals[ch], bfis[ch]) for ch in CHANNELS if vals[ch] > 0]
                        if len(active) != 1:
                            continue
                        active_channel, _value, bfi = active[0]
                        if active_channel != channel:
                            continue
                        estimated_nits = float(row["Y"]) * float(int(bfi) + 1)
                        if peak_nits is None or estimated_nits > peak_nits:
                            peak_nits = estimated_nits
            except Exception:
                continue

        return peak_nits

    def _resolve_transfer_peak_nits(self, channel):
        override_nits = self._parse_optional_float(self.transfer_peak_nits_override_var.get())
        if override_nits is not None and float(override_nits) > 0.0:
            return float(override_nits), "override"

        summary = self._load_lut_summary_preview()
        channel_summary = summary.get("channels", {}).get(str(channel or "").upper(), {})
        peak_nits = channel_summary.get("max_estimated_nobfi_Y")
        try:
            peak_nits = float(peak_nits)
            if peak_nits > 0.0:
                return peak_nits, "lut summary"
        except Exception:
            pass

        peak_nits = self._estimate_peak_nits_from_measurements(channel)
        if peak_nits is not None and float(peak_nits) > 0.0:
            return float(peak_nits), "captures"

        return 100.0, "fallback"

    def _resolve_transfer_peak_metadata(self, exclude_white: bool = False):
        active_channels = [ch for ch in CHANNELS if not (exclude_white and ch == "W")]
        override_nits = self._parse_optional_float(self.transfer_peak_nits_override_var.get())
        if override_nits is not None and float(override_nits) > 0.0:
            reference_peak_nits = float(override_nits)
            source = "override"
            channel_peaks = {ch: float(reference_peak_nits) for ch in CHANNELS}
        else:
            summary = self._load_lut_summary_preview()
            channel_peaks = {}
            for ch in CHANNELS:
                raw_peak = (summary.get("channels", {}).get(ch, {}) or {}).get("max_estimated_nobfi_Y")
                try:
                    peak = float(raw_peak)
                except Exception:
                    peak = 0.0
                if peak > 0.0:
                    channel_peaks[ch] = peak
            active_peaks = {ch: v for ch, v in channel_peaks.items() if ch in active_channels}
            if active_peaks:
                reference_peak_nits = max(float(v) for v in active_peaks.values())
                source = "lut summary"
            elif channel_peaks:
                reference_peak_nits = max(float(v) for v in channel_peaks.values())
                source = "lut summary"
            else:
                reference_peak_nits = 100.0
                source = "fallback"
                channel_peaks = {ch: 100.0 for ch in CHANNELS}

        for ch in CHANNELS:
            channel_peaks.setdefault(ch, float(reference_peak_nits))

        brightest_channel = max(
            (ch for ch in active_channels if ch in channel_peaks),
            key=lambda name: float(channel_peaks[name]),
            default="R" if exclude_white else "W",
        ) if channel_peaks else ("R" if exclude_white else "W")
        return {
            "reference_peak_nits": float(reference_peak_nits),
            "source": str(source),
            "brightest_channel": str(brightest_channel),
            "channel_peak_nits": {ch: float(channel_peaks[ch]) for ch in CHANNELS},
        }

    def _choose_mono_state(self, ladder, target_q16):
        if not ladder:
            return {"value": 0, "bfi": 0, "output_q16": 0}
        selection = self.transfer_selection_var.get()
        target_q16 = int(max(0, min(65535, target_q16)))
        if selection == "nearest":
            return min(ladder, key=lambda e: abs(int(e["output_q16"]) - target_q16))
        best = ladder[0]
        for e in ladder:
            if int(e["output_q16"]) <= target_q16:
                best = e
            else:
                break
        return best

    def refresh_transfer_curve(self):
        self._save_config()
        exclude_white = bool(self.transfer_exclude_white_var.get())
        ch = self.preview_channel_var.get()
        if exclude_white and ch == "W":
            ch = "R"  # fall back to R when previewing with white excluded
        ladder = self._load_monotonic_ladder_preview(ch)
        buckets = self._resolve_transfer_bucket_count()
        peak_meta = self._resolve_transfer_peak_metadata(exclude_white=exclude_white)
        peak_nits = float(peak_meta["channel_peak_nits"].get(ch, peak_meta["reference_peak_nits"]))
        peak_source = peak_meta["source"]
        reference_peak_nits = float(peak_meta["reference_peak_nits"])
        brightest_channel = str(peak_meta["brightest_channel"])
        nit_cap = self._parse_optional_float(self.transfer_nit_cap_var.get())

        # When white is excluded and no explicit nit cap, auto-cap to brightest RGB.
        if exclude_white and nit_cap is None:
            rgb_peaks = [float(peak_meta["channel_peak_nits"].get(c, 0.0)) for c in ["R", "G", "B"]]
            max_rgb = max(rgb_peaks) if rgb_peaks else 0.0
            if max_rgb > 0.0:
                nit_cap = max_rgb

        nit_cap_enabled = nit_cap is not None and float(nit_cap) > 0.0 and reference_peak_nits > 0.0
        effective_nit_cap = min(float(nit_cap), float(reference_peak_nits)) if nit_cap_enabled else None
        normalized_limit = (float(effective_nit_cap) / float(reference_peak_nits)) if nit_cap_enabled else 1.0
        curve_cfg = self._get_transfer_curve_config(ch)

        xs = list(range(buckets))
        target_q16 = []
        achieved_q16 = []
        target_nits = []
        achieved_nits = []
        value = []
        bfi = []

        for i in xs:
            x = i / (buckets - 1)
            y = self._apply_transfer_curve_norm(x)
            if nit_cap_enabled:
                y = float(y) * float(normalized_limit)
            tq16 = int(round(y * 65535.0))
            state = self._choose_mono_state(ladder, tq16)
            target_q16.append(tq16)
            achieved_q16.append(int(state.get("output_q16", 0)))
            target_nits.append((float(tq16) / 65535.0) * peak_nits)
            achieved_nits.append((float(int(state.get("output_q16", 0))) / 65535.0) * peak_nits)
            value.append(int(state.get("value", 0)))
            bfi.append(int(state.get("bfi", 0)))

        self.ax_transfer_top.clear()
        self.ax_transfer_mid.clear()
        self.ax_transfer_bottom.clear()

        self.ax_transfer_top.plot(xs, target_q16, label="target curve Q16")
        self.ax_transfer_top.plot(xs, achieved_q16, label="achieved ladder Q16")
        self.ax_transfer_top.set_title(f"Transfer Curve Preview — {ch} ({curve_cfg['curve']})")
        self.ax_transfer_top.set_xlabel("Bucket")
        self.ax_transfer_top.set_ylabel("Q16")
        self.ax_transfer_top.grid(True, alpha=0.3)
        self.ax_transfer_top.legend()

        self.ax_transfer_mid.plot(xs, target_nits, label="target curve nits")
        self.ax_transfer_mid.plot(xs, achieved_nits, label="achieved ladder nits")
        mid_title = f"Absolute luminance (~{peak_nits:.2f} nits channel peak; reference {reference_peak_nits:.2f} from {peak_source}, brightest {brightest_channel})"
        if nit_cap_enabled:
            mid_title += f"\nNit cap active at {effective_nit_cap:.2f} nits"
            self.ax_transfer_mid.axhline(y=float(effective_nit_cap), color="#b22222", linewidth=1.2, linestyle="--", alpha=0.8, label="nit cap")
        self.ax_transfer_mid.set_title(mid_title)
        self.ax_transfer_mid.set_xlabel("Bucket")
        self.ax_transfer_mid.set_ylabel("Nits")
        self.ax_transfer_mid.grid(True, alpha=0.3)
        self.ax_transfer_mid.legend()

        self.ax_transfer_bottom.plot(xs, value, label="value")
        self.ax_transfer_bottom.plot(xs, bfi, label="BFI")
        self.ax_transfer_bottom.set_title("Selected runtime state")
        self.ax_transfer_bottom.set_xlabel("Bucket")
        self.ax_transfer_bottom.set_ylabel("Value / BFI")
        self.ax_transfer_bottom.grid(True, alpha=0.3)
        self.ax_transfer_bottom.legend()

        self.figure_transfer.tight_layout()
        self.canvas_transfer.draw()

    def export_transfer_json(self):
        out_path = Path(self.transfer_export_json_var.get()).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        args = [
            sys.executable, str(self.tool_path), "export-transfer-json",
            "--lut-dir", str(Path(self.build_out_dir_var.get()).expanduser()),
            "--out", str(out_path),
        ]
        self._append_transfer_curve_args(args)
        self.run_subprocess(args, on_success=lambda _s: messagebox.showinfo("Exported", f"Transfer JSON written to:\n{out_path}"))

    def export_transfer_header(self):
        out_path = Path(self.transfer_export_header_var.get()).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        args = [
            sys.executable, str(self.tool_path), "export-transfer-header",
            "--lut-dir", str(Path(self.build_out_dir_var.get()).expanduser()),
            "--out", str(out_path),
        ]
        self._append_transfer_curve_args(args)
        self.run_subprocess(args, on_success=lambda _s: messagebox.showinfo("Exported", f"Transfer header written to:\n{out_path}"))


    def _compute_luma_weights_preview(self):
        measure_dir = Path(self.measure_dir_var.get()).expanduser()
        bfi_source = self.luma_bfi_source_var.get()
        bfi_filter = None if str(bfi_source).lower() == "all" else int(bfi_source)
        method = self.luma_method_var.get()

        rows = []
        # Use integrated patch/teensy capture CSVs.
        for p in sorted(measure_dir.glob("plan_capture_*.csv")):
            try:
                with open(p, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if str(row.get("ok", "")).strip() != "True" or row.get("Y") in (None, ""):
                            continue
                        active = [(ch, int(row.get(ch.lower(), 0)), int(row.get(f"bfi_{ch.lower()}", 0))) for ch in CHANNELS if int(row.get(ch.lower(), 0)) > 0]
                        if len(active) != 1:
                            continue
                        ch, value, bfi = active[0]
                        if bfi_filter is not None and int(bfi) != bfi_filter:
                            continue
                        rows.append((ch, int(value), int(bfi), float(row["Y"])))
            except Exception as exc:
                self.log_line(f"Failed reading {p.name}: {exc}")

        per = {ch: [] for ch in CHANNELS}
        for ch, value, bfi, y in rows:
            per[ch].append(y)

        raw = {}
        stats = {}
        for ch in CHANNELS:
            vals = sorted(per[ch])
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

        total = sum(max(0.0, raw[ch]) for ch in CHANNELS)
        if total <= 0.0:
            floats = {ch: 0.0 for ch in CHANNELS}
            q16 = {ch: 0 for ch in CHANNELS}
        else:
            floats = {ch: max(0.0, raw[ch]) / total for ch in CHANNELS}
            q16 = {ch: int(round(floats[ch] * 65535.0)) for ch in CHANNELS}
            diff = 65535 - sum(q16.values())
            if diff != 0:
                target = max(CHANNELS, key=lambda ch: floats[ch])
                q16[target] = max(0, q16[target] + diff)

        return {
            "method": method,
            "bfi_source": str(bfi_source),
            "raw": raw,
            "normalized_float": floats,
            "normalized_q16": q16,
            "stats": stats,
            "measurement_count": len(rows),
        }

    def refresh_luma_weights(self):
        self._save_config()
        data = self._compute_luma_weights_preview()
        self.ax_luma.clear()
        xs = CHANNELS
        ys = [data["normalized_float"][ch] for ch in CHANNELS]
        self.ax_luma.bar(xs, ys)
        self.ax_luma.set_title(f"Luma Weights — method={data['method']} bfi={data['bfi_source']}")
        self.ax_luma.set_ylabel("Normalized weight")
        self.ax_luma.set_ylim(0.0, max(1.0, max(ys) * 1.15 if ys else 1.0))
        self.ax_luma.grid(True, axis="y", alpha=0.3)
        self.canvas_luma.draw()

        self.luma_text.delete("1.0", "end")
        self.luma_text.insert("end", json.dumps(data, indent=2))
        self.luma_text.insert("end", "\n\nC++ snippet\n===========\n")
        self.luma_text.insert("end", f"static constexpr float lumaWeightR = {data['normalized_float']['R']:.9f}f;\n")
        self.luma_text.insert("end", f"static constexpr float lumaWeightG = {data['normalized_float']['G']:.9f}f;\n")
        self.luma_text.insert("end", f"static constexpr float lumaWeightB = {data['normalized_float']['B']:.9f}f;\n")
        self.luma_text.insert("end", f"static constexpr float lumaWeightW = {data['normalized_float']['W']:.9f}f;\n\n")
        self.luma_text.insert("end", f"static constexpr uint16_t lumaWeightR_Q16 = {data['normalized_q16']['R']};\n")
        self.luma_text.insert("end", f"static constexpr uint16_t lumaWeightG_Q16 = {data['normalized_q16']['G']};\n")
        self.luma_text.insert("end", f"static constexpr uint16_t lumaWeightB_Q16 = {data['normalized_q16']['B']};\n")
        self.luma_text.insert("end", f"static constexpr uint16_t lumaWeightW_Q16 = {data['normalized_q16']['W']};\n")

    def export_luma_weights_json(self):
        out_path = Path(self.luma_export_json_var.get()).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        args = [
            sys.executable, str(self.tool_path), "export-luma-weights-json",
            "--measure-dir", str(Path(self.measure_dir_var.get()).expanduser()),
            "--out", str(out_path),
            "--method", self.luma_method_var.get(),
            "--bfi-source", str(self.luma_bfi_source_var.get()),
        ]
        self.run_subprocess(args, on_success=lambda _s: messagebox.showinfo("Exported", f"Luma weights JSON written to:\n{out_path}"))

    def export_luma_weights_header(self):
        out_path = Path(self.luma_export_header_var.get()).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        args = [
            sys.executable, str(self.tool_path), "export-luma-weights-header",
            "--measure-dir", str(Path(self.measure_dir_var.get()).expanduser()),
            "--out", str(out_path),
            "--method", self.luma_method_var.get(),
            "--bfi-source", str(self.luma_bfi_source_var.get()),
        ]
        self.run_subprocess(args, on_success=lambda _s: messagebox.showinfo("Exported", f"Luma weights header written to:\n{out_path}"))

    def export_runtime_json(self):
        out_dir = Path(self.export_out_var.get()).expanduser(); out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "temporal_runtime_luts.json"
        args = [sys.executable, str(self.tool_path), "export-runtime-json", "--lut-dir", str(Path(self.build_out_dir_var.get()).expanduser()), "--out", str(out_path)]
        self.run_subprocess(args, on_success=lambda _s: messagebox.showinfo("Exported", f"Runtime JSON written to:\n{out_path}"))

    def export_runtime_header(self):
        out_dir = Path(self.export_out_var.get()).expanduser(); out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "temporal_runtime_luts.h"
        args = [sys.executable, str(self.tool_path), "export-runtime-header", "--lut-dir", str(Path(self.build_out_dir_var.get()).expanduser()), "--out", str(out_path)]
        self.run_subprocess(args, on_success=lambda _s: messagebox.showinfo("Exported", f"Runtime header written to:\n{out_path}"))

    def export_solver_header(self):
        out_path = Path(self.solver_header_out_var.get()).expanduser(); out_path.parent.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, str(self.tool_path), "export-solver-header", "--lut-dir", str(Path(self.build_out_dir_var.get()).expanduser()), "--out", str(out_path), "--max-bfi", str(self.plan_max_bfi_var.get())]
        self.run_subprocess(args, on_success=lambda _s: messagebox.showinfo("Exported", f"Solver header written to:\n{out_path}"))

    def export_precomputed_solver_luts_header(self):
        out_path = Path(self.precomputed_solver_out_var.get()).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        max_bfi = max(0, self._safe_int(self.plan_max_bfi_var, 4))
        fixed_levels = max(1, max_bfi + 1)
        args = [
            sys.executable, str(self.tool_path), "export-precomputed-solver-luts-header",
            "--solver-header", str(Path(self.precomputed_solver_source_header_var.get()).expanduser()),
            "--out", str(out_path),
            "--max-bfi", str(max_bfi),
            "--solver-fixed-bfi-levels", str(fixed_levels),
            "--solver-lut-size", str(self.precomputed_solver_lut_size_var.get()),
            "--channels", str(self.precomputed_solver_channels_var.get()),
        ]
        self.run_subprocess(
            args,
            on_success=lambda _s: messagebox.showinfo("Exported", f"Precomputed solver LUT header written to:\n{out_path}"),
        )


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
