"""
guard_upload.py  —  pre: extra_script

Registers an upload pre-action that aborts with a clear message when no
explicit -e / --environment flag was passed on the command line.

`pio run`                          → builds all envs freely  (guard never fires)
`pio run --target upload`          → blocked with env list
`pio run -e HyperTeensy --target upload`  → allowed
"""

Import("env")  # noqa: F821 — PlatformIO SConstruct global

import sys


def _require_explicit_env(source, target, env):
    args = sys.argv
    if "-e" not in args and "--environment" not in args:
        print()
        print("=" * 70)
        print("  ERROR: Uploads require an explicit -e <env> flag.")
        print()
        print("  Board targets are NOT interchangeable.")
        print("  Example: pio run -e HyperTeensy --target upload")
        print("           pio run -e ESP32S3_DoubleBuffer --target upload")
        print()
        print("  Available environments:")
        envs = [
            "HyperTeensy", "Calibration", "FrameworkDemo",
            "RGB16InputDemo", "ColorCalibrationABDemo", "PrecomputeDemo",
            "rgbwNoExtractionDemo", "True16RGBWGradientDemo",
            "TemporalFastLEDDemo", "PackedBFIMapDemo", "CubeLUT3DDemo",
            "LoadPrecomputedDemo", "ESP32S3_DoubleBuffer",
        ]
        for name in envs:
            print(f"    {name}")
        print("=" * 70)
        print()
        sys.exit(1)


env.AddPreAction("upload", _require_explicit_env)
