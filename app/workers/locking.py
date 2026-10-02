import hashlib
import threading
import uuid

from sqlalchemy import text

from app.services.errors import GatewayError

RENEW = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""
RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class InstanceLease:
    """Redis lease plus a dedicated PostgreSQL session lock. Never fall back on Redis failure."""

    def __init__(self, redis, engine, instance_id, settings):
        self.redis, self.engine, self.settings = redis, engine, settings
        self.key = f"whatsapp:instance:{instance_id}:lock"
        self.token = uuid.uuid4().hex
        self.advisory_id = int.from_bytes(hashlib.sha256(str(instance_id).encode()).digest()[:8], "big")
        self.advisory_id &= (1 << 63) - 1
        self.connection = None
        self.backend_pid = None
        self.stop = threading.Event()
        self.lost = threading.Event()
        self.thread = None
        self.acquired = False

    def __enter__(self):
        try:
            self.connection = self.engine.connect().execution_options(isolation_level="AUTOCOMMIT")
            locked = self.connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": self.advisory_id})
            if not locked:
                self.connection.close()
                self.connection = None
                raise GatewayError("INSTANCE_BUSY", 409, retryable=True)
            self.backend_pid = self.connection.scalar(text("SELECT pg_backend_pid()"))
            if not self.redis.set(self.key, self.token, nx=True, px=self.settings.lock_ttl_seconds * 1000):
                raise GatewayError("INSTANCE_BUSY", 409, retryable=True)
            self.acquired = True
            self.thread = threading.Thread(target=self._renew_loop, daemon=True)
            self.thread.start()
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def _renew_loop(self):
        while not self.stop.wait(self.settings.lock_renew_seconds):
            try:
                if not self.redis.eval(RENEW, 1, self.key, self.token, self.settings.lock_ttl_seconds * 1000):
                    self.lost.set()
                    return
            except Exception:
                self.lost.set()
                return

    def assert_owned(self):
        try:
            if self.lost.is_set() or not self.acquired:
                raise RuntimeError("lost")
            # Renewal before every command provides a complete bounded command window.
            if not self.redis.eval(RENEW, 1, self.key, self.token, self.settings.lock_ttl_seconds * 1000):
                raise RuntimeError("lost")
            if self.connection.invalidated or self.connection.scalar(text("SELECT pg_backend_pid()")) != (
                self.backend_pid
            ):
                raise RuntimeError("lost")
        except Exception:
            self.lost.set()
            raise GatewayError("LOCK_LOST", 503) from None

    def __exit__(self, *_):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)
        if self.acquired:
            try:
                self.redis.eval(RELEASE, 1, self.key, self.token)
            except Exception:
                pass
        if self.connection:
            try:
                self.connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self.advisory_id})
            except Exception:
                self.connection.invalidate()
            finally:
                self.connection.close()
        self.acquired = False
