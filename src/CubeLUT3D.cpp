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

static inline int32_t mulDiffQ16(int32_t diff, uint16_t fracQ16)
{
    const int64_t acc = (int64_t)diff * (int64_t)fracQ16;
    if (acc >= 0) return (int32_t)((acc + 32767) / 65535);
    return (int32_t)-(((-acc) + 32767) / 65535);
}

static inline uint16_t clampU16FromI32(int32_t value)
{
    if (value <= 0) return 0;
    if (value >= 65535) return 65535;
    return (uint16_t)value;
}

static bool validatePermutation(const uint8_t* map, uint8_t count)
{
    if (!map || count == 0 || count > CUBE_MAX_SUPPORTED_CHANNELS) return false;
    uint8_t seenMask = 0;
    for (uint8_t i = 0; i < count; ++i) {
        const uint8_t v = map[i];
        if (v >= count) return false;
        const uint8_t bit = (uint8_t)(1u << v);
        if (seenMask & bit) return false;
        seenMask = (uint8_t)(seenMask | bit);
    }
    return true;
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
    if (g < 2 || c < 3 || c > CUBE_MAX_SUPPORTED_CHANNELS) return false;
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
    for (uint8_t i = 0; i < CUBE_MAX_SUPPORTED_CHANNELS; ++i)
        logicalToStored[i] = i;
    setDefaultInterpolationForChannels();
}

bool CubeLUT3D::setLogicalToStoredMap(const uint8_t* map, uint8_t count)
{
    if (count != channels) return false;
    if (!validatePermutation(map, count)) return false;
    for (uint8_t i = 0; i < count; ++i)
        logicalToStored[i] = map[i];
    return true;
}

void CubeLUT3D::setDefaultInterpolationForChannels()
{
    interpolation = (channels <= 3)
        ? CubeLUTInterpolation::Trilinear
        : CubeLUTInterpolation::Tetrahedral;
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
    for (uint8_t i = 0; i < CUBE_MAX_SUPPORTED_CHANNELS; ++i)
        logicalToStored[i] = i;
    setDefaultInterpolationForChannels();
    return true;
}

// ============================================================================
// Interpolation lookup
// ============================================================================

uint8_t CubeLUT3D::lookupChannels(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16,
                                  uint16_t* outValues, uint8_t outCapacity) const
{
    if (!outValues || outCapacity == 0) return 0;
    for (uint8_t i = 0; i < outCapacity; ++i) outValues[i] = 0;

    if (!isValid()) return 0;

    const uint16_t gs1 = gridSize - 1;
    const uint32_t rPos = (uint32_t)rQ16 * gs1;
    const uint32_t gPos = (uint32_t)gQ16 * gs1;
    const uint32_t bPos = (uint32_t)bQ16 * gs1;

    uint16_t ri = (uint16_t)(rPos / 65535u);
    uint16_t gi = (uint16_t)(gPos / 65535u);
    uint16_t bi = (uint16_t)(bPos / 65535u);
    if (ri > gs1 - 1) ri = gs1 - 1;
    if (gi > gs1 - 1) gi = gs1 - 1;
    if (bi > gs1 - 1) bi = gs1 - 1;

    const uint16_t rFracQ16 = (uint16_t)(rPos - (uint32_t)ri * 65535u);
    const uint16_t gFracQ16 = (uint16_t)(gPos - (uint32_t)gi * 65535u);
    const uint16_t bFracQ16 = (uint16_t)(bPos - (uint32_t)bi * 65535u);

    const uint16_t rF = (uint16_t)(((uint32_t)rFracQ16 * 256u + 32767u) / 65535u);
    const uint16_t gF = (uint16_t)(((uint32_t)gFracQ16 * 256u + 32767u) / 65535u);
    const uint16_t bF = (uint16_t)(((uint32_t)bFracQ16 * 256u + 32767u) / 65535u);

    const uint32_t sB = (uint32_t)channels;
    const uint32_t sG = (uint32_t)gridSize * sB;
    const uint32_t sR = (uint32_t)gridSize * sG;

    const uint32_t base = ri * sR + gi * sG + bi * sB;

    const uint32_t c000 = base;
    const uint32_t c001 = base + sB;
    const uint32_t c010 = base + sG;
    const uint32_t c011 = base + sG + sB;
    const uint32_t c100 = base + sR;
    const uint32_t c101 = base + sR + sB;
    const uint32_t c110 = base + sR + sG;
    const uint32_t c111 = base + sR + sG + sB;

    const uint8_t numCh = channels;
    uint16_t result[CUBE_MAX_SUPPORTED_CHANNELS] = {0, 0, 0, 0, 0, 0};

    for (uint8_t ch = 0; ch < numCh; ++ch) {
        const uint8_t storedCh = logicalToStored[ch];
        if (storedCh >= channels) {
            result[ch] = 0;
            continue;
        }

        if (interpolation == CubeLUTInterpolation::Tetrahedral) {
            const int32_t v000 = data[c000 + storedCh];
            const int32_t v001 = data[c001 + storedCh];
            const int32_t v010 = data[c010 + storedCh];
            const int32_t v011 = data[c011 + storedCh];
            const int32_t v100 = data[c100 + storedCh];
            const int32_t v101 = data[c101 + storedCh];
            const int32_t v110 = data[c110 + storedCh];
            const int32_t v111 = data[c111 + storedCh];

            int32_t accum = v000;

            if (rFracQ16 >= gFracQ16) {
                if (gFracQ16 >= bFracQ16) {
                    accum += mulDiffQ16(v100 - v000, rFracQ16);
                    accum += mulDiffQ16(v110 - v100, gFracQ16);
                    accum += mulDiffQ16(v111 - v110, bFracQ16);
                } else if (rFracQ16 >= bFracQ16) {
                    accum += mulDiffQ16(v100 - v000, rFracQ16);
                    accum += mulDiffQ16(v101 - v100, bFracQ16);
                    accum += mulDiffQ16(v111 - v101, gFracQ16);
                } else {
                    accum += mulDiffQ16(v001 - v000, bFracQ16);
                    accum += mulDiffQ16(v101 - v001, rFracQ16);
                    accum += mulDiffQ16(v111 - v101, gFracQ16);
                }
            } else {
                if (bFracQ16 >= gFracQ16) {
                    accum += mulDiffQ16(v001 - v000, bFracQ16);
                    accum += mulDiffQ16(v011 - v001, gFracQ16);
                    accum += mulDiffQ16(v111 - v011, rFracQ16);
                } else if (bFracQ16 >= rFracQ16) {
                    accum += mulDiffQ16(v010 - v000, gFracQ16);
                    accum += mulDiffQ16(v011 - v010, bFracQ16);
                    accum += mulDiffQ16(v111 - v011, rFracQ16);
                } else {
                    accum += mulDiffQ16(v010 - v000, gFracQ16);
                    accum += mulDiffQ16(v110 - v010, rFracQ16);
                    accum += mulDiffQ16(v111 - v110, bFracQ16);
                }
            }

            result[ch] = clampU16FromI32(accum);
        } else {
            const uint16_t b00 = lerpQ8(data[c000 + storedCh], data[c001 + storedCh], bF);
            const uint16_t b01 = lerpQ8(data[c010 + storedCh], data[c011 + storedCh], bF);
            const uint16_t b10 = lerpQ8(data[c100 + storedCh], data[c101 + storedCh], bF);
            const uint16_t b11 = lerpQ8(data[c110 + storedCh], data[c111 + storedCh], bF);
            const uint16_t g0 = lerpQ8(b00, b01, gF);
            const uint16_t g1 = lerpQ8(b10, b11, gF);
            result[ch] = lerpQ8(g0, g1, rF);
        }
    }

    const uint8_t writeCount = (numCh < outCapacity) ? numCh : outCapacity;
    for (uint8_t i = 0; i < writeCount; ++i)
        outValues[i] = result[i];
    return writeCount;
}

RgbwwTargets CubeLUT3D::lookupRgbww(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const
{
    uint16_t out[5] = {0, 0, 0, 0, 0};
    lookupChannels(rQ16, gQ16, bQ16, out, 5);
    return {out[0], out[1], out[2], out[3], out[4]};
}

RgbwTargets CubeLUT3D::lookup(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const
{
    const RgbwwTargets rgbww = lookupRgbww(rQ16, gQ16, bQ16);
    RgbwTargets out;
    out.rQ16 = rgbww.rQ16;
    out.gQ16 = rgbww.gQ16;
    out.bQ16 = rgbww.bQ16;
    out.wQ16 = rgbww.w1Q16;
    return out;
}

} // namespace TemporalBFI
