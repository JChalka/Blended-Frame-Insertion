#include <Arduino.h>

#include <ObjectFLED.h>

#ifndef FASTLED_RGBW_COLORIMETRIC
#define FASTLED_RGBW_COLORIMETRIC 1
#endif
#include <FastLED.h>
#include <fl/gfx/rgbw_colorimetric.h>

#define USER_DEFINED_TEMPORAL_SOLVER_HEADER

#include "temporal_runtime_solver_header_temporal_blend_130815_v2.h"

#include <TemporalBFI.h>
#include <TemporalBFIRuntime.h>

#define NUM_PINS 2
#define LEDS_PER_PIN 48
#define LED_COUNT (NUM_PINS * LEDS_PER_PIN)
#define SERIAL_BAUD 30000000UL
#define MAX_BFI_FRAMES 4
#define TEMPORAL_BFI_CYCLE (MAX_BFI_FRAMES + 1)
#define MIN_SHOW_INTERVAL_US 1600u
#define DIRECT_FRAME_MAGIC_0 'T'
#define DIRECT_FRAME_MAGIC_1 'C'
#define DIRECT_FRAME_MAGIC_2 'A'
#define DIRECT_FRAME_MAGIC_3 'L'
#define DIRECT_FRAME_MAX_PAYLOAD 128
#define FRAME_KIND_HELLO_REQ 0x01
#define FRAME_KIND_HELLO_RSP 0x81
#define FRAME_KIND_PING_REQ 0x02
#define FRAME_KIND_PING_RSP 0x82
#define FRAME_KIND_LOG 0x90
#define FRAME_KIND_CAL_REQ 0x30
#define FRAME_KIND_CAL_RSP 0xB0
#define OP_GET_STATE 0x00
#define OP_SET_RENDER_ENABLED 0x20
#define OP_SET_FILL 0x21
#define OP_CLEAR 0x23
#define OP_SET_PHASE 0x24
#define OP_COMMIT 0x26
#define OP_SET_PHASE_MODE 0x28
#define OP_SET_SOLVER_ENABLED 0x29
#define OP_SET_TEMPORAL_BLEND 0x2A
#define OP_SET_FILL16 0x2B
#define OP_SET_ANALYTICAL_RGB16 0x2C
#define PHASE_MODE_AUTO 0x00
#define PHASE_MODE_MANUAL 0x01
#define ANALYTICAL_MODEL_SUB_GAMUT 0x00
#define ANALYTICAL_MODEL_LP_LEGACY 0x01
#define ANALYTICAL_SOLVE_NONE 0x00
#define ANALYTICAL_SOLVE_STRICT_SUB_GAMUT 0x01
#define ANALYTICAL_SOLVE_LP_LEGACY 0x02
#define ANALYTICAL_SOLVE_STRICT_FAILED 0x03
#define STATUS_OK 0x00
#define STATUS_BAD_PAYLOAD 0x01
#define STATUS_BAD_OPCODE 0x02
#define STATUS_SOLVE_FAILED 0x03

const uint8_t ledPins[NUM_PINS] = {5, 21};

DMAMEM uint8_t displayBuffer[LED_COUNT * 4] = {0};
DMAMEM uint8_t upperFrameBuffer[LED_COUNT * 4] = {0};
DMAMEM uint8_t lowerFrameBuffer[LED_COUNT * 4] = {0};
DMAMEM uint8_t bfiMapG[LED_COUNT] = {0};
DMAMEM uint8_t bfiMapR[LED_COUNT] = {0};
DMAMEM uint8_t bfiMapB[LED_COUNT] = {0};
DMAMEM uint8_t bfiMapW[LED_COUNT] = {0};
bool renderEnabled = true;
bool manualPhaseMode = false;
bool solverEnabled = false;
uint8_t analyticalModel = ANALYTICAL_MODEL_SUB_GAMUT;
uint8_t analyticalSolvePath = ANALYTICAL_SOLVE_NONE;
uint32_t temporalTick = 0;
ObjectFLED leds(LED_COUNT, displayBuffer, CORDER_GRBW, NUM_PINS, ledPins, 0);

static constexpr uint16_t SOLVER_LUT_SIZE = TemporalBFIRuntime::SOLVER_LUT_SIZE;
static_assert(TemporalBFI::SOLVER_FIXED_BFI_LEVELS == (MAX_BFI_FRAMES + 1), "SOLVER_FIXED_BFI_LEVELS must match MAX_BFI_FRAMES + 1");
static_assert(SOLVER_LUT_SIZE >= 2u, "Derived solver LUT size must be at least 2");

uint8_t solverBFILUT[4][SOLVER_LUT_SIZE] = {0};
DMAMEM uint8_t solverValueLUT[4][SOLVER_LUT_SIZE] = {0};
DMAMEM uint8_t solverValueFloorLUT[4][SOLVER_LUT_SIZE] = {0};

TemporalBFI::SolverRuntime solver;
fl::colorimetric_detail::ProfileCache analyticalCache;

const fl::DiodeProfile testBenchRgbwProfile = {
  {0.6853f, 0.3147f},
  {0.1379f, 0.7480f},
  {0.1295f, 0.0663f},
  {0.3299f, 0.3582f},
  154.670592f / 1543.643989f,
  566.278306f / 1543.643989f,
  129.649350f / 1543.643989f,
  1.0f,
  0,
};

uint16_t lastInputR16 = 0;
uint16_t lastInputG16 = 0;
uint16_t lastInputB16 = 0;
uint16_t lastSolvedR16 = 0;
uint16_t lastSolvedG16 = 0;
uint16_t lastSolvedB16 = 0;
uint16_t lastSolvedW16 = 0;
uint8_t lastStrictOk = 0;
uint16_t lastStrictR16 = 0;
uint16_t lastStrictG16 = 0;
uint16_t lastStrictB16 = 0;
uint16_t lastStrictW16 = 0;
uint16_t lastLpR16 = 0;
uint16_t lastLpG16 = 0;
uint16_t lastLpB16 = 0;
uint16_t lastLpW16 = 0;

enum class DirectFrameState : uint8_t {
  SYNC0,
  SYNC1,
  SYNC2,
  SYNC3,
  KIND,
  LEN_HI,
  LEN_LO,
  PAYLOAD,
  CRC
};

struct DirectFrameParser {
  DirectFrameState state = DirectFrameState::SYNC0;
  uint8_t kind = 0;
  uint16_t expectedLen = 0;
  uint16_t receivedLen = 0;
  uint8_t crc = 0;
  uint8_t payload[DIRECT_FRAME_MAX_PAYLOAD];
} parser;

struct RGBW16Tuple {
  uint16_t r;
  uint16_t g;
  uint16_t b;
  uint16_t w;
};

static inline uint8_t clampU8(int value) {
  if (value < 0) return 0;
  if (value > 255) return 255;
  return (uint8_t)value;
}

static inline uint8_t clampBfi(int value) {
  if (value < 0) return 0;
  if (value > MAX_BFI_FRAMES) return MAX_BFI_FRAMES;
  return (uint8_t)value;
}

static inline uint16_t clampQ16FromFloat(float value) {
  if (!(value > 0.0f)) return 0;
  if (value >= 1.0f) return 65535;
  return (uint16_t)(value * 65535.0f + 0.5f);
}

static inline void normalizeTemporalTick() {
  temporalTick %= (uint32_t)TEMPORAL_BFI_CYCLE;
}

static inline TemporalTrue16BFIPolicySolver::EncodedState solveTrue16State(uint16_t valueQ16, uint8_t channel) {
  return solver.solve(valueQ16, channel);
}

void resetParser() {
  parser.state = DirectFrameState::SYNC0;
  parser.kind = 0;
  parser.expectedLen = 0;
  parser.receivedLen = 0;
  parser.crc = 0;
}

void writeFrameByte(uint8_t value) {
  Serial.write(value);
}

void sendFrame(uint8_t kind, const uint8_t* payload, uint16_t payloadLen) {
  if (payloadLen > DIRECT_FRAME_MAX_PAYLOAD) payloadLen = DIRECT_FRAME_MAX_PAYLOAD;
  uint8_t lenHi = (payloadLen >> 8) & 0xFF;
  uint8_t lenLo = payloadLen & 0xFF;
  uint8_t crc = kind ^ lenHi ^ lenLo;
  writeFrameByte((uint8_t)DIRECT_FRAME_MAGIC_0);
  writeFrameByte((uint8_t)DIRECT_FRAME_MAGIC_1);
  writeFrameByte((uint8_t)DIRECT_FRAME_MAGIC_2);
  writeFrameByte((uint8_t)DIRECT_FRAME_MAGIC_3);
  writeFrameByte(kind);
  writeFrameByte(lenHi);
  writeFrameByte(lenLo);
  for (uint16_t i = 0; i < payloadLen; i++) {
    crc ^= payload[i];
    writeFrameByte(payload[i]);
  }
  writeFrameByte(crc);
}

void sendLog(const char* text) {
  sendFrame(FRAME_KIND_LOG, (const uint8_t*)text, strlen(text));
}

static inline void writeU16BE(uint8_t* payload, uint8_t offset, uint16_t value) {
  payload[offset] = (value >> 8) & 0xFF;
  payload[offset + 1] = value & 0xFF;
}

void sendCalResponse(uint8_t op, uint8_t status) {
  uint8_t payload[51];
  payload[0] = op;
  payload[1] = status;
  payload[2] = renderEnabled ? 1 : 0;
  payload[3] = manualPhaseMode ? 1 : 0;
  payload[4] = (uint8_t)temporalTick;
  payload[5] = upperFrameBuffer[1];
  payload[6] = upperFrameBuffer[0];
  payload[7] = upperFrameBuffer[2];
  payload[8] = upperFrameBuffer[3];
  payload[9] = bfiMapR[0];
  payload[10] = bfiMapG[0];
  payload[11] = bfiMapB[0];
  payload[12] = bfiMapW[0];
  payload[13] = 0;
  payload[14] = 0;
  payload[15] = 0;
  payload[16] = 0;
  payload[17] = solverEnabled ? 1 : 0;
  writeU16BE(payload, 18, lastSolvedR16);
  writeU16BE(payload, 20, lastSolvedG16);
  writeU16BE(payload, 22, lastSolvedB16);
  writeU16BE(payload, 24, lastSolvedW16);
  writeU16BE(payload, 26, lastInputR16);
  writeU16BE(payload, 28, lastInputG16);
  writeU16BE(payload, 30, lastInputB16);
  payload[32] = analyticalModel;
  payload[33] = analyticalSolvePath;
  payload[34] = lastStrictOk;
  writeU16BE(payload, 35, lastStrictR16);
  writeU16BE(payload, 37, lastStrictG16);
  writeU16BE(payload, 39, lastStrictB16);
  writeU16BE(payload, 41, lastStrictW16);
  writeU16BE(payload, 43, lastLpR16);
  writeU16BE(payload, 45, lastLpG16);
  writeU16BE(payload, 47, lastLpB16);
  writeU16BE(payload, 49, lastLpW16);
  sendFrame(FRAME_KIND_CAL_RSP, payload, sizeof(payload));
}

void clearAnalyticalDebug() {
  lastStrictOk = 0;
  lastStrictR16 = 0;
  lastStrictG16 = 0;
  lastStrictB16 = 0;
  lastStrictW16 = 0;
  lastLpR16 = 0;
  lastLpG16 = 0;
  lastLpB16 = 0;
  lastLpW16 = 0;
  analyticalSolvePath = ANALYTICAL_SOLVE_NONE;
}

void clearAll() {
  memset(upperFrameBuffer, 0, sizeof(upperFrameBuffer));
  memset(lowerFrameBuffer, 0, sizeof(lowerFrameBuffer));
  memset(displayBuffer, 0, sizeof(displayBuffer));
  memset(bfiMapG, 0, sizeof(bfiMapG));
  memset(bfiMapR, 0, sizeof(bfiMapR));
  memset(bfiMapB, 0, sizeof(bfiMapB));
  memset(bfiMapW, 0, sizeof(bfiMapW));
  lastInputR16 = 0;
  lastInputG16 = 0;
  lastInputB16 = 0;
  lastSolvedR16 = 0;
  lastSolvedG16 = 0;
  lastSolvedB16 = 0;
  lastSolvedW16 = 0;
  clearAnalyticalDebug();
  normalizeTemporalTick();
}

void fillAll(uint8_t r, uint8_t g, uint8_t b, uint8_t w, uint8_t bfiR, uint8_t bfiG, uint8_t bfiB, uint8_t bfiW) {
  for (uint16_t i = 0; i < LED_COUNT; i++) {
    uint32_t offset = (uint32_t)i * 4u;
    upperFrameBuffer[offset + 0] = g;
    upperFrameBuffer[offset + 1] = r;
    upperFrameBuffer[offset + 2] = b;
    upperFrameBuffer[offset + 3] = w;
    lowerFrameBuffer[offset + 0] = 0;
    lowerFrameBuffer[offset + 1] = 0;
    lowerFrameBuffer[offset + 2] = 0;
    lowerFrameBuffer[offset + 3] = 0;
    bfiMapG[i] = bfiG;
    bfiMapR[i] = bfiR;
    bfiMapB[i] = bfiB;
    bfiMapW[i] = bfiW;
  }
  lastInputR16 = (uint16_t)r * 257u;
  lastInputG16 = (uint16_t)g * 257u;
  lastInputB16 = (uint16_t)b * 257u;
  lastSolvedR16 = (uint16_t)r * 257u;
  lastSolvedG16 = (uint16_t)g * 257u;
  lastSolvedB16 = (uint16_t)b * 257u;
  lastSolvedW16 = (uint16_t)w * 257u;
  clearAnalyticalDebug();
  normalizeTemporalTick();
}

void applySolvedRGBW16(uint16_t r16, uint16_t g16, uint16_t b16, uint16_t w16) {
  const auto gState = solveTrue16State(g16, 0);
  const auto rState = solveTrue16State(r16, 1);
  const auto bState = solveTrue16State(b16, 2);
  const auto wState = solveTrue16State(w16, 3);

  for (uint16_t i = 0; i < LED_COUNT; i++) {
    uint32_t offset = (uint32_t)i * 4u;
    upperFrameBuffer[offset + 0] = gState.value;
    upperFrameBuffer[offset + 1] = rState.value;
    upperFrameBuffer[offset + 2] = bState.value;
    upperFrameBuffer[offset + 3] = wState.value;
    lowerFrameBuffer[offset + 0] = gState.lowerValue;
    lowerFrameBuffer[offset + 1] = rState.lowerValue;
    lowerFrameBuffer[offset + 2] = bState.lowerValue;
    lowerFrameBuffer[offset + 3] = wState.lowerValue;
    bfiMapG[i] = clampBfi(gState.bfi);
    bfiMapR[i] = clampBfi(rState.bfi);
    bfiMapB[i] = clampBfi(bState.bfi);
    bfiMapW[i] = clampBfi(wState.bfi);
  }

  lastSolvedR16 = r16;
  lastSolvedG16 = g16;
  lastSolvedB16 = b16;
  lastSolvedW16 = w16;
  normalizeTemporalTick();
}

void fillAll16(uint16_t r16, uint16_t g16, uint16_t b16, uint16_t w16) {
  lastInputR16 = r16;
  lastInputG16 = g16;
  lastInputB16 = b16;
  clearAnalyticalDebug();
  applySolvedRGBW16(r16, g16, b16, w16);
}

bool solveAnalyticalRGB16(uint16_t r16, uint16_t g16, uint16_t b16, uint8_t model, RGBW16Tuple& solved) {
  const float sR = (float)r16 * (1.0f / 65535.0f);
  const float sG = (float)g16 * (1.0f / 65535.0f);
  const float sB = (float)b16 * (1.0f / 65535.0f);
  float strictRgbw[4] = {0.0f, 0.0f, 0.0f, 0.0f};
  float lpRgbw[4] = {0.0f, 0.0f, 0.0f, 0.0f};

  lastStrictOk = fl::colorimetric_detail::solve_strict_subgamut(analyticalCache, sR, sG, sB, strictRgbw) ? 1 : 0;
  fl::colorimetric_detail::solve_wx_lp(analyticalCache, sR, sG, sB, lpRgbw);

  lastStrictR16 = clampQ16FromFloat(strictRgbw[0]);
  lastStrictG16 = clampQ16FromFloat(strictRgbw[1]);
  lastStrictB16 = clampQ16FromFloat(strictRgbw[2]);
  lastStrictW16 = clampQ16FromFloat(strictRgbw[3]);
  lastLpR16 = clampQ16FromFloat(lpRgbw[0]);
  lastLpG16 = clampQ16FromFloat(lpRgbw[1]);
  lastLpB16 = clampQ16FromFloat(lpRgbw[2]);
  lastLpW16 = clampQ16FromFloat(lpRgbw[3]);

  if (model == ANALYTICAL_MODEL_LP_LEGACY) {
    analyticalSolvePath = ANALYTICAL_SOLVE_LP_LEGACY;
    solved = {lastLpR16, lastLpG16, lastLpB16, lastLpW16};
  } else if (!lastStrictOk) {
    analyticalSolvePath = ANALYTICAL_SOLVE_STRICT_FAILED;
    solved = {0, 0, 0, 0};
    return false;
  } else {
    analyticalSolvePath = ANALYTICAL_SOLVE_STRICT_SUB_GAMUT;
    solved = {lastStrictR16, lastStrictG16, lastStrictB16, lastStrictW16};
  }
  return true;
}

bool fillAnalyticalRGB16(uint16_t r16, uint16_t g16, uint16_t b16, uint8_t model) {
  analyticalModel = (model == ANALYTICAL_MODEL_LP_LEGACY) ? ANALYTICAL_MODEL_LP_LEGACY : ANALYTICAL_MODEL_SUB_GAMUT;
  lastInputR16 = r16;
  lastInputG16 = g16;
  lastInputB16 = b16;
  RGBW16Tuple solved;
  if (!solveAnalyticalRGB16(r16, g16, b16, analyticalModel, solved)) {
    return false;
  }
  applySolvedRGBW16(solved.r, solved.g, solved.b, solved.w);
  return true;
}

void setTemporalBlend(
  uint8_t lowerR,
  uint8_t lowerG,
  uint8_t lowerB,
  uint8_t lowerW,
  uint8_t upperR,
  uint8_t upperG,
  uint8_t upperB,
  uint8_t upperW,
  uint8_t bfiR,
  uint8_t bfiG,
  uint8_t bfiB,
  uint8_t bfiW
) {
  for (uint16_t i = 0; i < LED_COUNT; i++) {
    uint32_t offset = (uint32_t)i * 4u;
    lowerFrameBuffer[offset + 0] = lowerG;
    lowerFrameBuffer[offset + 1] = lowerR;
    lowerFrameBuffer[offset + 2] = lowerB;
    lowerFrameBuffer[offset + 3] = lowerW;
    upperFrameBuffer[offset + 0] = upperG;
    upperFrameBuffer[offset + 1] = upperR;
    upperFrameBuffer[offset + 2] = upperB;
    upperFrameBuffer[offset + 3] = upperW;
    bfiMapG[i] = bfiG;
    bfiMapR[i] = bfiR;
    bfiMapB[i] = bfiB;
    bfiMapW[i] = bfiW;
  }
  lastInputR16 = (uint16_t)upperR * 257u;
  lastInputG16 = (uint16_t)upperG * 257u;
  lastInputB16 = (uint16_t)upperB * 257u;
  lastSolvedR16 = (uint16_t)upperR * 257u;
  lastSolvedG16 = (uint16_t)upperG * 257u;
  lastSolvedB16 = (uint16_t)upperB * 257u;
  lastSolvedW16 = (uint16_t)upperW * 257u;
  clearAnalyticalDebug();
  normalizeTemporalTick();
}

void renderIndependentSubpixelBFI() {
  const uint8_t phase = (uint8_t)(temporalTick % (uint32_t)TEMPORAL_BFI_CYCLE);
  TemporalBFI::SolverRuntime::renderSubpixelBFI_RGBW(
      upperFrameBuffer, lowerFrameBuffer,
      bfiMapG, bfiMapR, bfiMapB, bfiMapW,
      displayBuffer, LED_COUNT, phase);
}

uint16_t readU16(const uint8_t* payload, uint8_t offset) {
  return ((uint16_t)payload[offset] << 8) | payload[offset + 1];
}

void handleCalFrame(const uint8_t* payload, uint16_t payloadLen) {
  if (payloadLen < 1) {
    sendCalResponse(0xFF, STATUS_BAD_PAYLOAD);
    return;
  }

  const uint8_t op = payload[0];
  uint8_t status = STATUS_OK;

  switch (op) {
    case OP_GET_STATE:
      break;
    case OP_SET_RENDER_ENABLED:
      if (payloadLen < 2) status = STATUS_BAD_PAYLOAD;
      else renderEnabled = payload[1] ? true : false;
      break;
    case OP_SET_FILL:
      if (payloadLen < 9) status = STATUS_BAD_PAYLOAD;
      else fillAll(clampU8(payload[1]), clampU8(payload[2]), clampU8(payload[3]), clampU8(payload[4]), clampBfi(payload[5]), clampBfi(payload[6]), clampBfi(payload[7]), clampBfi(payload[8]));
      break;
    case OP_SET_TEMPORAL_BLEND:
      if (payloadLen < 13) status = STATUS_BAD_PAYLOAD;
      else setTemporalBlend(
        clampU8(payload[1]),
        clampU8(payload[2]),
        clampU8(payload[3]),
        clampU8(payload[4]),
        clampU8(payload[5]),
        clampU8(payload[6]),
        clampU8(payload[7]),
        clampU8(payload[8]),
        clampBfi(payload[9]),
        clampBfi(payload[10]),
        clampBfi(payload[11]),
        clampBfi(payload[12])
      );
      break;
    case OP_CLEAR:
      clearAll();
      break;
    case OP_SET_PHASE:
      if (payloadLen < 2) status = STATUS_BAD_PAYLOAD;
      else {
        temporalTick = payload[1];
        normalizeTemporalTick();
      }
      break;
    case OP_SET_PHASE_MODE:
      if (payloadLen < 2) status = STATUS_BAD_PAYLOAD;
      else manualPhaseMode = (payload[1] == PHASE_MODE_MANUAL);
      break;
    case OP_SET_SOLVER_ENABLED:
      if (payloadLen < 2) status = STATUS_BAD_PAYLOAD;
      else solverEnabled = payload[1] ? true : false;
      break;
    case OP_SET_FILL16:
      if (payloadLen < 9) status = STATUS_BAD_PAYLOAD;
      else fillAll16(readU16(payload, 1), readU16(payload, 3), readU16(payload, 5), readU16(payload, 7));
      break;
    case OP_SET_ANALYTICAL_RGB16:
      if (payloadLen < 8) status = STATUS_BAD_PAYLOAD;
      else if (!fillAnalyticalRGB16(readU16(payload, 2), readU16(payload, 4), readU16(payload, 6), payload[1])) status = STATUS_SOLVE_FAILED;
      break;
    case OP_COMMIT:
      break;
    default:
      status = STATUS_BAD_OPCODE;
      break;
  }

  sendCalResponse(op, status);
}

void handleFrame(uint8_t kind, const uint8_t* payload, uint16_t payloadLen) {
  if (kind == FRAME_KIND_HELLO_REQ) {
    static const uint8_t helloPayload[] = {'t', 'e', 'e', 'n', 's', 'y', '-', 'r', 'g', 'b', 'w', '-', 'a', 'n', 'a', 'l', 'y', 't', 'i', 'c', '-', 'v', '1'};
    sendFrame(FRAME_KIND_HELLO_RSP, helloPayload, sizeof(helloPayload));
    return;
  }
  if (kind == FRAME_KIND_PING_REQ) {
    sendFrame(FRAME_KIND_PING_RSP, payload, payloadLen);
    return;
  }
  if (kind == FRAME_KIND_CAL_REQ) {
    handleCalFrame(payload, payloadLen);
    return;
  }
}

bool processFrameByte(uint8_t input) {
  switch (parser.state) {
    case DirectFrameState::SYNC0:
      if (input == (uint8_t)DIRECT_FRAME_MAGIC_0) {
        resetParser();
        parser.state = DirectFrameState::SYNC1;
        return true;
      }
      return false;
    case DirectFrameState::SYNC1:
      if (input == (uint8_t)DIRECT_FRAME_MAGIC_1) parser.state = DirectFrameState::SYNC2;
      else resetParser();
      return true;
    case DirectFrameState::SYNC2:
      if (input == (uint8_t)DIRECT_FRAME_MAGIC_2) parser.state = DirectFrameState::SYNC3;
      else resetParser();
      return true;
    case DirectFrameState::SYNC3:
      if (input == (uint8_t)DIRECT_FRAME_MAGIC_3) parser.state = DirectFrameState::KIND;
      else resetParser();
      return true;
    case DirectFrameState::KIND:
      parser.kind = input;
      parser.crc = input;
      parser.state = DirectFrameState::LEN_HI;
      return true;
    case DirectFrameState::LEN_HI:
      parser.expectedLen = ((uint16_t)input << 8);
      parser.crc ^= input;
      parser.state = DirectFrameState::LEN_LO;
      return true;
    case DirectFrameState::LEN_LO:
      parser.expectedLen |= input;
      parser.crc ^= input;
      parser.receivedLen = 0;
      if (parser.expectedLen > DIRECT_FRAME_MAX_PAYLOAD) resetParser();
      else if (parser.expectedLen == 0) parser.state = DirectFrameState::CRC;
      else parser.state = DirectFrameState::PAYLOAD;
      return true;
    case DirectFrameState::PAYLOAD:
      parser.payload[parser.receivedLen++] = input;
      parser.crc ^= input;
      if (parser.receivedLen >= parser.expectedLen) parser.state = DirectFrameState::CRC;
      return true;
    case DirectFrameState::CRC:
      if (input == parser.crc) handleFrame(parser.kind, parser.payload, parser.expectedLen);
      resetParser();
      return true;
  }
  resetParser();
  return false;
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  leds.begin(1.4, 100);
  leds.setBrightness(255);

  fl::set_rgbw_colorimetric_profile(&testBenchRgbwProfile);
  fl::colorimetric_detail::build_profile_cache(&testBenchRgbwProfile, &analyticalCache);

  auto& cfg = solver.config();
  cfg.maxBFI = MAX_BFI_FRAMES;
  cfg.relativeErrorDivisor = 24;
  cfg.minErrorQ16 = 64;
  cfg.enableInputQ16Calibration = false;

  solver.attachLUTs(&solverValueLUT[0][0], &solverBFILUT[0][0],
                    &solverValueFloorLUT[0][0], nullptr, SOLVER_LUT_SIZE);

  sendLog("Generating precomputed true16 solver LUT...");

  solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16);

  sendLog("Precomputed true16 solver LUT ready.");

  clearAll();
  solverEnabled = true;
  sendLog("teensy RGBW analytical FastLED calibration sketch boot (TemporalBFI output, ObjectFLED driver)");
}

void loop() {
  static uint32_t lastShowUs = (uint32_t)micros();

  for (uint16_t budget = 0; budget < 96 && Serial.available(); budget++) {
    uint8_t input = (uint8_t)Serial.read();
    processFrameByte(input);
  }

  uint32_t nowUs = (uint32_t)micros();
  if ((uint32_t)(nowUs - lastShowUs) < MIN_SHOW_INTERVAL_US) {
    yield();
    return;
  }

  if (!renderEnabled) {
    memset(displayBuffer, 0, sizeof(displayBuffer));
  } else {
    renderIndependentSubpixelBFI();
  }

  leds.show();
  lastShowUs = (uint32_t)micros();

  if (!manualPhaseMode) {
    temporalTick++;
    normalizeTemporalTick();
  }
}