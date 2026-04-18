// LoadPrecomputedDemo.ino
// Demonstrates loading precomputed solver LUTs from an offline-generated
// header — no solver or raw ladder data is compiled in.
//
// Usage:
// 1. Generate a precomputed header with the Python tools:
//      python temporal_lut_tools.py export-precomputed-solver-luts \
//          --solver-header <your_solver_header.h> \
//          --solver-lut-size 4096 \
//          --output solver_precomputed_luts.h
//
// 2. Place solver_precomputed_luts.h next to this sketch (or in src/).
//
// 3. Build and upload.  The solver LUTs are loaded from flash at startup
//    with zero on-device computation time.

#include <Arduino.h>

// Tell the library we only need the precomputed path — no solver, no ladders.
#define TEMPORAL_BFI_PRECOMPUTED_ONLY

#include <TemporalBFI.h>

// Include the generated precomputed header BEFORE TemporalBFIRuntime.h
// so that SOLVER_LUT_SIZE is picked up from the precomputed namespace.
#include "solver_precomputed_luts_4096_rgbw.h"

#include <TemporalBFIRuntime.h>

using namespace TemporalBFI;

static constexpr uint16_t LUT_SIZE = TemporalBFIRuntime::SOLVER_LUT_SIZE;
static constexpr uint8_t  NUM_CH   = TemporalBFIPrecomputedSolverLUTs::NUM_CHANNELS;

// Runtime buffers — sized to match the precomputed header.
static uint8_t  solverValueLUT[NUM_CH * LUT_SIZE];
static uint8_t  solverBFILUT  [NUM_CH * LUT_SIZE];
static uint8_t  solverFloorLUT[NUM_CH * LUT_SIZE];

static SolverRuntime solver;

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000) {}

    Serial.println("LoadPrecomputedDemo");
    Serial.print("LUT size per channel: "); Serial.println(LUT_SIZE);
    Serial.print("Channels:             "); Serial.println(NUM_CH);

    // Attach runtime buffers.
    solver.attachLUTs(solverValueLUT, solverBFILUT, solverFloorLUT,
                      nullptr, LUT_SIZE);

    // Load from the precomputed flash arrays — no on-device computation.
    uint32_t t0 = micros();
    solver.loadPrecomputed(
        (const uint8_t*)TemporalBFIPrecomputedSolverLUTs::solverValueLUT,
        (const uint8_t*)TemporalBFIPrecomputedSolverLUTs::solverBFILUT,
        (const uint8_t*)TemporalBFIPrecomputedSolverLUTs::solverValueFloorLUT,
        nullptr,
        NUM_CH,
        TemporalBFIPrecomputedSolverLUTs::SOLVER_LUT_SIZE);
    uint32_t elapsed = micros() - t0;

    Serial.print("Load time:            "); Serial.print(elapsed); Serial.println(" us");

    size_t totalBytes = (size_t)NUM_CH * LUT_SIZE * 3u;  // value + bfi + floor
    Serial.print("Total LUT memory:     "); Serial.print((unsigned long)totalBytes); Serial.println(" bytes");

    // Quick sanity: solve a mid-range value on channel 0 (G).
    EncodedState st = solver.solve(32768, 0);
    Serial.print("solve(32768, ch0): value="); Serial.print(st.value);
    Serial.print(" bfi="); Serial.print(st.bfi);
    Serial.print(" floor="); Serial.println(st.lowerValue);

    // Benchmark 1000 LUT solves.
    volatile uint8_t sink = 0;
    uint32_t t1 = micros();
    for (uint16_t i = 0; i < 1000; ++i) {
        EncodedState r = solver.solve(32768, 1);
        sink = r.value;
    }
    uint32_t solveTime = micros() - t1;
    (void)sink;
    Serial.print("1000 LUT solves:      "); Serial.print(solveTime); Serial.println(" us");

    Serial.println("Done.");
}

void loop() {}
