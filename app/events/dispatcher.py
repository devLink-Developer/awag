import threading
from datetime import timedelta

from sqlalchemy import exists, select

from app.config.settings import get_settings
from app.instances.service import bootstrap_instance
from app.models.entities import Instance, Message, MessageStatus, Outbox, utcnow
from app.services.database import session_factory
from app.services.logging import configure_logging, event


def publish_pending(db, publish, batch=100):
    rows = db.scalars(select(Outbox).where(Outbox.published_at.is_(None), Outbox.available_at <= utcnow())
                      .order_by(Outbox.created_at).limit(batch).with_for_update(skip_locked=True)).all()
    for row in rows:
        publish(str(row.message_id))
        row.published_at = utcnow()
    db.commit()
    return len(rows)


def repair_pending(db, settings):
    queued_cutoff = utcnow() - timedelta(seconds=settings.stale_processing_seconds)
    pending_outbox = exists(select(Outbox.id).where(Outbox.message_id == Message.id,
                                                   Outbox.published_at.is_(None)))
    recently_published = exists(select(Outbox.id).where(
        Outbox.message_id == Message.id,
        Outbox.published_at > utcnow() - timedelta(seconds=settings.health_interval_seconds)))
    rows = db.scalars(select(Message).where(
        Message.status.in_([MessageStatus.QUEUED, MessageStatus.PROCESSING]),
        Message.updated_at < queued_cutoff, ~pending_outbox, ~recently_published,
    ).with_for_update(skip_locked=True)).all()
    for message in rows:
        db.add(Outbox(message_id=message.id))
        # Do not touch message.updated_at: it identifies interrupted attempts.
    db.commit()


def main():
    import signal
    from app.workers.tasks import check_health, send_message
    settings = get_settings()
    configure_logging()
    sessions = session_factory()
    with sessions() as db:
        bootstrap_instance(db, settings)
    stop = threading.Event()
    for sig in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, lambda *_: stop.set())
    last_health = utcnow() - timedelta(seconds=settings.health_interval_seconds)
    while not stop.is_set():
        try:
            with sessions() as db:
                repair_pending(db, settings)
                publish_pending(db, lambda uid: send_message.apply_async(args=[uid], retry=False))
                if (utcnow() - last_health).total_seconds() >= settings.health_interval_seconds:
                    for instance in db.scalars(select(Instance)):
                        check_health.apply_async(args=[str(instance.id)], expires=settings.health_interval_seconds,
                                                 retry=False)
                    last_health = utcnow()
        except Exception:
            event("dispatch", "FAILED", error="DISPATCH_UNAVAILABLE")
        stop.wait(1)


if __name__ == "__main__":
    main()
