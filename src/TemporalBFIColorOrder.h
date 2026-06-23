#pragma once

#include "TemporalBFI.h"

namespace TemporalBFI {
namespace ColorOrderDetail {

/// Build a 3-channel logical-to-physical map for a LedColorOrder preset.
bool mapFor3(LedColorOrder order, uint8_t (&map)[3]);
/// Build a 4-channel logical-to-physical map for a LedColorOrder preset.
bool mapFor4(LedColorOrder order, uint8_t (&map)[4]);
/// Build a 5-channel logical-to-physical map for a LedColorOrder preset.
bool mapFor5(LedColorOrder order, uint8_t (&map)[5]);

/// Return the channel count implied by a LedColorOrder preset.
uint8_t channelCount(LedColorOrder order);
/// Validate that a custom channel map is a permutation for the channel count.
bool validateCustomMap(const uint8_t* map, uint8_t channels);
/// Build a logical-to-physical map for an arbitrary supported channel count.
bool mapForChannels(LedColorOrder order, uint8_t channels, uint8_t* outMap);

} // namespace ColorOrderDetail
} // namespace TemporalBFI
