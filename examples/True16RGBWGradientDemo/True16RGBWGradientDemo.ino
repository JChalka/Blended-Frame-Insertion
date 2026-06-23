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
enum class DemoOutputLayout : uint8_t {
    RGB = 3,
    RGBW = 4,
    RGBWW = 5,
};

// Switch this to RGB, RGBW, or RGBWW to compare output families.
static constexpr DemoOutputLayout DEMO_LAYOUT = DemoOutputLayout::RGBWW;

static constexpr uint8_t channelCountForDemoLayout(DemoOutputLayout layout) {
    switch (layout) {
        case DemoOutputLayout::RGB: return 3;
        case DemoOutputLayout::RGBW: return 4;
        default: return 5;
    }
}

static constexpr LedColorOrder colorOrderForDemoLayout(DemoOutputLayout layout) {
    switch (layout) {
        case DemoOutputLayout::RGB: return LedColorOrder::GRB;
        case DemoOutputLayout::RGBW: return LedColorOrder::GRBW;
        default: return LedColorOrder::GRBW1W2;
    }
}

static constexpr const char* demoLayoutName(DemoOutputLayout layout) {
    switch (layout) {
        case DemoOutputLayout::RGB: return "RGB";
        case DemoOutputLayout::RGBW: return "RGBW";
        default: return "RGBWW";
    }
}

static constexpr uint8_t DEMO_CHANNELS = channelCountForDemoLayout(DEMO_LAYOUT);

static constexpr RenderOptions RENDER_OPTIONS = {
    colorOrderForDemoLayout(DEMO_LAYOUT),
    BfiMapStorageMode::Separate,
};

static uint8_t  solverValueLUT[5 * LUT_SIZE];
static uint8_t  solverBFILUT  [5 * LUT_SIZE];
static uint8_t  solverFloorLUT[5 * LUT_SIZE];

static uint8_t upperFrame[LED_COUNT * DEMO_CHANNELS] = {0};
static uint8_t floorFrame[LED_COUNT * DEMO_CHANNELS] = {0};
static uint8_t displayBuf[LED_COUNT * DEMO_CHANNELS] = {0};
static uint8_t bfiG[LED_COUNT] = {0};
static uint8_t bfiR[LED_COUNT] = {0};
static uint8_t bfiB[LED_COUNT] = {0};
static uint8_t bfiW[LED_COUNT] = {0};
static uint8_t bfiW2[LED_COUNT] = {0};

static SolverRuntime solver;
static uint8_t  phase  = 0;
static uint16_t offset = 0;

static void updateGradient() {
    BfiMapWriteView bfiMaps;
    bfiMaps.bfiMapG = bfiG;
    bfiMaps.bfiMapR = bfiR;
    bfiMaps.bfiMapB = bfiB;
    bfiMaps.bfiMapW1 = bfiW;
    bfiMaps.bfiMapW2 = bfiW2;

    for (uint16_t i = 0; i < LED_COUNT; ++i) {
        // Each LED gets a unique position in a smooth colour sweep.
        uint32_t pos = ((uint32_t)(i + offset) * 65535u) / LED_COUNT;
        uint16_t rQ16 = (uint16_t)(pos & 0xFFFFu);
        uint16_t gQ16 = (uint16_t)((65535u - pos) & 0xFFFFu);
        uint16_t bQ16 = (uint16_t)((pos >> 1) & 0xFFFFu);

        EncodedState states[5] = {};
        uint8_t stateCount = DEMO_CHANNELS;

        if (DEMO_LAYOUT == DemoOutputLayout::RGB) {
            states[0] = solver.solve(gQ16, 0);
            states[1] = solver.solve(rQ16, 1);
            states[2] = solver.solve(bQ16, 2);
        } else if (DEMO_LAYOUT == DemoOutputLayout::RGBW) {
            const RgbwTargets t = solver.extractRgbw(rQ16, gQ16, bQ16);
            states[0] = solver.solve(t.gQ16, 0);
            states[1] = solver.solve(t.rQ16, 1);
            states[2] = solver.solve(t.bQ16, 2);
            states[3] = solver.solve(t.wQ16, 3);
        } else {
            const RgbwwTargets t = solver.extractRgbwwEmulated(rQ16, gQ16, bQ16);
            states[0] = solver.solve(t.gQ16, 0);
            states[1] = solver.solve(t.rQ16, 1);
            states[2] = solver.solve(t.bQ16, 2);
            states[3] = solver.solveWhiteEmulated(t.w1Q16);
            states[4] = solver.solveWhiteEmulated(t.w2Q16);
        }

        SolverRuntime::commitPixel(
            upperFrame, floorFrame,
            bfiMaps,
            i,
            states,
            stateCount,
            RENDER_OPTIONS);
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000) {}

    solver.attachLUTs(solverValueLUT, solverBFILUT, solverFloorLUT, nullptr, LUT_SIZE);
    solver.setLedColorOrder(RENDER_OPTIONS.colorOrder);
    solver.setSolverLUTMode(SolverLUTMode::PerChannel);
    solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16, DEMO_CHANNELS);

    Serial.println("True16RGBWGradientDemo");
    Serial.print("Layout: ");   Serial.println(demoLayoutName(DEMO_LAYOUT));
    Serial.print("Channels: "); Serial.println(DEMO_CHANNELS);
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

    BfiMapView bfiMaps;
    bfiMaps.bfiMapG = bfiG;
    bfiMaps.bfiMapR = bfiR;
    bfiMaps.bfiMapB = bfiB;
    bfiMaps.bfiMapW1 = bfiW;
    bfiMaps.bfiMapW2 = bfiW2;

    SolverRuntime::renderLoopStatic(
        upperFrame, floorFrame,
        bfiMaps,
        displayBuf, LED_COUNT, phase,
        RENDER_OPTIONS);

    // --- LED .show() would go here in a real sketch ---

    // Throttled serial output.
    if (now - lastSerialMs >= SERIAL_INTERVAL_MS) {
        lastSerialMs = now;
        Serial.print("Ph");
        Serial.print(phase);
        for (uint16_t i = 0; i < 4 && i < LED_COUNT; ++i) {
            const uint32_t off = (uint32_t)i * DEMO_CHANNELS;
            Serial.print(" [");
            for (uint8_t ch = 0; ch < DEMO_CHANNELS; ++ch) {
                if (ch) Serial.print(",");
                Serial.print(displayBuf[off + ch]);
            }
            Serial.print("]");
        }
        Serial.println();
    }

    phase = (phase + 1) % CYCLE_LEN;
}
