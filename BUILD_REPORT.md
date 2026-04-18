# TemporalBFI Build Report

**13/13** environments built successfully.

## Teensy (IMXRT1062)

| Environment | Status | Flash | Flash Free | RAM1 | RAM1 Free | RAM2 | RAM2 Free |
|-------------|--------|-------|------------|------|-----------|------|-----------|
| HyperTeensy | SUCCESS | 1563.0 KB | 421.0 KB | 270.1 KB | 228.5 KB | 434.1 KB | 77.9 KB |
| Calibration | SUCCESS | 1009.0 KB | 975.0 KB | 223.3 KB | 276.5 KB | 412.2 KB | 99.8 KB |
| FrameworkDemo | SUCCESS | 84.0 KB | 1900.0 KB | 14.1 KB | 476.2 KB | 12.1 KB | 499.9 KB |
| RGB16InputDemo | SUCCESS | 106.0 KB | 1878.0 KB | 64.6 KB | 427.2 KB | 12.1 KB | 499.9 KB |
| ColorCalibrationABDemo | SUCCESS | 138.0 KB | 1846.0 KB | 96.4 KB | 395.2 KB | 12.1 KB | 499.9 KB |
| PrecomputeDemo | SUCCESS | 105.0 KB | 1879.0 KB | 95.1 KB | 395.5 KB | 12.1 KB | 499.9 KB |
| rgbwNoExtractionDemo | SUCCESS | 106.0 KB | 1878.0 KB | 64.6 KB | 427.2 KB | 12.1 KB | 499.9 KB |
| True16RGBWGradientDemo | SUCCESS | 106.0 KB | 1878.0 KB | 65.4 KB | 427.0 KB | 12.1 KB | 499.9 KB |
| TemporalFastLEDDemo | SUCCESS | 127.0 KB | 1857.0 KB | 86.8 KB | 424.6 KB | 17.2 KB | 494.8 KB |
| PackedBFIMapDemo | SUCCESS | 133.0 KB | 1851.0 KB | 92.5 KB | 392.8 KB | 12.1 KB | 499.9 KB |
| CubeLUT3DDemo | SUCCESS | 160.0 KB | 7776.0 KB | 120.3 KB | 389.9 KB | 12.1 KB | 499.9 KB |
| LoadPrecomputedDemo | SUCCESS | 73.0 KB | 1911.0 KB | 62.9 KB | 426.8 KB | 12.1 KB | 499.9 KB |

## ESP32

| Environment | Status | Flash Code | Flash Data | Flash Used | Flash Free | RAM (DIRAM) | DIRAM Free | IRAM | IRAM Free | Image |
|-------------|--------|------------|------------|------------|------------|-------------|------------|------|-----------|-------|
| ESP32S3_DoubleBuffer | SUCCESS | 183.5 KB | 208.2 KB | 391.7 KB | 7800.3 KB | 93.6 KB | 240.2 KB | - | - | 476.1 KB |

Target: **Teensy 4.0 (IMXRT1062) — 1984 KB Flash, 512 KB RAM1, 512 KB RAM2**<br>Environments: HyperTeensy, Calibration, FrameworkDemo, RGB16InputDemo, ColorCalibrationABDemo, PrecomputeDemo, rgbwNoExtractionDemo, True16RGBWGradientDemo, TemporalFastLEDDemo, PackedBFIMapDemo, LoadPrecomputedDemo

Target: **Teensy 4.1 (IMXRT1062) — 7936 KB Flash, 512 KB RAM1, 512 KB RAM2, PSRAM + QSPI pads**<br>Environments: CubeLUT3DDemo

Target: **ESP32-S3 DevKitC-1 — 8 MB Flash, 512 KB SRAM, PSRAM**<br>Environments: ESP32S3_DoubleBuffer

