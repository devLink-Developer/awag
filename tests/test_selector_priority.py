from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.automation.whatsapp import WhatsAppAutomation
from app.services.errors import GatewayError


def automation(settings):
    instance = SimpleNamespace(adb_serial="emulator-5554")
    result = WhatsAppAutomation(instance, settings, Mock(spec=["assert_owned"]), Mock())
    result.driver = Mock()
    return result


def test_resource_id_wins_over_a_different_accessibility_element(settings):
    service = automation(settings)
    resource_id, accessibility = ("id", "send"), ("accessibility id", "Enviar")
    primary, fallback = Mock(), Mock()
    service.driver.find_elements.side_effect = lambda by, value: [primary] if by == "id" else [fallback]
    assert service._unique([resource_id, accessibility]) is primary
    assert service.driver.find_elements.call_count == 1


def test_ambiguous_primary_is_not_replaced_by_a_weaker_selector(settings):
    service = automation(settings)
    service.driver.find_elements.return_value = [Mock(), Mock()]
    with pytest.raises(GatewayError, match="SELECTOR_AMBIGUOUS"):
        service._unique([("id", "send"), ("accessibility id", "Enviar")])


def test_fallback_only_when_primary_is_absent(settings):
    service = automation(settings)
    fallback = Mock()
    service.driver.find_elements.side_effect = [[], [fallback]]
    assert service._unique([("id", "send"), ("accessibility id", "Enviar")]) is fallback


def test_chat_history_cannot_be_mistaken_for_an_invalid_recipient_notice(settings):
    service = automation(settings)
    message = '<hierarchy><node resource-id="com.whatsapp:id/message_text" text="El documento no es válido"/></hierarchy>'
    assert not service.selectors.invalid_notice(message)
    alert = '<hierarchy><node resource-id="android:id/message" text="El número compartido no es válido"/></hierarchy>'
    assert service.selectors.invalid_notice(alert)
