#pragma once
#include "TemporalBFI.h"

namespace TemporalBFI {

// ============================================================================
// CubeLUT3D — Platform-agnostic 3D color-correction cube loader
//
// Binary file layout produced by rgbw_lut_gui.py "Export Binary Cube":
//   Bytes 0-1:   grid size N  (uint16, little-endian)
//   Bytes 2-3:   channels C   (uint16, little-endian) — 4 for RGBW, 3 for RGB
//   Bytes 4...:  N×N×N×C uint16 values in R-major, G, B row-major order
//                i.e. cube[r][g][b] = {ch0, ch1, ..., chC-1}
//   Total file size = 4 + N³ × C × 2  bytes.
//
// Pipeline placement:
//   Input → Transfer Curve → **3D Cube LUT** → Solver
//   The cube contains pre-calibrated RGBW (or RGB) values.
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

struct CubeLUT3D {
    uint16_t* data     = nullptr;
    uint16_t  gridSize = 0;
    uint8_t   channels = 0;

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
    /// a valid cube (grid >= 2, channels == 3 or 4).
    static bool parseHeader(const uint8_t* header4,
                            uint16_t& outGrid, uint8_t& outChannels);

    /// Attach a pre-populated, caller-owned data buffer.
    /// The buffer must contain gridSize³ × channels uint16 values.
    void attach(uint16_t* cubeData, uint16_t grid, uint8_t ch);

    /// Load from a complete file buffer (4-byte header followed by payload).
    /// The `data` pointer must already point to a buffer of at least
    /// dataBytes(grid, ch) bytes — call parseHeader() first to discover
    /// the size, allocate, then call this.
    /// Returns false on header mismatch or insufficient buffer size.
    bool loadFromFileBuffer(const uint8_t* fileBuffer, size_t fileSize);

    // --- Lookup ---

    /// Trilinear-interpolated lookup.  Maps input RGB (Q16) through the
    /// cube and returns the interpolated output.
    /// For RGBW cubes all four channels are populated.
    /// For RGB cubes, wQ16 is always 0.
    RgbwTargets lookup(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const;

    // --- Queries ---

    bool isValid() const { return data && gridSize >= 2 && (channels == 3 || channels == 4); }
    bool isRGBW()  const { return channels == 4; }
};

} // namespace TemporalBFI
