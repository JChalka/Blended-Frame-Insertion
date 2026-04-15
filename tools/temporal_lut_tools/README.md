# Temporal LUT Tools — Workflow Guide

CLI (`temporal_lut_tools.py`) and GUI (`temporal_lut_tools_gui.py`) for
building per-channel temporal ladders and transfer-curve LUTs used by the
TemporalBFI firmware.

---

## 1. Generate a Ladder Measurement Plan

Create a patch plan that lists every ladder state the host needs to capture.

- **Channel scope** — generate for a single channel or all channels at once.
- **Custom preset** — set upper/lower step sizes to control ladder density.
- **Mode** — choose *Black Frame Insertion* or *Temporal Blend*.
- **Max BFI** — sets the maximum BFI divisor (e.g. Max BFI 4 → cycle length 5).

The output is a CSV patch plan ready for import into the host capture GUI.

## 2. Capture Ladder States

Import the generated plan into the host GUI and run the capture sweep.
Each ladder state is measured in sequence and written to a capture directory.

## 3. Build the Temporal LUT

Once captures are complete, point **Measurement Dir** to the ladder-capture
folder and run **Build LUT**. This produces:

- Per-channel temporal and monotonic ladders
- XY capture data
- LUT summary JSON

On completion the GUI loads previews and the LUT summary automatically.

## 4. Export the Solver Header

Click **Export Solver Header** to emit the C++ header consumed by the
firmware solver.

Optionally, point **Solver Source Header** to the exported header and run
**Precompute Solver LUT Header** — this writes a precomputed LUT that can
be baked into flash instead of computing the solver LUT at boot time.

---

## Visualization — Transfer Curve Tab

Generate gamma / tone-mapping transfer curves and export them as firmware
headers.

### Curve types

| Curve | Notes |
|-------|-------|
| Linear | Identity mapping |
| Gamma | Power-law — uses the **Gamma** box |
| PQ | SMPTE ST 2084 perceptual quantizer |
| HLG | ARIB STD-B67 hybrid log-gamma |
| BT.1886 | ITU-R BT.1886 EOTF |
| sRGB-ish | Piece-wise sRGB-like curve |
| Toe-Gamma | Gamma with a toe region — uses the **Gamma** box |

### Key parameters

| Parameter | Applies to | Description |
|-----------|------------|-------------|
| **Gamma** | Gamma, Toe-Gamma | Power exponent |
| **Shadow Lift** | All curves | Raises the shadow floor |
| **Shoulder** | All curves | Soft roll-off near peak |
| **Bucket count** | All curves | Number of output buckets; `0` derives the count from solver outputs |
| **Bucket selection** | All curves | Choose bucket states by *floor* or *nearest* |
| **Per-channel tuning** | All curves | Tune across all channels together or independently |
| **Peak Nits override** | All curves | Overrides the measured peak-nits value for curve generation |
| **Nit cap** | All curves | Clamps all channels based on the highest measured channel, preserving the overall curve shape |

> **Peak Nits override ≠ Nit cap.** Peak Nits override changes the
> reference point used to generate the curve; Nit cap hard-clamps the
> output while keeping the curve shape intact.

### Export

Set a custom output directory and file names, then export. Large ladder
state counts may result in longer export times.
