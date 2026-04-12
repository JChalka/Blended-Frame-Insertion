// TemporalFastLEDDemo.ino
// Integrates TemporalBFI with FastLED CRGB output (RGB, 3-byte pixels).
// Color work stays in 16-bit Q16 until the solver maps it to temporal
// blend states.  The CRGB array is only the display buffer that receives
// the 8-bit render output each BFI phase.
// Requires the FastLED library: https://fastled.io

#include <Arduino.h>
#include <FastLED.h>
#include <TemporalBFI.h>
#include <TemporalBFIRuntime.h>

using namespace TemporalBFI;

static constexpr uint16_t LED_COUNT = 16;
static constexpr uint8_t  CYCLE_LEN = 5;
static constexpr uint8_t  DATA_PIN  = 2;
static constexpr uint16_t LUT_SIZE  = TemporalBFIRuntime::SOLVER_LUT_SIZE;

// Solver LUTs.
static uint8_t solverValueLUT[4 * LUT_SIZE];
static uint8_t solverBFILUT  [4 * LUT_SIZE];
static uint8_t solverFloorLUT[4 * LUT_SIZE];

// 16-bit color source — all color/gradient work happens here.
static uint16_t srcR[LED_COUNT];
static uint16_t srcG[LED_COUNT];
static uint16_t srcB[LED_COUNT];

// BFI buffers (GRB internal byte order, 3 bytes per pixel).
static uint8_t upperFrame[LED_COUNT * 3] = {0};
static uint8_t floorFrame[LED_COUNT * 3] = {0};
static uint8_t displayBuf[LED_COUNT * 3] = {0};
static uint8_t bfiG[LED_COUNT] = {0};
static uint8_t bfiR[LED_COUNT] = {0};
static uint8_t bfiB[LED_COUNT] = {0};

// FastLED output array — this is the display buffer, not the color source.
static CRGB leds[LED_COUNT];

static SolverRuntime solver;
static uint8_t phase = 0;

// Solve 16-bit source colors and commit to the BFI frame buffers.
static void solveAndCommit(uint16_t count) {
    for (uint16_t i = 0; i < count; ++i) {
        // Channel map: 0=G, 1=R, 2=B.
        EncodedState stG = solver.solve(srcG[i], 0);
        EncodedState stR = solver.solve(srcR[i], 1);
        EncodedState stB = solver.solve(srcB[i], 2);

        SolverRuntime::commitPixelRGB(
            upperFrame, floorFrame,
            bfiG, bfiR, bfiB,
            i, stG, stR, stB);
    }
}

// Render one BFI phase and write back to the CRGB display array.
static void renderToCRGB(CRGB* dst, uint16_t count, uint8_t ph) {
    SolverRuntime::renderSubpixelBFI_RGB(
        upperFrame, floorFrame,
        bfiG, bfiR, bfiB,
        displayBuf, count, ph);

    // Map internal GRB byte order to CRGB (RGB memory order).
    for (uint16_t i = 0; i < count; ++i) {
        const uint32_t off = (uint32_t)i * 3u;
        dst[i].r = displayBuf[off + 1];
        dst[i].g = displayBuf[off + 0];
        dst[i].b = displayBuf[off + 2];
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000) {}

    FastLED.addLeds<WS2812B, DATA_PIN, GRB>(leds, LED_COUNT);
    FastLED.setBrightness(255);

    solver.attachLUTs(solverValueLUT, solverBFILUT, solverFloorLUT, nullptr, LUT_SIZE);
    solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16);

    // Fill a simple gradient in 16-bit Q16 space.
    for (uint16_t i = 0; i < LED_COUNT; ++i) {
        srcR[i] = (uint16_t)((uint32_t)i * 65535u / LED_COUNT);
        srcG[i] = 32768u;
        srcB[i] = (uint16_t)(65535u - (uint32_t)i * 65535u / LED_COUNT);
    }

    solveAndCommit(LED_COUNT);
    Serial.println("TemporalFastLEDDemo ready.");
}

void loop() {
    renderToCRGB(leds, LED_COUNT, phase);
    FastLED.show();

    phase = (phase + 1) % CYCLE_LEN;
}
