// Backward-compatibility shim.  All runtime helpers now live in TemporalBFI.h.
// New code should #include <TemporalBFI.h> directly.
//
// Precomputed-only mode: define TEMPORAL_BFI_PRECOMPUTED_ONLY and include the
// precomputed LUT header *before* this file.  The solver and raw ladder data
// are then completely excluded — only loadPrecomputed() is needed at runtime.
#pragma once
#include "TemporalBFI.h"

#if !defined(TEMPORAL_BFI_PRECOMPUTED_ONLY)
#include "TemporalTrue16BFIPolicySolver_per_bfi_v3.h"
#endif

namespace TemporalBFIRuntime {

static constexpr uint8_t SOLVER_FIXED_BFI_LEVELS = TemporalBFI::SOLVER_FIXED_BFI_LEVELS;

#if defined(TEMPORAL_BFI_PRECOMPUTED_ONLY)

// In precomputed-only mode SOLVER_LUT_SIZE comes from the precomputed header.
#if !defined(TEMPORAL_BFI_PRECOMPUTED_HAS_LUT_SIZE)
#error "TEMPORAL_BFI_PRECOMPUTED_ONLY requires the precomputed LUT header (which defines TEMPORAL_BFI_PRECOMPUTED_HAS_LUT_SIZE) to be included first."
#endif
static constexpr uint16_t SOLVER_LUT_SIZE = TemporalBFIPrecomputedSolverLUTs::SOLVER_LUT_SIZE;
static_assert(SOLVER_LUT_SIZE >= 2u, "Precomputed SOLVER_LUT_SIZE must be at least 2");

#else // !TEMPORAL_BFI_PRECOMPUTED_ONLY

static constexpr uint16_t maxU16Constexpr(uint16_t a, uint16_t b)
{
    return (a > b) ? a : b;
}

static constexpr uint16_t derivedSolverLutSizeFromLadders()
{
    return maxU16Constexpr(
        maxU16Constexpr(TemporalBFIRuntimeLUT::LADDER_R_COUNT, TemporalBFIRuntimeLUT::LADDER_G_COUNT),
        maxU16Constexpr(TemporalBFIRuntimeLUT::LADDER_B_COUNT, TemporalBFIRuntimeLUT::LADDER_W_COUNT));
}

static constexpr uint16_t SOLVER_LUT_SIZE = derivedSolverLutSizeFromLadders();
static_assert(SOLVER_LUT_SIZE >= 2u, "Derived solver LUT size must be at least 2");

#endif // TEMPORAL_BFI_PRECOMPUTED_ONLY

static constexpr uint8_t PHASE_EMIT_MASK[SOLVER_FIXED_BFI_LEVELS] = {0x1F, 0x1B, 0x15, 0x09, 0x01};

static inline bool channelOnThisTick(uint8_t bfi, uint32_t tick, uint8_t cycleLen)
{
    const uint8_t phase = (uint8_t)(tick % (uint32_t)cycleLen);
    return TemporalBFI::channelOnPhase(bfi, phase);
}

static inline size_t solverLutIndexFromQ16(uint16_t q16, uint16_t lutSize)
{
    return TemporalBFI::lutIndexForSize(q16, lutSize);
}

static inline size_t solverLutIndexFromQ16(uint16_t q16)
{
    return TemporalBFI::lutIndexForSize(q16, SOLVER_LUT_SIZE);
}

} // namespace TemporalBFIRuntime
