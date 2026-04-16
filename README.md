# TemporalBFI

Temporal rendering framework for addressable LED strips, providing sub-8-bit brightness resolution through Blended Frame Insertion (BFI). By rapidly alternating between two brightness levels across a multi-phase display cycle, the library achieves 16-bit equivalent perceived output using only 8-bit LED drivers. In the industry this is typically known as Temporal Dithering or FRC (Frame Rate Control). The main distinction (and why I chose to call it Blended Frame Insertion) is that we introduce a larger cycle length allowing for finer control.

> **[Skip to How It Works](#how-it-works)** if you want to jump straight to the technical overview.

## Project Background

Around 6 years ago I had built up a sparse peripheral display from 5x5mm WS2812 LEDs, which quickly evolved into ordering APA102-2020s and creating a custom circuit with 576 LEDs per eye. ([V1](https://www.reddit.com/r/ValveIndex/comments/cqbnmp/a_comprehensive_guide_on_how_to_augment_a_wider/) — V2 found here: [V2](https://www.reddit.com/r/ValveIndex/comments/cw635m/peripheral_fov_led_mod_v2_improved_led_placement/) — the eventual v3 custom flex circuit had issues from being designed as a matrix that was too dense and didn't account for radius bends, pictures may be available in imgur)

I was in talks with some attorneys at Microsoft about the possibility of obtaining a license/permission to sell HMD sparse peripheral displays as they had done research on this and held a patent over the rendering methods. Funds ran dry on my end and I had tabled moving forward with licensing/working on the FOV design any further.

Flash forward to 3/24/24 I had been browsing AliExpress for addressable LEDs as I was interested in the current offerings and stumbled across 1212 & 1010 sized addressable SK6805 (NeoPixel protocol). I ordered a 100 sample package so that I could see how small they actually were in person and laugh a bit about how tiny they were. My good friend ttsgeb (aka moth) had mentioned that a 10x10 matrix could fit within about half an inch footprint, and then jokingly said "you could have 10\*10 displays in keyboard keys..." to which I responded that I would make at least an 8x8 and then place by hand.

LEDs arrived. They were *tiny*. About the size of a grain of sand. I quickly spun up an 8x8 matrix within KiCad, uploaded it to a board fab, and in a week or so received the first prototype matrix boards.

First boards were placed by hand using tweezers, generally speaking given the size of the LEDs themselves this was a nightmare. I spent a lot of time dealing with alignment issues and burning diodes with hot air. I started having my contact from the factory that produced the LEDs send my orders directly to JLC so that they could handle placement but this increased cost and overall time it took to receive boards.

Flash forward a few months and I was able to afford a pick and place machine. At the time the LumenPnP (at the time called the IndexPnP) was still in the early stages and I wanted a production-ready machine so I chose the NeodenYY1 which I ordered directly from Neoden as well as a Controleo3 reflow oven so that I could do more board-placement in-house and not worry about the increased cost/time associated with having the fab house place things for me and hold onto all my parts. I also had purchased an Elegoo Mars 5 Ultra which allowed me to start printing finer detailed parts that could be used with the LEDs, as well as the BambuLabs P1S which was a large improvement over my old SV01 that had been sitting around for a few years collecting dust.

The pick and place + desktop reflow + resin printer + FDM printer allowed me to enter a much more sane workflow in where I could design boards, design enclosures/functional parts that could hold PCBs and other objects, and actually quickly iterate on designs with the only wait time now being the fab house producing boards or awaiting filament/resin/part shipments.

This led to the creation of the first-joked-about 8x8 LED Matrix per key macropad. This started off as a 3x3 prototype based on the Teensy 4.1, and I had ordered 97500 LEDs to work with so I could iterate over some time and nail down designs then possibly have a small production run. The 3x3 macropad comprised of SK6805-EC10 keycaps with APA102-2020 LEDs on the base PCB to handle lighting outside of the keycaps on the main board itself. This was functional but there was an odd mix and match of LED types that I wasn't a fan of so later iterations moved towards strictly using SK6805-EC10.

Somewhere along the line I switched from Teensy 4.1 as the main MCU to the ESP32-S3. Cost was the main decision maker for this change, and the ESP32-S3 also boasts a fast dual-core architecture that already supported most things I was using the Teensy for. Generally speaking I tend to use FastLED for its fast math functions and driver capabilities and it supported both platforms which made the switch easy.

I had spent a month or so working to port I2SClocklessVirtualLED driver from the ESP32 to the ESP32-S3 but couldn't exactly wrap my head around the transposition logic and never got my implementation fully working, although I could manually display pixels correctly if I wrote a buffer, the transposition logic I had setup or buffer arrangement wasn't exactly correct which displayed noisy pixels. Yves/hpwit eventually added support for the ESP32-S3 and I dropped my port of their code and started using the main source again which allowed me to build a [5x6 macropad utilizing 32 8x8 matrices](https://www.reddit.com/r/FastLED/comments/1gslqo4/latest_project_macropad_with_8x8_panels_in_the/) (30 keycaps, 128 LEDs for underkeycap lighting/underglow).

After assessing build costs I decided for now not to move forward with selling 5x6 macropads. The idea has not been shelved entirely, but the LED stock I had has been used on ~1200 8x8 matrices designed to be used with 1.27mm pin headers instead of the FFC approach the macropad uses. These are available to purchase on Tindie from the RGKeeB store (8x8 SK6805-EC10 matrix with 1.5mm pixel pitch, data in/out very small footprint).

The biggest issue I had with the macropad given that it had 64 LEDs per keycap was that the heat output from each panel made each keycap physically hot to the touch. Not only were the keycaps hot, they were *bright*. Which generally speaking made things uncomfortable to look at.

Around 7/15/2024 I had begun implementing Black Frame Insertion with the goal of reducing the displayed brightness while maintaining 8 bit color resolution. This worked well, *very well*. Not only did it lower the overall brightness, it also reduced LED warmth and reduced power draw considerably which allowed me to run the 5x6 macropad from a single USB-PD source with a 5v10a stepdown and keep power draws within ~25w–45w. Moving forward I had & continue to use Black Frame Insertion as a way to help manage brightness with strict 8 bit resolution, and planned to eventually move this to an ambilight system where it very much made sense to use as my largest gripe with the typical ambilight system is that brightness of the LEDs tends to be much larger than the screen they surround creating a jarring visual effect where the screen is no longer the main focus.

Around the end of January 2026 I finally had ordered everything needed to build an ambilight system for my living room and setup a simple HyperTeensy (HyperHDR HyperSerial AWA protocol based implementation on the Teensy 4.0) driver with ObjectFLED to drive my ambilight system and implemented black frame insertion. At this point things were still static BFI. No dynamic changes in the pixel loop, just strict black frame insertion with a configurable 0...4 BFI level. This quickly evolved into exploring new approaches to black frame insertion like scene-brightness detection & highlight detection which got implemented as ways to increase/decrease the BFI level given what was going on from the HyperHDR output.

This worked fairly well — on darker scenes BFI would decrease → allow more vanilla light usage, bright scenes → BFI increase → keep LEDs less bright than the main screen. But it was still a fairly rough implementation. This eventually evolved into the thought of "well, instead of controlling black frame insertion on a per-pixel basis statically across the whole display, what if we dynamically change black frame insertion on a per-subpixel basis for more granularity?"

The first prototypes did not derive from any kind of physics-based real world measurements, merely using luma weights and some crude tools to guess monotonicity based off expected output based on luma weights that were guessed based off of Rec709 standards + inclusion of a white LED as the ambilight system uses RGBW SK6812. This wasn't perfect, it was certainly functional, but it took a lot of manual tweaking/clamping to get things to work in a way that (while not correct) did not cause visual artifacts. Seeing how I had purchased a Calibrite Display Pro HL a few years ago to calibrate my displays I started wondering how beneficial it would be to just start measuring states and seeing how that data could be helpful in the dynamic black frame insertion system instead of guessing states based on luma weights.

This was the first real step towards the current library state. I started looking at black frame insertion as a way to gain resolution instead of a way to just reduce the overall brightness of the LEDs while maintaining actual 8 bit resolution. This is where the initial creation of Temporal LUT Tools had begun. I begrudgingly began to prompt GPT/VS Code Copilot about developing tools that would allow me to capture the states of the LEDs and eventually after telling the LLM they were wrong about things a bunch, a usable toolset was produced. I'm not well versed in Python so the tools are mostly written by the LLMs with me providing input on the actual rendering system and how things work (I find they tend to be wrong a lot and it takes a lot of steering to get something actually usable out of them, essentially my first time trying to develop a project using LLMs as I tend to find LLM use detractive from growing as a developer).

At this point the first set of usable tools were there, but this was still strictly-speaking a black frame insertion rendering model. I was only capturing states switching between a lower floor of 0 and an upper ceiling of 1–255. This allowed for true ~12 bit resolution spread over a quantized 16 bit space, certainly much more resolution than raw 8 bit outputs but not anywhere close to the current resolution possible.

Once the black frame insertion temporal ladders were built I started to explore outlier detection, color calibration, transfer curve generation, which all eventually made its way into a custom HyperHDR fork that I have hosted in another repository here on GitHub. Took a lot of tweaking but I got things to a point where I was fairly happy with the image on screen. The transfer curves in particular played a huge role in moving away from "scene aware BFI shifts and highlight detection" — there's still some remnants of this with the HyperTeensy RawHID modified AWA protocol as well as that sketch in particular (and the HyperHDR fork). These days I recommend entirely relying on transfer curves for brightness/highlight tuning based off measured nits.

Of course once I started to become happy with the black frame insertion rendering model I naturally went towards thinking "well, what next?" and started instead thinking of the rendering model as a temporal blend model that could be used to gain even greater resolution increases. The toolset at the time of thinking was essentially already geared towards the new rendering model idea, the only main change was that I needed to stop thinking of things in terms of strict black-frame insertion where the floor was always 0 and instead think of things as "lower floor value" "upper ceiling/input value" and "amount of frames blended within the cycle length" which led to the creation of the current toolset and workflow.

## How It Works

Each display cycle consists of `cycle_length` phases (default 5). Within one cycle, a pixel distributes phases between two brightness levels:

- **(cycle\_length − bfi)** phases display the **upper value** (ceiling)
- **bfi** phases display the **lower value** (floor)

The perceived output integrates over the full cycle, producing fine-grained brightness steps between adjacent 8-bit levels. A 4096-entry per-channel temporal ladder maps every Q16 (0–65535) target to the optimal `(value, bfi, lowerValue)` tuple, selected from physically measured LED states.

### Phase Distribution Modes

The library supports three phase distribution modes that control *when* upper vs lower frames are emitted within a cycle:

**FixedMask (legacy, default)** — A compile-time 5-bit bitmask (`PHASE_EMIT_MASK`) determines which of the 5 fixed phases show the upper value. This is backward-compatible with all existing captures, calibration data, and the HyperTeensy production sketch. However, some BFI levels produce uneven clustering — for example BFI 3 yields an `ULLUL` pattern where two upper frames appear consecutively instead of being maximally spaced. The resulting brightness levels are distinct and measurably correct, but the cadence doesn't produce a true 1:1 interleaved blend ratio at every level.

**Distributed (recommended)** — Each BFI level defines its own natural cycle of length `bfi + 1`: one upper frame followed by `bfi` lower frames. This produces a simple, predictable pattern:

| BFI | Pattern | Cycle | Duty (Q8) |
|-----|---------|-------|-----------|
| 0   | `U`     | 1     | 256       |
| 1   | `UL`    | 2     | 128       |
| 2   | `ULL`   | 3     | 85        |
| 3   | `ULLL`  | 4     | 64        |
| 4   | `ULLLL` | 5     | 51        |

No configuration is needed — the cycle length is derived automatically from the BFI level. The number of usable BFI levels is bounded only by `MAX_SUPPORTED_CYCLE_LENGTH` (16), giving BFI 0–15.

**DistributedGlobal (advanced)** — A Bresenham-style algorithm distributes upper and lower frames as evenly as possible across a configurable global cycle length (2–16). For any BFI level, no two upper frames appear back-to-back unless there are more upper frames than lower. The cycle length is set via `setCycleLength()` (e.g. cycle length 8 gives BFI levels 0–7). This mode is useful when a uniform global cadence is required but is not needed for typical use.

```cpp
// Legacy mode (default — no changes needed for existing code):
solver.setPhaseMode(PhaseMode::FixedMask);

// Recommended distributed mode (per-BFI natural cycle):
solver.setPhaseMode(PhaseMode::Distributed);

// Advanced: Bresenham-even global cycle:
solver.setPhaseMode(PhaseMode::DistributedGlobal);
solver.setCycleLength(8);  // 8-phase global cycle → BFI 0..7

// Render loop uses the internal tick counter:
solver.renderBFI_RGBW(upper, floor, bfiG, bfiR, bfiB, bfiW, display, count);
showLEDs();
bool cycleEnd = solver.advanceTick();  // returns true on cycle boundary
```

The static `renderSubpixelBFI_*()` methods remain unchanged and always use FixedMask — existing sketches don't need modification. The new instance `renderBFI_*()` methods use the configured phase mode and internal tick counter.

## Features

- **True 16-bit rendering** — 4096+ distinct brightness levels per channel from 8-bit LED hardware
- **RGBW & RGB support** — white extraction from RGB, direct RGBW input, or white-limit clamping
- **Calibration-aware pipeline** — optional per-channel Q16 input calibration for device-specific correction
- **Transfer curves** — pluggable gamma/tone-mapping curves (linear, gamma, BT.1886, HLG, PQ, sRGB, toe-gamma)
- **Precomputed or runtime solving** — LUTs can be computed at boot or loaded from PROGMEM headers
- **Distributed phase scheduling** — per-BFI natural cycle (1 upper + N lowers) with automatic duty derivation; optional Bresenham-even global-cycle mode for advanced use; legacy FixedMask mode preserved as default
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
| `setCubeLUT3D(const CubeLUT3D*)` | Attach a loaded 3D cube for runtime color correction |
| `setCubeLUT3DEnabled(bool)` | Enable/disable the 3D cube LUT stage in the pipeline |
| `cubeLUT3DEnabled()` | Query whether the cube LUT stage is active |
| `applyCubeLUT3D(rQ16, gQ16, bQ16)` | Trilinear lookup through the attached cube, returns `RgbwTargets` |
| `setPhaseMode(mode)` | Set phase distribution: `FixedMask` (legacy), `Distributed` (per-BFI cycle), or `DistributedGlobal` (Bresenham-even) |
| `setCycleLength(len)` | Set global cycle length for DistributedGlobal mode (2–16) |
| `advanceTick()` | Step the internal tick counter; returns `true` on cycle boundary |
| `resetTick()` | Reset the internal tick counter to 0 |
| `channelActiveOnCurrentTick(bfi)` | Query whether a BFI level shows upper on the current tick |
| `renderBFI_RGBW(...)` | Instance render using configured phase mode + internal tick (RGBW, separate BFI maps) |
| `renderBFI_RGB(...)` | Instance render using configured phase mode + internal tick (RGB, separate BFI maps) |
| `renderBFI_RGBW_Packed(...)` | Instance render using configured phase mode + internal tick (RGBW, packed BFI map) |
| `renderBFI_RGB_Packed(...)` | Instance render using configured phase mode + internal tick (RGB, packed BFI map) |
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

### CubeLUT3D

Platform-agnostic 3D color-correction cube loader and trilinear interpolation engine. Cubes can be loaded from SD card binary files, PROGMEM header arrays, or external QSPI flash.

| Method / Field | Description |
|----------------|-------------|
| `attach(data, gridSize, channels)` | Attach a non-owning pointer to an existing cube buffer |
| `loadFromFileBuffer(buf, len)` | Parse a 4-byte header + payload from a raw file buffer |
| `lookup(rQ16, gQ16, bQ16, out[])` | Trilinear interpolation — writes 3 (RGB) or 4 (RGBW) uint16 results |
| `isValid()` | Returns `true` if data is attached and grid/channels are set |
| `isRGBW()` | Returns `true` if `channels == 4` |
| `dataBytes(grid, ch)` | (static) Payload size in bytes for a given grid and channel count |
| `fileBytes(grid, ch)` | (static) Total file size (4-byte header + payload) |
| `maxGridForBytes(bytes, ch)` | (static) Largest grid that fits within a byte budget |
| `parseHeader(hdr, grid, ch)` | (static) Read grid size and channel count from a 4-byte LE header |

Binary cube format: `[uint16 gridSize LE][uint16 channels LE][N³ × C × uint16 payload LE]`

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
| [CubeLUT3DDemo](examples/CubeLUT3DDemo/) | Demonstrates loading & using rgbw_lut_builder Cube LUTS at runtime. Includes SD binary & header array loading. | Library + SD.h |
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

- **3D cube headers** — PROGMEM C arrays for on-device trilinear interpolation
- **Binary cubes** — raw uint16 for PSRAM/SD/QSPI flash loading
- **1D calibration headers** — per-channel correction in the same format as the temporal ladder calibration

### 6. Import External 3D LUTs (optional)

If you have an RGB 3D LUT from an external calibration tool (DisplayCAL, DaVinci Resolve, ArgyllCMS, etc.), use `cube_to_header.py` to convert a standard `.cube` file into a CubeLUT3D-compatible binary and/or PROGMEM C++ header. This lets you use any display profiling workflow — not just the built-in RGBW capture pipeline — to produce the 3D color correction cube that the library loads at runtime.

## Tools

Host-side Python tools supporting the calibration and LUT-building pipeline. All tools live under [`tools/`](tools/).

| Tool | Description |
|------|-------------|
| [Rendering Model & Interpolation Pipeline](tools/README_RENDERING_MODEL.md) | Reference document — physical BFI rendering model, temporal blend equations, 5-axis synthesis-dominant interpolation, monotonic clamping, progressive registration, and hardware timing. |
| [Host Calibration GUI](tools/host_calibration_gui/) | Tkinter application that drives the Teensy\_Temporal\_Calibration sketch and an ArgyllCMS colorimeter (`spotread`) to capture fill8, blend8, and Fill16 LED state measurements. Supports plan import/export, pause/resume, and progress reports. |
| [RGBW Capture Analysis & LUT Builder](tools/rgbw_lut_builder/) | CLI + GUI toolset for analyzing RGBW capture data, fitting measured RGBW→XYZ basis vectors, building 3D cube LUTs (PROGMEM C header and binary), and exporting 1D calibration headers. Includes CIE 1931 chromaticity plotting, white-slice analysis, histogram visualization, and a 3D cube viewer. |
| [Cube to Header Converter](tools/cube_to_header/) | CLI tool to convert standard `.cube` 3D LUT files (from DisplayCAL, Resolve, ArgyllCMS, etc.) into CubeLUT3D-compatible binary and PROGMEM C++ headers. Supports RGB and RGBW cubes. |
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
