# TemporalBFI — API Reference

> **Auto-generated** by `generate_api_docs.py`. Descriptions are taken from adjacent C++ `///` / `/** */` comments when present; manual descriptions are preserved for symbols that still lack source comments.

> API status notes mark current consolidated APIs and specialized color-order / shared-LUT / transfer-curve surfaces.

---

## API Status Legend

- **Current render/commit API**: preferred surface for new examples/code.
- **Current color-order API**: use to make physical byte order explicit.
- **Current solver LUT storage API**: opt-in shared-LUT controls and related query helpers.
- **Current transfer-curve API**: shared transfer curve is the default; per-channel transfer is opt-in compatibility.

## Contents

- [CubeLUT3D.h](#cubelut3dh)
- [TemporalBFI.h](#temporalbfih)
- [TemporalBFIColorOrder.h](#temporalbficolororderh)
- [TemporalBFIRenderCommit.h](#temporalbfirendercommith)
- [TemporalBFIRuntime.h](#temporalbfiruntimeh)
- [TemporalTrue16BFIPolicySolver_per_bfi_v3.h](#temporaltrue16bfipolicysolverperbfiv3h)

---

## CubeLUT3D.h

### File-level

| Kind | Signature | Description |
|------|-----------|-------------|
| enum | `enum class CubeLUTInterpolation { Trilinear, Tetrahedral }` | Interpolation algorithm used for 3D cube lookup. |
| constant | `static constexpr uint16_t CUBE_HEADER_BYTES` |  |
| constant | `static constexpr uint8_t CUBE_MAX_SUPPORTED_CHANNELS` | Maximum channel count accepted by CubeLUT3D payloads. |
| struct | `struct CubeLUT3D` | Non-owning 3D color-correction cube view and lookup engine. |

### `CubeLUT3D`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `uint8_t channels` | Stored output channel count; valid cubes support 3..CUBE_MAX_SUPPORTED_CHANNELS. |
| field | `uint16_t* data` | Caller-owned cube payload: gridSize^3 * channels uint16 values. |
| field | `uint16_t gridSize` | Cube dimension per axis; valid cubes require gridSize >= 2. |
| field | `CubeLUTInterpolation interpolation` | Active interpolation algorithm. |
| method | `void attach(uint16_t* cubeData, uint16_t grid, uint8_t ch)` | Attach a pre-populated, caller-owned data buffer. The buffer must contain gridSize³ × channels uint16 values. |
| method | `CubeLUTInterpolation interpolationMode() const` | Return the active interpolation mode. |
| method | `bool isRGB() const` | Return true when the attached cube has RGB output. |
| method | `bool isRGBW() const` | Return true when the attached cube has RGBW output. |
| method | `bool isRGBWW() const` | Return true when the attached cube has RGBWW/RGBCCT-style output. |
| method | `bool isValid() const` | Return true when data, grid size, and channel count describe a usable cube. |
| method | `bool loadFromFileBuffer(const uint8_t* fileBuffer, size_t fileSize)` | Load from a complete file buffer (4-byte header followed by payload). The `data` pointer must already point to a buffer of at least dataBytes(grid, ch) bytes — call parseHeader() first to discover the size, allocate, then call this. Returns false on header mismatch or insufficient buffer size. |
| method | `RgbwTargets lookup(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const` | Interpolated lookup (trilinear or tetrahedral).  Maps input RGB (Q16) through the cube and returns logical RGBW output. For RGBW cubes all four channels are populated. For RGB cubes, wQ16 is always 0. |
| method | `uint8_t lookupChannels(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16, uint16_t* outValues, uint8_t outCapacity) const` | Raw logical channel lookup. Returns number of channels written (up to outCapacity), or 0 on invalid cube. |
| method | `RgbwwTargets lookupRgbww(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const` | Logical RGBWW/RGBCCT output. For cubes with <5 channels, missing channels are returned as 0. |
| method | `void setDefaultInterpolationForChannels()` | Apply default interpolation policy by channel family: - RGB (3ch): Trilinear - RGBW/RGBCCT/future 5-6ch: Tetrahedral |
| method | `void setInterpolation(CubeLUTInterpolation mode)` | Set interpolation mode explicitly. |
| method | `bool setLogicalToStoredMap(const uint8_t* map, uint8_t count)` | Configure logical-to-stored channel mapping. `count` must equal current `channels` and describe a permutation over [0..channels-1]. |
| static method | `static size_t dataBytes(uint16_t grid, uint8_t ch)` | Data payload size in bytes (excludes the 4-byte file header). |
| static method | `static size_t fileBytes(uint16_t grid, uint8_t ch)` | Total file size including the 4-byte header. |
| static method | `static uint16_t maxGridForBytes(size_t availableBytes, uint8_t ch)` | Largest grid size whose data fits within `availableBytes`. |
| static method | `static bool parseHeader(const uint8_t* header4, uint16_t& outGrid, uint8_t& outChannels)` | Parse the 4-byte file header.  Returns true if the header describes a valid cube (grid >= 2, channels in 3..CUBE_MAX_SUPPORTED_CHANNELS). |

---

## TemporalBFI.h

### File-level

| Kind | Signature | Description |
|------|-----------|-------------|
| enum | `enum class BfiMapStorageMode { Separate, Packed }` | Storage layout for BFI maps passed to consolidated render/commit APIs. |
| enum | `enum class FifthChannelSolveMode { EmulateFromW, Native }` | Controls whether logical W2 uses the W ladder or a native fifth-channel ladder. |
| enum | `enum class LedColorOrder { GRB, RGB, BRG, BGR, RBG, GBR, GRBW, GRWB, GBRW, GBWR, GWRB, GWBR, RGBW, RGWB, RBGW, RBWG, RWGB, RWBG, BGRW, BGWR, BRGW, BRWG, BWGR, BWRG, WRGB, WRBG, WGRB, WGBR, WBRG, WBGR, GRBW1W2, GRBW2W1, RGBW1W2, RGBW2W1, W1W2RGB, W2W1RGB, W1RGBW2, W2RGBW1, W1GRBW2, W2GRBW1 }` | **Current color-order API.** Use to make logical-vs-physical channel order explicit. Physical byte-order presets for mapping logical solver channels to LED buffers. |
| enum | `enum class PhaseMode { FixedMask, Distributed, DistributedGlobal }` | Phase distribution mode for BFI rendering. |
| enum | `enum class PixelLayout { RGB, RGBW, RGBWW, RGBCCT }` | Logical pixel layout used to derive channel count for LUT and render paths. |
| enum | `enum class SolverLUTMode { PerChannel, Shared }` | **Current solver LUT storage API.** Shared mode is opt-in for low-memory/bringup use. Selects per-channel solver LUT storage or one shared LUT set. |
| enum | `enum class TransferCurveMode { Single, LegacyPerChannel }` | **Current transfer-curve API.** Single shared curve is the default; per-channel curves are legacy/opt-in. Selects shared single-curve transfer lookup or opt-in per-channel curves. |
| enum | `enum class WhitePolicy { Disabled, NearNeutralOnly, AlwaysAllowed, WhitePriority, MeasuredOptimal }` | Strategy for deciding when extracted white output is allowed. |
| using | `using CalibrationFn = uint16_t (*)(uint16_t q16, uint8_t channel)` | Calibration callback that maps an input Q16 value and logical channel to calibrated Q16. |
| using | `using SolverFn = EncodedState (*)(uint16_t q16, uint8_t channel, const PolicyConfig& cfg)` | Solver callback that maps a Q16 value and logical channel to an EncodedState. |
| constant | `static constexpr uint16_t INV_CYCLE_Q8` |  |
| constant | `static constexpr uint8_t MAX_SUPPORTED_CYCLE_LENGTH` |  |
| constant | `static constexpr uint16_t PACKED_BFI_BYTES_PER_PIXEL` |  |
| constant | `static constexpr uint8_t PHASE_EMIT_MASK` |  |
| constant | `static constexpr uint8_t SOLVER_DEFAULT_CHANNELS` |  |
| constant | `static constexpr uint8_t SOLVER_FIXED_BFI_LEVELS` |  |
| constant | `static constexpr uint8_t SOLVER_MAX_CHANNELS` |  |
| struct | `struct BfiMapView` | **Current render/commit API.** Preferred for new examples/code. Read-only BFI map view for render APIs; provide separate maps or a packed map. |
| struct | `struct BfiMapWriteView` | **Current render/commit API.** Preferred for new examples/code. Mutable BFI map view for commit APIs; provide separate maps or a packed map. |
| struct | `struct CalibrationMixingConfig` | Weighting and threshold knobs used by measured RGBW calibration profiles. |
| struct | `struct CalibrationProfile` | Non-owning calibration LUT bundle; caller owns all referenced tables. |
| struct | `struct EncodedState` | Solver output state for a single channel; per_bfi_v3.h aliases this canonical type. |
| struct | `struct LadderEntry` | Measured ladder sample used by the policy solver for one output state. |
| struct | `struct PolicyConfig` | Solver policy tuning knobs; per_bfi_v3.h aliases this canonical type. |
| struct | `struct RenderOptions` | **Current render/commit API.** Preferred for new examples/code. Render/commit options for logical channel layout, physical byte order, and BFI map storage. |
| struct | `struct RgbwTargets` | Four-channel RGBW target values in Q16. |
| struct | `struct RgbwwTargets` | **Current RGBWW/RGBCCT API.** Supports 5-channel bringup and dual-white paths. Five-channel RGBWW/RGBCCT-style target values in Q16. |
| class | `class SolverRuntime` |  |
| inline function | `uint16_t applyScaleQ8(uint16_t q16, uint16_t scaleQ8)` |  |
| inline function | `bool channelOnPhase(uint8_t bfi, uint8_t phase)` |  |
| inline function | `bool channelOnTickDistributedGlobal(uint8_t bfi, uint32_t tick, uint8_t cycleLength)` |  |
| inline function | `bool channelOnTickPerBfi(uint8_t bfi, uint32_t tick)` |  |
| inline function | `uint8_t clampBfi(uint8_t bfi)` |  |
| inline function | `uint16_t invCycleQ8ForBfi(uint8_t bfi, uint8_t cycleLength)` |  |
| inline function | `uint16_t invCycleQ8ForBfiPerBfi(uint8_t bfi)` |  |
| inline function | `size_t lutIndexForSize(uint16_t q16, uint16_t lutSize)` |  |
| inline function | `uint16_t min3U16(uint16_t a, uint16_t b, uint16_t c)` |  |
| inline function | `uint16_t mulQ16(uint16_t a, uint16_t b)` |  |
| inline function | `void packBfi3(uint8_t* packed, uint16_t pixelIndex, uint8_t g, uint8_t r, uint8_t b)` |  |
| inline function | `void packBfi4(uint8_t* packed, uint16_t pixelIndex, uint8_t g, uint8_t r, uint8_t b, uint8_t w)` |  |
| inline function | `uint8_t readPackedBfiChannel(const uint8_t* packed, uint16_t pixelIndex, uint8_t channelGRBW)` |  |
| inline function | `uint16_t scale12ToQ16(uint16_t value12)` |  |
| inline function | `uint16_t scale4ToQ16(uint8_t value4)` |  |
| inline function | `uint16_t scale8ToQ16(uint8_t value)` |  |
| inline function | `uint8_t scaleQ16To8(uint16_t q16)` |  |
| inline function | `void unpackBfi3(const uint8_t* packed, uint16_t pixelIndex, uint8_t& g, uint8_t& r, uint8_t& b)` |  |
| inline function | `void unpackBfi4(const uint8_t* packed, uint16_t pixelIndex, uint8_t& g, uint8_t& r, uint8_t& b, uint8_t& w)` |  |
| inline function | `void writePackedBfiChannel(uint8_t* packed, uint16_t pixelIndex, uint8_t channelGRBW, uint8_t value)` |  |

### `LadderEntry`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `uint16_t outputQ16` |  |

### `CalibrationMixingConfig`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `uint16_t neutralThresholdQ16` |  |
| field | `uint16_t rgbWeightQ16` |  |
| field | `WhitePolicy whitePolicy` |  |
| field | `uint16_t whiteWeightQ16` |  |

### `CalibrationProfile`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `const uint16_t* lutB16` |  |
| field | `const uint16_t* lutB8To16` |  |
| field | `const uint16_t* lutG16` |  |
| field | `const uint16_t* lutG8To16` |  |
| field | `const uint16_t* lutR16` |  |
| field | `const uint16_t* lutR8To16` |  |
| field | `const uint16_t* lutW16` |  |
| field | `const uint16_t* lutW8To16` |  |
| field | `CalibrationMixingConfig mixing` |  |

### `RenderOptions`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `BfiMapStorageMode bfiMapStorage` |  |
| field | `LedColorOrder colorOrder` |  |

### `BfiMapView`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `const uint8_t* bfiMapB` |  |
| field | `const uint8_t* bfiMapG` |  |
| field | `const uint8_t* bfiMapR` |  |
| field | `const uint8_t* bfiMapW1` |  |
| field | `const uint8_t* bfiMapW2` |  |
| field | `const uint8_t* packedBfiMap` |  |

### `BfiMapWriteView`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `uint8_t* bfiMapB` |  |
| field | `uint8_t* bfiMapG` |  |
| field | `uint8_t* bfiMapR` |  |
| field | `uint8_t* bfiMapW1` |  |
| field | `uint8_t* bfiMapW2` |  |
| field | `uint8_t* packedBfiMap` |  |

### `RgbwTargets`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `uint16_t bQ16` |  |
| field | `uint16_t gQ16` |  |
| field | `uint16_t rQ16` |  |
| field | `uint16_t wQ16` |  |

### `RgbwwTargets`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `uint16_t bQ16` |  |
| field | `uint16_t gQ16` |  |
| field | `uint16_t rQ16` |  |
| field | `uint16_t w1Q16` |  |
| field | `uint16_t w2Q16` |  |

### `EncodedState`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `uint8_t bfi` |  |
| field | `uint16_t ladderIndex` |  |
| field | `uint8_t lowerValue` |  |
| field | `uint16_t outputQ16` |  |
| field | `uint8_t value` |  |

### `PolicyConfig`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `bool enableInputQ16Calibration` |  |
| field | `uint8_t highlightBypassStart` |  |
| field | `uint8_t lowEndMaxDrop` |  |
| field | `uint8_t lowEndProtectThreshold` |  |
| field | `uint8_t maxBFI` |  |
| field | `uint16_t minErrorQ16` |  |
| field | `uint8_t minValueRatioDenominator` |  |
| field | `uint8_t minValueRatioNumerator` |  |
| field | `bool preferHigherBFI` |  |
| field | `uint8_t preferredMinBFI` |  |
| field | `uint16_t relativeErrorDivisor` |  |

### `SolverRuntime`

| Kind | Signature | Description |
|------|-----------|-------------|
| method | `uint8_t activeRenderChannelCount() const` | **Current color-order API.** Use to make logical-vs-physical channel order explicit. Return the current render channel count derived from ledColorOrder(). |
| method | `bool advanceTick()` | Advance the internal tick counter. Returns true when the tick reaches a cycle boundary (start of a new display cycle). |
| method | `uint16_t applyCalibration(uint16_t q16, uint8_t channel) const` | Apply the active input calibration callback to one Q16 value and channel. |
| method | `RgbwTargets applyCubeLUT3D(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const` | Look up (rQ16, gQ16, bQ16) through the attached 3D cube. Legacy RGBW-compatible view: for 5-channel cubes this returns W1. If the cube is disabled or missing, returns passthrough RGB + W=0. |
| method | `RgbwwTargets applyCubeLUT3D_RGBWW(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const` | **Current RGBWW/RGBCCT API.** Supports 5-channel bringup and dual-white paths. RGBWW/RGBCCT-capable cube lookup. For RGB cubes: W1=W2=0. For RGBW cubes: W2=0. If the cube is disabled or missing, returns passthrough RGB + W1/W2=0. |
| method | `uint16_t applyTransferCurve(uint16_t q16, uint8_t channel) const` | Apply the active transfer curve to a Q16 value for the requested logical channel. |
| method | `RgbwTargets applyWhiteLimit(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16, uint16_t wQ16) const` | Clamp white output and redistribute excess into RGB channels where possible. |
| method | `void attachLUTs(uint8_t* valueLUT, uint8_t* bfiLUT, uint8_t* floorLUT, uint16_t* outputQ16LUT, uint16_t lutSize)` | Attach caller-owned solver LUT buffers and set the LUT size used by solve/precompute/load. |
| method | `bool calibrationEnabled() const` | Return whether input calibration is enabled. |
| method | `bool channelActiveOnCurrentTick(uint8_t bfi) const` | Check whether a channel with the given BFI level shows its upper value on the current internal tick, using the configured mode. |
| method | `PolicyConfig& config()` | Mutable access to solver policy knobs used by precompute and runtime solve helpers. |
| method | `const PolicyConfig& config() const` | Read-only access to solver policy knobs. |
| method | `bool cubeLUT3DEnabled() const` | Return whether cube LUT lookup is enabled. |
| method | `uint32_t currentTick() const` | Return the current internal render tick. |
| method | `uint8_t cycleLength() const` | Return the active global cycle length. |
| method | `void dumpLUTHeader(Print& out) const` | Emit the currently attached LUTs as an embeddable PROGMEM header. |
| method | `RgbwTargets extractRgbw(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const` | Extract RGBW targets from RGB input using the configured calibration and white policy. |
| method | `RgbwwTargets extractRgbwwEmulated(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const` | **Current RGBWW/RGBCCT API.** Supports 5-channel bringup and dual-white paths. Split extracted white equally into W1/W2 for RGBWW/RGBCCT bringup emulation. |
| method | `FifthChannelSolveMode fifthChannelSolveMode() const` | Return the active fifth-channel solve mode. |
| method | `LedColorOrder ledColorOrder() const` | **Current color-order API.** Use to make logical-vs-physical channel order explicit. Return the active physical byte-order mapping. |
| method | `void loadPrecomputed(const uint8_t* srcValue, const uint8_t* srcBfi, const uint8_t* srcFloor, const uint16_t* srcOutputQ16, uint8_t numChannels = SOLVER_DEFAULT_CHANNELS, uint16_t srcLutSize = 0)` | Load precomputed solver LUT tables; srcLutSize guards against stride mismatches when nonzero. |
| method | `void loadPrecomputed(const uint8_t* srcValue, const uint8_t* srcBfi, const uint8_t* srcFloor, const uint16_t* srcOutputQ16, PixelLayout layout, uint16_t srcLutSize = 0)` | Load precomputed LUTs using a PixelLayout-derived channel count. |
| method | `uint16_t lutSize() const` | Return the active solver LUT size, or 0 if LUT storage is not attached. |
| method | `PhaseMode phaseMode() const` | Return the active BFI phase distribution mode. |
| method | `void precompute(SolverFn fn, uint8_t numChannels = SOLVER_DEFAULT_CHANNELS)` | Precompute solver LUTs; Shared mode computes one storage channel reused by all logical channels. |
| method | `void precompute(SolverFn fn, PixelLayout layout)` | Precompute solver LUTs using a PixelLayout-derived channel count. |
| method | `void renderIndexed(const uint8_t* upperFrame, const uint8_t* floorFrame, const BfiMapView& bfiMaps, uint8_t* displayBuffer, uint16_t pixelIndex, const RenderOptions* options = nullptr) const` | **Current render/commit API.** Preferred for new examples/code. Render one pixel using the configured PhaseMode and current internal tick. |
| method | `void renderLoop(const uint8_t* upperFrame, const uint8_t* floorFrame, const BfiMapView& bfiMaps, uint8_t* displayBuffer, uint16_t pixelCount, const RenderOptions* options = nullptr) const` | **Current render/commit API.** Preferred for new examples/code. Render a full buffer using the configured PhaseMode and current internal tick. |
| method | `void resetTick()` | Reset the internal render tick to 0. |
| method | `void setCalibrationEnabled(bool enabled)` | Enable or disable input calibration callback application. |
| method | `void setCalibrationFunction(CalibrationFn fn)` | Register a per-channel input calibration callback used before solving. |
| method | `void setCubeLUT3D(const CubeLUT3D* cube)` | Attach a non-owning 3D cube LUT pointer for RGB-to-output color correction. |
| method | `void setCubeLUT3DEnabled(bool enabled)` | Enable or disable cube LUT lookup in the input pipeline. |
| method | `bool setCustomColorOrderMap3(const uint8_t map[3])` | **Current color-order API.** Use to make logical-vs-physical channel order explicit. Set a custom 3-channel logical-to-physical map; entries must be a permutation of [0..2]. |
| method | `bool setCustomColorOrderMap4(const uint8_t map[4])` | **Current color-order API.** Use to make logical-vs-physical channel order explicit. Set a custom 4-channel logical-to-physical map; entries must be a permutation of [0..3]. |
| method | `bool setCustomColorOrderMap5(const uint8_t map[5])` | **Current color-order API.** Use to make logical-vs-physical channel order explicit. Set a custom 5-channel logical-to-physical map; entries must be a permutation of [0..4]. |
| method | `void setCycleLength(uint8_t len)` | Set the global cycle length used by DistributedGlobal mode, clamped to the supported range. |
| method | `void setFifthChannelSolveMode(FifthChannelSolveMode mode)` | Select whether logical W2 solves through W emulation or a native fifth-channel ladder. |
| method | `void setLedColorOrder(LedColorOrder order)` | **Current color-order API.** Use to make logical-vs-physical channel order explicit. Configure physical byte-order mapping for rendered buffers; solver/commit order remains logical GRB(W/W1W2). |
| method | `void setPhaseMode(PhaseMode mode)` | Set the BFI phase distribution mode used by instance render APIs. |
| method | `void setSolverLUTMode(SolverLUTMode mode)` | **Current solver LUT storage API.** Shared mode is opt-in for low-memory/bringup use. Select solver LUT storage mode: PerChannel for calibrated output, Shared for low-memory/bringup. |
| method | `void setTransferCurve(const uint16_t* curve, uint16_t bucketCount)` | **Current transfer-curve API.** Single shared curve is the default; per-channel curves are legacy/opt-in. Attach one shared transfer curve LUT for all logical channels. |
| method | `void setTransferCurve(const uint16_t* curveR, const uint16_t* curveG, const uint16_t* curveB, const uint16_t* curveW, uint16_t bucketCount)` | **Current transfer-curve API.** Single shared curve is the default; per-channel curves are legacy/opt-in. Attach per-channel RGBW transfer curves and select LegacyPerChannel mode. |
| method | `void setTransferCurve(const uint16_t* curveR, const uint16_t* curveG, const uint16_t* curveB, const uint16_t* curveW, uint16_t bucketCount, const uint16_t* curveW2)` | **Current transfer-curve API.** Single shared curve is the default; per-channel curves are legacy/opt-in. Attach per-channel RGBWW/RGBCCT transfer curves and select LegacyPerChannel mode. |
| method | `void setTransferCurveEnabled(bool enabled)` | Enable or disable transfer-curve application in the input pipeline. |
| method | `void setTransferCurveMode(TransferCurveMode mode)` | **Current transfer-curve API.** Single shared curve is the default; per-channel curves are legacy/opt-in. Select shared or per-channel transfer-curve lookup mode. |
| method | `void setWhiteLimit(uint8_t limit)` | Set the maximum 8-bit white-channel value allowed by applyWhiteLimit(). |
| method | `EncodedState solve(uint16_t q16, uint8_t channel) const` | Look up a Q16 target for one logical channel and return the encoded temporal state. |
| method | `EncodedState solveWhiteEmulated(uint16_t q16) const` | **Current RGBWW/RGBCCT API.** Supports 5-channel bringup and dual-white paths. Solve a white target through the existing W solver/LUT path for RGBWW/RGBCCT emulation. |
| method | `SolverLUTMode solverLUTMode() const` | **Current solver LUT storage API.** Shared mode is opt-in for low-memory/bringup use. Return the active solver LUT storage mode. |
| method | `bool solverLUTSharedModeEnabled() const` | **Current solver LUT storage API.** Shared mode is opt-in for low-memory/bringup use. Return true when solve lookups use one shared LUT storage channel. |
| method | `size_t solverLutIndex(uint16_t q16) const` | Convert a Q16 value to the nearest active LUT index. |
| method | `bool transferCurveEnabled() const` | Return whether transfer-curve application is enabled. |
| method | `TransferCurveMode transferCurveMode() const` | **Current transfer-curve API.** Single shared curve is the default; per-channel curves are legacy/opt-in. Return the active transfer-curve lookup mode. |
| method | `uint8_t whiteLimit() const` | Return the configured white-channel limit. |
| static method | `static uint8_t channelCountForColorOrder(LedColorOrder order)` | **Current color-order API.** Use to make logical-vs-physical channel order explicit. Derive channel count from a color-order contract: RGB=3, RGBW=4, RGBWW/RGBCCT=5. |
| static method | `static void commitPixel(uint8_t* upperFrame, uint8_t* floorFrame, BfiMapWriteView& bfiMaps, uint16_t pixelIndex, const EncodedState* channelStates, uint8_t stateCount, const RenderOptions& options)` | **Current render/commit API.** Preferred for new examples/code. Commit one pixel's encoded channel states to logical frame buffers and BFI maps. |
| static method | `static void renderIndexedStatic(const uint8_t* upperFrame, const uint8_t* floorFrame, const BfiMapView& bfiMaps, uint8_t* displayBuffer, uint16_t pixelIndex, uint8_t phase, const RenderOptions& options)` | **Current render/commit API.** Preferred for new examples/code. Render one pixel using an explicit FixedMask phase and RenderOptions. |
| static method | `static void renderLoopStatic(const uint8_t* upperFrame, const uint8_t* floorFrame, const BfiMapView& bfiMaps, uint8_t* displayBuffer, uint16_t pixelCount, uint8_t phase, const RenderOptions& options)` | **Current render/commit API.** Preferred for new examples/code. Render a full buffer using an explicit FixedMask phase and RenderOptions. |

---

## TemporalBFIColorOrder.h

> Implementation declarations for LedColorOrder mapping tables, channel-count derivation, custom-map validation, and color-order wiring on SolverRuntime.

_No public API symbols detected._

---

## TemporalBFIRenderCommit.h

> Implementation module marker for consolidated render/commit methods, BFI map storage helpers, and phase/tick render dispatch. Public declarations remain centralized in TemporalBFI.h.

_No public API symbols detected._

---

## TemporalBFIRuntime.h

### File-level

| Kind | Signature | Description |
|------|-----------|-------------|
| constant | `static constexpr uint8_t PHASE_EMIT_MASK` |  |
| constant | `static constexpr uint8_t SOLVER_FIXED_BFI_LEVELS` |  |
| constant | `static constexpr uint16_t SOLVER_LUT_SIZE` |  |
| constant | `static constexpr uint16_t SOLVER_LUT_SIZE` |  |
| inline function | `bool channelOnThisTick(uint8_t bfi, uint32_t tick, uint8_t cycleLen)` |  |
| inline function | `size_t solverLutIndexFromQ16(uint16_t q16, uint16_t lutSize)` |  |
| inline function | `size_t solverLutIndexFromQ16(uint16_t q16)` |  |

---

## TemporalTrue16BFIPolicySolver_per_bfi_v3.h

### File-level

| Kind | Signature | Description |
|------|-----------|-------------|
| using | `using EncodedState = TemporalBFI::EncodedState` |  |
| using | `using PolicyConfig = TemporalBFI::PolicyConfig` |  |
| inline function | `uint16_t absDiffU16(uint16_t a, uint16_t b)` |  |
| inline function | `uint16_t allowedErrorQ16(uint16_t targetQ16, const PolicyConfig& cfg)` |  |
| inline function | `uint16_t calibrateInputQ16ForSolver(uint16_t inputQ16, uint8_t channel, bool enableCalibration = true)` |  |
| inline function | `EncodedState encodeStateFrom16(uint16_t q16, uint8_t channel, const PolicyConfig& cfg = PolicyConfig()` |  |
| inline function | `bool passesBaselinePolicy(uint8_t input8Approx, uint8_t candidateBFI, const PolicyConfig& cfg)` |  |
| inline function | `bool passesResolutionGuard(uint8_t input8Approx, uint8_t candidateValue, const PolicyConfig& cfg)` |  |
| inline function | `uint8_t resolveLowerValueFromLadderIndex(uint8_t channel, uint16_t ladderIndex, uint8_t fallbackValue)` |  |
| inline function | `EncodedState solveStateFromQ16Internal(uint16_t targetQ16, uint8_t input8Approx, uint8_t channel, const PolicyConfig& cfg)` |  |

