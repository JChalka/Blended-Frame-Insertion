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

/// Measured ladder sample used by the policy solver for one output state.
struct LadderEntry { uint16_t outputQ16; uint8_t value; uint8_t bfi; };

/// Strategy for deciding when extracted white output is allowed.
enum class WhitePolicy : uint8_t {
    Disabled = 0,
    NearNeutralOnly = 1,
    AlwaysAllowed = 2,
    WhitePriority = 3,
    MeasuredOptimal = 4
};

/// Weighting and threshold knobs used by measured RGBW calibration profiles.
struct CalibrationMixingConfig {
    WhitePolicy whitePolicy;
    uint16_t neutralThresholdQ16;
    uint16_t whiteWeightQ16;
    uint16_t rgbWeightQ16;
};

/// Non-owning calibration LUT bundle; caller owns all referenced tables.
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

/// Logical pixel layout used to derive channel count for LUT and render paths.
enum class PixelLayout : uint8_t { RGB = 3, RGBW = 4, RGBWW = 5, RGBCCT = 5 };

/// Controls whether logical W2 uses the W ladder or a native fifth-channel ladder.
enum class FifthChannelSolveMode : uint8_t {
    EmulateFromW = 0,
    Native = 1
};

/// Selects shared single-curve transfer lookup or opt-in per-channel curves.
enum class TransferCurveMode : uint8_t {
    Single = 0,
    LegacyPerChannel = 1
};

/// Selects per-channel solver LUT storage or one shared LUT set.
enum class SolverLUTMode : uint8_t {
    PerChannel = 0,
    Shared = 1
};

/// Physical byte-order presets for mapping logical solver channels to LED buffers.
enum class LedColorOrder : uint8_t {
    // 3-channel
    GRB = 0,
    RGB,
    BRG,
    BGR,
    RBG,
    GBR,

    // 4-channel
    GRBW,
    GRWB,
    GBRW,
    GBWR,
    GWRB,
    GWBR,
    RGBW,
    RGWB,
    RBGW,
    RBWG,
    RWGB,
    RWBG,
    BGRW,
    BGWR,
    BRGW,
    BRWG,
    BWGR,
    BWRG,
    WRGB,
    WRBG,
    WGRB,
    WGBR,
    WBRG,
    WBGR,

    // 5-channel (W1/W2 common presets)
    GRBW1W2,
    GRBW2W1,
    RGBW1W2,
    RGBW2W1,
    W1W2RGB,
    W2W1RGB,
    W1RGBW2,
    W2RGBW1,
    W1GRBW2,
    W2GRBW1
};

/// Storage layout for BFI maps passed to consolidated render/commit APIs.
enum class BfiMapStorageMode : uint8_t {
    Separate = 0,
    Packed = 1
};

/// Render/commit options for logical channel layout, physical byte order, and BFI map storage.
struct RenderOptions {
    LedColorOrder colorOrder = LedColorOrder::GRBW;
    BfiMapStorageMode bfiMapStorage = BfiMapStorageMode::Separate;
};

/// Read-only BFI map view for render APIs; provide separate maps or a packed map.
struct BfiMapView {
    // Separate per-channel maps in logical channel order:
    // 0=G, 1=R, 2=B, 3=W1, 4=W2.
    const uint8_t* bfiMapG = nullptr;
    const uint8_t* bfiMapR = nullptr;
    const uint8_t* bfiMapB = nullptr;
    const uint8_t* bfiMapW1 = nullptr;
    const uint8_t* bfiMapW2 = nullptr;

    // Packed nibble map. For consolidated APIs this is interpreted as
    // ceil(channelCount/2) bytes per pixel, two 4-bit BFI values per byte.
    const uint8_t* packedBfiMap = nullptr;
};

/// Mutable BFI map view for commit APIs; provide separate maps or a packed map.
struct BfiMapWriteView {
    // Separate per-channel maps in logical channel order:
    // 0=G, 1=R, 2=B, 3=W1, 4=W2.
    uint8_t* bfiMapG = nullptr;
    uint8_t* bfiMapR = nullptr;
    uint8_t* bfiMapB = nullptr;
    uint8_t* bfiMapW1 = nullptr;
    uint8_t* bfiMapW2 = nullptr;

    // Packed nibble map. For consolidated APIs this is interpreted as
    // ceil(channelCount/2) bytes per pixel, two 4-bit BFI values per byte.
    uint8_t* packedBfiMap = nullptr;
};

/// Phase distribution mode for BFI rendering.
enum class PhaseMode : uint8_t {
    FixedMask        = 0,   // Legacy 5-phase bitmask (PHASE_EMIT_MASK)
    Distributed      = 1,   // Per-BFI cycle: 1 upper + bfi lowers (cycle = bfi+1)
    DistributedGlobal = 2   // Bresenham-distributed even spacing across a fixed global cycle
};

/// Four-channel RGBW target values in Q16.
struct RgbwTargets {
    uint16_t rQ16;
    uint16_t gQ16;
    uint16_t bQ16;
    uint16_t wQ16;
};

/// Five-channel RGBWW/RGBCCT-style target values in Q16.
struct RgbwwTargets {
    uint16_t rQ16;
    uint16_t gQ16;
    uint16_t bQ16;
    uint16_t w1Q16;
    uint16_t w2Q16;
};

/// Solver output state for a single channel; per_bfi_v3.h aliases this canonical type.
struct EncodedState {
    uint8_t value;
    uint8_t bfi;
    uint8_t lowerValue;
    uint16_t outputQ16;
    uint16_t ladderIndex;
};

/// Solver policy tuning knobs; per_bfi_v3.h aliases this canonical type.
struct PolicyConfig {
    uint16_t minErrorQ16 = 64;
    uint16_t relativeErrorDivisor = 24;
    uint8_t minValueRatioNumerator = 0;
    uint8_t minValueRatioDenominator = 1;
    uint8_t lowEndProtectThreshold = 0;
    uint8_t lowEndMaxDrop = 0;
    uint8_t maxBFI = 4;
    bool preferHigherBFI = false;
    uint8_t preferredMinBFI = 0;
    uint8_t highlightBypassStart = 255;
    bool enableInputQ16Calibration = false;
};

// ============================================================================
// Callback signatures
// ============================================================================

/// Solver callback that maps a Q16 value and logical channel to an EncodedState.
using SolverFn = EncodedState (*)(uint16_t q16, uint8_t channel, const PolicyConfig& cfg);

/// Calibration callback that maps an input Q16 value and logical channel to calibrated Q16.
using CalibrationFn = uint16_t (*)(uint16_t q16, uint8_t channel);

// ============================================================================
// Constants
// ============================================================================

static constexpr uint8_t SOLVER_FIXED_BFI_LEVELS = 5;
static constexpr uint8_t SOLVER_DEFAULT_CHANNELS = 4;
static constexpr uint8_t SOLVER_MAX_CHANNELS = 5;

static constexpr uint8_t PHASE_EMIT_MASK[SOLVER_FIXED_BFI_LEVELS] = {
    0x1F, 0x1B, 0x15, 0x09, 0x01
};

static constexpr uint16_t INV_CYCLE_Q8[SOLVER_FIXED_BFI_LEVELS] = {
    256, 205, 154, 102, 51
};

// Maximum cycle length supported by the precomputed phase table
// used in the instance render methods.
static constexpr uint8_t MAX_SUPPORTED_CYCLE_LENGTH = 16;

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

// Bresenham-distributed phase determination (global fixed cycle).
// For a given BFI level and cycle length, distributes upper and lower
// frames as evenly as possible across the cycle — no consecutive
// clustering of upper frames.
// Stateless — depends only on (bfi, tick, cycleLength).
inline bool channelOnTickDistributedGlobal(uint8_t bfi, uint32_t tick, uint8_t cycleLength)
{
    if (bfi == 0) return true;
    if (cycleLength == 0 || bfi >= cycleLength) return false;
    const uint8_t t = (uint8_t)(tick % cycleLength);
    // Lower at phase t when: floor((t+1)*bfi/C) > floor(t*bfi/C).
    return !(((uint16_t)(t + 1) * bfi / cycleLength) >
             ((uint16_t)t * bfi / cycleLength));
}

// Per-BFI distributed phase determination.
// Each BFI level has its own natural cycle length of (bfi + 1):
//   BFI 0 → U          (always upper)
//   BFI 1 → U L        (cycle 2)
//   BFI 2 → U L L      (cycle 3)
//   BFI 3 → U L L L    (cycle 4)
// Phase 0 of each cycle is always the upper frame.
// Stateless — depends only on (bfi, tick).
inline bool channelOnTickPerBfi(uint8_t bfi, uint32_t tick)
{
    if (bfi == 0) return true;
    const uint8_t cycleLen = bfi + 1;
    return (tick % cycleLen) == 0;
}

// Dynamic duty-cycle scaling for the DistributedGlobal mode.
// Generalises the fixed INV_CYCLE_Q8[] table.
// Result is Q8: upper-frame duty ratio × 256.
inline uint16_t invCycleQ8ForBfi(uint8_t bfi, uint8_t cycleLength)
{
    if (cycleLength == 0 || bfi >= cycleLength) return 0;
    return (uint16_t)(((uint16_t)(cycleLength - bfi) * 256u
                       + cycleLength / 2u) / cycleLength);
}

// Duty-cycle scaling for the per-BFI distributed mode.
// Cycle = bfi + 1, upper count = 1.  Result is Q8.
inline uint16_t invCycleQ8ForBfiPerBfi(uint8_t bfi)
{
    const uint8_t cl = bfi + 1u;
    return (uint16_t)((256u + cl / 2u) / cl);
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

    /// Attach caller-owned solver LUT buffers and set the LUT size used by solve/precompute/load.
    void attachLUTs(uint8_t* valueLUT, uint8_t* bfiLUT,
                    uint8_t* floorLUT, uint16_t* outputQ16LUT,
                    uint16_t lutSize);

    /// Precompute solver LUTs; Shared mode computes one storage channel reused by all logical channels.
    void precompute(SolverFn fn, uint8_t numChannels = SOLVER_DEFAULT_CHANNELS);

    /// Precompute solver LUTs using a PixelLayout-derived channel count.
    void precompute(SolverFn fn, PixelLayout layout)
    {
        precompute(fn, channelsForLayout(layout));
    }

    /// Load precomputed solver LUT tables; srcLutSize guards against stride mismatches when nonzero.
    void loadPrecomputed(const uint8_t* srcValue, const uint8_t* srcBfi,
                         const uint8_t* srcFloor, const uint16_t* srcOutputQ16,
                         uint8_t numChannels = SOLVER_DEFAULT_CHANNELS, uint16_t srcLutSize = 0);

    /// Load precomputed LUTs using a PixelLayout-derived channel count.
    void loadPrecomputed(const uint8_t* srcValue, const uint8_t* srcBfi,
                         const uint8_t* srcFloor, const uint16_t* srcOutputQ16,
                         PixelLayout layout, uint16_t srcLutSize = 0)
    {
        loadPrecomputed(srcValue, srcBfi, srcFloor, srcOutputQ16,
                        channelsForLayout(layout), srcLutSize);
    }

    // ----- Configuration -----

    /// Mutable access to solver policy knobs used by precompute and runtime solve helpers.
    PolicyConfig& config() { return m_cfg; }
    /// Read-only access to solver policy knobs.
    const PolicyConfig& config() const { return m_cfg; }

    /// Return the active solver LUT size, or 0 if LUT storage is not attached.
    uint16_t lutSize() const { return m_lutSize; }

    /// Select solver LUT storage mode: PerChannel for calibrated output, Shared for low-memory/bringup.
    void setSolverLUTMode(SolverLUTMode mode);
    /// Return the active solver LUT storage mode.
    SolverLUTMode solverLUTMode() const { return m_solverLUTMode; }
    /// Return true when solve lookups use one shared LUT storage channel.
    bool solverLUTSharedModeEnabled() const { return m_solverLUTMode == SolverLUTMode::Shared; }

    // ----- Solver (runtime hot path) -----

    /// Look up a Q16 target for one logical channel and return the encoded temporal state.
    EncodedState solve(uint16_t q16, uint8_t channel) const;
    /// Convert a Q16 value to the nearest active LUT index.
    size_t solverLutIndex(uint16_t q16) const;

    // ----- Transfer Curve -----

    /// Attach one shared transfer curve LUT for all logical channels.
    void setTransferCurve(const uint16_t* curve, uint16_t bucketCount);

    /// Attach per-channel RGBW transfer curves and select LegacyPerChannel mode.
    void setTransferCurve(const uint16_t* curveR, const uint16_t* curveG,
                          const uint16_t* curveB, const uint16_t* curveW,
                          uint16_t bucketCount);

    /// Enable or disable transfer-curve application in the input pipeline.
    void setTransferCurveEnabled(bool enabled);
    /// Return whether transfer-curve application is enabled.
    bool transferCurveEnabled() const { return m_transferCurveEnabled; }

    /// Apply the active transfer curve to a Q16 value for the requested logical channel.
    uint16_t applyTransferCurve(uint16_t q16, uint8_t channel) const;

    /// Attach per-channel RGBWW/RGBCCT transfer curves and select LegacyPerChannel mode.
    void setTransferCurve(const uint16_t* curveR, const uint16_t* curveG,
                          const uint16_t* curveB, const uint16_t* curveW,
                          uint16_t bucketCount, const uint16_t* curveW2);

    /// Select shared or per-channel transfer-curve lookup mode.
    void setTransferCurveMode(TransferCurveMode mode);
    /// Return the active transfer-curve lookup mode.
    TransferCurveMode transferCurveMode() const { return m_transferCurveMode; }

    /// Select whether logical W2 solves through W emulation or a native fifth-channel ladder.
    void setFifthChannelSolveMode(FifthChannelSolveMode mode);
    /// Return the active fifth-channel solve mode.
    FifthChannelSolveMode fifthChannelSolveMode() const { return m_fifthChannelSolveMode; }

    /// Configure physical byte-order mapping for rendered buffers; solver/commit order remains logical GRB(W/W1W2).
    void setLedColorOrder(LedColorOrder order);
    /// Return the active physical byte-order mapping.
    LedColorOrder ledColorOrder() const { return m_ledColorOrder; }

    /// Derive channel count from a color-order contract: RGB=3, RGBW=4, RGBWW/RGBCCT=5.
    static uint8_t channelCountForColorOrder(LedColorOrder order);
    /// Return the current render channel count derived from ledColorOrder().
    uint8_t activeRenderChannelCount() const;

    /// Set a custom 3-channel logical-to-physical map; entries must be a permutation of [0..2].
    bool setCustomColorOrderMap3(const uint8_t map[3]);
    /// Set a custom 4-channel logical-to-physical map; entries must be a permutation of [0..3].
    bool setCustomColorOrderMap4(const uint8_t map[4]);
    /// Set a custom 5-channel logical-to-physical map; entries must be a permutation of [0..4].
    bool setCustomColorOrderMap5(const uint8_t map[5]);

    // ----- Input Calibration -----

    /// Register a per-channel input calibration callback used before solving.
    void setCalibrationFunction(CalibrationFn fn);

    /// Enable or disable input calibration callback application.
    void setCalibrationEnabled(bool enabled);
    /// Return whether input calibration is enabled.
    bool calibrationEnabled() const { return m_calibrationEnabled; }

    /// Apply the active input calibration callback to one Q16 value and channel.
    uint16_t applyCalibration(uint16_t q16, uint8_t channel) const;

    // ----- RGBW Extraction -----

    /// Set the maximum 8-bit white-channel value allowed by applyWhiteLimit().
    void setWhiteLimit(uint8_t limit);
    /// Return the configured white-channel limit.
    uint8_t whiteLimit() const { return m_whiteLimit; }

    /// Extract RGBW targets from RGB input using the configured calibration and white policy.
    virtual RgbwTargets extractRgbw(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const;

    /// Clamp white output and redistribute excess into RGB channels where possible.
    RgbwTargets applyWhiteLimit(uint16_t rQ16, uint16_t gQ16,
                                uint16_t bQ16, uint16_t wQ16) const;

    /// Split extracted white equally into W1/W2 for RGBWW/RGBCCT bringup emulation.
    RgbwwTargets extractRgbwwEmulated(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const;

    /// Solve a white target through the existing W solver/LUT path for RGBWW/RGBCCT emulation.
    EncodedState solveWhiteEmulated(uint16_t q16) const;

    // ----- 3D Cube LUT -----
    // Applies a pre-calibrated RGB->RGB, RGBW, RGBWW, or future generalized N-channel 3D lookup table.
    // RGB uses trilinear interpolation by default, while 4-channel and above uses
    // tetrahedral interpolation due to the fact that trilinear interpolation can 
    // introduce illegal topology in a strict sub-gamut solve, while tetrahedral interpolation avoids this issue.
    // In the pipeline this replaces calibration + white extraction:
    //   Input → Transfer Curve → **Cube LUT** → Solver
    // Values returned by the cube are calibrated targets — do not modify
    // them before passing to the solver.

    /// Attach a non-owning 3D cube LUT pointer for RGB-to-output color correction.
    void setCubeLUT3D(const CubeLUT3D* cube);
    /// Enable or disable cube LUT lookup in the input pipeline.
    void setCubeLUT3DEnabled(bool enabled);
    /// Return whether cube LUT lookup is enabled.
    bool cubeLUT3DEnabled() const { return m_cubeLUTEnabled; }

    /// Look up (rQ16, gQ16, bQ16) through the attached 3D cube.
    /// Legacy RGBW-compatible view: for 5-channel cubes this returns W1.
    /// If the cube is disabled or missing, returns passthrough RGB + W=0.
    RgbwTargets applyCubeLUT3D(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const;

    /// RGBWW/RGBCCT-capable cube lookup.
    /// For RGB cubes: W1=W2=0. For RGBW cubes: W2=0.
    /// If the cube is disabled or missing, returns passthrough RGB + W1/W2=0.
    RgbwwTargets applyCubeLUT3D_RGBWW(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const;

    // ----- Phase Mode / Tick Management -----
    // Controls how BFI phases are distributed within a display cycle.
    //
    // FixedMask (default):
    //   Uses the compile-time PHASE_EMIT_MASK bitmask with a 5-phase
    //   cycle.  Backward-compatible with all existing captures and the
    //   HyperTeensy production sketch.
    //
    // Distributed:
    //   Per-BFI natural cycle: each BFI level N repeats a pattern of
    //   1 upper frame followed by N lower frames (cycle = N+1).
    //   BFI 0 → U, BFI 1 → UL, BFI 2 → ULL, BFI 3 → ULLL, etc.
    //
    // DistributedGlobal:
    //   Bresenham-style spacing across a configurable global cycle
    //   length.  Upper and lower frames are spread as evenly as
    //   possible.  Requires setCycleLength().

    /// Set the BFI phase distribution mode used by instance render APIs.
    void setPhaseMode(PhaseMode mode);
    /// Return the active BFI phase distribution mode.
    PhaseMode phaseMode() const { return m_phaseMode; }

    /// Set the global cycle length used by DistributedGlobal mode, clamped to the supported range.
    void setCycleLength(uint8_t len);
    /// Return the active global cycle length.
    uint8_t cycleLength() const { return m_cycleLength; }

    /// Advance the internal tick counter.
    /// Returns true when the tick reaches a cycle boundary (start of a
    /// new display cycle).
    bool advanceTick();

    /// Reset the internal render tick to 0.
    void resetTick();
    /// Return the current internal render tick.
    uint32_t currentTick() const { return m_tick; }

    /// Check whether a channel with the given BFI level shows its upper
    /// value on the current internal tick, using the configured mode.
    bool channelActiveOnCurrentTick(uint8_t bfi) const;

    // ----- Render API -----
    // Use RenderOptions to make channel layout, physical byte order, and BFI
    // map storage explicit at the call site.

    /// Render a full buffer using an explicit FixedMask phase and RenderOptions.
    static void renderLoopStatic(
        const uint8_t* upperFrame, const uint8_t* floorFrame,
        const BfiMapView& bfiMaps,
        uint8_t* displayBuffer, uint16_t pixelCount,
        uint8_t phase,
        const RenderOptions& options);

    /// Render one pixel using an explicit FixedMask phase and RenderOptions.
    static void renderIndexedStatic(
        const uint8_t* upperFrame, const uint8_t* floorFrame,
        const BfiMapView& bfiMaps,
        uint8_t* displayBuffer, uint16_t pixelIndex,
        uint8_t phase,
        const RenderOptions& options);

    /// Render a full buffer using the configured PhaseMode and current internal tick.
    void renderLoop(
        const uint8_t* upperFrame, const uint8_t* floorFrame,
        const BfiMapView& bfiMaps,
        uint8_t* displayBuffer, uint16_t pixelCount,
        const RenderOptions* options = nullptr) const;

    /// Render one pixel using the configured PhaseMode and current internal tick.
    void renderIndexed(
        const uint8_t* upperFrame, const uint8_t* floorFrame,
        const BfiMapView& bfiMaps,
        uint8_t* displayBuffer, uint16_t pixelIndex,
        const RenderOptions* options = nullptr) const;

    // ----- Pixel Commit -----

    /// Commit one pixel's encoded channel states to logical frame buffers and BFI maps.
    static void commitPixel(
        uint8_t* upperFrame, uint8_t* floorFrame,
        BfiMapWriteView& bfiMaps,
        uint16_t pixelIndex,
        const EncodedState* channelStates,
        uint8_t stateCount,
        const RenderOptions& options);

    // ----- LUT Header Dump -----

    /// Emit the currently attached LUTs as an embeddable PROGMEM header.
    void dumpLUTHeader(Print& out) const;

private:
    static bool colorOrderMapFor3(LedColorOrder order, uint8_t (&map)[3]);
    static bool colorOrderMapFor4(LedColorOrder order, uint8_t (&map)[4]);
    static bool colorOrderMapFor5(LedColorOrder order, uint8_t (&map)[5]);
    static bool validateCustomMap(const uint8_t* map, uint8_t channels);
    static bool colorOrderMapForChannels(LedColorOrder order, uint8_t channels,
                                         uint8_t* outMap);
    static uint8_t packedBytesPerPixelForChannels(uint8_t channels);
    static uint8_t readPackedBfiChannelForChannels(const uint8_t* packed,
                                                   uint16_t pixelIndex,
                                                   uint8_t channel,
                                                   uint8_t channels);
    static void writePackedBfiChannelForChannels(uint8_t* packed,
                                                 uint16_t pixelIndex,
                                                 uint8_t channel,
                                                 uint8_t channels,
                                                 uint8_t value);
    static const uint8_t* separateBfiMapForChannel(const BfiMapView& bfiMaps,
                                                   uint8_t channel);
    static uint8_t* separateBfiMapForChannel(BfiMapWriteView& bfiMaps,
                                             uint8_t channel);

    static constexpr uint8_t channelsForLayout(PixelLayout layout)
    {
        return static_cast<uint8_t>(layout);
    }

    uint8_t solverLUTStorageChannels() const
    {
        const uint8_t logicalChannels = (m_numChannels == 0u)
            ? SOLVER_DEFAULT_CHANNELS
            : m_numChannels;
        return (m_solverLUTMode == SolverLUTMode::Shared) ? 1u : logicalChannels;
    }

    // LUT storage (caller-owned)
    uint8_t* m_valueLUT = nullptr;
    uint8_t* m_bfiLUT = nullptr;
    uint8_t* m_floorLUT = nullptr;
    uint16_t* m_outputQ16LUT = nullptr;
    uint16_t m_lutSize = 0;

    // Transfer curve (caller-owned data pointers)
    const uint16_t* m_curveShared = nullptr;
    const uint16_t* m_curveR = nullptr;
    const uint16_t* m_curveG = nullptr;
    const uint16_t* m_curveB = nullptr;
    const uint16_t* m_curveW = nullptr;
    const uint16_t* m_curveW2 = nullptr;
    uint16_t m_curveBucketCount = 0;
    TransferCurveMode m_transferCurveMode = TransferCurveMode::Single;
    bool m_transferCurveEnabled = false;

    // Active logical channel count for solver mapping/clamping.
    uint8_t m_numChannels = SOLVER_DEFAULT_CHANNELS;
    SolverLUTMode m_solverLUTMode = SolverLUTMode::PerChannel;

    FifthChannelSolveMode m_fifthChannelSolveMode = FifthChannelSolveMode::EmulateFromW;
    LedColorOrder m_ledColorOrder = LedColorOrder::GRBW;
    uint8_t m_colorOrderMap3[3] = {0u, 1u, 2u};
    uint8_t m_colorOrderMap4[4] = {0u, 1u, 2u, 3u};
    uint8_t m_colorOrderMap5[5] = {0u, 1u, 2u, 3u, 4u};

    // Input calibration
    CalibrationFn m_calibrationFn = nullptr;
    bool m_calibrationEnabled = false;

    // White limit
    uint8_t m_whiteLimit = 255;

    // 3D Cube LUT (non-owning pointer — caller owns the CubeLUT3D)
    const CubeLUT3D* m_cubeLUT = nullptr;
    bool m_cubeLUTEnabled = false;

    // Phase mode / tick
    PhaseMode m_phaseMode = PhaseMode::FixedMask;
    uint8_t m_cycleLength = SOLVER_FIXED_BFI_LEVELS;
    uint32_t m_tick = 0;

    // Solver config (owned directly — no external type dependency)
    PolicyConfig m_cfg;
};

} // namespace TemporalBFI
