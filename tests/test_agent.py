"""Discovery contract tests. All radios/APs are fakes; no real scans run here."""
from contextlib import nullcontext
import http.client
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
from jarvis_wifi.location import LocationController
from jarvis_wifi.scanner import (
    CoreWLANScanner, DemoScanner, ScanError, make_record, normalize_network,
    security_assessment, summarize,
)


class FakeLocation:
    def snapshot(self):
        return {"status": "not_determined", "services_enabled": True, "can_request": False}

    def request(self):
        return False


class FakeNetwork:
    """Only documented read accessors exist; no association/configuration methods."""
    def __init__(self, ssid="Test AP", security=(404,), bssid="02:00:00:00:00:01"):
        self.name, self.allowed, self.address = ssid, security, bssid
        self.security_queries = []

    def ssid(self):
        return self.name

    def bssid(self):
        return self.address

    def rssiValue(self):
        return -62

    def noiseMeasurement(self):
        return -94

    def wlanChannel(self):
        return SimpleNamespace(channelBand=lambda: 303, channelWidth=lambda: 808,
                               channelNumber=lambda: 5)

    def supportsSecurity_(self, constant):
        self.security_queries.append(constant)
        return constant in self.allowed


def fake_corewlan(interface=None):
    # Intentionally non-Apple numbers detect incorrect hard-coded enum assumptions.
    client = SimpleNamespace(interface=lambda: interface,
                             interfaceWithName_=lambda name: interface)
    module = SimpleNamespace(
        kCWSecurityNone=100, kCWSecurityWEP=101, kCWSecurityWPAPersonal=102,
        kCWSecurityWPA2Personal=404, kCWSecurityWPA3Personal=411,
        kCWSecurityWPAPersonalMixed=403, kCWSecurityWPA3Transition=413,
        kCWSecurityPersonal=900, kCWSecurityEnterprise=901,
        kCWChannelBand6GHz=303, kCWChannelBand2GHz=301,
        kCWChannelWidth80MHz=808,
        CWWiFiClient=SimpleNamespace(sharedWiFiClient=lambda: client),
    )
    return module


class FakeInterface:
    def __init__(self, networks=(), error=None, powered=True):
        self.networks, self.error, self.powered = networks, error, powered
        self.scan_arguments = []

    def powerOn(self):
        return self.powered

    def interfaceName(self):
        return "en-test"

    def scanForNetworksWithName_error_(self, name, error):
        self.scan_arguments.append((name, error))
        return self.networks, self.error


class ModelTests(unittest.TestCase):
    def test_named_security_and_channel_constants(self):
        network = FakeNetwork()
        row = normalize_network(network, fake_corewlan())
        self.assertEqual(row["security"], ["WPA2 Personal"])
        self.assertEqual(row["security_assessment"], "modern")
        self.assertEqual((row["band"], row["width_mhz"], row["channel"]), ("6 GHz", 80, 5))
        self.assertEqual(row["snr_db"], 32)
        self.assertNotIn(900, network.security_queries)
        self.assertNotIn(901, network.security_queries)

    def test_missing_security_never_becomes_open(self):
        unknown = normalize_network(FakeNetwork(security=()), fake_corewlan())
        opened = normalize_network(FakeNetwork(security=(100,)), fake_corewlan())
        self.assertEqual(unknown["security_assessment"], "unknown")
        self.assertEqual(unknown["security"], [])
        self.assertEqual(opened["security_assessment"], "open")

    def test_security_access_failure_stays_unknown(self):
        network = FakeNetwork()
        network.supportsSecurity_ = lambda value: (_ for _ in ()).throw(RuntimeError("not exposed"))
        self.assertEqual(normalize_network(network, fake_corewlan())["security_assessment"], "unknown")

    def test_concrete_legacy_and_owe_options_are_explained(self):
        self.assertEqual(security_assessment(["WPA2 Personal", "WPA Personal"])[0], "legacy")
        self.assertEqual(security_assessment(["OWE", "Open"])[0], "open")
        self.assertEqual(security_assessment(["OWE"])[0], "modern")
        self.assertTrue(any("without authenticating" in note for note in security_assessment(["OWE"])[1]))

    def test_union_queries_do_not_mislabel_wpa2_as_legacy_or_wpa3(self):
        network = FakeNetwork(security=(404, 403, 413))
        row = normalize_network(network, fake_corewlan())
        self.assertEqual(row["security"], ["WPA2 Personal"])
        self.assertEqual(row["security_assessment"], "modern")
        self.assertNotIn(403, network.security_queries)
        self.assertNotIn(413, network.security_queries)

    def test_unknown_channel_band_not_inferred_from_number(self):
        network = FakeNetwork()
        network.wlanChannel = lambda: SimpleNamespace(channelBand=lambda: 999,
            channelWidth=lambda: 999, channelNumber=lambda: 5)
        row = normalize_network(network, fake_corewlan())
        self.assertIsNone(row["band"])
        self.assertIsNone(row["width_mhz"])
        self.assertEqual(row["channel"], 5)

    def test_unavailable_measurements_do_not_create_fabricated_snr(self):
        for value in (None, 0, -127, 1, float("nan"), "invalid"):
            with self.subTest(value=value):
                row = make_record(rssi=-62, noise=value)
                self.assertIsNone(row["noise_dbm"])
                self.assertIsNone(row["snr_db"])
        row = make_record(rssi=0, noise=-95, channel=0)
        self.assertEqual(row["signal_label"], "Unknown")
        self.assertIsNone(row["signal_percent"])
        self.assertIsNone(row["channel"])

    def test_redacted_records_keep_separate_identities(self):
        records = [make_record(rssi=-65), make_record(rssi=-65)]
        self.assertNotEqual(records[0]["id"], records[1]["id"])
        summary = summarize(records)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["visible_ssids"], 0)
        self.assertEqual(summary["redacted_names"], 2)
        self.assertTrue(any("may be hidden" in note for note in records[0]["notes"]))

    def test_shared_ssids_count_access_points_separately(self):
        records = [make_record(ssid="Shared", bssid="02:00:00:00:00:01", band="5 GHz", channel=36),
                   make_record(ssid="Shared", bssid="02:00:00:00:00:02", band="5 GHz", channel=36)]
        summary = summarize(records)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["visible_ssids"], 2)
        self.assertEqual(summary["unique_ssids"], 1)
        self.assertEqual(summary["channels"], [{"band": "5 GHz", "channel": 36, "count": 2}])

    def test_ssid_is_preserved_as_data_for_safe_client_rendering(self):
        name = '<img src=x onerror="alert(1)">'
        self.assertEqual(make_record(ssid=name)["ssid"], name)


class CoreWLANTests(unittest.TestCase):
    def scan_with(self, interface):
        with patch("jarvis_wifi.scanner.platform.system", return_value="Darwin"), \
             patch.dict(sys.modules, {"CoreWLAN": fake_corewlan(interface),
                                      "objc": SimpleNamespace(autorelease_pool=nullcontext)}):
            return CoreWLANScanner().scan()

    def test_broadcast_scan_uses_nil_name_and_error_argument(self):
        interface = FakeInterface([FakeNetwork()])
        result = self.scan_with(interface)
        self.assertEqual(interface.scan_arguments, [(None, None)])
        self.assertEqual(result["interface"], "en-test")
        self.assertEqual(result["summary"]["total"], 1)

    def test_empty_result_is_distinct_from_failure(self):
        result = self.scan_with(FakeInterface([]))
        self.assertEqual(result["networks"], [])
        self.assertTrue(any("does not prove" in warning for warning in result["warnings"]))
        with self.assertRaises(ScanError) as caught:
            self.scan_with(FakeInterface(None))
        self.assertEqual(caught.exception.code, "scan_failed")

    def test_error_without_records_reports_failure(self):
        error = SimpleNamespace(localizedDescription=lambda: "Permission unavailable")
        with self.assertRaises(ScanError) as caught:
            self.scan_with(FakeInterface([], error))
        self.assertEqual(caught.exception.message, "Permission unavailable")

    def test_partial_records_preserved_with_warning(self):
        error = SimpleNamespace(localizedDescription=lambda: "Scan interrupted")
        result = self.scan_with(FakeInterface([FakeNetwork()], error))
        self.assertEqual(result["summary"]["total"], 1)
        self.assertTrue(any("partial" in warning for warning in result["warnings"]))

    def test_wifi_off_does_not_attempt_scan_or_enable_radio(self):
        interface = FakeInterface(powered=False)
        with self.assertRaises(ScanError) as caught:
            self.scan_with(interface)
        self.assertEqual(caught.exception.code, "wifi_off")
        self.assertEqual(interface.scan_arguments, [])

    def test_missing_interface_and_unsupported_platform(self):
        with self.assertRaises(ScanError) as caught:
            self.scan_with(None)
        self.assertEqual(caught.exception.code, "no_interface")
        with patch("jarvis_wifi.scanner.platform.system", return_value="Linux"):
            with self.assertRaises(ScanError) as caught:
                CoreWLANScanner().scan()
        self.assertEqual(caught.exception.code, "unsupported_platform")


class StateTests(unittest.TestCase):
    def test_no_scan_occurs_on_agent_construction(self):
        scanner = SimpleNamespace(scan=lambda: self.fail("Unexpected automatic scan"))
        agent = app.Agent(scanner, FakeLocation())
        self.assertFalse(agent.state()["scanning"])
        self.assertIsNone(agent.state()["last_result"])

    def test_busy_and_cooldown_prevent_overlapping_scans(self):
        release = threading.Event()
        scanner = SimpleNamespace(scan=lambda: release.wait(3) or {})
        agent = app.Agent(scanner, FakeLocation(), cooldown=30)
        try:
            self.assertEqual(agent.start_scan()[0], 202)
            self.assertEqual(agent.start_scan()[0], 409)
        finally:
            release.set()
        deadline = time.monotonic() + 3
        while agent.state()["scanning"] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(agent.state()["scanning"])
        self.assertEqual(agent.start_scan()[0], 429)

    def test_error_preserves_previous_result_as_stale(self):
        def fail():
            raise ScanError("scan_failed", "Radio error", "Retry")
        agent = app.Agent(SimpleNamespace(scan=fail), FakeLocation())
        agent.last_result = {"networks": [{"ssid": "Prior observation"}]}
        agent.scanning = True
        agent._scan_worker()
        state = agent.state()
        self.assertEqual(state["last_result"]["networks"][0]["ssid"], "Prior observation")
        self.assertEqual(state["error"]["code"], "scan_failed")
        self.assertFalse(state["scanning"])
        state["last_result"]["networks"].clear()
        self.assertEqual(len(agent.state()["last_result"]["networks"]), 1)

    def test_demo_is_labeled_and_never_imports_radio_api(self):
        with patch.dict(sys.modules, {"CoreWLAN": None, "objc": None}):
            result = DemoScanner().scan()
        self.assertIn("DEMO", result["interface"])
        self.assertTrue(any("invented" in warning for warning in result["warnings"]))
        self.assertEqual(result["summary"]["total"], 5)

    def test_cli_location_controller_does_not_request_or_read_coordinates(self):
        calls = []
        manager = SimpleNamespace(authorizationStatus=lambda: 0,
                                  requestWhenInUseAuthorization=lambda: calls.append("request"))
        foundation = SimpleNamespace(NSBundle=SimpleNamespace(mainBundle=lambda:
                    SimpleNamespace(infoDictionary=lambda: {})))
        location = SimpleNamespace(CLLocationManager=SimpleNamespace(
            alloc=lambda: SimpleNamespace(init=lambda: manager), locationServicesEnabled=lambda: True))
        with patch("jarvis_wifi.location.platform.system", return_value="Darwin"), \
             patch.dict(sys.modules, {"Foundation": foundation, "CoreLocation": location}):
            controller = LocationController()
        self.assertEqual(controller.snapshot()["status"], "not_determined")
        self.assertFalse(controller.request())
        self.assertEqual(calls, [])


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = app.Agent(DemoScanner(), FakeLocation(), demo=True, cooldown=0)
        cls.server = app.make_server(cls.agent, port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, method, path, headers=None, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        data = json.loads(raw) if raw and "application/json" in response.getheader("Content-Type", "") else raw
        result = response.status, data, dict(response.getheaders())
        connection.close()
        return result

    def token_headers(self):
        status, data, _ = self.request("GET", "/api/session")
        self.assertEqual(status, 200)
        return {"X-Jarvis-Token": data["token"]}

    def test_loopback_only_and_response_headers(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        status, data, headers = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(data["mode"], "demo")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertNotIn("token", data)

    def test_untrusted_host_and_origin_blocked_even_with_token(self):
        self.assertEqual(self.request("GET", "/api/session", {"Host": "attacker.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/state", {"Origin": "https://attacker.example"})[0], 403)
        headers = {**self.token_headers(), "Origin": "https://attacker.example"}
        self.assertEqual(self.request("POST", "/api/scan", headers)[0], 403)

    def test_scan_requires_session_token_and_accepts_no_credentials(self):
        self.assertEqual(self.request("POST", "/api/scan")[0], 403)
        self.assertEqual(self.request("POST", "/api/scan", {"X-Jarvis-Token": "invalid"})[0], 403)
        status, data, _ = self.request("POST", "/api/scan", self.token_headers(), body='{"password":"example"}')
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "unexpected_body")

    def test_no_association_or_credential_routes(self):
        headers = self.token_headers()
        for path in ("/api/connect", "/api/password", "/api/credentials", "/api/configure"):
            with self.subTest(path=path):
                self.assertEqual(self.request("POST", path, headers)[0], 404)
        self.assertEqual(self.request("GET", "/api/scan")[0], 404)

    def test_authorized_scan_and_cli_permission_explanation(self):
        status, _, _ = self.request("POST", "/api/scan", self.token_headers())
        self.assertEqual(status, 202)
        deadline = time.monotonic() + 3
        while self.agent.state()["scanning"] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNotNone(self.agent.state()["last_result"])
        status, data, _ = self.request("POST", "/api/location/request", self.token_headers())
        self.assertEqual(status, 409)
        self.assertEqual(data["error"]["code"], "location_requires_app")

    def test_static_path_traversal_blocked(self):
        for path in ("/../app.py", "/%2e%2e/app.py", "/app.py", "/requirements.txt"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)

    def test_shutdown_requires_token_before_signaling_local_agent(self):
        self.agent.stop.clear()
        try:
            self.assertEqual(self.request("POST", "/api/shutdown")[0], 403)
            self.assertFalse(self.agent.stop.is_set())
            status, data, _ = self.request("POST", "/api/shutdown", self.token_headers())
            self.assertEqual(status, 202)
            self.assertEqual(data["status"], "stopping")
            self.assertTrue(self.agent.stop.wait(timeout=1))
        finally:
            self.agent.stop.clear()


if __name__ == "__main__":
    unittest.main()
