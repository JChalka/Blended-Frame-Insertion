# Host Calibration GUI

`host_calibration_gui.py` is the Tkinter host application for the Temporal RGBW calibration workflow. It talks to the `Teensy_Temporal_Calibration` firmware over the TCAL USB serial protocol, renders RGBW states on the LED target, triggers ArgyllCMS `spotread`, and writes measurement artifacts for the downstream temporal ladder, RGBW model, 3D LUT, and verifier tools.

The current GUI is more than a simple capture runner. It now supports manual Fill8 / Blend8 / Fill16 rendering, resumable capture plans, spotread preset management, a UDP sparse-capture bridge for external builders, and an integrated LUT / FastLED analytical verifier with trilinear or tetrahedral interpolation, target-gamut selection, transfer selection, out-of-hull projection, and pass/fail CSV export.

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
3. **Sparse-capture bridge** — run a local UDP JSON server so external tools can ask the host to render RGBW16 patches and optionally capture them with the colorimeter.
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
| **Phase mode** | Auto lets the Teensy cycle phases. Manual lets the host force a phase index. |
| **Phase index** | Manual phase value. The GUI supports the full phase-control range exposed by the firmware constant. |
| **Apply phase** | Sends the current manual phase index. |
| **Send State** | Sends the selected Fill8 / Blend8 / Fill16 state to the firmware. |
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
| **Load LUT (.npy)** | Loads an RGBW LUT cube with shape `(N, N, N, 4)`. Values are treated as uint16 RGBW outputs over a 0–65535 RGB input axis. Required for the **3D LUT** output path. |
| **Load Summary (.json)** | Loads `lut_summary.json` from the builder. Used for reference white, native expected xy, measured LED hull, model-style projection, and auto-selecting settings when present. |

The summary loader looks for settings such as `gamut`, `input_gamut`, `input_transfer`, and `recommended_interpolation`. If present and supported, the GUI updates the verifier controls to match.

### Verifier options

| Control | Values | Purpose |
|---------|--------|---------|
| **dE threshold** | numeric, default `2.0` | Pass/fail threshold for the chromaticity dE calculation. |
| **Patch set** | `quick`, `medium`, `full` | Selects the generated verifier patches. |
| **Interp** | `tetrahedral`, `trilinear` | Interpolation method used for `.npy` LUT lookup. |
| **Output** | `3D LUT`, `FastLED analytical MCU` | Chooses whether RGB input is converted to RGBW by the loaded LUT or by the firmware analytical solver. |
| **Model** | `sub-gamut`, `lp_legacy` | Analytical model requested from the MCU when using **FastLED analytical MCU** output. |
| **Target gamut** | `summary/native`, `rec709`, `rec2020`, `dci-p3`, `adobe-rgb` | Expected source chromaticity model. |
| **Transfer** | `linear`, `gamut` | Whether verifier RGB inputs are treated as linear-light or decoded using the named gamut's transfer assumption. |
| **Project OOH xy** | on/off | Projects out-of-hull named-gamut targets into the measured LED/model hull before scoring. |

### Patch sets

| Preset | Contents |
|--------|----------|
| `quick` | 36 named patches: neutral ramp, primaries, secondaries, half-drive colors, desaturated primaries, tertiaries, skin tones, warm/cool whites, and dark saturated primaries. |
| `medium` | Named patches plus a coarser neutral ramp and HSV grid. Useful for routine LUT sanity checks. |
| `full` | Named patches plus a denser neutral ramp and HSV grid. Useful for more exhaustive validation. |

### 3D LUT output path

When **Output** is `3D LUT`, the verifier:

1. Generates an RGB16 verifier patch.
2. Looks up the RGBW16 output in the loaded `(N,N,N,4)` LUT.
3. Uses either tetrahedral or trilinear interpolation.
4. Sends the resulting RGBW16 Fill16 state to the firmware.
5. Measures the rendered output with `spotread`.
6. Computes expected xy and dE.

Tetrahedral interpolation follows the standard six-tetrahedra cube split. This is generally preferred for these RGBW cubes because equal channel fractions stay on the neutral diagonal instead of blending all eight cube corners the way trilinear interpolation does.

### FastLED analytical MCU output path

When **Output** is `FastLED analytical MCU`, the verifier does not require a loaded `.npy` LUT. Instead, it sends the RGB16 input plus analytical model ID to the firmware using the analytical RGB16 opcode. The MCU returns the solved RGBW16 output and path metadata, and the GUI measures that rendered state.

The results table and CSV include:

- `analytical_model`
- `analytical_solve_path`
- `analytical_strict_ok`
- `analytical_strict_rgbw16`
- `analytical_lp_rgbw16`
- MCU solved RGBW16 values

This makes the tab useful for comparing a generated 3D LUT against the firmware's current analytical solver without rebuilding a full cube.

### Target gamut and transfer handling

`summary/native` uses RGB basis data from the loaded summary to estimate expected xy in the measured/native LED space. For named gamuts, the verifier builds a D65-normalized RGB→XYZ matrix from the selected primaries:

- Rec.709
- Rec.2020
- DCI-P3
- Adobe RGB

`Transfer = linear` treats the RGB16 patch values as already linear-light.

`Transfer = gamut` applies the verifier's per-gamut decode assumption before computing expected xy:

| Gamut | Transfer behavior |
|-------|-------------------|
| `rec709` | sRGB/Rec.709-style piecewise decode. |
| `rec2020` | Power 2.4 decode. |
| `dci-p3` | Power 2.6 decode. |
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
| `output_rgbw16` | LUT output or MCU-solved RGBW16. |
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

Communication uses a binary framed protocol over USB serial:

```text
[TCAL] [kind:1] [len_hi:1] [len_lo:1] [payload:0..128] [crc:1]
```

| Kind | Direction | Purpose |
|------|-----------|---------|
| `0x01` / `0x81` | Host → Teensy / response | Hello handshake. |
| `0x02` / `0x82` | Host → Teensy / response | Ping / pong. |
| `0x30` / `0xB0` | Host → Teensy / response | Calibration command / acknowledgement. |
| `0x90` | Teensy → Host | Device log message. |

Calibration command opcodes currently used or recognized by the host:

| Opcode | Name | Action |
|--------|------|--------|
| `0x00` | Get State | Query current firmware render state. |
| `0x20` | Set Render Enabled | Firmware render enable/disable command. |
| `0x21` | Set Fill | Set 8-bit RGBW values plus BFI fields. |
| `0x23` | Clear | Clear output. |
| `0x24` | Set Phase | Set manual phase index. |
| `0x26` | Commit | Latch staged render state. |
| `0x28` | Set Phase Mode | Auto or manual phase mode. |
| `0x29` | Set Solver Enabled | Enable/disable firmware solver mode for plan runs. |
| `0x2A` | Set Temporal Blend | Send Blend8 lower/upper/BFI state. |
| `0x2B` | Set Fill16 | Send direct 16-bit RGBW target values. |
| `0x2C` | Set Analytical RGB16 | Ask the MCU analytical model to solve an RGB16 input to RGBW16, used by the verifier. |

The host parses extended calibration responses when available, including solved RGBW16, input RGB16, analytical model ID, analytical solve path, strict candidate, and LP candidate fields.

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

1. Load the `.npy` RGBW LUT cube in the **LUT Verifier** tab.
2. Load the matching `lut_summary.json` so expected xy, reference white, gamut, transfer, and projection metadata are available.
3. Select `tetrahedral` or `trilinear` interpolation.
4. Select target gamut and transfer mode. Use the summary-loaded defaults when they match the LUT build.
5. Choose `quick`, `medium`, or `full` patch set.
6. Click **Run Verification**.
7. Export CSV and inspect failures by patch, dE, projection path, output RGBW16, and W percentage.

### Workflow 5: Verify the firmware analytical solver

1. Connect the Teensy with firmware that supports the analytical RGB16 opcode.
2. In the verifier, set **Output** to **FastLED analytical MCU**.
3. Select the analytical **Model** (`sub-gamut` or `lp_legacy`).
4. Load a summary JSON if you want named-gamut projection/scoring against the measured model basis.
5. Run verification and export results.

This path is useful when checking whether the MCU-side analytical solver matches or diverges from a generated 3D LUT.

## Notes and limitations

- The verifier's dE is chromaticity-only and does not judge luminance accuracy.
- `summary/native` expected xy requires a compatible summary JSON with RGB basis data.
- Model-style out-of-hull projection requires RGBW basis data in the summary; otherwise the verifier falls back to nearest xy projection onto the RGB triangle.
- The UDP server serializes measurement requests because both the serial device and colorimeter are shared single resources.
- The GUI intentionally keeps raw Argyll `stdout` and `stderr` in capture artifacts so parsing changes can be audited later.
