#include "TemporalBFI.h"
#include "CubeLUT3D.h"

namespace TemporalBFI {

// ============================================================================
// LUT Management
// ============================================================================

void SolverRuntime::attachLUTs(uint8_t* valueLUT, uint8_t* bfiLUT,
                               uint8_t* floorLUT, uint16_t* outputQ16LUT,
                               uint16_t lutSize)
{
    m_valueLUT = valueLUT;
    m_bfiLUT = bfiLUT;
    m_floorLUT = floorLUT;
    m_outputQ16LUT = outputQ16LUT;
    m_lutSize = lutSize;
}

void SolverRuntime::precompute(SolverFn fn, uint8_t numChannels)
{
    if (!fn || !m_valueLUT || !m_bfiLUT || m_lutSize < 2u) return;

    for (uint8_t ch = 0; ch < numChannels; ++ch)
    {
        const size_t offset = (size_t)ch * (size_t)m_lutSize;
        for (size_t i = 0; i < m_lutSize; ++i)
        {
            const uint16_t q16 = (uint16_t)(((uint32_t)i * 65535u) / (uint32_t)(m_lutSize - 1u));
            const auto s = fn(q16, ch, m_cfg);
            m_valueLUT[offset + i] = s.value;
            m_bfiLUT[offset + i] = s.bfi;
            if (m_floorLUT) m_floorLUT[offset + i] = s.lowerValue;
            if (m_outputQ16LUT) m_outputQ16LUT[offset + i] = s.outputQ16;
        }
        m_valueLUT[offset] = 0;
        m_bfiLUT[offset] = 0;
        if (m_floorLUT) m_floorLUT[offset] = 0;
        if (m_outputQ16LUT) m_outputQ16LUT[offset] = 0;
    }
}

void SolverRuntime::loadPrecomputed(const uint8_t* srcValue, const uint8_t* srcBfi,
                                    const uint8_t* srcFloor, const uint16_t* srcOutputQ16,
                                    uint8_t numChannels, uint16_t srcLutSize)
{
    if (!m_valueLUT || !m_bfiLUT || m_lutSize < 2u) return;
    // If srcLutSize provided, verify it matches m_lutSize to prevent stride mismatch
    // (each channel is srcLutSize entries wide in the source; copying with wrong stride
    //  reads across channel boundaries and corrupts all channel data).
    if (srcLutSize != 0 && srcLutSize != m_lutSize) return;
    const size_t totalEntries = (size_t)numChannels * (size_t)m_lutSize;

    memcpy(m_valueLUT, srcValue, totalEntries);
    memcpy(m_bfiLUT, srcBfi, totalEntries);
    if (m_floorLUT && srcFloor)
        memcpy(m_floorLUT, srcFloor, totalEntries);
    if (m_outputQ16LUT && srcOutputQ16)
        memcpy(m_outputQ16LUT, srcOutputQ16, totalEntries * sizeof(uint16_t));
}

// ============================================================================
// Solver (runtime hot path)
// ============================================================================

size_t SolverRuntime::solverLutIndex(uint16_t q16) const
{
    return lutIndexForSize(q16, m_lutSize);
}

EncodedState SolverRuntime::solve(uint16_t q16, uint8_t channel) const
{
    EncodedState out{};
    if (q16 == 0 || !m_valueLUT || !m_bfiLUT || m_lutSize == 0)
        return out;

    const size_t idx = solverLutIndex(q16);
    const size_t offset = (size_t)channel * (size_t)m_lutSize + idx;

    out.value = m_valueLUT[offset];
    out.bfi = m_bfiLUT[offset];
    out.lowerValue = m_floorLUT ? m_floorLUT[offset] : out.value;
    out.outputQ16 = m_outputQ16LUT ? m_outputQ16LUT[offset] : 0;
    out.ladderIndex = (uint16_t)idx;
    return out;
}

// ============================================================================
// Transfer Curve
// ============================================================================

void SolverRuntime::setTransferCurve(const uint16_t* curveR, const uint16_t* curveG,
                                     const uint16_t* curveB, const uint16_t* curveW,
                                     uint16_t bucketCount)
{
    m_curveR = curveR;
    m_curveG = curveG;
    m_curveB = curveB;
    m_curveW = curveW;
    m_curveBucketCount = bucketCount;
}

void SolverRuntime::setTransferCurveEnabled(bool enabled)
{
    m_transferCurveEnabled = enabled;
}

uint16_t SolverRuntime::applyTransferCurve(uint16_t q16, uint8_t channel) const
{
    if (!m_transferCurveEnabled || m_curveBucketCount == 0) return q16;

    const uint16_t* curve = nullptr;
    switch (channel)
    {
        case 0: curve = m_curveG; break;
        case 1: curve = m_curveR; break;
        case 2: curve = m_curveB; break;
        default: curve = m_curveW; break;
    }
    if (!curve) return q16;

    const size_t idx = lutIndexForSize(q16, m_curveBucketCount);
    return curve[idx];
}

// ============================================================================
// Input Calibration
// ============================================================================

void SolverRuntime::setCalibrationFunction(CalibrationFn fn)
{
    m_calibrationFn = fn;
}

void SolverRuntime::setCalibrationEnabled(bool enabled)
{
    m_calibrationEnabled = enabled;
}

uint16_t SolverRuntime::applyCalibration(uint16_t q16, uint8_t channel) const
{
    if (!m_calibrationEnabled || !m_calibrationFn) return q16;
    return m_calibrationFn(q16, channel);
}

// ============================================================================
// 3D Cube LUT
// ============================================================================

void SolverRuntime::setCubeLUT3D(const CubeLUT3D* cube)
{
    m_cubeLUT = cube;
}

void SolverRuntime::setCubeLUT3DEnabled(bool enabled)
{
    m_cubeLUTEnabled = enabled;
}

RgbwTargets SolverRuntime::applyCubeLUT3D(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const
{
    if (!m_cubeLUTEnabled || !m_cubeLUT || !m_cubeLUT->isValid()) {
        // Passthrough — no cube loaded or disabled.
        return {rQ16, gQ16, bQ16, 0};
    }
    return m_cubeLUT->lookup(rQ16, gQ16, bQ16);
}

// ============================================================================
// RGBW Extraction
// ============================================================================

void SolverRuntime::setWhiteLimit(uint8_t limit)
{
    m_whiteLimit = limit;
}

RgbwTargets SolverRuntime::extractRgbw(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const
{
    // Apply calibration to each channel (solver channel map: 0=G, 1=R, 2=B, 3=W).
    const uint16_t rCal = applyCalibration(rQ16, 1);
    const uint16_t gCal = applyCalibration(gQ16, 0);
    const uint16_t bCal = applyCalibration(bQ16, 2);

    uint16_t wExtract = min3U16(rCal, gCal, bCal);

    // Apply white limit (calibrated domain).
    const uint16_t whiteLimitQ16 = scale8ToQ16(m_whiteLimit);
    const uint16_t whiteLimitCal = applyCalibration(whiteLimitQ16, 3);
    if (wExtract > whiteLimitCal)
        wExtract = whiteLimitCal;

    RgbwTargets out;
    out.rQ16 = (rCal > wExtract) ? uint16_t(rCal - wExtract) : 0;
    out.gQ16 = (gCal > wExtract) ? uint16_t(gCal - wExtract) : 0;
    out.bQ16 = (bCal > wExtract) ? uint16_t(bCal - wExtract) : 0;
    out.wQ16 = wExtract;
    return out;
}

RgbwTargets SolverRuntime::applyWhiteLimit(uint16_t rQ16, uint16_t gQ16,
                                           uint16_t bQ16, uint16_t wQ16) const
{
    const uint16_t whiteLimitQ16 = scale8ToQ16(m_whiteLimit);
    const uint16_t whiteLimitCal = applyCalibration(whiteLimitQ16, 3);
    if (wQ16 > whiteLimitCal)
        wQ16 = whiteLimitCal;

    RgbwTargets out;
    out.rQ16 = rQ16;
    out.gQ16 = gQ16;
    out.bQ16 = bQ16;
    out.wQ16 = wQ16;
    return out;
}

// ============================================================================
// Pixel Commit
// ============================================================================

void SolverRuntime::commitPixelRGBW(
    uint8_t* upperFrame, uint8_t* floorFrame,
    uint8_t* bfiMapG, uint8_t* bfiMapR,
    uint8_t* bfiMapB, uint8_t* bfiMapW,
    uint16_t pixelIndex,
    const EncodedState& g, const EncodedState& r,
    const EncodedState& b, const EncodedState& w)
{
    const uint32_t off = (uint32_t)pixelIndex * 4u;
    upperFrame[off + 0] = g.value;
    upperFrame[off + 1] = r.value;
    upperFrame[off + 2] = b.value;
    upperFrame[off + 3] = w.value;

    if (floorFrame)
    {
        floorFrame[off + 0] = g.lowerValue;
        floorFrame[off + 1] = r.lowerValue;
        floorFrame[off + 2] = b.lowerValue;
        floorFrame[off + 3] = w.lowerValue;
    }

    bfiMapG[pixelIndex] = g.bfi;
    bfiMapR[pixelIndex] = r.bfi;
    bfiMapB[pixelIndex] = b.bfi;
    bfiMapW[pixelIndex] = w.bfi;
}

void SolverRuntime::commitPixelRGB(
    uint8_t* upperFrame, uint8_t* floorFrame,
    uint8_t* bfiMapG, uint8_t* bfiMapR,
    uint8_t* bfiMapB,
    uint16_t pixelIndex,
    const EncodedState& g, const EncodedState& r,
    const EncodedState& b)
{
    const uint32_t off = (uint32_t)pixelIndex * 3u;
    upperFrame[off + 0] = g.value;
    upperFrame[off + 1] = r.value;
    upperFrame[off + 2] = b.value;

    if (floorFrame)
    {
        floorFrame[off + 0] = g.lowerValue;
        floorFrame[off + 1] = r.lowerValue;
        floorFrame[off + 2] = b.lowerValue;
    }

    bfiMapG[pixelIndex] = g.bfi;
    bfiMapR[pixelIndex] = r.bfi;
    bfiMapB[pixelIndex] = b.bfi;
}

// ============================================================================
// BFI Rendering
// ============================================================================

void SolverRuntime::renderSubpixelBFI_RGBW(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* bfiMapG, const uint8_t* bfiMapR,
    const uint8_t* bfiMapB, const uint8_t* bfiMapW,
    uint8_t* displayBuffer, uint16_t pixelCount,
    uint8_t phase)
{
    const uint8_t phaseBit = (uint8_t)(1u << (phase & 0x07u));

    const uint8_t* src = upperFrame;
    const uint8_t* floor = floorFrame;
    uint8_t* dst = displayBuffer;

    for (uint16_t i = 0; i < pixelCount; ++i)
    {
        dst[0] = (PHASE_EMIT_MASK[clampBfi(bfiMapG[i])] & phaseBit) ? src[0] : (floor ? floor[0] : 0);
        dst[1] = (PHASE_EMIT_MASK[clampBfi(bfiMapR[i])] & phaseBit) ? src[1] : (floor ? floor[1] : 0);
        dst[2] = (PHASE_EMIT_MASK[clampBfi(bfiMapB[i])] & phaseBit) ? src[2] : (floor ? floor[2] : 0);
        dst[3] = (PHASE_EMIT_MASK[clampBfi(bfiMapW[i])] & phaseBit) ? src[3] : (floor ? floor[3] : 0);

        src += 4;
        if (floor) floor += 4;
        dst += 4;
    }
}

void SolverRuntime::renderSubpixelBFI_RGB(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* bfiMapG, const uint8_t* bfiMapR,
    const uint8_t* bfiMapB,
    uint8_t* displayBuffer, uint16_t pixelCount,
    uint8_t phase)
{
    const uint8_t phaseBit = (uint8_t)(1u << (phase & 0x07u));

    const uint8_t* src = upperFrame;
    const uint8_t* floor = floorFrame;
    uint8_t* dst = displayBuffer;

    for (uint16_t i = 0; i < pixelCount; ++i)
    {
        dst[0] = (PHASE_EMIT_MASK[clampBfi(bfiMapG[i])] & phaseBit) ? src[0] : (floor ? floor[0] : 0);
        dst[1] = (PHASE_EMIT_MASK[clampBfi(bfiMapR[i])] & phaseBit) ? src[1] : (floor ? floor[1] : 0);
        dst[2] = (PHASE_EMIT_MASK[clampBfi(bfiMapB[i])] & phaseBit) ? src[2] : (floor ? floor[2] : 0);

        src += 3;
        if (floor) floor += 3;
        dst += 3;
    }
}

// ============================================================================
// Indexed BFI Rendering (single pixel, static / FixedMask)
// ============================================================================

void SolverRuntime::renderPixelBFI_RGBW(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* bfiMapG, const uint8_t* bfiMapR,
    const uint8_t* bfiMapB, const uint8_t* bfiMapW,
    uint8_t* displayBuffer, uint16_t pixelIndex,
    uint8_t phase)
{
    const uint8_t phaseBit = (uint8_t)(1u << (phase & 0x07u));
    const uint32_t off = (uint32_t)pixelIndex * 4u;

    const uint8_t* src = upperFrame + off;
    const uint8_t* flr = floorFrame ? floorFrame + off : nullptr;
    uint8_t* dst = displayBuffer + off;

    dst[0] = (PHASE_EMIT_MASK[clampBfi(bfiMapG[pixelIndex])] & phaseBit) ? src[0] : (flr ? flr[0] : 0);
    dst[1] = (PHASE_EMIT_MASK[clampBfi(bfiMapR[pixelIndex])] & phaseBit) ? src[1] : (flr ? flr[1] : 0);
    dst[2] = (PHASE_EMIT_MASK[clampBfi(bfiMapB[pixelIndex])] & phaseBit) ? src[2] : (flr ? flr[2] : 0);
    dst[3] = (PHASE_EMIT_MASK[clampBfi(bfiMapW[pixelIndex])] & phaseBit) ? src[3] : (flr ? flr[3] : 0);
}

void SolverRuntime::renderPixelBFI_RGB(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* bfiMapG, const uint8_t* bfiMapR,
    const uint8_t* bfiMapB,
    uint8_t* displayBuffer, uint16_t pixelIndex,
    uint8_t phase)
{
    const uint8_t phaseBit = (uint8_t)(1u << (phase & 0x07u));
    const uint32_t off = (uint32_t)pixelIndex * 3u;

    const uint8_t* src = upperFrame + off;
    const uint8_t* flr = floorFrame ? floorFrame + off : nullptr;
    uint8_t* dst = displayBuffer + off;

    dst[0] = (PHASE_EMIT_MASK[clampBfi(bfiMapG[pixelIndex])] & phaseBit) ? src[0] : (flr ? flr[0] : 0);
    dst[1] = (PHASE_EMIT_MASK[clampBfi(bfiMapR[pixelIndex])] & phaseBit) ? src[1] : (flr ? flr[1] : 0);
    dst[2] = (PHASE_EMIT_MASK[clampBfi(bfiMapB[pixelIndex])] & phaseBit) ? src[2] : (flr ? flr[2] : 0);
}

// ============================================================================
// Packed BFI Commit
// ============================================================================

void SolverRuntime::commitPixelRGBW_Packed(
    uint8_t* upperFrame, uint8_t* floorFrame,
    uint8_t* packedBfiMap,
    uint16_t pixelIndex,
    const EncodedState& g, const EncodedState& r,
    const EncodedState& b, const EncodedState& w)
{
    const uint32_t off = (uint32_t)pixelIndex * 4u;
    upperFrame[off + 0] = g.value;
    upperFrame[off + 1] = r.value;
    upperFrame[off + 2] = b.value;
    upperFrame[off + 3] = w.value;

    if (floorFrame)
    {
        floorFrame[off + 0] = g.lowerValue;
        floorFrame[off + 1] = r.lowerValue;
        floorFrame[off + 2] = b.lowerValue;
        floorFrame[off + 3] = w.lowerValue;
    }

    packBfi4(packedBfiMap, pixelIndex, g.bfi, r.bfi, b.bfi, w.bfi);
}

void SolverRuntime::commitPixelRGB_Packed(
    uint8_t* upperFrame, uint8_t* floorFrame,
    uint8_t* packedBfiMap,
    uint16_t pixelIndex,
    const EncodedState& g, const EncodedState& r,
    const EncodedState& b)
{
    const uint32_t off = (uint32_t)pixelIndex * 3u;
    upperFrame[off + 0] = g.value;
    upperFrame[off + 1] = r.value;
    upperFrame[off + 2] = b.value;

    if (floorFrame)
    {
        floorFrame[off + 0] = g.lowerValue;
        floorFrame[off + 1] = r.lowerValue;
        floorFrame[off + 2] = b.lowerValue;
    }

    packBfi3(packedBfiMap, pixelIndex, g.bfi, r.bfi, b.bfi);
}

// ============================================================================
// Packed BFI Rendering
// ============================================================================

void SolverRuntime::renderSubpixelBFI_RGBW_Packed(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* packedBfiMap,
    uint8_t* displayBuffer, uint16_t pixelCount,
    uint8_t phase)
{
    const uint8_t phaseBit = (uint8_t)(1u << (phase & 0x07u));

    const uint8_t* src = upperFrame;
    const uint8_t* floor = floorFrame;
    uint8_t* dst = displayBuffer;
    const uint8_t* pk = packedBfiMap;

    for (uint16_t i = 0; i < pixelCount; ++i)
    {
        const uint8_t gr = pk[0];
        const uint8_t bw = pk[1];

        dst[0] = (PHASE_EMIT_MASK[clampBfi(gr >> 4)]       & phaseBit) ? src[0] : (floor ? floor[0] : 0);
        dst[1] = (PHASE_EMIT_MASK[clampBfi(gr & 0x0Fu)]    & phaseBit) ? src[1] : (floor ? floor[1] : 0);
        dst[2] = (PHASE_EMIT_MASK[clampBfi(bw >> 4)]       & phaseBit) ? src[2] : (floor ? floor[2] : 0);
        dst[3] = (PHASE_EMIT_MASK[clampBfi(bw & 0x0Fu)]    & phaseBit) ? src[3] : (floor ? floor[3] : 0);

        src += 4;
        if (floor) floor += 4;
        dst += 4;
        pk += PACKED_BFI_BYTES_PER_PIXEL;
    }
}

void SolverRuntime::renderSubpixelBFI_RGB_Packed(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* packedBfiMap,
    uint8_t* displayBuffer, uint16_t pixelCount,
    uint8_t phase)
{
    const uint8_t phaseBit = (uint8_t)(1u << (phase & 0x07u));

    const uint8_t* src = upperFrame;
    const uint8_t* floor = floorFrame;
    uint8_t* dst = displayBuffer;
    const uint8_t* pk = packedBfiMap;

    for (uint16_t i = 0; i < pixelCount; ++i)
    {
        const uint8_t gr = pk[0];
        const uint8_t bw = pk[1];

        dst[0] = (PHASE_EMIT_MASK[clampBfi(gr >> 4)]       & phaseBit) ? src[0] : (floor ? floor[0] : 0);
        dst[1] = (PHASE_EMIT_MASK[clampBfi(gr & 0x0Fu)]    & phaseBit) ? src[1] : (floor ? floor[1] : 0);
        dst[2] = (PHASE_EMIT_MASK[clampBfi(bw >> 4)]        & phaseBit) ? src[2] : (floor ? floor[2] : 0);

        src += 3;
        if (floor) floor += 3;
        dst += 3;
        pk += PACKED_BFI_BYTES_PER_PIXEL;
    }
}

// ============================================================================
// Indexed Packed BFI Rendering (single pixel, static / FixedMask)
// ============================================================================

void SolverRuntime::renderPixelBFI_RGBW_Packed(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* packedBfiMap,
    uint8_t* displayBuffer, uint16_t pixelIndex,
    uint8_t phase)
{
    const uint8_t phaseBit = (uint8_t)(1u << (phase & 0x07u));
    const uint32_t off4 = (uint32_t)pixelIndex * 4u;
    const uint32_t pkOff = (uint32_t)pixelIndex * PACKED_BFI_BYTES_PER_PIXEL;

    const uint8_t* src = upperFrame + off4;
    const uint8_t* flr = floorFrame ? floorFrame + off4 : nullptr;
    uint8_t* dst = displayBuffer + off4;
    const uint8_t gr = packedBfiMap[pkOff];
    const uint8_t bw = packedBfiMap[pkOff + 1];

    dst[0] = (PHASE_EMIT_MASK[clampBfi(gr >> 4)]    & phaseBit) ? src[0] : (flr ? flr[0] : 0);
    dst[1] = (PHASE_EMIT_MASK[clampBfi(gr & 0x0Fu)] & phaseBit) ? src[1] : (flr ? flr[1] : 0);
    dst[2] = (PHASE_EMIT_MASK[clampBfi(bw >> 4)]    & phaseBit) ? src[2] : (flr ? flr[2] : 0);
    dst[3] = (PHASE_EMIT_MASK[clampBfi(bw & 0x0Fu)] & phaseBit) ? src[3] : (flr ? flr[3] : 0);
}

void SolverRuntime::renderPixelBFI_RGB_Packed(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* packedBfiMap,
    uint8_t* displayBuffer, uint16_t pixelIndex,
    uint8_t phase)
{
    const uint8_t phaseBit = (uint8_t)(1u << (phase & 0x07u));
    const uint32_t off3 = (uint32_t)pixelIndex * 3u;
    const uint32_t pkOff = (uint32_t)pixelIndex * PACKED_BFI_BYTES_PER_PIXEL;

    const uint8_t* src = upperFrame + off3;
    const uint8_t* flr = floorFrame ? floorFrame + off3 : nullptr;
    uint8_t* dst = displayBuffer + off3;
    const uint8_t gr = packedBfiMap[pkOff];
    const uint8_t bw = packedBfiMap[pkOff + 1];

    dst[0] = (PHASE_EMIT_MASK[clampBfi(gr >> 4)]    & phaseBit) ? src[0] : (flr ? flr[0] : 0);
    dst[1] = (PHASE_EMIT_MASK[clampBfi(gr & 0x0Fu)] & phaseBit) ? src[1] : (flr ? flr[1] : 0);
    dst[2] = (PHASE_EMIT_MASK[clampBfi(bw >> 4)]    & phaseBit) ? src[2] : (flr ? flr[2] : 0);
}

// ============================================================================
// Phase Mode / Tick Management
// ============================================================================

void SolverRuntime::setPhaseMode(PhaseMode mode)
{
    m_phaseMode = mode;
}

void SolverRuntime::setCycleLength(uint8_t len)
{
    if (len < 2) len = 2;
    if (len > MAX_SUPPORTED_CYCLE_LENGTH) len = MAX_SUPPORTED_CYCLE_LENGTH;
    m_cycleLength = len;
}

bool SolverRuntime::advanceTick()
{
    ++m_tick;
    // For FixedMask the cycle boundary is every SOLVER_FIXED_BFI_LEVELS ticks.
    // For Distributed, there is no single global cycle — each BFI level has
    // its own (bfi+1) length, so we report a boundary at the LCM-like
    // interval of SOLVER_FIXED_BFI_LEVELS (matches the legacy cadence).
    // For DistributedGlobal, use the configured m_cycleLength.
    uint8_t cl;
    switch (m_phaseMode) {
        case PhaseMode::DistributedGlobal: cl = m_cycleLength; break;
        default:                           cl = SOLVER_FIXED_BFI_LEVELS; break;
    }
    return (m_tick % cl) == 0;
}

void SolverRuntime::resetTick()
{
    m_tick = 0;
}

bool SolverRuntime::channelActiveOnCurrentTick(uint8_t bfi) const
{
    if (m_phaseMode == PhaseMode::FixedMask)
        return channelOnPhase(bfi, (uint8_t)(m_tick % SOLVER_FIXED_BFI_LEVELS));
    if (m_phaseMode == PhaseMode::Distributed)
        return channelOnTickPerBfi(bfi, m_tick);
    return channelOnTickDistributedGlobal(bfi, m_tick, m_cycleLength);
}

// ============================================================================
// Instance Render (uses internal tick/mode)
// ============================================================================

// Precompute upper/lower decision for each BFI level on the current tick.
static void fillPhaseTable(bool* table, PhaseMode mode, uint32_t tick,
                           uint8_t cycleLength)
{
    for (uint8_t b = 0; b < MAX_SUPPORTED_CYCLE_LENGTH; ++b)
        table[b] = false;

    if (mode == PhaseMode::FixedMask) {
        const uint8_t phase = (uint8_t)(tick % SOLVER_FIXED_BFI_LEVELS);
        const uint8_t phaseBit = (uint8_t)(1u << (phase & 0x07u));
        for (uint8_t b = 0; b < SOLVER_FIXED_BFI_LEVELS; ++b)
            table[b] = (PHASE_EMIT_MASK[b] & phaseBit) != 0;
    } else if (mode == PhaseMode::Distributed) {
        // Per-BFI natural cycle: upper when (tick % (bfi+1)) == 0.
        for (uint8_t b = 0; b < MAX_SUPPORTED_CYCLE_LENGTH; ++b)
            table[b] = channelOnTickPerBfi(b, tick);
    } else {
        // DistributedGlobal: Bresenham across fixed global cycle.
        const uint8_t cl = (cycleLength < MAX_SUPPORTED_CYCLE_LENGTH)
                            ? cycleLength : MAX_SUPPORTED_CYCLE_LENGTH;
        for (uint8_t b = 0; b < cl; ++b)
            table[b] = channelOnTickDistributedGlobal(b, tick, cycleLength);
    }
}

static inline uint8_t clampBfiToTable(uint8_t bfi)
{
    return (bfi < MAX_SUPPORTED_CYCLE_LENGTH)
               ? bfi : (uint8_t)(MAX_SUPPORTED_CYCLE_LENGTH - 1u);
}

void SolverRuntime::renderBFI_RGBW(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* bfiMapG, const uint8_t* bfiMapR,
    const uint8_t* bfiMapB, const uint8_t* bfiMapW,
    uint8_t* displayBuffer, uint16_t pixelCount) const
{
    bool isUp[MAX_SUPPORTED_CYCLE_LENGTH];
    fillPhaseTable(isUp, m_phaseMode, m_tick, m_cycleLength);

    const uint8_t* src = upperFrame;
    const uint8_t* flr = floorFrame;
    uint8_t* dst = displayBuffer;

    for (uint16_t i = 0; i < pixelCount; ++i)
    {
        dst[0] = isUp[clampBfiToTable(bfiMapG[i])] ? src[0] : (flr ? flr[0] : 0);
        dst[1] = isUp[clampBfiToTable(bfiMapR[i])] ? src[1] : (flr ? flr[1] : 0);
        dst[2] = isUp[clampBfiToTable(bfiMapB[i])] ? src[2] : (flr ? flr[2] : 0);
        dst[3] = isUp[clampBfiToTable(bfiMapW[i])] ? src[3] : (flr ? flr[3] : 0);

        src += 4;
        if (flr) flr += 4;
        dst += 4;
    }
}

void SolverRuntime::renderBFI_RGB(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* bfiMapG, const uint8_t* bfiMapR,
    const uint8_t* bfiMapB,
    uint8_t* displayBuffer, uint16_t pixelCount) const
{
    bool isUp[MAX_SUPPORTED_CYCLE_LENGTH];
    fillPhaseTable(isUp, m_phaseMode, m_tick, m_cycleLength);

    const uint8_t* src = upperFrame;
    const uint8_t* flr = floorFrame;
    uint8_t* dst = displayBuffer;

    for (uint16_t i = 0; i < pixelCount; ++i)
    {
        dst[0] = isUp[clampBfiToTable(bfiMapG[i])] ? src[0] : (flr ? flr[0] : 0);
        dst[1] = isUp[clampBfiToTable(bfiMapR[i])] ? src[1] : (flr ? flr[1] : 0);
        dst[2] = isUp[clampBfiToTable(bfiMapB[i])] ? src[2] : (flr ? flr[2] : 0);

        src += 3;
        if (flr) flr += 3;
        dst += 3;
    }
}

void SolverRuntime::renderBFI_RGBW_Packed(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* packedBfiMap,
    uint8_t* displayBuffer, uint16_t pixelCount) const
{
    bool isUp[MAX_SUPPORTED_CYCLE_LENGTH];
    fillPhaseTable(isUp, m_phaseMode, m_tick, m_cycleLength);

    const uint8_t* src = upperFrame;
    const uint8_t* flr = floorFrame;
    uint8_t* dst = displayBuffer;
    const uint8_t* pk = packedBfiMap;

    for (uint16_t i = 0; i < pixelCount; ++i)
    {
        const uint8_t gr = pk[0];
        const uint8_t bw = pk[1];

        dst[0] = isUp[clampBfiToTable(gr >> 4)]       ? src[0] : (flr ? flr[0] : 0);
        dst[1] = isUp[clampBfiToTable(gr & 0x0Fu)]    ? src[1] : (flr ? flr[1] : 0);
        dst[2] = isUp[clampBfiToTable(bw >> 4)]        ? src[2] : (flr ? flr[2] : 0);
        dst[3] = isUp[clampBfiToTable(bw & 0x0Fu)]    ? src[3] : (flr ? flr[3] : 0);

        src += 4;
        if (flr) flr += 4;
        dst += 4;
        pk += PACKED_BFI_BYTES_PER_PIXEL;
    }
}

void SolverRuntime::renderBFI_RGB_Packed(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* packedBfiMap,
    uint8_t* displayBuffer, uint16_t pixelCount) const
{
    bool isUp[MAX_SUPPORTED_CYCLE_LENGTH];
    fillPhaseTable(isUp, m_phaseMode, m_tick, m_cycleLength);

    const uint8_t* src = upperFrame;
    const uint8_t* flr = floorFrame;
    uint8_t* dst = displayBuffer;
    const uint8_t* pk = packedBfiMap;

    for (uint16_t i = 0; i < pixelCount; ++i)
    {
        const uint8_t gr = pk[0];
        const uint8_t bw = pk[1];

        dst[0] = isUp[clampBfiToTable(gr >> 4)]       ? src[0] : (flr ? flr[0] : 0);
        dst[1] = isUp[clampBfiToTable(gr & 0x0Fu)]    ? src[1] : (flr ? flr[1] : 0);
        dst[2] = isUp[clampBfiToTable(bw >> 4)]        ? src[2] : (flr ? flr[2] : 0);

        src += 3;
        if (flr) flr += 3;
        dst += 3;
        pk += PACKED_BFI_BYTES_PER_PIXEL;
    }
}

// ============================================================================
// Indexed Instance Render (single pixel, uses internal tick/mode)
// ============================================================================

void SolverRuntime::renderPixel_RGBW(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* bfiMapG, const uint8_t* bfiMapR,
    const uint8_t* bfiMapB, const uint8_t* bfiMapW,
    uint8_t* displayBuffer, uint16_t pixelIndex) const
{
    bool isUp[MAX_SUPPORTED_CYCLE_LENGTH];
    fillPhaseTable(isUp, m_phaseMode, m_tick, m_cycleLength);

    const uint32_t off = (uint32_t)pixelIndex * 4u;
    const uint8_t* src = upperFrame + off;
    const uint8_t* flr = floorFrame ? floorFrame + off : nullptr;
    uint8_t* dst = displayBuffer + off;

    dst[0] = isUp[clampBfiToTable(bfiMapG[pixelIndex])] ? src[0] : (flr ? flr[0] : 0);
    dst[1] = isUp[clampBfiToTable(bfiMapR[pixelIndex])] ? src[1] : (flr ? flr[1] : 0);
    dst[2] = isUp[clampBfiToTable(bfiMapB[pixelIndex])] ? src[2] : (flr ? flr[2] : 0);
    dst[3] = isUp[clampBfiToTable(bfiMapW[pixelIndex])] ? src[3] : (flr ? flr[3] : 0);
}

void SolverRuntime::renderPixel_RGB(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* bfiMapG, const uint8_t* bfiMapR,
    const uint8_t* bfiMapB,
    uint8_t* displayBuffer, uint16_t pixelIndex) const
{
    bool isUp[MAX_SUPPORTED_CYCLE_LENGTH];
    fillPhaseTable(isUp, m_phaseMode, m_tick, m_cycleLength);

    const uint32_t off = (uint32_t)pixelIndex * 3u;
    const uint8_t* src = upperFrame + off;
    const uint8_t* flr = floorFrame ? floorFrame + off : nullptr;
    uint8_t* dst = displayBuffer + off;

    dst[0] = isUp[clampBfiToTable(bfiMapG[pixelIndex])] ? src[0] : (flr ? flr[0] : 0);
    dst[1] = isUp[clampBfiToTable(bfiMapR[pixelIndex])] ? src[1] : (flr ? flr[1] : 0);
    dst[2] = isUp[clampBfiToTable(bfiMapB[pixelIndex])] ? src[2] : (flr ? flr[2] : 0);
}

void SolverRuntime::renderPixel_RGBW_Packed(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* packedBfiMap,
    uint8_t* displayBuffer, uint16_t pixelIndex) const
{
    bool isUp[MAX_SUPPORTED_CYCLE_LENGTH];
    fillPhaseTable(isUp, m_phaseMode, m_tick, m_cycleLength);

    const uint32_t off4 = (uint32_t)pixelIndex * 4u;
    const uint32_t pkOff = (uint32_t)pixelIndex * PACKED_BFI_BYTES_PER_PIXEL;

    const uint8_t* src = upperFrame + off4;
    const uint8_t* flr = floorFrame ? floorFrame + off4 : nullptr;
    uint8_t* dst = displayBuffer + off4;
    const uint8_t gr = packedBfiMap[pkOff];
    const uint8_t bw = packedBfiMap[pkOff + 1];

    dst[0] = isUp[clampBfiToTable(gr >> 4)]    ? src[0] : (flr ? flr[0] : 0);
    dst[1] = isUp[clampBfiToTable(gr & 0x0Fu)] ? src[1] : (flr ? flr[1] : 0);
    dst[2] = isUp[clampBfiToTable(bw >> 4)]    ? src[2] : (flr ? flr[2] : 0);
    dst[3] = isUp[clampBfiToTable(bw & 0x0Fu)] ? src[3] : (flr ? flr[3] : 0);
}

void SolverRuntime::renderPixel_RGB_Packed(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const uint8_t* packedBfiMap,
    uint8_t* displayBuffer, uint16_t pixelIndex) const
{
    bool isUp[MAX_SUPPORTED_CYCLE_LENGTH];
    fillPhaseTable(isUp, m_phaseMode, m_tick, m_cycleLength);

    const uint32_t off3 = (uint32_t)pixelIndex * 3u;
    const uint32_t pkOff = (uint32_t)pixelIndex * PACKED_BFI_BYTES_PER_PIXEL;

    const uint8_t* src = upperFrame + off3;
    const uint8_t* flr = floorFrame ? floorFrame + off3 : nullptr;
    uint8_t* dst = displayBuffer + off3;
    const uint8_t gr = packedBfiMap[pkOff];
    const uint8_t bw = packedBfiMap[pkOff + 1];

    dst[0] = isUp[clampBfiToTable(gr >> 4)]    ? src[0] : (flr ? flr[0] : 0);
    dst[1] = isUp[clampBfiToTable(gr & 0x0Fu)] ? src[1] : (flr ? flr[1] : 0);
    dst[2] = isUp[clampBfiToTable(bw >> 4)]    ? src[2] : (flr ? flr[2] : 0);
}

// ============================================================================
// LUT Header Dump
// ============================================================================

static void dumpLUTU8(Print& out, const char* name, const uint8_t* lut,
                      uint16_t lutSize, uint8_t channels)
{
    out.print("static const uint8_t ");
    out.print(name);
    out.print("[4][");
    out.print((unsigned)lutSize);
    out.println("] PROGMEM = {");
    for (uint8_t ch = 0; ch < channels; ++ch)
    {
        out.println("  {");
        const size_t offset = (size_t)ch * (size_t)lutSize;
        for (size_t i = 0; i < lutSize; ++i)
        {
            if ((i % 16u) == 0u) out.print("    ");
            out.print(lut[offset + i]);
            if (i + 1u != lutSize) out.print(", ");
            if ((i % 16u) == 15u) out.println();
        }
        out.println("  },");
    }
    out.println("};");
    out.println();
}

static void dumpLUTU16(Print& out, const char* name, const uint16_t* lut,
                       uint16_t lutSize, uint8_t channels)
{
    out.print("static const uint16_t ");
    out.print(name);
    out.print("[4][");
    out.print((unsigned)lutSize);
    out.println("] PROGMEM = {");
    for (uint8_t ch = 0; ch < channels; ++ch)
    {
        out.println("  {");
        const size_t offset = (size_t)ch * (size_t)lutSize;
        for (size_t i = 0; i < lutSize; ++i)
        {
            if ((i % 12u) == 0u) out.print("    ");
            out.print(lut[offset + i]);
            if (i + 1u != lutSize) out.print(", ");
            if ((i % 12u) == 11u) out.println();
        }
        out.println("  },");
    }
    out.println("};");
    out.println();
}

void SolverRuntime::dumpLUTHeader(Print& out) const
{
    out.println("// Auto-generated precomputed solver LUTs");
    out.println("// Save as solver_precomputed_luts.h, build with USE_PRECOMPUTED_LUTS");
    out.println("#pragma once");
    out.println("#include <Arduino.h>");
    out.println();
    out.println("namespace TemporalBFIPrecomputedSolverLUTs {");
    out.print("static constexpr uint8_t SOLVER_FIXED_BFI_LEVELS = ");
    out.print((unsigned)SOLVER_FIXED_BFI_LEVELS);
    out.println(";");
    out.print("static constexpr uint32_t SOLVER_LUT_SIZE = ");
    out.print((unsigned long)m_lutSize);
    out.println("u;");
    out.println();
    out.println("#define TEMPORAL_BFI_PRECOMPUTED_HAS_LUT_SIZE 1");
    if (m_floorLUT)
        out.println("#define TEMPORAL_BFI_PRECOMPUTED_HAS_FLOOR_LUT 1");
    out.println();

    if (m_bfiLUT)
        dumpLUTU8(out, "solverBFILUT", m_bfiLUT, m_lutSize, 4);
    if (m_valueLUT)
        dumpLUTU8(out, "solverValueLUT", m_valueLUT, m_lutSize, 4);
    if (m_floorLUT)
        dumpLUTU8(out, "solverValueFloorLUT", m_floorLUT, m_lutSize, 4);
    if (m_outputQ16LUT)
        dumpLUTU16(out, "solverOutputQ16LUT", m_outputQ16LUT, m_lutSize, 4);

    out.println("} // namespace TemporalBFIPrecomputedSolverLUTs");
    out.println();
}

} // namespace TemporalBFI