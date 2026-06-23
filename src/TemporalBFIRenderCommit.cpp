#include "TemporalBFIRenderCommit.h"

namespace TemporalBFI {

static inline void writeMapped3(uint8_t* dst, const uint8_t* logical,
                                const uint8_t (&map)[3])
{
    dst[0] = logical[map[0]];
    dst[1] = logical[map[1]];
    dst[2] = logical[map[2]];
}

static inline void writeMapped4(uint8_t* dst, const uint8_t* logical,
                                const uint8_t (&map)[4])
{
    dst[0] = logical[map[0]];
    dst[1] = logical[map[1]];
    dst[2] = logical[map[2]];
    dst[3] = logical[map[3]];
}

static inline void writeMapped5(uint8_t* dst, const uint8_t* logical,
                                const uint8_t (&map)[5])
{
    dst[0] = logical[map[0]];
    dst[1] = logical[map[1]];
    dst[2] = logical[map[2]];
    dst[3] = logical[map[3]];
    dst[4] = logical[map[4]];
}

uint8_t SolverRuntime::packedBytesPerPixelForChannels(uint8_t channels)
{
    return (uint8_t)((channels + 1u) / 2u);
}

uint8_t SolverRuntime::readPackedBfiChannelForChannels(const uint8_t* packed,
                                                       uint16_t pixelIndex,
                                                       uint8_t channel,
                                                       uint8_t channels)
{
    if (!packed || channels == 0 || channel >= channels) return 0;
    const uint8_t bpp = packedBytesPerPixelForChannels(channels);
    const uint32_t off = (uint32_t)pixelIndex * bpp + (channel / 2u);
    const uint8_t pair = packed[off];
    return (channel % 2u == 0u)
        ? (uint8_t)(pair >> 4)
        : (uint8_t)(pair & 0x0Fu);
}

void SolverRuntime::writePackedBfiChannelForChannels(uint8_t* packed,
                                                     uint16_t pixelIndex,
                                                     uint8_t channel,
                                                     uint8_t channels,
                                                     uint8_t value)
{
    if (!packed || channels == 0 || channel >= channels) return;
    const uint8_t bpp = packedBytesPerPixelForChannels(channels);
    const uint32_t off = (uint32_t)pixelIndex * bpp + (channel / 2u);
    uint8_t pair = packed[off];
    const uint8_t v = (uint8_t)(value & 0x0Fu);
    if (channel % 2u == 0u) {
        pair = (uint8_t)((pair & 0x0Fu) | (uint8_t)(v << 4));
    } else {
        pair = (uint8_t)((pair & 0xF0u) | v);
    }
    packed[off] = pair;
}

const uint8_t* SolverRuntime::separateBfiMapForChannel(const BfiMapView& bfiMaps,
                                                       uint8_t channel)
{
    switch (channel)
    {
        case 0: return bfiMaps.bfiMapG;
        case 1: return bfiMaps.bfiMapR;
        case 2: return bfiMaps.bfiMapB;
        case 3: return bfiMaps.bfiMapW1;
        case 4: return bfiMaps.bfiMapW2;
        default: return nullptr;
    }
}

uint8_t* SolverRuntime::separateBfiMapForChannel(BfiMapWriteView& bfiMaps,
                                                 uint8_t channel)
{
    switch (channel)
    {
        case 0: return bfiMaps.bfiMapG;
        case 1: return bfiMaps.bfiMapR;
        case 2: return bfiMaps.bfiMapB;
        case 3: return bfiMaps.bfiMapW1;
        case 4: return bfiMaps.bfiMapW2;
        default: return nullptr;
    }
}

void SolverRuntime::renderLoopStatic(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const BfiMapView& bfiMaps,
    uint8_t* displayBuffer, uint16_t pixelCount,
    uint8_t phase,
    const RenderOptions& options)
{
    if (!upperFrame || !displayBuffer) return;

    const uint8_t channels = channelCountForColorOrder(options.colorOrder);
    uint8_t map[5] = {0, 1, 2, 3, 4};
    if (!colorOrderMapForChannels(options.colorOrder, channels, map)) {
        for (uint8_t i = 0; i < channels; ++i) map[i] = i;
    }

    const uint8_t* src = upperFrame;
    const uint8_t* flr = floorFrame;
    uint8_t* dst = displayBuffer;

    for (uint16_t i = 0; i < pixelCount; ++i)
    {
        uint8_t logical[5] = {0, 0, 0, 0, 0};
        for (uint8_t ch = 0; ch < channels; ++ch)
        {
            uint8_t bfi = 0;
            if (options.bfiMapStorage == BfiMapStorageMode::Packed) {
                bfi = readPackedBfiChannelForChannels(bfiMaps.packedBfiMap, i, ch, channels);
            } else {
                const uint8_t* m = separateBfiMapForChannel(bfiMaps, ch);
                bfi = m ? m[i] : 0;
            }
            const bool up = channelOnPhase(bfi, phase);
            logical[ch] = up ? src[ch] : (flr ? flr[ch] : 0);
        }

        if (channels == 3) {
            const uint8_t map3[3] = {map[0], map[1], map[2]};
            writeMapped3(dst, logical, map3);
        } else if (channels == 4) {
            const uint8_t map4[4] = {map[0], map[1], map[2], map[3]};
            writeMapped4(dst, logical, map4);
        } else {
            const uint8_t map5[5] = {map[0], map[1], map[2], map[3], map[4]};
            writeMapped5(dst, logical, map5);
        }

        src += channels;
        if (flr) flr += channels;
        dst += channels;
    }
}

void SolverRuntime::renderIndexedStatic(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const BfiMapView& bfiMaps,
    uint8_t* displayBuffer, uint16_t pixelIndex,
    uint8_t phase,
    const RenderOptions& options)
{
    if (!upperFrame || !displayBuffer) return;

    const uint8_t channels = channelCountForColorOrder(options.colorOrder);
    uint8_t map[5] = {0, 1, 2, 3, 4};
    if (!colorOrderMapForChannels(options.colorOrder, channels, map)) {
        for (uint8_t i = 0; i < channels; ++i) map[i] = i;
    }

    const uint32_t off = (uint32_t)pixelIndex * channels;
    const uint8_t* src = upperFrame + off;
    const uint8_t* flr = floorFrame ? floorFrame + off : nullptr;
    uint8_t* dst = displayBuffer + off;

    uint8_t logical[5] = {0, 0, 0, 0, 0};
    for (uint8_t ch = 0; ch < channels; ++ch)
    {
        uint8_t bfi = 0;
        if (options.bfiMapStorage == BfiMapStorageMode::Packed) {
            bfi = readPackedBfiChannelForChannels(bfiMaps.packedBfiMap, pixelIndex, ch, channels);
        } else {
            const uint8_t* m = separateBfiMapForChannel(bfiMaps, ch);
            bfi = m ? m[pixelIndex] : 0;
        }
        const bool up = channelOnPhase(bfi, phase);
        logical[ch] = up ? src[ch] : (flr ? flr[ch] : 0);
    }

    if (channels == 3) {
        const uint8_t map3[3] = {map[0], map[1], map[2]};
        writeMapped3(dst, logical, map3);
    } else if (channels == 4) {
        const uint8_t map4[4] = {map[0], map[1], map[2], map[3]};
        writeMapped4(dst, logical, map4);
    } else {
        const uint8_t map5[5] = {map[0], map[1], map[2], map[3], map[4]};
        writeMapped5(dst, logical, map5);
    }
}

void SolverRuntime::renderLoop(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const BfiMapView& bfiMaps,
    uint8_t* displayBuffer, uint16_t pixelCount,
    const RenderOptions* options) const
{
    if (!upperFrame || !displayBuffer) return;

    RenderOptions active;
    if (options) {
        active = *options;
    } else {
        active.colorOrder = m_ledColorOrder;
        active.bfiMapStorage = BfiMapStorageMode::Separate;
    }

    const uint8_t channels = channelCountForColorOrder(active.colorOrder);
    uint8_t map[5] = {0, 1, 2, 3, 4};
    if (!colorOrderMapForChannels(active.colorOrder, channels, map)) {
        for (uint8_t i = 0; i < channels; ++i) map[i] = i;
    }

    const uint8_t* src = upperFrame;
    const uint8_t* flr = floorFrame;
    uint8_t* dst = displayBuffer;

    for (uint16_t i = 0; i < pixelCount; ++i)
    {
        uint8_t logical[5] = {0, 0, 0, 0, 0};
        for (uint8_t ch = 0; ch < channels; ++ch)
        {
            uint8_t bfi = 0;
            if (active.bfiMapStorage == BfiMapStorageMode::Packed) {
                bfi = readPackedBfiChannelForChannels(bfiMaps.packedBfiMap, i, ch, channels);
            } else {
                const uint8_t* m = separateBfiMapForChannel(bfiMaps, ch);
                bfi = m ? m[i] : 0;
            }
            const bool up = channelActiveOnCurrentTick(bfi);
            logical[ch] = up ? src[ch] : (flr ? flr[ch] : 0);
        }

        if (channels == 3) {
            const uint8_t map3[3] = {map[0], map[1], map[2]};
            writeMapped3(dst, logical, map3);
        } else if (channels == 4) {
            const uint8_t map4[4] = {map[0], map[1], map[2], map[3]};
            writeMapped4(dst, logical, map4);
        } else {
            const uint8_t map5[5] = {map[0], map[1], map[2], map[3], map[4]};
            writeMapped5(dst, logical, map5);
        }

        src += channels;
        if (flr) flr += channels;
        dst += channels;
    }
}

void SolverRuntime::renderIndexed(
    const uint8_t* upperFrame, const uint8_t* floorFrame,
    const BfiMapView& bfiMaps,
    uint8_t* displayBuffer, uint16_t pixelIndex,
    const RenderOptions* options) const
{
    if (!upperFrame || !displayBuffer) return;

    RenderOptions active;
    if (options) {
        active = *options;
    } else {
        active.colorOrder = m_ledColorOrder;
        active.bfiMapStorage = BfiMapStorageMode::Separate;
    }

    const uint8_t channels = channelCountForColorOrder(active.colorOrder);
    uint8_t map[5] = {0, 1, 2, 3, 4};
    if (!colorOrderMapForChannels(active.colorOrder, channels, map)) {
        for (uint8_t i = 0; i < channels; ++i) map[i] = i;
    }

    const uint32_t off = (uint32_t)pixelIndex * channels;
    const uint8_t* src = upperFrame + off;
    const uint8_t* flr = floorFrame ? floorFrame + off : nullptr;
    uint8_t* dst = displayBuffer + off;

    uint8_t logical[5] = {0, 0, 0, 0, 0};
    for (uint8_t ch = 0; ch < channels; ++ch)
    {
        uint8_t bfi = 0;
        if (active.bfiMapStorage == BfiMapStorageMode::Packed) {
            bfi = readPackedBfiChannelForChannels(bfiMaps.packedBfiMap, pixelIndex, ch, channels);
        } else {
            const uint8_t* m = separateBfiMapForChannel(bfiMaps, ch);
            bfi = m ? m[pixelIndex] : 0;
        }
        const bool up = channelActiveOnCurrentTick(bfi);
        logical[ch] = up ? src[ch] : (flr ? flr[ch] : 0);
    }

    if (channels == 3) {
        const uint8_t map3[3] = {map[0], map[1], map[2]};
        writeMapped3(dst, logical, map3);
    } else if (channels == 4) {
        const uint8_t map4[4] = {map[0], map[1], map[2], map[3]};
        writeMapped4(dst, logical, map4);
    } else {
        const uint8_t map5[5] = {map[0], map[1], map[2], map[3], map[4]};
        writeMapped5(dst, logical, map5);
    }
}

void SolverRuntime::commitPixel(
    uint8_t* upperFrame, uint8_t* floorFrame,
    BfiMapWriteView& bfiMaps,
    uint16_t pixelIndex,
    const EncodedState* channelStates,
    uint8_t stateCount,
    const RenderOptions& options)
{
    if (!upperFrame || !channelStates || stateCount == 0) return;

    uint8_t channels = channelCountForColorOrder(options.colorOrder);
    if (channels > stateCount) channels = stateCount;
    if (channels == 0) return;

    const uint32_t off = (uint32_t)pixelIndex * channels;
    for (uint8_t ch = 0; ch < channels; ++ch)
    {
        const EncodedState& state = channelStates[ch];
        upperFrame[off + ch] = state.value;
        if (floorFrame) floorFrame[off + ch] = state.lowerValue;

        if (options.bfiMapStorage == BfiMapStorageMode::Packed) {
            writePackedBfiChannelForChannels(
                bfiMaps.packedBfiMap, pixelIndex, ch, channels, state.bfi);
        } else {
            uint8_t* map = separateBfiMapForChannel(bfiMaps, ch);
            if (map) map[pixelIndex] = state.bfi;
        }
    }
}


void SolverRuntime::setPhaseMode(PhaseMode mode)
{
    m_phaseMode = mode;
}

void SolverRuntime::setCycleLength(uint8_t len)
{
    if (len < 2) len = 2;
    if (len > MAX_SUPPORTED_CYCLE_LENGTH) len = MAX_SUPPORTED_CYCLE_LENGTH;
    m_cycleLength = len;
}

bool SolverRuntime::advanceTick()
{
    ++m_tick;
    uint8_t cl;
    switch (m_phaseMode) {
        case PhaseMode::DistributedGlobal: cl = m_cycleLength; break;
        default:                           cl = SOLVER_FIXED_BFI_LEVELS; break;
    }
    return (m_tick % cl) == 0;
}

void SolverRuntime::resetTick()
{
    m_tick = 0;
}

bool SolverRuntime::channelActiveOnCurrentTick(uint8_t bfi) const
{
    if (m_phaseMode == PhaseMode::FixedMask)
        return channelOnPhase(bfi, (uint8_t)(m_tick % SOLVER_FIXED_BFI_LEVELS));
    if (m_phaseMode == PhaseMode::Distributed)
        return channelOnTickPerBfi(bfi, m_tick);
    return channelOnTickDistributedGlobal(bfi, m_tick, m_cycleLength);
}

} // namespace TemporalBFI
