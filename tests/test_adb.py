import shlex
import subprocess
from unittest.mock import Mock

import pytest

from app.automation.adb import AndroidDevice
from app.services.errors import GatewayError


def test_remote_shell_quoting(settings, monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert "shell" not in kwargs
        return subprocess.CompletedProcess(command, 0, stdout=b"ok")
    monkeypatch.setattr(subprocess, "run", run)
    guard = Mock()
    device = AndroidDevice(settings, "emulator-5554", guard)
    value = "file:///sdcard/example';touch /data/test;'.png"
    device.shell("am", "broadcast", "-d", value)
    assert shlex.split(calls[0][-1]) == ["am", "broadcast", "-d", value]
    assert guard.call_count == 2
    with pytest.raises(GatewayError, match="ADB_COMMAND_NOT_ALLOWED"):
        device.shell("sh", "-c", "bad")


def test_guard_blocks_command(settings, monkeypatch):
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    guard = Mock(side_effect=GatewayError("LOCK_LOST"))
    with pytest.raises(GatewayError):
        AndroidDevice(settings, "emulator-5554", guard).screenshot()
    run.assert_not_called()
