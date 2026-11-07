"""Location authorization status only; never requests coordinate updates."""
import platform
import threading


class LocationController:
    def __init__(self, demo=False):
        self.pending = threading.Event()
        self.manager = None
        self.foundation = None
        self.can_request = False
        self.app = None
        self._status = {"status": "demo" if demo else "unavailable", "services_enabled": None,
                        "can_request": False, "message": "Location authorization is not used in demo mode." if demo else "CoreLocation unavailable."}
        if demo or platform.system() != "Darwin":
            return
        try:
            import Foundation
            import CoreLocation
            self.foundation, self.corelocation = Foundation, CoreLocation
            info = Foundation.NSBundle.mainBundle().infoDictionary() or {}
            self.can_request = bool(info.get("NSLocationUsageDescription"))
            if self.can_request:
                from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
                self.app = NSApplication.sharedApplication()
                self.app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
                self.app.finishLaunching()
            self.manager = CoreLocation.CLLocationManager.alloc().init()
            self.update()
        except Exception as error:
            self._status["message"] = "CoreLocation initialization failed: " + str(error)

    def snapshot(self):
        return dict(self._status)

    def update(self):
        if self.manager is None:
            return
        status = int(self.manager.authorizationStatus())
        names = {0: "not_determined", 1: "restricted", 2: "denied", 3: "authorized", 4: "authorized_when_in_use"}
        self._status = {"status": names.get(status, "unknown"),
                        "services_enabled": bool(self.corelocation.CLLocationManager.locationServicesEnabled()),
                        "can_request": self.can_request,
                        "message": "Permission alone may not expose identifiers: modern macOS may require proper app signing. See README." if self.can_request else
                        "CLI Python cannot reliably request permission. Use the optional Mac app build with a purpose string; proper signing may be required. See README."}

    def request(self):
        if not self.can_request:
            return False
        self.pending.set()
        return True

    def step(self):
        # Called only by main(); Cocoa authorization runs on the main thread.
        if self.manager is not None:
            if self.pending.is_set():
                self.pending.clear()
                self.app.activateIgnoringOtherApps_(True)
                self.manager.requestWhenInUseAuthorization()
            self.foundation.NSRunLoop.currentRunLoop().runUntilDate_(self.foundation.NSDate.dateWithTimeIntervalSinceNow_(0.05))
            self.update()
