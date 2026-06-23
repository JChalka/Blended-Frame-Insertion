#include <Arduino.h>

#include <ObjectFLED.h>

#define USER_DEFINED_TEMPORAL_SOLVER_HEADER

#include "temporal_runtime_solver_header_temporal_blend_130815_v2.h"

#include <TemporalBFI.h>
#include <TemporalBFIRuntime.h>

// Direct 3DLUT/1DLUT correction companion sketch. The host GUI applies the
// correction/cube and sends already-solved RGB/RGBW/RGBWW channel values here.
// ObjectFLED currently emits RGB/RGBW only. RGBWW/RGBCCT requests are rejected
// until native 5-channel output lands; W2 is never folded into W silently.

#define NUM_PINS 2
#define LEDS_PER_PIN 48
#define LED_COUNT (NUM_PINS * LEDS_PER_PIN)
#define SERIAL_BAUD 30000000UL
#define MAX_BFI_FRAMES 4
#define DEFAULT_BLEND_CYCLE 5
#define TEMPORAL_BFI_CYCLE (MAX_BFI_FRAMES + 1)
#define TEMPORAL_BLEND_CYCLE_MAX 60
#define MIN_SHOW_INTERVAL_US 1600u  // 625 FPS max
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
#define OP_SET_OUTPUT_MODE 0x2E
#define OP_SET_DIRECT_RGBWW16 0x30
#define PHASE_MODE_AUTO 0x00
#define PHASE_MODE_MANUAL 0x01
#define OUTPUT_MODE_RGB 0x00
#define OUTPUT_MODE_RGBW 0x01
#define OUTPUT_MODE_RGBWW 0x02

#ifndef TEMPORAL_CAL_TARGET_OUTPUT_MODE
#define TEMPORAL_CAL_TARGET_OUTPUT_MODE OUTPUT_MODE_RGBW
#endif

#if TEMPORAL_CAL_TARGET_OUTPUT_MODE == OUTPUT_MODE_RGB
#define TEMPORAL_CAL_OBJECTFLED_CORDER CORDER_GRB
#define TEMPORAL_CAL_TARGET_CHANNELS 3
#elif TEMPORAL_CAL_TARGET_OUTPUT_MODE == OUTPUT_MODE_RGBW
#define TEMPORAL_CAL_OBJECTFLED_CORDER CORDER_GRBW
#define TEMPORAL_CAL_TARGET_CHANNELS 4
#elif TEMPORAL_CAL_TARGET_OUTPUT_MODE == OUTPUT_MODE_RGBWW
#error "TEMPORAL_CAL_TARGET_OUTPUT_MODE=OUTPUT_MODE_RGBWW requires native 5-channel ObjectFLED support."
#else
#error "Unsupported TEMPORAL_CAL_TARGET_OUTPUT_MODE"
#endif

#define STATUS_OK 0x00
#define STATUS_BAD_PAYLOAD 0x01
#define STATUS_BAD_OPCODE 0x02
#define STATUS_UNSUPPORTED_OUTPUT_MODE 0x04

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
uint8_t outputMode = OUTPUT_MODE_RGBW;
uint32_t temporalTick = 0;
ObjectFLED leds(LED_COUNT, displayBuffer, TEMPORAL_CAL_OBJECTFLED_CORDER, NUM_PINS, ledPins, 0);

static constexpr uint16_t SOLVER_LUT_SIZE = TemporalBFIRuntime::SOLVER_LUT_SIZE;
static_assert(TemporalBFI::SOLVER_FIXED_BFI_LEVELS == (MAX_BFI_FRAMES + 1), "SOLVER_FIXED_BFI_LEVELS must match MAX_BFI_FRAMES + 1");
static_assert(SOLVER_LUT_SIZE >= 2u, "Derived solver LUT size must be at least 2");

uint8_t solverBFILUT[4][SOLVER_LUT_SIZE] = {0};
DMAMEM uint8_t solverValueLUT[4][SOLVER_LUT_SIZE] = {0};
DMAMEM uint8_t solverValueFloorLUT[4][SOLVER_LUT_SIZE] = {0};

TemporalBFI::SolverRuntime solver;
static constexpr TemporalBFI::RenderOptions RENDER_OPTIONS = {
  TemporalBFI::LedColorOrder::GRBW,
  TemporalBFI::BfiMapStorageMode::Separate,
};

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

static inline void normalizeTemporalTick() {
  temporalTick %= (uint32_t)TEMPORAL_BFI_CYCLE;
}

static inline uint8_t activeLogicalChannels() {
  return (outputMode == OUTPUT_MODE_RGB) ? 3 : (outputMode == OUTPUT_MODE_RGBWW ? 5 : 4);
}

static inline uint8_t objectFledOutputChannels() {
  return TEMPORAL_CAL_TARGET_CHANNELS;
}

static inline uint8_t supportedOutputModeMask() {
  uint8_t mask = 0x01;  // RGB
#if TEMPORAL_CAL_TARGET_OUTPUT_MODE >= OUTPUT_MODE_RGBW
  mask |= 0x02;
#endif
#if TEMPORAL_CAL_TARGET_OUTPUT_MODE >= OUTPUT_MODE_RGBWW
  mask |= 0x04;
#endif
  return mask;
}

static inline bool outputModeSupported(uint8_t mode) {
  if (mode == OUTPUT_MODE_RGB) return true;
  if (mode == OUTPUT_MODE_RGBW) return TEMPORAL_CAL_TARGET_OUTPUT_MODE >= OUTPUT_MODE_RGBW;
  if (mode == OUTPUT_MODE_RGBWW) return TEMPORAL_CAL_TARGET_OUTPUT_MODE >= OUTPUT_MODE_RGBWW;
  return false;
}

static inline bool setOutputMode(uint8_t mode) {
  if (!outputModeSupported(mode)) return false;
  outputMode = mode;
  return true;
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

void sendCalResponse(uint8_t op, uint8_t status) {
  uint8_t payload[32] = {0};
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
  payload[18] = outputMode;
  payload[19] = supportedOutputModeMask();
  payload[20] = objectFledOutputChannels();
  payload[21] = activeLogicalChannels();
  payload[22] = TEMPORAL_CAL_TARGET_OUTPUT_MODE;
  payload[23] = 0;  // no fold/stub active: unsupported modes are rejected
  payload[29] = 1;  // response extension version
  sendFrame(FRAME_KIND_CAL_RSP, payload, sizeof(payload));
}

void clearAll() {
  memset(upperFrameBuffer, 0, sizeof(upperFrameBuffer));
  memset(lowerFrameBuffer, 0, sizeof(lowerFrameBuffer));
  memset(displayBuffer, 0, sizeof(displayBuffer));
  memset(bfiMapG, 0, sizeof(bfiMapG));
  memset(bfiMapR, 0, sizeof(bfiMapR));
  memset(bfiMapB, 0, sizeof(bfiMapB));
  memset(bfiMapW, 0, sizeof(bfiMapW));
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
  normalizeTemporalTick();
}

bool fillAllOutput16(uint16_t r16, uint16_t g16, uint16_t b16, uint16_t w16) {
  if (!outputModeSupported(outputMode)) return false;
  if (outputMode == OUTPUT_MODE_RGB) {
    if (w16 != 0) return false;
    w16 = 0;
  }

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

  normalizeTemporalTick();
  return true;
}

bool fillAll16(uint16_t r16, uint16_t g16, uint16_t b16, uint16_t w16) {
  return fillAllOutput16(r16, g16, b16, w16);
}

bool fillAllRgbww16(uint16_t, uint16_t, uint16_t, uint16_t, uint16_t) {
  return false;
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
  normalizeTemporalTick();
}

void renderIndependentSubpixelBFI() {
  const uint8_t phase = (uint8_t)(temporalTick % (uint32_t)TEMPORAL_BFI_CYCLE);
  TemporalBFI::BfiMapView bfiMaps;
  bfiMaps.bfiMapG = bfiMapG;
  bfiMaps.bfiMapR = bfiMapR;
  bfiMaps.bfiMapB = bfiMapB;
  bfiMaps.bfiMapW1 = bfiMapW;

  TemporalBFI::SolverRuntime::renderLoopStatic(
      upperFrameBuffer, lowerFrameBuffer,
      bfiMaps,
      displayBuffer, LED_COUNT, phase,
      RENDER_OPTIONS);
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
      else solverEnabled = true;
      break;
    case OP_SET_OUTPUT_MODE:
      if (payloadLen < 2) status = STATUS_BAD_PAYLOAD;
      else if (!setOutputMode(payload[1])) status = STATUS_UNSUPPORTED_OUTPUT_MODE;
      break;
    case OP_SET_FILL16:
      if (payloadLen < 9) status = STATUS_BAD_PAYLOAD;
      else if (!fillAll16(readU16(payload, 1), readU16(payload, 3), readU16(payload, 5), readU16(payload, 7))) status = STATUS_UNSUPPORTED_OUTPUT_MODE;
      break;
    case OP_SET_DIRECT_RGBWW16:
      if (payloadLen < 11) status = STATUS_BAD_PAYLOAD;
      else if (!fillAllRgbww16(readU16(payload, 1), readU16(payload, 3), readU16(payload, 5), readU16(payload, 7), readU16(payload, 9))) status = STATUS_UNSUPPORTED_OUTPUT_MODE;
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
    static const uint8_t helloPayload[] = {'t', 'e', 'e', 'n', 's', 'y', '-', 'c', 'a', 'l', '-', 'd', 'i', 'r', 'e', 'c', 't', '-', 'v', '1'};
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

  auto& cfg = solver.config();
  cfg.maxBFI = MAX_BFI_FRAMES;
  cfg.relativeErrorDivisor = 24;
  cfg.minErrorQ16 = 64;
  cfg.enableInputQ16Calibration = false;
  solver.setLedColorOrder(RENDER_OPTIONS.colorOrder);
  solver.setSolverLUTMode(TemporalBFI::SolverLUTMode::PerChannel);

  solver.attachLUTs(&solverValueLUT[0][0], &solverBFILUT[0][0],
                    &solverValueFloorLUT[0][0], nullptr, SOLVER_LUT_SIZE);

  sendLog("Generating precomputed true16 solver LUT...");

  solver.precompute(TemporalTrue16BFIPolicySolver::encodeStateFrom16, 4);

  sendLog("Precomputed true16 solver LUT ready.");

  clearAll();
  solverEnabled = true;
  sendLog("teensy temporal calibration direct serial sketch boot (raw true16 solver LUT precomputed, calibration disabled)");
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