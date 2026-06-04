"""
guard_upload.py  —  pre: extra_script

Registers an upload pre-action that aborts with a clear message when no
explicit single environment can be identified.

`pio run`                          → builds all envs freely  (guard never fires)
`pio run --target upload`          → blocked with env list
`pio run -e HyperTeensy --target upload`  → allowed
"""

Import("env")  # noqa: F821 — PlatformIO SConstruct global

import sys
from pathlib import PureWindowsPath

try:
    from SCons.Script import ARGUMENTS
except Exception:
    ARGUMENTS = {}


def _selected_envs_from_scons():
    raw = str(ARGUMENTS.get("PIOENV", ARGUMENTS.get("PIOENVS", "")) or "")
    return {part.strip() for part in raw.replace(";", ",").split(",") if part.strip()}


def _has_explicit_env_arg(args, selected_env):
    selected_envs = _selected_envs_from_scons()
    if selected_env and selected_env in selected_envs:
        return True

    for arg in args:
        if arg in ("-e", "--environment"):
            return True
        if arg.startswith("--environment=") or arg.startswith("-e="):
            return True
        if selected_env and arg == selected_env:
            return True
    return False


def _target_envs(target):
    envs = set()
    for node in target:
        parts = PureWindowsPath(str(node)).parts
        for index, part in enumerate(parts[:-1]):
            if part == "build" and index > 0 and parts[index - 1] == ".pio":
                envs.add(parts[index + 1])
    return envs


def _require_explicit_env(source, target, env):
    args = sys.argv
    selected_env = env.get("PIOENV", "")
    target_envs = _target_envs(target) | _target_envs(source)
    has_single_selected_target = selected_env and target_envs == {selected_env}
    if not (_has_explicit_env_arg(args, selected_env) or has_single_selected_target):
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
            "TemporalFastLEDDemo", "RGBW_Analytical_FastLED",
            "PackedBFIMapDemo", "CubeLUT3DDemo", "LoadPrecomputedDemo",
            "ESP32S3_DoubleBuffer",
        ]
        for name in envs:
            print(f"    {name}")
        print("=" * 70)
        print()
        sys.exit(1)


env.AddPreAction("upload", _require_explicit_env)
