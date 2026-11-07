# Jarvis Wi-Fi Discovery

A macOS network-discovery project by **Lewis Joseph Feik / AmericanSites**. Published as a sanitized source snapshot; no live network identifiers or credentials are included.

A local Python dashboard for discovering nearby Wi-Fi access points on an Apple Silicon Mac. It uses Apple's public **CoreWLAN** API through PyObjC. It displays the SSID, BSSID, received signal, noise, channel, band, width, and advertised security modes **only when macOS exposes them**.

The agent does not join networks, try passwords, inspect saved passwords, read Keychain credentials, change Wi-Fi settings, or capture packets. CoreWLAN discovery is a broadcast scan and **may transmit Wi-Fi probe requests**; this is not a strictly passive radio monitor. The Mac's own Wi-Fi auto-join behavior remains controlled by macOS.

## Start on this Mac

Clone this repository or extract a source ZIP first. Open the extracted `jarvis_wifi_agent` folder and double-click **Launch Jarvis.command**. The launcher creates a `.venv` in that folder when needed, installs the two pinned macOS framework bridges, and opens the local dashboard. It requires a native Apple Silicon Python 3.11 or newer on your PATH; Python 3.12 was used for validation. The first dependency installation needs internet access. Subsequent starts reuse the environment.

Keep the launcher's Terminal window open. Press **Control-C** in that window, or choose **Stop agent** at the bottom of the dashboard, to stop it. Closing a browser tab alone does not stop the agent. The dashboard normally opens at **http://127.0.0.1:8765**. If that port is occupied, choose a different one with `--port`.

If Finder blocks a downloaded launcher, review the files and use the manual Terminal instructions below. Do not disable Gatekeeper or other macOS security settings. Running the launcher does not install a login item or background service.

## Requirements

- Apple Silicon Mac running macOS 12 or newer, with a supported Wi-Fi interface.
- Native `arm64` Python 3.11 or newer. Python 3.12 is the tested version. Check with `python3 -c 'import platform, sys; print(sys.version); print(platform.machine())'`.
- PyObjC CoreWLAN, CoreLocation, Cocoa and the core bridge, all pinned to the validated version 13.0 in `requirements.txt`.
- A browser for the dashboard. All dashboard assets are included locally; no CDN, API key, cloud account, or hosted service is required.
- macOS Location Services and app authorization may be needed for names and access-point identifiers. Signing and packaging restrictions are explained below.

Python itself is not included in the ZIP. If you need it, obtain a current universal2 macOS installer from the [official Python downloads](https://www.python.org/downloads/macos/) and run Python natively on Apple Silicon. PyObjC's [supported-platform notes](https://pyobjc.readthedocs.io/en/latest/supported-platforms.html) describe arm64 support and supported Python versions.

## Manual setup and commands

In Terminal, replace `/path/to/jarvis_wifi_agent` with the actual extracted folder. Quoting the path handles spaces. You can also type `cd ` and drag the folder into Terminal.

```sh
cd "/path/to/jarvis_wifi_agent"
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Use another installed native Python 3.11+ command instead of `python3.12` if needed. Do not use `sudo`.

```sh
# Check environment and available permission information, without scanning.
.venv/bin/python app.py --diagnose

# Print one live scan as JSON, then exit; does not open a browser.
.venv/bin/python app.py --scan

# Run the dashboard without opening a browser automatically.
.venv/bin/python app.py --no-browser --port 8765

# Choose an interface explicitly if this Mac has more than one.
.venv/bin/python app.py --interface en0

# Use clearly labeled synthetic examples, with no Wi-Fi scan.
.venv/bin/python app.py --demo

# Save a scan intentionally. This file contains nearby network information.
.venv/bin/python app.py --scan > my-scan.json

# Run the automated validation suite.
.venv/bin/python -m unittest discover -s tests -v
```

If you move the project and its existing `.venv` no longer works, create a fresh virtual environment using the steps above. The virtual environment is deliberately excluded from the ZIP.

## macOS permissions and missing network names

Wi-Fi identifiers can reveal location, so macOS protects them. An unavailable SSID is **not proof of a hidden network**: it may be redacted by macOS, unavailable, or not decodable as a string. Missing values remain unknown. The dashboard never fabricates a live name, BSSID, channel, or security mode.

Apple's CoreWLAN headers state that BSSID information requires Location Services to be enabled and the calling app to be authorized. Modern macOS can also redact SSIDs. Current [PyObjC CoreWLAN notes](https://pyobjc.readthedocs.io/en/latest/apinotes/CoreWLAN.html) say privacy-relevant data requires a properly signed binary, excluding an ad-hoc signature. Apple DTS explains the need to [package CoreLocation clients as an app with an Info.plist usage string](https://developer.apple.com/forums/thread/710812).

Consequently, a bare Python process, an unsigned app, or an ad-hoc signed app **may scan successfully while still receiving redacted SSIDs/BSSIDs**. A Location Services toggle alone is not a guarantee. Running as administrator does not solve this privacy requirement.

Review **System Settings → Privacy & Security → Location Services**. Enable the system service if you want to permit access and authorize the actual app that requests it. The agent can report permission status, but it does not modify privacy settings. A signed application can show the standard macOS permission request; the final decision belongs to you. The code does not start coordinate updates or request latitude/longitude.

The optional app build includes `NSLocationUsageDescription` and `NSLocationWhenInUseUsageDescription`. Apple documents [requesting authorization](https://developer.apple.com/documentation/corelocation/requesting-authorization-to-use-location-services) and the [macOS usage-description key](https://developer.apple.com/documentation/bundleresources/information-property-list/nslocationwheninuseusagedescription). macOS permission handling and redaction can change between OS releases.

## Optional local Mac app

Double-click **Build Mac App.command**, or run:

```sh
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python setup_app.py py2app
```

This creates `dist/Jarvis Wi-Fi Discovery.app` with the local web assets. Launch the app from Finder. Its dashboard opens in your browser. The app build is optional; the command-line dashboard works without it.

This project does **not** include an Apple Developer certificate, Developer ID signature, or notarization. Building the app does not supply them, and py2app's automatic ad-hoc signing is insufficient to promise access to protected Wi-Fi identifiers. The locally built app did receive identifiers on the validated Mac after requesting authorization; see VALIDATION.md. That observation does not establish portability to another Mac or macOS release. If you need dependable identifier access or plan to distribute the app, use your own valid signing identity, sign the app and nested code correctly, and validate the resulting bundle on the target macOS release. See [PyObjC code signing and notarizing](https://pyobjc.readthedocs.io/en/latest/notes/codesigning.html) for PyObjC's hardened-runtime requirements. No signing credentials are requested or stored by this project.

## Reading the dashboard

- **Signal:** RSSI is in dBm; values closer to zero indicate a stronger received signal. The quality labels are illustrative heuristics, not calibrated performance measurements. Walls, antenna orientation, interference, and time can change readings.
- **Noise and SNR:** Noise is shown where exposed. SNR is RSSI minus noise when both values are usable; unavailable/invalid readings remain unknown.
- **Channels:** Channel, band, and width come from the reported `CWChannel`. Band matters: the same channel number in different bands is not the same radio frequency. Counts summarize visible scan records, not utilization or airtime. A busy-looking channel count alone cannot establish congestion or select an optimal channel.
- **Security:** Labels describe advertised security types reported by `CWNetwork.supportsSecurity_()`. Multiple modes can be advertised. They do not establish a network's ownership, trustworthiness, password strength, or end-to-end safety. Unknown security stays unknown.
- **Nearby records:** One SSID may appear on several access points or bands. A scan record is not necessarily a unique router or a unique household. Redacted records are not collapsed into a single alleged device.
- **Demo:** Synthetic data is explicitly labeled. Demo mode validates the interface without making a live scan or claiming to represent this location.

Signal labels use these illustrative RSSI thresholds: excellent at −50 dBm or above, good from −67 to below −50, fair from −75 to below −67, and weak below −75. Signal percentage is `2 × (RSSI + 100)`, clipped to 0–100. A missing reading or the 0/−127 sentinel remains unknown. Refresh scans have a 10-second server cooldown; repeated browser refreshes do not imply continuous radio monitoring. CoreWLAN scanning can take several seconds.

The scanner queries concrete security types only. Mixed, transition and aggregate enum queries can report compatibility with more than one protocol (a WPA2-only access point may match a WPA/WPA2 or WPA3-transition query). Such matches are not treated as proof of a legacy protocol or WPA3 support. Legacy flags require a concrete WEP, Dynamic WEP or WPA response. These are discovery observations, not an audit of router settings.

## Privacy and local operation

The dashboard server binds to **127.0.0.1 only**, so it is accessible on this Mac. It provides no public hosting or remote sharing option. The app keeps current scan results in memory; it has no database, automatic export, telemetry, or external analytics. Redirecting CLI output to a file is an explicit local export. Browser pages and Terminal output can still reveal nearby SSIDs/BSSIDs, so review them before sharing screenshots or JSON.

CoreWLAN discovery does not contact nearby devices at the IP layer. No join, authentication, password retrieval, network configuration, or packet-capture workflow is provided. For exact API semantics see Apple's [scanForNetworks(withName:) documentation](https://developer.apple.com/documentation/corewlan/cwinterface/scanfornetworks%28withname%3A%29?language=objc).

## Troubleshooting

- **Python not found:** Install native Python 3.11+ and reopen Terminal. The launcher searches common `python3.x` commands and checks that the selected interpreter runs as `arm64`.
- **Wi-Fi is off or no interface:** Enable Wi-Fi yourself in System Settings. Jarvis reports the condition and does not change interface power.
- **Scan denied or empty:** Read the displayed error and run `--diagnose`. Check Location Services and app identity. An empty scan is not evidence that no networks physically exist.
- **Names unavailable but signal/channel visible:** Read the permission/signing section. This is a partial result, not a successful validation of SSID access.
- **Port already in use:** Run `app.py --port 8766` and use the URL printed at startup. Do not stop unrelated services.
- **Build complains about pkg_resources:** Use `requirements-build.txt`, which retains a compatible setuptools release for the pinned py2app build chain.

## Validation and provenance

The earlier `jarvis_wifi_agent.zip` was not found in the inspected Codex workspace, Downloads, or Desktop locations. This is a fresh implementation, not a claimed improvement of an unavailable archive. No existing installed Jarvis application is modified.

Read **VALIDATION.md** for the actual automated checks, live macOS observations, and any remaining permission or physical-device limitations for this build. Demo validation and mocked API tests are not evidence that macOS disclosed live SSIDs. This source snapshot excludes virtual environments, machine-specific state, build caches, and live scan exports.

## Source license status

No open-source license has been selected for this source snapshot. Python, PyObjC and build dependencies retain their own licenses.
