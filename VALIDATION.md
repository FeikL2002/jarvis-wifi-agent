# Validation record — November 5, 2026

This record distinguishes hardware observations from synthetic fixtures and automated tests. All observations below were made on the target Mac during this build.

## Validated environment

- Apple Silicon `arm64`, macOS 26.6.2.
- Native Python 3.12.15.
- PyObjC core, Cocoa, CoreWLAN and CoreLocation 13.0.
- py2app 0.28.10; setuptools 80.10.2 for the optional Mac app build.

## Automated checks

`python -m unittest discover -s tests -v`: **28 tests passed**, approximately 0.55 seconds.

Coverage includes public CoreWLAN selectors and named constants; concrete security modes versus mixed/transition compatibility queries; unknown versus open security; optional, redacted and invalid measurements; separate scan records and shared SSIDs; empty, failed and partial scans; Wi-Fi power-off handling without changing power; explicit user-triggered discovery; busy/cooldown controls; retained previous results after a failed scan; demo isolation; no coordinate access; loopback binding; host/origin/session-token checks; rejection of request bodies, credential routes and path traversal; and authenticated shutdown.

JavaScript passed `node --check static/dashboard.js`. Both launcher scripts passed `zsh -n`.

## Live CoreWLAN observations

1. The command-line scan successfully used the default `en0` interface and returned actual nearby radio records, including RSSI, noise, channel, band, width and security support. The initial CLI process had undetermined location authorization, and SSIDs/BSSIDs were unavailable. This validated the partial-data state rather than identifier access.
2. The optional standalone Mac app built and launched through Finder/Launch Services. The app's diagnostics correctly detected its location-purpose strings and enabled permission requests.
3. The dashboard's explicit permission action ran through CoreLocation on the main thread. App authorization subsequently reported **authorized** with Location Services enabled.
4. A live app scan completed at **8:47:59 PM Eastern** in approximately **3.8 seconds**. CoreWLAN exposed **7 access-point records and 5 distinct SSIDs**, including BSSIDs, RSSI, noise/SNR, channel, band, width and concrete WPA2/WPA3 support. All 7 records in that snapshot matched modern security support. These labels do not establish network trust, password strength, or a security audit result.
5. A later refresh returned 4 access points with 4 distinct names. Counts and signals vary with time and radio conditions; a scan is not an inventory of every physically present network.

The live results are not embedded in the distributable source ZIP. Nearby names and addresses were not used as demo fixtures.

## Browser and app verification

- Opened and visually checked the real local dashboard and clearly marked demo mode.
- Exercised scan initiation, results rendering, search, band filtering and sorting.
- Checked a desktop viewport and a 390 × 844 narrow viewport. The network table supports horizontal scrolling on narrow screens.
- Browser console reported no errors or warnings during the checked flow.
- Used **Stop agent** and confirmed the local server stopped accepting connections; relaunched the Mac app successfully.
- Verified the standalone arm64 app bundle using `codesign --verify --deep --strict`.

The app carries a local **ad-hoc** signature, with no Developer ID identity or notarization. Identifier access succeeded on this particular Mac after authorization. Current PyObjC documentation states stricter signing requirements for privacy-sensitive data; this local success must not be generalized to other machines or future macOS releases. See the primary-source links and permission guidance in README.md.

## Scope and remaining limits

The agent makes only public CoreWLAN broadcast discovery requests. A broadcast scan may send probe requests; it is not a strictly passive radio capture. Source review and API tests found no network-association, credential, Keychain, Wi-Fi configuration, packet-capture or geographic-coordinate workflow. The Mac's own independent auto-join behavior remains controlled by macOS.

Security analysis reports concrete protocol support exposed by CoreWLAN. Mixed/transition enums were excluded after live testing showed that a WPA2-only record could also satisfy these compatibility queries. Unknown fields remain unknown.

No live WEP, open, OWE, 6 GHz or Wi-Fi-off condition was deliberately created. Those paths were exercised with fixtures or mock APIs only. Device counts on a network, router login, network traffic analysis and connection to a selected network are outside this discovery agent. An access-point count is not a connected-device count.

## Earlier package search

The referenced chat contained a historical `sandbox:/mnt/data/jarvis_wifi_agent.zip` link, but no accessible attachment was returned. A filename search in the inspected Documents/Codex, Downloads, Desktop and temporary locations found no prior package. This deliverable is a fresh implementation.
