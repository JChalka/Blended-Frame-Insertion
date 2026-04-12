// ColorCalibrationABDemo.ino
// Toggles calibration on/off to compare rendered output.
// Requires TEMPORAL_TRUE16_ENABLE_INPUT_Q16_CALIBRATION for active calibration.

#define TEMPORAL_TRUE16_ENABLE_INPUT_Q16_CALIBRATION
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
static bool lastCalState = false;

static const uint16_t testR = 45000;
static const uint16_t testG = 38000;
static const uint16_t testB = 20000;

static void solveAndCommit() {
    RgbwTargets t = solver.extractRgbw(testR, testG, testB);
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
}

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000) {}

    solver.attachLUTs(solverValueLUT, solverBFILUT, solverFloorLUT, nullptr, LUT_SIZE);

    // Register the calibration callback (wraps per_bfi_v3.h).
    solver.setCalibrationFunction([](uint16_t q16, uint8_t ch) -> uint16_t {
        return TemporalTrue16BFIPolicySolver::calibrateInputQ16ForSolver(q16, ch);
    });

    solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16);

    // Initial solve with calibration off.
    solveAndCommit();

    Serial.println("ColorCalibrationABDemo — toggles calibration every 3 s");
}
static constexpr uint32_t SERIAL_INTERVAL_MS = 200;
static uint32_t lastSerialMs = 0;
void loop() {
    bool calEnabled = ((millis() / 3000u) & 1u) != 0u;
    if (calEnabled != lastCalState) {
        lastCalState = calEnabled;
        solver.setCalibrationEnabled(calEnabled);
        solveAndCommit();
        Serial.print("Calibration: ");
        Serial.println(calEnabled ? "ON" : "OFF");
    }

    SolverRuntime::renderSubpixelBFI_RGBW(
        upperFrame, floorFrame,
        bfiG, bfiR, bfiB, bfiW,
        displayBuf, LED_COUNT, phase);

    // Throttled serial output — does not block the render loop.
    uint32_t now = millis();
    if (phase == 0 && now - lastSerialMs >= SERIAL_INTERVAL_MS) {
        lastSerialMs = now;
        Serial.print(calEnabled ? "[CAL] " : "[RAW] ");
        Serial.print("G=");  Serial.print(displayBuf[0]);
        Serial.print(" R="); Serial.print(displayBuf[1]);
        Serial.print(" B="); Serial.print(displayBuf[2]);
        Serial.print(" W="); Serial.println(displayBuf[3]);
    }

    phase = (phase + 1) % CYCLE_LEN;
}
