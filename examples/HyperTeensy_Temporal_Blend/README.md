# HyperTeensy Temporal Blend

Teensy 4.0 RGBW LED driver for SK6812 strips using the ObjectFLED library.
Receives LED data from a [custom HyperHDR fork](https://github.com/JChalka/HyperHDR/tree/BFI) over USB RawHID (with serial
fallback) and renders per-pixel temporal Blended Frame Insertion (BFI) via the
TemporalBFI solver.

> **Attribution.**
> The AWA protocol at the core of this sketch was designed by
> [awawa-dev](https://github.com/awawa-dev) for the HyperSerial family of
> LED drivers.  The official reference implementation is
> [HyperSerialESP32](https://github.com/awawa-dev/HyperSerialESP32), and the
> protocol is documented on the
> [HyperSerial wiki page](https://github.com/awawa-dev/HyperHDR/wiki/HyperSerial).
>
> **awawa-dev does not maintain this sketch and is not responsible for
> diagnosing issues related to it or the custom HyperHDR fork that
> accompanies it.**  If you encounter problems specific to the extensions
> described below, file them against this repository, not upstream HyperHDR
> or HyperSerial.

---

## What's Different from the Stock AWA Driver

The official HyperSerial drivers (ESP32 / ESP8266 / Pico) implement the
base AWA protocol: an `Awa` / `AwA` header, 8-bit RGB pixel data (with
optional V2 calibration and V3 direct-RGBW), a Fletcher checksum, and a
simple LUT-based RGB-to-RGBW conversion for white-channel strips.

This sketch extends that foundation substantially.  The table below
summarizes every major divergence.

### Transport

| Feature | Stock HyperSerial | This Sketch |
|---|---|---|
| Transport | UART serial only | USB RawHID (primary) + serial fallback |
| RawHID framing | N/A | `'H','D'` magic, 2-byte length, payload bytes fed into the same AWA state machine |
| RawHID log channel | N/A | `'H','L'` magic — device-to-host log packets over the same RawHID endpoint |
| Input sync gating | N/A | Serial reads are blocked at `HEADER_A` until the current BFI display cycle completes, preventing input overrun; a backlog bypass threshold allows draining if the serial buffer grows too large |

### Protocol Extensions

The base AWA header is `A`, `w`/`W`, `a`/`A` (3 bytes) followed by LED
count (hi, lo) and CRC.  Stock HyperSerial uses the second and third
bytes to select between RGB (`Awa`), RGB+V2 calibration (`AwA`), and
direct RGBW V3 (`AWa`).

This sketch adds new second-byte and third-byte codes to encode
additional frame metadata.  All extensions are backward-compatible — the
base `Awa` / `AwA` paths still work for plain 8-bit RGB.

| Header byte 2 | Meaning |
|---|---|
| `'w'` | Standard RGB (same as stock) |
| `'W'` | Host-derived RGBW — white channel computed on the host, sent as a 4th channel per pixel |
| `'t'` | Transfer-curve config trailer (RGB, no host white) |
| `'T'` | Host-derived RGBW + transfer-curve config trailer |

| Header byte 3 | Bit depth | Scene policy | Highlight/shadow mask |
|---|---|---|---|
| `'a'` / `'A'` | 8-bit (V1 / V2) | — | — |
| `'b'` / `'B'` | 16-bit (V1 / V2) | — | — |
| `'c'` / `'C'` | 12-bit+carry (V1 / V2) | — | — |
| `'d'` | 16-bit or 12-bit+carry | yes | — |
| `'e'` | 12-bit+carry | yes | — |
| `'f'` | 16-bit | yes | yes |
| `'g'` | 12-bit+carry | yes | yes |

When host-RGBW (`'W'`/`'T'`) is active, the same third-byte codes apply
but are decoded against the host-RGBW variant table.

#### Pixel payload formats

| Format | Bytes per pixel | Description |
|---|---|---|
| 8-bit RGB | 3 | `R G B` — upscaled to Q16 internally via `scale8ToQ16()` |
| 16-bit RGB(W) | 6 (or 8) | `R_hi R_lo G_hi G_lo B_hi B_lo [W_hi W_lo]` — native Q16 |
| 12-bit+carry RGB(W) | 4 (or 5) | `R G B [W] carry_RG carry_B` — 4-bit LSB nybbles packed into trailing carry bytes, reconstructed to Q16 via `scale12ToQ16()` |

#### Post-pixel trailer fields

After all pixel data, the frame may include any combination of:

| Field | Condition | Bytes | Purpose |
|---|---|---|---|
| V2 calibration | V2 flag set | 4 | Gain, R, G, B channel weights — sets `runtimeWhiteLimit` |
| Scene policy | Scene-policy flag | 4 | Magic, offset, 2 reserved bytes |
| Highlight/shadow mask | Highlight flag | ceil(LED_COUNT/8) | Per-pixel bitmask for highlight detection |
| Transfer config | Transfer flag | 2 | Curve flags byte + profile index byte — tells driver whether transfer curve and calibration were already applied by the host |
| Fletcher checksum | Always | 3 | `f1`, `f2`, `fext` — extended Fletcher integrity check |

#### Control frames

A frame with the sentinel count value `0x2AA2` is a control command
instead of pixel data.  The `fext` byte selects the command:

| `fext` | Action |
|---|---|
| `0x15` | Print hello / stats |
| `0x10` | Set global brightness |
| `0x11` | Set white calibration |
| `0x12` | Set runtime white limit |
| `0x13` | Toggle derived solver LUT size |

### Color Pipeline

| Stage | Stock HyperSerial | This Sketch |
|---|---|---|
| White extraction | 8-bit LUT: `min(calR[R], calG[G], calB[B])` with subtraction | 16-bit Q16 domain: either host-computed white or solver `extractRgbw()` with measured luma weights and calibration profiles |
| Transfer curve | None | Optional BT.1886-derived curve applied per-channel in Q16; can be applied on-device or flagged as host-applied |
| Input calibration | V2 gain/RGB bytes build a 256-entry LUT | Q16 calibration profile with per-channel curves; can be applied on-device or flagged as host-applied |
| Temporal solve | None | `SolverRuntime::solve()` per channel — maps Q16 input to encoded upper/floor values + BFI level |

### BFI Rendering

Stock HyperSerial writes each pixel once per frame.  This sketch renders
a multi-phase BFI cycle:

- **Cycle length** adapts to input frame rate via the input-sync cycle cap.
  Low-FPS input (< split threshold) gets a shorter cycle; high-FPS input
  gets up to `MAX_BFI_FRAMES + 1` phases.
- **Per-pixel BFI maps** (`bfiMapR`, `bfiMapG`, `bfiMapB`, `bfiMapW`) hold
  the solver-determined BFI level for each channel of each LED.  Brighter
  subpixels stay lit for more phases; dim subpixels blank early.
- **Upper/floor frame buffers** store the two intensity values that the
  solver alternates between.  `renderSubpixelBFI_RGBW()` selects upper or
  floor based on the current `bfiPhase` and each pixel's BFI map entry.
- **Phase advance** happens in `loop()`.  When the phase wraps around to
  zero, `frame_finished_displaying` is set, allowing the next input frame
  to be consumed.

---

## Power Limiting

This sketch implements two complementary power-limiting systems.

### 1. PSU Current Budget (`computeTargetFramePower`)

At startup, the static `ABL_POWER_LIMIT` fallback is replaced by a value
derived from real PSU and LED electrical parameters:

| Define | Default | Meaning |
|---|---|---|
| `PSU_MAX_CURRENT_MA` | 200000 | PSU maximum output current (mA) |
| `PSU_EFFICIENCY_PERCENT` | 85 | Derate factor for real-world losses |
| `LED_CHANNEL_CURRENT_MA` | 20 | Per-channel (R/G/B) current at full |
| `LED_WHITE_CHANNEL_CURRENT_MA` | 20 | White channel current at full |
| `POWER_WEIGHT_R/G/B/W` | 10/15/15/15 | Render-domain power weights per channel (based on SK6812 Vf × If) |

The formula converts the effective PSU current into the same per-pixel
power-weight domain used by the render pass, so the limiter's threshold
matches the physical current budget.

### 2. Frame Power Limiter (per-frame feedback loop)

When `ENABLE_FRAME_POWER_LIMIT` is true, a per-frame feedback limiter
runs after the BFI render pass:

1. **Power estimation** — during `renderIndependentSubpixelBFI()`, each
   pixel's RGBW subpixel values are multiplied by their power weights and
   by `invCycleQ8[bfi]` (compensating for BFI duty cycle) and accumulated
   into `renderPowerQ8`.
2. **Voltage-droop model** — if total power exceeds `DROOP_START_Q8` of
   the target, a linear sag factor is applied, bottoming out at
   `DROOP_MIN_SAG_Q8`.  This models real PSU voltage sag under heavy load.
3. **Over-power scale** — `frameScaleQ8 = targetPower * 256 / totalPower`.
4. **Hysteresis** — the limiter activates when the combined scale drops
   below `FRAME_LIMITER_ENTER_Q8` and deactivates when it rises above
   `FRAME_LIMITER_EXIT_Q8`, preventing flicker at the boundary.
5. **IIR smoothing** — separate attack (`FRAME_LIMITER_ATTACK_Q8`) and
   release (`FRAME_LIMITER_RELEASE_Q8`) time constants smooth the dimming
   transition.  Attack is fast (visible dim-down within one frame); release
   is slow (gradual recovery avoids popping).
6. **Feed-forward** — the smoothed scale is fed back into
   `frameLimiterFeedForwardScaleQ8`, which pre-scales the Q16 values
   entering the solver on the *next* frame.  This keeps the limiter's
   brightness reduction aligned with the solver's LUT behavior instead of
   applying a crude post-render clamp.
7. **Application** — the final smoothed scale is applied to all four RGBW
   channels of `displayBuffer[]` in-place before `leds.show()`.

Phase caching ensures the power estimate and scale are computed only once
per BFI cycle (on `bfiPhase == 0`).  Subsequent phases reuse the cached
scale and only perform the per-pixel multiply.

---

## Hardware Configuration

The sketch is configured for a Teensy 4.0 at 960 MHz driving 1200
SK6812 RGBW LEDs across 25 ObjectFLED output pins (48 LEDs per pin).
Key defines:

| Define | Value |
|---|---|
| `NUM_PINS` | 25 |
| `LEDS_PER_PIN` | 48 |
| `LED_COUNT` | 1200 |
| `MAX_BFI_FRAMES` | 4 (cycle length up to 5) |
| `SERIAL_BAUD` | 30000000 |

Buffers for frame data, floor data, BFI maps, and the display output are
placed in DMAMEM to keep RAM1 free for the stack and real-time state.

---

## Build

This sketch is part of the TemporalBFI PlatformIO project.  Build with:

```
pio run -e HyperTeensy_Temporal_Blend
```

Or use the PlatformIO IDE build button.  The environment expects a
Teensy 4.0 with USB type set to RawHID.
