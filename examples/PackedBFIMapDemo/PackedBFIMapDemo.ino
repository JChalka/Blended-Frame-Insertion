// PackedBFIMapDemo.ino
// Demonstrates the packed BFI map API — stores per-pixel BFI levels in a
// nybble-pair buffer (2 bytes/pixel) instead of separate per-channel arrays.
//
// This sketch exercises both RGB and RGBW packed paths:
//   - RGB:  commitPixelRGB_Packed  + renderSubpixelBFI_RGB_Packed
//   - RGBW: commitPixelRGBW_Packed + renderSubpixelBFI_RGBW_Packed
//
// The inline helpers packBfi4/unpackBfi4, readPackedBfiChannel, and
// writePackedBfiChannel are also demonstrated for post-commit clamping.
//
// Memory savings vs separate arrays:
//   RGBW: 4 bytes/pixel → 2 bytes/pixel  (50%)
//   RGB:  3 bytes/pixel → 2 bytes/pixel  (33%)

#include <Arduino.h>
#include <TemporalBFI.h>
#include <TemporalBFIRuntime.h>

using namespace TemporalBFI;

static constexpr uint16_t LED_COUNT  = 16;
static constexpr uint8_t  CYCLE_LEN  = SOLVER_FIXED_BFI_LEVELS;  // 5
static constexpr uint16_t LUT_SIZE   = TemporalBFIRuntime::SOLVER_LUT_SIZE;

// Solver LUTs.
static uint8_t solverValueLUT[4 * LUT_SIZE];
static uint8_t solverBFILUT  [4 * LUT_SIZE];
static uint8_t solverFloorLUT[4 * LUT_SIZE];

// ── RGB packed demo buffers ──

static uint8_t  upperRGB[LED_COUNT * 3]  = {0};
static uint8_t  floorRGB[LED_COUNT * 3]  = {0};
static uint8_t  dispRGB [LED_COUNT * 3]  = {0};

// Packed BFI map: 2 bytes per pixel (GR nybble, BW nybble; W=0 for RGB).
static uint8_t  packedBfiRGB[LED_COUNT * PACKED_BFI_BYTES_PER_PIXEL] = {0};

// ── RGBW packed demo buffers ──

static uint8_t  upperRGBW[LED_COUNT * 4] = {0};
static uint8_t  floorRGBW[LED_COUNT * 4] = {0};
static uint8_t  dispRGBW [LED_COUNT * 4] = {0};

static uint8_t  packedBfiRGBW[LED_COUNT * PACKED_BFI_BYTES_PER_PIXEL] = {0};

// ── Source colors (Q16) ──

static uint16_t srcR[LED_COUNT];
static uint16_t srcG[LED_COUNT];
static uint16_t srcB[LED_COUNT];

static SolverRuntime solver;
static uint8_t phase = 0;

// ── Helpers ──

static void fillGradient() {
    for (uint16_t i = 0; i < LED_COUNT; ++i) {
        srcR[i] = (uint16_t)((uint32_t)i * 65535u / LED_COUNT);
        srcG[i] = 32768u;
        srcB[i] = (uint16_t)(65535u - (uint32_t)i * 65535u / LED_COUNT);
    }
}

// Solve and commit into the RGB packed buffers.
static void solveRGB() {
    for (uint16_t i = 0; i < LED_COUNT; ++i) {
        EncodedState stG = solver.solve(srcG[i], 0);
        EncodedState stR = solver.solve(srcR[i], 1);
        EncodedState stB = solver.solve(srcB[i], 2);

        SolverRuntime::commitPixelRGB_Packed(
            upperRGB, floorRGB, packedBfiRGB,
            i, stG, stR, stB);
    }
}

// Solve and commit into the RGBW packed buffers (white = min-of-RGB).
static void solveRGBW() {
    for (uint16_t i = 0; i < LED_COUNT; ++i) {
        EncodedState stG = solver.solve(srcG[i], 0);
        EncodedState stR = solver.solve(srcR[i], 1);
        EncodedState stB = solver.solve(srcB[i], 2);
        uint16_t wQ16 = min3U16(srcR[i], srcG[i], srcB[i]);
        EncodedState stW = solver.solve(wQ16, 3);

        SolverRuntime::commitPixelRGBW_Packed(
            upperRGBW, floorRGBW, packedBfiRGBW,
            i, stG, stR, stB, stW);
    }
}

// Post-commit BFI clamping using the packed read/write helpers.
static void clampPackedBfi(uint8_t* packed, uint16_t count,
                           uint8_t maxBfi, uint8_t channels) {
    for (uint16_t i = 0; i < count; ++i) {
        for (uint8_t ch = 0; ch < channels; ++ch) {
            uint8_t bfi = readPackedBfiChannel(packed, i, ch);
            if (bfi > maxBfi)
                writePackedBfiChannel(packed, i, ch, maxBfi);
        }
    }
}

static void printPixelBfi(const char* label, const uint8_t* packed,
                           uint16_t count, uint8_t channels) {
    Serial.print(label);
    Serial.println(":");
    for (uint16_t i = 0; i < count; ++i) {
        Serial.print("  px ");
        Serial.print(i);
        Serial.print(": ");
        if (channels == 4) {
            uint8_t g, r, b, w;
            unpackBfi4(packed, i, g, r, b, w);
            Serial.print("G="); Serial.print(g);
            Serial.print(" R="); Serial.print(r);
            Serial.print(" B="); Serial.print(b);
            Serial.print(" W="); Serial.println(w);
        } else {
            uint8_t g, r, b;
            unpackBfi3(packed, i, g, r, b);
            Serial.print("G="); Serial.print(g);
            Serial.print(" R="); Serial.print(r);
            Serial.print(" B="); Serial.println(b);
        }
    }
}

static void printRenderRow(const char* label, const uint8_t* buf,
                           uint16_t count, uint8_t bpp) {
    Serial.print("  "); Serial.print(label); Serial.print(": ");
    for (uint16_t i = 0; i < count && i < 4; ++i) {
        const uint32_t off = (uint32_t)i * bpp;
        Serial.print("[");
        for (uint8_t c = 0; c < bpp; ++c) {
            if (c) Serial.print(",");
            Serial.print(buf[off + c]);
        }
        Serial.print("] ");
    }
    if (count > 4) Serial.print("...");
    Serial.println();
}

// ── Main ──

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000) {}

    solver.attachLUTs(solverValueLUT, solverBFILUT, solverFloorLUT, nullptr, LUT_SIZE);
    solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16);

    fillGradient();

    // ── RGB packed path ──
    solveRGB();
    clampPackedBfi(packedBfiRGB, LED_COUNT, CYCLE_LEN - 1, 3);

    Serial.println("=== PackedBFIMapDemo ===");
    Serial.print("LED_COUNT="); Serial.print(LED_COUNT);
    Serial.print("  CYCLE_LEN="); Serial.print(CYCLE_LEN);
    Serial.print("  packed bytes/pixel="); Serial.println(PACKED_BFI_BYTES_PER_PIXEL);

    Serial.print("\nRGB packed map size:  ");
    Serial.print(LED_COUNT * PACKED_BFI_BYTES_PER_PIXEL);
    Serial.print(" bytes  (unpacked would be ");
    Serial.print(LED_COUNT * 3);
    Serial.println(" bytes)");

    printPixelBfi("RGB BFI map", packedBfiRGB, LED_COUNT, 3);

    Serial.println("\nRGB render (first 4 pixels, all phases):");
    for (uint8_t ph = 0; ph < CYCLE_LEN; ++ph) {
        SolverRuntime::renderSubpixelBFI_RGB_Packed(
            upperRGB, floorRGB, packedBfiRGB,
            dispRGB, LED_COUNT, ph);
        char tag[16];
        snprintf(tag, sizeof(tag), "phase %u", ph);
        printRenderRow(tag, dispRGB, LED_COUNT, 3);
    }

    // ── RGBW packed path ──
    solveRGBW();
    clampPackedBfi(packedBfiRGBW, LED_COUNT, CYCLE_LEN - 1, 4);

    Serial.print("\nRGBW packed map size: ");
    Serial.print(LED_COUNT * PACKED_BFI_BYTES_PER_PIXEL);
    Serial.print(" bytes  (unpacked would be ");
    Serial.print(LED_COUNT * 4);
    Serial.println(" bytes)");

    printPixelBfi("RGBW BFI map", packedBfiRGBW, LED_COUNT, 4);

    Serial.println("\nRGBW render (first 4 pixels, all phases):");
    for (uint8_t ph = 0; ph < CYCLE_LEN; ++ph) {
        SolverRuntime::renderSubpixelBFI_RGBW_Packed(
            upperRGBW, floorRGBW, packedBfiRGBW,
            dispRGBW, LED_COUNT, ph);
        char tag[16];
        snprintf(tag, sizeof(tag), "phase %u", ph);
        printRenderRow(tag, dispRGBW, LED_COUNT, 4);
    }

    Serial.println("\nDone.");
}

void loop() {
    // Nothing — demo prints once in setup().
}
