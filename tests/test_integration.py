import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from redis import Redis
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.events.dispatcher import publish_pending, repair_pending
from app.instances.service import bootstrap_instance
from app.messages.service import create_message
from app.models.entities import Message, MessageStatus, Outbox, utcnow
from app.schemas.contracts import MessageCreate
from app.services.errors import GatewayError
from app.workers.locking import InstanceLease, RELEASE
from app.workers.processor import MessageProcessor

pytestmark = pytest.mark.integration


@pytest.fixture
def pg(settings):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL and TEST_REDIS_URL for integration tests")
    admin = create_engine(url)
    schema = "qa_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": "-csearch_path=" + schema}, pool_size=10)
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield engine, sessionmaker(engine, expire_on_commit=False), config
    engine.dispose()
    with admin.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


@pytest.fixture
def redis():
    if not os.environ.get("TEST_REDIS_URL"):
        pytest.skip("Set TEST_REDIS_URL")
    client = Redis.from_url(os.environ["TEST_REDIS_URL"], socket_timeout=2)
    yield client
    client.close()


def test_migration_roundtrip(pg):
    engine, sessions, config = pg
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.check(config)
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 0


def test_concurrent_idempotency(pg, settings):
    _, sessions, _ = pg
    with sessions() as db:
        instance_id = bootstrap_instance(db, settings).id
    barrier = threading.Barrier(8)
    def create(_):
        with sessions() as db:
            barrier.wait(timeout=10)
            message, _ = create_message(db, instance_id, MessageCreate(to="+5491112345678", text="QA"), "same")
            return message.id
    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(create, range(8)))
    assert len(set(ids)) == 1
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 1
        assert db.scalar(select(func.count()).select_from(Outbox)) == 1


def test_publication_failure_and_duplicate(pg, settings):
    _, sessions, _ = pg
    published = []
    with sessions() as db:
        instance = bootstrap_instance(db, settings)
        message, _ = create_message(db, instance.id, MessageCreate(to="+5491112345678", text="QA"))
        def publish_then_crash(uid):
            published.append(uid)
            raise RuntimeError("crash after publication")
        with pytest.raises(RuntimeError):
            publish_pending(db, publish_then_crash)
        db.rollback()
        assert publish_pending(db, published.append) == 1
        assert published == [str(message.id), str(message.id)]
        assert publish_pending(db, published.append) == 0


def test_redis_expiry_does_not_bypass_postgres(pg, redis, settings):
    engine, _, _ = pg
    uid = uuid.uuid4()
    with InstanceLease(redis, engine, uid, settings) as first:
        first.stop.set()
        first.thread.join(timeout=3)
        redis.pexpire(first.key, 50)
        deadline = threading.Event()
        for _ in range(100):
            if not redis.exists(first.key):
                break
            deadline.wait(0.01)
        assert not redis.exists(first.key)
        with pytest.raises(GatewayError, match="INSTANCE_BUSY"):
            with InstanceLease(redis, engine, uid, settings):
                pytest.fail("Overlapping lease")
        with pytest.raises(GatewayError, match="LOCK_LOST"):
            first.assert_owned()
    with InstanceLease(redis, engine, uid, settings) as second:
        second.assert_owned()
        assert redis.eval(RELEASE, 1, second.key, first.token) == 0
        second.assert_owned()


def test_lost_redis_ownership(pg, redis, settings):
    engine, _, _ = pg
    with InstanceLease(redis, engine, uuid.uuid4(), settings) as lease:
        redis.set(lease.key, "another-owner", ex=5)
        with pytest.raises(GatewayError, match="LOCK_LOST"):
            lease.assert_owned()
    assert redis.get(lease.key) == b"another-owner"
    redis.delete(lease.key)


def test_real_worker_serialization(pg, redis, settings):
    engine, sessions, _ = pg
    with sessions() as db:
        instance = bootstrap_instance(db, settings)
        message, _ = create_message(db, instance.id, MessageCreate(to="+5491112345678", text="QA"))
        uid = message.id
    entered, finish = threading.Event(), threading.Event()
    automation = Mock()
    automation.evidence.return_value = {}
    def send(m, media, before):
        entered.set()
        assert finish.wait(timeout=10)
        before()
    automation.send.side_effect = send
    processor = MessageProcessor(sessions, lambda uid: InstanceLease(redis, engine, uid, settings),
                                 lambda *_: automation, settings)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(processor.run, uid)
        assert entered.wait(timeout=10)
        try:
            assert processor.run(uid) == "DEFERRED"
        finally:
            finish.set()
        assert first.result(timeout=10) == "SENT"
    assert automation.send.call_count == 1


def test_repair_is_rate_limited(pg, settings):
    _, sessions, _ = pg
    with sessions() as db:
        instance = bootstrap_instance(db, settings)
        message, _ = create_message(db, instance.id, MessageCreate(to="+5491112345678", text="QA"))
        publish_pending(db, lambda _: None)
        original = db.scalar(select(Outbox))
        original.published_at = utcnow() - timedelta(seconds=1000)
        message.status = MessageStatus.PROCESSING
        message.updated_at = utcnow() - timedelta(seconds=1000)
        db.commit()
        repair_pending(db, settings)
        assert publish_pending(db, lambda _: None) == 1
        repair_pending(db, settings)
        assert db.scalar(select(func.count()).select_from(Outbox)) == 2


def test_api_health_with_real_dependencies(pg, settings, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import routes
    from app.config.settings import get_settings
    from app.main import create_app
    engine, _, _ = pg
    actual_settings = settings.model_copy(update={"redis_url": os.environ["TEST_REDIS_URL"]})
    api = create_app(actual_settings)
    api.dependency_overrides[get_settings] = lambda: actual_settings
    monkeypatch.setattr(routes, "get_engine", lambda: engine)
    with TestClient(api) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["checks"] == {"api": True, "postgres": True, "redis": True}


def test_celery_transport_with_real_redis(redis):
    from celery import Celery
    queue = "qa_" + uuid.uuid4().hex
    uid = str(uuid.uuid4())
    celery = Celery("qa", broker=os.environ["TEST_REDIS_URL"])
    celery.conf.update(task_serializer="json", accept_content=["json"])
    try:
        celery.send_task("gateway.send_message", args=[uid], queue=queue, retry=False)
        with celery.connection_for_read() as connection:
            with connection.SimpleQueue(queue) as consumer:
                received = consumer.get(block=True, timeout=3)
                assert received.headers["task"] == "gateway.send_message"
                assert received.payload[0] == [uid]
                received.ack()
                consumer.queue.delete()
    finally:
        celery.close()
