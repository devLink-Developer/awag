"""All UI identifiers, localized labels and dynamic selectors live here.

The shipped profile must be calibrated against the manually installed WhatsApp build.
Unknown layouts fail closed; coordinates are never used.
"""
import json

from appium.webdriver.common.appiumby import AppiumBy


class WhatsAppSelectors:
    IDS = {
        "message_input": ("entry",), "send": ("send", "send_button"),
        "attach": ("input_attach_button",), "home": ("conversations_list", "fab"),
        "registration": ("registration_phone", "eula_accept", "verify_sms_code", "registration_code"),
        "header": ("conversation_contact_name",),
        "contact_phone": ("contact_info_phone", "contact_info_phone_number", "phone_number"),
        "invalid_notice": ("alert_dialog_message", "invite_button", "invite_to_whatsapp"),
        "caption": ("caption", "caption_edit_text", "entry"),
        "thumbnail": ("media_thumbnail", "thumbnail", "image"),
        "bubble": ("row_content", "message_container", "message_row", "row_content_frame"),
        "status": ("status", "message_status"), "text": ("message_text",),
        "document": ("document_filename", "document_name"),
        "audio": ("audio_seekbar", "audio_play", "audio_play_pause", "audio_title"),
        "video": ("video_duration", "video_play"),
        "image": ("image", "thumbnail", "media_thumbnail"),
        "pending": ("progress", "progress_bar", "media_upload_progress", "clock"),
    }
    LABELS = {
        "es": {
            "gallery": ("Galería",), "document": ("Documento",), "audio": ("Audio",),
            "albums": ("Álbumes", "Todas las fotos"),
            "browse": ("Buscar otros documentos", "Explorar otros documentos"),
            "search": ("Buscar",), "contact_info": ("Ver contacto", "Info. del contacto"),
            "drawer": ("Mostrar raíces", "Mostrar ubicaciones"), "downloads": ("Descargas",),
            "invalid": ("El número de teléfono no está en WhatsApp", "Invitar a WhatsApp"),
            "sent": ("Enviado", "Entregado", "Leído", "Leída"),
            "pending": ("Pendiente", "Enviando", "Reloj"),
            "allow": ("Permitir", "Permitir todo", "Permitir todas las fotos", "Permitir todas las fotos y videos",
                      "Permitir todas las fotos y vídeos", "Mientras se usa la app"),
            "send": ("Enviar",),
        },
        "en": {
            "gallery": ("Gallery",), "document": ("Document",), "audio": ("Audio",),
            "albums": ("Albums", "All photos"), "browse": ("Browse other docs", "Browse other documents"),
            "search": ("Search",), "contact_info": ("View contact", "Contact info"),
            "drawer": ("Show roots",), "downloads": ("Downloads",),
            "invalid": ("Phone number isn't on WhatsApp", "Invite to WhatsApp"),
            "sent": ("Sent", "Delivered", "Read"), "pending": ("Pending", "Sending", "Clock"),
            "allow": ("Allow", "Allow all", "Allow all photos", "Allow all photos and videos", "While using the app"),
            "send": ("Send",),
        },
    }
    ANDROID_IDS = {
        "search": ("com.android.documentsui:id/option_menu_search", "com.google.android.documentsui:id/option_menu_search"),
        "search_input": ("android:id/search_src_text",),
        "permission": ("com.android.permissioncontroller:id/permission_allow_button",
                       "com.android.permissioncontroller:id/permission_allow_all_button",
                       "com.android.permissioncontroller:id/permission_allow_foreground_only_button"),
        "audio_confirm": ("android:id/button1",),
        "invalid_notice": ("android:id/message",),
    }
    CONTAINS = {
        "es": {"invalid": ("no está en WhatsApp", "no es válido")},
        "en": {"invalid": ("isn't on WhatsApp", "not on WhatsApp", "shared via url is invalid")},
    }

    def __init__(self, package, language):
        self.package, self.labels = package, self.LABELS[language]
        self.contains = self.CONTAINS[language]

    def locators(self, key):
        result = [(AppiumBy.ID, self.package + ":id/" + value) for value in self.IDS.get(key, ())]
        result += [(AppiumBy.ID, value) for value in self.ANDROID_IDS.get(key, ())]
        for value in self.labels.get(key, ()):
            result += [(AppiumBy.ACCESSIBILITY_ID, value), self.text(value)]
        for value in self.contains.get(key, ()):
            result.append((AppiumBy.ANDROID_UIAUTOMATOR,
                           "new UiSelector().textContains(" + json.dumps(value, ensure_ascii=False) + ")"))
        return result

    @staticmethod
    def text(value):
        return AppiumBy.ANDROID_UIAUTOMATOR, "new UiSelector().text(" + json.dumps(value, ensure_ascii=False) + ")"

    @staticmethod
    def scroll_text(value):
        target = "new UiSelector().text(" + json.dumps(value, ensure_ascii=False) + ")"
        return AppiumBy.ANDROID_UIAUTOMATOR, (
            "new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(" + target + ")"
        )

    def matches_id(self, node, key):
        return node.get("resource-id", "") in {self.package + ":id/" + v for v in self.IDS[key]}

    def invalid_notice(self, xml):
        from xml.etree import ElementTree as ET
        notices = {value for by, value in self.locators("invalid_notice") if by == AppiumBy.ID}
        labels = [value.casefold() for value in self.labels["invalid"] + self.contains["invalid"]]
        for node in ET.fromstring(xml).iter():
            if node.get("resource-id") in notices:
                content = (node.get("text", "") + " " + node.get("content-desc", "")).casefold()
                if any(label in content for label in labels):
                    return True
        return False
