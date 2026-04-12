# Host Calibration GUI

Tkinter application that drives the [Teensy\_Temporal\_Calibration](../../examples/Teensy_Temporal_Calibration/) sketch and an ArgyllCMS colorimeter to capture LED state measurements. It is the host side of the calibration pipeline — the Teensy sets LED states over serial, the GUI triggers `spotread` to measure CIE XYZ, and results are logged to CSV for downstream processing.

## Requirements

- Python 3.10+
- `pyserial`
- [ArgyllCMS](https://www.argyllcms.com/) (`spotread` on `PATH`)
- A supported colorimeter (i1Display Pro, i1Studio, ColorMunki Display, etc.)

```bash
pip install pyserial
```

## Quick Start

```bash
python host_calibration_gui.py
```

1. Connect the Teensy running `Teensy_Temporal_Calibration` via USB.
2. Select the serial port and click **Connect**.
3. Click **Hello** / **Ping** to verify communication.
4. Import a measurement plan CSV (or build one manually).
5. Click **Run plan** — the GUI will step through each state, measure, and write a capture CSV.

## GUI Layout

### Connection Bar

| Control | Purpose |
|---------|---------|
| **Serial port** | Dropdown of available COM ports. **Refresh** rescans. |
| **Baud** | Default 30 000 000 (matches Teensy USB serial). |
| **Connect** | Opens the serial link and starts the RX listener thread. |
| **Hello / Ping** | Protocol handshake and latency check. |
| **Get State** | Queries the Teensy's current render state. |

### Options Row

| Control | Purpose |
|---------|---------|
| **Capture dir** | Choose where capture CSVs and progress reports are saved. |
| **Settle delay** | Seconds to wait after setting an LED state before measuring. Allows phosphor/driver settling. |
| **Argyll command** | The base `spotread` command. Default: `spotread -x -O` (XYZ output, no display type prompt). |
| **Cleanup stale before read** | Kill any orphaned `spotread` processes before each measurement. |
| **Send newline trigger** | Send a newline to `spotread`'s stdin to trigger the reading (required for most modes). |
| **Show transport spam** | Unhides low-level serial frame logs in the log pane. |
| **Plan uses solver mode** | When checked, tells the Teensy to use its calibrated solver path instead of raw drive values; used for True16/Fill16 capture plans. |
| **Kill stale spotread** | Manual button to terminate orphaned ArgyllCMS processes. |
| **Abort Measurement** | Cancel an in-progress `spotread` read. |

### Resume Bar

| Control | Purpose |
|---------|---------|
| **Load report** | Load a `.progress.json` from a previous interrupted run. Restores the plan CSV, capture file, and row/repeat position so the plan can resume exactly where it stopped. |

### Render Panel (manual control)

| Control | Purpose |
|---------|---------|
| **Mode** | `Fill8` (static 8-bit), `Blend8` (temporal blend), or `Fill16` (True16 solver-driven). |
| **R / G / B / W sliders** | Set the 8-bit channel values (Fill8/Blend8) or 16-bit values (Fill16). |
| **Lower R / G / B / W** | Floor values for Blend8 mode. |
| **BFI R / G / B / W** | BFI level (0–4) per channel for Blend8 mode. |
| **Phase mode** | Auto (Teensy cycles phases internally) or Manual (host controls which phase is displayed). |
| **Send State** | Push the current slider values to the Teensy. |
| **Commit** | Latch the current state into the render pipeline. |
| **Clear** | Zero all channels. |
| **Measure Once** | Set the state, wait for settle, run `spotread`, and log the result. |

### Plan Panel

| Control | Purpose |
|---------|---------|
| **Add current** | Snapshot the current render panel values as a new plan row. |
| **Import plan CSV** | Load a plan file (columns: `name`, `mode`, `repeats`, `r`, `g`, `b`, `w`, `lower_*`, `upper_*`, `bfi_*`, `r16`–`w16`, `use_fill16`). |
| **Clear plan** | Remove all rows. |
| **Delete selected** | Remove highlighted rows from the treeview. |
| **Run plan** | Execute the plan — iterate rows × repeats, setting state → measuring → writing CSV. |
| **Pause / Resume** | Pause a running plan (current measurement finishes). Resume continues from the next step. |
| **Stop** | Halt the plan. Progress is saved; reload the report to resume later. |
| **Save plan CSV** | Export the current plan rows as a CSV that can be re-imported. |

### Log Panel

Scrolling text log with timestamped entries for serial traffic, ArgyllCMS output, plan progress, and errors.

## Measurement Modes

### Fill8 — Static 8-bit brightness

Each channel is driven at a single 8-bit level (0–255), all BFI phases show the same value. Used to capture the 256 fill8 anchor states per channel that form the monotonic backbone of the temporal ladder.

### Blend8 — Temporal blend capture

Each channel is driven with `(lower_value, upper_value, bfi)`. The Teensy alternates between floor and ceiling levels across the BFI cycle. Used to capture the intermediate brightness steps that the temporal ladder exploits for sub-8-bit resolution.

### Fill16 — True16 solver-driven

Each channel receives a 16-bit target (0–65535). The Teensy's onboard solver maps this to the best `(value, bfi, lowerValue)` tuple from the temporal ladder and renders accordingly. Used to capture RGBW patch sets for color LUT building — the solver handles the temporal encoding, the host only specifies the desired Q16 color.

## Capture Plan CSV Format

Plans are CSV files with one row per measurement state. Key columns:

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Human-readable label (e.g. `fill8_r_128`, `blend_r_100_120_bfi2`) |
| `mode` | string | `fill8`, `blend8`, or `fill16` |
| `repeats` | int | Number of repeat measurements per state (for averaging / outlier detection) |
| `r`, `g`, `b`, `w` | int | 8-bit channel values (Fill8/Blend8) |
| `lower_r`…`lower_w` | int | Floor values (Blend8 only) |
| `upper_r`…`upper_w` | int | Ceiling values (Blend8 only) |
| `r16`…`w16` | int | 16-bit targets (Fill16 only) |
| `bfi_r`…`bfi_w` | int | BFI levels per channel (Blend8 only) |
| `use_fill16` | 0/1 | Explicit Fill16 flag |

## Output: Capture CSV

Each plan run writes a timestamped CSV to the capture directory with one row per measurement:

| Column | Description |
|--------|-------------|
| `name`, `mode`, `use_fill16` | State identity |
| `r`–`w`, `lower_*`, `upper_*`, `bfi_*`, `r16`–`w16` | Drive values sent to Teensy |
| `repeat_index` | Which repeat of this state (0-based) |
| `solver_mode` | Whether the Teensy solver was active |
| `ok` | `True` if `spotread` returned valid XYZ |
| `returncode` | `spotread` exit code |
| `elapsed_s` | Measurement wall-clock time |
| `timed_out` | Whether the measurement hit the timeout |
| `X`, `Y`, `Z` | CIE 1931 tristimulus values |
| `x`, `y` | CIE 1931 chromaticity coordinates |
| `stdout`, `stderr` | Raw ArgyllCMS output |

## Progress Reports & Resume

When a plan runs, a `.progress.json` sidecar is written alongside the capture CSV after every measurement. It records:

- `total_steps` / `completed_steps` — overall progress
- `next_row_index` / `next_repeat_index` — exact resume point
- `capture_csv` — path to the capture file being appended to
- `status` — `running`, `stopped`, or `completed`

If a plan is interrupted (Stop, crash, power loss), click **Load report** and select the `.progress.json`. The GUI restores the plan CSV, capture file path, and resume position. Clicking **Run plan** again continues from the exact row and repeat where it left off, appending to the same capture CSV.

## Serial Protocol

Communication uses a binary framed protocol over USB serial at 30 Mbaud:

```
[TCAL] [kind:1] [len_hi:1] [len_lo:1] [payload:0..128] [crc:1]
```

| Kind | Direction | Purpose |
|------|-----------|---------|
| `0x01` / `0x81` | Host → Teensy / Response | Hello handshake |
| `0x02` / `0x82` | Host → Teensy / Response | Ping / pong |
| `0x30` / `0xB0` | Host → Teensy / Response | Calibration command / acknowledgement |
| `0x90` | Teensy → Host | Log message |

Calibration commands (`0x30`) carry an opcode byte selecting the operation:

| Opcode | Name | Action |
|--------|------|--------|
| `0x20` | Set Render Enabled | Enable/disable LED output |
| `0x21` | Set Fill | Set 8-bit RGBW levels |
| `0x23` | Clear | Zero all channels |
| `0x24` | Set Phase | Set manual phase index |
| `0x26` | Commit | Latch current state to render |
| `0x28` | Set Phase Mode | Auto (Teensy cycles) or Manual (host controls) |
| `0x29` | Set Solver Enabled | Enable/disable onboard solver for Fill16 |
| `0x2A` | Set Temporal Blend | Set Blend8 state (lower, upper, BFI per channel) |
| `0x2B` | Set Fill16 | Set 16-bit RGBW targets (solver maps to temporal blend) |

## Typical Workflows

### Workflow 1: Fill8 + Blend8 ladder capture

1. Generate a fill8/blend8 plan CSV with `temporal_lut_tools` (`generate-capture-plan` command).
2. Import the plan CSV into the GUI.
3. Connect the Teensy and colorimeter.
4. Run plan — captures all 256 fill8 anchors per channel plus the blend8 states.
5. Feed the output CSV to `temporal_lut_tools` for pruning, interpolation, and ladder building.

### Workflow 2: True16 RGBW patch capture

1. Generate a True16 patch plan with `temporal_lut_tools` (`generate-patch-plan` or `generate_patch_plan_true16_comprehensive_v6.py`).
2. Import the plan CSV. Enable **Plan uses solver mode**.
3. Run plan — the Teensy solver drives each RGBW target, the colorimeter measures the actual output.
4. Feed the output CSV to `rgbw_lut_builder` tools for color LUT building.
