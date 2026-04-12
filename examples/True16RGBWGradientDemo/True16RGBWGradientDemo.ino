// True16RGBWGradientDemo.ino
// Animates a smooth 16-bit RGBW gradient across the LED strip
// using True16 solver with RGBW extraction.

#include <Arduino.h>
#include <TemporalBFI.h>
#include <TemporalBFIRuntime.h>

using namespace TemporalBFI;

static constexpr uint16_t LED_COUNT = 16;
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
static uint8_t  phase  = 0;
static uint16_t offset = 0;

static void updateGradient() {
    for (uint16_t i = 0; i < LED_COUNT; ++i) {
        // Each LED gets a unique position in a smooth colour sweep.
        uint32_t pos = ((uint32_t)(i + offset) * 65535u) / LED_COUNT;
        uint16_t rQ16 = (uint16_t)(pos & 0xFFFFu);
        uint16_t gQ16 = (uint16_t)((65535u - pos) & 0xFFFFu);
        uint16_t bQ16 = (uint16_t)((pos >> 1) & 0xFFFFu);

        RgbwTargets t = solver.extractRgbw(rQ16, gQ16, bQ16);

        EncodedState stG = solver.solve(t.gQ16, 0);
        EncodedState stR = solver.solve(t.rQ16, 1);
        EncodedState stB = solver.solve(t.bQ16, 2);
        EncodedState stW = solver.solve(t.wQ16, 3);

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
    solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16);

    Serial.println("True16RGBWGradientDemo");
    Serial.print("LEDs: ");     Serial.println(LED_COUNT);
    Serial.print("LUT size: "); Serial.println(LUT_SIZE);
}

static constexpr uint32_t GRADIENT_INTERVAL_MS = 50;
static constexpr uint32_t SERIAL_INTERVAL_MS  = 200;
static uint32_t lastUpdateMs = 0;
static uint32_t lastSerialMs = 0;

void loop() {
    // Only re-solve the gradient when the offset actually changed.
    uint32_t now = millis();
    if (phase == 0 && now - lastUpdateMs >= GRADIENT_INTERVAL_MS) {
        lastUpdateMs = now;
        ++offset;
        updateGradient();
    }

    SolverRuntime::renderSubpixelBFI_RGBW(
        upperFrame, floorFrame,
        bfiG, bfiR, bfiB, bfiW,
        displayBuf, LED_COUNT, phase);

    // --- LED .show() would go here in a real sketch ---

    // Throttled serial output.
    if (now - lastSerialMs >= SERIAL_INTERVAL_MS) {
        lastSerialMs = now;
        Serial.print("Ph");
        Serial.print(phase);
        for (uint16_t i = 0; i < 4 && i < LED_COUNT; ++i) {
            const uint32_t off = (uint32_t)i * 4u;
            Serial.print(" [");
            Serial.print(displayBuf[off]);     Serial.print(",");
            Serial.print(displayBuf[off + 1]); Serial.print(",");
            Serial.print(displayBuf[off + 2]); Serial.print(",");
            Serial.print(displayBuf[off + 3]);
            Serial.print("]");
        }
        Serial.println();
    }

    phase = (phase + 1) % CYCLE_LEN;
}
