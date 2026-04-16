#pragma once
#include <Arduino.h>

// Platform compatibility — DMAMEM is Teensy-specific.
#ifndef DMAMEM
#define DMAMEM
#endif

namespace TemporalBFI {

// ============================================================================
// Types
// ============================================================================

struct LadderEntry { uint16_t outputQ16; uint8_t value; uint8_t bfi; };

enum class WhitePolicy : uint8_t {
    Disabled = 0,
    NearNeutralOnly = 1,
    AlwaysAllowed = 2,
    WhitePriority = 3,
    MeasuredOptimal = 4
};

struct CalibrationMixingConfig {
    WhitePolicy whitePolicy;
    uint16_t neutralThresholdQ16;
    uint16_t whiteWeightQ16;
    uint16_t rgbWeightQ16;
};

struct CalibrationProfile {
    const uint16_t* lutR16;
    const uint16_t* lutG16;
    const uint16_t* lutB16;
    const uint16_t* lutW16;
    const uint16_t* lutR8To16;
    const uint16_t* lutG8To16;
    const uint16_t* lutB8To16;
    const uint16_t* lutW8To16;
    CalibrationMixingConfig mixing;
};

enum class PixelLayout : uint8_t { RGB = 3, RGBW = 4 };

struct RgbwTargets {
    uint16_t rQ16;
    uint16_t gQ16;
    uint16_t bQ16;
    uint16_t wQ16;
};

// Solver output state for a single channel.
// Canonical definition — per_bfi_v3.h aliases this via using.
struct EncodedState {
    uint8_t value;
    uint8_t bfi;
    uint8_t lowerValue;
    uint16_t outputQ16;
    uint16_t ladderIndex;
};

// Solver policy tuning knobs.
// Canonical definition — per_bfi_v3.h aliases this via using.
struct PolicyConfig {
    uint16_t minErrorQ16 = 64;
    uint16_t relativeErrorDivisor = 24;
    uint8_t minValueRatioNumerator = 3;
    uint8_t minValueRatioDenominator = 8;
    uint8_t lowEndProtectThreshold = 48;
    uint8_t lowEndMaxDrop = 10;
    uint8_t maxBFI = 4;
    bool preferHigherBFI = true;
    uint8_t preferredMinBFI = 0;
    uint8_t highlightBypassStart = 240;
    bool enableInputQ16Calibration = false;
};

// ============================================================================
// Callback signatures
// ============================================================================

// Solver: maps a Q16 value + channel + policy config → EncodedState.
// Provided by the sketch from per_bfi_v3.h::encodeStateFrom16.
using SolverFn = EncodedState (*)(uint16_t q16, uint8_t channel, const PolicyConfig& cfg);

// Calibration: maps a Q16 value + channel → calibrated Q16.
// Provided by the sketch from per_bfi_v3.h::calibrateInputQ16ForSolver.
using CalibrationFn = uint16_t (*)(uint16_t q16, uint8_t channel);

// ============================================================================
// Constants
// ============================================================================

static constexpr uint8_t SOLVER_FIXED_BFI_LEVELS = 5;

static constexpr uint8_t PHASE_EMIT_MASK[SOLVER_FIXED_BFI_LEVELS] = {
    0x1F, 0x1B, 0x15, 0x09, 0x01
};

static constexpr uint16_t INV_CYCLE_Q8[SOLVER_FIXED_BFI_LEVELS] = {
    256, 205, 154, 102, 51
};

// ============================================================================
// Q16 Math Helpers (inline — trivial one-liners)
// ============================================================================

inline uint16_t scale8ToQ16(uint8_t value)
{
    return (uint16_t)(((uint16_t)value << 8) | value);
}

inline uint8_t scaleQ16To8(uint16_t q16)
{
    return (uint8_t)(((uint32_t)q16 * 255u + 32767u) / 65535u);
}

inline uint16_t scale12ToQ16(uint16_t value12)
{
    if (value12 >= 4095u) return 65535u;
    return (uint16_t)(((uint32_t)value12 * 65535u + 2047u) / 4095u);
}

inline uint16_t scale4ToQ16(uint8_t value4)
{
    if (value4 >= 15u) return 65535u;
    return (uint16_t)(((uint32_t)value4 * 65535u + 7u) / 15u);
}

inline uint16_t applyScaleQ8(uint16_t q16, uint16_t scaleQ8)
{
    if (scaleQ8 >= 256u) return q16;
    return (uint16_t)(((uint32_t)q16 * scaleQ8 + 127u) >> 8);
}

inline uint16_t mulQ16(uint16_t a, uint16_t b)
{
    return (uint16_t)(((uint32_t)a * b + 32767u) / 65535u);
}

inline uint16_t min3U16(uint16_t a, uint16_t b, uint16_t c)
{
    const uint16_t ab = (a < b) ? a : b;
    return (ab < c) ? ab : c;
}

inline size_t lutIndexForSize(uint16_t q16, uint16_t lutSize)
{
    if (lutSize <= 1u) return 0;
    return (size_t)(((uint32_t)q16 * (uint32_t)(lutSize - 1u) + 32767u) / 65535u);
}

inline uint8_t clampBfi(uint8_t bfi)
{
    return (bfi < SOLVER_FIXED_BFI_LEVELS) ? bfi : (uint8_t)(SOLVER_FIXED_BFI_LEVELS - 1u);
}

// ============================================================================
// Phase Helpers
// ============================================================================

inline bool channelOnPhase(uint8_t bfi, uint8_t phase)
{
    return (PHASE_EMIT_MASK[clampBfi(bfi)] & (1u << (phase & 0x07u))) != 0u;
}

// ============================================================================
// Packed BFI Map Helpers
//
// Nybble-pair encoding: 2 bytes per pixel.
//   byte 0: (G << 4) | R       — "GR"
//   byte 1: (B << 4) | W       — "BW"   (W = 0 for RGB-only)
//
// Each channel occupies 4 bits (values 0..15), supporting up to 16 BFI
// levels.  With the current SOLVER_FIXED_BFI_LEVELS = 5 the valid range
// is 0..4, leaving headroom for future expansion.
//
// Memory: 2 bytes/pixel vs 4 bytes/pixel (RGBW) or 3 bytes/pixel (RGB).
// ============================================================================

static constexpr uint16_t PACKED_BFI_BYTES_PER_PIXEL = 2u;

inline void packBfi4(uint8_t* packed, uint16_t pixelIndex,
                     uint8_t g, uint8_t r, uint8_t b, uint8_t w)
{
    const uint32_t off = (uint32_t)pixelIndex * PACKED_BFI_BYTES_PER_PIXEL;
    packed[off + 0] = (uint8_t)((g << 4) | (r & 0x0Fu));
    packed[off + 1] = (uint8_t)((b << 4) | (w & 0x0Fu));
}

inline void packBfi3(uint8_t* packed, uint16_t pixelIndex,
                     uint8_t g, uint8_t r, uint8_t b)
{
    packBfi4(packed, pixelIndex, g, r, b, 0);
}

inline void unpackBfi4(const uint8_t* packed, uint16_t pixelIndex,
                       uint8_t& g, uint8_t& r, uint8_t& b, uint8_t& w)
{
    const uint32_t off = (uint32_t)pixelIndex * PACKED_BFI_BYTES_PER_PIXEL;
    const uint8_t gr = packed[off + 0];
    const uint8_t bw = packed[off + 1];
    g = (uint8_t)(gr >> 4);
    r = (uint8_t)(gr & 0x0Fu);
    b = (uint8_t)(bw >> 4);
    w = (uint8_t)(bw & 0x0Fu);
}

inline void unpackBfi3(const uint8_t* packed, uint16_t pixelIndex,
                       uint8_t& g, uint8_t& r, uint8_t& b)
{
    uint8_t w;
    unpackBfi4(packed, pixelIndex, g, r, b, w);
    (void)w;
}

inline uint8_t readPackedBfiChannel(const uint8_t* packed,
                                    uint16_t pixelIndex, uint8_t channelGRBW)
{
    const uint32_t off = (uint32_t)pixelIndex * PACKED_BFI_BYTES_PER_PIXEL;
    switch (channelGRBW) {
        case 0: return (uint8_t)(packed[off + 0] >> 4);        // G
        case 1: return (uint8_t)(packed[off + 0] & 0x0Fu);     // R
        case 2: return (uint8_t)(packed[off + 1] >> 4);        // B
        default: return (uint8_t)(packed[off + 1] & 0x0Fu);    // W
    }
}

inline void writePackedBfiChannel(uint8_t* packed,
                                  uint16_t pixelIndex, uint8_t channelGRBW,
                                  uint8_t value)
{
    const uint32_t off = (uint32_t)pixelIndex * PACKED_BFI_BYTES_PER_PIXEL;
    switch (channelGRBW) {
        case 0: packed[off + 0] = (uint8_t)((value << 4) | (packed[off + 0] & 0x0Fu)); break;
        case 1: packed[off + 0] = (uint8_t)((packed[off + 0] & 0xF0u) | (value & 0x0Fu)); break;
        case 2: packed[off + 1] = (uint8_t)((value << 4) | (packed[off + 1] & 0x0Fu)); break;
        default: packed[off + 1] = (uint8_t)((packed[off + 1] & 0xF0u) | (value & 0x0Fu)); break;
    }
}

// ============================================================================
// Derive solver LUT size from ladder data at compile time.
// ============================================================================

static constexpr uint16_t maxU16(uint16_t a, uint16_t b) { return (a > b) ? a : b; }

// Forward declaration for 3D cube LUT support (defined in CubeLUT3D.h).
struct CubeLUT3D;

// ============================================================================
// SolverRuntime — the primary library interface
// ============================================================================

class SolverRuntime {
public:
    SolverRuntime() = default;
    virtual ~SolverRuntime() = default;

    // ----- LUT Management -----

    void attachLUTs(uint8_t* valueLUT, uint8_t* bfiLUT,
                    uint8_t* floorLUT, uint16_t* outputQ16LUT,
                    uint16_t lutSize);

    // Precompute all LUTs by calling the supplied solver function for each
    // (q16, channel) pair.  The solver function comes from per_bfi_v3.h
    // and depends on user-supplied ladder data, so it can't be in the .cpp.
    void precompute(SolverFn fn);

    void loadPrecomputed(const uint8_t* srcValue, const uint8_t* srcBfi,
                         const uint8_t* srcFloor, const uint16_t* srcOutputQ16);

    // ----- Configuration -----

    PolicyConfig& config() { return m_cfg; }
    const PolicyConfig& config() const { return m_cfg; }

    uint16_t lutSize() const { return m_lutSize; }

    // ----- Solver (runtime hot path) -----

    EncodedState solve(uint16_t q16, uint8_t channel) const;
    size_t solverLutIndex(uint16_t q16) const;

    // ----- Transfer Curve -----

    void setTransferCurve(const uint16_t* curveR, const uint16_t* curveG,
                          const uint16_t* curveB, const uint16_t* curveW,
                          uint16_t bucketCount);

    void setTransferCurveEnabled(bool enabled);
    bool transferCurveEnabled() const { return m_transferCurveEnabled; }

    uint16_t applyTransferCurve(uint16_t q16, uint8_t channel) const;

    // ----- Input Calibration -----

    // Register a calibration function (from per_bfi_v3.h).
    void setCalibrationFunction(CalibrationFn fn);

    void setCalibrationEnabled(bool enabled);
    bool calibrationEnabled() const { return m_calibrationEnabled; }

    uint16_t applyCalibration(uint16_t q16, uint8_t channel) const;

    // ----- RGBW Extraction -----

    void setWhiteLimit(uint8_t limit);
    uint8_t whiteLimit() const { return m_whiteLimit; }

    virtual RgbwTargets extractRgbw(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const;

    RgbwTargets applyWhiteLimit(uint16_t rQ16, uint16_t gQ16,
                                uint16_t bQ16, uint16_t wQ16) const;

    // ----- 3D Cube LUT -----
    // Applies a pre-calibrated RGB→RGBW (or RGB→RGB) 3D lookup table.
    // In the pipeline this replaces calibration + white extraction:
    //   Input → Transfer Curve → **Cube LUT** → Solver
    // Values returned by the cube are calibrated targets — do not modify
    // them before passing to the solver.

    void setCubeLUT3D(const CubeLUT3D* cube);
    void setCubeLUT3DEnabled(bool enabled);
    bool cubeLUT3DEnabled() const { return m_cubeLUTEnabled; }

    /// Look up (rQ16, gQ16, bQ16) through the attached 3D cube.
    /// Returns RGBW targets when a valid RGBW cube is loaded, or RGB
    /// targets (wQ16 = 0) for an RGB cube.  If the cube is disabled or
    /// missing, returns a passthrough (rQ16, gQ16, bQ16, 0).
    RgbwTargets applyCubeLUT3D(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const;

    // ----- Pixel Commit -----

    static void commitPixelRGBW(
        uint8_t* upperFrame, uint8_t* floorFrame,
        uint8_t* bfiMapG, uint8_t* bfiMapR,
        uint8_t* bfiMapB, uint8_t* bfiMapW,
        uint16_t pixelIndex,
        const EncodedState& g, const EncodedState& r,
        const EncodedState& b, const EncodedState& w);

    static void commitPixelRGB(
        uint8_t* upperFrame, uint8_t* floorFrame,
        uint8_t* bfiMapG, uint8_t* bfiMapR,
        uint8_t* bfiMapB,
        uint16_t pixelIndex,
        const EncodedState& g, const EncodedState& r,
        const EncodedState& b);

    // ----- BFI Rendering -----

    static void renderSubpixelBFI_RGBW(
        const uint8_t* upperFrame, const uint8_t* floorFrame,
        const uint8_t* bfiMapG, const uint8_t* bfiMapR,
        const uint8_t* bfiMapB, const uint8_t* bfiMapW,
        uint8_t* displayBuffer, uint16_t pixelCount,
        uint8_t phase);

    static void renderSubpixelBFI_RGB(
        const uint8_t* upperFrame, const uint8_t* floorFrame,
        const uint8_t* bfiMapG, const uint8_t* bfiMapR,
        const uint8_t* bfiMapB,
        uint8_t* displayBuffer, uint16_t pixelCount,
        uint8_t phase);

    // ----- Packed BFI Pixel Commit -----
    // These variants write BFI levels into a packed nybble-pair buffer
    // (2 bytes/pixel) instead of separate per-channel arrays.

    static void commitPixelRGBW_Packed(
        uint8_t* upperFrame, uint8_t* floorFrame,
        uint8_t* packedBfiMap,
        uint16_t pixelIndex,
        const EncodedState& g, const EncodedState& r,
        const EncodedState& b, const EncodedState& w);

    static void commitPixelRGB_Packed(
        uint8_t* upperFrame, uint8_t* floorFrame,
        uint8_t* packedBfiMap,
        uint16_t pixelIndex,
        const EncodedState& g, const EncodedState& r,
        const EncodedState& b);

    // ----- Packed BFI Rendering -----

    static void renderSubpixelBFI_RGBW_Packed(
        const uint8_t* upperFrame, const uint8_t* floorFrame,
        const uint8_t* packedBfiMap,
        uint8_t* displayBuffer, uint16_t pixelCount,
        uint8_t phase);

    static void renderSubpixelBFI_RGB_Packed(
        const uint8_t* upperFrame, const uint8_t* floorFrame,
        const uint8_t* packedBfiMap,
        uint8_t* displayBuffer, uint16_t pixelCount,
        uint8_t phase);

    // ----- LUT Header Dump -----

    void dumpLUTHeader(Print& out) const;

private:
    // LUT storage (caller-owned)
    uint8_t* m_valueLUT = nullptr;
    uint8_t* m_bfiLUT = nullptr;
    uint8_t* m_floorLUT = nullptr;
    uint16_t* m_outputQ16LUT = nullptr;
    uint16_t m_lutSize = 0;

    // Transfer curve (caller-owned data pointers)
    const uint16_t* m_curveR = nullptr;
    const uint16_t* m_curveG = nullptr;
    const uint16_t* m_curveB = nullptr;
    const uint16_t* m_curveW = nullptr;
    uint16_t m_curveBucketCount = 0;
    bool m_transferCurveEnabled = false;

    // Input calibration
    CalibrationFn m_calibrationFn = nullptr;
    bool m_calibrationEnabled = false;

    // White limit
    uint8_t m_whiteLimit = 255;

    // 3D Cube LUT (non-owning pointer — caller owns the CubeLUT3D)
    const CubeLUT3D* m_cubeLUT = nullptr;
    bool m_cubeLUTEnabled = false;

    // Solver config (owned directly — no external type dependency)
    PolicyConfig m_cfg;
};

} // namespace TemporalBFI
