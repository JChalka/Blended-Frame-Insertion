# RGBW LUT Builder / Capture Analysis

This repository currently contains the first-generation RGBW capture-analysis and measured RGBW LUT tools. The current hosted code is still useful for analyzing RGBW patch captures, experimenting with measured white usage, and exporting RGB/RGBW cubes for device testing.

The project direction has changed substantially from the original README: the long-term target is a standalone, model-guided, measurement-corrected LUT builder for RGB, RGBW, TemporalBFI, and arbitrary multi-emitter LED packages.

## Current repository status

The code currently hosted here is still the original/legacy builder family. It is **not yet** the final standalone `rgbw_lut_builder` architecture described below.

Current repo focus:

```text
RGBW capture analysis
measured-basis white extraction experiments
coarse RGB cube solve + dense LUT export
interactive tkinter/matplotlib GUI
True16 calibration header export
binary RGB/RGBW cube export
RGB mode with W folded back into RGB
```

Current roadmap focus:

```text
model-guided topology solve
measurement-corrected response fields
strict RGB / RGBW sub-gamut modes
explicit WX / white-overdrive model families
capture-cloud simplex correction
first-class pass/fail + response-learning dictionaries
tetrahedral / coefficient-tetra runtime LUTs
standalone package + CLI + GUI
RGB, RGBW, RGBCCT, RGBY/RGBV, RGBY+W, and arbitrary emitter profiles
```

In other words, this repo is currently the working/legacy toolkit, while the next standalone builder is intended to replace the old solver core and carry forward the useful infrastructure.

---

## Why the direction changed

The original tools asked a narrow question:

> How much white can be used while preserving measured color accuracy and avoiding obvious over-whitening of saturated hues?

That was a useful starting point, but it also made the builder behave like a partially measured, partially guessed white-extraction LUT. The newer direction treats the LUT builder more like a display-correction tool:

```text
math model = physical/topological prediction axis
patch captures = real-world correction field
pass/fail dictionary = measured truth override
local line/triangle/simplex solve = shared primitive for prediction and correction
multi-emitter packages = layered simplex composition, not unconstrained N-channel solving
```

The model should be good enough to produce a sane initial LUT and define legal topology. Measurements then correct the model for actual LED packages, wall/diffuser optics, capture geometry, low-end behavior, channel response, and display profile quirks.

---

## Current tools in this repository

### Capture analyzer

```powershell
python rgbw_capture_analysis/analyze_rgbw_captures.py
```

Reads RGBW patch-capture CSVs, derives measured Lab/LCh values from captured XYZ, and writes:

```text
per-row metrics CSV
summary JSON
white usage vs measured chroma/hue plots
empirical hue/chroma white-usage envelopes
family sweep plots where RGB is fixed and W is stepped
```

Common options:

```text
--input-dir
--output-dir
--white-x / --white-y / --white-Y
--min-measured-y
--top-family-count
```

### Prototype measured-white solver

```powershell
python rgbw_capture_analysis/prototype_measured_white_solver.py
```

Fits measured RGBW → XYZ basis vectors from pure-channel sweeps and compares classic `w = min(rgb)` extraction against a bounded-error measured-basis solver.

Common options:

```text
--max-delta-e
--max-hue-shift
--grid-size
--sample-scale
--include-value-zero
```

### LUT builder CLI

```powershell
python rgbw_capture_analysis/build_measured_rgbw_lut.py
```

Solves a coarse regular RGB cube with the measured-basis bounded-error solver, then upsamples into a dense LUT and exports C headers.

Important options:

```text
--coarse-grid-size
--full-grid-size
--max-delta-e
--max-hue-shift
--target-white-balance-mode reference-white
--neutral-classic-chroma
--neutral-classic-fade-width
--measured-prior-mode family
--measured-prior-neighbors
--measured-family-count
--measured-prior-strength
--nondegenerate-regularization
--sample-scale
--skip-full-lut
--skip-header
--emit-classic-header
--header-name
--header-grid-size
```

### Interactive GUI

```powershell
python rgbw_capture_analysis/rgbw_lut_gui.py
```

The GUI wraps the capture loading, solver settings, output export, and visualization workflow.

Current GUI features include:

```text
reference white controls
color constraints
neutral region settings
measured prior settings
grid sizes
RGBW/RGB channel mode
CIE 1931 chart overlays
white-gain histogram
white slice heatmaps
coarse-grid comparison table
3D viewer
header export
True16 calibration header export
binary cube export
persistent settings
output summary loading
```

---

## Current export formats

### True16 calibration header

The GUI can export per-channel 1D calibration LUTs in the `TemporalBFICalibrationTrue16` namespace format consumed by `calibrateInputQ16ForSolver()` in the TemporalBFI solver library.

The output includes:

```text
LUT_R_16_TO_16[]
LUT_G_16_TO_16[]
LUT_B_16_TO_16[]
LUT_W_16_TO_16[]
per-channel metadata
True16LUTSet accessor helpers
```

The True16 export is intentionally a 1D per-channel ladder, not a full 3D cube. It is the correct export when matching dense temporal ladder state counts.

### Binary cube export

The GUI can write a raw little-endian binary cube for PSRAM / SD / flash loading:

```text
uint16 grid_size
uint16 channel_count
uint16 cube[grid_size][grid_size][grid_size][channel_count]
```

Current practical Teensy 4.1 PSRAM guidance remains:

```text
N≈100 with one 8 MB PSRAM chip for RGBW16
N≈120–125 with two 8 MB PSRAM chips for RGBW16
RGB mode is smaller because it stores three channels instead of four
```

### RGB mode

The current repo supports an RGB output mode for strips without a W diode. In the current legacy solver, RGB mode folds the allocated W back into RGB on export:

```text
R_out = R + W
G_out = G + W
B_out = B + W
```

In the future standalone builder, RGB will become its own first-class three-primary solve rather than an RGBW solve with W folded away.

---

## What is changing in the standalone builder

The next standalone builder should keep the useful GUI/export/capture plumbing, but replace the old solver core.

### Current hosted solver

The current hosted builder is based around:

```text
measured RGBW basis fitting
bounded-error white extraction
classic min(rgb) neutral bias
measured family prior blending
coarse cube solve
dense/trilinear-style export paths
```

This can be useful, but it does not fully model:

```text
named source gamuts as first-class targets
linear-light LED LUT contracts
strict RGB/RGBW topology legality
out-of-hull projection shared between builder and verifier
separate strict vs overdrive model families
capture-cloud local simplex correction
arbitrary emitter packages
```

### New solver direction

The standalone builder is moving toward:

```text
linear RGB in declared source gamut
→ model projection into device gamut
→ strict RGB / RGBW / multi-emitter topology solve
→ optional WX / white-overdrive model family
→ measured response provider
→ measured capture-cloud correction
→ pass/fail and response-learning override
→ tetrahedral / coefficient-tetra LUT output
```

The LED LUT is intended to operate on **linear-light RGB** in a declared gamut. Upstream tone mapping, HDR/DV handling, video-gamut remapping, and transfer curves should remain outside the LED LUT unless a legacy/test mode explicitly bakes them in.

---

## Math model roadmap

### RGB-only

RGB-only devices are the simple three-emitter case:

```text
linear RGB in selected source gamut
→ project/map into measured RGB triangle
→ solve R/G/B only
```

This is the correct path for RGB strips and RGB SPI chipsets such as APA102 or HD108 when no W diode exists.

### Strict RGBW sub-gamut

For RGBW packages, the W diode sits inside the measured RGB triangle and divides the device hull into:

```text
RGW
RBW
BGW
```

Strict mode is the topology-safe default. It only emits legal vertex, edge, or sub-gamut combinations:

```text
black
R, G, B, W
RG, RB, BG
RW, GW, BW
RGW, RBW, BGW
```

In strict mode, arbitrary four-channel RGBW output is not allowed.

### WX / white-overdrive modes

WX modes are opt-in white-extraction / brightness-overdrive models. They intentionally allow four-channel output, but do so through constrained virtual-primary solves rather than unconstrained RGBW optimization.

Planned/current WX taxonomy:

```text
strict_subgamut              default topology-safe RGBW solve
wx_radial_virtual            radial virtual-primary white-overdrive model
wx_virtual_axis_maxbright    virtual-axis max-brightness / high-W model
wx_lp_legacy                 direct LP max-white endpoint / reference model
```

These modes are useful for wallwash / ambilight / HDR-style use cases where higher W participation and brightness headroom can be beneficial, as long as verification/correction data shows the residuals are predictable.

### Capture-cloud simplex correction

The same primitive appears in WX and measured correction:

```text
known point = XYZxyY + output channel tuple + source/trust metadata
target lies inside a valid line/triangle/simplex
solve barycentric/simplex weights
expand weights back into output channels
score dE, dY, topology, headroom, and trust
```

The measured correction field should rank local measured triangles/simplexes instead of blindly trusting the first candidate.

Correction ladder:

```text
exact verifier pass
→ measured local triangle/simplex correction
→ measured edge/pair correction
→ measured channel-ramp correction
→ math model prediction
→ hardcoded fallback
```

### Multi-emitter layered simplex

The standalone builder is intended to support more than RGBW without turning into an unconstrained N-channel optimizer.

Emitter classification:

```text
outer emitter:
    expands or defines the measured hull

inner emitter:
    lives inside the measured hull and becomes an alternate anchor

edge emitter:
    lies on or near an existing hull edge and can be treated as a hull refinement or constrained edge anchor
```

Examples:

```text
RGBCCT:
    solve RGB + warm white
    solve RGB + cool white
    blend/solve between those inner-anchor results

RGBY+W:
    yellow expands the outer hull
    white remains an inner anchor
    solve the measured outer-hull fan against W

RGBV+W:
    violet may expand the blue/red side of the hull
    W remains an inner anchor
```

The core rule is:

```text
extra emitters change the point set and layer order;
they do not force an unconstrained N-channel solve.
```

---

## Virtual reference hull and response learning

A later extension is the virtual reference hull / virtual-emitter profile layer.

Instead of solving every LUT node against a huge CIE-wide reference hull, the builder can preprocess the display/emitter profile:

```text
measured physical hull
→ slightly expanded virtual reference hull
→ remap measured emitters into reference-space virtual emitters
→ solve all LUT nodes against stored virtual emitters
→ expand back to physical channel tuples
→ let correction decide where expansion helped or hurt
```

This is useful for edge cases where strict physical hull rules are too conservative. For example, a yellow target sitting on an `RG` edge may still benefit from a tiny W contribution in a wall/diffuser setup. The virtual profile gives the solver permission to test that, while measured correction can back it off if W drags the result inward too much.

The pass/fail dictionary should also evolve into a learning response model:

```text
CorrectionResponseProfile:
    display profile
    emitter profile
    model family
    active channel family
    drive path signature
    expected xyY curve
    measured xyY curve
    residual vectors
    dE / dY trend
    headroom limits
    known good / bad regions
    recommended next probes
```

The goal is for calibration to become adaptive:

```text
generate candidate
compare to learned response curve
predict whether adding/removing a channel helps
capture the smallest useful probe
update the response curve
repeat only where uncertainty remains high
```

---

## Interpolation and runtime direction

The future builder should emit LUTs that are intended for tetrahedral interpolation by default.

Why tetrahedral:

```text
trilinear can blend all eight cell corners
tetrahedral uses one selected tetrahedron
for RGBW/multi-emitter topology this reduces illegal blended channel participation
```

Planned runtime formats:

```text
vertex_tetra:
    store output values at cube vertices
    smallest storage
    more runtime math/fetches

coefficient_tetra:
    precompute per-cell tetrahedral affine coefficients
    larger storage
    faster MCU/SBC runtime path
```

This matters for ESP32-S3, ESP32-P4, Teensy 4.x, SBCs, and other targets where PSRAM/storage/runtime cost must be balanced.

Approximate RGBW16 storage:

```text
vertex_tetra size ≈ grid_size^3 * 4 channels * 2 bytes
coefficient_tetra size ≈ (grid_size - 1)^3 * 6 tetra * 4 terms * 4 channels * bytes_per_coeff
```

---

## Where the standalone builder fits

The new standalone `rgbw_lut_builder` is planned as the consolidation point for the spread-out tools.

It should carry forward:

```text
current GUI settings/profile/export plumbing
capture loading conventions
worker and memory-aware LUT build utilities
NumPy memmap output helpers
summary JSON / diagnostics patterns
binary cube export patterns
True16 / TemporalBFI export concepts
host calibration GUI UDP capture protocol
verifier/pass-fail feedback banks
```

It should refactor or replace:

```text
legacy Delaunay as the default solver
hardcoded ramp arrays
RGB mode as W-foldback instead of a true RGB solve
implicit gamut assumptions
trilinear-default runtime assumptions
one-off pass/fail hints
unconstrained or loosely constrained white-extraction behavior
```

It should keep as legacy/reference:

```text
Delaunay point-cloud solver
LP measured-white / wx_lp_legacy reference mode
older GUI toggles that are useful for comparison
existing capture-analysis scripts
```

No ETA is attached here. The intent of this README is to make it clear that the current repo is still the first-generation builder, while the active design direction is the standalone model-measured builder.

---

## Planned standalone repository shape

The exact layout may change, but the rough structure is:

```text
rgbw_lut_builder/
  README.md
  README_MATH_MODEL.md
  pyproject.toml

  rgbw_lut_builder/
    gui/
    model/
      gamuts.py
      rgb_model.py
      rgbw_model.py
      topology.py
      projection.py
      virtual_reference_hull.py
      virtual_emitter_profile.py
      emitter_classification.py
      layered_simplex.py
      wx_modes.py
      simplex.py
      interpolation/
        tetrahedral.py
        tetra_coefficients.py
        fixed_point.py

    response/
      base.py
      hardcoded_ramps.py
      fill16_ramps.py
      temporal_bfi.py
      hybrid.py
      multi_emitter_profile.py

    captures/
      schemas.py
      loaders.py
      validators.py
      spotread_protocol.py
      udp_client.py

    correction/
      residuals.py
      correction_field.py
      measured_simplex.py
      triangle_ranker.py
      response_profiles.py
      observed_response_curve.py
      pass_fail_dictionary.py
      live_retry.py

    build/
      model_only.py
      offline_measured.py
      live_measured.py
      lut_writer.py
      diagnostics.py

    verify/
      verifier.py
      metrics.py
      reports.py

    output/
      rgb8.py
      rgb16.py
      rgbw8.py
      rgbw16.py
      channels16.py
      temporal_bfi_encoder.py
      binary_cube_export.py
      coefficient_cube_export.py
      mcu_header_export.py

    legacy/
      delaunay_builder.py
      lp_solver_adapter.py
```

---

## Roadmap phases

The rough plan is:

```text
1. repository split and cleanup
2. RGB and RGBW model unification
3. measured response provider abstraction
4. model-vs-capture diagnostics
5. multi-emitter layered simplex support
6. offline correction field
7. live UDP active calibration
8. output backend generalization
9. adaptive capture planning
```

The current GitHub repo sits before that standalone split. It contains useful legacy/capture/export tooling, but the standalone builder is where the new model architecture should be implemented.

---

## Practical guidance for current users

Use the current repo when you want to:

```text
analyze existing RGBW captures
experiment with measured white extraction
build/export the existing coarse/dense LUTs
generate True16 calibration headers
generate binary RGB/RGBW cubes for device testing
inspect capture behavior in the GUI
```

Expect the future standalone builder to be the better target when you need:

```text
strict gamut-aware RGB/RGBW output
separate strict vs WX white-overdrive models
Rec.709 / Rec.2020 / P3 / native linear-light behavior
TV/display-primary-aware target gamuts
capture-cloud correction
arbitrary emitter profiles
RGBCCT / RGBY / RGBV / RGBY+W support
tetrahedral coefficient runtime LUTs
live adaptive calibration
```

---

## Design note

The older builder can be summarized as:

```text
measured RGBW captures
→ bounded white extraction
→ neutral bias / measured prior
→ coarse cube
→ exported LUT
```

The newer builder direction is:

```text
declared linear source gamut
→ topology-aware math model
→ calibrated response provider
→ measured correction field
→ pass/fail and response-learning override
→ tetrahedral RGB/RGBW/channels LUT
```

That shift is the main reason the roadmap now extends beyond SK6812-style RGBW strips into RGB-only devices, TemporalBFI response backends, RGBCCT packages, yellow/violet gamut-expanding packages, and arbitrary emitter counts.
