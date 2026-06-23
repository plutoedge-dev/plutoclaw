"""
Platform detection - Mac vs Raspberry Pi
All components use this to determine the environment
"""
import platform
import os


def get_platform() -> str:
    """Detect whether running on Mac or Raspberry Pi"""
    system = platform.system()
    machine = platform.machine()

    if system == "Darwin":
        return "mac"
    elif system == "Linux" and ("aarch64" in machine or "armv" in machine):
        return "pi"
    else:
        return "linux"


def is_mac() -> bool:
    return get_platform() == "mac"


def is_pi() -> bool:
    return get_platform() == "pi"


def has_hailo() -> bool:
    """Check whether AI HAT+ Hailo is available"""
    if not is_pi():
        return False
    try:
        import hailo
        return True
    except ImportError:
        return False


def has_gpio() -> bool:
    """Check whether GPIO is available"""
    if not is_pi():
        return False
    try:
        import RPi.GPIO
        return True
    except ImportError:
        return False


def print_platform_info():
    p = get_platform()
    print(f"  Platform   : {p.upper()}")
    print(f"  OS         : {platform.system()} {platform.release()}")
    print(f"  Machine    : {platform.machine()}")
    print(f"  Hailo NPU  : {'✅ Available' if has_hailo() else '❌ Not available (using CPU)'}")
    print(f"  GPIO       : {'✅ Available' if has_gpio() else '❌ Not available (skip sensors)'}")
