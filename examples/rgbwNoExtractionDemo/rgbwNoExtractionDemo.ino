// rgbwNoExtractionDemo.ino
// Demonstrates direct RGBW input without white-channel extraction.
// Use this when the source signal already provides a separate W channel.

#include <Arduino.h>
#include <TemporalBFI.h>
#include <TemporalBFIRuntime.h>

using namespace TemporalBFI;

static constexpr uint16_t LED_COUNT = 4;
static constexpr uint8_t  CYCLE_LEN = 5;
static constexpr uint16_t LUT_SIZE  = TemporalBFIRuntime::SOLVER_LUT_SIZE;

static uint8_t  solverValueLUT[4 * LUT_SIZE];
static uint8_t  solverBFILUT  [4 * LUT_SIZE];
static uint8_t  solverFloorLUT[4 * LUT_SIZE];

static uint8_t upperFrame[LED_COUNT * 4] = {0};
static uint8_t floorFrame[LED_COUNT * 4] = {0};
static uint8_t displayBuf[LED_COUNT * 4] = {0};
static uint8_t bfiG[LED_COUNT] = {0};
static uint8_t bfiR[LED_COUNT] = {0};
static uint8_t bfiB[LED_COUNT] = {0};
static uint8_t bfiW[LED_COUNT] = {0};

static SolverRuntime solver;
static uint8_t phase = 0;

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000) {}

    solver.attachLUTs(solverValueLUT, solverBFILUT, solverFloorLUT, nullptr, LUT_SIZE);
    solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16);

    // Direct RGBW input — no extractRgbw() needed.
    const uint16_t rQ16 = 30000;
    const uint16_t gQ16 = 25000;
    const uint16_t bQ16 = 10000;
    const uint16_t wQ16 = 20000;

    // Optionally cap the white channel.
    solver.setWhiteLimit(200);  // ~78 %
    RgbwTargets t = solver.applyWhiteLimit(rQ16, gQ16, bQ16, wQ16);

    // Solve each channel.
    EncodedState stG = solver.solve(t.gQ16, 0);
    EncodedState stR = solver.solve(t.rQ16, 1);
    EncodedState stB = solver.solve(t.bQ16, 2);
    EncodedState stW = solver.solve(t.wQ16, 3);

    for (uint16_t i = 0; i < LED_COUNT; ++i) {
        SolverRuntime::commitPixelRGBW(
            upperFrame, floorFrame,
            bfiG, bfiR, bfiB, bfiW,
            i, stG, stR, stB, stW);
    }

    Serial.println("rgbwNoExtractionDemo — direct RGBW input");
    Serial.print("Input  RGBW: ");
    Serial.print(rQ16); Serial.print(", ");
    Serial.print(gQ16); Serial.print(", ");
    Serial.print(bQ16); Serial.print(", ");
    Serial.println(wQ16);
    Serial.print("After limit: W="); Serial.println(t.wQ16);
}

static constexpr uint32_t SERIAL_INTERVAL_MS = 200;
static uint32_t lastSerialMs = 0;

void loop() {
    SolverRuntime::renderSubpixelBFI_RGBW(
        upperFrame, floorFrame,
        bfiG, bfiR, bfiB, bfiW,
        displayBuf, LED_COUNT, phase);

    // --- LED .show() would go here in a real sketch ---

    uint32_t now = millis();
    if (now - lastSerialMs >= SERIAL_INTERVAL_MS) {
        lastSerialMs = now;
        Serial.print("Phase ");
        Serial.print(phase);
        Serial.print(": G=");  Serial.print(displayBuf[0]);
        Serial.print(" R=");   Serial.print(displayBuf[1]);
        Serial.print(" B=");   Serial.print(displayBuf[2]);
        Serial.print(" W=");   Serial.println(displayBuf[3]);
    }

    phase = (phase + 1) % CYCLE_LEN;
}
