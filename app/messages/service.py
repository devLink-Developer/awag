import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.entities import Instance, Media, Message, Outbox
from app.services.errors import GatewayError


def create_message(db, instance_id, request, key=None):
    if key is not None and (not key.strip() or len(key) > 200):
        raise GatewayError("INVALID_IDEMPOTENCY_KEY")
    if db.get(Instance, instance_id) is None:
        raise GatewayError("INSTANCE_NOT_FOUND", 404)
    if request.media_id:
        media = db.get(Media, request.media_id)
        if media is None:
            raise GatewayError("MEDIA_NOT_FOUND", 404)
        if media.type != request.type:
            raise GatewayError("MEDIA_TYPE_MISMATCH")
    payload_hash = hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True,
                                             ensure_ascii=False).encode()).hexdigest()

    def previous():
        existing = db.scalar(select(Message).where(Message.instance_id == instance_id,
                                                   Message.idempotency_key == key))
        if existing and existing.payload_hash != payload_hash:
            raise GatewayError("IDEMPOTENCY_CONFLICT", 409)
        return existing

    if key and (existing := previous()):
        return existing, False
    message = Message(instance_id=instance_id, recipient=request.to, type=request.type,
                      text=request.text, media_id=request.media_id,
                      idempotency_key=key, payload_hash=payload_hash)
    db.add(message)
    try:
        db.flush()
        db.add(Outbox(message_id=message.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        if key and (existing := previous()):
            return existing, False
        raise
    return message, True
