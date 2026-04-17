// SPDX-License-Identifier: MIT
// Teensy 4.0 ObjectFLED HyperSerial RGBW Driver (AWA protocol)

// Optional A/B switch: enable Q16 input-domain calibration in the solver.
// #define TEMPORAL_TRUE16_ENABLE_INPUT_Q16_CALIBRATION 1
// Optional one-shot exporter: dumps solver_precomputed_luts.h to serial.
// #define DUMP_PRECOMPUTED_LUTS_HEADER 1
#define USER_DEFINED_TEMPORAL_SOLVER_HEADER
#define TEMPORAL_TRUE16_USER_PROVIDED_CALIBRATION
#define TEMPORAL_TRUE16_ENABLE_INPUT_Q16_CALIBRATION
#define ENABLE_TRANSFER_CURVE true


#include <Arduino.h>
#include <ObjectFLED.h>
#include <stdarg.h>
//#include <temporal_runtime_solver_header.h>
//#include "temporal_runtime_solver_header_29_fixed.h"

#include "temporal_runtime_solver_header_temporal_blend_130815_v2.h"

//#include "calibration_profile_true16_patchesv3.h"
//#include "calibration_profile_true16_patches.h"
//#include "calibration_profile_true16_patchesv10.h"
#include "True16_Calibration_21388.h" 


//#define USE_PRECOMPUTED_LUTS // Flash not fast enough given our LED refresh rate of ~500+fps

#include <TemporalBFI.h>
#include <TemporalBFIRuntime.h>


#define APPLY_CURVE_BEFORE_CALIBRATION true

#include "transfer_curve_bt1886_375nit_130815_v2.h"

extern "C" uint32_t set_arm_clock(uint32_t frequency);
extern "C" char* __brkval;
extern "C" unsigned long _ebss;
extern "C" unsigned long _estack;
extern "C" unsigned long _heap_start;
extern "C" unsigned long _heap_end;

//uint32_t speed = 960000000;
uint32_t speed = 960000000; //lowered to 960MHz, tad more stable

static constexpr uint16_t TRANSFER_CURVE_BUCKET_COUNT = TemporalBFITransferCurve::BUCKET_COUNT;
static_assert(
  TRANSFER_CURVE_BUCKET_COUNT >= 2u,
  "transfer curve bucket count must be at least 2");

// Define USE_PRECOMPUTED_LUTS to read solver LUTs from flash instead of
// generating them into RAM/DMAMEM during setup.
#if defined(USE_PRECOMPUTED_LUTS)
#include "solver_precomputed_luts.h"
#define USE_PRECOMPUTED_LUTS_ACTIVE 1
#else
#define USE_PRECOMPUTED_LUTS_ACTIVE 0
#endif

#if USE_PRECOMPUTED_LUTS_ACTIVE && defined(DUMP_PRECOMPUTED_LUTS_HEADER)
#error "DUMP_PRECOMPUTED_LUTS_HEADER requires runtime LUT generation (disable USE_PRECOMPUTED_LUTS)."
#endif

constexpr uint8_t SOLVER_FIXED_BFI_LEVELS = TemporalBFI::SOLVER_FIXED_BFI_LEVELS;

#define ENABLE_RUNTIME_DERIVED_SOLVER_LUT_SIZE true

static constexpr uint16_t DERIVED_SOLVER_LUT_SIZE = TemporalBFIRuntime::SOLVER_LUT_SIZE;
static_assert(DERIVED_SOLVER_LUT_SIZE >= 2u, "Derived solver LUT size must be at least 2");
static constexpr uint16_t SOLVER_LUT_SIZE = DERIVED_SOLVER_LUT_SIZE;

#if USE_PRECOMPUTED_LUTS_ACTIVE
static_assert(
  TemporalBFIPrecomputedSolverLUTs::SOLVER_FIXED_BFI_LEVELS == SOLVER_FIXED_BFI_LEVELS,
  "Precomputed LUT header SOLVER_FIXED_BFI_LEVELS mismatch");

#if defined(TEMPORAL_BFI_PRECOMPUTED_HAS_LUT_SIZE)
static_assert(
  TemporalBFIPrecomputedSolverLUTs::SOLVER_LUT_SIZE == SOLVER_LUT_SIZE,
  "Precomputed LUT header SOLVER_LUT_SIZE mismatch");
#endif

#define solverBFILUT TemporalBFIPrecomputedSolverLUTs::solverBFILUT
#define solverValueLUT TemporalBFIPrecomputedSolverLUTs::solverValueLUT
#if defined(TEMPORAL_BFI_PRECOMPUTED_HAS_FLOOR_LUT)
#define solverValueFloorLUT TemporalBFIPrecomputedSolverLUTs::solverValueFloorLUT
#endif
#else
uint8_t solverBFILUT[4][SOLVER_LUT_SIZE];
DMAMEM uint8_t solverValueLUT[4][SOLVER_LUT_SIZE] = { 0 };
DMAMEM uint8_t solverValueFloorLUT[4][SOLVER_LUT_SIZE] = { 0 };
#endif

TemporalBFI::SolverRuntime solver;
bool runtimeUseDerivedSolverLutSize = ENABLE_RUNTIME_DERIVED_SOLVER_LUT_SIZE;
uint16_t runtimeActiveSolverLutSize = ENABLE_RUNTIME_DERIVED_SOLVER_LUT_SIZE ? DERIVED_SOLVER_LUT_SIZE : SOLVER_LUT_SIZE;

static inline uint16_t clampSolverLutSize(uint16_t value)
{
  if (value < 2u)
    return 2u;
  if (value > SOLVER_LUT_SIZE)
    return SOLVER_LUT_SIZE;
  return value;
}

static inline uint16_t resolveRuntimeSolverLutSize()
{
  return runtimeUseDerivedSolverLutSize ? DERIVED_SOLVER_LUT_SIZE : SOLVER_LUT_SIZE;
}

static inline void refreshRuntimeSolverLutSize()
{
  runtimeActiveSolverLutSize = clampSolverLutSize(resolveRuntimeSolverLutSize());
}

using TemporalBFI::scale8ToQ16;
using TemporalBFI::scaleQ16To8;
using TemporalBFI::scale12ToQ16;
using TemporalBFI::scale4ToQ16;
using TemporalBFI::min3U16;
using TemporalBFI::mulQ16;
using TemporalBFI::lutIndexForSize;

static inline uint16_t applyScaleQ8ToQ16(uint16_t q16, uint16_t scaleQ8)
{
  return TemporalBFI::applyScaleQ8(q16, scaleQ8);
}

static inline size_t lutIndexFromQ16ForSize(uint16_t q16, size_t lutSize)
{
  return TemporalBFI::lutIndexForSize(q16, (uint16_t)lutSize);
}

static inline uint16_t mulQ16U16(uint16_t value, uint16_t scaleQ16)
{
  return TemporalBFI::mulQ16(value, scaleQ16);
}

static inline uint16_t applyTransferCurveQ16(uint16_t q16, uint8_t channel)
{
  return solver.applyTransferCurve(q16, channel);
}

static constexpr uint8_t TRANSFER_CURVE_PROFILE_DISABLED = 0u;
static constexpr uint8_t TRANSFER_CURVE_PROFILE_3_4_NEW = 1u;
static constexpr uint8_t DEFAULT_RUNTIME_TRANSFER_CURVE_PROFILE =
#if ENABLE_TRANSFER_CURVE
  TRANSFER_CURVE_PROFILE_3_4_NEW;
#else
  TRANSFER_CURVE_PROFILE_DISABLED;
#endif
static constexpr uint8_t TRANSFER_CURVE_FLAG_APPLIED_BY_HOST = 0x01u;
static constexpr uint8_t CALIBRATION_FLAG_APPLIED_BY_HOST = 0x02u;

extern bool runtimeTransferCurveAppliedByHostFrame;
extern uint8_t runtimeTransferCurveProfileFrame;
extern bool runtimeCalibrationAppliedByHostFrame;

static inline uint16_t applyTransferCurveProfileQ16(uint16_t q16, uint8_t channel, uint8_t profile)
{
  switch (profile)
  {
    case TRANSFER_CURVE_PROFILE_3_4_NEW:
      return applyTransferCurveQ16(q16, channel);
    default:
      return q16;
  }
}

static inline bool runtimeTransferCurveActiveOnDevice()
{
#if ENABLE_TRANSFER_CURVE
  return runtimeTransferCurveProfileFrame != TRANSFER_CURVE_PROFILE_DISABLED && !runtimeTransferCurveAppliedByHostFrame;
#else
  return false;
#endif
}

static inline uint16_t maybeApplyRuntimeTransferCurveQ16(uint16_t q16, uint8_t channel)
{
  return runtimeTransferCurveActiveOnDevice()
    ? applyTransferCurveProfileQ16(q16, channel, runtimeTransferCurveProfileFrame)
    : q16;
}

static inline bool runtimeCalibrationActiveOnDevice()
{
  return !runtimeCalibrationAppliedByHostFrame;
}

static inline uint16_t maybeApplyRuntimeCalibrationQ16(uint16_t q16, uint8_t channel)
{
  return runtimeCalibrationActiveOnDevice()
    ? TemporalTrue16BFIPolicySolver::calibrateInputQ16ForSolver(q16, channel)
    : q16;
}

extern uint8_t runtimeWhiteLimitActiveFrame;

static inline uint16_t clampWhiteCalibratedQ16(uint16_t wCalQ16)
{
  solver.setCalibrationEnabled(runtimeCalibrationActiveOnDevice());
  solver.setWhiteLimit(runtimeWhiteLimitActiveFrame);
  const auto t = solver.applyWhiteLimit(0, 0, 0, wCalQ16);
  return t.wQ16;
}

static inline uint8_t clampToRuntimeMaxBfi(uint8_t value);

static inline TemporalTrue16BFIPolicySolver::EncodedState solveQ16State(
    uint16_t q16,
    uint8_t channel)
{
  return solver.solve(q16, channel);
}

#if !USE_PRECOMPUTED_LUTS_ACTIVE && defined(DUMP_PRECOMPUTED_LUTS_HEADER)
static void dumpPrecomputedSolverLUTHeader()
{
  solver.dumpLUTHeader(Serial);
}
#endif

#define ENABLE_BFI_SANITY_CHECK false
#define ENABLE_POST_BFI_TRUE16_RESOLVE 0

#define ENABLE_PIPE_DIAGNOSTICS true
#define ENABLE_STATS_MINIMAL true
#define ENABLE_STATS_BFI_DIAGNOSTICS false
#define ENABLE_STATS_PIPE_DIAGNOSTICS false
#define ENABLE_PERIODIC_HYPERSERIAL_STATS true
#define PERIODIC_STATS_INTERVAL_MS 10000UL
#define ENABLE_STAGE_TIMING_STATS true
#define ENABLE_HIGHLIGHT_SHADOW_COMPARE_STATS false

// Pipeline probe for near-black residuals (1..3 codes) through the render path.
#define ENABLE_NEAR_BLACK_DIAGNOSTICS false

// SK6812 power weights (based on Vf × If): R=42mW, G/B/W=62mW
#define POWER_WEIGHT_R 10
#define POWER_WEIGHT_G 15
#define POWER_WEIGHT_B 15
#define POWER_WEIGHT_W 15

#define FORCE_BFI0 false
#define FORCE_BFI1 false
#define FORCE_BFI2 false
#define FORCE_BFI3 false
#define FORCE_BFI4 false

// ---------------- CONFIG ----------------

#define NUM_PINS 25
#define LEDS_PER_PIN 48
#define LED_COUNT (NUM_PINS * LEDS_PER_PIN)
#define SERIAL_BAUD 30000000

#define ENABLE_RAWHID_INPUT true
#if defined(RAWHID_RX_SIZE)
#define RAWHID_REPORT_SIZE RAWHID_RX_SIZE
#else
#define RAWHID_REPORT_SIZE 64
#endif
#define RAWHID_RX_BUDGET_PER_LOOP 48
#define RAWHID_PACKET_MAGIC_0 'H'
#define RAWHID_PACKET_MAGIC_1 'D'
#define RAWHID_LOG_PACKET_MAGIC_1 'L'
#define RAWHID_PACKET_HEADER_SIZE 4
#define ENABLE_RAWHID_LOG_CHANNEL true
#define RAWHID_LOG_SEND_TIMEOUT_MS 0

//original, 1200 LEDs
const uint8_t ledPins[NUM_PINS] = { 1, 2, 3, 4, 6, 5, 7, 8, 9, 10, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 11 };

// ---- BFI MODE CONTROL ----
#define MAX_BFI_FRAMES 4         // hard max black frames (cycle hard max = MAX_BFI_FRAMES + 1)
static_assert(SOLVER_FIXED_BFI_LEVELS == (MAX_BFI_FRAMES + 1), "SOLVER_FIXED_BFI_LEVELS must match MAX_BFI_FRAMES + 1");

#define ENABLE_INPUT_SYNC_CYCLE_CAP true
#define INPUT_SYNC_SPLIT_FPS 90
#define INPUT_SYNC_TARGET_FPS_LOW 60
#define INPUT_SYNC_TARGET_FPS_HIGH 120
#define INPUT_SYNC_MAX_DISPLAY_FPS 480
#define INPUT_SYNC_EWMA_SHIFT 3
#define INPUT_SYNC_CLASS_HYST_FPS 10
#define INPUT_SYNC_CAP_STABLE_FRAMES 20
#define INPUT_SYNC_HIGH_CLASS_MAX_CYCLE MAX_BFI_FRAMES + 1

#define SERIAL_RX_BACKLOG_BYPASS_BYTES 2048
#define SERIAL_RX_BACKLOG_BYPASS_BUDGET_BYTES 6144

// threshold before dimming kicks in
#define ABL_POWER_LIMIT 29803125UL

// PSU / LED electrical parameters (tune to your hardware)
// PSU max current in milliamps (e.g. 200A -> 200000 mA)
#define PSU_MAX_CURRENT_MA 200000UL
// PSU efficiency headroom - accounts for real-world PSU inefficiency
// 85 = 85% efficiency (15% headroom for losses, voltage sag, etc.)
#define PSU_EFFICIENCY_PERCENT 85
// per-channel RGB current at full (mA) - SK6812 datasheet
#define LED_CHANNEL_CURRENT_MA 20U
// white channel current at full (mA) - SK6812 datasheet
#define LED_WHITE_CHANNEL_CURRENT_MA 20U

// ===============================
// PEAK-WINDOW ABL CONFIG
// ===============================

// -------- ABL + HDR PEAK WINDOW --------

#define ENABLE_FRAME_POWER_LIMIT true

#define FRAME_LIMITER_ENTER_Q8 259
#define FRAME_LIMITER_EXIT_Q8 248
#define FRAME_LIMITER_ATTACK_Q8 120
#define FRAME_LIMITER_RELEASE_Q8 26
#define DROOP_START_Q8 294
#define DROOP_MIN_SAG_Q8 210

uint32_t targetFramePower = ABL_POWER_LIMIT;  // tune to PSU
uint16_t frameLimiterScaleQ8 = 256;
uint16_t frameLimiterFeedForwardScaleQ8 = 256;
bool frameLimiterActive = false;

// ---------------- DMA BUFFERS ----------------

DMAMEM uint8_t displayBuffer[LED_COUNT * 4] = {0};
DMAMEM uint8_t latchedFrameBuffer[LED_COUNT * 4] = {0};
DMAMEM uint8_t frameFloorBuffer[LED_COUNT * 4] = {0};
DMAMEM uint8_t latchedFloorFrameBuffer[LED_COUNT * 4] = {0};
uint8_t bfiMapR[LED_COUNT] = {0};
uint8_t bfiMapG[LED_COUNT] = {0};
uint8_t bfiMapB[LED_COUNT] = {0};
uint8_t bfiMapW[LED_COUNT] = {0};

uint8_t bfiPhase = 0;

static constexpr uint16_t HOST_HIGHLIGHT_MASK_BYTES = (LED_COUNT + 7u) / 8u;
uint8_t hostHighlightMaskPending[HOST_HIGHLIGHT_MASK_BYTES] = {0};
uint8_t hostHighlightMaskActive[HOST_HIGHLIGHT_MASK_BYTES] = {0};
bool hostHighlightShadowFrameValid = false;

// Luma weights from measured "max" method dataset.
// normalized_float: R=0.088719000, G=0.330453171, B=0.072570224, W=0.508257605
// Q16 constants are canonical for decision-space math.
static constexpr uint16_t lumaWeightR_Q16 = 5814u;
static constexpr uint16_t lumaWeightG_Q16 = 21656u;
static constexpr uint16_t lumaWeightB_Q16 = 4756u;
static constexpr uint16_t lumaWeightW_Q16 = 33309u;
static constexpr uint32_t lumaWeightSumQ16 =
  (uint32_t)lumaWeightR_Q16 +
  (uint32_t)lumaWeightG_Q16 +
  (uint32_t)lumaWeightB_Q16 +
  (uint32_t)lumaWeightW_Q16;
static constexpr uint32_t lumaWeightRgbSumQ16 =
  (uint32_t)lumaWeightR_Q16 +
  (uint32_t)lumaWeightG_Q16 +
  (uint32_t)lumaWeightB_Q16;
static_assert(lumaWeightSumQ16 == 65535u, "Q16 luma weights must sum to 65535");

uint8_t maxBFIFramesPerChannel[4] = {MAX_BFI_FRAMES, MAX_BFI_FRAMES, MAX_BFI_FRAMES, MAX_BFI_FRAMES}; // G,R,B,W
DMAMEM uint8_t frameBuffer[LED_COUNT * 4] = {0};
uint16_t frameInputQ16[LED_COUNT * 3] = {0};
uint16_t frameInputWQ16[LED_COUNT] = {0};

// Use library constants for BFI phase masks and inverse cycle lengths.
static const uint8_t (&phaseEmitMask)[TemporalBFI::SOLVER_FIXED_BFI_LEVELS] = TemporalBFI::PHASE_EMIT_MASK;
static const uint16_t (&invCycleQ8)[TemporalBFI::SOLVER_FIXED_BFI_LEVELS] = TemporalBFI::INV_CYCLE_Q8;

bool frame_finished_displaying = true;

#if ENABLE_PIPE_DIAGNOSTICS
uint16_t diagRawNonZeroPixels = 0;
uint16_t diagConvertedNonZeroPixels = 0;
uint16_t diagOutputNonZeroPixels = 0;
uint16_t diagOutputWNonZeroPixels = 0;
uint16_t diagOutputNonZeroMaxInCycle = 0;
uint16_t diagOutputWNonZeroMaxInCycle = 0;
uint32_t diagBlackInToConvertedNonZeroFrames = 0;
uint32_t diagBlackInToOutputNonZeroFrames = 0;
uint8_t diagResolvedCycleLen = MAX_BFI_FRAMES + 1;
uint8_t diagCycleCap = MAX_BFI_FRAMES + 1;
#if ENABLE_NEAR_BLACK_DIAGNOSTICS
uint32_t diagNearBlackSrcSubpixels = 0;
uint32_t diagNearBlackOutSubpixels = 0;
uint32_t diagZeroToNonZeroSubpixels = 0;
#endif
#endif
// ---------------- OBJECTFLED ----------------

ObjectFLED leds(
  LED_COUNT,
  displayBuffer,
  CORDER_GRBW,
  NUM_PINS,
  ledPins,
  0);

// ---------------- Per-pixel BFI ----------------

uint64_t renderPowerQ8 = 0;
uint8_t activeBfiCycleLen = MAX_BFI_FRAMES + 1;
uint8_t activeBfiCycleCap = MAX_BFI_FRAMES + 1;
uint32_t inputFrameIntervalUsEwma = 0;
uint32_t lastCommitMicros = 0;
uint32_t inputSignalFpsX100 = 0;
bool inputSyncHighClass = true;
uint8_t inputSyncCapStable = MAX_BFI_FRAMES + 1;
uint8_t inputSyncCapReqCount = 0;

#if ENABLE_STATS_BFI_DIAGNOSTICS
uint32_t diagBlackPixelsAccumG = 0;
uint32_t diagBlackPixelsAccumR = 0;
uint32_t diagBlackPixelsAccumB = 0;
uint32_t diagBlackPixelsAccumW = 0;
uint32_t diagHighlightActiveSamples = 0;
uint32_t diagRenderSamples = 0;
#endif

// ---------------- RUNTIME STATE ----------------

uint8_t globalBrightness = 255;
uint8_t whiteCal = 255;
uint8_t whiteLimit = 255;
uint8_t runtimeWhiteLimit = 255;

uint8_t blackFrameCountdown = 0;
uint8_t runtimeMaxBfiFrames = MAX_BFI_FRAMES;
uint8_t runtimeForcedBfiFromDefines = 0;
uint8_t runtimeForcedBfiFromDefinesEnabled = 0;
bool runtimeSelectedProbeHighlightActive = false;
bool runtimeTransferCurveAppliedByHostFrame = false;
uint8_t runtimeTransferCurveProfileFrame = DEFAULT_RUNTIME_TRANSFER_CURVE_PROFILE;
bool runtimeCalibrationAppliedByHostFrame = false;
bool startupSidebandBootLogsPending = true;
uint8_t startupRuntimeMaxBfi = MAX_BFI_FRAMES;
uint8_t runtimeWhiteLimitActiveFrame = 255;
uint16_t runtimeSelectedProbeLedFrame = 0;


static inline uint8_t resolveRuntimeWhiteLimit()
{
  return runtimeWhiteLimit;
}

static inline uint8_t resolveRuntimeMaxBfiFrames()
{
  if (runtimeMaxBfiFrames > MAX_BFI_FRAMES)
    return MAX_BFI_FRAMES;
  return runtimeMaxBfiFrames;
}

static inline uint8_t clampToRuntimeMaxBfi(uint8_t value)
{
  const uint8_t maxBfi = resolveRuntimeMaxBfiFrames();
  if (value > maxBfi)
    return maxBfi;
  return value;
}

// -------- TELEMETRY --------
struct {
  uint32_t bytesReceived = 0;
  uint32_t lastBytes = 0;
  float incomingMBps = 0.0f;
  float displayFPS = 0.0f;
  float whiteRatio = 0.0f;
  uint32_t framesRgb8 = 0;
  uint32_t framesRgb16 = 0;
  uint32_t framesRgb12Carry = 0;
  uint32_t framesVersion2 = 0;
  char lastInputTransportTag = '-';
  uint64_t rgbwConvertUsTotal = 0;
  uint64_t bfiRenderUsTotal = 0;
  uint64_t powerLimiterUsTotal = 0;
  uint64_t showUsTotal = 0;
  uint32_t rgbwConvertSamples = 0;
  uint32_t bfiRenderSamples = 0;
  uint32_t powerLimiterSamples = 0;
  uint32_t showSamples = 0;
  uint32_t whitePreOnAccum = 0;
  uint32_t whitePreHighAccum = 0;
  uint32_t whitePreToggleAccum = 0;
  uint32_t whitePreLevelAccum = 0;
  uint32_t whiteDiagSamples = 0;
  uint32_t baselineClampCount = 0;
  uint32_t sceneOffsetChangeCount = 0;
  uint32_t sceneShapedAccum = 0;
  uint32_t sceneUpdateSamples = 0;
  uint32_t highlightShadowFrames = 0;
  uint32_t hostShadowHighlightAccum = 0;
  uint32_t localShadowHighlightAccum = 0;
  uint32_t shadowMismatchAccum = 0;
  uint32_t shadowHostOnlyAccum = 0;
  uint32_t shadowLocalOnlyAccum = 0;
  uint32_t postBfiResolveChannelAccum = 0;
  uint32_t postBfiResolvePixelAccum = 0;
  uint32_t highlightTriggeredAccum = 0;
  uint32_t highlightRolloffActiveAccum = 0;
  uint32_t frameLimiterControlSamples = 0;
  uint32_t frameLimiterActiveFrames = 0;
  uint32_t frameLimiterLastPower = 0;
  uint32_t frameLimiterMaxPower = 0;
  uint16_t frameLimiterLastScaleQ8 = 256;
  uint16_t frameLimiterMinScaleQ8 = 256;
  uint32_t heapUsedBytes = 0;
  uint32_t heapFreeBytes = 0;
  uint32_t stackGapBytes = 0;
  uint32_t minStackGapBytes = 0;
} telemetry;

static inline uintptr_t currentStackPointer()
{
  uintptr_t stackPointer = 0;
  __asm__ volatile("mov %0, sp" : "=r"(stackPointer));
  return stackPointer;
}

static inline void sampleRam1Telemetry()
{
  const uintptr_t heapStart = (uintptr_t)&_heap_start;
  const uintptr_t heapEnd = (uintptr_t)&_heap_end;
  uintptr_t heapCurrent = (uintptr_t)__brkval;
  if (heapCurrent < heapStart)
    heapCurrent = heapStart;
  if (heapCurrent > heapEnd)
    heapCurrent = heapEnd;

  const uintptr_t stackBase = (uintptr_t)&_ebss;
  const uintptr_t stackTop = (uintptr_t)&_estack;
  uintptr_t stackPointer = currentStackPointer();
  if (stackPointer < stackBase)
    stackPointer = stackBase;
  if (stackPointer > stackTop)
    stackPointer = stackTop;

  const uint32_t heapUsedBytes = (uint32_t)(heapCurrent - heapStart);
  const uint32_t heapFreeBytes = (uint32_t)(heapEnd - heapCurrent);
  const uint32_t stackGapBytes = (uint32_t)(stackPointer - stackBase);

  telemetry.heapUsedBytes = heapUsedBytes;
  telemetry.heapFreeBytes = heapFreeBytes;
  telemetry.stackGapBytes = stackGapBytes;
  if (telemetry.minStackGapBytes == 0 || stackGapBytes < telemetry.minStackGapBytes)
    telemetry.minStackGapBytes = stackGapBytes;
}
 
// ---------------- ABL STATE ----------------

static inline uint16_t estimatePixelPower(uint8_t r, uint8_t g, uint8_t b, uint8_t w, uint8_t bfiRemaining, uint8_t maxBfi) {
  // white channel typically draws more current
  const uint16_t WR = 3;  // weight RGB
  const uint16_t WW = 5;  // weight W

  uint16_t p = WR * (r + g + b) + WW * w;

  // duty scaling due to BFI
  uint8_t shown = (maxBfi + 1) - bfiRemaining;
  uint8_t total = (maxBfi + 1);
  p = (p * shown) / total;

  return p;
}

static inline uint16_t normalizeInputQ16(uint16_t valueQ16, bool sourceIs16Bit)
{
  if (sourceIs16Bit)
    return valueQ16;

  // Legacy 8-bit AWA packets may flow through as raw 0..255 values.
  // Upscale to full Q16 domain when protocol marker indicates 8-bit payload.
  if (valueQ16 <= 255u)
    return (uint16_t)(((valueQ16 & 0xFFu) << 8) | (valueQ16 & 0xFFu));

  return valueQ16;
}

static inline uint16_t addMod255Fast(uint16_t acc, uint16_t value)
{
  acc = (uint16_t)(acc + value);
  if (acc >= 255u)
    acc = (uint16_t)(acc - 255u);
  if (acc >= 255u)
    acc = (uint16_t)(acc - 255u);
  return acc;
}

// ---------------- STATS ----------------

struct {
  uint32_t totalFrames = 0;
  uint32_t goodFrames = 0;
  uint32_t shownFrames = 0;
  uint32_t errors = 0;
  uint32_t lastPrint = 0;
} stats;

// ---------------- AWA STATE MACHINE ----------------

enum class AwaProtocol {
  HEADER_A,
  HEADER_w,
  HEADER_a,
  HEADER_HI,
  HEADER_LO,
  HEADER_CRC,

  RED,
  GREEN,
  BLUE,
  WHITE12,
  CARRY12_RG,
  CARRY12_B,

  RED16_HI,
  RED16_LO,
  GREEN16_HI,
  GREEN16_LO,
  BLUE16_HI,
  BLUE16_LO,
  WHITE16_HI,
  WHITE16_LO,

  VERSION2_GAIN,
  VERSION2_RED,
  VERSION2_GREEN,
  VERSION2_BLUE,

  POLICY_SCENE_MAGIC,
  POLICY_SCENE_OFFSET,
  POLICY_SCENE_RESERVED0,
  POLICY_SCENE_RESERVED1,
  POLICY_HIGHLIGHT_MASK,
  TRANSFER_FLAGS,
  TRANSFER_PROFILE,

  FLETCHER1,
  FLETCHER2,
  FLETCHER_EXT
};

struct FrameState {

  AwaProtocol state = AwaProtocol::HEADER_A;

  bool protocolV2 = false;
  bool protocolRgb16 = false;
  bool protocolRgb12Carry = false;
  bool protocolHostRgbw = false;
  bool protocolScenePolicy = false;
  bool protocolHighlightShadow = false;
  bool protocolTransferConfig = false;

  uint8_t crc = 0;
  uint16_t count = 0;
  uint16_t currentLed = 0;

  uint16_t f1 = 0, f2 = 0, fext = 0;
  uint8_t pos = 0;

	uint8_t r, g, b, w;
  uint16_t r16, g16, b16, w16;
  uint8_t rgCarry = 0;
  uint8_t bCarryReserved = 0;
  uint8_t hiByte = 0;
  uint8_t transferCurveFlags = 0u;
  uint8_t transferCurveProfile = DEFAULT_RUNTIME_TRANSFER_CURVE_PROFILE;

  struct {
    uint8_t gain = 255;
    uint8_t red = 255;
    uint8_t green = 255;
    uint8_t blue = 255;
  } incomingCal;

  uint16_t highlightMaskByteIndex = 0;
  bool highlightShadowValid = false;

  void setProtocolVersion2(bool v) {
    protocolV2 = v;
  }
  bool isProtocolVersion2() {
    return protocolV2;
  }

  void setProtocolRgb16(bool v) {
    protocolRgb16 = v;
  }
  bool isProtocolRgb16() {
    return protocolRgb16;
  }

  void setProtocolRgb12Carry(bool v) {
    protocolRgb12Carry = v;
  }
  bool isProtocolRgb12Carry() {
    return protocolRgb12Carry;
  }

  void setProtocolHostRgbw(bool v) {
    protocolHostRgbw = v;
  }
  bool isProtocolHostRgbw() {
    return protocolHostRgbw;
  }

  void setProtocolScenePolicy(bool v) {
    protocolScenePolicy = v;
  }
  bool isProtocolScenePolicy() {
    return protocolScenePolicy;
  }

  void setProtocolHighlightShadow(bool v) {
    protocolHighlightShadow = v;
  }
  bool isProtocolHighlightShadow() {
    return protocolHighlightShadow;
  }

  void setProtocolTransferConfig(bool v) {
    protocolTransferConfig = v;
  }
  bool isProtocolTransferConfig() {
    return protocolTransferConfig;
  }

  bool isProtocolTransferCurveAppliedByHost() {
    return (transferCurveFlags & TRANSFER_CURVE_FLAG_APPLIED_BY_HOST) != 0u;
  }

  bool isProtocolCalibrationAppliedByHost() {
    return (transferCurveFlags & CALIBRATION_FLAG_APPLIED_BY_HOST) != 0u;
  }

  uint8_t getProtocolTransferCurveProfile() {
    return transferCurveProfile;
  }

  void resetScenePolicy() {
    highlightMaskByteIndex = 0;
    highlightShadowValid = false;
  }

  void init(uint8_t hi) {
    currentLed = 0;
    count = hi * 256;
    crc = hi;
    f1 = f2 = fext = 0;
    pos = 0;
    transferCurveFlags = 0u;
    transferCurveProfile = DEFAULT_RUNTIME_TRANSFER_CURVE_PROFILE;
    resetScenePolicy();
#if ENABLE_PIPE_DIAGNOSTICS
    diagRawNonZeroPixels = 0;
#endif
  }

  void computeCRC(uint8_t lo) {
    count += lo;
    crc ^= lo ^ 0x55;
  }

  void addFletcher(uint8_t v) {
    f1 = addMod255Fast(f1, v);
    f2 = addMod255Fast(f2, f1);
    fext = addMod255Fast(fext, (uint16_t)(v ^ pos++));
  }

  uint8_t getF1() {
    return f1;
  }
  uint8_t getF2() {
    return f2;
  }
  uint8_t getFext() {
    return (fext != 0x41) ? fext : 0xaa;
  }

  void applyIncomingCalibration(uint8_t &r, uint8_t &g, uint8_t &b) {
    r = (r * incomingCal.red) >> 8;
    g = (g * incomingCal.green) >> 8;
    b = (b * incomingCal.blue) >> 8;

    whiteLimit = incomingCal.gain;
  }

} frameState;

static inline char currentInputTransportTag()
{
  if (frameState.isProtocolTransferConfig())
    return frameState.isProtocolHostRgbw() ? 'T' : 't';
  if (frameState.isProtocolHostRgbw())
    return frameState.isProtocolHighlightShadow() ? (frameState.isProtocolRgb12Carry() ? 'G' : 'F') : (frameState.isProtocolScenePolicy() ? (frameState.isProtocolRgb12Carry() ? 'E' : 'D') : (frameState.isProtocolRgb12Carry() ? 'C' : 'W'));
  if (frameState.isProtocolHighlightShadow())
    return frameState.isProtocolRgb12Carry() ? 'g' : 'f';
  if (frameState.isProtocolScenePolicy())
    return frameState.isProtocolRgb12Carry() ? 'e' : 'd';
  if (frameState.isProtocolRgb12Carry())
    return frameState.isProtocolVersion2() ? 'C' : 'c';
  if (frameState.isProtocolRgb16())
    return frameState.isProtocolVersion2() ? 'B' : 'b';
  return frameState.isProtocolVersion2() ? 'A' : 'a';
}

static inline void recordCommittedInputTransportFrame()
{
  const char transportTag = currentInputTransportTag();
  telemetry.lastInputTransportTag = transportTag;

  if (frameState.isProtocolRgb12Carry())
    telemetry.framesRgb12Carry++;
  else if (frameState.isProtocolRgb16())
    telemetry.framesRgb16++;
  else
    telemetry.framesRgb8++;

  if (frameState.isProtocolVersion2())
    telemetry.framesVersion2++;
}

static inline uint16_t resolveSelectedProbeLedIndex()
{
  // Calibration-side selected-index probing was removed with sideband gain packets.
  (void)LED_COUNT;
  return 0;
}

static inline void initRuntimeForcedBfiFromDefines()
{
  runtimeForcedBfiFromDefines = 0;
  runtimeForcedBfiFromDefinesEnabled = 0;

#if FORCE_BFI0
  runtimeForcedBfiFromDefines = 0;
  runtimeForcedBfiFromDefinesEnabled = 1;
#endif
#if FORCE_BFI1
  runtimeForcedBfiFromDefines = 1;
  runtimeForcedBfiFromDefinesEnabled = 1;
#endif
#if FORCE_BFI2
  runtimeForcedBfiFromDefines = 2;
  runtimeForcedBfiFromDefinesEnabled = 1;
#endif
#if FORCE_BFI3
  runtimeForcedBfiFromDefines = 3;
  runtimeForcedBfiFromDefinesEnabled = 1;
#endif
#if FORCE_BFI4
  runtimeForcedBfiFromDefines = 4;
  runtimeForcedBfiFromDefinesEnabled = 1;
#endif

  if (runtimeForcedBfiFromDefinesEnabled)
    runtimeForcedBfiFromDefines = clampToRuntimeMaxBfi(runtimeForcedBfiFromDefines);
}

static inline bool resolveEffectiveForcedBfi(uint8_t &forcedBfi)
{
  if (runtimeForcedBfiFromDefinesEnabled)
  {
    forcedBfi = clampToRuntimeMaxBfi(runtimeForcedBfiFromDefines);
    return true;
  }

  return false;
}

void resetRuntimeBfiGainStateToDefaults()
{
  runtimeWhiteLimit = 255;
  whiteLimit = runtimeWhiteLimit;
  runtimeMaxBfiFrames = MAX_BFI_FRAMES;
  runtimeUseDerivedSolverLutSize = ENABLE_RUNTIME_DERIVED_SOLVER_LUT_SIZE;
  refreshRuntimeSolverLutSize();
  initRuntimeForcedBfiFromDefines();
}

inline void updateInputSignalEstimate()
{
  uint32_t nowUs = micros();

  if (lastCommitMicros != 0)
  {
    uint32_t dtUs = nowUs - lastCommitMicros;

    if (dtUs > 0 && dtUs < 2000000UL)
    {
      if (inputFrameIntervalUsEwma == 0)
      {
        inputFrameIntervalUsEwma = dtUs;
      }
      else
      {
        inputFrameIntervalUsEwma =
          (((inputFrameIntervalUsEwma << INPUT_SYNC_EWMA_SHIFT) - inputFrameIntervalUsEwma) + dtUs) >> INPUT_SYNC_EWMA_SHIFT;
      }

      if (inputFrameIntervalUsEwma > 0)
        inputSignalFpsX100 = 100000000UL / inputFrameIntervalUsEwma;
    }
  }

  lastCommitMicros = nowUs;
}

inline uint8_t resolveInputSyncCycleCap()
{
#if !ENABLE_INPUT_SYNC_CYCLE_CAP
  return resolveRuntimeMaxBfiFrames() + 1;
#else
  const uint8_t runtimeMaxBfi = resolveRuntimeMaxBfiFrames();
  if (inputSignalFpsX100 == 0)
    return runtimeMaxBfi + 1;

  uint32_t inputFps = (inputSignalFpsX100 + 50UL) / 100UL;
  if (inputFps == 0) inputFps = 1;

  const uint32_t splitLo = (INPUT_SYNC_SPLIT_FPS > INPUT_SYNC_CLASS_HYST_FPS)
    ? (INPUT_SYNC_SPLIT_FPS - INPUT_SYNC_CLASS_HYST_FPS)
    : 1;
  const uint32_t splitHi = INPUT_SYNC_SPLIT_FPS + INPUT_SYNC_CLASS_HYST_FPS;

  if (inputSyncHighClass)
  {
    if (inputFps < splitLo) inputSyncHighClass = false;
  }
  else
  {
    if (inputFps > splitHi) inputSyncHighClass = true;
  }

  uint32_t classFps = inputSyncHighClass ? INPUT_SYNC_TARGET_FPS_HIGH : INPUT_SYNC_TARGET_FPS_LOW;
  if (classFps == 0) classFps = 1;

  uint32_t requestedBlackFrames = INPUT_SYNC_MAX_DISPLAY_FPS / classFps;
  const uint32_t hardMaxBfi = (uint32_t)runtimeMaxBfi;
  if (requestedBlackFrames > hardMaxBfi) requestedBlackFrames = hardMaxBfi;

  uint32_t requestedCap = requestedBlackFrames + 1u;

  if (inputSyncHighClass)
  {
    uint32_t highClassMaxCycle = INPUT_SYNC_HIGH_CLASS_MAX_CYCLE;
    if (highClassMaxCycle < 1u) highClassMaxCycle = 1u;
    const uint32_t hardMaxCycle = hardMaxBfi + 1u;
    if (highClassMaxCycle > hardMaxCycle)
      highClassMaxCycle = hardMaxCycle; 

    if (requestedCap > highClassMaxCycle)
      requestedCap = highClassMaxCycle;
  }

  if (requestedCap != inputSyncCapStable)
  {
    if (inputSyncCapReqCount < 255) inputSyncCapReqCount++;

    if (inputSyncCapReqCount >= INPUT_SYNC_CAP_STABLE_FRAMES)
    {
      inputSyncCapStable = (uint8_t)requestedCap;
      inputSyncCapReqCount = 0;
    }
  }
  else
  {
    inputSyncCapReqCount = 0;
  }

  return inputSyncCapStable;
#endif
}

inline void rgbToRgbw(uint16_t index, uint16_t rInputQ16, uint16_t gInputQ16, uint16_t bInputQ16, bool sourceIs16Bit) {
  if (index >= LED_COUNT) return;

  const bool useHostDerivedWhite = frameState.isProtocolHostRgbw();
  uint16_t wQ16 = 0u;

  rInputQ16 = normalizeInputQ16(rInputQ16, sourceIs16Bit);
  gInputQ16 = normalizeInputQ16(gInputQ16, sourceIs16Bit);
  bInputQ16 = normalizeInputQ16(bInputQ16, sourceIs16Bit);

  const uint16_t gShapedQ16 = maybeApplyRuntimeTransferCurveQ16(gInputQ16, 0);
  const uint16_t rShapedQ16 = maybeApplyRuntimeTransferCurveQ16(rInputQ16, 1);
  const uint16_t bShapedQ16 = maybeApplyRuntimeTransferCurveQ16(bInputQ16, 2);

  uint16_t gQ16 = 0u;
  uint16_t rQ16 = 0u;
  uint16_t bQ16 = 0u;

  if (useHostDerivedWhite)
  {
    const uint16_t wInputQ16 = frameInputWQ16[index];
    const uint16_t wShapedQ16 = maybeApplyRuntimeTransferCurveQ16(wInputQ16, 4);

    gQ16 = maybeApplyRuntimeCalibrationQ16(gShapedQ16, 0);
    rQ16 = maybeApplyRuntimeCalibrationQ16(rShapedQ16, 1);
    bQ16 = maybeApplyRuntimeCalibrationQ16(bShapedQ16, 2);
    wQ16 = clampWhiteCalibratedQ16(
        maybeApplyRuntimeCalibrationQ16(wShapedQ16, 3));
  }
  else
  {
    solver.setCalibrationEnabled(runtimeCalibrationActiveOnDevice());
    solver.setWhiteLimit(runtimeWhiteLimitActiveFrame);
    const auto rgbw = solver.extractRgbw(rShapedQ16, gShapedQ16, bShapedQ16);
    gQ16 = rgbw.gQ16;
    rQ16 = rgbw.rQ16;
    bQ16 = rgbw.bQ16;
    wQ16 = rgbw.wQ16;
  }

  // Feed ABL decisions back into the calibrated true16 solve path.
  // This keeps limiter-related brightness changes aligned with LUT behavior.
  const uint16_t ablScaleQ8 = frameLimiterFeedForwardScaleQ8;
  if (ablScaleQ8 < 256u)
  {
    gQ16 = applyScaleQ8ToQ16(gQ16, ablScaleQ8);
    rQ16 = applyScaleQ8ToQ16(rQ16, ablScaleQ8);
    bQ16 = applyScaleQ8ToQ16(bQ16, ablScaleQ8);
    wQ16 = applyScaleQ8ToQ16(wQ16, ablScaleQ8);
  }

  auto gBase = solveQ16State(gQ16, 0);
  auto rBase = solveQ16State(rQ16, 1);
  auto bBase = solveQ16State(bQ16, 2);
  auto wBase = solveQ16State(wQ16, 3);

  // Commit frame + floor buffers and BFI maps via library.
  TemporalBFI::SolverRuntime::commitPixelRGBW(
      frameBuffer, frameFloorBuffer,
      bfiMapG, bfiMapR, bfiMapB, bfiMapW,
      index, gBase, rBase, bBase, wBase);

  // Apply runtime BFI overrides after commit.
  bfiMapR[index] = clampToRuntimeMaxBfi(bfiMapR[index]);
  bfiMapG[index] = clampToRuntimeMaxBfi(bfiMapG[index]);
  bfiMapB[index] = clampToRuntimeMaxBfi(bfiMapB[index]);
  bfiMapW[index] = clampToRuntimeMaxBfi(bfiMapW[index]);

  uint8_t forcedBfi = 0;
  if (resolveEffectiveForcedBfi(forcedBfi))
  {
    bfiMapR[index] = forcedBfi;
    bfiMapG[index] = forcedBfi;
    bfiMapB[index] = forcedBfi;
    bfiMapW[index] = forcedBfi;
  }

#if ENABLE_PIPE_DIAGNOSTICS
  if (gBase.value | rBase.value | bBase.value | wBase.value) {
    if (diagConvertedNonZeroPixels < LED_COUNT) diagConvertedNonZeroPixels++;
  }
#endif

}

void processFrameRGBWBatch()
{
  const bool sourceIs16Bit = frameState.isProtocolRgb16() || frameState.isProtocolRgb12Carry();

  for (uint16_t i = 0, q = 0; i < LED_COUNT; i += 4, q += 12)
    {
        rgbToRgbw(i+0,
      frameInputQ16[q + 0],
      frameInputQ16[q + 1],
      frameInputQ16[q + 2],
      sourceIs16Bit);

        rgbToRgbw(i+1,
      frameInputQ16[q + 3],
      frameInputQ16[q + 4],
      frameInputQ16[q + 5],
      sourceIs16Bit);

        rgbToRgbw(i+2,
      frameInputQ16[q + 6],
      frameInputQ16[q + 7],
      frameInputQ16[q + 8],
      sourceIs16Bit);

        rgbToRgbw(i+3,
      frameInputQ16[q + 9],
      frameInputQ16[q + 10],
      frameInputQ16[q + 11],
      sourceIs16Bit);
    }
}

// ---------------- FRAME COMMIT ----------------

void commitFrame() {
  recordCommittedInputTransportFrame();
  runtimeSelectedProbeHighlightActive = false;
  runtimeTransferCurveAppliedByHostFrame = frameState.isProtocolTransferCurveAppliedByHost();
  runtimeCalibrationAppliedByHostFrame = frameState.isProtocolCalibrationAppliedByHost();
  runtimeTransferCurveProfileFrame = frameState.getProtocolTransferCurveProfile();
  runtimeWhiteLimitActiveFrame = resolveRuntimeWhiteLimit();
  runtimeSelectedProbeLedFrame = resolveSelectedProbeLedIndex();

#if ENABLE_PIPE_DIAGNOSTICS
  diagConvertedNonZeroPixels = 0;
  diagOutputNonZeroMaxInCycle = 0;
  diagOutputWNonZeroMaxInCycle = 0;
#endif

  // Convert raw frameBuffer in-place to processed RGBW + per-channel BFI decisions.
#if ENABLE_STAGE_TIMING_STATS
  const uint32_t rgbwConvertStartUs = micros();
#endif
  processFrameRGBWBatch();
#if ENABLE_STAGE_TIMING_STATS
  telemetry.rgbwConvertUsTotal += (uint64_t)(micros() - rgbwConvertStartUs);
  telemetry.rgbwConvertSamples++;
#endif

  // Render stage consumes latchedFrameBuffer; latch the processed frame, not raw input.
  memcpy(latchedFrameBuffer, frameBuffer, sizeof(latchedFrameBuffer));
  memcpy(latchedFloorFrameBuffer, frameFloorBuffer, sizeof(latchedFloorFrameBuffer));

  updateInputSignalEstimate();

#if ENABLE_PIPE_DIAGNOSTICS
  if (diagRawNonZeroPixels == 0 && diagConvertedNonZeroPixels > 0) {
    diagBlackInToConvertedNonZeroFrames++;
  }
#endif

  blackFrameCountdown = 0;
  stats.goodFrames++;
}

// ---------------- HYPERSERIAL OUTPUT ----------------

void serialMonitorPrint(const char* text);
void serialMonitorPrintln(const char* text);
void serialMonitorPrintf(const char* format, ...);

static inline void rawHidLogWriteBuffer(const uint8_t* data, size_t length)
{
#if ENABLE_RAWHID_LOG_CHANNEL && (defined(USB_RAWHID) || defined(RAWHID_INTERFACE))
  if (!data || length == 0)
    return;

  if (RAWHID_REPORT_SIZE <= RAWHID_PACKET_HEADER_SIZE)
    return;

  static uint8_t report[RAWHID_REPORT_SIZE];
  const uint16_t payloadCapacity = (uint16_t)(RAWHID_REPORT_SIZE - RAWHID_PACKET_HEADER_SIZE);

  while (length > 0)
  {
    const uint16_t chunk = (length > payloadCapacity)
                             ? payloadCapacity
                             : (uint16_t)length;

    memset(report, 0, sizeof(report));
    report[0] = (uint8_t)RAWHID_PACKET_MAGIC_0;
    report[1] = (uint8_t)RAWHID_LOG_PACKET_MAGIC_1;
    report[2] = (uint8_t)((chunk >> 8) & 0xFF);
    report[3] = (uint8_t)(chunk & 0xFF);
    memcpy(report + RAWHID_PACKET_HEADER_SIZE, data, chunk);

    const int sent = RawHID.send(report, RAWHID_LOG_SEND_TIMEOUT_MS);
    if (sent <= 0)
      break;

    data += chunk;
    length -= chunk;
  }
#else
  (void)data;
  (void)length;
#endif
}

static inline void rawHidLogWriteLineBreak()
{
  static const uint8_t lineBreak[] = {'\n'};
  rawHidLogWriteBuffer(lineBreak, sizeof(lineBreak));
}

void hyperSerialPrintln(const char* text)
{
  if (!text)
    text = "";
  Serial.println(text);
  rawHidLogWriteBuffer((const uint8_t*)text, strlen(text));
  rawHidLogWriteLineBreak();
}

void hyperSerialPrint(const char* text)
{
  if (!text)
    return;
  Serial.print(text);
  rawHidLogWriteBuffer((const uint8_t*)text, strlen(text));
}

void hyperSerialPrintf(const char* format, ...)
{
  if (!format)
    return;

  char buffer[192];
  va_list args;
  va_start(args, format);
  const int written = vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);

  if (written <= 0)
    return;

  const size_t count = (written >= (int)sizeof(buffer))
                         ? (sizeof(buffer) - 1)
                         : (size_t)written;
  Serial.write((const uint8_t*)buffer, count);
  rawHidLogWriteBuffer((const uint8_t*)buffer, count);
}

void printHyperSerialWelcome() {
  hyperSerialPrintln("Awa driver HyperSerialTeensy");
  hyperSerialPrintln("\r\nHyperSerial Teensy 4.0 ObjectFLED");
  hyperSerialPrintln("Protocol: AWA RGBW");
  hyperSerialPrintln("Status: Ready");
}

void printBFIClampConfig() {
  char out[192];
  snprintf(out, sizeof(out),
           "BFI config | true16 LUT solve path active | solverLut active=%u alloc=%u derived=%u mode=%s transferBuckets=%u\r\n",
           (unsigned)runtimeActiveSolverLutSize,
           (unsigned)SOLVER_LUT_SIZE,
           (unsigned)DERIVED_SOLVER_LUT_SIZE,
           runtimeUseDerivedSolverLutSize ? "derived" : "full",
           (unsigned)TRANSFER_CURVE_BUCKET_COUNT);
  serialMonitorPrint(out);
}

void printHyperSerialStats() {
  char out[512];
  sampleRam1Telemetry();
  uint32_t now = millis();
  uint32_t elapsedMs = now - stats.lastPrint;
  if (elapsedMs == 0) elapsedMs = 1;

  uint32_t displayFpsX100 = (stats.shownFrames * 100000UL) / elapsedMs;
  uint32_t inputFpsX100 = (stats.goodFrames * 100000UL) / elapsedMs;

  uint32_t avgRgbwConvertUs = 0;
  uint32_t avgRenderUs = 0;
  uint32_t avgPowerLimiterUs = 0;
  uint32_t avgShowUs = 0;
  uint32_t avgHostShadowHighlights = 0;
  uint32_t avgLocalShadowHighlights = 0;
  uint32_t avgShadowMismatch = 0;
  uint32_t avgPostBfiResolveChannels = 0;
  uint32_t avgPostBfiResolvePixels = 0;
  uint32_t avgHighlightTriggered = 0;
  uint32_t avgHighlightRolloffActive = 0;
  const uint32_t frameLimiterControlSamples = telemetry.frameLimiterControlSamples;
  const uint32_t frameLimiterActiveFrames = telemetry.frameLimiterActiveFrames;
  const uint32_t frameLimiterLastPower = telemetry.frameLimiterLastPower;
  const uint32_t frameLimiterMaxPower = telemetry.frameLimiterMaxPower;
  const uint16_t frameLimiterLastScaleQ8 = telemetry.frameLimiterLastScaleQ8;
  const uint16_t frameLimiterMinScaleQ8 = telemetry.frameLimiterMinScaleQ8;
  const uint32_t heapUsedBytes = telemetry.heapUsedBytes;
  const uint32_t heapFreeBytes = telemetry.heapFreeBytes;
  const uint32_t stackGapBytes = telemetry.stackGapBytes;
  const uint32_t minStackGapBytes = telemetry.minStackGapBytes;
  const uint32_t rxBytes = telemetry.bytesReceived;
  const uint32_t rxKBpsX100 = (rxBytes * 100UL) / elapsedMs;
  const char lastTransportTag = telemetry.lastInputTransportTag;
  if (telemetry.highlightShadowFrames > 0)
  {
    avgHostShadowHighlights = telemetry.hostShadowHighlightAccum / telemetry.highlightShadowFrames;
    avgLocalShadowHighlights = telemetry.localShadowHighlightAccum / telemetry.highlightShadowFrames;
    avgShadowMismatch = telemetry.shadowMismatchAccum / telemetry.highlightShadowFrames;
  }
  if (telemetry.rgbwConvertSamples > 0)
  {
    avgPostBfiResolveChannels = telemetry.postBfiResolveChannelAccum / telemetry.rgbwConvertSamples;
    avgPostBfiResolvePixels = telemetry.postBfiResolvePixelAccum / telemetry.rgbwConvertSamples;
    avgHighlightTriggered = telemetry.highlightTriggeredAccum / telemetry.rgbwConvertSamples;
    avgHighlightRolloffActive = telemetry.highlightRolloffActiveAccum / telemetry.rgbwConvertSamples;
  }
#if ENABLE_STAGE_TIMING_STATS
  if (telemetry.rgbwConvertSamples > 0)
    avgRgbwConvertUs = (uint32_t)(telemetry.rgbwConvertUsTotal / telemetry.rgbwConvertSamples);
  if (telemetry.bfiRenderSamples > 0)
    avgRenderUs = (uint32_t)(telemetry.bfiRenderUsTotal / telemetry.bfiRenderSamples);
  if (telemetry.powerLimiterSamples > 0)
    avgPowerLimiterUs = (uint32_t)(telemetry.powerLimiterUsTotal / telemetry.powerLimiterSamples);
  if (telemetry.showSamples > 0)
    avgShowUs = (uint32_t)(telemetry.showUsTotal / telemetry.showSamples);
#endif

#if ENABLE_STATS_BFI_DIAGNOSTICS
  uint32_t samples = (diagRenderSamples == 0) ? 1 : diagRenderSamples;
  uint16_t avgBlackG = (uint16_t)(diagBlackPixelsAccumG / samples);
  uint16_t avgBlackR = (uint16_t)(diagBlackPixelsAccumR / samples);
  uint16_t avgBlackB = (uint16_t)(diagBlackPixelsAccumB / samples);
  uint16_t avgBlackW = (uint16_t)(diagBlackPixelsAccumW / samples);
  uint8_t highlightPct = (uint8_t)((diagHighlightActiveSamples * 100UL) / samples);
#endif

#if ENABLE_STATS_MINIMAL
  snprintf(out, sizeof(out),
           "HyperSerialTeensy | fps:%lu.%02lu ifps:%lu.%02lu cy:%u cap:%u err:%lu rx:%lu.%02luKB/s m:%c 8:%lu 12:%lu 16:%lu v2:%lu sh:h%lu l%lu m%lu so:%d cv:rc%lu rp%lu ht%lu hr%lu abl:af%lu/%lu sc%u mn%u p%lu mx%lu tg%lu mem:hu%lu hf%lu sg%lu mn%lu us:c%lu r%lu a%lu s%lu\r\n",
           displayFpsX100 / 100,
           displayFpsX100 % 100,
           inputFpsX100 / 100,
           inputFpsX100 % 100,
           diagResolvedCycleLen,
           diagCycleCap,
           stats.errors,
           rxKBpsX100 / 100,
           rxKBpsX100 % 100,
           lastTransportTag,
           telemetry.framesRgb8,
           telemetry.framesRgb12Carry,
           telemetry.framesRgb16,
           telemetry.framesVersion2,
           avgHostShadowHighlights,
           avgLocalShadowHighlights,
           avgShadowMismatch,
           0,
           avgPostBfiResolveChannels,
           avgPostBfiResolvePixels,
           avgHighlightTriggered,
           avgHighlightRolloffActive,
           frameLimiterActiveFrames,
           frameLimiterControlSamples,
           frameLimiterLastScaleQ8,
           frameLimiterMinScaleQ8,
           frameLimiterLastPower,
           frameLimiterMaxPower,
           targetFramePower,
           heapUsedBytes,
           heapFreeBytes,
           stackGapBytes,
           minStackGapBytes,
           avgRgbwConvertUs,
           avgRenderUs,
           avgPowerLimiterUs,
           avgShowUs);
#elif ENABLE_STATS_BFI_DIAGNOSTICS
  snprintf(out, sizeof(out),
           "HyperSerialTeensy | fps:%lu.%02lu ifps:%lu.%02lu cy:%u cap:%u bk:g%u r%u b%u w%u hl:%u%% err:%lu rx:%lu.%02luKB/s m:%c 8:%lu 12:%lu 16:%lu v2:%lu sh:h%lu l%lu m%lu\r\n",
           displayFpsX100 / 100,
           displayFpsX100 % 100,
           inputFpsX100 / 100,
           inputFpsX100 % 100,
           diagResolvedCycleLen,
           diagCycleCap,
           avgBlackG,
           avgBlackR,
           avgBlackB,
           avgBlackW,
           highlightPct,
           stats.errors,
           rxKBpsX100 / 100,
           rxKBpsX100 % 100,
           lastTransportTag,
           telemetry.framesRgb8,
           telemetry.framesRgb12Carry,
           telemetry.framesRgb16,
           telemetry.framesVersion2,
           avgHostShadowHighlights,
           avgLocalShadowHighlights,
           avgShadowMismatch);
#elif ENABLE_STATS_PIPE_DIAGNOSTICS
  snprintf(out, sizeof(out),
           "HyperSerialTeensy | fps:%lu.%02lu ifps:%lu.%02lu cy:%u cap:%u err:%lu rz:%u cz:%u oz:%u ow:%u br:%lu bo:%lu nbs:%lu nbo:%lu z2n:%lu rx:%lu.%02luKB/s m:%c 8:%lu 12:%lu 16:%lu v2:%lu sh:h%lu l%lu m%lu\r\n",
           displayFpsX100 / 100,
           displayFpsX100 % 100,
           inputFpsX100 / 100,
           inputFpsX100 % 100,
           diagResolvedCycleLen,
           diagCycleCap,
           stats.errors,
           diagRawNonZeroPixels,
           diagConvertedNonZeroPixels,
           diagOutputNonZeroMaxInCycle,
           diagOutputWNonZeroMaxInCycle,
           diagBlackInToConvertedNonZeroFrames,
           diagBlackInToOutputNonZeroFrames,
#if ENABLE_NEAR_BLACK_DIAGNOSTICS
           diagNearBlackSrcSubpixels,
           diagNearBlackOutSubpixels,
           diagZeroToNonZeroSubpixels,
           rxKBpsX100 / 100,
           rxKBpsX100 % 100,
           lastTransportTag,
           telemetry.framesRgb8,
           telemetry.framesRgb12Carry,
           telemetry.framesRgb16,
           telemetry.framesVersion2,
           avgHostShadowHighlights,
           avgLocalShadowHighlights,
           avgShadowMismatch);
#else
           0UL,
           0UL,
           0UL,
           rxKBpsX100 / 100,
           rxKBpsX100 % 100,
           lastTransportTag,
           telemetry.framesRgb8,
           telemetry.framesRgb12Carry,
           telemetry.framesRgb16,
           telemetry.framesVersion2);
#endif
#else
  snprintf(out, sizeof(out),
           "HyperSerialTeensy | fps:%lu.%02lu ifps:%lu.%02lu cy:%u cap:%u err:%lu rx:%lu.%02luKB/s m:%c 8:%lu 12:%lu 16:%lu v2:%lu sh:h%lu l%lu m%lu mem:hu%lu hf%lu sg%lu mn%lu us:c%lu r%lu a%lu s%lu\r\n",
           displayFpsX100 / 100,
           displayFpsX100 % 100,
           inputFpsX100 / 100,
           inputFpsX100 % 100,
           diagResolvedCycleLen,
           diagCycleCap,
           stats.errors,
           rxKBpsX100 / 100,
           rxKBpsX100 % 100,
           lastTransportTag,
           telemetry.framesRgb8,
           telemetry.framesRgb12Carry,
           telemetry.framesRgb16,
           telemetry.framesVersion2,
           avgHostShadowHighlights,
           avgLocalShadowHighlights,
           avgShadowMismatch,
           heapUsedBytes,
           heapFreeBytes,
           stackGapBytes,
           minStackGapBytes,
           avgRgbwConvertUs,
           avgRenderUs,
           avgPowerLimiterUs,
           avgShowUs);
#endif

  hyperSerialPrint(out);

  stats.totalFrames = 0;
  stats.goodFrames = 0;
  stats.shownFrames = 0;
  stats.errors = 0;
  stats.lastPrint = now;
  telemetry.bytesReceived = 0;
  telemetry.framesRgb8 = 0;
  telemetry.framesRgb16 = 0;
  telemetry.framesRgb12Carry = 0;
  telemetry.framesVersion2 = 0;
  telemetry.highlightShadowFrames = 0;
  telemetry.hostShadowHighlightAccum = 0;
  telemetry.localShadowHighlightAccum = 0;
  telemetry.shadowMismatchAccum = 0;
  telemetry.shadowHostOnlyAccum = 0;
  telemetry.shadowLocalOnlyAccum = 0;
  telemetry.postBfiResolveChannelAccum = 0;
  telemetry.postBfiResolvePixelAccum = 0;
  telemetry.highlightTriggeredAccum = 0;
  telemetry.highlightRolloffActiveAccum = 0;
  telemetry.frameLimiterControlSamples = 0;
  telemetry.frameLimiterActiveFrames = 0;
  telemetry.frameLimiterLastPower = 0;
  telemetry.frameLimiterMaxPower = 0;
  telemetry.frameLimiterLastScaleQ8 = 256;
  telemetry.frameLimiterMinScaleQ8 = 256;
  telemetry.minStackGapBytes = telemetry.stackGapBytes;

#if ENABLE_PIPE_DIAGNOSTICS && ENABLE_NEAR_BLACK_DIAGNOSTICS
  diagNearBlackSrcSubpixels = 0;
  diagNearBlackOutSubpixels = 0;
  diagZeroToNonZeroSubpixels = 0;
#endif

#if ENABLE_STATS_BFI_DIAGNOSTICS
  diagBlackPixelsAccumG = 0;
  diagBlackPixelsAccumR = 0;
  diagBlackPixelsAccumB = 0;
  diagBlackPixelsAccumW = 0;
  diagHighlightActiveSamples = 0;
  diagRenderSamples = 0;
#endif

#if ENABLE_STAGE_TIMING_STATS
  telemetry.rgbwConvertUsTotal = 0;
  telemetry.bfiRenderUsTotal = 0;
  telemetry.powerLimiterUsTotal = 0;
  telemetry.showUsTotal = 0;
  telemetry.rgbwConvertSamples = 0;
  telemetry.bfiRenderSamples = 0;
  telemetry.powerLimiterSamples = 0;
  telemetry.showSamples = 0;
#endif
}

// ---------------- CONTROL COMMANDS ----------------

uint8_t controlCommand = 0;
bool expectingValue = false;

void handleControlCommand(uint8_t cmd, uint8_t value) {
  switch (cmd) {
    case 0x10:
      globalBrightness = value;
      leds.setBrightness(globalBrightness);
      break;

    case 0x11:
      whiteCal = value;
      break;

    case 0x12:
      runtimeWhiteLimit = value;
      whiteLimit = value;
      break;

    case 0x13:
      runtimeUseDerivedSolverLutSize = (value != 0u);
      refreshRuntimeSolverLutSize();
      break;
  }
}

void flushStartupSidebandBootLogsIfPending();

static inline void serialMonitorPacketWrite(const char* text, size_t length)
{
  if (!text || length == 0)
    return;

  const uint8_t* logMirror = (const uint8_t*)text;
  const size_t logMirrorLength = length;

  rawHidLogWriteBuffer(logMirror, logMirrorLength);
}

void serialMonitorPrint(const char* text)
{
  if (!text)
    return;
  serialMonitorPacketWrite(text, strlen(text));
}

void serialMonitorPrintln(const char* text)
{
  if (!text)
    text = "";

  rawHidLogWriteBuffer((const uint8_t*)text, strlen(text));
  rawHidLogWriteLineBreak();
}

void serialMonitorPrintf(const char* format, ...)
{
  if (!format)
    return;

  char buffer[192];
  va_list args;
  va_start(args, format);
  const int written = vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);

  if (written <= 0)
    return;

  const size_t count = (written >= (int)sizeof(buffer))
                         ? (sizeof(buffer) - 1)
                         : (size_t)written;
  serialMonitorPacketWrite(buffer, count);
}


void flushStartupSidebandBootLogsIfPending()
{
  if (!startupSidebandBootLogsPending)
    return;

  char out[128];
  snprintf(out, sizeof(out), "Runtime max BFI=%u | solverLut=%u\r\n",
           startupRuntimeMaxBfi,
           (unsigned)runtimeActiveSolverLutSize);
  serialMonitorPrint(out);

  startupSidebandBootLogsPending = false;
}

// ---------------- BYTE PROCESSOR ----------------

void processAwaByte(uint8_t input) {
  frame_finished_displaying = false;
  switch (frameState.state) {
    case AwaProtocol::HEADER_A:
      frameState.setProtocolVersion2(false);
      frameState.setProtocolRgb16(false);
      frameState.setProtocolRgb12Carry(false);
      frameState.setProtocolHostRgbw(false);
      frameState.setProtocolScenePolicy(false);
      frameState.setProtocolHighlightShadow(false);
      frameState.setProtocolTransferConfig(false);
      if (input == 'A') frameState.state = AwaProtocol::HEADER_w;
      break;

    case AwaProtocol::HEADER_w:
      if (input == 'w') {
        frameState.setProtocolHostRgbw(false);
        frameState.setProtocolTransferConfig(false);
        frameState.state = AwaProtocol::HEADER_a;
      } else if (input == 'W') {
        frameState.setProtocolHostRgbw(true);
        frameState.setProtocolTransferConfig(false);
        frameState.state = AwaProtocol::HEADER_a;
      } else if (input == 't') {
        frameState.setProtocolHostRgbw(false);
        frameState.setProtocolTransferConfig(true);
        frameState.state = AwaProtocol::HEADER_a;
      } else if (input == 'T') {
        frameState.setProtocolHostRgbw(true);
        frameState.setProtocolTransferConfig(true);
        frameState.state = AwaProtocol::HEADER_a;
      } else {
        frameState.state = AwaProtocol::HEADER_A;
      }
      break;

    case AwaProtocol::HEADER_a:
      if (frameState.isProtocolHostRgbw()) {
        if (input == 'b') {
          frameState.setProtocolVersion2(false);
          frameState.setProtocolRgb16(true);
          frameState.setProtocolRgb12Carry(false);
          frameState.setProtocolScenePolicy(false);
          frameState.setProtocolHighlightShadow(false);
          frameState.state = AwaProtocol::HEADER_HI;
        } else if (input == 'd') {
          frameState.setProtocolVersion2(false);
          frameState.setProtocolRgb16(true);
          frameState.setProtocolRgb12Carry(false);
          frameState.setProtocolScenePolicy(true);
          frameState.setProtocolHighlightShadow(false);
          frameState.state = AwaProtocol::HEADER_HI;
        } else if (input == 'f') {
          frameState.setProtocolVersion2(false);
          frameState.setProtocolRgb16(true);
          frameState.setProtocolRgb12Carry(false);
          frameState.setProtocolScenePolicy(true);
          frameState.setProtocolHighlightShadow(true);
          frameState.state = AwaProtocol::HEADER_HI;
        } else if (input == 'c') {
          frameState.setProtocolVersion2(false);
          frameState.setProtocolRgb16(false);
          frameState.setProtocolRgb12Carry(true);
          frameState.setProtocolScenePolicy(false);
          frameState.setProtocolHighlightShadow(false);
          frameState.state = AwaProtocol::HEADER_HI;
        } else if (input == 'e') {
          frameState.setProtocolVersion2(false);
          frameState.setProtocolRgb16(false);
          frameState.setProtocolRgb12Carry(true);
          frameState.setProtocolScenePolicy(true);
          frameState.setProtocolHighlightShadow(false);
          frameState.state = AwaProtocol::HEADER_HI;
        } else if (input == 'g') {
          frameState.setProtocolVersion2(false);
          frameState.setProtocolRgb16(false);
          frameState.setProtocolRgb12Carry(true);
          frameState.setProtocolScenePolicy(true);
          frameState.setProtocolHighlightShadow(true);
          frameState.state = AwaProtocol::HEADER_HI;
        } else {
          frameState.state = AwaProtocol::HEADER_A;
        }
      } else if (input == 'a') {
        frameState.setProtocolVersion2(false);
        frameState.setProtocolRgb16(false);
        frameState.setProtocolRgb12Carry(false);
        frameState.state = AwaProtocol::HEADER_HI;
      } else if (input == 'A') {
        frameState.setProtocolVersion2(true);
        frameState.setProtocolRgb16(false);
        frameState.setProtocolRgb12Carry(false);
        frameState.state = AwaProtocol::HEADER_HI;
      } else if (input == 'b') {
        frameState.setProtocolVersion2(false);
        frameState.setProtocolRgb16(true);
        frameState.setProtocolRgb12Carry(false);
        frameState.state = AwaProtocol::HEADER_HI;
      } else if (input == 'B') {
        frameState.setProtocolVersion2(true);
        frameState.setProtocolRgb16(true);
        frameState.setProtocolRgb12Carry(false);
        frameState.state = AwaProtocol::HEADER_HI;
      } else if (input == 'c') {
        frameState.setProtocolVersion2(false);
        frameState.setProtocolRgb16(false);
        frameState.setProtocolRgb12Carry(true);
        frameState.state = AwaProtocol::HEADER_HI;
      } else if (input == 'C') {
        frameState.setProtocolVersion2(true);
        frameState.setProtocolRgb16(false);
        frameState.setProtocolRgb12Carry(true);
        frameState.setProtocolScenePolicy(false);
        frameState.state = AwaProtocol::HEADER_HI;
      } else if (input == 'd') {
        frameState.setProtocolVersion2(false);
        frameState.setProtocolRgb16(true);
        frameState.setProtocolRgb12Carry(false);
        frameState.setProtocolScenePolicy(true);
        frameState.state = AwaProtocol::HEADER_HI;
      } else if (input == 'e') {
        frameState.setProtocolVersion2(false);
        frameState.setProtocolRgb16(false);
        frameState.setProtocolRgb12Carry(true);
        frameState.setProtocolScenePolicy(true);
        frameState.setProtocolHighlightShadow(false);
        frameState.state = AwaProtocol::HEADER_HI;
      } else if (input == 'f') {
        frameState.setProtocolVersion2(false);
        frameState.setProtocolRgb16(true);
        frameState.setProtocolRgb12Carry(false);
        frameState.setProtocolScenePolicy(true);
        frameState.setProtocolHighlightShadow(true);
        frameState.state = AwaProtocol::HEADER_HI;
      } else if (input == 'g') {
        frameState.setProtocolVersion2(false);
        frameState.setProtocolRgb16(false);
        frameState.setProtocolRgb12Carry(true);
        frameState.setProtocolScenePolicy(true);
        frameState.setProtocolHighlightShadow(true);
        frameState.state = AwaProtocol::HEADER_HI;
      } else
        frameState.state = AwaProtocol::HEADER_A;
      break;

    case AwaProtocol::HEADER_HI:
      frameState.init(input);
      frameState.state = AwaProtocol::HEADER_LO;
      break;

    case AwaProtocol::HEADER_LO:
      frameState.computeCRC(input);
      frameState.state = AwaProtocol::HEADER_CRC;
      break;

    case AwaProtocol::HEADER_CRC:
      if (frameState.crc == input) {
        stats.totalFrames++;
        frame_finished_displaying = false;
        frameState.state = frameState.isProtocolRgb16() ? AwaProtocol::RED16_HI : AwaProtocol::RED;
      } else if (frameState.count == 0x2aa2 && (input == 0x15 || input == 0x35)) {
        printHyperSerialStats();

        if (input == 0x15) {
          printHyperSerialWelcome();
          printBFIClampConfig();
        }

        frameState.state = AwaProtocol::HEADER_A;
      } else {
        stats.errors++;
        frameState.state = AwaProtocol::HEADER_A;
      }
      break;

    case AwaProtocol::RED:
      frameState.r = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::GREEN;
      break;

    case AwaProtocol::GREEN:
      frameState.g = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::BLUE;
      break;

    case AwaProtocol::BLUE:
      frameState.b = input;
      frameState.addFletcher(input);

      /*if(frameState.isProtocolVersion2())
        frameState.applyIncomingCalibration(
          frameState.r,
          frameState.g,
          frameState.b
        );*/

      // Batch processing: store raw RGB in frame buffer; conversion is deferred
      // to commitFrame()/processFrameRGBWBatch().

      if (frameState.isProtocolRgb12Carry())
      {
  		frameState.state = frameState.isProtocolHostRgbw() ? AwaProtocol::WHITE12 : AwaProtocol::CARRY12_RG;
        break;
      }

      {
      uint32_t q = frameState.currentLed * 3;
      frameInputQ16[q + 0] = scale8ToQ16(frameState.r);
      frameInputQ16[q + 1] = scale8ToQ16(frameState.g);
      frameInputQ16[q + 2] = scale8ToQ16(frameState.b);
      frameInputWQ16[frameState.currentLed] = 0u;
    #if ENABLE_PIPE_DIAGNOSTICS
      if (frameState.r | frameState.g | frameState.b) {
        if (diagRawNonZeroPixels < LED_COUNT) diagRawNonZeroPixels++;
      }
    #endif
      }

      frameState.currentLed++;

      if (frameState.currentLed < LED_COUNT)
        frameState.state = frameState.isProtocolRgb16() ? AwaProtocol::RED16_HI : AwaProtocol::RED;
      else if (frameState.isProtocolScenePolicy())
        frameState.state = AwaProtocol::POLICY_SCENE_MAGIC;
      else if (frameState.isProtocolVersion2())
        frameState.state = AwaProtocol::VERSION2_GAIN;
      else if (frameState.isProtocolTransferConfig())
        frameState.state = AwaProtocol::TRANSFER_FLAGS;
      else
        frameState.state = AwaProtocol::FLETCHER1;

      break;

    case AwaProtocol::WHITE12:
      frameState.w = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::CARRY12_RG;
      break;

    case AwaProtocol::CARRY12_RG:
      frameState.rgCarry = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::CARRY12_B;
      break;

    case AwaProtocol::CARRY12_B:
      frameState.bCarryReserved = input;
      frameState.addFletcher(input);

      {
      const uint16_t r12 = (uint16_t)(((uint16_t)frameState.r << 4) | ((frameState.rgCarry >> 4) & 0x0Fu));
      const uint16_t g12 = (uint16_t)(((uint16_t)frameState.g << 4) | (frameState.rgCarry & 0x0Fu));
      const uint16_t b12 = (uint16_t)(((uint16_t)frameState.b << 4) | ((frameState.bCarryReserved >> 4) & 0x0Fu));
  		const uint16_t w12 = (uint16_t)(((uint16_t)frameState.w << 4) | (frameState.bCarryReserved & 0x0Fu));

      const uint16_t rQ16 = scale12ToQ16(r12);
      const uint16_t gQ16 = scale12ToQ16(g12);
      const uint16_t bQ16 = scale12ToQ16(b12);
  		const uint16_t wQ16 = frameState.isProtocolHostRgbw() ? scale12ToQ16(w12) : 0u;

      uint32_t q = frameState.currentLed * 3;
      frameInputQ16[q + 0] = rQ16;
      frameInputQ16[q + 1] = gQ16;
      frameInputQ16[q + 2] = bQ16;
      frameInputWQ16[frameState.currentLed] = wQ16;
    #if ENABLE_PIPE_DIAGNOSTICS
      if (rQ16 | gQ16 | bQ16 | wQ16) {
        if (diagRawNonZeroPixels < LED_COUNT) diagRawNonZeroPixels++;
      }
    #endif
      }

      frameState.currentLed++;

      if (frameState.currentLed < LED_COUNT)
        frameState.state = AwaProtocol::RED;
      else if (frameState.isProtocolScenePolicy())
        frameState.state = AwaProtocol::POLICY_SCENE_MAGIC;
      else if (frameState.isProtocolVersion2())
        frameState.state = AwaProtocol::VERSION2_GAIN;
      else if (frameState.isProtocolTransferConfig())
        frameState.state = AwaProtocol::TRANSFER_FLAGS;
      else
        frameState.state = AwaProtocol::FLETCHER1;

      break;

    case AwaProtocol::RED16_HI:
      frameState.hiByte = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::RED16_LO;
      break;

    case AwaProtocol::RED16_LO:
      frameState.r16 = ((uint16_t)frameState.hiByte << 8) | input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::GREEN16_HI;
      break;

    case AwaProtocol::GREEN16_HI:
      frameState.hiByte = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::GREEN16_LO;
      break;

    case AwaProtocol::GREEN16_LO:
      frameState.g16 = ((uint16_t)frameState.hiByte << 8) | input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::BLUE16_HI;
      break;

    case AwaProtocol::BLUE16_HI:
      frameState.hiByte = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::BLUE16_LO;
      break;

    case AwaProtocol::BLUE16_LO:
      frameState.b16 = ((uint16_t)frameState.hiByte << 8) | input;
      frameState.addFletcher(input);

      if (frameState.isProtocolHostRgbw())
      {
        frameState.state = AwaProtocol::WHITE16_HI;
        break;
      }

      {
      uint32_t q = frameState.currentLed * 3;
      frameInputQ16[q + 0] = frameState.r16;
      frameInputQ16[q + 1] = frameState.g16;
      frameInputQ16[q + 2] = frameState.b16;
      frameInputWQ16[frameState.currentLed] = 0u;
    #if ENABLE_PIPE_DIAGNOSTICS
      if (frameState.r16 | frameState.g16 | frameState.b16) {
        if (diagRawNonZeroPixels < LED_COUNT) diagRawNonZeroPixels++;
      }
    #endif
      }

      frameState.currentLed++;

      if (frameState.currentLed < LED_COUNT)
        frameState.state = AwaProtocol::RED16_HI;
      else if (frameState.isProtocolScenePolicy())
        frameState.state = AwaProtocol::POLICY_SCENE_MAGIC;
      else if (frameState.isProtocolVersion2())
        frameState.state = AwaProtocol::VERSION2_GAIN;
      else if (frameState.isProtocolTransferConfig())
        frameState.state = AwaProtocol::TRANSFER_FLAGS;
      else
        frameState.state = AwaProtocol::FLETCHER1;

      break;

    case AwaProtocol::WHITE16_HI:
      frameState.hiByte = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::WHITE16_LO;
      break;

    case AwaProtocol::WHITE16_LO:
      frameState.w16 = ((uint16_t)frameState.hiByte << 8) | input;
      frameState.addFletcher(input);

      {
      uint32_t q = frameState.currentLed * 3;
      frameInputQ16[q + 0] = frameState.r16;
      frameInputQ16[q + 1] = frameState.g16;
      frameInputQ16[q + 2] = frameState.b16;
      frameInputWQ16[frameState.currentLed] = frameState.w16;
    #if ENABLE_PIPE_DIAGNOSTICS
      if (frameState.r16 | frameState.g16 | frameState.b16 | frameState.w16) {
        if (diagRawNonZeroPixels < LED_COUNT) diagRawNonZeroPixels++;
      }
    #endif
      }

      frameState.currentLed++;

      if (frameState.currentLed < LED_COUNT)
        frameState.state = AwaProtocol::RED16_HI;
      else if (frameState.isProtocolScenePolicy())
        frameState.state = AwaProtocol::POLICY_SCENE_MAGIC;
      else if (frameState.isProtocolTransferConfig())
        frameState.state = AwaProtocol::TRANSFER_FLAGS;
      else
        frameState.state = AwaProtocol::FLETCHER1;

      break;

    case AwaProtocol::VERSION2_GAIN:
      frameState.incomingCal.gain = input;
      runtimeWhiteLimit = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::VERSION2_RED;
      break;

    case AwaProtocol::VERSION2_RED:
      frameState.incomingCal.red = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::VERSION2_GREEN;
      break;

    case AwaProtocol::VERSION2_GREEN:
      frameState.incomingCal.green = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::VERSION2_BLUE;
      break;

    case AwaProtocol::VERSION2_BLUE:
      frameState.incomingCal.blue = input;
      frameState.addFletcher(input);
      frameState.state = frameState.isProtocolTransferConfig() ? AwaProtocol::TRANSFER_FLAGS : AwaProtocol::FLETCHER1;
      break;

    case AwaProtocol::POLICY_SCENE_MAGIC:
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::POLICY_SCENE_OFFSET;
      break;

    case AwaProtocol::POLICY_SCENE_OFFSET:
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::POLICY_SCENE_RESERVED0;
      break;

    case AwaProtocol::POLICY_SCENE_RESERVED0:
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::POLICY_SCENE_RESERVED1;
      break;

    case AwaProtocol::POLICY_SCENE_RESERVED1:
      frameState.addFletcher(input);
      if (frameState.isProtocolHighlightShadow() && HOST_HIGHLIGHT_MASK_BYTES > 0u)
      {
#if ENABLE_HIGHLIGHT_SHADOW_COMPARE_STATS
        memset(hostHighlightMaskPending, 0, sizeof(hostHighlightMaskPending));
#endif
        frameState.highlightMaskByteIndex = 0u;
        frameState.highlightShadowValid = false;
        frameState.state = AwaProtocol::POLICY_HIGHLIGHT_MASK;
      }
      else
      {
        frameState.state = frameState.isProtocolTransferConfig() ? AwaProtocol::TRANSFER_FLAGS : AwaProtocol::FLETCHER1;
      }
      break;

    case AwaProtocol::POLICY_HIGHLIGHT_MASK:
      if (frameState.highlightMaskByteIndex < HOST_HIGHLIGHT_MASK_BYTES)
      {
#if ENABLE_HIGHLIGHT_SHADOW_COMPARE_STATS
        hostHighlightMaskPending[frameState.highlightMaskByteIndex++] = input;
        if (frameState.highlightMaskByteIndex >= HOST_HIGHLIGHT_MASK_BYTES)
          frameState.highlightShadowValid = true;
#else
        frameState.highlightMaskByteIndex++;
#endif
      }
      frameState.addFletcher(input);
      frameState.state = (frameState.highlightMaskByteIndex >= HOST_HIGHLIGHT_MASK_BYTES)
                           ? (frameState.isProtocolTransferConfig() ? AwaProtocol::TRANSFER_FLAGS : AwaProtocol::FLETCHER1)
                           : AwaProtocol::POLICY_HIGHLIGHT_MASK;
      break;

    case AwaProtocol::TRANSFER_FLAGS:
      frameState.transferCurveFlags = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::TRANSFER_PROFILE;
      break;

    case AwaProtocol::TRANSFER_PROFILE:
      frameState.transferCurveProfile = input;
      frameState.addFletcher(input);
      frameState.state = AwaProtocol::FLETCHER1;
      break;

    case AwaProtocol::FLETCHER1:
      frameState.state = (input == frameState.getF1())
                           ? AwaProtocol::FLETCHER2
                           : AwaProtocol::HEADER_A;
      break;

    case AwaProtocol::FLETCHER2:
      frameState.state = (input == frameState.getF2())
                           ? AwaProtocol::FLETCHER_EXT
                           : AwaProtocol::HEADER_A;
      break;

    case AwaProtocol::FLETCHER_EXT:

      if (frameState.count == 0x2aa2) {
        if (!expectingValue) {
          controlCommand = input;

          if (controlCommand == 0x15) {
            printHyperSerialWelcome();
            printBFIClampConfig();
            printHyperSerialStats();
          } else if (controlCommand == 0x35) {
            printHyperSerialStats();
          } else {
            expectingValue = true;
          }
        } else {
          handleControlCommand(controlCommand, input);
          expectingValue = false;
        }
      } else if (input == frameState.getFext()) {
        if (frameState.isProtocolHighlightShadow() && frameState.highlightShadowValid)
        {
#if ENABLE_HIGHLIGHT_SHADOW_COMPARE_STATS
          memcpy(hostHighlightMaskActive, hostHighlightMaskPending, sizeof(hostHighlightMaskActive));
          hostHighlightShadowFrameValid = true;
#else
          hostHighlightShadowFrameValid = false;
#endif
        }
        else
        {
          hostHighlightShadowFrameValid = false;
        }
        commitFrame();
      } else {
        stats.errors++;
        hostHighlightShadowFrameValid = false;
      }

      frameState.state = AwaProtocol::HEADER_A;
      break;
  }
}

inline void processIncomingTransportByte(uint8_t input)
{
  telemetry.bytesReceived++;
  processAwaByte(input);
}

#if ENABLE_RAWHID_INPUT && (defined(USB_RAWHID) || defined(RAWHID_INTERFACE))
inline void processRawHidPacket(const uint8_t* packet, uint16_t packetLen)
{
  if (!packet || packetLen < RAWHID_PACKET_HEADER_SIZE)
    return;

  if (packet[0] != (uint8_t)RAWHID_PACKET_MAGIC_0 ||
      packet[1] != (uint8_t)RAWHID_PACKET_MAGIC_1)
    return;

  uint16_t payloadLen = ((uint16_t)packet[2] << 8) | packet[3];
  const uint16_t maxPayload = (uint16_t)(packetLen - RAWHID_PACKET_HEADER_SIZE);
  if (payloadLen > maxPayload)
    payloadLen = maxPayload;

  for (uint16_t i = 0; i < payloadLen; i++)
    processIncomingTransportByte(packet[RAWHID_PACKET_HEADER_SIZE + i]);
}
#endif

void applyABLToDisplayBuffer() {
#if ENABLE_STAGE_TIMING_STATS
  const uint32_t powerLimiterStartUs = micros();
  auto finalizePowerLimiterTiming = [&]() {
    telemetry.powerLimiterUsTotal += (uint64_t)(micros() - powerLimiterStartUs);
    telemetry.powerLimiterSamples++;
  };
#endif
#if !ENABLE_FRAME_POWER_LIMIT
  frameLimiterFeedForwardScaleQ8 = 256;
  if (bfiPhase == 0)
  {
    telemetry.frameLimiterControlSamples++;
    telemetry.frameLimiterLastPower = 0;
    telemetry.frameLimiterLastScaleQ8 = 256;
  }
#if ENABLE_STAGE_TIMING_STATS
  finalizePowerLimiterTiming();
#endif
  return;
#endif

  static uint16_t cachedCommonScaleQ8 = 256;
  const bool updateControlThisPhase = (bfiPhase == 0);

  if (!updateControlThisPhase)
  {
    if (cachedCommonScaleQ8 >= 256)
    {
#if ENABLE_STAGE_TIMING_STATS
      finalizePowerLimiterTiming();
#endif
      return;
    }

    for (uint16_t i = 0; i < LED_COUNT; i++)
    {
      uint32_t o = i * 4;
      displayBuffer[o + 0] = (uint16_t(displayBuffer[o + 0]) * cachedCommonScaleQ8) >> 8;
      displayBuffer[o + 1] = (uint16_t(displayBuffer[o + 1]) * cachedCommonScaleQ8) >> 8;
      displayBuffer[o + 2] = (uint16_t(displayBuffer[o + 2]) * cachedCommonScaleQ8) >> 8;
      displayBuffer[o + 3] = (uint16_t(displayBuffer[o + 3]) * cachedCommonScaleQ8) >> 8;
    }
#if ENABLE_STAGE_TIMING_STATS
    finalizePowerLimiterTiming();
#endif
    return;
  }

  const uint32_t totalPower = (uint32_t)(renderPowerQ8 >> 8);

  if (targetFramePower == 0 || totalPower == 0)
  {
    frameLimiterActive = false;
    frameLimiterScaleQ8 = 256;
    frameLimiterFeedForwardScaleQ8 = 256;
    cachedCommonScaleQ8 = 256;
    telemetry.frameLimiterControlSamples++;
    telemetry.frameLimiterLastPower = totalPower;
    telemetry.frameLimiterLastScaleQ8 = 256;
    if (totalPower > telemetry.frameLimiterMaxPower)
      telemetry.frameLimiterMaxPower = totalPower;
#if ENABLE_STAGE_TIMING_STATS
    finalizePowerLimiterTiming();
#endif
    return;
  }

  const bool overPowerTarget = totalPower > targetFramePower;

  uint16_t sagQ8 = 256;
  const uint32_t droopStartPower =
      (uint32_t)(((uint64_t)targetFramePower * DROOP_START_Q8 + 255u) >> 8);
  if (totalPower > droopStartPower && droopStartPower > 0)
  {
    const uint32_t excess = totalPower - droopStartPower;
    uint32_t dropQ8 = (excess * 64u) / droopStartPower;
    if (dropQ8 > (256u - DROOP_MIN_SAG_Q8))
      dropQ8 = (256u - DROOP_MIN_SAG_Q8);
    sagQ8 = (uint16_t)(256u - dropQ8);
  }

  uint16_t frameScaleQ8 = 256;
  if (overPowerTarget)
  {
    frameScaleQ8 = (uint16_t)(((uint64_t)targetFramePower * 256u) / totalPower);
    if (frameScaleQ8 > 256u)
      frameScaleQ8 = 256u;
  }

  const uint16_t rawCommonScaleQ8 = (uint16_t)(((uint32_t)sagQ8 * frameScaleQ8) >> 8);

  if (frameLimiterActive)
  {
    if (((uint64_t)totalPower << 8) <= (uint64_t)targetFramePower * FRAME_LIMITER_EXIT_Q8)
      frameLimiterActive = false;
  }
  else
  {
    if (((uint64_t)totalPower << 8) >= (uint64_t)targetFramePower * FRAME_LIMITER_ENTER_Q8)
      frameLimiterActive = true;
  }

  const uint16_t targetCommonScaleQ8 = frameLimiterActive ? rawCommonScaleQ8 : 256;
  const int32_t deltaScale = (int32_t)targetCommonScaleQ8 - (int32_t)frameLimiterScaleQ8;
  const uint8_t alphaQ8 = (deltaScale < 0) ? FRAME_LIMITER_ATTACK_Q8 : FRAME_LIMITER_RELEASE_Q8;
  frameLimiterScaleQ8 = (uint16_t)((int32_t)frameLimiterScaleQ8 + ((deltaScale * alphaQ8) >> 8));
  if (frameLimiterScaleQ8 > 256)
    frameLimiterScaleQ8 = 256;
  if (frameLimiterScaleQ8 < 8)
    frameLimiterScaleQ8 = 8;

  const uint16_t commonScaleQ8 = frameLimiterScaleQ8;
  cachedCommonScaleQ8 = commonScaleQ8;
  frameLimiterFeedForwardScaleQ8 = commonScaleQ8;
  telemetry.frameLimiterControlSamples++;
  telemetry.frameLimiterLastPower = totalPower;
  telemetry.frameLimiterLastScaleQ8 = commonScaleQ8;
  if (totalPower > telemetry.frameLimiterMaxPower)
    telemetry.frameLimiterMaxPower = totalPower;
  if (commonScaleQ8 < telemetry.frameLimiterMinScaleQ8)
    telemetry.frameLimiterMinScaleQ8 = commonScaleQ8;
  if (frameLimiterActive || commonScaleQ8 < 256)
    telemetry.frameLimiterActiveFrames++;

  if (commonScaleQ8 >= 256)
  {
#if ENABLE_STAGE_TIMING_STATS
    finalizePowerLimiterTiming();
#endif
    return;
  }

  for (uint16_t i = 0; i < LED_COUNT; i++)
  {
    uint32_t o = i * 4;
    displayBuffer[o + 0] = (uint16_t(displayBuffer[o + 0]) * commonScaleQ8) >> 8;
    displayBuffer[o + 1] = (uint16_t(displayBuffer[o + 1]) * commonScaleQ8) >> 8;
    displayBuffer[o + 2] = (uint16_t(displayBuffer[o + 2]) * commonScaleQ8) >> 8;
    displayBuffer[o + 3] = (uint16_t(displayBuffer[o + 3]) * commonScaleQ8) >> 8;
  }
#if ENABLE_STAGE_TIMING_STATS
  finalizePowerLimiterTiming();
#endif
}

// ---------------- BFI DISPLAY ----------------

void showDisplayFrame() {
#if ENABLE_STAGE_TIMING_STATS
  const uint32_t showStartUs = micros();
#endif
  leds.show();
#if ENABLE_STAGE_TIMING_STATS
  telemetry.showUsTotal += (uint64_t)(micros() - showStartUs);
  telemetry.showSamples++;
#endif
  stats.shownFrames++;
}

void startupAnimation() {
  memset(displayBuffer, 0, sizeof(displayBuffer));
  leds.show();
  delay(100);

  for (int i = 0; i < LED_COUNT; i++) {
    displayBuffer[i * 4 + 0] = 64;
    displayBuffer[i * 4 + 1] = 64;
    displayBuffer[i * 4 + 2] = 64;
    displayBuffer[i * 4 + 3] = 64;
  }
  leds.show();

  delay(50);

  memset(displayBuffer, 0, sizeof(displayBuffer));
  leds.show();
}

void renderIndependentSubpixelBFI()
{
#if ENABLE_STAGE_TIMING_STATS
  const uint32_t renderStartUs = micros();
#endif

  uint16_t outNonZero = 0;
  uint16_t outWNonZero = 0;
  uint64_t totalPowerQ8 = 0;
#if ENABLE_STATS_BFI_DIAGNOSTICS
  uint16_t blackG = 0;
  uint16_t blackR = 0;
  uint16_t blackB = 0;
  uint16_t blackW = 0;
#endif

#if ENABLE_PIPE_DIAGNOSTICS
  diagResolvedCycleLen = activeBfiCycleLen;
#endif

  // Pre-pass: apply runtime forced-BFI / max-BFI clamp to the maps so the
  // library render reads the correct values.  These may have changed since
  // the last rgbToRgbw commit (e.g. mid-cycle serial command).
  uint8_t forcedBfi = 0;
  const bool hasForcedBfi = resolveEffectiveForcedBfi(forcedBfi);
  if (hasForcedBfi)
  {
    for (uint16_t i = 0; i < LED_COUNT; i++)
    {
      bfiMapG[i] = forcedBfi;
      bfiMapR[i] = forcedBfi;
      bfiMapB[i] = forcedBfi;
      bfiMapW[i] = forcedBfi;
    }
  }

  // Fused render + power/diagnostics pass: render each pixel by index,
  // then accumulate power estimation in the same loop iteration.
  for (uint16_t i = 0; i < LED_COUNT; i++)
  {
    TemporalBFI::SolverRuntime::renderPixelBFI_RGBW(
        latchedFrameBuffer, latchedFloorFrameBuffer,
        bfiMapG, bfiMapR, bfiMapB, bfiMapW,
        displayBuffer, i, bfiPhase);

    const uint8_t bfiG = bfiMapG[i];
    const uint8_t bfiR = bfiMapR[i];
    const uint8_t bfiB = bfiMapB[i];
    const uint8_t bfiW = bfiMapW[i];

    const uint8_t* dst = displayBuffer + (uint32_t)i * 4u;
    totalPowerQ8 += (uint32_t)POWER_WEIGHT_G * (uint32_t)dst[0] * (uint32_t)invCycleQ8[TemporalBFI::clampBfi(bfiG)];
    totalPowerQ8 += (uint32_t)POWER_WEIGHT_R * (uint32_t)dst[1] * (uint32_t)invCycleQ8[TemporalBFI::clampBfi(bfiR)];
    totalPowerQ8 += (uint32_t)POWER_WEIGHT_B * (uint32_t)dst[2] * (uint32_t)invCycleQ8[TemporalBFI::clampBfi(bfiB)];
    totalPowerQ8 += (uint32_t)POWER_WEIGHT_W * (uint32_t)dst[3] * (uint32_t)invCycleQ8[TemporalBFI::clampBfi(bfiW)];

#if ENABLE_STATS_BFI_DIAGNOSTICS
    const uint8_t phaseBit = (uint8_t)(1u << (bfiPhase & 0x07u));
    if (!(phaseEmitMask[TemporalBFI::clampBfi(bfiG)] & phaseBit) && blackG < LED_COUNT) blackG++;
    if (!(phaseEmitMask[TemporalBFI::clampBfi(bfiR)] & phaseBit) && blackR < LED_COUNT) blackR++;
    if (!(phaseEmitMask[TemporalBFI::clampBfi(bfiB)] & phaseBit) && blackB < LED_COUNT) blackB++;
    if (!(phaseEmitMask[TemporalBFI::clampBfi(bfiW)] & phaseBit) && blackW < LED_COUNT) blackW++;
#endif

#if ENABLE_PIPE_DIAGNOSTICS
    if (dst[0] | dst[1] | dst[2] | dst[3]) {
      if (outNonZero < LED_COUNT) outNonZero++;
    }
    if (dst[3]) {
      if (outWNonZero < LED_COUNT) outWNonZero++;
    }
#endif

  }

#if ENABLE_PIPE_DIAGNOSTICS
  diagOutputNonZeroPixels = outNonZero;
  diagOutputWNonZeroPixels = outWNonZero;
  if (outNonZero > diagOutputNonZeroMaxInCycle) diagOutputNonZeroMaxInCycle = outNonZero;
  if (outWNonZero > diagOutputWNonZeroMaxInCycle) diagOutputWNonZeroMaxInCycle = outWNonZero;
#endif

#if ENABLE_STATS_BFI_DIAGNOSTICS
  diagBlackPixelsAccumG += blackG;
  diagBlackPixelsAccumR += blackR;
  diagBlackPixelsAccumB += blackB;
  diagBlackPixelsAccumW += blackW;
  if (highlightWindowActiveR || highlightWindowActiveG || highlightWindowActiveB || highlightWindowActiveW)
    diagHighlightActiveSamples++;
  diagRenderSamples++;
#endif

  renderPowerQ8 = totalPowerQ8;

#if ENABLE_STAGE_TIMING_STATS
  telemetry.bfiRenderUsTotal += (uint64_t)(micros() - renderStartUs);
  telemetry.bfiRenderSamples++;
#endif
}

void computeTargetFramePower() {
    // SK6812 power weights: R=42mW, G/B/W=62mW → ratio 10:15:15:15
    const uint32_t p_max_per_led = 
        POWER_WEIGHT_R * 255U + 
        POWER_WEIGHT_G * 255U + 
        POWER_WEIGHT_B * 255U + 
        POWER_WEIGHT_W * 255U;
    // units used by estimatePixelPower
    const uint32_t current_max_per_led_mA =
        3U * (uint32_t)LED_CHANNEL_CURRENT_MA +
        (uint32_t)LED_WHITE_CHANNEL_CURRENT_MA;
    uint32_t computed = 0;
    if (current_max_per_led_mA != 0) {
      // Apply PSU efficiency headroom to available current
      uint32_t effective_psu_current = (PSU_MAX_CURRENT_MA * PSU_EFFICIENCY_PERCENT) / 100;
      computed = (effective_psu_current * p_max_per_led) / current_max_per_led_mA;
    }
    targetFramePower = computed;
    // report computed target so you can tune/verify
    char buf[128];
    snprintf(buf, sizeof(buf), 
             "Computed targetFramePower=%lu (PSU %lu mA @ %d%%, perLED mA=%lu)\r\n",
             (unsigned long)targetFramePower, (unsigned long)PSU_MAX_CURRENT_MA,
             PSU_EFFICIENCY_PERCENT, (unsigned long)current_max_per_led_mA);
    Serial.print(buf);
}

// ---------------- SETUP ----------------

void setup() {
  Serial.begin(SERIAL_BAUD);

  delay(100);
  set_arm_clock(speed); 

#if ENABLE_RAWHID_INPUT && !(defined(USB_RAWHID) || defined(RAWHID_INTERFACE))
  Serial.println("RawHID input enabled in sketch, but USB type is not RawHID. Falling back to Serial.");
#endif

  leds.begin(1.4, 100);
  leds.setBrightness(globalBrightness);
  startupAnimation();
  stats.lastPrint = millis();

  auto& cfg = solver.config();
  cfg.maxBFI = MAX_BFI_FRAMES;
  cfg.relativeErrorDivisor = 24;
  cfg.minErrorQ16 = 64;
  cfg.minValueRatioNumerator = 3;
  cfg.minValueRatioDenominator = 8;
  cfg.lowEndProtectThreshold = 48;
  cfg.lowEndMaxDrop = 10;

  // Register solver callbacks (decoupled from library .cpp).
  solver.setCalibrationFunction([](uint16_t q16, uint8_t ch) -> uint16_t {
      return TemporalTrue16BFIPolicySolver::calibrateInputQ16ForSolver(q16, ch);
  });

  // Set up transfer curve data from the included transfer curve header.
  solver.setTransferCurve(
      TemporalBFITransferCurve::TARGET_R,
      TemporalBFITransferCurve::TARGET_G,
      TemporalBFITransferCurve::TARGET_B,
      TemporalBFITransferCurve::TARGET_W,
      TRANSFER_CURVE_BUCKET_COUNT);
  solver.setTransferCurveEnabled(true);  // Sketch-level runtime logic handles actual enable/disable.

#if USE_PRECOMPUTED_LUTS_ACTIVE
  solver.attachLUTs(
      const_cast<uint8_t*>(&solverValueLUT[0][0]),
      const_cast<uint8_t*>(&solverBFILUT[0][0]),
      const_cast<uint8_t*>(&solverValueFloorLUT[0][0]),
      const_cast<uint16_t*>(&TemporalBFIPrecomputedSolverLUTs::solverOutputQ16LUT[0][0]),
      SOLVER_LUT_SIZE);
  Serial.println("Using precomputed solver LUTs from flash (USE_PRECOMPUTED_LUTS).\r\n");
#else
  solver.attachLUTs(
      &solverValueLUT[0][0],
      &solverBFILUT[0][0],
      &solverValueFloorLUT[0][0],
      nullptr,
      SOLVER_LUT_SIZE);
  solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16);

  #if defined(DUMP_PRECOMPUTED_LUTS_HEADER)
    Serial.println("\r\n--- BEGIN solver_precomputed_luts.h ---\r\n");
    dumpPrecomputedSolverLUTHeader();
    Serial.println("\r\n--- END solver_precomputed_luts.h ---\r\n");
    Serial.println("Header dump complete. Disable DUMP_PRECOMPUTED_LUTS_HEADER and enable USE_PRECOMPUTED_LUTS for flash-backed LUTs.");
    while (true)
      delay(1000);
  #endif
#endif

  initRuntimeForcedBfiFromDefines();
  resetRuntimeBfiGainStateToDefaults();

  startupRuntimeMaxBfi = resolveRuntimeMaxBfiFrames();
  startupSidebandBootLogsPending = true;

  flushStartupSidebandBootLogsIfPending();

  computeTargetFramePower(); // Get Target Frame Power Limit based on SK6812 + PSU Characteristics
  printHyperSerialWelcome();
  printBFIClampConfig();

}

// ---------------- LOOP ----------------

void loop() {

#if ENABLE_RAWHID_INPUT && (defined(USB_RAWHID) || defined(RAWHID_INTERFACE))
  static uint8_t rawHidReport[RAWHID_REPORT_SIZE];
  uint16_t rawHidBudget = RAWHID_RX_BUDGET_PER_LOOP;
  while (rawHidBudget > 0)
  {
    const int packetLen = RawHID.recv(rawHidReport, 0);
    if (packetLen <= 0)
      break;

    processRawHidPacket(rawHidReport, (uint16_t)packetLen);
    rawHidBudget--;
  }
#else
  uint16_t rxBypassBudget = SERIAL_RX_BACKLOG_BYPASS_BUDGET_BYTES;
  while (true) {
    int backlogBytes = Serial.available();
    if (backlogBytes <= 0)
      break;

    bool consumedAny = false;
    bool stalledOnSyncGate = false;
    while (backlogBytes > 0) {
      const bool allowRead = (frame_finished_displaying || frameState.state != AwaProtocol::HEADER_A);
      if (!allowRead)
      {
        if (backlogBytes < SERIAL_RX_BACKLOG_BYPASS_BYTES)
        {
          stalledOnSyncGate = true;
          break;
        }
        if (rxBypassBudget == 0)
        {
          stalledOnSyncGate = true;
          break;
        }
        rxBypassBudget--;
      }

      const int rawInput = Serial.read();
      if (rawInput < 0)
        break;
      const uint8_t input = (uint8_t)rawInput;
      backlogBytes--;
      consumedAny = true;
      processIncomingTransportByte(input);
    }

    // Avoid spinning forever when sync gating blocks reads until render advances.
    if (!consumedAny || stalledOnSyncGate)
      break;
  }
#endif

  activeBfiCycleCap = resolveInputSyncCycleCap();
  activeBfiCycleLen = activeBfiCycleCap;
  const uint8_t runtimeCycleHardMax = (uint8_t)(resolveRuntimeMaxBfiFrames() + 1u);

  if (activeBfiCycleCap < 1u) activeBfiCycleCap = 1u;
  if (activeBfiCycleCap > runtimeCycleHardMax) activeBfiCycleCap = runtimeCycleHardMax;

  diagCycleCap = activeBfiCycleCap;

  if (bfiPhase >= activeBfiCycleLen)
    bfiPhase = 0;

  renderIndependentSubpixelBFI();
  applyABLToDisplayBuffer();

  showDisplayFrame();

  bfiPhase++;
  if (bfiPhase >= activeBfiCycleLen) {
#if ENABLE_PIPE_DIAGNOSTICS
    if (diagRawNonZeroPixels == 0 && diagOutputNonZeroMaxInCycle > 0) {
      diagBlackInToOutputNonZeroFrames++;
    }
#endif
    bfiPhase = 0;
    frame_finished_displaying = true;
  }

#if ENABLE_PERIODIC_HYPERSERIAL_STATS
  static uint32_t periodicStatsLastTickMs = 0;
  static bool periodicStatsEmitHyper = true;
  const uint32_t nowMs = millis();
  if (periodicStatsLastTickMs == 0)
    periodicStatsLastTickMs = nowMs;

  if ((nowMs - periodicStatsLastTickMs) > PERIODIC_STATS_INTERVAL_MS)
  {
    periodicStatsLastTickMs = nowMs;
    printHyperSerialStats();
  }
#endif
}
