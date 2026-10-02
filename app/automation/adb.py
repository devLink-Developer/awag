import re
import shlex
import subprocess

from app.services.errors import GatewayError


class AndroidDevice:
    def __init__(self, settings, serial, guard):
        self.settings, self.serial, self.guard = settings, serial, guard

    def _run(self, *args, binary=False):
        self.guard()
        command = [self.settings.adb_binary, "-H", self.settings.adb_host,
                   "-P", str(self.settings.adb_port), "-s", self.serial, *map(str, args)]
        try:
            result = subprocess.run(command, capture_output=True,
                                    timeout=self.settings.command_timeout_seconds, check=True)
        except FileNotFoundError:
            raise GatewayError("ADB_UNAVAILABLE", 503, retryable=True) from None
        except (subprocess.SubprocessError, OSError):
            raise GatewayError("ADB_COMMAND_FAILED", 503, retryable=True) from None
        self.guard()
        return result.stdout if binary else result.stdout.decode("utf-8", errors="replace").strip()

    def is_connected(self):
        return self._run("get-state") == "device"

    def is_adb_available(self):
        return "Android Debug Bridge" in self._run("version")

    def shell(self, *args):
        if not args or args[0] not in {"getprop", "am", "pm", "dumpsys", "mkdir", "rm", "cmd"}:
            raise GatewayError("ADB_COMMAND_NOT_ALLOWED")
        # adb shell interprets a remote shell command, even with local shell=False.
        return self._run("shell", shlex.join(list(args)))

    def start_app(self, package):
        self.shell("am", "start", "-W", "-a", "android.intent.action.MAIN", "-c",
                   "android.intent.category.LAUNCHER", "-p", package)

    def stop_app(self, package):
        self.shell("am", "force-stop", package)

    def screenshot(self):
        return self._run("exec-out", "screencap", "-p", binary=True)

    def current_activity(self):
        data = self.shell("dumpsys", "activity", "activities")
        match = re.search(r"(?:mResumedActivity|topResumedActivity).*?\s([\w.]+/[\w.$]+)", data)
        return match.group(1) if match else "UNKNOWN"

    def list_packages(self):
        return {line.removeprefix("package:") for line in self.shell("pm", "list", "packages").splitlines()}

    def push(self, local_path, remote_path):
        self.shell("mkdir", "-p", remote_path.rsplit("/", 1)[0])
        self._run("push", str(local_path), remote_path)

    def index_media(self, remote_path):
        from urllib.parse import quote
        self.shell("am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                   "-d", "file://" + quote(remote_path, safe="/"))

    def open_chat_link(self, package, number):
        if not re.fullmatch(r"\+[1-9][0-9]{6,14}", number):
            raise GatewayError("INVALID_RECIPIENT")
        result = self.shell("am", "start", "-W", "-a", "android.intent.action.VIEW", "-d",
                            "https://wa.me/" + number[1:], "-p", package)
        if "Error:" in result or "unable to resolve" in result.lower():
            raise GatewayError("CHAT_LINK_UNAVAILABLE")
