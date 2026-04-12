// PrecomputeDemo.ino
// Demonstrates precomputing solver LUTs at startup and optionally
// dumping them as a header for compile-time embedding.

#include <Arduino.h>
#include <TemporalBFI.h>
#include <TemporalBFIRuntime.h>

using namespace TemporalBFI;

static constexpr uint16_t LUT_SIZE = TemporalBFIRuntime::SOLVER_LUT_SIZE;

static uint8_t  solverValueLUT    [4 * LUT_SIZE];
static uint8_t  solverBFILUT      [4 * LUT_SIZE];
static uint8_t  solverFloorLUT    [4 * LUT_SIZE];
static uint16_t solverOutputQ16LUT[4 * LUT_SIZE];

static SolverRuntime solver;

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000) {}

    solver.attachLUTs(solverValueLUT, solverBFILUT, solverFloorLUT,
                      solverOutputQ16LUT, LUT_SIZE);

    // Time the precomputation pass.
    uint32_t t0 = micros();
    solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16);
    uint32_t elapsed = micros() - t0;

    Serial.println("PrecomputeDemo");
    Serial.print("LUT size per channel: "); Serial.println(LUT_SIZE);
    Serial.print("Total LUT memory:     ");
    Serial.print((unsigned long)(4u * LUT_SIZE) * (1u + 1u + 1u) +
                 (unsigned long)(4u * LUT_SIZE) * 2u);
    Serial.println(" bytes");
    Serial.print("Precompute time:      ");
    Serial.print(elapsed); Serial.println(" us");

    // Benchmark 1000 LUT solves.
    volatile EncodedState dummy{};
    uint32_t t1 = micros();
    for (uint16_t i = 0; i < 1000; ++i) {
        dummy = solver.solve(32768, 1);
    }
    uint32_t solveTime = micros() - t1;
    (void)dummy;

    Serial.print("1000 LUT solves:      ");
    Serial.print(solveTime); Serial.println(" us");

    // Uncomment the line below to dump a precomputed header to Serial.
    // Save the output as solver_precomputed_luts.h.
    // solver.dumpLUTHeader(Serial);

    Serial.println("Done.");
}

void loop() {}
