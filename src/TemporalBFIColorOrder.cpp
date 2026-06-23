#include "TemporalBFIColorOrder.h"

namespace TemporalBFI {
namespace ColorOrderDetail {

bool mapFor3(LedColorOrder order, uint8_t (&map)[3])
{
    switch (order)
    {
        case LedColorOrder::GRB: map[0] = 0; map[1] = 1; map[2] = 2; return true;
        case LedColorOrder::RGB: map[0] = 1; map[1] = 0; map[2] = 2; return true;
        case LedColorOrder::BRG: map[0] = 2; map[1] = 1; map[2] = 0; return true;
        case LedColorOrder::BGR: map[0] = 2; map[1] = 0; map[2] = 1; return true;
        case LedColorOrder::RBG: map[0] = 1; map[1] = 2; map[2] = 0; return true;
        case LedColorOrder::GBR: map[0] = 0; map[1] = 2; map[2] = 1; return true;
        default: return false;
    }
}

bool mapFor4(LedColorOrder order, uint8_t (&map)[4])
{
    switch (order)
    {
        case LedColorOrder::GRBW: map[0] = 0; map[1] = 1; map[2] = 2; map[3] = 3; return true;
        case LedColorOrder::GRWB: map[0] = 0; map[1] = 1; map[2] = 3; map[3] = 2; return true;
        case LedColorOrder::GBRW: map[0] = 0; map[1] = 2; map[2] = 1; map[3] = 3; return true;
        case LedColorOrder::GBWR: map[0] = 0; map[1] = 2; map[2] = 3; map[3] = 1; return true;
        case LedColorOrder::GWRB: map[0] = 0; map[1] = 3; map[2] = 1; map[3] = 2; return true;
        case LedColorOrder::GWBR: map[0] = 0; map[1] = 3; map[2] = 2; map[3] = 1; return true;
        case LedColorOrder::RGBW: map[0] = 1; map[1] = 0; map[2] = 2; map[3] = 3; return true;
        case LedColorOrder::RGWB: map[0] = 1; map[1] = 0; map[2] = 3; map[3] = 2; return true;
        case LedColorOrder::RBGW: map[0] = 1; map[1] = 2; map[2] = 0; map[3] = 3; return true;
        case LedColorOrder::RBWG: map[0] = 1; map[1] = 2; map[2] = 3; map[3] = 0; return true;
        case LedColorOrder::RWGB: map[0] = 1; map[1] = 3; map[2] = 0; map[3] = 2; return true;
        case LedColorOrder::RWBG: map[0] = 1; map[1] = 3; map[2] = 2; map[3] = 0; return true;
        case LedColorOrder::BGRW: map[0] = 2; map[1] = 0; map[2] = 1; map[3] = 3; return true;
        case LedColorOrder::BGWR: map[0] = 2; map[1] = 0; map[2] = 3; map[3] = 1; return true;
        case LedColorOrder::BRGW: map[0] = 2; map[1] = 1; map[2] = 0; map[3] = 3; return true;
        case LedColorOrder::BRWG: map[0] = 2; map[1] = 1; map[2] = 3; map[3] = 0; return true;
        case LedColorOrder::BWGR: map[0] = 2; map[1] = 3; map[2] = 0; map[3] = 1; return true;
        case LedColorOrder::BWRG: map[0] = 2; map[1] = 3; map[2] = 1; map[3] = 0; return true;
        case LedColorOrder::WRGB: map[0] = 3; map[1] = 1; map[2] = 0; map[3] = 2; return true;
        case LedColorOrder::WRBG: map[0] = 3; map[1] = 1; map[2] = 2; map[3] = 0; return true;
        case LedColorOrder::WGRB: map[0] = 3; map[1] = 0; map[2] = 1; map[3] = 2; return true;
        case LedColorOrder::WGBR: map[0] = 3; map[1] = 0; map[2] = 2; map[3] = 1; return true;
        case LedColorOrder::WBRG: map[0] = 3; map[1] = 2; map[2] = 1; map[3] = 0; return true;
        case LedColorOrder::WBGR: map[0] = 3; map[1] = 2; map[2] = 0; map[3] = 1; return true;
        default: return false;
    }
}

bool mapFor5(LedColorOrder order, uint8_t (&map)[5])
{
    switch (order)
    {
        case LedColorOrder::GRBW1W2: map[0] = 0; map[1] = 1; map[2] = 2; map[3] = 3; map[4] = 4; return true;
        case LedColorOrder::GRBW2W1: map[0] = 0; map[1] = 1; map[2] = 2; map[3] = 4; map[4] = 3; return true;
        case LedColorOrder::RGBW1W2: map[0] = 1; map[1] = 0; map[2] = 2; map[3] = 3; map[4] = 4; return true;
        case LedColorOrder::RGBW2W1: map[0] = 1; map[1] = 0; map[2] = 2; map[3] = 4; map[4] = 3; return true;
        case LedColorOrder::W1W2RGB: map[0] = 3; map[1] = 4; map[2] = 1; map[3] = 0; map[4] = 2; return true;
        case LedColorOrder::W2W1RGB: map[0] = 4; map[1] = 3; map[2] = 1; map[3] = 0; map[4] = 2; return true;
        case LedColorOrder::W1RGBW2: map[0] = 3; map[1] = 1; map[2] = 0; map[3] = 2; map[4] = 4; return true;
        case LedColorOrder::W2RGBW1: map[0] = 4; map[1] = 1; map[2] = 0; map[3] = 2; map[4] = 3; return true;
        case LedColorOrder::W1GRBW2: map[0] = 3; map[1] = 0; map[2] = 1; map[3] = 2; map[4] = 4; return true;
        case LedColorOrder::W2GRBW1: map[0] = 4; map[1] = 0; map[2] = 1; map[3] = 2; map[4] = 3; return true;
        default: return false;
    }
}

uint8_t channelCount(LedColorOrder order)
{
    uint8_t map5[5];
    if (mapFor5(order, map5)) return 5;

    uint8_t map4[4];
    if (mapFor4(order, map4)) return 4;

    uint8_t map3[3];
    if (mapFor3(order, map3)) return 3;

    // Conservative fallback matches current runtime default.
    return 4;
}

bool validateCustomMap(const uint8_t* map, uint8_t channels)
{
    if (!map || channels == 0 || channels > 8) return false;

    uint8_t seenMask = 0;
    for (uint8_t i = 0; i < channels; ++i)
    {
        const uint8_t value = map[i];
        if (value >= channels) return false;

        const uint8_t bit = (uint8_t)(1u << value);
        if (seenMask & bit) return false;
        seenMask = (uint8_t)(seenMask | bit);
    }
    return true;
}

bool mapForChannels(LedColorOrder order, uint8_t channels, uint8_t* outMap)
{
    if (!outMap) return false;
    if (channels == 3) {
        uint8_t map3[3];
        if (!mapFor3(order, map3)) return false;
        outMap[0] = map3[0];
        outMap[1] = map3[1];
        outMap[2] = map3[2];
        return true;
    }
    if (channels == 4) {
        uint8_t map4[4];
        if (!mapFor4(order, map4)) return false;
        outMap[0] = map4[0];
        outMap[1] = map4[1];
        outMap[2] = map4[2];
        outMap[3] = map4[3];
        return true;
    }
    if (channels == 5) {
        uint8_t map5[5];
        if (!mapFor5(order, map5)) return false;
        outMap[0] = map5[0];
        outMap[1] = map5[1];
        outMap[2] = map5[2];
        outMap[3] = map5[3];
        outMap[4] = map5[4];
        return true;
    }
    return false;
}

} // namespace ColorOrderDetail

bool SolverRuntime::colorOrderMapFor3(LedColorOrder order, uint8_t (&map)[3])
{
    return ColorOrderDetail::mapFor3(order, map);
}

bool SolverRuntime::colorOrderMapFor4(LedColorOrder order, uint8_t (&map)[4])
{
    return ColorOrderDetail::mapFor4(order, map);
}

bool SolverRuntime::colorOrderMapFor5(LedColorOrder order, uint8_t (&map)[5])
{
    return ColorOrderDetail::mapFor5(order, map);
}

uint8_t SolverRuntime::channelCountForColorOrder(LedColorOrder order)
{
    return ColorOrderDetail::channelCount(order);
}

uint8_t SolverRuntime::activeRenderChannelCount() const
{
    return channelCountForColorOrder(m_ledColorOrder);
}

bool SolverRuntime::validateCustomMap(const uint8_t* map, uint8_t channels)
{
    return ColorOrderDetail::validateCustomMap(map, channels);
}

bool SolverRuntime::colorOrderMapForChannels(LedColorOrder order, uint8_t channels,
                                             uint8_t* outMap)
{
    return ColorOrderDetail::mapForChannels(order, channels, outMap);
}

void SolverRuntime::setLedColorOrder(LedColorOrder order)
{
    m_ledColorOrder = order;

    if (!colorOrderMapFor3(order, m_colorOrderMap3)) {
        m_colorOrderMap3[0] = 0;
        m_colorOrderMap3[1] = 1;
        m_colorOrderMap3[2] = 2;
    }

    if (!colorOrderMapFor4(order, m_colorOrderMap4)) {
        m_colorOrderMap4[0] = 0;
        m_colorOrderMap4[1] = 1;
        m_colorOrderMap4[2] = 2;
        m_colorOrderMap4[3] = 3;
    }

    if (!colorOrderMapFor5(order, m_colorOrderMap5)) {
        m_colorOrderMap5[0] = 0;
        m_colorOrderMap5[1] = 1;
        m_colorOrderMap5[2] = 2;
        m_colorOrderMap5[3] = 3;
        m_colorOrderMap5[4] = 4;
    }
}

bool SolverRuntime::setCustomColorOrderMap3(const uint8_t map[3])
{
    if (!validateCustomMap(map, 3)) return false;
    m_colorOrderMap3[0] = map[0];
    m_colorOrderMap3[1] = map[1];
    m_colorOrderMap3[2] = map[2];
    return true;
}

bool SolverRuntime::setCustomColorOrderMap4(const uint8_t map[4])
{
    if (!validateCustomMap(map, 4)) return false;
    m_colorOrderMap4[0] = map[0];
    m_colorOrderMap4[1] = map[1];
    m_colorOrderMap4[2] = map[2];
    m_colorOrderMap4[3] = map[3];
    return true;
}

bool SolverRuntime::setCustomColorOrderMap5(const uint8_t map[5])
{
    if (!validateCustomMap(map, 5)) return false;
    m_colorOrderMap5[0] = map[0];
    m_colorOrderMap5[1] = map[1];
    m_colorOrderMap5[2] = map[2];
    m_colorOrderMap5[3] = map[3];
    m_colorOrderMap5[4] = map[4];
    return true;
}

} // namespace TemporalBFI
