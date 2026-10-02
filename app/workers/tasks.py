import base64
import json
import uuid
from datetime import timedelta

from redis import Redis
from sqlalchemy import select

from app.automation.whatsapp import WhatsAppAutomation
from app.config.settings import get_settings
from app.models.entities import Instance, InstanceStatus, Message, MessageStatus, utcnow
from app.services.database import get_engine, session_factory
from app.services.errors import GatewayError
from app.services.logging import configure_logging, event
from app.workers.celery_app import celery
from app.workers.locking import InstanceLease
from app.workers.processor import MessageProcessor


def dependencies():
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)
    sessions = session_factory()
    def leases(uid):
        return InstanceLease(redis, get_engine(), uid, settings)
    def automations(instance, lease, callback):
        return WhatsAppAutomation(instance, settings, lease, callback)
    return settings, redis, sessions, leases, automations


@celery.task(name="gateway.send_message")
def send_message(message_id):
    configure_logging()
    settings, redis, sessions, leases, automations = dependencies()
    try:
        return MessageProcessor(sessions, leases, automations, settings).run(message_id)
    except Exception:
        # No raw task arguments or driver exception strings in Celery error output.
        event("worker", "FAILED", message_id=message_id, error="WORKER_OPERATION_FAILED")
        return "DEFERRED"
    finally:
        redis.close()


@celery.task(name="gateway.check_health")
def check_health(instance_id):
    configure_logging()
    settings, redis, sessions, leases, automations = dependencies()
    try:
        with sessions() as db:
            instance = db.get(Instance, uuid.UUID(instance_id))
            if instance is None:
                return
            active = db.scalar(select(Message.id).where(
                Message.instance_id == instance.id, Message.status == MessageStatus.PROCESSING,
                Message.updated_at > utcnow() - timedelta(seconds=settings.stale_processing_seconds)))
            if active:
                return
            with leases(instance.id) as lease:
                checks = {"adb_available": False, "device_visible": False, "boot_completed": False,
                          "appium_accessible": False, "whatsapp_installed": False,
                          "whatsapp_executable": False, "whatsapp_state": "UNKNOWN",
                          "ui_language": settings.ui_language}
                def callback(session_id):
                    instance.appium_session_id = session_id
                    db.commit()
                automation = automations(instance, lease, callback)
                state = InstanceStatus.OFFLINE
                try:
                    checks["appium_accessible"] = automation.session.available()
                    checks["adb_available"] = automation.device.is_adb_available()
                    checks["device_visible"] = automation.device.is_connected()
                    state = InstanceStatus.BOOTING
                    checks["boot_completed"] = automation.device.shell("getprop", "sys.boot_completed") == "1"
                    if checks["boot_completed"]:
                        state = InstanceStatus.ONLINE
                        checks["whatsapp_installed"] = settings.whatsapp_package in automation.device.list_packages()
                        if not checks["whatsapp_installed"]:
                            checks["whatsapp_state"] = "WHATSAPP_NOT_INSTALLED"
                        elif checks["appium_accessible"]:
                            automation.recover()
                            automation.open()
                            checks["whatsapp_executable"] = True
                            checks["whatsapp_state"] = "WHATSAPP_READY"
                            state = InstanceStatus.WHATSAPP_READY
                except GatewayError as error:
                    checks["error"] = error.code
                    if error.code == "WHATSAPP_NOT_CONFIGURED":
                        checks["whatsapp_executable"] = True
                        checks["whatsapp_state"] = error.code
                    elif error.code not in {"ADB_UNAVAILABLE", "ADB_COMMAND_FAILED"}:
                        state = InstanceStatus.ERROR
                except Exception:
                    checks["error"] = "HEALTH_CHECK_FAILED"
                    state = InstanceStatus.ERROR
                finally:
                    try:
                        automation.close()
                    except Exception:
                        checks["cleanup_error"] = "SESSION_CLEANUP_FAILED"
                        state = InstanceStatus.ERROR
                lease.assert_owned()
                instance.health = checks
                instance.health_checked_at = utcnow()
                instance.status = state
                db.commit()
    except GatewayError as error:
        if error.code != "INSTANCE_BUSY":
            event("health", "DEFERRED", instance_id=instance_id, error=error.code)
    except Exception:
        event("health", "FAILED", instance_id=instance_id, error="HEALTH_UNAVAILABLE")
    finally:
        redis.close()


@celery.task(name="gateway.debug_capture")
def debug_capture(instance_id, operation, request_id):
    settings, redis, sessions, leases, automations = dependencies()
    if not settings.debug_automation or operation not in {"screenshot", "activity"}:
        return
    request_key = "whatsapp:debug:request:" + request_id
    response_key = "whatsapp:debug:response:" + request_id
    try:
        # A timed-out HTTP request must not cause delayed UI interaction.
        if not redis.get(request_key):
            return
        with sessions() as db:
            instance = db.get(Instance, uuid.UUID(instance_id))
            with leases(instance.id) as lease:
                if not redis.get(request_key):
                    return
                from app.automation.adb import AndroidDevice
                device = AndroidDevice(settings, instance.adb_serial, lease.assert_owned)
                data = (base64.b64encode(device.screenshot()).decode() if operation == "screenshot"
                        else device.current_activity())
                redis.set(response_key, json.dumps({"data": data}), ex=settings.debug_timeout_seconds)
    except GatewayError as error:
        redis.set(response_key, json.dumps({"error": error.code}), ex=settings.debug_timeout_seconds)
    except Exception:
        try:
            redis.set(response_key, json.dumps({"error": "DEBUG_CAPTURE_FAILED"}),
                      ex=settings.debug_timeout_seconds)
        except Exception:
            pass
    finally:
        redis.close()
