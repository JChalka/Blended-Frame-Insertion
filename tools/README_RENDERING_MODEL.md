# Temporal BFI Rendering Model & Interpolation Pipeline

## 1. Physical Rendering Model

The temporal BFI (Blended Frame Insertion) system renders LED output using a phase-cycle architecture. Each display cycle consists of `cycle_length` phases (default 5, corresponding to `MAX_BFI_FRAMES + 1`). Within one cycle, a blend8 state distributes phases between two brightness levels:

- **(cycle_length − bfi)** phases display the **upper value** (ceiling)
- **bfi** phases display the **lower value** (floor)

The perceived colorimetric output integrates over the full cycle:

$$\vec{C}_\text{blend} = \frac{(\text{cycle} - \text{bfi}) \cdot \vec{C}_\text{upper} + \text{bfi} \cdot \vec{C}_\text{lower}}{\text{cycle}}$$

where $\vec{C} = (X, Y, Z)$ in CIE 1931 colorimetry. This is a linear temporal blend model — the eye integrates the two brightness levels over the refresh period, producing a weighted average.

### 1.1 Operating Modes

| Mode | lower_value | upper_value | bfi | Description |
|------|-------------|-------------|-----|-------------|
| `fill8` | 0 | 0–255 | 0 | Static brightness anchor. All phases show `upper_value`. |
| `blend8` | 0–255 | 0–255 | 1–4 | Temporal blend between floor and ceiling levels. |

A **state** is the 5-tuple `(channel, mode, lower_value, upper_value, bfi)`.

- **Channels**: R, G, B, W for RGBW capture/calibration. Runtime render paths now also define 5-channel RGBWW/RGBCCT-style layouts (`W1/W2` or CCT-style dual white) with either emulated fifth-channel behavior or native fifth-channel LUT storage.
- **fill8 anchors** at `(channel, "fill8", 0, v, 0)` define the absolute colorimetric response at each 8-bit level. These are the ground truth for all interpolation.
- **blend8 states** span the 4D space of `(lower_value, upper_value, bfi)` per channel, producing fine-grained brightness steps between adjacent fill8 levels.

### 1.2 State Space Geometry

For a single channel with `max_bfi = 4`:

- 256 fill8 anchors (v = 0..255)
- Up to `(256 × 255 / 2) × 4 = 130,560` blend8 states when only physically meaningful `lower_value < upper_value` pairs are counted
- The **span** of a blend8 state is `upper_value − lower_value`

The fill8 anchors form the monotonic backbone: $Y_\text{fill8}(v)$ must be non-decreasing in $v$.

Each blend8 state's Y is bounded:

$$Y_\text{fill8}(\text{lower}) \leq Y_\text{blend8}(\text{lower}, \text{upper}, \text{bfi}) \leq Y_\text{fill8}(\text{upper})$$

## 2. Capture & Measurement Pipeline

### 2.1 Raw Captures

A colorimeter (typically i1Display Pro / i1Studio) measures CIE XYZ for each state driven by the Teensy. Captures are CSV files with columns including:

```
name, mode, r, g, b, w, lower_r..lower_w, upper_r..upper_w, bfi_r..bfi_w,
repeat_index, ok, returncode, elapsed_s, X, Y, Z, x, y
```

Multiple capture sessions produce multiple CSVs. A state may be measured multiple times across sessions (repeat captures).

### 2.2 Outlier Pruning (`analyze` command)

The pruning pipeline operates in multiple passes:

1. **Multi-pass outlier detection**: Flags states with monotonicity violations, BFI-direction violations, floor-tolerance violations, upper-residual anomalies, xy chromaticity drift, and xy spread.
2. **Repeat averaging**: After pruning flagged states, remaining rows for each state are averaged — X, Y, Z, x, y, and elapsed_s are mean-averaged across repeats. Output is one row per surviving state.
3. **Chunk writing**: Filtered output is written in chunked CSV files with `extrasaction="ignore"` to tolerate unexpected fields.

Output: pruned capture CSVs + a JSON report of flagged findings + a recapture plan CSV for flagged states.

### 2.3 Measurement Summarization

Before interpolation, pruned captures are summarized into `CaptureMeasurementSummary` objects:

- Per-state **median** of X, Y, Z across all rows
- **std_Y**: sample standard deviation of Y (used for high-variance flagging)
- **samples**: number of measurement rows
- **repeats**: maximum repeat_index seen

The median provides robustness against residual outliers that survived pruning.

## 3. Interpolation Pipeline

### 3.1 Goal

Most blend8 states in the 4D space are never physically measured — they are interpolated from the measured states. The interpolation step produces synthetic capture rows that fill the gaps, creating a dense dataset for the downstream LUT solver.

### 3.2 Measurement Repair

Before interpolation, existing measurement summaries undergo multi-pass monotonic repair:

1. Build constraint indexes from all summaries
2. For each state, compute Y bounds from neighbors and fill8 anchors
3. If `median_Y` violates bounds, scale the full XYZ vector to the midpoint of the valid range
4. Repeat up to 4 passes until no further repairs are needed

This ensures the measured data itself is monotonically consistent before being used as interpolation anchors.

### 3.3 Prediction: Five-Axis Synthesis-Dominant Blending

For each missing blend8 state, `_predict_xyz_for_state` independently predicts X, Y, and Z.

Axes 1–4 are **empirical axes**: each linearly interpolates between the two nearest measured (or previously-interpolated) points along one dimension of the state space. Their median forms the empirical prediction.

Axis 5 is the **physics-informed synthesis model**. When available, it is blended 50/50 with the empirical median rather than entering the median pool as a single vote. This prevents progressive-registration echo — a cascade where each freshly-interpolated state is registered as a neighbor for the next, causing empirical axes to copy the previous state's clamped value and drown out the physics model.

#### Axis 1 — Upper-value interpolation (same lower, same bfi)

Fix `(channel, mode, lower_value, bfi)`. Interpolate along the `upper_value` dimension using linear interpolation between the two nearest measured points.

#### Axis 2 — Lower-value interpolation (same span, same bfi)

Fix `(channel, mode, span, bfi)` where `span = upper − lower`. Interpolate along the `lower_value` dimension. This leverages the observation that states with the same span and bfi produce similar Y regardless of absolute position.

#### Axis 3 — BFI interpolation (same lower, same upper)

Fix `(channel, mode, lower_value, upper_value)`. Interpolate along the `bfi` dimension. This captures the temporal blend progression for a specific floor/ceiling pair.

#### Axis 4 — Cross-floor interpolation (same upper, same bfi)

Fix `(channel, mode, upper_value, bfi)`. Interpolate along the `lower_value` dimension. This captures how raising the floor affects the blend for a given ceiling and BFI count.

#### Axis 5 — Fill8 synthesis model (physical prior)

For blend8 states with `bfi > 0`, compute the physically-predicted XYZ using the temporal blend model from §1:

$$\vec{C}_\text{synth} = \frac{(\text{cycle} - \text{bfi}) \cdot \vec{C}_\text{fill8}(\text{upper}) + \text{bfi} \cdot \vec{C}_\text{fill8}(\text{lower})}{\text{cycle}}$$

This axis requires both fill8 anchors to exist for the target's lower and upper values. It acts as a **physics-informed prior** that anchors predictions to the correct magnitude when empirical data is sparse.

#### Fallback — Inverse-distance weighting

If none of the 5 axes produce a prediction, a fallback uses the 6 nearest states in the same `(channel, mode)` space, weighted by inverse distance. BFI distance is scaled by 96× to reflect its outsized physical effect.

#### Why 50/50 synthesis blending instead of pure median?

Early iterations added the synthesis prediction as one of N values in the median pool. With 4 empirical axes and 1 synthesis axis, the median was almost always dominated by the empirical values. Because progressive registration feeds each interpolated state back as a neighbor for the next, the 4 empirical axes tend to **echo** the previous state's (clamped) Y — producing exact duplicates at consecutive upper_values.

The 50/50 blend gives the physics model equal weight to all empirical evidence combined:

$$\hat{C}_\text{metric} = \frac{1}{2} C_\text{synth} + \frac{1}{2} \text{median}(C_\text{emp,1} \ldots C_\text{emp,k})$$

This ensures each consecutive `upper_value` gets a distinct predicted Y (since the fill8 anchors differ), while still allowing empirical axes to correct for LED non-linearities that the linear temporal model does not capture.

When synthesis is not available (fill8 states, states where an anchor is missing), the pure empirical median is used unchanged.

### 3.4 Monotonic Y Clamping

After prediction, each state's Y is clamped to monotonic bounds computed from:

- **Fill8 floor anchor**: $Y \geq Y_\text{fill8}(\text{lower})$
- **Fill8 ceiling anchor**: $Y \leq Y_\text{fill8}(\text{upper})$ (for blend8 states)
- **Nearest measured neighbors** along each axis (previous ≤ target ≤ next)
- **Cross-floor neighbors**: same (upper, bfi), varying lower — increasing lower must give increasing Y

When Y is clamped, the full XYZ vector is **proportionally scaled** to the target Y, preserving chromaticity (x, y coordinates).

If the lower bound exceeds the upper bound (conflicting constraints), Y is set to the midpoint.

### 3.5 Progressive Registration

Each interpolated state is immediately registered into the measurement indexes after emission. This means later interpolations can use earlier interpolated states as neighbors, enabling the interpolation to "fill in" progressively from measured anchors outward.

The emission order (dense state rows sorted by channel → lower → bfi → upper) ensures that states near measured data are interpolated first, providing high-quality anchors for states further from measurements.

## 4. Downstream: LUT Solver

The combined dataset (pruned real captures + interpolated synthetic captures) feeds the solver/tooling pipeline, which computes:

1. **Transfer curves** — Q16 (0–65535) monotonic mappings from input to measured/target output. Runtime defaults to a single shared transfer curve; legacy per-channel curves remain available when calibrated channel-specific tone mapping is required.
2. **RGBW calibration headers** — per-channel gain/offset profiles for the LED driver
3. **Solver profiles / precomputed solver LUTs** — value, BFI, floor, and optional output-Q16 tables for runtime solving

The solver consumes the state-space XYZ data and produces firmware artifacts (.h headers with `PROGMEM` arrays) that the MCU can load at boot. Per-channel solver LUTs remain the calibrated-output default. A separate opt-in shared solver LUT mode stores and precomputes exactly one solver LUT set and reuses it for all logical channels; this is a low-memory / bringup / approximate mode, not a calibrated-output replacement.

### 4.1 3D Color Correction Cubes

For full-gamut color correction beyond per-channel 1D calibration, the pipeline supports 3D cube LUTs loaded through the `CubeLUT3D` interface. Two paths exist:

- **Measured RGBW/RGBWW cubes** — Built by `rgbw_lut_gui.py` / `build_measured_rgbw_lut.py` from colorimeter-measured patch sets. These capture the LED hardware's actual color response and produce RGBW (4-channel) or RGBWW/RGBCCT-style (5-channel) cubes optimized for white-channel or dual-white extraction. Headers are emitted with `PROGMEM` to reside in flash.

- **External `.cube` files** — Standard RGB 3D LUTs from any profiling tool (DisplayCAL, DaVinci Resolve, ArgyllCMS, CalMAN, etc.) can be converted to CubeLUT3D-compatible binary or PROGMEM headers via `cube_to_header.py`. This allows users to leverage existing display calibration workflows without requiring the full RGBW capture pipeline.

Both paths produce data in the same interleaved Q16 format consumed by `CubeLUT3D::attach()` and `CubeLUT3D::loadFromFileBuffer()`. RGB cubes use trilinear interpolation. Four-channel and five-channel output paths use tetrahedral interpolation in the runtime lookup layer because strict multi-emitter solves can otherwise cross illegal topology inside the measured sub-gamut.

## 5. Diagnostic Metrics

### 5.1 Outlier Detection Passes

| Pass | Check | Recommended Action |
|------|-------|--------------------|
| monotonic | Y not increasing with upper_value at fixed (lower, bfi) | prune |
| bfi_direction | Y not decreasing with bfi at fixed (lower, upper) | prune |
| lower_floor | Y below fill8 floor anchor minus tolerance | prune |
| upper_residual | Y deviates from expected by more than threshold | recapture |
| xy_drift | Chromaticity (x,y) deviates from channel median | recapture |
| xy_spread | Max chromaticity spread within a state exceeds threshold | recapture |
| capture_high_variance | std_Y disproportionately large (>1% of channel peak) | recapture |

### 5.2 Interpolation Statistics

| Stat | Meaning |
|------|---------|
| `states_already_present` | Requested states that already have measured data |
| `states_interpolated` | States successfully predicted and emitted |
| `states_unresolved` | States where no axis could produce a prediction |
| `states_clamped` | States where predicted Y was adjusted to monotonic bounds |
| `source_states_repaired` | Measured states adjusted during pre-interpolation repair |

## 6. Hardware Timing & Driver Architecture

### 6.1 Reference Configuration

The current calibration target uses SK6812 RGBW strips with the following parameters:

| Parameter | Value |
|-----------|-------|
| LED type | SK6812 RGBW |
| Nominal data rate | 800 kHz |
| Overclocked data rate | 1120 kHz (`leds.begin(1.4, 100)`) |
| Latch delay | 100 µs |
| Strip length | 48 LEDs |
| Parallel output lines | 25 |
| Minimum LED refresh rate | ≥600 Hz (5 phases × ≥120 Hz perceived frame rate) |

The overclock factor of 1.4× shortens the bit period, reducing per-strip transmission time and enabling higher frame rates at the cost of tighter signal integrity margins. The 100 µs latch delay is the reset period between frames.

### 6.2 Frame Rate Budget

For NeoPixel-protocol LEDs (~800 kHz class), the number of blended frames that can be inserted per display cycle is proportional to:

1. **Strip length** — longer strips take more time per frame
2. **Render/calculation loop tightness** — any per-frame computation must complete within the inter-frame budget
3. **Parallel output count** — more parallel lines reduce total wall-clock time per frame

For SPI / high-speed LEDs (≥10 MHz), the data transfer is fast enough that the bottleneck shifts to per-cycle computation throughput on the MCU.

> **Phase timing note:** The current reference implementation relies on SK6812 transmission time (~800 kHz–1.12 MHz per bit) as an implicit phase timer — each `showLEDs()` call takes long enough that phases are naturally spaced at consistent intervals without explicit timing control. For faster LED chipsets (≥10 MHz SPI class such as APA102, SK9822, HD108, etc.), the transmission completes in a fraction of the time, and the phase cadence becomes dominated by loop jitter and computation variance. In these cases, **explicit phase timing** (e.g. a hardware timer interrupt or `delayMicroseconds()` guard) is required to ensure consistent inter-phase intervals. Without it, uneven phase spacing will cause visible flicker and incorrect temporal blend ratios.

#### 6.2.1 Show Cadence Window (too fast vs too slow)

Correct BFI rendering requires keeping `showLEDs()` calls within a valid cadence window:

- **Too fast (over-submission):** If the LED backend returns before physical output has completed and does not enforce an internal in-flight lock, calling `showLEDs()` again can queue/overwrite while the prior frame is still shifting out. This can cause partial updates, frame tearing, and end-of-strip flicker.
- **Too slow (under-submission):** If `showLEDs()` is delayed too long, phase refresh drops and the temporal blend cycle becomes visible. The observer sees shimmer/flicker/stepping because the eye is no longer integrating enough phase updates per perceived frame.

A practical implementation should enforce both bounds:

- **Minimum submission interval:** do not call `showLEDs()` again until at least one full frame transmission plus protocol latch/reset time has elapsed.
- **Maximum submission interval:** keep phase cadence high enough that temporal blending remains above flicker visibility (for 5 phases, commonly target at least ~600 Hz phase refresh for ~120 Hz perceived output).

Frame production and ingestion should also be rate-matched to the intended perceived refresh. If the content target is ~120 Hz perceived motion, generating/ingesting pattern frames far above ~120 FPS rarely improves image quality and usually just burns CPU cycles while increasing scheduling pressure.

On backends that provide a busy/in-flight status, prefer that signal over a fixed delay. When no status API exists, use a conservative microsecond interval guard derived from measured on-wire frame time.

On dual-core architectures (ESP32), the render loop should spin on a dedicated core with data preparation (LUT lookups, blend computation, incoming data processing) running on the other core. This separation is critical for sustaining ≥600 Hz LED refresh (≥120 Hz perceived) without frame drops.

### 6.3 Known High-FPS Parallel Output Drivers

#### FastLED

[FastLED](https://github.com/FastLED/FastLED) — the most widely used addressable LED library.

| Platform | Parallel mechanism | Max parallel strips |
|----------|-------------------|---------------------|
| ESP32 | I2S / LCD / ParallelIO peripherals | 16 |
| Teensy 4.0/4.1 | [ObjectFLED](https://github.com/KurtMF/ObjectFLED) / [OctoWS2811](https://www.pjrc.com/teensy/td_libs_OctoWS2811.html) integration | Full digital pin count |
| ESP32-S3 | LCD peripheral | 16 |
| ESP32-P4 | ParallelIO | 16 (expected) |

- **ObjectFLED** is a newer fork of OctoWS2811 that adds overclocking and fine-grained control of T0H, T1H, and latch timings for NeoPixel-type protocols. ObjectFLED can also be used independently of FastLED.
- Known functional targets: Teensy 4.0/4.1, ESP32, ESP32-S3, ESP32-P4.

#### I2SClocklessLedDriver (hpwit)

[I2SClocklessLedDriver](https://github.com/hpwit/I2SClocklessLedDriver) — targeted at I2S on ESP32 and LCD peripheral on ESP32-S3.

- Up to 16 parallel outputs for NeoPixel-style LEDs
- Includes advanced control features (timing tuning, buffer management)
- Can be used in conjunction with FastLED or standalone

#### I2SClocklessVirtualLedDriver (hpwit)

[I2SClocklessVirtualLedDriver](https://github.com/hpwit/I2SClocklessVirtualLedDriver) — same core architecture as I2SClocklessLedDriver, extended with shift-register multiplexing.

- Uses 15 data lines + 1 latch line to drive NeoPixel-style LEDs through shift registers
- Supports up to **120 parallel strips**
- Well-suited for the ESP32/S3 dual-core architecture driving very large LED counts
- The LCD peripheral is largely unchanged in ESP32-P4, so both I2SClockless drivers should port with minimal changes

#### Other Potentially Suitable Drivers

| Driver / Platform | Notes |
|-------------------|-------|
| [NeoPixelBus](https://github.com/Makuna/NeoPixelBus) | Parallel output support on ESP32 |
| [WLED](https://kno.wled.ge/) (NeoPixelBus backend) | By extension of NeoPixelBus parallel capabilities |
| STM32 MCUs (DMA + timer) | Parallel output via DMA to GPIO |
| Pi Pico / Pico 2 (RP2040/RP2350) | PIO state machines provide flexible parallel output |

### 6.4 General Hardware Requirements

Any device capable of the following should be able to drive the temporal BFI system:

- **Parallel output**: ~800 kHz–25 MHz on multiple pins simultaneously
- **Memory**: Sufficient RAM/flash/DMAMEM for solver LUT storage, transfer curves, render buffers, and LED backend buffers
- **Processing**: Fast enough to process incoming data and compute blended output within the per-cycle budget
- **Dual-core preferred**: Dedicated render core + data processing core for sustained high frame rates

### 6.5 MCU Memory Budgeting

TemporalBFI memory usage splits into two independent pools:

1. **Solver/transfer bucket tables**: fixed cost per configured bucket count, independent of LED count.
2. **Render state buffers**: per-pixel cost for upper/lower values, BFI maps, and the active display buffer.

The current True16 solver tables use three required `uint8_t[storage_channel_count][bucket_count]` arrays and one optional `uint16_t[storage_channel_count][bucket_count]` output-Q16 array:

```text
solverValueLUT       storage_channel_count x bucket_count x 1 byte
solverValueFloorLUT  storage_channel_count x bucket_count x 1 byte
solverBFILUT         storage_channel_count x bucket_count x 1 byte
solverOutputQ16LUT   storage_channel_count x bucket_count x 2 bytes  (optional)
```

`storage_channel_count` depends on solver LUT mode:

- **Per-channel mode (default):** `storage_channel_count = logical solver channel count`.
- **Shared mode (opt-in):** `storage_channel_count = 1`, and `precompute()` computes exactly one LUT set reused by every logical channel.

So the required solver table cost is:

```text
solver_bytes = bucket_count x storage_channel_count x 3 bytes
solver_bytes_with_output_q16 = bucket_count x storage_channel_count x 5 bytes
```

Transfer curves are now a separate storage choice. Runtime defaults to one shared `uint16_t[bucket_count]` transfer curve for all channels. Legacy per-channel transfer curves remain available:

```text
shared_transfer_bytes = bucket_count x 2 bytes
legacy_transfer_bytes = bucket_count x logical_channel_count x 2 bytes
```

These estimates describe storage only. Tables may live in RAM, DMAMEM, or flash/PROGMEM depending on the target and how the firmware is generated. If the tables are in PROGMEM, they primarily consume flash rather than runtime RAM.

Required solver tables plus the default shared transfer curve:

| Solver buckets | Shared solver + shared transfer | RGB per-channel + shared transfer | RGBW / emulated RGBWW + shared transfer | Native RGBWW/RGBCCT + shared transfer |
|---:|---:|---:|---:|---:|
| 256 | 1,280 B (1.2 KiB) | 2,816 B (2.8 KiB) | 3,584 B (3.5 KiB) | 4,352 B (4.2 KiB) |
| 512 | 2,560 B (2.5 KiB) | 5,632 B (5.5 KiB) | 7,168 B (7.0 KiB) | 8,704 B (8.5 KiB) |
| 1,024 | 5,120 B (5.0 KiB) | 11,264 B (11.0 KiB) | 14,336 B (14.0 KiB) | 17,408 B (17.0 KiB) |
| 2,048 | 10,240 B (10.0 KiB) | 22,528 B (22.0 KiB) | 28,672 B (28.0 KiB) | 34,816 B (34.0 KiB) |
| 4,096 | 20,480 B (20.0 KiB) | 45,056 B (44.0 KiB) | 57,344 B (56.0 KiB) | 69,632 B (68.0 KiB) |
| 8,192 | 40,960 B (40.0 KiB) | 90,112 B (88.0 KiB) | 114,688 B (112.0 KiB) | 139,264 B (136.0 KiB) |
| 16,384 | 81,920 B (80.0 KiB) | 180,224 B (176.0 KiB) | 229,376 B (224.0 KiB) | 278,528 B (272.0 KiB) |

For comparison, legacy per-channel transfer curves add `bucket_count x logical_channel_count x 2 bytes` instead of the default `bucket_count x 2 bytes`. Optional `solverOutputQ16LUT` adds `bucket_count x storage_channel_count x 2 bytes`.

RGBWW/RGBCCT cost depends on fifth-channel solve mode:

- **Emulated fifth channel:** W2 reuses W behavior, so solver LUT storage can remain RGBW-like if only four solver channels are precomputed/loaded.
- **Native fifth channel:** W2/CCT gets its own solver LUT storage in per-channel mode, increasing required solver storage from four to five channels.
- **Shared solver LUT mode:** RGB, RGBW, and RGBWW/RGBCCT all use one storage channel, but output accuracy becomes approximate unless the physical channels truly match the shared model.

#### 6.5.1 Per-Pixel Render Buffers

For RGB output, the core per-pixel buffers are:

```text
upperFrameBuffer   3 bytes/pixel  (G,R,B upper values)
lowerFrameBuffer   3 bytes/pixel  (G,R,B floor values)
displayBuffer      3 bytes/pixel  (active RGB frame sent to LED backend)
BFI maps, normal   3 bytes/pixel  (one uint8_t map per G,R,B channel)
BFI map, packed    2 bytes/pixel  (packed storage still uses two bytes/pixel)
```

For RGBW output, the core per-pixel buffers are:

```text
upperFrameBuffer   4 bytes/pixel  (G,R,B,W upper values)
lowerFrameBuffer   4 bytes/pixel  (G,R,B,W floor values)
displayBuffer      4 bytes/pixel  (active RGBW frame sent to LED backend)
BFI maps, normal   4 bytes/pixel  (one uint8_t map per G,R,B,W channel)
BFI map, packed    2 bytes/pixel  (two bytes hold four 4-bit BFI values)
```

RGB upper/lower solves cost 6 bytes per pixel before BFI storage. RGBW upper/lower solves cost 8 bytes per pixel. Normal BFI maps add one byte per active channel; packed BFI maps use 2 bytes per pixel in both RGB and RGBW modes.

For RGBWW/RGBCCT-style 5-channel output, the same pattern extends to five logical channels:

```text
upperFrameBuffer   5 bytes/pixel  (G,R,B,W1,W2 upper values)
lowerFrameBuffer   5 bytes/pixel  (G,R,B,W1,W2 floor values)
displayBuffer      5 bytes/pixel  (active 5-channel frame sent to LED backend)
BFI maps, normal   5 bytes/pixel  (one uint8_t map per logical channel)
BFI map, packed    3 bytes/pixel  (ceil(5 / 2) bytes hold five 4-bit BFI values)
```

Emulated RGBWW/RGBCCT can have RGBW-like solver LUT cost, but render buffers still carry five output channels when the physical LED layout has five emitters.

RGB buffer groups:

| Buffer group | Normal BFI maps | Packed BFI map |
|---|---:|---:|
| Upper + lower solve buffers only | 6 bytes/pixel | 6 bytes/pixel |
| BFI storage only | 3 bytes/pixel | 2 bytes/pixel |
| Upper + lower + BFI storage | 9 bytes/pixel | 8 bytes/pixel |
| Upper + lower + BFI + display buffer | 12 bytes/pixel | 11 bytes/pixel |

RGBW buffer groups:

| Buffer group | Normal BFI maps | Packed BFI map |
|---|---:|---:|
| Upper + lower solve buffers only | 8 bytes/pixel | 8 bytes/pixel |
| BFI storage only | 4 bytes/pixel | 2 bytes/pixel |
| Upper + lower + BFI storage | 12 bytes/pixel | 10 bytes/pixel |
| Upper + lower + BFI + display buffer | 16 bytes/pixel | 14 bytes/pixel |

RGBWW/RGBCCT buffer groups:

| Buffer group | Normal BFI maps | Packed BFI map |
|---|---:|---:|
| Upper + lower solve buffers only | 10 bytes/pixel | 10 bytes/pixel |
| BFI storage only | 5 bytes/pixel | 3 bytes/pixel |
| Upper + lower + BFI storage | 15 bytes/pixel | 13 bytes/pixel |
| Upper + lower + BFI + display buffer | 20 bytes/pixel | 18 bytes/pixel |

Example RGB render-buffer costs:

| Pixels | Upper + lower | Normal BFI maps | Packed BFI map | Upper/lower + normal BFI | Upper/lower + packed BFI | With display, normal BFI | With display, packed BFI |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 96 | 576 B | 288 B | 192 B | 864 B | 768 B | 1,152 B | 1,056 B |
| 1,200 | 7,200 B | 3,600 B | 2,400 B | 10,800 B | 9,600 B | 14,400 B | 13,200 B |
| 2,400 | 14,400 B | 7,200 B | 4,800 B | 21,600 B | 19,200 B | 28,800 B | 26,400 B |
| 3,000 | 18,000 B | 9,000 B | 6,000 B | 27,000 B | 24,000 B | 36,000 B | 33,000 B |

Example RGBW render-buffer costs:

| Pixels | Upper + lower | Normal BFI maps | Packed BFI map | Upper/lower + normal BFI | Upper/lower + packed BFI | With display, normal BFI | With display, packed BFI |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 96 | 768 B | 384 B | 192 B | 1,152 B | 960 B | 1,536 B | 1,344 B |
| 1,200 | 9,600 B | 4,800 B | 2,400 B | 14,400 B | 12,000 B | 19,200 B | 16,800 B |
| 2,400 | 19,200 B | 9,600 B | 4,800 B | 28,800 B | 24,000 B | 38,400 B | 33,600 B |
| 3,000 | 24,000 B | 12,000 B | 6,000 B | 36,000 B | 30,000 B | 48,000 B | 42,000 B |

Example RGBWW/RGBCCT render-buffer costs:

| Pixels | Upper + lower | Normal BFI maps | Packed BFI map | Upper/lower + normal BFI | Upper/lower + packed BFI | With display, normal BFI | With display, packed BFI |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 96 | 960 B | 480 B | 288 B | 1,440 B | 1,248 B | 1,920 B | 1,728 B |
| 1,200 | 12,000 B | 6,000 B | 3,600 B | 18,000 B | 15,600 B | 24,000 B | 21,600 B |
| 2,400 | 24,000 B | 12,000 B | 7,200 B | 36,000 B | 31,200 B | 48,000 B | 43,200 B |
| 3,000 | 30,000 B | 15,000 B | 9,000 B | 45,000 B | 39,000 B | 60,000 B | 54,000 B |

The packed BFI representation cuts RGBW BFI-map storage in half, from 4 bytes/pixel to 2 bytes/pixel. For RGB-only output it reduces BFI-map storage from 3 bytes/pixel to 2 bytes/pixel. For RGBWW/RGBCCT it stores five logical BFI values in 3 bytes/pixel. It does not reduce the upper/lower solve buffers or the active display buffer.

#### 6.5.2 Practical Memory Targets

For low-memory MCUs, the first large lever is the solver bucket count. The second is solver LUT storage mode. The third is whether transfer curves use the default shared curve or legacy per-channel curves. With the current default shared transfer curve, a 4,096-bucket RGB solver is about 44 KiB, RGBW/emulated-RGBWW is about 56 KiB, native RGBWW/RGBCCT is about 68 KiB, and shared solver LUT mode is about 20 KiB before render buffers. At 16,384 buckets those become about 176 KiB, 224 KiB, 272 KiB, and 80 KiB respectively.

For RAM-constrained targets, likely minimum viable profiles are:

| Target class | Suggested solver buckets | Transfer strategy | BFI map strategy | Notes |
|---|---:|---|---|---|
| Very small MCU | 256-1,024 | Shared transfer curve; consider shared solver LUT | Packed | Lowest RAM target; approximate shared-solver output may be acceptable for bringup. |
| Midrange MCU | 2,048-4,096 | Shared transfer curve; per-channel solver when RAM allows | Packed preferred | Good first target for ESP32-class RAM budgets. |
| Teensy 4.x RAM1/RAM2 split | 4,096-8,192 | Shared transfer default; legacy per-channel only when calibrated need justifies it | Normal or packed | Enough room for calibration experiments, but table placement matters. |
| High-memory / flash-table target | 16,384+ | Prefer PROGMEM/generated headers | Packed for large pixel counts | High solver precision; not suitable as pure RAM tables on small MCUs. |

Additional memory not included above: stack, serial/USB buffers, LED backend DMA/internal buffers, 3D cube LUTs, calibration profiles, UDP/network buffers on ESP-class devices, and any capture/debug telemetry retained at runtime.

### 6.6 Fail-Safe: Stale-Frame Protection

Because the BFI render loop continuously alternates between upper and floor frames, the LEDs always hold the contents of whichever sub-frame was most recently transmitted. If the MCU loses power, crashes, or otherwise stops driving the data lines while the LED supply remains live, the strip will latch the last transmitted frame indefinitely. Depending on where in the cycle the output stopped, this could be the upper frame (full brightness), the floor frame (dim), or a partially written buffer — any of which may be visually jarring and electrically wasteful.

Three mitigation approaches are outlined below, roughly in order of increasing suitability for larger installations.

#### Option A — Data-Line Reset Circuit (small setups)

Add a power-detect latch circuit on the LED data output line(s). The circuit monitors the MCU supply rail (or a GPIO "heartbeat" signal) and, when the MCU is detected as absent or non-responsive, pulls the data line low for longer than the LED reset period (~80 µs for WS2812/SK6812). This forces the strip to latch an all-zero (black) frame, clearing the display.

A minimal implementation is a single N-channel MOSFET or open-drain buffer with its gate/enable tied to the MCU power rail through a voltage divider or supervisor IC. When the rail drops, the MOSFET releases and a pull-down resistor holds the data line low. More robust designs use a dedicated voltage supervisor (e.g. TPS3839) with a watchdog timeout, so even a hung MCU that keeps its rail alive but stops toggling data will trigger the latch-off.

This approach works well for small to moderate strip counts where each data line can be individually gated. It becomes impractical at scale (dozens of parallel data lines) because each line needs its own reset circuit.

#### Option B — PSU Kill on Transmission Timeout (large setups, recommended)

Rather than resetting individual data lines, disable the LED power supply entirely when the MCU stops transmitting. A heartbeat GPIO (toggled every frame by the render loop) feeds a simple watchdog — either a discrete RC + comparator / voltage supervisor, or a small supervisory MCU (ATtiny, etc.). If the heartbeat stops for longer than a configurable timeout (e.g. 50–100 ms), the watchdog de-asserts the PSU enable line, cutting power to all LED strips simultaneously.

This is the more sensible approach for setups with many parallel data lines because a single watchdog protects the entire installation regardless of strip count. Re-enabling is automatic once the heartbeat resumes (or requires a manual reset, depending on the supervisor design).

#### Option C — Combined (belt-and-suspenders)

Use PSU-kill as the primary protection and add data-line reset circuits on a small number of critical strips (e.g. those visible during boot or power-on sequencing) so they blank immediately rather than waiting for the PSU timeout to expire.

None of these are strictly required for correct BFI operation, but at least one is strongly recommended for any installation where the LED power supply and MCU power supply are independently switched or fused.

## 7. Known Limitations & Design Decisions

1. **Linear temporal integration assumption**: The blend model assumes perfect temporal integration by the eye. Actual perception may depend on refresh rate, persistence, and individual visual sensitivity.

2. **Fill8 anchor dependency**: Axis 5 (synthesis) requires both fill8 anchors. If a fill8 level was not measured, the synthesis prediction is unavailable and the empirical axes alone must suffice.

3. **Chromaticity preservation during clamping**: When Y is clamped, X and Z are scaled proportionally. This preserves the chromaticity (x, y) but may introduce small absolute errors in X and Z if the true relationship is non-linear at the clamped Y level.

4. **Progressive interpolation ordering**: The fill-order determines which states benefit from already-interpolated neighbors. Different orderings could produce slightly different results for states far from measured data.

5. **Median vs. weighted mean**: The median was chosen over a weighted mean because it is more robust to outlier axes. However, when only 2 axes contribute, the median is just their average, which may not reflect the confidence difference between a well-sampled axis and a sparse one.
