// ESP32S3_DoubleBuffer.ino
// Demonstrates double-buffered BFI rendering on ESP32-S3 with FastLED.
// Uses consolidated commit/render APIs plus explicit color-order and
// solver-LUT mode configuration for migration-clean behavior.
//
// Architecture:
//   Core 0 — Solve task: generates 16-bit color, solves to BFI frames.
//   Core 1 — Display task (loop): swaps buffers, renders BFI sub-frames,
//            drives LEDs via FastLED.
//
// The solve task writes to one set of buffers while the display task reads
// from the other. When solve is done it sets a flag; the display loop swaps
// pointer pairs (zero-copy) and wakes the solve task for the next frame.
//
// Requires:
//   - ESP32-S3 board with PSRAM
//   - FastLED library
//   - TemporalBFI library

#include <Arduino.h>
#include <FastLED.h>
#include <TemporalBFI.h>
#include <TemporalBFIRuntime.h>
#include <esp_task_wdt.h>
#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

using namespace TemporalBFI;

// ---------------------------------------------------------------------------
// User-tunable constants
// ---------------------------------------------------------------------------
static constexpr uint16_t LED_COUNT    = 64;     // total pixel count
static constexpr uint8_t  DATA_PIN     = 2;      // WS2812B data pin
static constexpr uint8_t  CYCLE_LEN    = 5;      // BFI phases per frame (0-4)
static constexpr uint16_t LUT_SIZE     = TemporalBFIRuntime::SOLVER_LUT_SIZE;
static constexpr uint8_t  CHANNELS      = 3;      // RGB

static constexpr RenderOptions RENDER_OPTIONS = {
    LedColorOrder::GRB,
    BfiMapStorageMode::Separate,
};

// ---------------------------------------------------------------------------
// Solver LUTs — allocated in PSRAM at startup
// ---------------------------------------------------------------------------
static uint8_t* solverValueLUT = nullptr;
static uint8_t* solverBFILUT   = nullptr;
static uint8_t* solverFloorLUT = nullptr;

// ---------------------------------------------------------------------------
// Double-buffered frame storage
//
// "solve" buffers — written by the solve task (core 0)
// "disp"  buffers — read by the display loop (core 1)
// On swap, only the pointers are exchanged (zero-copy).
// ---------------------------------------------------------------------------
static uint8_t* upperFrame     = nullptr;  // PSRAM — solve side
static uint8_t* floorFrame     = nullptr;
static uint8_t* dispUpperFrame = nullptr;  // PSRAM — display side
static uint8_t* dispFloorFrame = nullptr;

// BFI channel maps — two banks, pointer-swapped on frame boundary.
static uint8_t bfiG_store[2][LED_COUNT] = {};
static uint8_t bfiR_store[2][LED_COUNT] = {};
static uint8_t bfiB_store[2][LED_COUNT] = {};

static uint8_t* bfiG     = bfiG_store[0];
static uint8_t* bfiR     = bfiR_store[0];
static uint8_t* bfiB     = bfiB_store[0];
static uint8_t* dispBfiG = bfiG_store[1];
static uint8_t* dispBfiR = bfiR_store[1];
static uint8_t* dispBfiB = bfiB_store[1];

// Intermediate render buffer (GRB byte order, 3 bytes/pixel).
static uint8_t displayBuf[LED_COUNT * 3] = {};

// FastLED output array.
static CRGB leds[LED_COUNT];

// ---------------------------------------------------------------------------
// Synchronisation
// ---------------------------------------------------------------------------
static volatile bool     solveReady      = false;
static TaskHandle_t      solveTaskHandle = nullptr;

// ---------------------------------------------------------------------------
// Solver instance
// ---------------------------------------------------------------------------
static SolverRuntime solver;

// ---------------------------------------------------------------------------
// 16-bit source color arrays — patterns write here, solve reads from here.
// ---------------------------------------------------------------------------
static uint16_t srcR[LED_COUNT];
static uint16_t srcG[LED_COUNT];
static uint16_t srcB[LED_COUNT];

// Display pacing + telemetry.
static constexpr uint32_t MIN_SHOW_INTERVAL_US = 1600u;   // 625 FPS max (allows jitter headroom)
static constexpr uint32_t FPS_REPORT_INTERVAL_US = 2000000u;

// ---------------------------------------------------------------------------
// Pattern — simple animated rainbow in 16-bit Q16 space
// ---------------------------------------------------------------------------
static uint16_t hueOffset = 0;

static void generatePattern() {
    for (uint16_t i = 0; i < LED_COUNT; ++i) {
        // Map pixel position + animation offset to a hue in [0, 65535].
        uint16_t hue16 = (uint16_t)((uint32_t)i * 65535u / LED_COUNT) + hueOffset;

        // HSV-to-RGB in Q16.  Use a simple 6-sector conversion.
        uint16_t sector = hue16 / 10923;           // 0-5
        uint16_t frac   = (hue16 % 10923) * 6;     // 0-65535 within sector
        uint16_t inv    = 65535u - frac;

        uint16_t r, g, b;
        switch (sector) {
            case 0:  r = 65535; g = frac;   b = 0;      break;
            case 1:  r = inv;   g = 65535;  b = 0;      break;
            case 2:  r = 0;     g = 65535;  b = frac;   break;
            case 3:  r = 0;     g = inv;    b = 65535;   break;
            case 4:  r = frac;  g = 0;      b = 65535;   break;
            default: r = 65535; g = 0;      b = inv;     break;
        }

        srcR[i] = r;
        srcG[i] = g;
        srcB[i] = b;
    }
    hueOffset += 256;  // advance animation
}

// ---------------------------------------------------------------------------
// Solve all pixels and commit to the solve-side BFI frame buffers.
// ---------------------------------------------------------------------------
static void solveAndCommitAll() {
    BfiMapWriteView bfiMaps;
    bfiMaps.bfiMapG = bfiG;
    bfiMaps.bfiMapR = bfiR;
    bfiMaps.bfiMapB = bfiB;

    for (uint16_t i = 0; i < LED_COUNT; ++i) {
        EncodedState stG = solver.solve(srcG[i], 0);
        EncodedState stR = solver.solve(srcR[i], 1);
        EncodedState stB = solver.solve(srcB[i], 2);

        EncodedState states[3] = {stG, stR, stB};

        SolverRuntime::commitPixel(
            upperFrame, floorFrame,
            bfiMaps,
            i,
            states,
            CHANNELS,
            RENDER_OPTIONS);
    }
}

// ---------------------------------------------------------------------------
// Solve task — runs on core 0.
//
// Each iteration: generate pattern → solve → signal display → wait for swap.
// ---------------------------------------------------------------------------
static void solveTask(void* pvParameters) {
    // Subscribe solve task to TWDT and feed it explicitly in the tight loop.
    esp_task_wdt_add(NULL);

    for (;;) {
        esp_task_wdt_reset();

        uint32_t tStart = micros();

        generatePattern();
        solveAndCommitAll();

        uint32_t tEnd = micros();

        // Optional: periodic timing printout.
        static uint32_t frameCount = 0, accumUs = 0;
        accumUs += (tEnd - tStart);
        if (++frameCount >= 60) {
            Serial.printf("  solveTask: %luus avg (%lu frames)\n",
                          accumUs / frameCount, frameCount);
            accumUs    = 0;
            frameCount = 0;
        }

        // Signal that new solve data is ready, then block until display swaps.
        solveReady = true;
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    }
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------
static uint8_t bframe = 0;

// Swap solve ↔ display buffer pointers (zero-copy).
static void swapBuffers() {
    uint8_t* tmp;
    tmp = upperFrame;  upperFrame  = dispUpperFrame;  dispUpperFrame  = tmp;
    tmp = floorFrame;  floorFrame  = dispFloorFrame;  dispFloorFrame  = tmp;

    uint8_t* tmpB;
    tmpB = bfiG;  bfiG = dispBfiG;  dispBfiG = tmpB;
    tmpB = bfiR;  bfiR = dispBfiR;  dispBfiR = tmpB;
    tmpB = bfiB;  bfiB = dispBfiB;  dispBfiB = tmpB;
}

// Render one BFI sub-frame from the display-side buffers into the CRGB array.
static void renderPhase(uint8_t phase) {
    BfiMapView bfiMaps;
    bfiMaps.bfiMapG = dispBfiG;
    bfiMaps.bfiMapR = dispBfiR;
    bfiMaps.bfiMapB = dispBfiB;

    SolverRuntime::renderLoopStatic(
        dispUpperFrame, dispFloorFrame,
        bfiMaps,
        displayBuf, LED_COUNT, phase,
        RENDER_OPTIONS);

    // Map internal GRB byte order → CRGB (RGB memory order).
    for (uint16_t i = 0; i < LED_COUNT; ++i) {
        const uint32_t off = (uint32_t)i * 3u;
        leds[i].r = displayBuf[off + 1];
        leds[i].g = displayBuf[off + 0];
        leds[i].b = displayBuf[off + 2];
    }
}

// ---------------------------------------------------------------------------
// Arduino setup — runs on core 1
// ---------------------------------------------------------------------------
void setup() {
    Serial.begin(115200);
    delay(500);

    // --- Allocate PSRAM buffers ---
    solverValueLUT = (uint8_t*)ps_malloc(CHANNELS * LUT_SIZE);
    solverBFILUT   = (uint8_t*)ps_malloc(CHANNELS * LUT_SIZE);
    solverFloorLUT = (uint8_t*)ps_malloc(CHANNELS * LUT_SIZE);

    upperFrame     = (uint8_t*)ps_malloc(LED_COUNT * CHANNELS);
    floorFrame     = (uint8_t*)ps_malloc(LED_COUNT * CHANNELS);
    dispUpperFrame = (uint8_t*)ps_malloc(LED_COUNT * CHANNELS);
    dispFloorFrame = (uint8_t*)ps_malloc(LED_COUNT * CHANNELS);

    memset(upperFrame,     0, LED_COUNT * CHANNELS);
    memset(floorFrame,     0, LED_COUNT * CHANNELS);
    memset(dispUpperFrame, 0, LED_COUNT * CHANNELS);
    memset(dispFloorFrame, 0, LED_COUNT * CHANNELS);

    // --- Initialise solver ---
    solver.attachLUTs(solverValueLUT, solverBFILUT, solverFloorLUT, nullptr, LUT_SIZE);
    solver.setLedColorOrder(RENDER_OPTIONS.colorOrder);
    solver.setSolverLUTMode(SolverLUTMode::PerChannel);
    solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16, CHANNELS);

    // --- Initialise FastLED ---
    FastLED.addLeds<WS2812B, DATA_PIN, GRB>(leds, LED_COUNT);
    FastLED.setBrightness(255);

    // --- Solve the first frame synchronously so there's something to display ---
    generatePattern();
    solveAndCommitAll();
    swapBuffers();   // move solve data into the display side

    // --- Launch solve task on core 0 ---
    xTaskCreatePinnedToCore(
        solveTask,
        "solve",
        8192,              // stack — no heavy allocations on stack
        nullptr,
        2,                 // priority
        &solveTaskHandle,
        0                  // core 0
    );

    Serial.println("ESP32S3_DoubleBuffer ready.");
}

// ---------------------------------------------------------------------------
// Arduino loop — display task, runs on core 1
//
// Each iteration renders one BFI sub-frame.  When a fresh solve is ready the
// buffer pointers are swapped (zero-copy) and the solve task is woken.
// ---------------------------------------------------------------------------
void loop() {
    static uint32_t lastShowUs = (uint32_t)micros();
    static uint32_t fpsFrameCount = 0;
    static uint32_t fpsSwapCount = 0;
    static uint32_t fpsMaxFrameUs = 0;
    static uint32_t fpsMinFrameUs = UINT32_MAX;
    static uint32_t fpsLastReportUs = (uint32_t)micros();
    static uint32_t frameStartUs = (uint32_t)micros();

    frameStartUs = (uint32_t)micros();

    // Unsigned subtraction keeps this rollover-safe when micros() wraps.
    uint32_t elapsedSinceShowUs = (uint32_t)(frameStartUs - lastShowUs);
    if (elapsedSinceShowUs < MIN_SHOW_INTERVAL_US) {
        vTaskDelay(1);
        return;
    }

    bool didSwap = false;

    // --- Check for new solve data ---
    if (solveReady) {
        swapBuffers();
        solveReady = false;
        didSwap = true;
        xTaskNotifyGive(solveTaskHandle);  // wake solve task for next frame
    }

    // --- Render current BFI phase ---
    renderPhase(bframe);
    FastLED.show();
    lastShowUs = (uint32_t)micros();

    bframe = (bframe + 1) % CYCLE_LEN;

    uint32_t frameEndUs = (uint32_t)micros();
    uint32_t frameDeltaUs = (uint32_t)(frameEndUs - frameStartUs);

    ++fpsFrameCount;
    if (didSwap) {
        ++fpsSwapCount;
    }
    if (frameDeltaUs > fpsMaxFrameUs) {
        fpsMaxFrameUs = frameDeltaUs;
    }
    if (frameDeltaUs < fpsMinFrameUs) {
        fpsMinFrameUs = frameDeltaUs;
    }

    uint32_t elapsedReportUs = (uint32_t)(frameEndUs - fpsLastReportUs);
    if (elapsedReportUs >= FPS_REPORT_INTERVAL_US && fpsFrameCount > 0) {
        float fps = (float)fpsFrameCount * 1000000.0f / (float)elapsedReportUs;
        float frameMs = (float)elapsedReportUs / (float)fpsFrameCount / 1000.0f;
        Serial.printf("FPS: %.1f (%.2f ms/frame) | min %.2f max %.2f ms | swaps %lu | %lu fr\n",
                      fps,
                      frameMs,
                      (float)fpsMinFrameUs / 1000.0f,
                      (float)fpsMaxFrameUs / 1000.0f,
                      (unsigned long)fpsSwapCount,
                      (unsigned long)fpsFrameCount);

        fpsFrameCount = 0;
        fpsSwapCount = 0;
        fpsMaxFrameUs = 0;
        fpsMinFrameUs = UINT32_MAX;
        fpsLastReportUs = frameEndUs;
    }

    if (!didSwap) {
        vTaskDelay(1);
    }
}
