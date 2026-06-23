# Host Calibration GUI

`host_calibration_gui.py` is the Tkinter host application for the Temporal RGBW calibration workflow. It talks to the `Teensy_Temporal_Calibration` firmware over the TCAL USB serial protocol, renders RGBW states on the LED target, triggers ArgyllCMS `spotread`, and writes measurement artifacts for the downstream temporal ladder, RGBW model, 3D LUT, and verifier tools.

The current GUI is more than a simple capture runner. It now supports manual Fill8 / Blend8 / Fill16 rendering, resumable capture plans, spotread preset management, a UDP sparse-capture bridge for external builders, and an integrated LUT / FastLED analytical verifier with trilinear or tetrahedral interpolation, target-gamut selection, transfer selection, out-of-hull projection, and pass/fail CSV export.

The measured multi-emitter 3D LUT builder has grown into its own standalone project. This README keeps the host-side capture, verifier, and TCAL protocol details local, while the broader model-builder workflow lives in [Multi-Emitter-Color-Correction-3DLUT-Builder](https://github.com/JChalka/Multi-Emitter-Color-Correction-3DLUT-Builder).

## Requirements

- Python 3.10+
- `numpy`
- `pyserial`
- Tkinter, normally included with desktop Python builds
- [ArgyllCMS](https://www.argyllcms.com/) with `spotread` available on `PATH`
- A supported colorimeter, such as i1Display Pro, i1Studio, ColorMunki Display, or another ArgyllCMS-supported meter
- A Teensy running a compatible `Teensy_Temporal_Calibration` / TCAL firmware build

```bash
pip install numpy pyserial
```

## Quick Start

```bash
python host_calibration_gui.py
```

1. Connect the Teensy running the TCAL calibration firmware over USB.
2. Select the serial port and click **Connect Serial**.
3. Use **Hello**, **Ping**, or **Get State** to confirm the link.
4. Select an Argyll preset, or leave the default `spotread -x -O` for XYZ/xyY capture.
5. Choose a capture directory.
6. Either render and measure a manual state with **Measure Once**, import a measurement plan and click **Run plan**, or use the **LUT Verifier** tab to verify a 3D LUT / MCU analytical solve path.

## What the GUI does

The GUI has four main roles:

1. **Manual render host** — send Fill8, Blend8, or Fill16 states to the Teensy, commit them, control phase display, and run one-off measurements.
2. **Capture plan runner** — import or build CSV measurement plans, execute row × repeat captures, save measurement CSVs, and resume interrupted runs from `.progress.json` files.
3. **Sparse-capture bridge** — run a local UDP JSON server so external tools, including the standalone [Multi-Emitter-Color-Correction-3DLUT-Builder](https://github.com/JChalka/Multi-Emitter-Color-Correction-3DLUT-Builder), can ask the host to render RGBW16 patches and optionally capture them with the colorimeter.
4. **Verifier** — load an RGBW 3D LUT or use the firmware's analytical solver, measure a named/generated patch set, compare measured xy against expected source xy, and export verification results.

## GUI Layout

### Connection / transport controls

| Control | Purpose |
|---------|---------|
| **Serial port** | Dropdown of available COM ports. **Refresh** rescans. |
| **Baud** | Serial baud setting. Default is `30000000`, matching the high-speed Teensy calibration link. |
| **Connect Serial** | Opens the serial link and starts the RX listener thread. |
| **Hello** | Sends the TCAL hello request and logs the device response. |
| **Ping** | Sends a ping request and logs the response. |
| **Get State** | Requests the current render state from the firmware. |
| **Device output mode** | Selects the logical output mode requested from compatible firmware: RGB, RGBW, or RGBWW/RGBCCT. Unsupported physical targets return an explicit unsupported-mode status. |
| **Apply output mode** | Sends `OP_SET_OUTPUT_MODE` to the device and updates the displayed output-mode status from the response. |

### UDP capture server

The UDP capture row starts a host-side JSON RPC server. This is not a replacement for the serial device transport: the LED target still receives TCAL commands over USB serial. UDP is only a bridge so tools such as RGBW LUT builders can request a patch render or sparse measurement from another process.

| Control | Purpose |
|---------|---------|
| **UDP capture server host/port** | Bind address and port. Defaults to `0.0.0.0:19446`. |
| **Start UDP capture** | Starts the UDP JSON request listener. |
| **Stop UDP capture** | Stops the listener. |
| **Status label** | Shows whether the server is stopped or listening. |

Supported UDP request types include `status`, `ping`, `capture_rgbw16`, `render`, `set`, `set_rgbw16`, and `display_rgbw16`.

A request may provide RGBW data as any of the following:

- `rgbw16: [r, g, b, w]`
- `r16`, `g16`, `b16`, `w16`
- `rgbw8: [r, g, b, w]`
- `r`, `g`, `b`, `w`

For capture requests, the GUI renders the requested Fill16 RGBW state, runs `spotread`, returns the parsed measurement, and writes a local `udp_capture_<timestamp>_<name>.json` trace in the capture directory. Render-only requests set the output state but do not measure.

Optional request fields include `request_id` / `id`, `name`, `reply_host`, `reply_port`, `spotread_command`, `argyll_command`, `spotread_preset`, `measurement_preset`, `measurement_format`, or `measurement_mode`.

### Argyll / measurement controls

| Control | Purpose |
|---------|---------|
| **Argyll preset** | Selects a predefined `spotread` command. |
| **Apply** | Copies the selected preset into the editable command field. |
| **Argyll command** | The actual command used for measurements. The GUI automatically ensures `spotread` commands keep the one-shot `-O` flag. |
| **Capture dir** | Directory for plan CSVs, progress reports, one-off JSON measurements, UDP traces, and verifier exports. |
| **Settle s** | Delay after rendering before measurement and after commit. |
| **Timeout s** | Maximum time to wait for `spotread`. |
| **Cleanup stale before read** | Kills stale `spotread` processes before each measurement. |
| **Send newline trigger** | Sends a newline to `spotread` stdin, useful for interactive spotread modes. |
| **Show transport spam** | Shows low-level serial and UDP frame logging. Disabled by default to keep logs readable. |
| **Plan uses solver mode** | Enables the firmware's calibrated solver path for plan execution. Use this for True16 / Fill16 solver-driven plans. |
| **Kill stale spotread** | Manually terminates orphaned ArgyllCMS processes. |
| **Abort Measurement** | Cancels the active `spotread` process. |

Built-in spotread presets:

| Preset | Command | Notes |
|--------|---------|-------|
| `XYZxy (-x -O)` | `spotread -x -O` | Default. Captures XYZ and xyY-style values. |
| `Lab (-O)` | `spotread -O` | Parses XYZ plus Lab when available. |
| `LCh (-h -O)` | `spotread -h -O` | Parses XYZ plus LCh when available. |
| `Luv (-u -O)` | `spotread -u -O` | Parses XYZ plus Luv when available. |

### Resume controls

| Control | Purpose |
|---------|---------|
| **Resume row** | Row index to start from when resuming. Usually loaded from a progress report. |
| **Resume repeat** | Repeat index to start from within the row. |
| **Load report** | Loads a `.progress.json` sidecar from an interrupted or completed run. |
| **Resume status** | Shows the loaded progress report name. |

If the progress report records the original plan CSV path and the current GUI has no plan loaded, the GUI will try to reload that plan. If the path is missing or stale, it prompts for the original plan CSV.

## Render / Manual Control Panel

The manual panel can render quick patches without a CSV plan. It has two input tabs: **8-bit / Blend8** and **True16**.

### Modes

| Mode | Meaning |
|------|---------|
| **Fill8** | Sends static 8-bit RGBW values. Each channel is 0–255. |
| **Blend8** | Sends lower/floor RGBW values, upper/current RGBW values, and per-channel BFI counts. |
| **Fill16** | Sends 16-bit RGBW targets. Each channel is 0–65535. |

### Manual controls

| Control | Purpose |
|---------|---------|
| **R / G / B / W** | 8-bit upper/current values for Fill8 and Blend8. |
| **Floor R / G / B / W** | Blend8 lower/previous values. |
| **BFI R / G / B / W** | Per-channel BFI insertion counts. Current firmware constants expose 0–4 in the GUI. |
| **R16 / G16 / B16 / W16** | True16 Fill16 patch values. Moving these also updates the 8-bit preview values. |
| **W2 16** | Optional second white / CCT channel used only by the RGBWW/RGBCCT direct-output opcode. The host does not fold W2 into W. |
| **Phase mode** | Auto lets the Teensy cycle phases. Manual lets the host force a phase index. |
| **Phase index** | Manual phase value. The GUI supports the full phase-control range exposed by the firmware constant. |
| **Apply phase** | Sends the current manual phase index. |
| **Send State** | Sends the selected Fill8 / Blend8 / Fill16 state to the firmware. |
| **Temporal Fill16 (Direct RGBW16)** | Sends the current R16/G16/B16/W16 values through `OP_SET_FILL16`, the temporal companion's direct RGBW16 path. |
| **Temporal Direct RGBWW16** | Sends R16/G16/B16/W16/W2 16 through the RGBWW/RGBCCT direct opcode. Current 4-channel ObjectFLED targets reject this with unsupported-mode status. |
| **Commit** | Latches the currently staged state into the render pipeline. |
| **Clear** | Sends the firmware clear command. |
| **Measure Once** | Renders the manual state, commits it, waits for settling, runs `spotread`, and writes a `single_measure_<timestamp>.json` artifact. |

The preview boxes show a rough RGB display approximation of the upper/current state and, for Blend8, the lower/previous state. White is added into RGB for preview only; this is not a color-managed simulation.

## Measurement Plan Tab

The plan tab is for automated capture runs. A plan is a CSV containing one row per render state. Each row may be repeated multiple times.

| Control | Purpose |
|---------|---------|
| **Add current** | Adds the current manual render state to the plan. |
| **Import plan CSV** | Imports a legacy Fill8, raw Blend8, True16 Fill16, or generic plan CSV. |
| **Clear plan** | Clears all rows and resets resume state. |
| **Delete selected** | Deletes selected rows from the plan tree. |
| **Run plan** | Executes the plan from the configured resume row/repeat. |
| **Pause/Resume** | Pauses after the active measurement finishes, or resumes from pause. |
| **Stop** | Requests a stop and writes a progress report so the run can be resumed. |
| **Save plan CSV** | Saves the current plan rows with the generic schema. |

The tree view shows the row name, mode, RGBW8, RGBW16, BFI, lower/upper values, timing summary, and repeat count.

## Measurement Modes

### Fill8 — static 8-bit brightness

Each channel is driven at a single 8-bit level. This is useful for raw per-channel anchor captures and quick manual sanity checks.

### Blend8 — temporal blend capture

Each channel is represented by lower/floor values, upper/current values, and per-channel BFI insertion counts. The firmware renders the temporal state according to its current blend / BFI implementation. This mode is used for temporal ladder characterization and low-level display-behavior captures.

### Fill16 — True16 / solver-driven target values

Each channel receives a 16-bit target. In plan mode, **Plan uses solver mode** controls whether the firmware's solver is enabled before the run. In manual/verifier paths, Fill16 values are also used to drive RGBW outputs directly through the firmware protocol.

## Capture Plan CSV Format

The importer accepts older and newer schemas. Supported plan shapes include:

1. Legacy Fill8 rows with `name`, `r`, `g`, `b`, `w`, `bfi_r`, `bfi_g`, `bfi_b`, `bfi_w`, and `repeats`.
2. Raw Blend8 rows with `name`, `lower_r`…`lower_w`, `upper_r`…`upper_w`, and optional BFI/repeat columns.
3. True16 Fill16 rows with `name`, `r16`, `g16`, `b16`, `w16`, and optional repeat/mode columns.
4. Generic rows containing a `mode` column and any matching fields from the table below.

Generic schema fields written by **Save plan CSV**:

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Human-readable patch/state name. |
| `mode` | string | `fill8`, `blend8`, or `fill16`. |
| `repeats` | int | Measurements per row. Values below 1 are coerced to 1. |
| `r`, `g`, `b`, `w` | int | 8-bit current/upper values. |
| `lower_r`…`lower_w` | int | Blend8 lower/floor values. |
| `upper_r`…`upper_w` | int | Blend8 upper/current values. |
| `r16`…`w16` | int | 16-bit Fill16 targets. |
| `bfi_r`…`bfi_w` | int | Per-channel BFI values. |
| `use_fill16` | 0/1 | Explicit Fill16 compatibility flag. |

Rows normalize to one of `fill8`, `blend8`, or `fill16`. For Blend8 rows, the displayed `r/g/b/w` values are derived from the upper values, and the 16-bit preview values are upper × 257.

## Output: Plan Capture CSV

Each plan run writes a timestamped capture CSV in the capture directory. Plans containing any non-Fill8 rows use an `advanced` filename prefix.

| Column | Description |
|--------|-------------|
| `name`, `mode`, `use_fill16` | State identity and normalized mode. |
| `r`–`w` | 8-bit current/upper values. |
| `lower_*`, `upper_*` | Blend8 floor and ceiling values. |
| `r16`–`w16` | 16-bit target values. |
| `bfi_*` | Per-channel BFI values. |
| `repeat_index` | Zero-based repeat index. |
| `solver_mode` | Whether plan solver mode was enabled for the run. |
| `measurement_format` | Parsed Argyll output format. |
| `spotread_command` | Actual command used for this measurement. |
| `ok`, `returncode`, `elapsed_s`, `timed_out` | Measurement status. |
| `XYZ_X`, `XYZ_Y`, `XYZ_Z` | Parsed XYZ tristimulus values when present. |
| `xyY_Y`, `xyY_x`, `xyY_y` | Parsed xyY-style values when present. |
| `Lab_L`, `Lab_a`, `Lab_b` | Parsed Lab values when present. |
| `LCh_L`, `LCh_C`, `LCh_h` | Parsed LCh values when present. |
| `Luv_L`, `Luv_u`, `Luv_v` | Parsed Luv values when present. |
| `stdout`, `stderr` | Raw ArgyllCMS output streams. |

## Progress Reports & Resume

During a plan run, the GUI writes a `.progress.json` sidecar after each measurement. It stores:

- `app`
- `updated_ts`
- `capture_csv`
- `row_count`
- `total_steps`
- `completed_steps`
- `status`: `running`, `stopped`, or `completed`
- `solver_mode`
- `next_row_index`
- `next_repeat_index`
- `plan_source_csv`

When a run is interrupted, load the progress report, confirm or locate the original plan CSV if needed, and click **Run plan**. The GUI appends to the existing capture CSV and resumes from the recorded row/repeat.

## LUT Verifier Tab

The verifier measures generated RGB input patches through either a loaded RGB→RGBW 3D LUT or the firmware's analytical RGB16 solve path. It then compares measured xy against an expected xy target and reports pass/fail using the configured chromaticity dE threshold.

The verifier dE is chromaticity-only: both measured and expected xy points are converted into a Lab-like a*b* plane at normalized Y=100, then compared by Euclidean distance. It is intended for hue/chromaticity verification, not full luminance ΔE validation.

### Loading verifier inputs

| Control | Purpose |
|---------|---------|
| **Load LUT (.npy)** | Loads an RGB-indexed LUT cube with shape `(N, N, N, C)`, where `C=3` for RGB, `C=4` for RGBW, and `C=5` for RGBWW/RGBCCT. Values are treated as uint16 outputs over a 0–65535 RGB input axis. Required for the **3D LUT** output path. |
| **Load Summary (.json)** | Loads `lut_summary.json` from the builder. Used for reference white, native expected xy, measured LED hull, model-style projection, and auto-selecting settings when present. |

The summary loader looks for settings such as `gamut`, `input_gamut`, `input_transfer`, and `recommended_interpolation`. If present and supported, the GUI updates the verifier controls to match.

### Verifier options

| Control | Values | Purpose |
|---------|--------|---------|
| **dE threshold** | numeric, default `2.0` | Pass/fail threshold for the chromaticity dE calculation. |
| **Patch set** | `quick`, `medium`, `full` | Selects the generated verifier patches. |
| **Interp** | `tetrahedral`, `trilinear` | Interpolation method used for `.npy` LUT lookup. |
| **Output** | `3D LUT`, `FastLED analytical MCU` | Chooses whether RGB input is converted by the loaded LUT cube or by the firmware analytical solver. |
| **Strip** | `RGB`, `RGBW`, `RGBWW/RGBCCT` | Declares the intended output strip family for verifier transport. RGB strips reject 4+ channel output; RGBW strips reject 5-channel output. Current ObjectFLED firmware cannot switch to native 5-channel output yet, so RGBWW/RGBCCT transport is expected to fail on today’s 4-channel target. |
| **Cube** | `auto`, `RGB`, `RGBW`, `RGBWW/RGBCCT` | Declares the loaded cube output type. `auto` uses the cube’s channel count. Explicit selections may use a subset of a wider cube but cannot request more channels than the file contains. |
| **Model** | `rgbw_strict_sub_gamut`, `rgbw_lp_legacy`, `rgbww_overdrive`, `rgb_direct_stub`, `rgbww_strict_stub` | Analytical model family requested from the MCU when using **FastLED analytical MCU** output. Ignored for **3D LUT** output. |
| **Dual edge** | `y_correct_clip`, `rolloff_after_clip`, `scale_to_full_endpoint` | Dual-channel edge policy sent with analytical RGB16 requests when using **FastLED analytical MCU** output. Ignored for **3D LUT** output. |
| **Target gamut** | `summary/native`, `rec709`, `rec2020`, `dci-p3`, `dci-p3-d60`, `adobe-rgb` | Expected source chromaticity model. In **FastLED analytical MCU** mode, supported values are also sent to the Teensy as FastLED input gamut before verification. `adobe-rgb` is verifier-only because FastLED does not currently define that input gamut. |
| **Transfer** | `linear`, `gamut` | Whether verifier RGB inputs are treated as linear-light or decoded using the named gamut's transfer assumption. |
| **Project OOH xy** | on/off | Projects out-of-hull named-gamut targets into the measured LED/model hull before scoring. |
| **Get FastLED gamut** | button | Reads the active FastLED input gamut from analytical firmware using `OP_GET_INPUT_GAMUT`. |

### Diode profile controls

The verifier can use a diode basis from a loaded LUT summary, measure a basis locally, or exchange a compact `DiodeProfile` with the FastLED analytical verifier firmware. The profile chain accepts RGB, RGBW, and RGBWW/RGBCCT basis shapes; solver families that are still stubs report explicit unsupported status.

| Control | Purpose |
|---------|---------|
| **Fetch Teensy DiodeProfile** | Requests the compiled/runtime diode profile from compatible analytical firmware using `OP_GET_DIODE_PROFILE`. RGB, RGBW, and RGBWW/RGBCCT payloads are decoded into verifier basis state. |
| **Send DiodeProfile to Teensy** | Encodes the currently loaded, fetched, or measured basis as a DPRF q1e6 payload and sends it with `OP_SET_DIODE_PROFILE`. |
| **Measure diode basis now** | Measures local R/G/B/W basis states with the colorimeter when a compatible summary is missing or a fresh basis is needed. |

### Patch sets

| Preset | Contents |
|--------|----------|
| `quick` | 36 named patches: neutral ramp, primaries, secondaries, half-drive colors, desaturated primaries, tertiaries, skin tones, warm/cool whites, and dark saturated primaries. |
| `medium` | Named patches plus a coarser neutral ramp and HSV grid. Useful for routine LUT sanity checks. |
| `full` | Named patches plus a denser neutral ramp and HSV grid. Useful for more exhaustive validation. |

### 3D LUT output path

When **Output** is `3D LUT`, the verifier:

1. Generates an RGB16 verifier patch.
2. Looks up the output tuple in the loaded `(N,N,N,C)` LUT.
3. Uses either tetrahedral or trilinear interpolation.
4. Validates that the selected strip type can carry the cube output type. RGB cubes can drive RGB, RGBW, or RGBWW/RGBCCT strips by padding missing white channels with zero. RGBW cubes can drive RGBW or RGBWW/RGBCCT strips. RGBWW/RGBCCT cubes require a 5-channel strip transport.
5. Sends the resulting output using the selected strip transport. RGB/RGBW output uses `OP_SET_FILL16`; RGB output sends W=0. RGBWW/RGBCCT output uses `OP_SET_DIRECT_RGBWW16`.
6. Measures the rendered output with `spotread`.
7. Computes expected xy and dE.

Tetrahedral interpolation follows the standard six-tetrahedra cube split. This is generally preferred for these RGBW cubes because equal channel fractions stay on the neutral diagonal instead of blending all eight cube corners the way trilinear interpolation does.

### FastLED analytical MCU output path

When **Output** is `FastLED analytical MCU`, the verifier does not require a loaded `.npy` LUT. Instead, it sends the RGB16 input, analytical model ID, selected FastLED input gamut, and optional dual-edge policy to the firmware using the analytical RGB16 opcode. The MCU returns the solved output tuple, solve-path metadata, active output mode, and debug candidates when supported, and the GUI measures that rendered state.

The results table and CSV include:

- `analytical_model`
- `analytical_solve_path`
- `analytical_strict_ok`
- `analytical_strict_rgbw16`
- `analytical_lp_rgbw16`
- `analytical_dual_edge_policy` when present
- MCU solved output values, including W2 when present

This makes the tab useful for comparing a generated 3D LUT against the firmware's current analytical solver without rebuilding a full cube.

### Target gamut and transfer handling

`summary/native` uses RGB basis data from the loaded summary to estimate expected xy in the measured/native LED space. For named gamuts, the verifier builds an RGB→XYZ matrix from the selected primaries and reference white:

- Rec.709
- Rec.2020
- DCI-P3 D65
- DCI-P3 D60
- Adobe RGB

`Transfer = linear` treats the RGB16 patch values as already linear-light.

`Transfer = gamut` applies the verifier's per-gamut decode assumption before computing expected xy:

| Gamut | Transfer behavior |
|-------|-------------------|
| `rec709` | sRGB/Rec.709-style piecewise decode. |
| `rec2020` | Power 2.4 decode. |
| `dci-p3` | Power 2.6 decode. |
| `dci-p3-d60` | Power 2.6 decode. |
| `adobe-rgb` | Power 2.2 decode. |

### Out-of-hull projection

When **Project OOH xy** is enabled, expected xy targets that are outside the measured LED/model gamut are projected before scoring. If the summary contains RGBW basis information, the verifier mirrors the model-style projection policy by solving against RGW, RBW, and BGW topologies and clipping when needed. If only RGB hull data is available, it falls back to nearest CIE xy projection onto the measured RGB triangle.

The verifier records both raw expected xy and final/projected expected xy in the exported CSV.

### Verifier results table

The table shows:

| Column | Meaning |
|--------|---------|
| `patch` | Patch name. |
| `input_rgb16` | Source RGB16 input. |
| `output_rgbw16` | LUT output or MCU-solved output tuple. The historical column name is retained; RGB rows contain R/G/B, RGBW rows contain R/G/B/W, and RGBWW/RGBCCT rows include W2. |
| `path` | Analytical solve path when using MCU output. |
| `strict_rgbw16` | Strict analytical candidate returned by MCU, when available. |
| `lp_rgbw16` | LP legacy analytical candidate returned by MCU, when available. |
| `w_pct` | White-channel output as a percentage of 65535. |
| `meas_x`, `meas_y`, `meas_Y` | Measured chromaticity and luminance. |
| `exp_x`, `exp_y` | Expected/scored chromaticity. |
| `proj` | Projection edge/path if expected xy was projected. |
| `dE` | Chromaticity dE. |
| `ok` | Pass/fail marker or no-reference marker. |

### Verifier CSV export

**Export CSV** writes all measured verifier rows with the fields shown in the table plus extra metadata:

- source RGB16
- output RGBW16
- output source
- analytical model/path/candidates
- measured xyY
- raw expected xy
- final expected xy
- projection metadata
- expected hull data
- dE and pass/fail tag
- interpolation mode
- expected / verification gamut
- input transfer

## Serial Protocol Summary

The GUI speaks the TCAL frame protocol over USB serial. The same frame envelope is shared by the direct Teensy temporal calibration companion and the FastLED analytical verifier endpoint.

```text
[TCAL] [kind:1] [len_hi:1] [len_lo:1] [payload:0..128] [crc:1]
```

The CRC is the XOR of `kind`, `len_hi`, `len_lo`, and every payload byte. Payloads are capped at 128 bytes.

### Frame kinds

| Kind | Direction | Purpose |
|------|-----------|---------|
| `0x01` / `0x81` | Host → device / response | Hello handshake. The response payload is the sketch identity string. |
| `0x02` / `0x82` | Host → device / response | Ping / pong echo test. |
| `0x30` / `0xB0` | Host → device / response | Calibration, render, analytical, and output-mode command / response. |
| `0x90` | Device → host | Device log message. |

### Device roles

Two current firmware roles use the shared envelope:

| Firmware role | Identity payload | Purpose |
|---------------|------------------|---------|
| `Teensy_Temporal_Calibration` companion | `teensy-cal-direct-v1` | Direct-output companion. The host performs LUT / verifier logic and sends final RGBW/RGBWW targets. It does not expose diode-profile editing opcodes. |
| `RGBW_Analytical_FastLED` verifier | `teensy-rgbw-analytic-v2` | Analytical verification endpoint. The host can send RGB16 inputs for MCU-side solving, direct RGBW/RGBWW analytical targets, and diode-profile get/set payloads. |

### Shared status values

| Status | Value | Meaning |
|--------|------:|---------|
| `STATUS_OK` | `0x00` | Request accepted. |
| `STATUS_BAD_PAYLOAD` | `0x01` | Payload too short or malformed for the opcode. |
| `STATUS_BAD_OPCODE` | `0x02` | Unknown opcode. |
| `STATUS_UNSUPPORTED_OUTPUT_MODE` | `0x04` | Requested logical output mode cannot be represented by the active physical target. |

The FastLED analytical verifier also reports:

| Status | Value | Meaning |
|--------|------:|---------|
| `STATUS_SOLVE_FAILED` | `0x03` | Analytical strict-subgamut solve failed. |
| `STATUS_BAD_PROFILE` | `0x05` | Diode-profile signature, version, format, or range validation failed. |
| `STATUS_UNSUPPORTED_MODEL` | `0x06` | Requested analytical model family or profile operation is not implemented for the active firmware path. |
| `STATUS_UNSUPPORTED_GAMUT` | `0x07` | Requested FastLED input gamut is not implemented by the analytical firmware. |

### Output modes

The host tracks the device's active logical output mode, supported-mode bitmask, physical output channel count, and active logical channel count when those response fields are available.

| Mode | Value | Meaning |
|------|------:|---------|
| `OUTPUT_MODE_RGB` | `0x00` | Three logical output channels. |
| `OUTPUT_MODE_RGBW` | `0x01` | Four logical output channels. |
| `OUTPUT_MODE_RGBWW` | `0x02` | Five logical RGBWW / RGBCCT-style channels. |

Current 4-channel ObjectFLED targets reject RGBWW/RGBCCT requests with `STATUS_UNSUPPORTED_OUTPUT_MODE`. W2 is not folded into W.

### Shared base opcodes

These opcodes are used by both current firmware roles unless noted by the target firmware response.

| Opcode | Name | Payload after opcode | Response / behavior |
|--------|------|----------------------|---------------------|
| `0x00` | `OP_GET_STATE` | none | Current state response. |
| `0x20` | `OP_SET_RENDER_ENABLED` | byte 1: nonzero enables render output | Current state response. |
| `0x21` | `OP_SET_FILL` | bytes 1..4: 8-bit R,G,B,W; bytes 5..8: BFI R,G,B,W | Sets Fill8-style values and BFI fields. |
| `0x23` | `OP_CLEAR` | none | Clears output buffers and state. |
| `0x24` | `OP_SET_PHASE` | byte 1: explicit temporal tick / phase value | Sets manual phase index. |
| `0x26` | `OP_COMMIT` | none | Acknowledge/latch point for the currently staged render state. |
| `0x28` | `OP_SET_PHASE_MODE` | byte 1: `0x00` auto, `0x01` manual | Selects automatic or host-forced phase control. |
| `0x29` | `OP_SET_SOLVER_ENABLED` | byte 1: nonzero enables solver mode | Enables/disables firmware solver mode for plan execution. |
| `0x2A` | `OP_SET_TEMPORAL_BLEND` | bytes 1..4: lower R,G,B,W; bytes 5..8: upper R,G,B,W; bytes 9..12: BFI R,G,B,W | Sends a Blend8 lower/upper/BFI state. |
| `0x2B` | `OP_SET_FILL16` | u16be R,G,B,W at offsets 1,3,5,7 | Sends 16-bit RGBW targets. Unsupported status may be returned if the active target mode cannot represent the requested channels. |
| `0x2E` | `OP_SET_OUTPUT_MODE` | byte 1: `OUTPUT_MODE_*` | Requests RGB, RGBW, or RGBWW logical output mode. |

### FastLED analytical verifier opcodes

These are specific to the FastLED analytical verifier endpoint.

| Opcode | Name | Payload after opcode | Behavior |
|--------|------|----------------------|----------|
| `0x2C` | `OP_SET_ANALYTICAL_RGB16` | byte 1: analytical model family; u16be R,G,B at offsets 2,4,6; optional byte 8: dual-edge policy | Sends source RGB16 to the FastLED analytical path. Implemented families render their solved output and return selected output plus sanity/debug fields. Stub families return `STATUS_UNSUPPORTED_MODEL`. |
| `0x2D` | `OP_GET_DIODE_PROFILE` | none | Returns a DPRF diode profile payload for the active analytical family when available. |
| `0x31` | `OP_SET_DIODE_PROFILE` | DPRF diode-profile payload | Validates and applies a host-provided RGB/RGBW/RGBWW profile where supported, rebuilds compatible FastLED colorimetric state, clears analytical debug state, and returns a DPRF profile response. |
| `0x32` | `OP_GET_INPUT_GAMUT` | none | Returns the active FastLED analytical input gamut and supported-gamut bitmask. |
| `0x33` | `OP_SET_INPUT_GAMUT` | byte 1: input gamut enum value | Sets the FastLED analytical input gamut, rebuilds compatible RGBW/RGBWW colorimetric state, and returns the active gamut. |

Analytical model values:

| Value | Meaning |
|------:|---------|
| `0x00` | `rgbw_strict_sub_gamut`: FastLED RGBW strict sub-gamut solve. |
| `0x01` | `rgbw_lp_legacy`: FastLED RGBW legacy LP solve. |
| `0x02` | `rgbww_overdrive`: FastLED RGBWW/RGBCCT layered overdrive solve. Rendering still requires physical output support. |
| `0x03` | `rgb_direct_stub`: RGB direct solver placeholder; currently returns `STATUS_UNSUPPORTED_MODEL`. |
| `0x04` | `rgbww_strict_stub`: strict RGBCCT placeholder; currently returns `STATUS_UNSUPPORTED_MODEL`. |

Dual-edge policy values:

| Value | Meaning |
|------:|---------|
| `0x00` | Y-correct clip. |
| `0x01` | Rolloff after clip. |
| `0x02` | Scale to full endpoint. |

FastLED analytical input-gamut values:

| Value | Meaning |
|------:|---------|
| `0x00` | Native LED primaries + D65 white. |
| `0x01` | Rec.709 / sRGB primaries + D65 white. |
| `0x02` | Rec.2020 primaries + D65 white. |
| `0x03` | DCI-P3 D65 consumer/display variant. |
| `0x04` | DCI-P3 D60 ACES/cinema variant. |

### Direct-output companion opcodes

The temporal calibration companion uses the shared Fill16 opcode for direct RGBW16 output. It does not accept a duplicate `0x2F` RGBW16 direct path.

| Opcode | Name | Payload after opcode | Behavior |
|--------|------|----------------------|----------|
| `0x2B` | `OP_SET_FILL16` | u16be R,G,B,W at offsets 1,3,5,7 | Applies direct RGBW16 output values through the TemporalBFI true16 render path. RGB-only targets reject nonzero W. |
| `0x30` | `OP_SET_DIRECT_RGBWW16` | u16be R,G,B,W1,W2 at offsets 1,3,5,7,9 | Rejected unless a future native 5-channel ObjectFLED target is available. W2 is never folded into W. |

### FastLED analytical response layout

The analytical verifier returns a 64-byte calibration response when the extended state is available.

| Offset | Field |
|-------:|-------|
| 0 | Echoed opcode. |
| 1 | Status. |
| 2 | Render enabled flag. |
| 3 | Manual phase flag. |
| 4 | Current temporal tick low byte. |
| 5..8 | First pixel upper R,G,B,W response-order bytes. |
| 9..12 | First pixel BFI R,G,B,W. |
| 17 | Solver enabled flag. |
| 18..25 | Last solved R,G,B,W as u16be. |
| 26..31 | Last input R,G,B as u16be. |
| 32 | Analytical model. |
| 33 | Analytical solve path. |
| 34 | Strict solve OK flag. |
| 35..42 | Strict solved R,G,B,W as u16be. |
| 43..50 | Legacy LP solved R,G,B,W as u16be. |
| 51 | Dual-edge policy. |
| 52 | Active output mode. |
| 53 | Supported output mode bitmask. |
| 54 | Physical ObjectFLED output channel count. |
| 55 | Active logical channel count. |
| 56..59 | Last input W and W2 as u16be. |
| 60..61 | Last solved W2 as u16be. |
| 62 | Fold/stub flag, currently `0` because unsupported modes are rejected. |
| 63 | Response extension version, currently `1`. |

Analytical solve-path values parsed by the host are `none`, `strict_sub_gamut`, `lp_legacy`, `strict_failed`, `rgbww_overdrive`, and `unavailable`.

### Temporal calibration companion response layout

The direct-output companion returns a 32-byte calibration response when the extended state is available.

| Offset | Field |
|-------:|-------|
| 0 | Echoed opcode. |
| 1 | Status. |
| 2 | Render enabled flag. |
| 3 | Manual phase flag. |
| 4 | Current temporal tick low byte. |
| 5..8 | First pixel upper R,G,B,W response-order bytes. |
| 9..12 | First pixel BFI R,G,B,W. |
| 17 | Solver enabled flag. |
| 18 | Active output mode. |
| 19 | Supported output mode bitmask. |
| 20 | Physical ObjectFLED output channel count. |
| 21 | Active logical channel count. |
| 22 | Compile-time target output mode. |
| 23 | Fold/stub flag, currently `0` because unsupported modes are rejected. |
| 29 | Response extension version, currently `1`. |

### Diode profile payload

`OP_GET_DIODE_PROFILE` and `OP_SET_DIODE_PROFILE` use a compact DPRF block for diode basis exchange.

| Field | Meaning |
|-------|---------|
| Signature | ASCII `DPRF`; in responses it follows opcode/status alignment, while set requests place it immediately after the opcode. |
| Version | `1`. |
| Format | `1` for RGBW (`R,G,B,W`), `2` for RGBWW/RGBCCT (`R,G,B,WW,WC`), `3` reserved for future RGB-only (`R,G,B`). Values are unsigned 32-bit big-endian scaled by 1e6. |
| Values | For each channel in the format order, x, y, and relative Y are stored as u32be q1e6 values. |

Set-profile validation requires each x and y to be greater than 0 and less than 1, `x + y < 1`, and relative Y greater than 0. Accepted profiles rebuild the analytical firmware's compatible colorimetric state immediately; unsupported model/profile combinations return `STATUS_UNSUPPORTED_MODEL`.

## Typical Workflows

### Workflow 1: Fill8 / Blend8 temporal ladder capture

1. Generate a Fill8 / Blend8 capture plan with the temporal LUT tooling.
2. Import the CSV in the **Measurement Plan** tab.
3. Confirm the Teensy and colorimeter are connected.
4. Leave **Plan uses solver mode** disabled unless the plan explicitly expects solver output.
5. Run the plan.
6. Feed the capture CSV into the temporal ladder pruning/interpolation tools.

### Workflow 2: True16 RGBW patch capture

1. Generate a True16 / Fill16 RGBW patch plan.
2. Import the CSV.
3. Enable **Plan uses solver mode** if the firmware should map the 16-bit targets through its calibrated solver path.
4. Run the plan.
5. Use the resulting CSV for RGBW model fitting, LUT builder input, or verifier/reference datasets.

### Workflow 3: External sparse capture through UDP

1. Connect the serial device normally.
2. Start the UDP capture server, usually on `0.0.0.0:19446`.
3. From the external builder/tool, send JSON requests containing RGBW16 targets.
4. Use `render` / `set_rgbw16` for display-only patches or `capture_rgbw16` for render + colorimeter measurement.
5. Read the JSON response and/or the local UDP trace written in the capture directory.

### Workflow 4: Verify a generated 3D LUT

1. Load the `.npy` RGB-indexed LUT cube in the **LUT Verifier** tab.
2. Load the matching `lut_summary.json` so expected xy, reference white, gamut, transfer, and projection metadata are available.
3. Select `tetrahedral` or `trilinear` interpolation.
4. Select target gamut and transfer mode. Use the summary-loaded defaults when they match the LUT build.
5. Choose `quick`, `medium`, or `full` patch set.
6. Click **Run Verification**.
7. Export CSV and inspect failures by patch, dE, projection path, output RGBW16, and W percentage.

### Workflow 5: Verify the firmware analytical solver

1. Connect the Teensy with firmware that supports the analytical RGB16 opcode.
2. In the verifier, set **Output** to **FastLED analytical MCU**.
3. Select the analytical **Model** (`rgbw_strict_sub_gamut`, `rgbw_lp_legacy`, `rgbww_overdrive`, or one of the explicit stub families).
4. Select **Target gamut**. For FastLED analytical output, the GUI sends this to the Teensy with `OP_SET_INPUT_GAMUT` before verification. `summary/native`, `rec709`, `rec2020`, `dci-p3`, and `dci-p3-d60` are supported; `adobe-rgb` is verifier-only and cannot be sent as a FastLED input gamut.
5. Load a summary JSON if you want named-gamut projection/scoring against the measured model basis.
6. Run verification and export results.

This path is useful when checking whether the MCU-side analytical solver matches or diverges from a generated 3D LUT. Interpolation is ignored for this path; model family, input gamut, and dual-edge policy are FastLED-only controls.

## Notes and limitations

- The verifier's dE is chromaticity-only and does not judge luminance accuracy.
- `summary/native` expected xy requires a compatible summary JSON with RGB basis data.
- Model-style out-of-hull projection uses RGBW basis data when present. RGBWW/RGBCCT basis data is accepted and an effective W basis is synthesized from WW/WC for RGBW-style projection helpers. RGB-only basis data falls back to nearest xy projection onto the RGB triangle.
- RGBWW/RGBCCT overdrive solving is wired through the FastLED analytical path, but current 4-channel ObjectFLED targets still reject physical five-channel rendering until native 5-channel output support lands.
- The GUI currently models strip/cube output families as RGB, RGBW, and RGBWW/RGBCCT. Generalized N-channel emitter families can be added later once real hardware/test benches exist.
- ObjectFLED cannot currently change the physical strip emitter count at runtime. The GUI exposes strip type so verifier transport and validation are correct; firmware support for native 5-channel output is a later ObjectFLED/FastLED integration pass.
- W2 is intentionally kept separate and is never folded into W by the host.
- Diode-profile get/set is scoped to the FastLED analytical verifier endpoint; the direct temporal calibration companion does not expose diode-profile editing opcodes.
- The UDP server serializes measurement requests because both the serial device and colorimeter are shared single resources.
- The GUI intentionally keeps raw Argyll `stdout` and `stderr` in capture artifacts so parsing changes can be audited later.
