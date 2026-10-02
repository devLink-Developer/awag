from datetime import timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from redis import Redis
from sqlalchemy import func, select, text

from app.api.auth import authenticate
from app.config.settings import get_settings
from app.messages.service import create_message
from app.models.entities import Instance, Media, Message, MessageStatus, utcnow
from app.schemas.contracts import (InstanceView, MediaRegister, MediaView, MessageAccepted,
                                  MessageCreate, MessageView)
from app.services.database import get_db, get_engine
from app.services.errors import GatewayError
from app.services.media import register_media

router = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticate)])
public = APIRouter()


def find(db, model, object_id):
    obj = db.get(model, object_id)
    if obj is None:
        raise GatewayError(model.__name__.upper() + "_NOT_FOUND", 404)
    return obj


@public.get("/health")
def health(settings=Depends(get_settings)):
    checks = {"api": True, "postgres": False, "redis": False}
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:
        pass
    try:
        with Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2) as redis:
            checks["redis"] = bool(redis.ping())
    except Exception:
        pass
    from fastapi.responses import JSONResponse
    return JSONResponse({"status": "ok" if all(checks.values()) else "degraded", "checks": checks},
                        status_code=200 if all(checks.values()) else 503)


@router.get("/instances", response_model=list[InstanceView])
def instances(db=Depends(get_db)):
    return db.scalars(select(Instance).order_by(Instance.created_at)).all()


@router.get("/instances/{instance_id}", response_model=InstanceView)
def instance(instance_id: UUID, db=Depends(get_db)):
    return find(db, Instance, instance_id)


@router.get("/instances/{instance_id}/status")
def status(instance_id: UUID, db=Depends(get_db)):
    obj = find(db, Instance, instance_id)
    return {"id": obj.id, "status": obj.status, "updated_at": obj.updated_at}


@router.get("/instances/{instance_id}/health")
def instance_health(instance_id: UUID, db=Depends(get_db), settings=Depends(get_settings)):
    obj = find(db, Instance, instance_id)
    checked = obj.health_checked_at
    stale = checked is None or (utcnow() - checked.replace(tzinfo=timezone.utc)).total_seconds() > (
        2 * settings.health_interval_seconds
    )
    return {"id": obj.id, "status": obj.status, "checks": obj.health, "checked_at": checked,
            "stale": stale, "source": "worker", "busy": obj.status.value == "BUSY"}


@router.post("/media", response_model=MediaView, status_code=201)
def register(request: MediaRegister, db=Depends(get_db), settings=Depends(get_settings)):
    return register_media(db, settings, request)


@router.get("/media/{media_id}", response_model=MediaView)
def media(media_id: UUID, db=Depends(get_db)):
    return find(db, Media, media_id)


@router.post("/instances/{instance_id}/messages", response_model=MessageAccepted, status_code=202)
def send(instance_id: UUID, request: MessageCreate, response: Response,
         idempotency_key: str | None = Header(None), db=Depends(get_db)):
    obj, created = create_message(db, instance_id, request, idempotency_key)
    response.status_code = 202 if created else 200
    return obj


@router.get("/messages/{message_id}", response_model=MessageView)
def message(message_id: UUID, db=Depends(get_db)):
    return find(db, Message, message_id)


@public.get("/metrics", dependencies=[Depends(authenticate)])
def metrics(db=Depends(get_db)):
    counts = dict(db.execute(select(Message.status, func.count()).group_by(Message.status)).all())
    lines = []
    for name, state, kind in [("messages_queued", MessageStatus.QUEUED, "gauge"),
                              ("messages_sent", MessageStatus.SENT, "counter"),
                              ("messages_failed", MessageStatus.FAILED, "counter")]:
        lines += [f"# TYPE {name} {kind}", f"{name} {counts.get(state, 0)}"]
    lines += ["# TYPE automation_duration_seconds summary"]
    durations = [(m.completed_at - m.started_at).total_seconds() for m in db.scalars(
        select(Message).where(Message.completed_at.is_not(None), Message.started_at.is_not(None))
    )]
    lines += [f"automation_duration_seconds_count {len(durations)}",
              f"automation_duration_seconds_sum {sum(durations)}", "# TYPE instance_status gauge"]
    for obj in db.scalars(select(Instance)):
        lines.append(f'instance_status{{instance_id="{obj.id}",status="{obj.status.value}"}} 1')
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
