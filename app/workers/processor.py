import hashlib
import time
import uuid
from datetime import timedelta, timezone

from app.models.entities import Instance, InstanceStatus, Media, Message, MessageStatus, Outbox, utcnow
from app.services.errors import GatewayError
from app.services.logging import event


def older_than(value, seconds):
    return value is None or (utcnow() - value.replace(tzinfo=timezone.utc)).total_seconds() > seconds


def record_failure(db, message, code, retryable, settings, evidence=None):
    if message.send_started_at:
        evidence = {**(evidence or {}), "cause": code}
        code, retryable = "SEND_OUTCOME_UNKNOWN", False
    message.error = code
    message.evidence = evidence
    message.run_token = None
    if retryable and message.attempts < settings.max_attempts:
        message.status = MessageStatus.QUEUED
        db.add(Outbox(message_id=message.id, available_at=utcnow() + timedelta(
            seconds=5 * (3 ** max(0, message.attempts - 1)))))
    else:
        message.status = MessageStatus.FAILED
        message.completed_at = utcnow()
    db.commit()


class MessageProcessor:
    def __init__(self, session_factory, lease_factory, automation_factory, settings):
        self.sessions, self.leases, self.automations, self.settings = (
            session_factory, lease_factory, automation_factory, settings
        )

    def run(self, message_id):
        started = time.monotonic()
        with self.sessions() as db:
            message = db.get(Message, uuid.UUID(str(message_id)))
            if message is None or message.status in {MessageStatus.SENT, MessageStatus.FAILED}:
                return "IGNORED"
            instance = db.get(Instance, message.instance_id)
            try:
                with self.leases(instance.id) as lease:
                    db.refresh(message)
                    if message.status in {MessageStatus.SENT, MessageStatus.FAILED}:
                        return "IGNORED"
                    if message.status == MessageStatus.PROCESSING and not older_than(
                        message.updated_at, self.settings.stale_processing_seconds
                    ):
                        return "PROCESSING"
                    automation = None
                    token = uuid.uuid4().hex
                    instance.status = InstanceStatus.BUSY
                    message.run_token = token
                    message.status = MessageStatus.PROCESSING
                    message.started_at = message.started_at or utcnow()
                    exhausted = message.attempts >= self.settings.max_attempts
                    if not message.send_started_at and not exhausted:
                        message.attempts += 1
                    db.commit()

                    def session_changed(session_id):
                        lease.assert_owned()
                        instance.appium_session_id = session_id
                        db.commit()

                    def before_send():
                        lease.assert_owned()
                        db.refresh(message)
                        if message.run_token != token or message.send_started_at:
                            raise GatewayError("SEND_GUARD_REJECTED")
                        message.send_started_at = utcnow()
                        db.commit()
                        # A failed commit raises before any irreversible UI action.
                        lease.assert_owned()

                    try:
                        automation = self.automations(instance, lease, session_changed)
                        automation.recover()
                        if message.send_started_at:
                            raise GatewayError("SEND_OUTCOME_UNKNOWN")
                        if exhausted:
                            raise GatewayError("RETRY_EXHAUSTED")
                        message.error = None
                        db.commit()
                        media = db.get(Media, message.media_id) if message.media_id else None
                        if media:
                            path = self.settings.media_dir / media.storage_name
                            if not path.is_file():
                                raise GatewayError("MEDIA_FILE_MISSING")
                            with path.open("rb") as src:
                                if hashlib.file_digest(src, "sha256").hexdigest() != media.sha256:
                                    raise GatewayError("MEDIA_INTEGRITY_ERROR")
                        automation.send(message, media, before_send)
                        lease.assert_owned()
                        db.refresh(message)
                        if message.run_token != token:
                            raise GatewayError("RUN_OWNERSHIP_LOST")
                        if message.send_started_at is None:
                            raise GatewayError("SEND_NOT_ATTEMPTED")
                        message.status = MessageStatus.SENT
                        message.error = None
                        message.run_token = None
                        message.completed_at = utcnow()
                        db.commit()
                        event("send", "SENT", instance_id=instance.id, message_id=message.id,
                              duration_ms=round((time.monotonic() - started) * 1000))
                    except Exception as error:
                        db.rollback()
                        lease.assert_owned()
                        db.refresh(message)
                        if message.run_token != token:
                            raise GatewayError("RUN_OWNERSHIP_LOST") from None
                        code = error.code if isinstance(error, GatewayError) else "AUTOMATION_ERROR"
                        retryable = isinstance(error, GatewayError) and error.retryable
                        evidence = {"capture_error": "AUTOMATION_UNAVAILABLE"}
                        if automation:
                            try:
                                evidence = automation.evidence(message.id)
                            except Exception:
                                evidence = {"capture_error": "EVIDENCE_CAPTURE_FAILED"}
                        record_failure(db, message, code, retryable, self.settings, evidence)
                        event("send", message.status.value, instance_id=instance.id, message_id=message.id,
                              error=message.error, duration_ms=round((time.monotonic() - started) * 1000))
                    finally:
                        try:
                            lease.assert_owned()
                        except GatewayError:
                            # A stale worker must not change UI or status owned by its successor.
                            event("close_session", "DEFERRED", error="LOCK_LOST")
                        else:
                            if automation:
                                try:
                                    automation.close()
                                except Exception:
                                    db.rollback()
                                    lease.assert_owned()
                                    instance.status = InstanceStatus.ERROR
                                    db.commit()
                                    event("close_session", "FAILED", instance_id=instance.id,
                                          error="SESSION_CLEANUP_FAILED")
                            if instance.status == InstanceStatus.BUSY:
                                instance.status = InstanceStatus.ONLINE
                                db.commit()
                    return message.status.value
            except GatewayError as error:
                # Durable outbox recovery handles busy or lost leases. Never resend after a marker.
                event("worker", "DEFERRED", instance_id=instance.id, message_id=message.id, error=error.code)
                return "DEFERRED"
