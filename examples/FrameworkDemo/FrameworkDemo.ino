// FrameworkDemo.ino
// Minimal TemporalBFI pipeline: solve → commit → BFI render.
// Calls the policy solver directly — no LUT precomputation needed.

#include <Arduino.h>
#include <TemporalBFI.h>
#include <TemporalBFIRuntime.h>

static constexpr uint16_t LED_COUNT = 4;
static constexpr uint8_t  CYCLE_LEN = 5;

// Pixel buffers (GRBW byte order, 4 bytes per pixel).
static uint8_t upperFrame[LED_COUNT * 4] = {0};
static uint8_t floorFrame[LED_COUNT * 4] = {0};
static uint8_t displayBuf[LED_COUNT * 4] = {0};

// Per-pixel BFI maps (one per sub-pixel channel).
static uint8_t bfiG[LED_COUNT] = {0};
static uint8_t bfiR[LED_COUNT] = {0};
static uint8_t bfiB[LED_COUNT] = {0};
static uint8_t bfiW[LED_COUNT] = {0};

static uint8_t phase = 0;

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000) {}

    // Test color in Q16 (0–65535 range).
    const uint16_t rQ16 = 45000;
    const uint16_t gQ16 = 38000;
    const uint16_t bQ16 = 20000;

    // Solve each channel directly via the policy solver.
    // Channel map: 0=G, 1=R, 2=B, 3=W.
    TemporalBFI::EncodedState stG = TemporalTrue16BFIPolicySolver::encodeStateFrom16(gQ16, 0);
    TemporalBFI::EncodedState stR = TemporalTrue16BFIPolicySolver::encodeStateFrom16(rQ16, 1);
    TemporalBFI::EncodedState stB = TemporalTrue16BFIPolicySolver::encodeStateFrom16(bQ16, 2);
    TemporalBFI::EncodedState stW = {0, 0, 0, 0, 0};

    // Commit solved state to every LED.
    for (uint16_t i = 0; i < LED_COUNT; ++i) {
        TemporalBFI::SolverRuntime::commitPixelRGBW(
            upperFrame, floorFrame,
            bfiG, bfiR, bfiB, bfiW,
            i, stG, stR, stB, stW);
    }

    Serial.println("FrameworkDemo — minimal TemporalBFI pipeline");
    Serial.print("R: val="); Serial.print(stR.value);
    Serial.print(" floor="); Serial.print(stR.lowerValue);
    Serial.print(" bfi=");  Serial.println(stR.bfi);
    Serial.print("G: val="); Serial.print(stG.value);
    Serial.print(" floor="); Serial.print(stG.lowerValue);
    Serial.print(" bfi=");  Serial.println(stG.bfi);
    Serial.print("B: val="); Serial.print(stB.value);
    Serial.print(" floor="); Serial.print(stB.lowerValue);
    Serial.print(" bfi=");  Serial.println(stB.bfi);
}

static constexpr uint32_t SERIAL_INTERVAL_MS = 200;
static uint32_t lastSerialMs = 0;

void loop() {
    // Render the current BFI phase into the display buffer.
    TemporalBFI::SolverRuntime::renderSubpixelBFI_RGBW(
        upperFrame, floorFrame,
        bfiG, bfiR, bfiB, bfiW,
        displayBuf, LED_COUNT, phase);

    // --- LED .show() would go here in a real sketch ---

    // Throttled serial output — does not block the render loop.
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
