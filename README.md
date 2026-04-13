# TemporalBFI

Temporal rendering framework for addressable LED strips, providing sub-8-bit brightness resolution through Blended Frame Insertion (BFI). By rapidly alternating between two brightness levels across a multi-phase display cycle, the library achieves 16-bit equivalent perceived output using only 8-bit LED drivers.

## How It Works

Each display cycle consists of `cycle_length` phases (default 5). Within one cycle, a pixel distributes phases between two brightness levels:

- **(cycle\_length − bfi)** phases display the **upper value** (ceiling)
- **bfi** phases display the **lower value** (floor)

The perceived output integrates over the full cycle, producing fine-grained brightness steps between adjacent 8-bit levels. A 4096-entry per-channel temporal ladder maps every Q16 (0–65535) target to the optimal `(value, bfi, lowerValue)` tuple, selected from physically measured LED states.

## Features

- **True 16-bit rendering** — 4096+ distinct brightness levels per channel from 8-bit LED hardware
- **RGBW & RGB support** — white extraction from RGB, direct RGBW input, or white-limit clamping
- **Calibration-aware pipeline** — optional per-channel Q16 input calibration for device-specific correction
- **Transfer curves** — pluggable gamma/tone-mapping curves (linear, gamma, BT.1886, HLG, PQ, sRGB, toe-gamma)
- **Precomputed or runtime solving** — LUTs can be computed at boot or loaded from PROGMEM headers
- **FastLED integration** — works alongside FastLED CRGB buffers with GRB byte-order handling
- **Platform-agnostic core** — runs on Teensy 4.x, ESP32, and any Arduino-compatible board with sufficient RAM

## Quick Start

```cpp
#include <TemporalBFI.h>
#include <TemporalBFIRuntime.h>

SolverRuntime solver;

// Allocate LUT buffers (4 channels × lutSize entries each)
uint8_t  valueLUT[4 * 4096];
uint8_t  bfiLUT[4 * 4096];
uint8_t  floorLUT[4 * 4096];

void setup() {
    solver.attachLUTs(valueLUT, bfiLUT, floorLUT, nullptr, 4096);
    solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16);
}

void loop() {
    // Solve a 16-bit color → encoded states
    auto r = solver.solve(rQ16, 1);  // channel 1 = R
    auto g = solver.solve(gQ16, 0);  // channel 0 = G
    auto b = solver.solve(bQ16, 2);  // channel 2 = B
    auto w = solver.solve(wQ16, 3);  // channel 3 = W

    // Commit to frame buffers
    SolverRuntime::commitPixelRGBW(upperFrame, floorFrame,
        bfiMapG, bfiMapR, bfiMapB, bfiMapW, pixelIndex, g, r, b, w);

    // Render each BFI phase — 5 phases per perceived frame at ≥600 Hz LED refresh
    for (uint8_t phase = 0; phase < 5; phase++) {
        SolverRuntime::renderSubpixelBFI_RGBW(upperFrame, floorFrame,
            bfiMapG, bfiMapR, bfiMapB, bfiMapW,
            displayBuffer, pixelCount, phase);
        // Send displayBuffer to LEDs
    }
}
```

## API Reference

### SolverRuntime

| Method | Description |
|--------|-------------|
| `attachLUTs(value, bfi, floor, outputQ16, size)` | Attach pre-allocated LUT buffers (4 channels × size) |
| `precompute(solverFn)` | Populate LUTs by solving all Q16 values across GRBW channels |
| `loadPrecomputed(srcValue, srcBfi, srcFloor, srcOutputQ16)` | Load LUTs from PROGMEM or pre-built data |
| `solve(q16, channel)` | Look up precomputed `EncodedState` for a Q16 input |
| `config()` | Access `PolicyConfig` tuning knobs |
| `setTransferCurve(r, g, b, w, buckets)` | Register per-channel transfer curves |
| `setCalibrationFunction(fn)` | Register per-channel Q16 calibration callback |
| `extractRgbw(rQ16, gQ16, bQ16)` | Extract white from RGB (white = min of calibrated channels) |
| `applyWhiteLimit(r, g, b, w)` | Clamp white and redistribute to RGB |
| `setWhiteLimit(limit)` | Set 0–255 white channel maximum |
| `commitPixelRGBW(...)` | Write encoded RGBW state to frame/BFI buffers (static) |
| `commitPixelRGB(...)` | Write encoded RGB state to frame/BFI buffers (static) |
| `renderSubpixelBFI_RGBW(...)` | Render one BFI phase for RGBW pixels (static) |
| `renderSubpixelBFI_RGB(...)` | Render one BFI phase for RGB pixels (static) |
| `commitPixelRGBW_Packed(...)` | Write encoded RGBW state to frame buffers + packed BFI map (static) |
| `commitPixelRGB_Packed(...)` | Write encoded RGB state to frame buffers + packed BFI map (static) |
| `renderSubpixelBFI_RGBW_Packed(...)` | Render one BFI phase for RGBW pixels from packed BFI map (static) |
| `renderSubpixelBFI_RGB_Packed(...)` | Render one BFI phase for RGB pixels from packed BFI map (static) |
| `dumpLUTHeader(Serial)` | Emit embeddable PROGMEM header of current LUTs |

### Key Types

```cpp
struct EncodedState {
    uint8_t  value;        // output brightness (0–255)
    uint8_t  bfi;          // BFI level (0–4)
    uint8_t  lowerValue;   // floor value for off-phases
    uint16_t outputQ16;    // actual Q16 output
    uint16_t ladderIndex;  // ladder index used
};

struct LadderEntry {
    uint16_t outputQ16;    // measured Q16 output
    uint8_t  value;        // brightness level
    uint8_t  bfi;          // BFI level
};

struct PolicyConfig {
    uint16_t minErrorQ16 = 64;
    uint16_t relativeErrorDivisor = 24;
    uint8_t  maxBFI = 4;
    bool     preferHigherBFI = true;
    uint8_t  highlightBypassStart = 240;
    // ... and more — see TemporalBFI.h
};
```

## Examples

| Example | Description | Dependencies |
|---------|-------------|--------------|
| [FrameworkDemo](examples/FrameworkDemo/) | Minimal pipeline — direct solver calls, commit, render. No precomputation. | Library only |
| [RGB16InputDemo](examples/RGB16InputDemo/) | 16-bit RGB input with precomputed LUTs and RGBW white extraction. | Library only |
| [ColorCalibrationABDemo](examples/ColorCalibrationABDemo/) | A/B comparison toggling True16 input calibration on/off every 3 seconds. | Library only |
| [PrecomputeDemo](examples/PrecomputeDemo/) | Benchmarks precompute timing, solver lookups, and memory footprint. | Library only |
| [rgbwNoExtractionDemo](examples/rgbwNoExtractionDemo/) | Direct RGBW input with white-limit clamping, no extraction step. | Library only |
| [True16RGBWGradientDemo](examples/True16RGBWGradientDemo/) | Animated 16-bit gradient sweep with per-pixel RGBW extraction and BFI. | Library only |
| [TemporalFastLEDDemo](examples/TemporalFastLEDDemo/) | FastLED CRGB integration with GRB byte-order mapping and 5-phase BFI. | FastLED |
| [PackedBFIMapDemo](examples/PackedBFIMapDemo/) | Demonstrates packed BFI maps — nybble-pair encoding halves per-pixel BFI storage from 4 bytes to 2. | Library only |
| [HyperTeensy_Temporal_Blend](examples/HyperTeensy_Temporal_Blend/) | Full production sketch — ObjectFLED parallel output, RawHID+Serial USB, independent solver/calibration headers. | ObjectFLED |
| [Teensy_Temporal_Calibration](examples/Teensy_Temporal_Calibration/) | Calibration capture sketch — drives LED states for host-side colorimetric measurement via serial protocol. | ObjectFLED |

### Build Status

`build_report.py` runs on every PIO build and generates a table of all example build sizes and status.

See [BUILD_REPORT.md](BUILD_REPORT.md) for the latest MCU firmware build results and [TOOLS_COMPILE_REPORT.md](TOOLS_COMPILE_REPORT.md) for the Python tools compile-check report.

## Calibration & Tools Workflow

The library ships with default solver headers suitable for demo/testing, but production use requires device-specific calibration. The measurement and tuning workflow produces the firmware-ready headers that the solver loads.

### 1. Capture Fill8 & Blend8 States

Drive the LEDs through fill8 (static 0–255) and blend8 (floor/ceiling/bfi) states using the calibration sketch and `host_calibration_gui` on the host. A colorimeter (i1Display Pro / i1Studio) measures CIE XYZ for each state. This characterizes the physical response of the specific LED hardware — not color correction, but capturing what the diodes actually produce at each drive level and temporal blend configuration. `Host calibration gui assumes Argyll drivers are accessible. known to work with v3.5.0 and should be added to environmental variables PATH "{DIRECTORYPATH}\Argyll_V3.5.0\bin"`

### 2. Prune & Interpolate

Process raw captures through outlier detection (monotonicity violations, BFI-direction violations, chromaticity drift, high variance). Flagged states are either pruned or marked for recapture. Optionally interpolate missing states using a five-axis synthesis-dominant blending model that combines empirical nearest-neighbor interpolation with a physics-informed temporal blend prior, preserving monotonicity through progressive clamping.

### 3. Build Temporal Ladder (temporal\_lut\_tools\_v15)

The LUT builder produces MCU-ready artifacts from the pruned/interpolated dataset:

- **Solver headers** — per-channel `LadderEntry` arrays with `(outputQ16, value, bfi)` tuples plus `LADDER_*_LOWER` floor arrays. Configurable bucket count (e.g. `--max-entries 4096` for 12-bit resolution).
- **Precomputed headers** — full LUT tables that can be loaded into RAM at boot, avoiding runtime solving.
- **Transfer curves** — tunable tone-mapping with linear, gamma, BT.1886, HLG, PQ, sRGB, and toe-gamma presets. Configurable max nits, bucket count, shadow lift, shoulder, and floor/nearest selection.
- **Calibration headers** — per-channel Q16→Q16 LUTs for input calibration (1D color correction).

### 4. Capture RGBW Patch Set

Generate a True16 patch plan (`temporal_lut_tools` or `generate_patch_plan_true16_comprehensive_v6.py`) covering the RGBW color space — neutral corridors, chromatic sweeps, hue-family spreads, and impossible-state ramps. Capture patches using the same `host_calibration_gui` and colorimeter workflow.

### 5. Build RGBW Color LUT

Use `rgbw_lut_gui.py` (or the CLI `build_measured_rgbw_lut.py`) to build a 3D cube LUT from measured RGBW patches. The solver fits measured RGBW→XYZ basis vectors with bounded ΔE and hue-shift constraints, supporting both RGBW strips (with measured white optimization) and RGB-only exports. Output formats include:

- **3D cube headers** — flat C arrays for on-device trilinear interpolation
- **Binary cubes** — raw uint16 for PSRAM/SD/QSPI flash loading
- **1D calibration headers** — per-channel correction in the same format as the temporal ladder calibration

## Tools

Host-side Python tools supporting the calibration and LUT-building pipeline. All tools live under [`tools/`](tools/).

| Tool | Description |
|------|-------------|
| [Rendering Model & Interpolation Pipeline](tools/README_RENDERING_MODEL.md) | Reference document — physical BFI rendering model, temporal blend equations, 5-axis synthesis-dominant interpolation, monotonic clamping, progressive registration, and hardware timing. |
| [Host Calibration GUI](tools/host_calibration_gui/) | Tkinter application that drives the Teensy\_Temporal\_Calibration sketch and an ArgyllCMS colorimeter (`spotread`) to capture fill8, blend8, and Fill16 LED state measurements. Supports plan import/export, pause/resume, and progress reports. |
| [RGBW Capture Analysis & LUT Builder](tools/rgbw_lut_builder/) | CLI + GUI toolset for analyzing RGBW capture data, fitting measured RGBW→XYZ basis vectors, building 3D cube LUTs (C header and binary), and exporting 1D calibration headers. Includes CIE 1931 chromaticity plotting, white-slice analysis, histogram visualization, and a 3D cube viewer. |
| [Temporal Brightness Visualizer](tools/temporal_brightness_visualizer/) | Standalone visualizer for temporal monotonic ladders and 16-bit brightness distribution. Generates interactive HTML reports with per-channel charts. |
| [Temporal LUT Tools](tools/temporal_lut_tools/) | Core CLI + GUI for the temporal ladder pipeline — capture-plan generation, solver-header export, precomputed-header export, transfer-curve generation, and calibration-header export. |
| [Temporal Ladder Family Viewer](tools/temporal_ladder_family_viewer/) | Per-family drill-down viewer for temporal LUT outputs — inspect individual value/BFI families, monotonicity, and inter-family transitions. |
| [Temporal Ladder Tuning Tool](tools/temporal_ladder_tuning_tool/) | Prune, interpolate, and repair raw capture data. Combines pruned and interpolated outputs into a clean dataset ready to feed back into Temporal LUT Tools for final header export. |
| [Comprehensive Patch Plan Generator](tools/comprehensive_patch_plan/) | Generate True16 RGBW patch plans covering neutral corridors, chromatic sweeps, hue-family spreads, and impossible-state ramps for colorimetric capture. |

## Building with PlatformIO

The library includes a `platformio.ini` with environments for all examples:

```bash
# Build everything
pio run

# Build a single example
pio run -e FrameworkDemo

# Build just the demos (no production sketches)
pio run -e FrameworkDemo -e RGB16InputDemo -e PrecomputeDemo
```

All demo environments target Teensy 4.0 at 816 MHz with LTO. The `HyperTeensy` environment additionally requires ObjectFLED and uses a custom USB descriptor for combined RawHID + Serial.

## Hardware Requirements

- **Minimum**: Any Arduino-compatible board with ≥64 KB RAM (for 4096-entry LUTs)
- **Recommended**: Teensy 4.0/4.1 (1 MB RAM, 600+ MHz ARM Cortex-M7)
- **Parallel output**: ObjectFLED (Teensy), FastLED (ESP32/Teensy), or I2SClocklessLedDriver (ESP32/S3)
- **Target LED refresh rate**: ≥600 Hz (5 phases × ≥120 Hz perceived frame rate)

## License

See [LICENSE](LICENSE) for details.
