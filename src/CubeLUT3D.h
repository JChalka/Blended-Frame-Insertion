#pragma once
#include "TemporalBFI.h"

namespace TemporalBFI {

/// Interpolation algorithm used for 3D cube lookup.
enum class CubeLUTInterpolation : uint8_t {
    Trilinear = 0,
    Tetrahedral = 1
};

/// Maximum channel count accepted by CubeLUT3D payloads.
static constexpr uint8_t CUBE_MAX_SUPPORTED_CHANNELS = 6;

// ============================================================================
// CubeLUT3D — Platform-agnostic 3D color-correction cube loader
//
// Binary file layout produced by rgbw_lut_gui.py "Export Binary Cube":
//   Bytes 0-1:   grid size N  (uint16, little-endian)
//   Bytes 2-3:   channels C   (uint16, little-endian) — currently 3..6
//   Bytes 4...:  N×N×N×C uint16 values in R-major, G, B row-major order
//                i.e. cube[r][g][b] = {ch0, ch1, ..., chC-1}
//   Total file size = 4 + N³ × C × 2  bytes.
//
// Pipeline placement:
//   Input → Transfer Curve → **3D Cube LUT** → Solver
//   The cube contains pre-calibrated RGB / RGBW / RGBWW-style values.
//   Do not modify channel values after the cube lookup — they are the
//   calibrated targets that feed directly into the BFI solver.
//
// Memory ownership:
//   The caller allocates and owns the data buffer.  CubeLUT3D holds a
//   non-owning pointer.  Use platform-specific allocation in your sketch
//   (EXTMEM, DMAMEM, heap, etc.) and pass the buffer via attach() or
//   loadFromFileBuffer().
// ============================================================================

static constexpr uint16_t CUBE_HEADER_BYTES = 4;

/// Non-owning 3D color-correction cube view and lookup engine.
struct CubeLUT3D {
    /// Caller-owned cube payload: gridSize^3 * channels uint16 values.
    uint16_t* data     = nullptr;
    /// Cube dimension per axis; valid cubes require gridSize >= 2.
    uint16_t  gridSize = 0;
    /// Stored output channel count; valid cubes support 3..CUBE_MAX_SUPPORTED_CHANNELS.
    uint8_t   channels = 0;
    /// Active interpolation algorithm.
    CubeLUTInterpolation interpolation = CubeLUTInterpolation::Trilinear;
    /// Logical output channel index -> stored cube channel index.
    /// First five logical channels are [R, G, B, W1, W2].
    uint8_t logicalToStored[CUBE_MAX_SUPPORTED_CHANNELS] = {0, 1, 2, 3, 4, 5};

    // --- Size helpers ---

    /// Data payload size in bytes (excludes the 4-byte file header).
    static size_t dataBytes(uint16_t grid, uint8_t ch)
    {
        return (size_t)grid * grid * grid * ch * sizeof(uint16_t);
    }

    /// Total file size including the 4-byte header.
    static size_t fileBytes(uint16_t grid, uint8_t ch)
    {
        return CUBE_HEADER_BYTES + dataBytes(grid, ch);
    }

    /// Largest grid size whose data fits within `availableBytes`.
    static uint16_t maxGridForBytes(size_t availableBytes, uint8_t ch);

    // --- Loading ---

    /// Parse the 4-byte file header.  Returns true if the header describes
    /// a valid cube (grid >= 2, channels in 3..CUBE_MAX_SUPPORTED_CHANNELS).
    static bool parseHeader(const uint8_t* header4,
                            uint16_t& outGrid, uint8_t& outChannels);

    /// Attach a pre-populated, caller-owned data buffer.
    /// The buffer must contain gridSize³ × channels uint16 values.
    void attach(uint16_t* cubeData, uint16_t grid, uint8_t ch);

    /// Configure logical-to-stored channel mapping.
    /// `count` must equal current `channels` and describe a permutation
    /// over [0..channels-1].
    bool setLogicalToStoredMap(const uint8_t* map, uint8_t count);

    /// Load from a complete file buffer (4-byte header followed by payload).
    /// The `data` pointer must already point to a buffer of at least
    /// dataBytes(grid, ch) bytes — call parseHeader() first to discover
    /// the size, allocate, then call this.
    /// Returns false on header mismatch or insufficient buffer size.
    bool loadFromFileBuffer(const uint8_t* fileBuffer, size_t fileSize);

    // --- Lookup ---

    /// Interpolated lookup (trilinear or tetrahedral).  Maps input RGB (Q16)
    /// through the cube and returns logical RGBW output.
    /// For RGBW cubes all four channels are populated.
    /// For RGB cubes, wQ16 is always 0.
    RgbwTargets lookup(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const;

    /// Logical RGBWW/RGBCCT output. For cubes with <5 channels, missing
    /// channels are returned as 0.
    RgbwwTargets lookupRgbww(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const;

    /// Raw logical channel lookup. Returns number of channels written
    /// (up to outCapacity), or 0 on invalid cube.
    uint8_t lookupChannels(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16,
                           uint16_t* outValues, uint8_t outCapacity) const;

    /// Set interpolation mode explicitly.
    void setInterpolation(CubeLUTInterpolation mode) { interpolation = mode; }
    /// Return the active interpolation mode.
    CubeLUTInterpolation interpolationMode() const { return interpolation; }

    /// Apply default interpolation policy by channel family:
    /// - RGB (3ch): Trilinear
    /// - RGBW/RGBCCT/future 5-6ch: Tetrahedral
    void setDefaultInterpolationForChannels();

    // --- Queries ---

    /// Return true when data, grid size, and channel count describe a usable cube.
    bool isValid() const {
        return data && gridSize >= 2 && channels >= 3 && channels <= CUBE_MAX_SUPPORTED_CHANNELS;
    }
    /// Return true when the attached cube has RGB output.
    bool isRGB()   const { return channels == 3; }
    /// Return true when the attached cube has RGBW output.
    bool isRGBW()  const { return channels == 4; }
    /// Return true when the attached cube has RGBWW/RGBCCT-style output.
    bool isRGBWW() const { return channels == 5; }
};

} // namespace TemporalBFI
