import asyncio
import base64
import json
import time
import uuid

from fastapi import APIRouter, Depends, Response
from redis.asyncio import Redis

from app.api.auth import authenticate
from app.api.routes import find
from app.config.settings import get_settings
from app.models.entities import Instance, InstanceStatus
from app.services.database import get_db
from app.services.errors import GatewayError

router = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticate)])


async def capture(instance_id, operation, db, settings):
    from app.workers.tasks import debug_capture
    instance = find(db, Instance, instance_id)
    if instance.status == InstanceStatus.BUSY:
        raise GatewayError("INSTANCE_BUSY", 409)
    request_id = uuid.uuid4().hex
    request_key = "whatsapp:debug:request:" + request_id
    response_key = "whatsapp:debug:response:" + request_id
    try:
        async with Redis.from_url(settings.redis_url, socket_timeout=2) as redis:
            if await redis.exists(f"whatsapp:instance:{instance_id}:lock"):
                raise GatewayError("INSTANCE_BUSY", 409)
            await redis.set(request_key, "1", ex=settings.debug_timeout_seconds)
            try:
                await asyncio.to_thread(debug_capture.apply_async, args=[str(instance_id), operation, request_id],
                                        expires=settings.debug_timeout_seconds, retry=False)
                deadline = time.monotonic() + settings.debug_timeout_seconds
                while time.monotonic() < deadline:
                    data = await redis.get(response_key)
                    if data:
                        value = json.loads(data)
                        if "error" in value:
                            raise GatewayError(value["error"], 409 if value["error"] == "INSTANCE_BUSY" else 503)
                        return value["data"]
                    await asyncio.sleep(0.1)
                raise GatewayError("DEBUG_TIMEOUT", 503)
            finally:
                await redis.delete(request_key, response_key)
    except GatewayError:
        raise
    except Exception:
        raise GatewayError("DEBUG_UNAVAILABLE", 503) from None


@router.get("/instances/{instance_id}/screenshot")
async def screenshot(instance_id: uuid.UUID, db=Depends(get_db), settings=Depends(get_settings)):
    data = await capture(instance_id, "screenshot", db, settings)
    return Response(base64.b64decode(data), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/instances/{instance_id}/activity")
async def activity(instance_id: uuid.UUID, db=Depends(get_db), settings=Depends(get_settings)):
    return {"activity": await capture(instance_id, "activity", db, settings)}
