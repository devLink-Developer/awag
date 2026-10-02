import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.automation.appium import AppiumSession
from app.services.errors import GatewayError


@pytest.mark.parametrize("command_timeout", [25, 300])
def test_pinned_client_guard_and_capabilities(settings, command_timeout):
    settings.command_timeout_seconds = command_timeout
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
            calls.append((self.path, body))
            value = {"sessionId": "test-session", "capabilities": {}} if self.path == "/session" else None
            self.respond(value)
        def do_DELETE(self):
            calls.append((self.path, None))
            self.respond(None)
        def respond(self, value):
            data = json.dumps({"value": value}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        instance = SimpleNamespace(adb_serial="emulator-5554", appium_url=f"http://127.0.0.1:{server.server_port}",
                                   system_port=8200)
        guard, callback = Mock(), Mock()
        session = AppiumSession(instance, settings, Mock(), guard, callback)
        driver = session.connect()
        assert driver.session_id == "test-session"
        caps = calls[0][1]["capabilities"]["alwaysMatch"]
        assert caps["appium:noReset"] is True
        assert caps["appium:fullReset"] is False
        assert caps["appium:udid"] == "emulator-5554"
        for name in ("adbExecTimeout", "uiautomator2ServerReadTimeout", "uiautomator2ServerLaunchTimeout",
                     "uiautomator2ServerInstallTimeout", "androidInstallTimeout"):
            assert caps[f"appium:{name}"] == command_timeout * 1000
        assert caps["appium:newCommandTimeout"] >= command_timeout + settings.ui_wait_seconds
        before = len(calls)
        guard.side_effect = GatewayError("LOCK_LOST")
        with pytest.raises(GatewayError):
            driver.find_elements("id", "any")
        assert len(calls) == before
        guard.side_effect = None
        session.close()
        assert callback.call_args_list[-1].args == (None,)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
