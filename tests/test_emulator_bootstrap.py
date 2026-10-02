import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Bash boot lifecycle is checked on Linux")


@pytest.mark.parametrize("fail_bootstrap", [False, True])
def test_software_boot_restores_adb_or_stops_its_process(tmp_path, fail_bootstrap):
    sdk = tmp_path / "sdk"
    (sdk / "platform-tools").mkdir(parents=True)
    (sdk / "emulator").mkdir()
    avd = tmp_path / "avd"
    avd.mkdir()
    (avd / "WhatsApp_QA.ini").touch()
    adb = sdk / "platform-tools" / "adb"
    adb.write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
root = Path(os.environ["BOOT_FIXTURE"])
args = sys.argv[1:]
with (root / "calls").open("a") as log:
    log.write(" ".join(args) + "\\n")
if args == ["version"]:
    print("Android Debug Bridge version 37.0.1")
elif args[-1:] == ["get-state"]:
    if not (root / "running").exists(): sys.exit(1)
    print("device")
elif args[-3:] == ["shell", "getprop", "sys.boot_completed"]:
    print("1" if (root / "unrooted").exists() else "0")
elif args[-3:] == ["shell", "getprop", "ro.hw_timeout_multiplier"]:
    print("10" if (root / "configured").exists() else "")
elif args[-4:] == ["shell", "setprop", "ro.hw_timeout_multiplier", "10"]:
    if os.environ["FAIL_BOOTSTRAP"] == "1": sys.exit(1)
    (root / "configured").touch()
elif args[-1:] == ["unroot"]:
    (root / "unrooted").touch()
''')
    emulator = sdk / "emulator" / "emulator"
    emulator.write_text('''#!/usr/bin/env bash
printf '%s\\n' "$@" > "$BOOT_FIXTURE/args"
touch "$BOOT_FIXTURE/running"
trap 'rm -f "$BOOT_FIXTURE/running"; touch "$BOOT_FIXTURE/terminated"; exit 0' TERM
for (( i=0; i<12; i++ )); do sleep 1; done
rm -f "$BOOT_FIXTURE/running"
''')
    adb.chmod(0o755)
    emulator.chmod(0o755)
    env = dict(os.environ, ANDROID_HOME=str(sdk), ANDROID_AVD_HOME=str(avd),
               BOOT_FIXTURE=str(tmp_path), FAIL_BOOTSTRAP="1" if fail_bootstrap else "0",
               EMULATOR_ACCEL_MODE="off", EMULATOR_MEMORY_MB="1024", EMULATOR_CORES="2", EMULATOR_BOOT_TIMEOUT_SECONDS="30")
    script = Path(__file__).resolve().parents[1] / "scripts" / "start-emulator.sh"
    result = subprocess.run(["bash", str(script), "--headless"], env=env, capture_output=True,
                            text=True, timeout=20)
    assert not (tmp_path / "running").exists()
    if fail_bootstrap:
        assert result.returncode != 0
        assert (tmp_path / "terminated").exists()
    else:
        assert result.returncode == 0, result.stderr
        assert "booted" in result.stdout
        calls = (tmp_path / "calls").read_text()
        assert calls.index(" setprop ro.hw_timeout_multiplier 10") < calls.index(" unroot")
        args = (tmp_path / "args").read_text().splitlines()
        assert args[args.index("-accel") + 1] == "off"
        assert args[args.index("-tb-size") + 1] == "64"
        assert args[args.index("-memory") + 1] == "1024"
        assert args[args.index("-cores") + 1] == "2"
        assert "-wipe-data" not in args
