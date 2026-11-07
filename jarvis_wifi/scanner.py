"""Public CoreWLAN discovery API and deterministic, local analysis."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import platform
import time
import uuid


class ScanError(Exception):
    def __init__(self, code, message, remediation):
        super().__init__(message)
        self.code, self.message, self.remediation = code, message, remediation

    def as_dict(self):
        return {"code": self.code, "message": self.message, "remediation": self.remediation}


SECURITY_TYPES = (
    ("kCWSecurityNone", "Open"),
    ("kCWSecurityWEP", "WEP"),
    ("kCWSecurityDynamicWEP", "Dynamic WEP"),
    ("kCWSecurityWPAPersonal", "WPA Personal"),
    ("kCWSecurityWPA2Personal", "WPA2 Personal"),
    ("kCWSecurityWPAEnterprise", "WPA Enterprise"),
    ("kCWSecurityWPA2Enterprise", "WPA2 Enterprise"),
    ("kCWSecurityWPA3Personal", "WPA3 Personal"),
    ("kCWSecurityWPA3Enterprise", "WPA3 Enterprise"),
    ("kCWSecurityOWE", "OWE"),
)
# Mixed/transition/aggregate enum queries match compatibility unions on macOS.
# A WPA2-only AP may return True for WPAPersonalMixed and WPA3Transition.
# Query only concrete protocols; never infer a legacy protocol from a union.
LEGACY = {"WEP", "Dynamic WEP", "WPA Personal", "WPA Enterprise"}


def read_method(obj, name):
    """Missing or restricted optional fields stay unknown, never fabricated."""
    try:
        return getattr(obj, name)()
    except Exception:
        return None


def dbm(value):
    try:
        number = int(value)
        return number if -126 <= number < 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def positive_int(value):
    try:
        number = int(value)
        return number if number > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def signal(rssi):
    if rssi is None:
        return "Unknown", None
    label = "Excellent" if rssi >= -50 else "Good" if rssi >= -67 else "Fair" if rssi >= -75 else "Weak"
    return label, max(0, min(100, 2 * (rssi + 100)))


def security_assessment(labels):
    notes = []
    if "Open" in labels:
        assessment = "open"
        notes.append("Advertises an unencrypted access option. This scan does not test traffic protection.")
    elif LEGACY.intersection(labels):
        assessment = "legacy"
        notes.append("Advertises a legacy security option; review the router configuration if you manage it.")
    elif labels:
        assessment = "modern"
        notes.append("Advertises modern encryption; passwords, router configuration and authenticity are not tested.")
    else:
        assessment = "unknown"
        notes.append("Security was not exposed by CoreWLAN. Unknown does not mean open.")
    if "OWE" in labels:
        notes.append("OWE can encrypt a wireless link without authenticating the access point.")
    if {"WPA2 Personal", "WPA3 Personal"}.issubset(labels):
        notes.append("CoreWLAN reports both WPA2 and WPA3 Personal support; exact router configuration is not tested.")
    return assessment, notes


def make_record(*, ssid=None, bssid=None, rssi=None, noise=None, channel=None,
                band=None, width=None, security=()):
    rssi, noise = dbm(rssi), dbm(noise)
    label, percent = signal(rssi)
    assessment, notes = security_assessment(security)
    ssid = str(ssid) if ssid else None
    bssid = str(bssid) if bssid else None
    if ssid is None:
        notes.append("SSID unavailable: may be hidden, redacted by macOS, or not decodable.")
    if bssid is None:
        notes.append("BSSID unavailable; this entry cannot be reliably tracked across scans.")
    identifier = hashlib.sha256(bssid.encode()).hexdigest()[:16] if bssid else uuid.uuid4().hex[:16]
    return {"id": identifier, "ssid": ssid, "bssid": bssid,
            "rssi_dbm": rssi, "noise_dbm": noise,
            "snr_db": rssi - noise if rssi is not None and noise is not None else None,
            "signal_label": label, "signal_percent": percent,
            "channel": positive_int(channel), "band": band, "width_mhz": width,
            "security": list(security), "security_assessment": assessment, "notes": notes}


def normalize_network(network, corewlan):
    security = []
    for symbol, label in SECURITY_TYPES:
        value = getattr(corewlan, symbol, None)
        if value is not None:
            try:
                if network.supportsSecurity_(value):
                    security.append(label)
            except Exception:
                continue
    channel = read_method(network, "wlanChannel")
    band_value = read_method(channel, "channelBand")
    width_value = read_method(channel, "channelWidth")
    # Use SDK symbols instead of guessing band from overlapping channel numbers.
    bands = {getattr(corewlan, key): label for key, label in (
        ("kCWChannelBand2GHz", "2.4 GHz"), ("kCWChannelBand5GHz", "5 GHz"),
        ("kCWChannelBand6GHz", "6 GHz")) if hasattr(corewlan, key)}
    widths = {getattr(corewlan, key): mhz for key, mhz in (
        ("kCWChannelWidth20MHz", 20), ("kCWChannelWidth40MHz", 40),
        ("kCWChannelWidth80MHz", 80), ("kCWChannelWidth160MHz", 160),
        ("kCWChannelWidth320MHz", 320)) if hasattr(corewlan, key)}
    return make_record(ssid=read_method(network, "ssid"), bssid=read_method(network, "bssid"),
                       rssi=read_method(network, "rssiValue"), noise=read_method(network, "noiseMeasurement"),
                       channel=read_method(channel, "channelNumber"), band=bands.get(band_value),
                       width=widths.get(width_value), security=security)


def summarize(networks):
    counts = Counter(n["security_assessment"] for n in networks)
    channels = Counter((n["band"], n["channel"]) for n in networks if n["band"] and n["channel"])
    return {"total": len(networks), "visible_ssids": sum(n["ssid"] is not None for n in networks),
            "unique_ssids": len({n["ssid"] for n in networks if n["ssid"] is not None}),
            "redacted_names": sum(n["ssid"] is None for n in networks),
            **{key: counts[key] for key in ("open", "legacy", "modern", "unknown")},
            "channels": [{"band": band, "channel": channel, "count": count}
                         for (band, channel), count in sorted(channels.items())],
            "notes": ["Each row is one CoreWLAN scan record, usually an access point; shared SSIDs may appear more than once.",
                      "Channel counts are observed access points, not airtime, utilization, or a best-channel recommendation.",
                      "Signal labels and percentages are approximate local heuristics, not speed measurements."]}


def scan_result(networks, interface, started, warnings=()):
    networks.sort(key=lambda n: (n["rssi_dbm"] is None, -(n["rssi_dbm"] or -200), n["ssid"] or ""))
    warnings = list(warnings)
    if any(n["ssid"] is None or n["bssid"] is None for n in networks):
        warnings.append("macOS withheld some identifiers, or they are unavailable. Location permission and app signing can affect this. Missing names are not proof of hidden networks.")
    if not networks:
        warnings.append("CoreWLAN returned no networks. This does not prove no networks are nearby. Check Wi-Fi power, Location Services and app authorization.")
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "duration_seconds": round(time.monotonic() - started, 3),
            "interface": interface, "networks": networks, "summary": summarize(networks), "warnings": warnings}


class CoreWLANScanner:
    def __init__(self, interface=None):
        self.interface_name = interface

    def scan(self):
        if platform.system() != "Darwin":
            raise ScanError("unsupported_platform", "Live scanning requires macOS.", "Use --demo to view sample data on other systems.")
        try:
            import CoreWLAN
            import objc
        except ImportError as error:
            raise ScanError("missing_dependency", "PyObjC CoreWLAN is not installed in this Python environment.",
                            "Install requirements.txt using the same Python that runs app.py.") from error
        started = time.monotonic()
        with objc.autorelease_pool():
            client = CoreWLAN.CWWiFiClient.sharedWiFiClient()
            interface = client.interfaceWithName_(self.interface_name) if self.interface_name else client.interface()
            if interface is None:
                raise ScanError("no_interface", "No matching Wi-Fi interface is available.", "Check the Mac's Wi-Fi hardware or omit --interface to use the default.")
            if not interface.powerOn():
                raise ScanError("wifi_off", "Wi-Fi is switched off.", "Enable Wi-Fi in macOS settings, then scan again. Jarvis will not change it.")
            # Public broadcast discovery only. No association, credential or configuration API is used.
            networks, error = interface.scanForNetworksWithName_error_(None, None)
            if networks is None or (error is not None and not len(networks)):
                description = str(error.localizedDescription()) if error else "No result was returned by CoreWLAN."
                raise ScanError("scan_failed", description, "Check Location Services and app authorization; wait a few seconds and retry. See README for signing requirements.")
            warnings = ["CoreWLAN reported a partial result: " + str(error.localizedDescription())] if error else []
            rows = [normalize_network(network, CoreWLAN) for network in networks]
            return scan_result(rows, str(interface.interfaceName()), started, warnings)


class DemoScanner:
    def scan(self):
        started = time.monotonic()
        rows = [
            make_record(ssid="Jarvis Lab", bssid="02:00:00:00:00:01", rssi=-43, noise=-95, channel=36, band="5 GHz", width=80, security=["WPA3 Personal"]),
            make_record(ssid="Workshop", bssid="02:00:00:00:00:02", rssi=-64, noise=-92, channel=6, band="2.4 GHz", width=20, security=["WPA2 Personal"]),
            make_record(ssid="Sample Guest", bssid="02:00:00:00:00:03", rssi=-74, noise=-94, channel=11, band="2.4 GHz", width=20, security=["Open"]),
            make_record(ssid="Legacy example", bssid="02:00:00:00:00:04", rssi=-81, noise=None, channel=1, band="2.4 GHz", width=20, security=["WPA Personal", "WPA2 Personal"]),
            make_record(ssid=None, bssid=None, rssi=-70, channel=5, band="6 GHz", width=80, security=[]),
        ]
        result = scan_result(rows, "DEMO — synthetic fixtures", started)
        # The persistent demo banner labels fixtures; do not imply macOS redacted sample data.
        result["warnings"] = ["DEMO: all networks and measurements are invented examples. No hardware scan occurred."]
        return result
