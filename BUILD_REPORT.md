# TemporalBFI Build Report

**14/14** environments built successfully.

## Teensy (IMXRT1062)

| Environment | Status | Flash | Flash Free | RAM1 | RAM1 Free | RAM2 | RAM2 Free |
|-------------|--------|-------|------------|------|-----------|------|-----------|
| HyperTeensy | SUCCESS | 1565.0 KB | 419.0 KB | 272.4 KB | 228.5 KB | 434.1 KB | 77.9 KB |
| Calibration | SUCCESS | 1010.0 KB | 974.0 KB | 224.2 KB | 276.5 KB | 412.2 KB | 99.8 KB |
| FrameworkDemo | SUCCESS | 84.0 KB | 1900.0 KB | 14.2 KB | 476.2 KB | 12.1 KB | 499.9 KB |
| RGB16InputDemo | SUCCESS | 108.0 KB | 1876.0 KB | 66.3 KB | 427.6 KB | 12.1 KB | 499.9 KB |
| ColorCalibrationABDemo | SUCCESS | 140.0 KB | 1844.0 KB | 98.3 KB | 395.6 KB | 12.1 KB | 499.9 KB |
| PrecomputeDemo | SUCCESS | 106.0 KB | 1878.0 KB | 96.6 KB | 395.9 KB | 12.1 KB | 499.9 KB |
| rgbwNoExtractionDemo | SUCCESS | 108.0 KB | 1876.0 KB | 66.4 KB | 427.6 KB | 12.1 KB | 499.9 KB |
| True16RGBWGradientDemo | SUCCESS | 109.0 KB | 1875.0 KB | 79.5 KB | 415.4 KB | 12.1 KB | 499.9 KB |
| TemporalFastLEDDemo | SUCCESS | 127.0 KB | 1857.0 KB | 87.7 KB | 392.6 KB | 17.2 KB | 494.8 KB |
| RGBW_Analytical_FastLED | SUCCESS | 1043.0 KB | 941.0 KB | 258.7 KB | 242.2 KB | 421.2 KB | 90.8 KB |
| PackedBFIMapDemo | SUCCESS | 139.0 KB | 1845.0 KB | 97.9 KB | 393.2 KB | 12.1 KB | 499.9 KB |
| CubeLUT3DDemo | SUCCESS | 166.0 KB | 7770.0 KB | 126.1 KB | 358.2 KB | 12.1 KB | 499.9 KB |
| LoadPrecomputedDemo | SUCCESS | 74.0 KB | 1910.0 KB | 64.2 KB | 427.2 KB | 12.1 KB | 499.9 KB |

## ESP32

| Environment | Status | Flash Code | Flash Data | Flash Used | Flash Free | RAM (DIRAM) | DIRAM Free | IRAM | IRAM Free | Image |
|-------------|--------|------------|------------|------------|------------|-------------|------------|------|-----------|-------|
| ESP32S3_DoubleBuffer | SUCCESS | 186.0 KB | 208.7 KB | 394.8 KB | 7797.2 KB | 93.7 KB | 240.1 KB | - | - | 479.1 KB |

Target: **Teensy 4.0 (IMXRT1062) — 1984 KB Flash, 512 KB RAM1, 512 KB RAM2**<br>Environments: HyperTeensy, Calibration, FrameworkDemo, RGB16InputDemo, ColorCalibrationABDemo, PrecomputeDemo, rgbwNoExtractionDemo, True16RGBWGradientDemo, TemporalFastLEDDemo, RGBW_Analytical_FastLED, PackedBFIMapDemo, LoadPrecomputedDemo

Target: **Teensy 4.1 (IMXRT1062) — 7936 KB Flash, 512 KB RAM1, 512 KB RAM2, PSRAM + QSPI pads**<br>Environments: CubeLUT3DDemo

Target: **ESP32-S3 DevKitC-1 — 8 MB Flash, 512 KB SRAM, PSRAM**<br>Environments: ESP32S3_DoubleBuffer

