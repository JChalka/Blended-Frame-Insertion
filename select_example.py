"""
PlatformIO extra script: route each environment to its example folder.

Maps env names to subdirectories under examples/.  If the env name
matches a folder directly, no explicit entry is needed in the map.
"""
Import("env")
import os

# Only environments whose folder name differs from the env name need an entry.
_ENV_TO_FOLDER = {
    "HyperTeensy": "HyperTeensy_Temporal_Blend",
    "Calibration": "Teensy_Temporal_Calibration",
}

folder = _ENV_TO_FOLDER.get(env["PIOENV"], env["PIOENV"])
env["PROJECT_SRC_DIR"] = os.path.join(env["PROJECT_DIR"], "examples", folder, "src")
