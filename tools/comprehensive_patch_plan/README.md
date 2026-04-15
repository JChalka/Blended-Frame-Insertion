# Comprehensive Patch Plan Generators

Two scripts for generating RGBW Q16 patch plans used to drive True16 LED capture sweeps.
All patch values are raw 16-bit RGBW (0–65535) meant to be sent directly to the LED
controller; downstream tooling converts measured results to CIE xy via the fitted LED
basis vectors.

---

## generate_patch_batches_v2.py

Standalone batch library. Each function returns a `list[dict]` with keys
`name, r16, g16, b16, w16`. Running it directly exports every batch as an
individual CSV under `patch_plans/`.

```
python generate_patch_batches_v2.py
```

No CLI arguments — it writes one CSV per batch into `patch_plans/`:

```
patch_plans/patch_plan_batch_warm_saturation.csv
patch_plans/patch_plan_batch_cool_saturation.csv
...
```

### CSV columns

| Column | Type | Description |
|--------|------|-------------|
| `name` | str  | Human-readable patch label |
| `r16`  | int  | Red channel Q16 (0–65535) |
| `g16`  | int  | Green channel Q16 |
| `b16`  | int  | Blue channel Q16 |
| `w16`  | int  | White channel Q16 |

### Batch functions (17)

| Function | Description |
|----------|-------------|
| `generate_warm_saturation_batch` | Yellow / orange / amber with RGBW sweeps |
| `generate_cool_saturation_batch` | Cyan / blue / magenta with RGBW sweeps |
| `generate_skin_tones_batch` | Skin, tan, brown tones with W brightness |
| `generate_gray_ramp_whitechannel_batch` | Gray ramp — RGB-only and RGBW variants |
| `generate_pastel_batch` | Pastel colors with gentle white mixes |
| `generate_white_channel_focus_batch` | Warm RGB base, varying W levels |
| `generate_high_saturation_edges_batch` | Primary / secondary saturation edges |
| `generate_secondary_color_batch` | Yellow, cyan, magenta + white mixes |
| `generate_tertiary_color_batch` | Orange, chartreuse, spring green, azure, violet, rose |
| `generate_brown_tan_profile_batch` | 20 base-ratio brown & tan grid |
| `generate_yellow_orange_batch` | Green-yellow → deep red-orange |
| `generate_bright_yellow_orange_batch` | Dense bright yellow / orange hue coverage |
| `generate_edge_case_colors_batch` | Deep / dark, muddy, extreme white-tint, off-axis |
| `generate_white_mix_orange_peach_batch` | Orange / peach / coral with wide W range |
| `generate_sparse_cyan_teal_batch` | Saturated cyan / teal (CIE xy upper-left gap) |
| `generate_sparse_green_yellowgreen_batch` | Green / yellow-green (CIE xy upper-center gap) |
| `generate_sparse_warm_saturated_batch` | Saturated warm reds / oranges (CIE xy lower-right gap) |

The last three batches were added to fill sparse regions identified from the
CIE 1931 xy chromaticity diagram of existing capture data.

---

## generate_patch_plan_true16_comprehensive_v6.py

Orchestrator that combines core anchors, all v2 batches, white corridors,
chroma families, impossible-color spreads, and more into a single
deduplicated CSV. This is the primary plan used for full capture runs.

```
python generate_patch_plan_true16_comprehensive_v6.py [--profile PROFILE] [--out PATH] [--summary-out PATH]
```

### CLI arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--profile` | choice | `meaningful` | Density profile — controls how many brightness levels, ratios, and bases are swept |
| `--out` | path | `patch_plans/patch_plan_true16_comprehensive_v6.csv` | Output CSV path |
| `--summary-out` | path | `patch_plans/patch_plan_true16_comprehensive_v6_summary.json` | Output summary JSON path |

### Profiles

Three built-in density presets (`ProfileConfig` dataclass):

| Profile | Purpose | Relative size |
|---------|---------|---------------|
| `meaningful` | Default capture set — good coverage, manageable run time | ~1× |
| `extended` | Finer grid — more brightness levels and ratio gradations | ~2–3× |
| `capture` | Maximum density — 15 color grid levels, finest ratios | ~4–5× |

Each profile controls: `ramp_values`, `color_grid_levels`, `color_grid_ratios`,
`neutral_rgb_bases`, `neutral_white_levels`, and equivalent fields for every
corridor/family category.

### CSV columns

| Column | Type | Description |
|--------|------|-------------|
| `name` | str  | Patch label (includes category prefix) |
| `mode` | str  | Always `fill16` |
| `use_fill16` | int | Always `1` |
| `r16`  | int  | Red channel Q16 (0–65535) |
| `g16`  | int  | Green channel Q16 |
| `b16`  | int  | Blue channel Q16 |
| `w16`  | int  | White channel Q16 |

### Builder pipeline

The orchestrator calls these builder stages in order, all feeding into a
`PatchPlanBuilder` that deduplicates on `(r16, g16, b16, w16)` tuples:

1. **Core True16 anchors** — gray ramps, RGB primaries, color grid
2. **Legacy RGBW batches** — all 17 functions from `generate_patch_batches_v2`
3. **Neutral white corridors** — neutral RGB with varying white levels
4. **Chromatic white corridors** — 31 chroma families × rgb bases × white levels
5. **White-dominant tints** — 10 white-dominant families
6. **Floor RGBW states** — 8 near-black families
7. **Peak RGBW states** — 8 peak-brightness families
8. **Dominance sweeps** — 12 single-channel dominance families
9. **Off-axis sweeps** — 10 off-neutral-axis families
10. **Impossible RGBW spread** — 14 impossible-color families (W >> RGB)
11. **Structured impossible ramps** — 18 structured patterns

### Chroma families (CHROMA_FAMILIES)

31 entries as `(name, (r_ratio, g_ratio, b_ratio))`. Includes original 12
warm/cool families plus 19 gap-fill additions targeting sparse CIE xy
regions:

- **Cyan-teal gap** (5): bluecyan, cyanteal, teal, greenteal, steelteal
- **Green/yellow-green gap** (5): puregreen, yellowgreen, chartreuse, warmchartreuse, gentlegreen
- **Warm saturated gap** (9): purered, deepredorange, redorange, saturatedorange, redpink, redmagenta, coralsat, darkorange, deepcoral

### Summary JSON

The `--summary-out` file records:

- `profile` name
- `row_count`, `with_white_rows`, `rgb_only_rows`
- `all_nonzero_rgbw_rows` / fraction
- `category_counts` — per-category patch counts
- `top_name_prefixes` — top 40 name prefix frequencies
- `max_channel_values` / `min_nonzero_channel_values` per channel
- `example_first_rows` / `example_last_rows` (10 each)

---

## Examples

```bash
# Export all individual batch CSVs
python generate_patch_batches_v2.py

# Generate a full plan with default (meaningful) profile
python generate_patch_plan_true16_comprehensive_v6.py

# Generate with extended density
python generate_patch_plan_true16_comprehensive_v6.py --profile extended

# Custom output paths
python generate_patch_plan_true16_comprehensive_v6.py \
    --profile capture \
    --out patch_plans/my_capture_plan.csv \
    --summary-out patch_plans/my_capture_plan_summary.json
```
