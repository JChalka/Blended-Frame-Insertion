#include "CubeLUT3D.h"
#include <string.h> // memcpy

namespace TemporalBFI {

// ============================================================================
// Q8 linear interpolation helper (file-local)
// ============================================================================

static inline uint16_t lerpQ8(uint16_t a, uint16_t b, uint16_t f256)
{
    // f256 in [0, 256]: 0 → a, 256 → b.
    // Max intermediate: 65535 × 256 = 16,776,960 — fits uint32.
    return (uint16_t)(((uint32_t)a * (256u - f256) + (uint32_t)b * f256 + 128u) >> 8);
}

// ============================================================================
// Static helpers
// ============================================================================

uint16_t CubeLUT3D::maxGridForBytes(size_t availableBytes, uint8_t ch)
{
    if (ch == 0) return 0;
    const size_t maxN3 = availableBytes / ((size_t)ch * sizeof(uint16_t));
    if (maxN3 == 0) return 0;

    // Binary search for integer cube root.
    uint16_t n = 1;
    for (uint16_t step = 256; step > 0; step >>= 1) {
        const uint16_t test = n + step;
        const size_t vol = (size_t)test * test * test;
        if (vol <= maxN3) n = test;
    }
    return n;
}

bool CubeLUT3D::parseHeader(const uint8_t* h, uint16_t& outGrid, uint8_t& outCh)
{
    // Little-endian uint16 reads (portable).
    const uint16_t g = (uint16_t)h[0] | ((uint16_t)h[1] << 8);
    const uint16_t c = (uint16_t)h[2] | ((uint16_t)h[3] << 8);
    if (g < 2 || (c != 3 && c != 4)) return false;
    outGrid = g;
    outCh   = (uint8_t)c;
    return true;
}

// ============================================================================
// attach / loadFromFileBuffer
// ============================================================================

void CubeLUT3D::attach(uint16_t* cubeData, uint16_t grid, uint8_t ch)
{
    data     = cubeData;
    gridSize = grid;
    channels = ch;
}

bool CubeLUT3D::loadFromFileBuffer(const uint8_t* fileBuffer, size_t fileSize)
{
    if (fileSize < CUBE_HEADER_BYTES) return false;

    uint16_t headerGrid = 0;
    uint8_t  headerCh   = 0;
    if (!parseHeader(fileBuffer, headerGrid, headerCh)) return false;

    const size_t payloadBytes = dataBytes(headerGrid, headerCh);
    if (fileSize < CUBE_HEADER_BYTES + payloadBytes) return false;
    if (!data) return false;

    memcpy(data, fileBuffer + CUBE_HEADER_BYTES, payloadBytes);
    gridSize = headerGrid;
    channels = headerCh;
    return true;
}

// ============================================================================
// Trilinear interpolation lookup
// ============================================================================

RgbwTargets CubeLUT3D::lookup(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const
{
    RgbwTargets out = {0, 0, 0, 0};
    if (!data || gridSize < 2) return out;

    const uint16_t gs1 = gridSize - 1;

    // Map each Q16 input to a fractional grid position.
    // gridPos = q16 × (gridSize − 1), range 0 … 65535×gs1.
    const uint32_t rPos = (uint32_t)rQ16 * gs1;
    const uint32_t gPos = (uint32_t)gQ16 * gs1;
    const uint32_t bPos = (uint32_t)bQ16 * gs1;

    // Floor grid indices, clamped so +1 is always in-bounds.
    uint16_t ri = (uint16_t)(rPos / 65535u);
    uint16_t gi = (uint16_t)(gPos / 65535u);
    uint16_t bi = (uint16_t)(bPos / 65535u);
    if (ri > gs1 - 1) ri = gs1 - 1;
    if (gi > gs1 - 1) gi = gs1 - 1;
    if (bi > gs1 - 1) bi = gs1 - 1;

    // Fractional part in Q8 (0 … 256, where 256 = fully at next vertex).
    const uint16_t rF = (uint16_t)(((rPos - (uint32_t)ri * 65535u) * 256u + 32767u) / 65535u);
    const uint16_t gF = (uint16_t)(((gPos - (uint32_t)gi * 65535u) * 256u + 32767u) / 65535u);
    const uint16_t bF = (uint16_t)(((bPos - (uint32_t)bi * 65535u) * 256u + 32767u) / 65535u);

    // Strides for flat data layout: data[(r×gs×gs + g×gs + b) × ch + c]
    const uint32_t sB = (uint32_t)channels;
    const uint32_t sG = (uint32_t)gridSize * sB;
    const uint32_t sR = (uint32_t)gridSize * sG;

    // Base offset for corner (ri, gi, bi).
    const uint32_t base = ri * sR + gi * sG + bi * sB;

    // Eight surrounding cube vertices.
    const uint32_t c000 = base;
    const uint32_t c001 = base + sB;
    const uint32_t c010 = base + sG;
    const uint32_t c011 = base + sG + sB;
    const uint32_t c100 = base + sR;
    const uint32_t c101 = base + sR + sB;
    const uint32_t c110 = base + sR + sG;
    const uint32_t c111 = base + sR + sG + sB;

    // Trilinear interpolation: lerp along B, then G, then R.
    // 7 lerps per channel, 4 (RGBW) or 3 (RGB) channels total.
    const uint8_t numCh = (channels >= 4) ? 4 : 3;
    uint16_t result[4] = {0, 0, 0, 0};

    for (uint8_t ch = 0; ch < numCh; ++ch) {
        // Along B axis (4 pairs → 4).
        const uint16_t b00 = lerpQ8(data[c000 + ch], data[c001 + ch], bF);
        const uint16_t b01 = lerpQ8(data[c010 + ch], data[c011 + ch], bF);
        const uint16_t b10 = lerpQ8(data[c100 + ch], data[c101 + ch], bF);
        const uint16_t b11 = lerpQ8(data[c110 + ch], data[c111 + ch], bF);
        // Along G axis (2 pairs → 2).
        const uint16_t g0 = lerpQ8(b00, b01, gF);
        const uint16_t g1 = lerpQ8(b10, b11, gF);
        // Along R axis (1 pair → result).
        result[ch] = lerpQ8(g0, g1, rF);
    }

    out.rQ16 = result[0];
    out.gQ16 = result[1];
    out.bQ16 = result[2];
    out.wQ16 = result[3]; // remains 0 for 3-channel cubes
    return out;
}

} // namespace TemporalBFI
