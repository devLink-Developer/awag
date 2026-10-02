from contextlib import nullcontext
from datetime import timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.messages.service import create_message
from app.models.entities import MessageStatus, Outbox, utcnow
from app.schemas.contracts import MessageCreate
from app.services.errors import GatewayError
from app.workers.processor import MessageProcessor


def processor(db, instance, settings, automation):
    automation.evidence.return_value = {}
    lease = Mock(spec=["assert_owned"])
    p = MessageProcessor(lambda: nullcontext(db), lambda _: nullcontext(lease),
                         lambda *_: automation, settings)
    msg, _ = create_message(db, instance.id, MessageCreate(to="+5491112345678", text="QA"), "test")
    return p, msg, lease


def test_confirmed_and_duplicate(db, instance, settings):
    automation = Mock()
    automation.send.side_effect = lambda m, media, before: before()
    p, msg, _ = processor(db, instance, settings, automation)
    assert p.run(msg.id) == "SENT"
    assert msg.send_started_at
    assert p.run(msg.id) == "IGNORED"
    assert automation.send.call_count == 1
    assert msg.attempts == 1


def test_preclick_retry(db, instance, settings):
    automation = Mock()
    automation.send.side_effect = GatewayError("DEVICE_OFFLINE", retryable=True)
    automation.evidence.return_value = {"activity": "test"}
    p, msg, _ = processor(db, instance, settings, automation)
    assert p.run(msg.id) == "QUEUED"
    assert msg.send_started_at is None
    assert len(db.scalars(select(Outbox)).all()) == 2
    assert p.run(msg.id) == "QUEUED"
    assert p.run(msg.id) == "FAILED"
    assert msg.attempts == 3


@pytest.mark.parametrize("error", [GatewayError("TIMEOUT", retryable=True), RuntimeError("sensitive")])
def test_postclick_unknown(db, instance, settings, error):
    automation = Mock()
    def send(m, media, before):
        before()
        raise error
    automation.send.side_effect = send
    automation.evidence.side_effect = OSError("capture failed")
    p, msg, _ = processor(db, instance, settings, automation)
    assert p.run(msg.id) == "FAILED"
    assert msg.error == "SEND_OUTCOME_UNKNOWN"
    assert msg.evidence["capture_error"] == "EVIDENCE_CAPTURE_FAILED"
    assert msg.evidence["cause"] == (error.code if isinstance(error, GatewayError) else "AUTOMATION_ERROR")
    assert p.run(msg.id) == "IGNORED"


def test_recover_interrupted_send(db, instance, settings):
    automation = Mock()
    p, msg, _ = processor(db, instance, settings, automation)
    msg.status = MessageStatus.PROCESSING
    msg.send_started_at = utcnow()
    msg.updated_at = utcnow() - timedelta(seconds=settings.stale_processing_seconds + 1)
    db.commit()
    assert p.run(msg.id) == "FAILED"
    assert msg.error == "SEND_OUTCOME_UNKNOWN"
    automation.recover.assert_called_once()
    automation.send.assert_not_called()


def test_adapter_cannot_report_sent_without_persisted_marker(db, instance, settings):
    automation = Mock()
    p, msg, _ = processor(db, instance, settings, automation)
    assert p.run(msg.id) == "FAILED"
    assert msg.error == "SEND_NOT_ATTEMPTED"
    assert msg.send_started_at is None
