// CubeLUT3DDemo.ino
// Demonstrates loading calibrated RGB/RGBW 3D cube LUTs from multiple sources.
//
// Three loading paths are shown:
//   1. SD Card   — Full-size binary cubes exported by rgbw_lut_gui.py
//   2. PROGMEM   — Small cubes compiled into internal flash as headers
//   3. QSPI Flash — External soldered flash (placeholder, board-specific)
//
// Pipeline order:
//   Input → Transfer Curve → 3D Cube LUT → Solver
//
// The cube LUT already contains pre-calibrated RGBW (or RGB) values
// and should be the last color-modifying stage before the solver encodes
// BFI states.  Do not modify channel values after the cube lookup.
//
// Why Transfer Curve before Cube?
//   Applying white extraction before the curve and then the transfer
//   curve afterwards breaks the calibrated energy split between
//   channels and reduces total energy further.  The correct order
//   keeps the cube values as the calibrated ground truth.
//
// Memory allocation:
//   Large cubes (grid ≥ 33 RGBW ≈ 281 KB) will only fit in PSRAM.
//   The demo uses a tiered fallback:
//     PSRAM (EXTMEM) → general heap (RAM)
//   The buffer is zeroed after allocation — EXTMEM (PSRAM) and DMAMEM
//   can contain garbage data on power-up.
//
// PSRAM overclocking:
//   On Teensy 4.1 the PSRAM runs at 88 MHz by default.  It can be
//   overclocked (e.g. 132 MHz) for higher read throughput during cube
//   lookups, but this is not demonstrated here to keep the example
//   portable.  See the Teensy documentation for PSRAM clock settings.

#include <Arduino.h>
#include <TemporalBFI.h>
#include <CubeLUT3D.h>
#include <TemporalBFIRuntime.h>
#include <SD.h>

using namespace TemporalBFI;

// ============================================================================
// Configuration
// ============================================================================

static constexpr uint16_t LED_COUNT = 4;
static constexpr uint8_t  CYCLE_LEN = 5;
static constexpr uint16_t LUT_SIZE  = TemporalBFIRuntime::SOLVER_LUT_SIZE;

// SD card filename (exported by rgbw_lut_gui.py → "Export Binary Cube").
static const char* SD_CUBE_FILENAME = "cube.bin";

// SD chip select — BUILTIN_SDCARD on Teensy 4.1, or SPI CS pin otherwise.
#if defined(BUILTIN_SDCARD)
static constexpr int SD_CS = BUILTIN_SDCARD;
#else
static constexpr int SD_CS = 10;
#endif

// ============================================================================
// Memory tier allocation (Teensy-specific, falls back to heap elsewhere)
// ============================================================================

#if defined(__IMXRT1062__)
extern "C" uint8_t external_psram_size;
extern "C" void* extmem_malloc(size_t size);
extern "C" void  extmem_free(void* ptr);
#endif

enum class MemTier : uint8_t { PSRAM, RAM, NONE };

static uint16_t* allocCubeTiered(size_t bytes, MemTier& tier) {
#if defined(__IMXRT1062__)
    if (external_psram_size > 0) {
        uint16_t* p = (uint16_t*)extmem_malloc(bytes);
        if (p) { memset(p, 0, bytes); tier = MemTier::PSRAM; return p; }
    }
#endif
    uint16_t* p = (uint16_t*)malloc(bytes);
    if (p) { memset(p, 0, bytes); tier = MemTier::RAM; return p; }
    tier = MemTier::NONE;
    return nullptr;
}

static void freeCubeTiered(uint16_t* p, MemTier tier) {
    if (!p) return;
#if defined(__IMXRT1062__)
    if (tier == MemTier::PSRAM) { extmem_free(p); return; }
#endif
    free(p);
}

static const char* tierStr(MemTier t) {
    switch (t) {
        case MemTier::PSRAM: return "PSRAM (EXTMEM)";
        case MemTier::RAM:   return "RAM (heap)";
        default:             return "FAILED";
    }
}

static void printFitSuggestions(size_t budgetBytes) {
    Serial.print("  Max RGBW grid in ");
    Serial.print(budgetBytes / 1024);
    Serial.print(" KB: ");
    Serial.println(CubeLUT3D::maxGridForBytes(budgetBytes, 4));
    Serial.print("  Max RGB  grid in ");
    Serial.print(budgetBytes / 1024);
    Serial.print(" KB: ");
    Serial.println(CubeLUT3D::maxGridForBytes(budgetBytes, 3));
}

// ============================================================================
// Embedded demo cube (internal flash / PROGMEM demonstration)
// ============================================================================
// A trivial 5×5×5 RGBW cube using classic min(RGB) white extraction.
// In production, replace with a real measured cube exported by the GUI
// and stored as a PROGMEM const array or loaded from flash.

static constexpr uint16_t DEMO_GRID = 5;
static constexpr uint8_t  DEMO_CH   = 4;
static constexpr size_t   DEMO_ENTRIES = DEMO_GRID * DEMO_GRID * DEMO_GRID * DEMO_CH;

static uint16_t demoCubeData[DEMO_ENTRIES];

static void generateDemoCube() {
    static const uint16_t axis[DEMO_GRID] = {0, 16383, 32767, 49151, 65535};
    size_t idx = 0;
    for (uint8_t r = 0; r < DEMO_GRID; r++) {
        for (uint8_t g = 0; g < DEMO_GRID; g++) {
            for (uint8_t b = 0; b < DEMO_GRID; b++) {
                uint16_t rv = axis[r], gv = axis[g], bv = axis[b];
                uint16_t w = min(rv, min(gv, bv));
                demoCubeData[idx++] = rv - w;
                demoCubeData[idx++] = gv - w;
                demoCubeData[idx++] = bv - w;
                demoCubeData[idx++] = w;
            }
        }
    }
}

// ============================================================================
// Globals
// ============================================================================

static SolverRuntime solver;
static CubeLUT3D    cube;

static uint16_t*    sdCubeBuffer = nullptr;
static MemTier      sdCubeTier   = MemTier::NONE;

// Solver LUTs
static uint8_t solverValueLUT[4 * LUT_SIZE];
static uint8_t solverBFILUT  [4 * LUT_SIZE];
static uint8_t solverFloorLUT[4 * LUT_SIZE];

// Pixel buffers
static uint8_t upperFrame[LED_COUNT * 4] = {0};
static uint8_t floorFrame[LED_COUNT * 4] = {0};
static uint8_t displayBuf[LED_COUNT * 4] = {0};
static uint8_t bfiG[LED_COUNT] = {0};
static uint8_t bfiR[LED_COUNT] = {0};
static uint8_t bfiB[LED_COUNT] = {0};
static uint8_t bfiW[LED_COUNT] = {0};

static uint8_t phase = 0;

// ============================================================================
// SD card loading (Path 1)
// ============================================================================

static bool tryLoadFromSD() {
    if (!SD.begin(SD_CS)) {
        Serial.println("[SD] No SD card detected.");
        return false;
    }

    File f = SD.open(SD_CUBE_FILENAME, FILE_READ);
    if (!f) {
        Serial.print("[SD] File not found: ");
        Serial.println(SD_CUBE_FILENAME);
        return false;
    }

    uint8_t hdr[4];
    if (f.read(hdr, 4) != 4) {
        Serial.println("[SD] Failed to read header.");
        f.close();
        return false;
    }

    uint16_t grid = 0;
    uint8_t ch = 0;
    if (!CubeLUT3D::parseHeader(hdr, grid, ch)) {
        Serial.println("[SD] Invalid cube header.");
        f.close();
        return false;
    }

    const size_t payloadBytes = CubeLUT3D::dataBytes(grid, ch);
    if ((size_t)f.size() < CubeLUT3D::fileBytes(grid, ch)) {
        Serial.println("[SD] File too small for declared grid size.");
        f.close();
        return false;
    }

    Serial.print("[SD] Cube: grid=");
    Serial.print(grid);
    Serial.print(", ch=");
    Serial.print(ch);
    Serial.print(" (");
    Serial.print(ch == 4 ? "RGBW" : "RGB");
    Serial.print("), payload=");
    Serial.print(payloadBytes);
    Serial.println(" bytes");

    sdCubeBuffer = allocCubeTiered(payloadBytes, sdCubeTier);
    if (!sdCubeBuffer) {
        Serial.println("[SD] ERROR: Could not allocate cube buffer.");
        Serial.print("  Needed: "); Serial.print(payloadBytes); Serial.println(" bytes");
        printFitSuggestions(200 * 1024);
        f.close();
        return false;
    }

    Serial.print("[SD] Allocated in: ");
    Serial.println(tierStr(sdCubeTier));

    const size_t bytesRead = f.read((uint8_t*)sdCubeBuffer, payloadBytes);
    f.close();

    if (bytesRead != payloadBytes) {
        Serial.println("[SD] Read size mismatch.");
        freeCubeTiered(sdCubeBuffer, sdCubeTier);
        sdCubeBuffer = nullptr;
        return false;
    }

    cube.attach(sdCubeBuffer, grid, ch);
    Serial.println("[SD] Cube loaded successfully.");
    return true;
}

// ============================================================================
// PROGMEM / internal flash loading (Path 2)
// ============================================================================

static bool loadFromProgmem() {
    generateDemoCube();
    cube.attach(demoCubeData, DEMO_GRID, DEMO_CH);
    Serial.print("[PROGMEM] Demo cube: grid=");
    Serial.print(DEMO_GRID);
    Serial.print(", ch=");
    Serial.print(DEMO_CH);
    Serial.print(", size=");
    Serial.print(sizeof(demoCubeData));
    Serial.println(" bytes");
    return true;
}

// ============================================================================
// External QSPI flash loading (Path 3 — placeholder)
// ============================================================================
// Teensy 4.1 supports soldered QSPI flash chips accessed via LittleFS.
// The loading pattern is identical to the SD card path above:
//
//   #include <LittleFS.h>
//   LittleFS_QSPIFlash flash;
//   if (flash.begin()) {
//       File f = flash.open("cube.bin", FILE_READ);
//       // Read header, allocate with allocCubeTiered(), read payload, attach.
//   }

// ============================================================================
// Pipeline demonstration
// ============================================================================

static void processTestPixel(uint16_t rQ16, uint16_t gQ16, uint16_t bQ16) {
    Serial.print("\nInput: R="); Serial.print(rQ16);
    Serial.print(" G="); Serial.print(gQ16);
    Serial.print(" B="); Serial.println(bQ16);

    // Step 1: Transfer curve (if enabled — not configured in this demo).
    // rQ16 = solver.applyTransferCurve(rQ16, 1);
    // gQ16 = solver.applyTransferCurve(gQ16, 0);
    // bQ16 = solver.applyTransferCurve(bQ16, 2);

    // Step 2: 3D Cube LUT — replaces calibration + white extraction when
    //         enabled.  The cube values are the calibrated RGBW targets.
    //         Do not modify them after this point.
    RgbwTargets targets;
    if (solver.cubeLUT3DEnabled()) {
        targets = solver.applyCubeLUT3D(rQ16, gQ16, bQ16);
        Serial.print("Cube RGBW:    ");
    } else {
        targets = solver.extractRgbw(rQ16, gQ16, bQ16);
        Serial.print("Classic RGBW: ");
    }
    Serial.print(targets.rQ16); Serial.print(", ");
    Serial.print(targets.gQ16); Serial.print(", ");
    Serial.print(targets.bQ16); Serial.print(", ");
    Serial.println(targets.wQ16);

    // Step 3: Solve each channel through precomputed BFI LUTs.
    EncodedState stG = solver.solve(targets.gQ16, 0);
    EncodedState stR = solver.solve(targets.rQ16, 1);
    EncodedState stB = solver.solve(targets.bQ16, 2);
    EncodedState stW = solver.solve(targets.wQ16, 3);

    for (uint16_t i = 0; i < LED_COUNT; ++i) {
        SolverRuntime::commitPixelRGBW(
            upperFrame, floorFrame,
            bfiG, bfiR, bfiB, bfiW,
            i, stG, stR, stB, stW);
    }

    Serial.print("Solver: G(v="); Serial.print(stG.value);
    Serial.print(",f="); Serial.print(stG.lowerValue);
    Serial.print(",bfi="); Serial.print(stG.bfi);
    Serial.print(") R(v="); Serial.print(stR.value);
    Serial.print(",f="); Serial.print(stR.lowerValue);
    Serial.print(",bfi="); Serial.print(stR.bfi);
    Serial.print(") B(v="); Serial.print(stB.value);
    Serial.print(",f="); Serial.print(stB.lowerValue);
    Serial.print(",bfi="); Serial.print(stB.bfi);
    Serial.print(") W(v="); Serial.print(stW.value);
    Serial.print(",f="); Serial.print(stW.lowerValue);
    Serial.print(",bfi="); Serial.print(stW.bfi);
    Serial.println(")");
}

// ============================================================================
// Setup
// ============================================================================

void setup() {
    Serial.begin(115200);
    delay(250);
    while (!Serial && millis() < 3000) {}

    Serial.println("=== CubeLUT3DDemo ===");
    Serial.println("Pipeline: Input -> Transfer Curve -> 3D Cube LUT -> Solver");
    Serial.println();

    // Print memory budget info.
    Serial.println("--- Memory budget (approximate) ---");
    printFitSuggestions(512 * 1024);   // ~512 KB typical heap headroom
#if defined(__IMXRT1062__)
    if (external_psram_size > 0) {
        Serial.print("PSRAM detected: ");
        Serial.print(external_psram_size);
        Serial.println(" MB");
        printFitSuggestions((size_t)external_psram_size * 1024 * 1024);
    } else {
        Serial.println("No PSRAM detected.");
    }
#endif
    Serial.println();

    // Initialise solver with precomputed BFI LUTs.
    solver.attachLUTs(solverValueLUT, solverBFILUT, solverFloorLUT, nullptr, LUT_SIZE);
    solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16);

    // --- Attempt to load a cube, falling through sources ---
    bool cubeLoaded = false;

    // Path 1: SD card (full-size binary cubes).
    if (!cubeLoaded) cubeLoaded = tryLoadFromSD();

    // Path 2: External QSPI flash — see placeholder above.

    // Path 3: Fall back to embedded PROGMEM demo cube.
    if (!cubeLoaded) {
        Serial.println("[Fallback] Loading embedded demo cube...");
        cubeLoaded = loadFromProgmem();
    }

    if (cubeLoaded && cube.isValid()) {
        solver.setCubeLUT3D(&cube);
        solver.setCubeLUT3DEnabled(true);
        Serial.print("\nCube LUT ENABLED: grid=");
        Serial.print(cube.gridSize);
        Serial.print(", ");
        Serial.println(cube.isRGBW() ? "RGBW" : "RGB");
        // NOTE: When receiving frames from HyperHDR with its own RGBW
        // cube applied at runtime, disable the local cube to avoid
        // double-correcting:
        //   solver.setCubeLUT3DEnabled(false);
    } else {
        Serial.println("WARNING: No cube loaded — using classic extraction.");
    }

    // --- Run some test pixels through the pipeline ---
    Serial.println("\n--- Test Pixels ---");
    processTestPixel(52000, 48000, 30000);  // Warm colour
    processTestPixel(10000, 10000, 10000);  // Near-neutral dark
    processTestPixel(65535,     0,     0);  // Pure red
    processTestPixel(32767, 32767, 32767);  // Mid gray

    Serial.println("\n--- BFI Render Demo ---");
}

// ============================================================================
// Loop — BFI phase rendering
// ============================================================================

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
