// PrecomputeDemo.ino
// Demonstrates precomputing solver LUTs at startup and optionally
// dumping them as a header for compile-time embedding.

#include <Arduino.h>
#include <TemporalBFI.h>
#include <TemporalBFIRuntime.h>

using namespace TemporalBFI;

static constexpr uint16_t LUT_SIZE = TemporalBFIRuntime::SOLVER_LUT_SIZE;
static constexpr uint8_t NUM_CH = 4;

static uint8_t  solverValueLUT    [NUM_CH * LUT_SIZE];
static uint8_t  solverBFILUT      [NUM_CH * LUT_SIZE];
static uint8_t  solverFloorLUT    [NUM_CH * LUT_SIZE];
static uint16_t solverOutputQ16LUT[NUM_CH * LUT_SIZE];

static SolverRuntime solver;

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000) {}

    solver.attachLUTs(solverValueLUT, solverBFILUT, solverFloorLUT,
                      solverOutputQ16LUT, LUT_SIZE);

    // Keep policy explicit for precomputed-header workflows.
    solver.setLedColorOrder(LedColorOrder::GRBW);
    solver.setSolverLUTMode(SolverLUTMode::PerChannel);

    // Time the precomputation pass.
    uint32_t t0 = micros();
    solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16, NUM_CH);
    uint32_t elapsed = micros() - t0;

    Serial.println("PrecomputeDemo");
    Serial.print("LUT size per channel: "); Serial.println(LUT_SIZE);
    Serial.print("Total LUT memory:     ");
    Serial.print((unsigned long)(NUM_CH * LUT_SIZE) * (1u + 1u + 1u) +
                 (unsigned long)(NUM_CH * LUT_SIZE) * 2u);
    Serial.println(" bytes");
    Serial.print("Precompute time:      ");
    Serial.print(elapsed); Serial.println(" us");

    // Benchmark 1000 LUT solves.
    volatile uint8_t solveSink = 0;
    uint32_t t1 = micros();
    for (uint16_t i = 0; i < 1000; ++i) {
        EncodedState result = solver.solve(32768, 1);
        solveSink = result.value;
    }
    uint32_t solveTime = micros() - t1;
    (void)solveSink;

    Serial.print("1000 LUT solves:      ");
    Serial.print(solveTime); Serial.println(" us");

    // Uncomment the line below to dump a precomputed header to Serial.
    // Save the output as solver_precomputed_luts.h.
    // solver.dumpLUTHeader(Serial);

    Serial.println("Done.");
}

void loop() {}
