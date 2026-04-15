#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import generate_patch_batches_v2 as batch_lib


SCRIPT_DIR = Path(__file__).resolve().parent
PATCH_PLAN_DIR = SCRIPT_DIR / "patch_plans"
DEFAULT_OUT = PATCH_PLAN_DIR / "patch_plan_true16_comprehensive_v6.csv"
DEFAULT_SUMMARY = PATCH_PLAN_DIR / "patch_plan_true16_comprehensive_v6_summary.json"


@dataclass(frozen=True)
class ProfileConfig:
    ramp_values: tuple[int, ...]
    color_grid_levels: tuple[int, ...]
    color_grid_ratios: tuple[float, ...]
    neutral_rgb_bases: tuple[int, ...]
    neutral_white_levels: tuple[int, ...]
    chroma_rgb_bases: tuple[int, ...]
    chroma_white_levels: tuple[int, ...]
    white_dominant_rgb_bases: tuple[int, ...]
    white_dominant_white_levels: tuple[int, ...]
    floor_rgb_bases: tuple[int, ...]
    floor_white_levels: tuple[int, ...]
    peak_rgb_bases: tuple[int, ...]
    peak_white_levels: tuple[int, ...]
    dominance_rgb_bases: tuple[int, ...]
    dominance_white_levels: tuple[int, ...]
    offaxis_rgb_bases: tuple[int, ...]
    offaxis_white_levels: tuple[int, ...]
    impossible_rgb_bases: tuple[int, ...]
    impossible_white_ratios: tuple[float, ...]
    structured_impossible_rgb_bases: tuple[int, ...]
    structured_impossible_white_ratios: tuple[float, ...]


PROFILE_CONFIGS = {
    "meaningful": ProfileConfig(
        ramp_values=tuple(sorted({
            *(index * 257 for index in range(256)),
            1, 2, 4, 8, 16, 32, 64, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 3072, 4096,
            6144, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535,
        })),
        color_grid_levels=(4096, 8192, 16384, 24576, 32768, 49152, 65535),
        color_grid_ratios=(0.25, 0.50, 0.75, 1.00),
        neutral_rgb_bases=(0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 24576, 32768),
        neutral_white_levels=(0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        chroma_rgb_bases=(32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        chroma_white_levels=(0, 32, 64, 128, 256, 512, 1024, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        white_dominant_rgb_bases=(8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 12288, 16384),
        white_dominant_white_levels=(32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        floor_rgb_bases=(1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096),
        floor_white_levels=(0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192),
        peak_rgb_bases=(32768, 40960, 49152, 57344, 65535),
        peak_white_levels=(0, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        dominance_rgb_bases=(256, 512, 1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        dominance_white_levels=(0, 256, 512, 1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        offaxis_rgb_bases=(512, 1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        offaxis_white_levels=(0, 512, 1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        impossible_rgb_bases=(512, 1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        impossible_white_ratios=(0.06, 0.12, 0.30, 0.48, 0.72, 1.00, 1.35),
        structured_impossible_rgb_bases=(1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        structured_impossible_white_ratios=(0.20, 0.35, 0.55, 0.75, 0.95, 1.20, 1.45),
    ),
    "extended": ProfileConfig(
        ramp_values=tuple(sorted({
            *(index * 257 for index in range(256)),
            1, 2, 4, 8, 16, 32, 64, 96, 128, 160, 192, 224, 256, 320, 384, 448, 512, 640, 768,
            896, 1024, 1280, 1536, 1792, 2048, 2560, 3072, 3584, 4096, 5120,
            6144, 7168, 8192, 10240, 12288, 14336, 16384, 20480, 24576, 28672,
            32768, 36864, 40960, 45056, 49152, 53248, 57344, 61440, 65535,
        })),
        color_grid_levels=(2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        color_grid_ratios=(0.20, 0.40, 0.60, 0.80, 1.00),
        neutral_rgb_bases=(0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 768, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768),
        neutral_white_levels=(0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        chroma_rgb_bases=(8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        chroma_white_levels=(0, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        white_dominant_rgb_bases=(1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 12288, 16384, 24576),
        white_dominant_white_levels=(8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        floor_rgb_bases=(1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192),
        floor_white_levels=(0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192),
        peak_rgb_bases=(24576, 32768, 40960, 49152, 57344, 65535),
        peak_white_levels=(0, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        dominance_rgb_bases=(128, 256, 512, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        dominance_white_levels=(0, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        offaxis_rgb_bases=(256, 512, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        offaxis_white_levels=(0, 256, 512, 1024, 2048, 4096, 8192, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        impossible_rgb_bases=(256, 512, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        impossible_white_ratios=(0.06, 0.12, 0.24, 0.42, 0.60, 0.84, 1.10, 1.45),
        structured_impossible_rgb_bases=(512, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        structured_impossible_white_ratios=(0.18, 0.30, 0.45, 0.60, 0.80, 1.00, 1.25, 1.50),
    ),
    "capture": ProfileConfig(
        ramp_values=tuple(sorted({
            *(index * 257 for index in range(256)),
            1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 160, 192, 224, 256,
            320, 384, 448, 512, 640, 768, 896, 1024, 1280, 1536, 1792, 2048, 2560,
            3072, 3584, 4096, 5120, 6144, 7168, 8192, 10240, 12288, 14336, 16384,
            18432, 20480, 22528, 24576, 26624, 28672, 30720, 32768, 34816, 36864,
            38912, 40960, 43008, 45056, 47104, 49152, 51200, 53248, 55296, 57344,
            59392, 61440, 63488, 65535,
        })),
        color_grid_levels=(1024, 2048, 4096, 8192, 12288, 16384, 20480, 24576, 28672, 32768, 36864, 40960, 49152, 57344, 65535),
        color_grid_ratios=(0.125, 0.25, 0.50, 0.75, 1.00),
        neutral_rgb_bases=(0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 256, 512, 768, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960),
        neutral_white_levels=(0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 256, 512, 768, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        chroma_rgb_bases=(4, 8, 16, 32, 64, 96, 128, 256, 512, 768, 1024, 2048, 4096, 8192, 12288, 16384, 20480, 24576, 28672, 32768, 36864, 40960, 49152, 57344, 65535),
        chroma_white_levels=(0, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        white_dominant_rgb_bases=(1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 256, 512, 768, 1024, 2048, 4096, 8192, 12288, 16384, 24576),
        white_dominant_white_levels=(4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        floor_rgb_bases=(1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 256, 512, 1024, 2048, 4096, 8192),
        floor_white_levels=(0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 256, 512, 1024, 2048, 4096, 8192),
        peak_rgb_bases=(24576, 28672, 32768, 36864, 40960, 49152, 57344, 65535),
        peak_white_levels=(0, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        dominance_rgb_bases=(32, 64, 96, 128, 256, 512, 768, 1024, 2048, 4096, 8192, 12288, 16384, 20480, 24576, 28672, 32768, 40960, 49152, 57344, 65535),
        dominance_white_levels=(0, 32, 64, 96, 128, 256, 512, 768, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        offaxis_rgb_bases=(32, 64, 96, 128, 256, 512, 768, 1024, 2048, 4096, 8192, 12288, 16384, 20480, 24576, 28672, 32768, 40960, 49152, 57344, 65535),
        offaxis_white_levels=(0, 32, 64, 96, 128, 256, 512, 768, 1024, 2048, 4096, 8192, 12288, 16384, 24576, 32768, 40960, 49152, 57344, 65535),
        impossible_rgb_bases=(24, 32, 48, 64, 96, 128, 256, 512, 768, 1024, 2048, 4096, 8192, 12288, 16384, 20480, 24576, 28672, 32768, 40960, 49152, 57344, 65535),
        impossible_white_ratios=(0.04, 0.09, 0.18, 0.36, 0.54, 0.78, 1.02, 1.30, 1.65),
        structured_impossible_rgb_bases=(96, 128, 256, 512, 768, 1024, 2048, 4096, 8192, 12288, 16384, 20480, 24576, 28672, 32768, 40960, 49152, 57344, 65535),
        structured_impossible_white_ratios=(0.16, 0.24, 0.36, 0.52, 0.68, 0.84, 1.00, 1.20, 1.45, 1.70),
    ),
}


CHROMA_FAMILIES = (
    ("warm", (1.00, 0.82, 0.08)),
    ("amber", (1.00, 0.66, 0.04)),
    ("orange", (1.00, 0.48, 0.00)),
    ("skin", (1.00, 0.72, 0.52)),
    ("tan", (1.00, 0.58, 0.34)),
    ("brown", (0.88, 0.42, 0.16)),
    ("cool", (0.12, 0.62, 1.00)),
    ("cyan", (0.00, 1.00, 1.00)),
    ("azure", (0.00, 0.45, 1.00)),
    ("violet", (0.55, 0.00, 1.00)),
    ("magenta", (1.00, 0.00, 1.00)),
    ("spring", (0.00, 1.00, 0.45)),
    # Sparse cyan-teal gap (CIE xy upper-left)
    ("bluecyan", (0.00, 0.45, 1.00)),
    ("cyanteal", (0.00, 0.70, 1.00)),
    ("teal", (0.00, 1.00, 0.75)),
    ("greenteal", (0.00, 1.00, 0.55)),
    ("steelteal", (0.05, 0.60, 0.90)),
    # Sparse green/yellow-green gap (CIE xy upper-center)
    ("puregreen", (0.00, 1.00, 0.00)),
    ("yellowgreen", (0.18, 1.00, 0.00)),
    ("chartreuse", (0.30, 1.00, 0.00)),
    ("warmchartreuse", (0.42, 1.00, 0.00)),
    ("gentlegreen", (0.08, 1.00, 0.06)),
    # Sparse warm saturated gap (CIE xy lower-right)
    ("purered", (1.00, 0.00, 0.00)),
    ("deepredorange", (1.00, 0.18, 0.00)),
    ("redorange", (1.00, 0.30, 0.00)),
    ("saturatedorange", (1.00, 0.50, 0.00)),
    ("redpink", (1.00, 0.00, 0.20)),
    ("redmagenta", (1.00, 0.00, 0.35)),
    ("coralsat", (1.00, 0.25, 0.10)),
)

WHITE_DOMINANT_FAMILIES = (
    ("warmwhite", (1.00, 0.30, 0.08)),
    ("peachwhite", (1.00, 0.52, 0.22)),
    ("skinwhite", (1.00, 0.66, 0.46)),
    ("limewhite", (0.38, 1.00, 0.10)),
    ("mintwhite", (0.12, 1.00, 0.62)),
    ("cyanwhite", (0.08, 0.78, 1.00)),
    ("bluewhite", (0.08, 0.22, 1.00)),
    ("violetwhite", (0.48, 0.12, 1.00)),
    ("rosewhite", (1.00, 0.14, 0.58)),
    ("neutralwhite", (0.55, 0.55, 0.55)),
)

FLOOR_FAMILIES = (
    ("deepblue", (0.08, 0.08, 0.22)),
    ("deepgreen", (0.08, 0.20, 0.10)),
    ("deepred", (0.20, 0.08, 0.08)),
    ("deepbrown", (0.16, 0.10, 0.06)),
    ("deepviolet", (0.14, 0.08, 0.18)),
    ("deepcyan", (0.06, 0.18, 0.18)),
    ("muddywarm", (0.22, 0.16, 0.10)),
    ("muddycool", (0.12, 0.18, 0.22)),
)

PEAK_FAMILIES = (
    ("peakamber", (1.00, 0.78, 0.04)),
    ("peakyellow", (1.00, 0.96, 0.02)),
    ("peakorange", (1.00, 0.56, 0.00)),
    ("peakcyan", (0.00, 0.94, 1.00)),
    ("peakazure", (0.00, 0.56, 1.00)),
    ("peakviolet", (0.62, 0.06, 1.00)),
    ("peakmagenta", (1.00, 0.06, 0.88)),
    ("peakmint", (0.18, 1.00, 0.72)),
)

DOMINANCE_FAMILIES = (
    ("rhard", (1.00, 0.08, 0.02)),
    ("rwarm", (1.00, 0.28, 0.06)),
    ("rrose", (1.00, 0.10, 0.34)),
    ("ghard", (0.06, 1.00, 0.04)),
    ("glime", (0.28, 1.00, 0.06)),
    ("gmint", (0.08, 1.00, 0.28)),
    ("bhard", (0.04, 0.10, 1.00)),
    ("bcyan", (0.04, 0.42, 1.00)),
    ("bviolet", (0.26, 0.08, 1.00)),
    ("yellowdom", (1.00, 0.92, 0.04)),
    ("cyandom", (0.05, 0.92, 1.00)),
    ("magentadom", (1.00, 0.06, 0.92)),
)

OFFAXIS_FAMILIES = (
    ("offaxis_01", (0.70, 0.20, 0.58)),
    ("offaxis_02", (0.32, 0.72, 0.48)),
    ("offaxis_03", (0.52, 0.34, 0.78)),
    ("offaxis_04", (0.68, 0.62, 0.18)),
    ("offaxis_05", (0.24, 0.46, 0.84)),
    ("offaxis_06", (0.82, 0.38, 0.24)),
    ("offaxis_07", (0.56, 0.74, 0.30)),
    ("offaxis_08", (0.42, 0.58, 0.72)),
    ("offaxis_09", (0.74, 0.28, 0.44)),
    ("offaxis_10", (0.18, 0.66, 0.64)),
)

IMPOSSIBLE_FAMILIES = (
    ("impossible_warmlift", (1.00, 0.64, 0.18)),
    ("impossible_amberlift", (1.00, 0.74, 0.12)),
    ("impossible_skinlift", (1.00, 0.78, 0.54)),
    ("impossible_tanlift", (0.92, 0.62, 0.34)),
    ("impossible_olive", (0.58, 0.72, 0.20)),
    ("impossible_mintlift", (0.20, 0.86, 0.56)),
    ("impossible_cyanlift", (0.14, 0.68, 0.94)),
    ("impossible_coollift", (0.24, 0.52, 1.00)),
    ("impossible_ice", (0.34, 0.78, 1.00)),
    ("impossible_violetlift", (0.62, 0.24, 1.00)),
    ("impossible_magentalift", (0.96, 0.20, 0.82)),
    ("impossible_mauve", (0.76, 0.42, 0.70)),
    ("impossible_copperlift", (0.84, 0.46, 0.22)),
    ("impossible_smoke", (0.46, 0.56, 0.40)),
)

STRUCTURED_IMPOSSIBLE_PATTERNS = (
    ("single_r", (1.00, 0.00, 0.00)),
    ("single_g", (0.00, 1.00, 0.00)),
    ("single_b", (0.00, 0.00, 1.00)),
    ("dual_rg_a", (1.00, 0.72, 0.00)),
    ("dual_rg_b", (0.72, 1.00, 0.00)),
    ("dual_rb_a", (1.00, 0.00, 0.72)),
    ("dual_rb_b", (0.72, 0.00, 1.00)),
    ("dual_gb_a", (0.00, 1.00, 0.72)),
    ("dual_gb_b", (0.00, 0.72, 1.00)),
    ("dual_rg_equal", (1.00, 1.00, 0.00)),
    ("dual_rb_equal", (1.00, 0.00, 1.00)),
    ("dual_gb_equal", (0.00, 1.00, 1.00)),
    ("triple_rgb_a", (1.00, 0.76, 0.52)),
    ("triple_rgb_b", (1.00, 0.52, 0.76)),
    ("triple_rgb_c", (0.76, 1.00, 0.52)),
    ("triple_rbg_d", (0.76, 0.52, 1.00)),
    ("triple_grb_e", (0.52, 1.00, 0.76)),
    ("triple_brg_f", (0.52, 0.76, 1.00)),
    ("triple_rgb_equal", (1.00, 1.00, 1.00)),
)


class PatchPlanBuilder:
    def __init__(self) -> None:
        self.rows: list[dict[str, int | str]] = []
        self._seen_values: set[tuple[int, int, int, int]] = set()
        self.category_counts: Counter[str] = Counter()

    def add(self, name: str, r16: int, g16: int, b16: int, w16: int, category: str) -> None:
        values = tuple(max(0, min(65535, int(value))) for value in (r16, g16, b16, w16))
        if values in self._seen_values:
            return
        self._seen_values.add(values)
        self.rows.append({
            "name": str(name),
            "r16": values[0],
            "g16": values[1],
            "b16": values[2],
            "w16": values[3],
        })
        self.category_counts[category] += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a larger True16 RGBW comprehensive patch plan.")
    parser.add_argument("--profile", choices=sorted(PROFILE_CONFIGS.keys()), default="meaningful")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def add_core_true16_anchors(builder: PatchPlanBuilder, config: ProfileConfig) -> None:
    for q16 in config.ramp_values:
        builder.add(f"gray_q16_{q16:05d}", q16, q16, q16, 0, "core_gray")
        builder.add(f"R_q16_{q16:05d}", q16, 0, 0, 0, "core_primary")
        builder.add(f"G_q16_{q16:05d}", 0, q16, 0, 0, "core_primary")
        builder.add(f"B_q16_{q16:05d}", 0, 0, q16, 0, "core_primary")
        builder.add(f"W_q16_{q16:05d}", 0, 0, 0, q16, "core_primary")

    for level in config.color_grid_levels:
        for r_ratio in config.color_grid_ratios:
            for g_ratio in config.color_grid_ratios:
                for b_ratio in config.color_grid_ratios:
                    if abs(r_ratio - g_ratio) < 1e-9 and abs(g_ratio - b_ratio) < 1e-9:
                        continue
                    builder.add(
                        f"color_r{r_ratio:.2f}_g{g_ratio:.2f}_b{b_ratio:.2f}_{level:05d}",
                        int(round(level * r_ratio)),
                        int(round(level * g_ratio)),
                        int(round(level * b_ratio)),
                        0,
                        "core_color_grid",
                    )


def add_legacy_rgbw_batches(builder: PatchPlanBuilder) -> None:
    batch_functions = (
        ("legacy_extended_warm", batch_lib.generate_warm_saturation_batch),
        ("legacy_extended_cool", batch_lib.generate_cool_saturation_batch),
        ("legacy_secondary", batch_lib.generate_secondary_color_batch),
        ("legacy_tertiary", batch_lib.generate_tertiary_color_batch),
        ("legacy_skin", batch_lib.generate_skin_tones_batch),
        ("legacy_gray_white", batch_lib.generate_gray_ramp_whitechannel_batch),
        ("legacy_pastels", batch_lib.generate_pastel_batch),
        ("legacy_white_focus", batch_lib.generate_white_channel_focus_batch),
        ("legacy_hi_sat", batch_lib.generate_high_saturation_edges_batch),
        ("legacy_brown_tan", batch_lib.generate_brown_tan_profile_batch),
        ("legacy_yellow_orange", batch_lib.generate_yellow_orange_batch),
        ("legacy_bright_yellow_orange", batch_lib.generate_bright_yellow_orange_batch),
        ("legacy_edge_cases", batch_lib.generate_edge_case_colors_batch),
        ("legacy_white_mix_orange_peach", batch_lib.generate_white_mix_orange_peach_batch),
        ("sparse_cyan_teal", batch_lib.generate_sparse_cyan_teal_batch),
        ("sparse_green_yellowgreen", batch_lib.generate_sparse_green_yellowgreen_batch),
        ("sparse_warm_saturated", batch_lib.generate_sparse_warm_saturated_batch),
    )
    for category, function in batch_functions:
        for row in function():
            builder.add(row["name"], row["r16"], row["g16"], row["b16"], row["w16"], category)


def add_neutral_white_corridors(builder: PatchPlanBuilder, config: ProfileConfig) -> None:
    for rgb_base in config.neutral_rgb_bases:
        for white in config.neutral_white_levels:
            builder.add(f"neutral_rgbw_rgb{rgb_base:05d}_w{white:05d}", rgb_base, rgb_base, rgb_base, white, "neutral_white_corridor")
            if white > rgb_base:
                builder.add(
                    f"neutral_impossible_rgb{rgb_base:05d}_w{white:05d}",
                    rgb_base,
                    rgb_base,
                    rgb_base,
                    white,
                    "neutral_impossible",
                )


def add_chromatic_white_corridors(builder: PatchPlanBuilder, config: ProfileConfig) -> None:
    for family_name, (r_ratio, g_ratio, b_ratio) in CHROMA_FAMILIES:
        for rgb_base in config.chroma_rgb_bases:
            r16 = int(round(rgb_base * r_ratio))
            g16 = int(round(rgb_base * g_ratio))
            b16 = int(round(rgb_base * b_ratio))
            for white in config.chroma_white_levels:
                builder.add(
                    f"corridor_{family_name}_rgb{rgb_base:05d}_w{white:05d}",
                    r16,
                    g16,
                    b16,
                    white,
                    "chromatic_white_corridor",
                )


def add_white_dominant_tints(builder: PatchPlanBuilder, config: ProfileConfig) -> None:
    for family_name, (r_ratio, g_ratio, b_ratio) in WHITE_DOMINANT_FAMILIES:
        for rgb_base in config.white_dominant_rgb_bases:
            r16 = int(round(rgb_base * r_ratio))
            g16 = int(round(rgb_base * g_ratio))
            b16 = int(round(rgb_base * b_ratio))
            for white in config.white_dominant_white_levels:
                builder.add(
                    f"white_dominant_{family_name}_rgb{rgb_base:05d}_w{white:05d}",
                    r16,
                    g16,
                    b16,
                    white,
                    "white_dominant_tint",
                )


def add_floor_rgbw_states(builder: PatchPlanBuilder, config: ProfileConfig) -> None:
    for family_name, (r_ratio, g_ratio, b_ratio) in FLOOR_FAMILIES:
        for rgb_base in config.floor_rgb_bases:
            r16 = int(round(rgb_base * r_ratio))
            g16 = int(round(rgb_base * g_ratio))
            b16 = int(round(rgb_base * b_ratio))
            for white in config.floor_white_levels:
                builder.add(
                    f"floor_{family_name}_rgb{rgb_base:05d}_w{white:05d}",
                    r16,
                    g16,
                    b16,
                    white,
                    "near_black_floor",
                )


def add_peak_rgbw_states(builder: PatchPlanBuilder, config: ProfileConfig) -> None:
    for family_name, (r_ratio, g_ratio, b_ratio) in PEAK_FAMILIES:
        for rgb_base in config.peak_rgb_bases:
            r16 = int(round(rgb_base * r_ratio))
            g16 = int(round(rgb_base * g_ratio))
            b16 = int(round(rgb_base * b_ratio))
            for white in config.peak_white_levels:
                builder.add(
                    f"peak_{family_name}_rgb{rgb_base:05d}_w{white:05d}",
                    r16,
                    g16,
                    b16,
                    white,
                    "peak_rgbw",
                )


def add_dominance_sweeps(builder: PatchPlanBuilder, config: ProfileConfig) -> None:
    for family_name, (r_ratio, g_ratio, b_ratio) in DOMINANCE_FAMILIES:
        for rgb_base in config.dominance_rgb_bases:
            r16 = int(round(rgb_base * r_ratio))
            g16 = int(round(rgb_base * g_ratio))
            b16 = int(round(rgb_base * b_ratio))
            for white in config.dominance_white_levels:
                builder.add(
                    f"dominance_{family_name}_rgb{rgb_base:05d}_w{white:05d}",
                    r16,
                    g16,
                    b16,
                    white,
                    "dominance_sweep",
                )


def add_offaxis_rgbw_sweeps(builder: PatchPlanBuilder, config: ProfileConfig) -> None:
    for family_name, (r_ratio, g_ratio, b_ratio) in OFFAXIS_FAMILIES:
        for rgb_base in config.offaxis_rgb_bases:
            r16 = int(round(rgb_base * r_ratio))
            g16 = int(round(rgb_base * g_ratio))
            b16 = int(round(rgb_base * b_ratio))
            for white in config.offaxis_white_levels:
                builder.add(
                    f"offaxis_{family_name}_rgb{rgb_base:05d}_w{white:05d}",
                    r16,
                    g16,
                    b16,
                    white,
                    "offaxis_rgbw",
                )


def add_impossible_rgbw_spread(builder: PatchPlanBuilder, config: ProfileConfig) -> None:
    for family_name, (r_ratio, g_ratio, b_ratio) in IMPOSSIBLE_FAMILIES:
        min_ratio = min(r_ratio, g_ratio, b_ratio)
        for rgb_base in config.impossible_rgb_bases:
            r16 = max(1, int(round(rgb_base * r_ratio)))
            g16 = max(1, int(round(rgb_base * g_ratio)))
            b16 = max(1, int(round(rgb_base * b_ratio)))
            min_rgb = min(r16, g16, b16)
            for white_ratio in config.impossible_white_ratios:
                if abs(white_ratio - min_ratio) < 0.08:
                    continue
                w16 = max(1, min(65535, int(round(rgb_base * white_ratio))))
                if w16 == min_rgb:
                    continue
                builder.add(
                    f"{family_name}_rgb{rgb_base:05d}_w{w16:05d}",
                    r16,
                    g16,
                    b16,
                    w16,
                    "impossible_rgbw_spread",
                )


def add_structured_impossible_ramps(builder: PatchPlanBuilder, config: ProfileConfig) -> None:
    for pattern_name, (r_ratio, g_ratio, b_ratio) in STRUCTURED_IMPOSSIBLE_PATTERNS:
        max_ratio = max(r_ratio, g_ratio, b_ratio)
        min_positive_ratio = min(value for value in (r_ratio, g_ratio, b_ratio) if value > 0.0)
        for rgb_base in config.structured_impossible_rgb_bases:
            scale = rgb_base / max_ratio if max_ratio > 0.0 else rgb_base
            r16 = int(round(scale * r_ratio))
            g16 = int(round(scale * g_ratio))
            b16 = int(round(scale * b_ratio))
            active_values = [value for value in (r16, g16, b16) if value > 0]
            if not active_values:
                continue
            min_active = min(active_values)
            for white_ratio in config.structured_impossible_white_ratios:
                w16 = max(1, min(65535, int(round(rgb_base * white_ratio))))
                if abs(white_ratio - min_positive_ratio) < 0.08:
                    continue
                if w16 == min_active:
                    continue
                builder.add(
                    f"impossible_struct_{pattern_name}_rgb{rgb_base:05d}_w{w16:05d}",
                    r16,
                    g16,
                    b16,
                    w16,
                    "impossible_structured_ramps",
                )


def summarize(rows: list[dict[str, int | str]], category_counts: Counter[str], profile: str) -> dict[str, object]:
    prefix_counts = Counter(str(row["name"]).split("_")[0] for row in rows)
    with_w = sum(1 for row in rows if int(row["w16"]) > 0)
    all_nonzero = sum(1 for row in rows if all(int(row[channel]) > 0 for channel in ("r16", "g16", "b16", "w16")))
    explicit_impossible = sum(
        int(count)
        for category, count in category_counts.items()
        if str(category).startswith("impossible_")
    )
    max_channel_values = {
        channel: max(int(row[channel]) for row in rows) if rows else 0
        for channel in ("r16", "g16", "b16", "w16")
    }
    min_nonzero_values = {
        channel: min((int(row[channel]) for row in rows if int(row[channel]) > 0), default=0)
        for channel in ("r16", "g16", "b16", "w16")
    }
    return {
        "profile": profile,
        "row_count": len(rows),
        "with_white_rows": with_w,
        "rgb_only_rows": len(rows) - with_w,
        "all_nonzero_rgbw_rows": all_nonzero,
        "all_nonzero_rgbw_fraction": float(all_nonzero / len(rows)) if rows else 0.0,
        "explicit_impossible_rgbw_rows": explicit_impossible,
        "explicit_impossible_rgbw_fraction": float(explicit_impossible / len(rows)) if rows else 0.0,
        "category_counts": dict(category_counts),
        "top_name_prefixes": prefix_counts.most_common(40),
        "max_channel_values": max_channel_values,
        "min_nonzero_channel_values": min_nonzero_values,
        "example_first_rows": rows[:10],
        "example_last_rows": rows[-10:],
    }


def write_csv(path: Path, rows: list[dict[str, int | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "mode", "use_fill16", "r16", "g16", "b16", "w16"])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "name": row["name"],
                "mode": "fill16",
                "use_fill16": 1,
                "r16": row["r16"],
                "g16": row["g16"],
                "b16": row["b16"],
                "w16": row["w16"],
            })


def main() -> None:
    args = parse_args()
    config = PROFILE_CONFIGS[args.profile]
    builder = PatchPlanBuilder()

    add_core_true16_anchors(builder, config)
    add_legacy_rgbw_batches(builder)
    add_neutral_white_corridors(builder, config)
    add_chromatic_white_corridors(builder, config)
    add_white_dominant_tints(builder, config)
    add_floor_rgbw_states(builder, config)
    add_peak_rgbw_states(builder, config)
    add_dominance_sweeps(builder, config)
    add_offaxis_rgbw_sweeps(builder, config)
    add_impossible_rgbw_spread(builder, config)
    add_structured_impossible_ramps(builder, config)

    write_csv(args.out, builder.rows)
    summary = summarize(builder.rows, builder.category_counts, args.profile)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "profile": args.profile,
        "rows": len(builder.rows),
        "with_white_rows": summary["with_white_rows"],
        "all_nonzero_rgbw_rows": summary["all_nonzero_rgbw_rows"],
        "out": str(args.out),
        "summary": str(args.summary_out),
    }, indent=2))


if __name__ == "__main__":
    main()