import httpx
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.client_config import AppiumClientConfig

from app.services.errors import GatewayError


class GuardedDriver(webdriver.Remote):
    def __init__(self, guard, **kwargs):
        self.guard = guard
        super().__init__(**kwargs)

    def execute(self, driver_command, params=None):
        self.guard()
        result = super().execute(driver_command, params)
        self.guard()
        return result


class AppiumSession:
    def __init__(self, instance, settings, device, guard, session_changed):
        self.instance, self.settings, self.device = instance, settings, device
        self.guard, self.session_changed = guard, session_changed
        self.driver = None

    def available(self):
        self.guard()
        try:
            response = httpx.get(self.instance.appium_url.rstrip("/") + "/status", timeout=3)
            response.raise_for_status()
            return bool(response.json()["value"]["ready"])
        except Exception:
            return False

    def recover(self):
        self.guard()
        base = self.instance.appium_url.rstrip("/")
        try:
            with httpx.Client(timeout=self.settings.command_timeout_seconds) as client:
                response = client.get(base + "/appium/sessions")
                response.raise_for_status()
                sessions = response.json()["value"]
                ids = {item["id"] for item in sessions if item.get("capabilities", {}).get(
                    "appium:udid", item.get("capabilities", {}).get("udid")
                ) == self.instance.adb_serial}
                if self.instance.appium_session_id:
                    ids.add(self.instance.appium_session_id)
                for session_id in ids:
                    self.guard()
                    result = client.delete(base + "/session/" + session_id)
                    if result.status_code not in {200, 404}:
                        raise GatewayError("SESSION_CLEANUP_FAILED", 503, retryable=True)
                self.guard()
                remaining = client.get(base + "/appium/sessions")
                remaining.raise_for_status()
                if any(s["id"] in ids for s in remaining.json()["value"]):
                    raise GatewayError("SESSION_CLEANUP_FAILED", 503, retryable=True)
        except GatewayError:
            raise
        except Exception:
            raise GatewayError("APPIUM_UNAVAILABLE", 503, retryable=True) from None
        # Cancel any orphaned UiAutomator instrumentation before a fresh session.
        self.device.stop_app("io.appium.uiautomator2.server")
        self.device.stop_app("io.appium.uiautomator2.server.test")
        self.session_changed(None)

    def connect(self):
        if self.driver:
            return self.driver
        options = UiAutomator2Options().load_capabilities({
            "platformName": "Android", "appium:automationName": "UiAutomator2",
            "appium:udid": self.instance.adb_serial, "appium:systemPort": self.instance.system_port,
            "appium:remoteAdbHost": self.settings.adb_host, "appium:adbPort": self.settings.adb_port,
            "appium:noReset": True, "appium:fullReset": False, "appium:autoLaunch": False,
            "appium:newCommandTimeout": max(45, self.settings.command_timeout_seconds + self.settings.ui_wait_seconds),
            "appium:adbExecTimeout": self.settings.command_timeout_seconds * 1000,
            "appium:uiautomator2ServerReadTimeout": self.settings.command_timeout_seconds * 1000,
            "appium:uiautomator2ServerLaunchTimeout": self.settings.command_timeout_seconds * 1000,
            "appium:uiautomator2ServerInstallTimeout": self.settings.command_timeout_seconds * 1000,
            "appium:androidInstallTimeout": self.settings.command_timeout_seconds * 1000,
            "appium:skipLogcatCapture": True, "appium:printPageSourceOnFindFailure": False,
            "appium:suppressKillServer": True,
        })
        config = AppiumClientConfig(remote_server_addr=self.instance.appium_url,
                                    timeout=self.settings.command_timeout_seconds,
                                    direct_connection=False)
        try:
            self.driver = GuardedDriver(self.guard, options=options, client_config=config)
            self.session_changed(self.driver.session_id)
            self.driver.implicitly_wait(0)
        except GatewayError:
            raise
        except Exception:
            raise GatewayError("APPIUM_SESSION_FAILED", 503, retryable=True) from None
        return self.driver

    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.session_changed(None)
