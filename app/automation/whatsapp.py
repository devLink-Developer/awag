import re
from pathlib import Path

from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from app.automation.adb import AndroidDevice
from app.automation.appium import AppiumSession
from app.automation.selectors import WhatsAppSelectors
from app.automation.verification import confirms_new_bubble, outgoing_bubbles
from app.models.entities import MessageType
from app.services.errors import GatewayError


class WhatsAppAutomation:
    def __init__(self, instance, settings, lease, session_changed):
        self.instance, self.settings, self.lease = instance, settings, lease
        self.device = AndroidDevice(settings, instance.adb_serial, lease.assert_owned)
        self.session = AppiumSession(instance, settings, self.device, lease.assert_owned, session_changed)
        self.selectors = WhatsAppSelectors(settings.whatsapp_package, settings.ui_language)
        self.driver = None

    def recover(self):
        self.session.recover()

    def _elements(self, locators):
        found = {}
        for locator in locators:
            for element in self.driver.find_elements(*locator):
                if element.is_displayed():
                    found[element.id] = element
        return list(found.values())

    def _unique(self, locators):
        for locator in locators:
            values = [element for element in self.driver.find_elements(*locator) if element.is_displayed()]
            if len(values) > 1:
                raise GatewayError("SELECTOR_AMBIGUOUS")
            if values:
                return values[0] if values[0].is_enabled() else False
        return False

    def _wait(self, predicate, timeout=None):
        try:
            return WebDriverWait(self.driver, timeout or self.settings.ui_wait_seconds,
                                 poll_frequency=0.4,
                                 ignored_exceptions=(NoSuchElementException, StaleElementReferenceException)).until(
                lambda _: predicate()
            )
        except TimeoutException:
            raise GatewayError("UI_STATE_TIMEOUT", retryable=True) from None

    def _find(self, key):
        return self._wait(lambda: self._unique(self.selectors.locators(key)))

    def _named(self, name):
        locators = [self.selectors.text(name)]
        element = self._unique(locators)
        if element:
            return element
        try:
            self.driver.find_element(*self.selectors.scroll_text(name))
        except NoSuchElementException:
            pass
        return self._wait(lambda: self._unique(locators))

    def _optional_click(self, key):
        element = self._unique(self.selectors.locators(key))
        if element:
            element.click()
            return True
        return False

    def open(self):
        if not self.device.is_connected():
            raise GatewayError("DEVICE_OFFLINE", retryable=True)
        if self.settings.whatsapp_package not in self.device.list_packages():
            raise GatewayError("WHATSAPP_NOT_INSTALLED")
        self.driver = self.session.connect()
        # Restart the task to leave stale galleries or previews from a pre-send failure.
        # Force-stop preserves WhatsApp's data and authenticated session.
        self.device.stop_app(self.settings.whatsapp_package)
        self.device.start_app(self.settings.whatsapp_package)

        def ready():
            if self._elements(self.selectors.locators("registration")):
                raise GatewayError("WHATSAPP_NOT_CONFIGURED")
            return self.is_ready()
        self._wait(ready)

    def is_ready(self):
        return bool(self._elements(self.selectors.locators("home")) or
                    self._elements(self.selectors.locators("message_input")))

    def open_chat(self, phone_number):
        self.device.open_chat_link(self.settings.whatsapp_package, phone_number)

        def opened():
            if self.selectors.invalid_notice(self.get_current_screen()):
                raise GatewayError("RECIPIENT_NOT_ON_WHATSAPP")
            return self._unique(self.selectors.locators("message_input"))
        self._wait(opened)
        expected = phone_number[1:]
        header = self._find("header")
        header.click()
        from xml.etree import ElementTree as ET
        def matches_phone():
            root = ET.fromstring(self.get_current_screen())
            values = {re.sub(r"\D", "", n.get("text", "")) for n in root.iter()
                      if self.selectors.matches_id(n, "contact_phone") and n.get("text", "").strip()}
            return values == {expected}
        self._wait(matches_phone)
        self.driver.back()
        self._find("message_input")

    def _enter(self, element, text):
        element.click()
        element.clear()
        self.driver.execute_script("mobile: type", {"text": text})
        if element.get_attribute("text") != text:
            raise GatewayError("INPUT_VERIFICATION_FAILED")

    def _prepare_attachment(self, message, media):
        folder = "QA_" + message.id.hex
        filename = media.original_name if message.type == MessageType.document else (
            message.id.hex + Path(media.storage_name).suffix)
        root = {MessageType.image: "Pictures", MessageType.video: "Movies",
                MessageType.audio: "Music", MessageType.document: "Download"}[message.type]
        remote = f"/sdcard/{root}/{folder}/{filename}"
        self.device.push(self.settings.media_dir / media.storage_name, remote)
        if message.type != MessageType.document:
            self.device.index_media(remote)
        self._find("attach").click()
        key = "gallery" if message.type in {MessageType.image, MessageType.video} else message.type.value
        self._find(key).click()
        self._optional_click("permission")
        self._optional_click("allow")
        if key == "gallery":
            self._optional_click("albums")
            self._named(folder).click()
            # Each generated album contains exactly one file. Never select a positional thumbnail.
            self._find("thumbnail").click()
        elif key == "document":
            self._optional_click("browse")
            self._find("drawer").click()
            self._find("downloads").click()
            self._named(folder).click()
            self._named(filename).click()
        else:
            # WhatsApp music picker displays a filename or its extensionless title.
            element = self._unique([self.selectors.text(filename), self.selectors.text(Path(filename).stem)])
            if not element:
                element = self._named(Path(filename).stem)
            element.click()
        if message.text:
            self._enter(self._find("caption"), message.text)
        self._find("send")
        return filename

    def send(self, message, media, before_send):
        self.open()
        self.open_chat(message.recipient)
        self._find("message_input").clear()
        baseline = outgoing_bubbles(self.get_current_screen(), self.selectors)
        filename = None
        if message.type == MessageType.text:
            self._enter(self._find("message_input"), message.text)
        else:
            filename = self._prepare_attachment(message, media)
        button = self._find("send")
        before_send()
        button.click()
        confirmed_audio_dialog = False

        def confirmed():
            nonlocal confirmed_audio_dialog
            if message.type == MessageType.audio and not confirmed_audio_dialog:
                dialog = self._unique(self.selectors.locators("audio_confirm"))
                if dialog and dialog.text.strip().casefold() in {
                    label.casefold() for label in self.selectors.labels["send"]
                }:
                    dialog.click()
                    confirmed_audio_dialog = True
            current = outgoing_bubbles(self.get_current_screen(), self.selectors)
            return confirms_new_bubble(baseline, current, message.type, message.text, filename)
        self._wait(confirmed, self.settings.send_wait_seconds)

    def send_text(self, phone_number, text, before_send):
        from types import SimpleNamespace
        import uuid
        self.send(SimpleNamespace(id=uuid.uuid4(), recipient=phone_number, type=MessageType.text,
                                  text=text), None, before_send)

    def get_current_screen(self):
        return self.driver.page_source

    def evidence(self, message_id):
        directory = self.settings.screenshot_dir / str(self.instance.id) / str(message_id)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        result = {}
        try:
            data = self.device.screenshot()
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("invalid screenshot")
            path = directory / "error.png"
            path.write_bytes(data)
            path.chmod(0o600)
            result["screenshot"] = str(path.relative_to(self.settings.screenshot_dir))
        except Exception:
            result["screenshot_error"] = "SCREENSHOT_UNAVAILABLE"
        try:
            result["activity"] = self.device.current_activity()
        except Exception:
            result["activity_error"] = "ACTIVITY_UNAVAILABLE"
        return result

    def close(self):
        self.session.close()
