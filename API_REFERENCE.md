# TemporalBFI — API Reference

> **Auto-generated** by `generate_api_docs.py`. Descriptions can be filled in manually; re-running the script preserves them via `.api_descriptions.json`.

---

## Contents

- [CubeLUT3D.h](#cubelut3dh)
- [TemporalBFI.h](#temporalbfih)
- [TemporalBFIRuntime.h](#temporalbfiruntimeh)
- [TemporalTrue16BFIPolicySolver_per_bfi_v3.h](#temporaltrue16bfipolicysolverperbfiv3h)

---

## CubeLUT3D.h

### File-level

| Kind | Signature | Description |
|------|-----------|-------------|
| constant | `static constexpr uint16_t CUBE_HEADER_BYTES` |  |
| struct | `struct CubeLUT3D` |  |

### `CubeLUT3D`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `uint8_t channels` |  |
| field | `uint16_t* data` |  |
| field | `uint16_t gridSize` |  |
| method | `void attach(uint16_t* cubeData, uint16_t grid, uint8_t ch)` |  |
| method | `bool isRGBW() const` |  |
| method | `bool isValid() const` |  |
| method | `bool loadFromFileBuffer(const uint8_t* fileBuffer, size_t fileSize)` |  |
| method | `RgbwTargets lookup(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const` |  |
| static method | `static size_t dataBytes(uint16_t grid, uint8_t ch)` |  |
| static method | `static size_t fileBytes(uint16_t grid, uint8_t ch)` |  |
| static method | `static uint16_t maxGridForBytes(size_t availableBytes, uint8_t ch)` |  |
| static method | `static bool parseHeader(const uint8_t* header4, uint16_t& outGrid, uint8_t& outChannels)` |  |

---

## TemporalBFI.h

### File-level

| Kind | Signature | Description |
|------|-----------|-------------|
| enum | `enum class PhaseMode { FixedMask, Distributed }` |  |
| enum | `enum class PixelLayout { RGB, RGBW }` |  |
| enum | `enum class WhitePolicy { Disabled, NearNeutralOnly, AlwaysAllowed, WhitePriority, MeasuredOptimal }` |  |
| using | `using CalibrationFn = uint16_t (*)(uint16_t q16, uint8_t channel)` |  |
| using | `using SolverFn = EncodedState (*)(uint16_t q16, uint8_t channel, const PolicyConfig& cfg)` |  |
| constant | `static constexpr uint16_t INV_CYCLE_Q8` |  |
| constant | `static constexpr uint8_t MAX_SUPPORTED_CYCLE_LENGTH` |  |
| constant | `static constexpr uint16_t PACKED_BFI_BYTES_PER_PIXEL` |  |
| constant | `static constexpr uint8_t PHASE_EMIT_MASK` |  |
| constant | `static constexpr uint8_t SOLVER_FIXED_BFI_LEVELS` |  |
| struct | `struct CalibrationMixingConfig` |  |
| struct | `struct CalibrationProfile` |  |
| struct | `struct EncodedState` |  |
| struct | `struct LadderEntry` |  |
| struct | `struct PolicyConfig` |  |
| struct | `struct RgbwTargets` |  |
| class | `class SolverRuntime` |  |
| inline function | `uint16_t applyScaleQ8(uint16_t q16, uint16_t scaleQ8)` |  |
| inline function | `bool channelOnPhase(uint8_t bfi, uint8_t phase)` |  |
| inline function | `bool channelOnTickDistributed(uint8_t bfi, uint32_t tick, uint8_t cycleLength)` |  |
| inline function | `uint8_t clampBfi(uint8_t bfi)` |  |
| inline function | `uint16_t invCycleQ8ForBfi(uint8_t bfi, uint8_t cycleLength)` |  |
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

### `RgbwTargets`

| Kind | Signature | Description |
|------|-----------|-------------|
| field | `uint16_t bQ16` |  |
| field | `uint16_t gQ16` |  |
| field | `uint16_t rQ16` |  |
| field | `uint16_t wQ16` |  |

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
| method | `bool advanceTick()` |  |
| method | `uint16_t applyCalibration(uint16_t q16, uint8_t channel) const` |  |
| method | `RgbwTargets applyCubeLUT3D(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const` |  |
| method | `uint16_t applyTransferCurve(uint16_t q16, uint8_t channel) const` |  |
| method | `RgbwTargets applyWhiteLimit(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16, uint16_t wQ16) const` |  |
| method | `void attachLUTs(uint8_t* valueLUT, uint8_t* bfiLUT, uint8_t* floorLUT, uint16_t* outputQ16LUT, uint16_t lutSize)` |  |
| method | `bool calibrationEnabled() const` |  |
| method | `bool channelActiveOnCurrentTick(uint8_t bfi) const` |  |
| method | `PolicyConfig& config()` |  |
| method | `PolicyConfig& config() const` |  |
| method | `bool cubeLUT3DEnabled() const` |  |
| method | `uint32_t currentTick() const` |  |
| method | `uint8_t cycleLength() const` |  |
| method | `void dumpLUTHeader(Print& out) const` |  |
| method | `RgbwTargets extractRgbw(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const` |  |
| method | `void loadPrecomputed(const uint8_t* srcValue, const uint8_t* srcBfi, const uint8_t* srcFloor, const uint16_t* srcOutputQ16)` |  |
| method | `uint16_t lutSize() const` |  |
| method | `PhaseMode phaseMode() const` |  |
| method | `void precompute(SolverFn fn)` |  |
| method | `void renderBFI_RGB(const uint8_t* upperFrame, const uint8_t* floorFrame, const uint8_t* bfiMapG, const uint8_t* bfiMapR, const uint8_t* bfiMapB, uint8_t* displayBuffer, uint16_t pixelCount) const` |  |
| method | `void renderBFI_RGBW(const uint8_t* upperFrame, const uint8_t* floorFrame, const uint8_t* bfiMapG, const uint8_t* bfiMapR, const uint8_t* bfiMapB, const uint8_t* bfiMapW, uint8_t* displayBuffer, uint16_t pixelCount) const` |  |
| method | `void renderBFI_RGBW_Packed(const uint8_t* upperFrame, const uint8_t* floorFrame, const uint8_t* packedBfiMap, uint8_t* displayBuffer, uint16_t pixelCount) const` |  |
| method | `void renderBFI_RGB_Packed(const uint8_t* upperFrame, const uint8_t* floorFrame, const uint8_t* packedBfiMap, uint8_t* displayBuffer, uint16_t pixelCount) const` |  |
| method | `void resetTick()` |  |
| method | `void setCalibrationEnabled(bool enabled)` |  |
| method | `void setCalibrationFunction(CalibrationFn fn)` |  |
| method | `void setCubeLUT3D(const CubeLUT3D* cube)` |  |
| method | `void setCubeLUT3DEnabled(bool enabled)` |  |
| method | `void setCycleLength(uint8_t len)` |  |
| method | `void setPhaseMode(PhaseMode mode)` |  |
| method | `void setTransferCurve(const uint16_t* curveR, const uint16_t* curveG, const uint16_t* curveB, const uint16_t* curveW, uint16_t bucketCount)` |  |
| method | `void setTransferCurveEnabled(bool enabled)` |  |
| method | `void setWhiteLimit(uint8_t limit)` |  |
| method | `EncodedState solve(uint16_t q16, uint8_t channel) const` |  |
| method | `size_t solverLutIndex(uint16_t q16) const` |  |
| method | `bool transferCurveEnabled() const` |  |
| method | `uint8_t whiteLimit() const` |  |
| static method | `static void commitPixelRGB(uint8_t* upperFrame, uint8_t* floorFrame, uint8_t* bfiMapG, uint8_t* bfiMapR, uint8_t* bfiMapB, uint16_t pixelIndex, const EncodedState& g, const EncodedState& r, const EncodedState& b)` |  |
| static method | `static void commitPixelRGBW(uint8_t* upperFrame, uint8_t* floorFrame, uint8_t* bfiMapG, uint8_t* bfiMapR, uint8_t* bfiMapB, uint8_t* bfiMapW, uint16_t pixelIndex, const EncodedState& g, const EncodedState& r, const EncodedState& b, const EncodedState& w)` |  |
| static method | `static void commitPixelRGBW_Packed(uint8_t* upperFrame, uint8_t* floorFrame, uint8_t* packedBfiMap, uint16_t pixelIndex, const EncodedState& g, const EncodedState& r, const EncodedState& b, const EncodedState& w)` |  |
| static method | `static void commitPixelRGB_Packed(uint8_t* upperFrame, uint8_t* floorFrame, uint8_t* packedBfiMap, uint16_t pixelIndex, const EncodedState& g, const EncodedState& r, const EncodedState& b)` |  |
| static method | `static void renderSubpixelBFI_RGB(const uint8_t* upperFrame, const uint8_t* floorFrame, const uint8_t* bfiMapG, const uint8_t* bfiMapR, const uint8_t* bfiMapB, uint8_t* displayBuffer, uint16_t pixelCount, uint8_t phase)` |  |
| static method | `static void renderSubpixelBFI_RGBW(const uint8_t* upperFrame, const uint8_t* floorFrame, const uint8_t* bfiMapG, const uint8_t* bfiMapR, const uint8_t* bfiMapB, const uint8_t* bfiMapW, uint8_t* displayBuffer, uint16_t pixelCount, uint8_t phase)` |  |
| static method | `static void renderSubpixelBFI_RGBW_Packed(const uint8_t* upperFrame, const uint8_t* floorFrame, const uint8_t* packedBfiMap, uint8_t* displayBuffer, uint16_t pixelCount, uint8_t phase)` |  |
| static method | `static void renderSubpixelBFI_RGB_Packed(const uint8_t* upperFrame, const uint8_t* floorFrame, const uint8_t* packedBfiMap, uint8_t* displayBuffer, uint16_t pixelCount, uint8_t phase)` |  |

---

## TemporalBFIRuntime.h

### File-level

| Kind | Signature | Description |
|------|-----------|-------------|
| constant | `static constexpr uint8_t PHASE_EMIT_MASK` |  |
| constant | `static constexpr uint8_t SOLVER_FIXED_BFI_LEVELS` |  |
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

