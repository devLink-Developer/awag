from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from app.automation.appium import AppiumSession
from app.services.errors import GatewayError


def test_orphan_sessions_are_closed_before_instrumentation(settings, monkeypatch):
    requests = []
    sessions = [{"id": "old", "capabilities": {"appium:udid": "emulator-5554"}},
                {"id": "other", "capabilities": {"appium:udid": "another-device"}}]
    def handle(request):
        requests.append((request.method, request.url.path))
        if request.method == "DELETE":
            sessions[:] = [s for s in sessions if s["id"] != request.url.path.rsplit("/", 1)[-1]]
            return httpx.Response(200, json={"value": None})
        return httpx.Response(200, json={"value": sessions[:]})
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    instance = SimpleNamespace(adb_serial="emulator-5554", appium_url="http://appium", appium_session_id="old")
    device, guard, callback = Mock(), Mock(), Mock()
    AppiumSession(instance, settings, device, guard, callback).recover()
    assert requests == [("GET", "/appium/sessions"), ("DELETE", "/session/old"), ("GET", "/appium/sessions")]
    assert len(sessions) == 1 and sessions[0]["id"] == "other"
    assert device.stop_app.call_count == 2
    callback.assert_called_once_with(None)


def test_cleanup_failure_blocks_new_session(settings, monkeypatch):
    def handle(request):
        if request.method == "DELETE":
            return httpx.Response(500, json={"value": {"error": "unknown error"}})
        return httpx.Response(200, json={"value": []})
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    instance = SimpleNamespace(adb_serial="emulator-5554", appium_url="http://appium", appium_session_id="old")
    device, callback = Mock(), Mock()
    with pytest.raises(GatewayError, match="SESSION_CLEANUP_FAILED"):
        AppiumSession(instance, settings, device, Mock(), callback).recover()
    device.stop_app.assert_not_called()
    callback.assert_not_called()
