import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


class InstanceStatus(str, enum.Enum):
    OFFLINE = "OFFLINE"
    BOOTING = "BOOTING"
    ONLINE = "ONLINE"
    WHATSAPP_READY = "WHATSAPP_READY"
    BUSY = "BUSY"
    ERROR = "ERROR"


class MessageStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    FAILED = "FAILED"


class MessageType(str, enum.Enum):
    text = "text"
    image = "image"
    document = "document"
    audio = "audio"
    video = "video"


def enum_type(cls):
    return Enum(cls, native_enum=False, create_constraint=True, name=cls.__name__.lower())


class Base(DeclarativeBase):
    pass


class Instance(Base):
    __tablename__ = "instances"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128))
    adb_serial: Mapped[str] = mapped_column(String(128), unique=True)
    appium_url: Mapped[str] = mapped_column(String(512))
    system_port: Mapped[int] = mapped_column(Integer, default=8200, unique=True)
    status: Mapped[InstanceStatus] = mapped_column(enum_type(InstanceStatus), default=InstanceStatus.OFFLINE)
    phone_number: Mapped[str | None] = mapped_column(String(32))
    health: Mapped[dict | None] = mapped_column(JSON)
    health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    appium_session_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Media(Base):
    __tablename__ = "media"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[MessageType] = mapped_column(enum_type(MessageType))
    original_name: Mapped[str] = mapped_column(String(255))
    storage_name: Mapped[str] = mapped_column(String(128), unique=True)
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("instance_id", "idempotency_key", name="uq_message_idempotency"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    instance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instances.id"), index=True)
    recipient: Mapped[str] = mapped_column(String(32))
    text: Mapped[str | None] = mapped_column(Text)
    type: Mapped[MessageType] = mapped_column(enum_type(MessageType), default=MessageType.text)
    media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media.id"))
    status: Mapped[MessageStatus] = mapped_column(enum_type(MessageStatus), default=MessageStatus.QUEUED, index=True)
    error: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_token: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    send_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict | None] = mapped_column(JSON)


class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), index=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
