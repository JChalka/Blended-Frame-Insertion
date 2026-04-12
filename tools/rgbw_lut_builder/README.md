# RGBW Capture Analysis

This directory contains tools for analyzing real RGBW patch captures and building color-corrected RGBW LUTs. The core question:

> How much white can be used while preserving measured color accuracy and avoiding obvious over-whitening of saturated hues?

---

## 1. Scripts

### 1.1 Capture Analyzer

```powershell
python rgbw_capture_analysis/analyze_rgbw_captures.py
```

Reads CSV captures from `tools/v15/patch captures`, derives measured Lab/LCh values from captured XYZ, and writes:

- Per-row metrics CSV and summary JSON
- Plots of white usage versus measured chroma and hue
- Empirical hue/chroma white-usage envelopes
- Family sweep plots (RGB fixed, W stepped)

Options: `--input-dir`, `--output-dir`, `--white-x/y/Y`, `--min-measured-y`, `--top-family-count`

### 1.2 Prototype Solver

```powershell
python rgbw_capture_analysis/prototype_measured_white_solver.py
```

Fits measured RGBW→XYZ basis vectors from pure-channel sweeps and compares classic `w = min(rgb)` extraction against a bounded-error measured-basis solver.

Options: `--max-delta-e`, `--max-hue-shift`, `--grid-size`, `--sample-scale`, `--include-value-zero`

### 1.3 LUT Builder (CLI)

```powershell
python rgbw_capture_analysis/build_measured_rgbw_lut.py
```

Solves a coarse regular RGB cube with the measured-basis bounded-error solver, then upsamples into a dense LUT. Exports C headers for on-device use.

Full CLI options:

- `--coarse-grid-size` — solved cube resolution
- `--full-grid-size` — exported dense LUT resolution
- `--max-delta-e`, `--max-hue-shift` — color error bounds
- `--target-white-balance-mode reference-white` — correct neutral axis toward reference white
- `--neutral-classic-chroma`, `--neutral-classic-fade-width` — classic extraction bias for near-neutral samples
- `--measured-prior-mode family` — average within capture families before blending
- `--measured-prior-neighbors`, `--measured-family-count` — neighbor/family limits (0 = all)
- `--measured-prior-strength` — strength of measured prior blend
- `--nondegenerate-regularization` — regularize away from zero-channel corners
- `--sample-scale` — 16-bit channel range
- `--skip-full-lut`, `--skip-header`, `--emit-classic-header`
- `--header-name`, `--header-grid-size`

---

## 2. Interactive GUI

```powershell
python rgbw_capture_analysis/rgbw_lut_gui.py
```

A tkinter + matplotlib application that replaces the CLI workflow with an interactive interface. All solver and builder parameters from the CLI are exposed as GUI controls.

### 2.1 Features

**Left panel — Controls:**
All parameters from the CLI scripts are available as editable fields: reference white, color constraints, white balance mode, neutral region settings, measured prior settings, grid sizes, channel mode, and export options.

**Right panel — Tabbed visualization:**

| Tab | Content |
|-----|---------|
| CIE 1931 | xy chromaticity chart with toggle overlays: Rec.709, DCI-P3, BT.2020, LED gamut, captured points, solved points, spectral locus |
| Histogram | White gain distribution across the solved cube |
| White Slices | Side-by-side heatmaps of classic vs measured W channel at 5 blue-axis slices |
| Comparison | Sortable table of all coarse grid results |
| 3D Viewer | Interactive scatter plot with per-channel selector, subsample step, classic overlay toggle |

**Action buttons:**

| Button | Output |
|--------|--------|
| Load Data | Reads capture CSVs, fits basis, builds target RGB basis |
| Load Output | Reloads a previously built output directory (reads `lut_summary.json` to restore settings) |
| Build LUT | Threaded build: coarse solve → optional gamut clamp → .npy cubes + comparison CSV + `lut_summary.json` |
| Export Header | 3D RGBW cube C header via `trilinear_expand_cube` → `write_rgbw_header` |
| Export True16 Cal Header | Per-channel 1D Q16→Q16 calibration header (see §3) |
| Export Binary Cube | Raw binary cube file for SD card / QSPI flash loading (see §4) |

### 2.2 Persistence

- **Config**: Settings auto-save to `rgbw_lut_gui_config.json` (next to the script) on window close and after each build. Restored on next launch.
- **Summary**: Each build writes `lut_summary.json` to the output directory with full settings, basis sanity data, white gain quantiles, and top increases/decreases. Loading an output directory reads this summary and restores all GUI settings to match.

---

## 3. True16 Calibration Header

The "Export True16 Cal Header" button generates a per-channel 1D calibration LUT in the `TemporalBFICalibrationTrue16` namespace format consumed by `calibrateInputQ16ForSolver()` in the solver library.

The LUT size is controlled by the **True16 LUT size** field in the GUI (0 = fall back to Full grid size). Because the export interpolates 1D pure-channel sweeps directly from the coarse cube knot points using piecewise linear interpolation, the target size can be arbitrarily large without expanding the full 3D cube in memory.

**Sizing guidance:**
- The v15/v16 temporal ladder typically has ~48k–50k states per channel
- A True16 LUT of 50,000 entries provides roughly 1:1 coverage of the Q16 input domain relative to ladder state count
- The runtime lookup `(inputQ16 * (lutSize-1) + 32767) / 65535` indexes the LUT, so more entries = finer correction granularity
- The reference calibration header (`True16_Calibration_21388.h`) uses 16,320 entries per channel

**Output format:**
- `LUT_{R,G,B,W}_16_TO_16[LUT_SIZE]` — Q16 input → Q16 output arrays
- Per-channel metadata: `{ch}_MAX_Y_X1000`, `MEASUREMENT_POINTS`, `SAMPLE_COUNT`, `LARGEST_GAP_Q16`
- `True16LUTSet` accessor struct with `lutForChannel(channel)` and `lutSize()`

---

## 4. Binary Cube Export (PSRAM / SD / QSPI Flash)

The "Export Binary Cube" button writes the measured cube as a raw binary file for loading into external memory at boot time, targeting Teensy 4.1 hardware with PSRAM.

**File layout (little-endian):**

| Offset | Size | Content |
|--------|------|---------|
| 0 | 2 bytes | Grid size N (uint16) |
| 2 | 2 bytes | Channel count C (uint16) — 4 for RGBW, 3 for RGB |
| 4 | N³×C×2 bytes | Cube data: `cube[r][g][b][ch]` as uint16, C-order |

**Memory budget for Teensy 4.1 with PSRAM:**

| Grid N | Entries N³ | Cube size | Fits in |
|--------|-----------|-----------|---------|
| 64 | 262,144 | 2.0 MB | 1× 8 MB PSRAM |
| 80 | 512,000 | 3.9 MB | 1× 8 MB PSRAM |
| 100 | 1,000,000 | 7.6 MB | 1× 8 MB PSRAM |
| 120 | 1,728,000 | 13.2 MB | 2× 8 MB PSRAM |
| 125 | 1,953,125 | 14.9 MB | 2× 8 MB PSRAM |

After reserving ~1–2 MB for solver LUTs, LED framebuffers, and headroom, the practical limit is approximately N=100 with one 8 MB PSRAM chip and N=120–125 with two.

**Loading options on Teensy 4.1:**

- **SD card (SDIO 4-bit)**: ~20–25 MB/s reads. A 100³ cube loads in ~0.3 s at boot. Cubes are trivially swappable as `.bin` files.
- **External QSPI flash (bottom pads)**: W25Q128JV or similar, memory-mapped reads. Solder-and-forget, no SD dependency, but requires reflashing to change cubes.
- **PROGMEM (built-in flash)**: Only practical for small cubes (N ≤ 48, ~0.8 MB) due to 8 MB total flash shared with program.

**Performance note:** PSRAM on the T4.1 runs at ~88 MHz via FlexSPI2. Trilinear interpolation reads 8 neighboring grid points per lookup. The 32-byte PSRAM cache line helps with spatially coherent access, but scattered lookups may bottleneck at very high LED refresh rates.

---

## 5. RGB Mode (No White Channel)

The **Channel mode** dropdown in the Output Mode section switches between `RGBW` (default) and `RGB`. In RGB mode, all exports are adapted for LED strips without a dedicated white channel:

**How it works:** The solver always runs in RGBW internally — the measured basis fit and white-bounded-error solve are identical. On export, the allocated white is folded back into the RGB channels: `R_out = R + W`, `G_out = G + W`, `B_out = B + W`. This preserves the solver's color-accuracy guarantees while producing pure RGB output.

**Per-export behavior:**

| Export | RGBW mode | RGB mode |
|--------|-----------|----------|
| True16 Cal Header | 4 LUTs (R, G, B, W) | 3 LUTs (R, G, B), W folded into sweeps |
| Binary Cube | N³×4 uint16 | N³×3 uint16 (25% smaller) |
| 3D Header | 4 flat arrays (R, G, B, W) | 4 arrays but W is all zeros |
| 3D Viewer | R, G, B, W channel radio buttons | R, G, B only |
| White Slices | Classic vs measured W heatmaps | Disabled (not applicable) |

**Memory savings for binary cubes in RGB mode:**

| Grid N | RGBW (4ch) | RGB (3ch) |
|--------|-----------|-----------|
| 64 | 2.0 MB | 1.5 MB |
| 100 | 7.6 MB | 5.7 MB |
| 120 | 13.2 MB | 9.9 MB |
| 125 | 14.9 MB | 11.2 MB |

With 3 channels per entry, a single 8 MB PSRAM chip supports up to N≈110 in RGB mode (vs N≈100 in RGBW mode).

---

## 6. Design Notes

The solver uses a neutral-preservation bias: low-chroma samples are blended back toward classic `min(rgb)` extraction, fading out across a configurable chroma band. This is intentionally conservative around whites and near-whites.

The measured capture prior biases the solve toward real RGBW family behavior across thousands of captured states. In `family` mode, rows from the same sweep family are averaged first so dense families don't dominate sparse ones.

The 3D header grid and the temporal solver's 1D ladder count are not directly comparable. A coarse grid of `17³ = 4,913` entries is expected for the 3D cube. The 1D True16 calibration header is the appropriate format when matching temporal ladder state counts (16k–50k entries per channel).