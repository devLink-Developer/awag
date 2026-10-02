from contextlib import nullcontext
from unittest.mock import Mock

from app.events.dispatcher import publish_pending
from app.messages.service import create_message
from app.models.entities import MessageStatus, Outbox
from app.schemas.contracts import MessageCreate
from app.services.errors import GatewayError
from app.workers.processor import MessageProcessor


def setup_processor(db, instance, settings, automation, lease=None):
    lease = lease or Mock(spec=["assert_owned"])
    automation.evidence.return_value = {}
    processor = MessageProcessor(lambda: nullcontext(db), lambda _: nullcontext(lease),
                                 lambda *_: automation, settings)
    message, _ = create_message(db, instance.id, MessageCreate(to="+5491112345678", text="QA"))
    return processor, message, lease


def test_database_failure_after_verified_click(db, instance, settings, monkeypatch):
    automation = Mock()
    automation.send.side_effect = lambda m, media, callback: callback()
    processor, message, _ = setup_processor(db, instance, settings, automation)
    commit = db.commit
    failed_once = False
    def failing_commit():
        nonlocal failed_once
        if message.status == MessageStatus.SENT and not failed_once:
            failed_once = True
            raise OSError("database temporarily unavailable")
        commit()
    monkeypatch.setattr(db, "commit", failing_commit)
    assert processor.run(message.id) == "FAILED"
    assert message.error == "SEND_OUTCOME_UNKNOWN"
    assert processor.run(message.id) == "IGNORED"
    assert automation.send.call_count == 1


def test_database_failure_before_marker_blocks_click(db, instance, settings, monkeypatch):
    click = Mock()
    automation = Mock()
    def send(m, media, callback):
        callback()
        click()
    automation.send.side_effect = send
    processor, message, _ = setup_processor(db, instance, settings, automation)
    commit = db.commit
    def failing_commit():
        if message.send_started_at:
            raise OSError("cannot persist marker")
        commit()
    monkeypatch.setattr(db, "commit", failing_commit)
    assert processor.run(message.id) == "FAILED"
    click.assert_not_called()
    assert message.send_started_at is None
    assert message.error == "AUTOMATION_ERROR"


def test_lost_lease_does_not_touch_successor(db, instance, settings):
    automation = Mock()
    processor, message, lease = setup_processor(db, instance, settings, automation)
    def send(m, media, callback):
        callback()
        lease.assert_owned.side_effect = GatewayError("LOCK_LOST")
        raise GatewayError("LOCK_LOST")
    automation.send.side_effect = send
    assert processor.run(message.id) == "DEFERRED"
    automation.close.assert_not_called()
    assert message.status == MessageStatus.PROCESSING
    assert message.send_started_at is not None


def test_outbox_publication_rollback(db, instance):
    message, _ = create_message(db, instance.id, MessageCreate(to="+5491112345678", text="QA"))
    from sqlalchemy import select
    row = db.scalar(select(Outbox))
    def publisher(_):
        raise OSError("Redis down")
    try:
        publish_pending(db, publisher)
    except OSError:
        db.rollback()
    db.refresh(row)
    assert row.published_at is None
    assert message.status == MessageStatus.QUEUED
