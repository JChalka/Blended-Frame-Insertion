#pragma once
#include <Arduino.h>
#include <TemporalBFI.h>

#if defined(USER_DEFINED_TEMPORAL_SOLVER_HEADER)

#else
#include "temporal_runtime_solver_header.h"
#endif // USER_DEFINED_TEMPORAL_SOLVER_HEADER

#if defined(TEMPORAL_TRUE16_USER_PROVIDED_CALIBRATION)

#else

#if defined(TEMPORAL_TRUE16_ENABLE_INPUT_Q16_CALIBRATION)
#include "calibration_profile_true16.h"
#else
#include "calibration_profile_finenearneutral.h"
#endif // TEMPORAL_TRUE16_ENABLE_INPUT_Q16_CALIBRATION

#endif // TEMPORAL_TRUE16_USER_PROVIDED_CALIBRATION

namespace TemporalTrue16BFIPolicySolver {

// Alias canonical types from TemporalBFI — single source of truth.
using EncodedState = TemporalBFI::EncodedState;
using PolicyConfig = TemporalBFI::PolicyConfig;

static inline uint16_t calibrateInputQ16ForSolver(uint16_t inputQ16, uint8_t channel, bool enableCalibration = true)
{
    if (!enableCalibration)
    {
        (void)channel;
        return inputQ16;
    }
#if defined(TEMPORAL_TRUE16_ENABLE_INPUT_Q16_CALIBRATION)
    const size_t lutSize = size_t(TemporalBFICalibrationTrue16::LUT_SIZE);
    if (lutSize == 0u) return inputQ16;

    const uint16_t* lut = nullptr;
    switch (channel)
    {
        case 0: lut = TemporalBFICalibrationTrue16::LUT_G_16_TO_16; break;
        case 1: lut = TemporalBFICalibrationTrue16::LUT_R_16_TO_16; break;
        case 2: lut = TemporalBFICalibrationTrue16::LUT_B_16_TO_16; break;
        default: lut = TemporalBFICalibrationTrue16::LUT_W_16_TO_16; break;
    }

    if (!lut) return inputQ16;

    size_t idx = (size_t)((uint32_t(inputQ16) * uint32_t(lutSize - 1u) + 32767u) / 65535u);
    if (idx >= lutSize) idx = lutSize - 1u;
    return lut[idx];
#else
    (void)channel;
    return inputQ16;
#endif
}

static inline const TemporalBFI::LadderEntry* ladderForChannel(uint8_t channel, uint16_t& count)
{
    switch (channel)
    {
        case 0: count = TemporalBFIRuntimeLUT::LADDER_G_COUNT; return TemporalBFIRuntimeLUT::LADDER_G;
        case 1: count = TemporalBFIRuntimeLUT::LADDER_R_COUNT; return TemporalBFIRuntimeLUT::LADDER_R;
        case 2: count = TemporalBFIRuntimeLUT::LADDER_B_COUNT; return TemporalBFIRuntimeLUT::LADDER_B;
        default: count = TemporalBFIRuntimeLUT::LADDER_W_COUNT; return TemporalBFIRuntimeLUT::LADDER_W;
    }
}

static inline const uint8_t* lowerLadderForChannel(uint8_t channel, uint16_t& count)
{
    switch (channel)
    {
        case 0: count = TemporalBFIRuntimeLUT::LADDER_G_COUNT; return TemporalBFIRuntimeLUT::LADDER_G_LOWER;
        case 1: count = TemporalBFIRuntimeLUT::LADDER_R_COUNT; return TemporalBFIRuntimeLUT::LADDER_R_LOWER;
        case 2: count = TemporalBFIRuntimeLUT::LADDER_B_COUNT; return TemporalBFIRuntimeLUT::LADDER_B_LOWER;
        default: count = TemporalBFIRuntimeLUT::LADDER_W_COUNT; return TemporalBFIRuntimeLUT::LADDER_W_LOWER;
    }
}

static inline uint16_t absDiffU16(uint16_t a, uint16_t b)
{
    return (a > b) ? uint16_t(a - b) : uint16_t(b - a);
}

static inline uint16_t allowedErrorQ16(uint16_t targetQ16, const PolicyConfig& cfg)
{
    uint16_t rel = (cfg.relativeErrorDivisor > 0) ? uint16_t(targetQ16 / cfg.relativeErrorDivisor) : 0;
    return (rel > cfg.minErrorQ16) ? rel : cfg.minErrorQ16;
}

static inline bool passesResolutionGuard(uint8_t input8Approx, uint8_t candidateValue, const PolicyConfig& cfg)
{
    if (input8Approx == 0) return candidateValue == 0;

    uint16_t minAllowedByRatio =
        (uint16_t(input8Approx) * cfg.minValueRatioNumerator) / cfg.minValueRatioDenominator;
    if (candidateValue < minAllowedByRatio) return false;

    if (input8Approx <= cfg.lowEndProtectThreshold)
    {
        uint8_t minAllowedLow = (input8Approx > cfg.lowEndMaxDrop) ? uint8_t(input8Approx - cfg.lowEndMaxDrop) : 0;
        if (candidateValue < minAllowedLow) return false;
    }
    return true;
}

static inline bool passesBaselinePolicy(uint8_t input8Approx, uint8_t candidateBFI, const PolicyConfig& cfg)
{
    if (candidateBFI > cfg.maxBFI) return false;
    if (cfg.preferredMinBFI == 0) return true;
    if (input8Approx >= cfg.highlightBypassStart) return true;
    return candidateBFI >= cfg.preferredMinBFI;
}

static inline uint8_t resolveLowerValueFromLadderIndex(
    uint8_t channel,
    uint16_t ladderIndex,
    uint8_t fallbackValue)
{
    uint16_t count = 0;
    const uint8_t* lower = lowerLadderForChannel(channel, count);
    if (!lower || ladderIndex >= count)
        return fallbackValue;
    return lower[ladderIndex];
}

static inline EncodedState solveStateFromQ16Internal(
    uint16_t targetQ16,
    uint8_t input8Approx,
    uint8_t channel,
    const PolicyConfig& cfg)
{
    EncodedState out{0, 0, 0, 0, 0};
    if (targetQ16 == 0 || input8Approx == 0) return out;

    uint16_t count = 0;
    const TemporalBFI::LadderEntry* ladder = ladderForChannel(channel, count);
    if (!ladder || count == 0) return out;

    const uint16_t tolerance = allowedErrorQ16(targetQ16, cfg);

    bool foundInTolerance = false;
    uint16_t bestIdx = 0;
    uint16_t bestErr = 0xFFFFu;

    for (uint16_t i = 0; i < count; ++i)
    {
        const auto& e = ladder[i];
        if (e.value == 0) continue;
        if (!passesBaselinePolicy(input8Approx, e.bfi, cfg)) continue;
        if (!passesResolutionGuard(input8Approx, e.value, cfg)) continue;

        uint16_t err = absDiffU16(e.outputQ16, targetQ16);
        if (err > tolerance) continue;

        if (!foundInTolerance)
        {
            foundInTolerance = true;
            bestIdx = i;
            bestErr = err;
            continue;
        }

        const auto& best = ladder[bestIdx];

        if (err < bestErr)
        {
            bestIdx = i;
            bestErr = err;
            continue;
        }
        if (err > bestErr) continue;

        if (cfg.preferHigherBFI)
        {
            if (e.bfi > best.bfi) { bestIdx = i; continue; }
            if (e.bfi < best.bfi) continue;
        }

        if (e.value > best.value) {
            bestIdx = i;
            bestErr = err;
            continue;
        }

        if (e.outputQ16 > best.outputQ16) {
            bestIdx = i;
            bestErr = err;
        }
    }

    if (foundInTolerance)
    {
        const auto& best = ladder[bestIdx];
        out.value = best.value;
        out.bfi = best.bfi;
        out.lowerValue = resolveLowerValueFromLadderIndex(channel, bestIdx, best.value);
        out.outputQ16 = best.outputQ16;
        out.ladderIndex = bestIdx;
        return out;
    }

    bool foundFloor = false;
    uint16_t bestFloorQ16 = 0;
    bestIdx = 0;

    for (uint16_t i = 0; i < count; ++i)
    {
        const auto& e = ladder[i];
        if (!passesBaselinePolicy(input8Approx, e.bfi, cfg)) continue;
        if (!passesResolutionGuard(input8Approx, e.value, cfg)) continue;

        if (e.outputQ16 > targetQ16) continue;

        if (!foundFloor || e.outputQ16 > bestFloorQ16)
        {
            foundFloor = true;
            bestFloorQ16 = e.outputQ16;
            bestIdx = i;
            continue;
        }

        if (e.outputQ16 == bestFloorQ16)
        {
            const auto& best = ladder[bestIdx];
            if (cfg.preferHigherBFI)
            {
                if (e.bfi > best.bfi) { bestIdx = i; continue; }
                if (e.bfi < best.bfi) continue;
            }
            if (e.value > best.value) bestIdx = i;
        }
    }

    if (foundFloor)
    {
        const auto& best = ladder[bestIdx];
        out.value = best.value;
        out.bfi = best.bfi;
        out.lowerValue = resolveLowerValueFromLadderIndex(channel, bestIdx, best.value);
        out.outputQ16 = best.outputQ16;
        out.ladderIndex = bestIdx;
        return out;
    }

    uint32_t nearestErr = 0xFFFFFFFFu;
    bestIdx = 0;

    for (uint16_t i = 0; i < count; ++i)
    {
        const auto& e = ladder[i];
        if (e.bfi > cfg.maxBFI) continue;

        uint32_t err = (e.outputQ16 > targetQ16)
                         ? uint32_t(e.outputQ16 - targetQ16)
                         : uint32_t(targetQ16 - e.outputQ16);
        if (err < nearestErr)
        {
            nearestErr = err;
            bestIdx = i;
        }
        else if (err == nearestErr)
        {
            const auto& best = ladder[bestIdx];
            if (cfg.preferHigherBFI)
            {
                if (e.bfi > best.bfi) { bestIdx = i; continue; }
                if (e.bfi < best.bfi) continue;
            }
            if (e.value > best.value) bestIdx = i;
        }
    }

    const auto& best = ladder[bestIdx];
    out.value = best.value;
    out.bfi = best.bfi;
    out.lowerValue = resolveLowerValueFromLadderIndex(channel, bestIdx, best.value);
    out.outputQ16 = best.outputQ16;
    out.ladderIndex = bestIdx;
    return out;
}

static inline EncodedState encodeStateFrom16(uint16_t q16, uint8_t channel, const PolicyConfig& cfg = PolicyConfig())
{
    if (q16 == 0) return {0,0,0,0,0};
    uint16_t targetQ16 = calibrateInputQ16ForSolver(q16, channel, cfg.enableInputQ16Calibration);
    uint8_t input8Approx = (uint8_t)((uint32_t(targetQ16) * 255u + 32767u) / 65535u);
    if (input8Approx == 0) input8Approx = 1;
    return solveStateFromQ16Internal(
        targetQ16,
        input8Approx,
        channel,
        cfg
    );
}

} // namespace TemporalTrue16BFIPolicySolver