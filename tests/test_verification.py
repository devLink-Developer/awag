import pytest

from app.automation.selectors import WhatsAppSelectors
from app.automation.verification import confirms_new_bubble, outgoing_bubbles
from app.models.entities import MessageType


def screen(kind="text", text="QA", status="Sent", count=1, pending=False):
    content = {
        "text": f'<node resource-id="com.whatsapp:id/message_text" text="{text}"/>',
        "document": '<node resource-id="com.whatsapp:id/document_filename" text="file.pdf"/>',
        "image": '<node resource-id="com.whatsapp:id/image"/>',
        "audio": '<node resource-id="com.whatsapp:id/audio_seekbar"/>',
        "video": '<node resource-id="com.whatsapp:id/image"/><node resource-id="com.whatsapp:id/video_duration"/>',
    }[kind]
    row = f'<node resource-id="com.whatsapp:id/row_content">{content}<node resource-id="com.whatsapp:id/status" content-desc="{status}"/>'
    if pending:
        row += '<node resource-id="com.whatsapp:id/media_upload_progress"/>'
    return "<hierarchy><node>" + (row + "</node>") * count + "</node></hierarchy>"


@pytest.mark.parametrize("language,status", [("en", "Sent"), ("es", "Enviado"), ("en", "Read")])
@pytest.mark.parametrize("kind", list(MessageType))
def test_new_confirmed_bubble(language, status, kind):
    selectors = WhatsAppSelectors("com.whatsapp", language)
    before = outgoing_bubbles(screen(kind.value, status=status), selectors)
    after = outgoing_bubbles(screen(kind.value, status=status, count=2), selectors)
    assert confirms_new_bubble(before, after, kind, "QA" if kind == MessageType.text else None, "file.pdf")
    assert not confirms_new_bubble(before, before, kind, "QA", "file.pdf")


@pytest.mark.parametrize("status,pending", [("Pending", False), ("Sent", True), ("", False)])
def test_click_or_pending_is_not_sent(status, pending):
    selectors = WhatsAppSelectors("com.whatsapp", "en")
    after = outgoing_bubbles(screen(status=status, pending=pending), selectors)
    assert not confirms_new_bubble([], after, MessageType.text, "QA")


def test_different_text_and_unknown_layout():
    selectors = WhatsAppSelectors("com.whatsapp", "en")
    after = outgoing_bubbles(screen(), selectors)
    assert not confirms_new_bubble([], after, MessageType.text, "other")
    assert outgoing_bubbles('<hierarchy><node text="QA"/></hierarchy>', selectors) == []
    unknown = screen().replace('resource-id="com.whatsapp:id/row_content"', '')
    assert outgoing_bubbles(unknown, selectors) == []
