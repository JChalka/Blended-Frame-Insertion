#include "TemporalBFI.h"
#include "CubeLUT3D.h"

namespace TemporalBFI {

static inline uint8_t mapSolverChannel(uint8_t requestedChannel,
                                       uint8_t activeChannels,
                                       FifthChannelSolveMode mode)
{
    if (activeChannels == 0) return 0;
    uint8_t ch = requestedChannel;
    if (ch >= activeChannels)
        ch = (uint8_t)(activeChannels - 1u);

    if (mode == FifthChannelSolveMode::EmulateFromW && ch == 4)
        return 3;
    return ch;
}

// Render/commit and phase/tick dispatch implementations live in
// TemporalBFIRenderCommit.cpp.

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

void SolverRuntime::setSolverLUTMode(SolverLUTMode mode)
{
    m_solverLUTMode = mode;
}

void SolverRuntime::precompute(SolverFn fn, uint8_t numChannels)
{
    if (!fn || !m_valueLUT || !m_bfiLUT || m_lutSize < 2u) return;

    uint8_t channelCount = numChannels;
    if (channelCount == 0) return;
    if (channelCount > SOLVER_MAX_CHANNELS) channelCount = SOLVER_MAX_CHANNELS;
    m_numChannels = channelCount;

    const uint8_t storageChannels = solverLUTStorageChannels();

    for (uint8_t ch = 0; ch < storageChannels; ++ch)
    {
        const size_t offset = (size_t)ch * (size_t)m_lutSize;
        const uint8_t solverChannel = (m_solverLUTMode == SolverLUTMode::Shared) ? 0u : ch;
        for (size_t i = 0; i < m_lutSize; ++i)
        {
            const uint16_t q16 = (uint16_t)(((uint32_t)i * 65535u) / (uint32_t)(m_lutSize - 1u));
            const auto s = fn(q16, solverChannel, m_cfg);
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
    uint8_t channelCount = numChannels;
    if (channelCount == 0) return;
    if (channelCount > SOLVER_MAX_CHANNELS) channelCount = SOLVER_MAX_CHANNELS;
    m_numChannels = channelCount;

    const uint8_t storageChannels = solverLUTStorageChannels();

    const size_t totalEntries = (size_t)storageChannels * (size_t)m_lutSize;

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

    if (m_numChannels == 0) return out;
    channel = mapSolverChannel(channel, m_numChannels, m_fifthChannelSolveMode);

    const uint8_t storageChannel = (m_solverLUTMode == SolverLUTMode::Shared) ? 0u : channel;

    const size_t idx = solverLutIndex(q16);
    const size_t offset = (size_t)storageChannel * (size_t)m_lutSize + idx;

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

void SolverRuntime::setTransferCurve(const uint16_t* curve, uint16_t bucketCount)
{
    m_curveShared = curve;
    m_curveBucketCount = bucketCount;
    m_transferCurveMode = TransferCurveMode::Single;
}

void SolverRuntime::setTransferCurve(const uint16_t* curveR, const uint16_t* curveG,
                                     const uint16_t* curveB, const uint16_t* curveW,
                                     uint16_t bucketCount)
{
    setTransferCurve(curveR, curveG, curveB, curveW, bucketCount, nullptr);
}

void SolverRuntime::setTransferCurve(const uint16_t* curveR, const uint16_t* curveG,
                                     const uint16_t* curveB, const uint16_t* curveW,
                                     uint16_t bucketCount, const uint16_t* curveW2)
{
    m_curveShared = nullptr;
    m_curveR = curveR;
    m_curveG = curveG;
    m_curveB = curveB;
    m_curveW = curveW;
    m_curveW2 = curveW2;
    m_curveBucketCount = bucketCount;
    m_transferCurveMode = TransferCurveMode::LegacyPerChannel;
}

void SolverRuntime::setTransferCurveMode(TransferCurveMode mode)
{
    m_transferCurveMode = mode;
}

void SolverRuntime::setTransferCurveEnabled(bool enabled)
{
    m_transferCurveEnabled = enabled;
}

uint16_t SolverRuntime::applyTransferCurve(uint16_t q16, uint8_t channel) const
{
    if (!m_transferCurveEnabled || m_curveBucketCount == 0) return q16;

    if (m_transferCurveMode == TransferCurveMode::Single) {
        if (!m_curveShared) return q16;
        const size_t idxShared = lutIndexForSize(q16, m_curveBucketCount);
        return m_curveShared[idxShared];
    }

    channel = mapSolverChannel(channel, SOLVER_MAX_CHANNELS, m_fifthChannelSolveMode);

    const uint16_t* curve = nullptr;
    switch (channel)
    {
        case 0: curve = m_curveG; break;
        case 1: curve = m_curveR; break;
        case 2: curve = m_curveB; break;
        case 3: curve = m_curveW; break;
        default: curve = m_curveW2 ? m_curveW2 : m_curveW; break;
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
    channel = mapSolverChannel(channel, SOLVER_MAX_CHANNELS, m_fifthChannelSolveMode);
    return m_calibrationFn(q16, channel);
}

void SolverRuntime::setFifthChannelSolveMode(FifthChannelSolveMode mode)
{
    m_fifthChannelSolveMode = mode;
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
    const RgbwwTargets rgbww = applyCubeLUT3D_RGBWW(rQ16, gQ16, bQ16);
    return {rgbww.rQ16, rgbww.gQ16, rgbww.bQ16, rgbww.w1Q16};
}

RgbwwTargets SolverRuntime::applyCubeLUT3D_RGBWW(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const
{
    if (!m_cubeLUTEnabled || !m_cubeLUT || !m_cubeLUT->isValid()) {
        // Passthrough — no cube loaded or disabled.
        return {rQ16, gQ16, bQ16, 0, 0};
    }
    return m_cubeLUT->lookupRgbww(rQ16, gQ16, bQ16);
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

RgbwwTargets SolverRuntime::extractRgbwwEmulated(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) const
{
    const RgbwTargets rgbw = extractRgbw(rQ16, gQ16, bQ16);
    const uint16_t w1 = (uint16_t)(rgbw.wQ16 / 2u);
    const uint16_t w2 = (uint16_t)(rgbw.wQ16 - w1);
    return {rgbw.rQ16, rgbw.gQ16, rgbw.bQ16, w1, w2};
}

EncodedState SolverRuntime::solveWhiteEmulated(uint16_t q16) const
{
    return solve(q16, 3);
}

// Render/commit and phase/tick dispatch implementations live in
// TemporalBFIRenderCommit.cpp.

// ============================================================================
// LUT Header Dump
// ============================================================================

static void dumpLUTU8(Print& out, const char* name, const uint8_t* lut,
                      uint16_t lutSize, uint8_t channels)
{
    out.print("static const uint8_t ");
    out.print(name);
    out.print("[");
    out.print((unsigned)channels);
    out.print("][");
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
    out.print("[");
    out.print((unsigned)channels);
    out.print("][");
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
    out.print("#define TEMPORAL_BFI_PRECOMPUTED_SOLVER_LUT_SHARED ");
    out.println((m_solverLUTMode == SolverLUTMode::Shared) ? 1 : 0);
    if (m_floorLUT)
        out.println("#define TEMPORAL_BFI_PRECOMPUTED_HAS_FLOOR_LUT 1");
    out.println();

    const uint8_t channelCount = solverLUTStorageChannels();

    if (m_bfiLUT)
        dumpLUTU8(out, "solverBFILUT", m_bfiLUT, m_lutSize, channelCount);
    if (m_valueLUT)
        dumpLUTU8(out, "solverValueLUT", m_valueLUT, m_lutSize, channelCount);
    if (m_floorLUT)
        dumpLUTU8(out, "solverValueFloorLUT", m_floorLUT, m_lutSize, channelCount);
    if (m_outputQ16LUT)
        dumpLUTU16(out, "solverOutputQ16LUT", m_outputQ16LUT, m_lutSize, channelCount);

    out.println("} // namespace TemporalBFIPrecomputedSolverLUTs");
    out.println();
}

} // namespace TemporalBFI