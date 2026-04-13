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

- **Channels**: R, G, B, W — each calibrated independently.
- **fill8 anchors** at `(channel, "fill8", 0, v, 0)` define the absolute colorimetric response at each 8-bit level. These are the ground truth for all interpolation.
- **blend8 states** span the 4D space of `(lower_value, upper_value, bfi)` per channel, producing fine-grained brightness steps between adjacent fill8 levels.

### 1.2 State Space Geometry

For a single channel with `max_bfi = 4`:

- 256 fill8 anchors (v = 0..255)
- Up to 256 × 256 × 4 = 262,144 blend8 states (most physically meaningful when `lower_value < upper_value`)
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

The combined dataset (pruned real captures + interpolated synthetic captures) feeds the solver, which computes:

1. **Transfer curves** — per-channel Q16 (0–65535) monotonic mappings from 8-bit input to measured Y
2. **RGBW calibration headers** — per-channel gain/offset profiles for the LED driver
3. **Solver profiles** — tuned parameters for the runtime interpolation engine on the Teensy

The solver consumes the state-space XYZ data and produces the firmware artifacts (.h headers with `PROGMEM` arrays) that the Teensy loads at boot.

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

On dual-core architectures (ESP32), the render loop should spin on a dedicated core with data preparation (LUT lookups, blend computation, incoming data processing) running on the other core. This separation is critical for sustaining ≥600 Hz LED refresh (≥120 Hz perceived) without frame drops.

### 6.3 Known High-FPS Parallel Output Drivers

#### FastLED

[FastLED](https://github.com/FastLED/FastLED) — the most widely used addressable LED library.

| Platform | Parallel mechanism | Max parallel strips |
|----------|-------------------|---------------------|
| ESP32 | I2S / LCD / ParallelIO peripherals | 16 |
| Teensy 4.0/4.1 | ObjectFLED / OctoWS2812 integration | Full digital pin count |
| ESP32-S3 | LCD peripheral | 16 |
| ESP32-P4 | ParallelIO | 16 (expected) |

- **ObjectFLED** is a newer fork of OctoWS2812 that adds overclocking and fine-grained control of T0H, T1H, and latch timings for NeoPixel-type protocols. ObjectFLED can also be used independently of FastLED.
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
| WLED (NeoPixelBus backend) | By extension of NeoPixelBus parallel capabilities |
| STM32 MCUs (DMA + timer) | Parallel output via DMA to GPIO |
| Pi Pico / Pico 2 (RP2040/RP2350) | PIO state machines provide flexible parallel output |

### 6.4 General Hardware Requirements

Any device capable of the following should be able to drive the temporal BFI system:

- **Parallel output**: ~800 kHz–25 MHz on multiple pins simultaneously
- **Memory**: Sufficient RAM to store the LUT (per-channel Q16 transfer curves + blend lookup tables)
- **Processing**: Fast enough to process incoming data and compute blended output within the per-cycle budget
- **Dual-core preferred**: Dedicated render core + data processing core for sustained high frame rates

### 6.5 Data-Line Latch / Power-Detect Circuit

Because the BFI render loop continuously alternates between upper and floor frames, the LEDs always hold the contents of whichever sub-frame was most recently transmitted. If the MCU loses power, crashes, or otherwise stops driving the data lines while the LED supply remains live, the strip will latch the last transmitted frame indefinitely. Depending on where in the cycle the output stopped, this could be the upper frame (full brightness), the floor frame (dim), or a partially written buffer — any of which may be visually jarring and electrically wasteful.

**Recommended mitigation:** add a power-detect latch circuit on the LED data output line(s). The circuit monitors the MCU supply rail (or a GPIO "heartbeat" signal) and, when the MCU is detected as absent or non-responsive, pulls the data line low for longer than the LED reset period (~80 µs for WS2812/SK6812). This forces the strip to latch an all-zero (black) frame, clearing the display.

A minimal implementation is a single N-channel MOSFET or open-drain buffer with its gate/enable tied to the MCU power rail through a voltage divider or supervisor IC. When the rail drops, the MOSFET releases and a pull-down resistor holds the data line low. More robust designs use a dedicated voltage supervisor (e.g. TPS3839) with a watchdog timeout, so even a hung MCU that keeps its rail alive but stops toggling data will trigger the latch-off.

This is not strictly required for correct BFI operation, but is strongly recommended for any installation where the LED power supply and MCU power supply are independently switched or fused.

## 7. Known Limitations & Design Decisions

1. **Linear temporal integration assumption**: The blend model assumes perfect temporal integration by the eye. Actual perception may depend on refresh rate, persistence, and individual visual sensitivity.

2. **Fill8 anchor dependency**: Axis 5 (synthesis) requires both fill8 anchors. If a fill8 level was not measured, the synthesis prediction is unavailable and the empirical axes alone must suffice.

3. **Chromaticity preservation during clamping**: When Y is clamped, X and Z are scaled proportionally. This preserves the chromaticity (x, y) but may introduce small absolute errors in X and Z if the true relationship is non-linear at the clamped Y level.

4. **Progressive interpolation ordering**: The fill-order determines which states benefit from already-interpolated neighbors. Different orderings could produce slightly different results for states far from measured data.

5. **Median vs. weighted mean**: The median was chosen over a weighted mean because it is more robust to outlier axes. However, when only 2 axes contribute, the median is just their average, which may not reflect the confidence difference between a well-sampled axis and a sparse one.
