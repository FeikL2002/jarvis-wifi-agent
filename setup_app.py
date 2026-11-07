"""Optional local macOS app build: .venv/bin/python setup_app.py py2app."""
from pathlib import Path
from setuptools import setup
import py2app  # noqa: F401 -- registers the build command

ROOT = Path(__file__).resolve().parent
PURPOSE = (
    "macOS requires location permission to reveal nearby Wi-Fi names and access-point "
    "identifiers. Jarvis only displays Wi-Fi discovery results locally and does not "
    "request geographic coordinates."
)

setup(
    name="Jarvis Wi-Fi Discovery",
    version="1.0.0",
    app=[str(ROOT / "app.py")],
    options={
        "py2app": {
            "argv_emulation": False,
            "packages": ["jarvis_wifi"],
            "includes": ["CoreWLAN", "CoreLocation", "Foundation", "AppKit"],
            "resources": [str(ROOT / "static")],
            "plist": {
                "CFBundleName": "Jarvis Wi-Fi Discovery",
                "CFBundleDisplayName": "Jarvis Wi-Fi Discovery",
                "CFBundleIdentifier": "local.jarvis.wifi-discovery",
                "CFBundleShortVersionString": "1.0.0",
                "CFBundleVersion": "1",
                "LSMinimumSystemVersion": "12.0",
                "NSHighResolutionCapable": True,
                "NSLocationUsageDescription": PURPOSE,
                "NSLocationWhenInUseUsageDescription": PURPOSE,
            },
        }
    },
)
