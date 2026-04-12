"""
PlatformIO extra script: override Teensy core USB descriptors.

Prepends the custom usb_desc.h / usb_desc.c directory to the include
path so it shadows the stock core versions, and adds usb_desc.c as an
extra source file.  Only active for environments that define
USB_RAWHID_SERIAL (or any other custom USB type not in the stock core).
"""
Import("env")
import os

# PROJECT_DIR is the TemporalBFI root (where platformio.ini lives).
# usb_desc.h and usb_desc.c sit directly in that directory.
usb_dir = env["PROJECT_DIR"]

# Put our custom header ahead of the core so #include "usb_desc.h" resolves here first.
env.Prepend(CPPPATH=[usb_dir])

# Compile our custom usb_desc.c alongside the sketch sources.
usb_src = os.path.join(usb_dir, "usb_desc.c")
env.BuildSources(os.path.join("$BUILD_DIR", "custom_usb"), usb_dir,
                 src_filter="+<usb_desc.c>")
