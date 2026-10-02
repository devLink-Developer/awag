import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.entities import InstanceStatus, MessageStatus, MessageType


class Contract(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class MediaRegister(Contract):
    filename: str = Field(min_length=1, max_length=255)
    type: MessageType

    @model_validator(mode="after")
    def validate_type(self):
        if self.type == MessageType.text:
            raise ValueError("Files cannot have type text")
        return self


class MediaView(Contract):
    id: UUID
    type: MessageType
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class MessageCreate(Contract):
    to: str
    type: MessageType = MessageType.text
    text: str | None = None
    media_id: UUID | None = None

    @field_validator("to")
    @classmethod
    def phone(cls, value):
        if not re.fullmatch(r"\+[1-9][0-9]{6,14}", value):
            raise ValueError("Use an E.164 number")
        return value

    @model_validator(mode="after")
    def content(self):
        if self.type == MessageType.text:
            if self.media_id or not self.text or not self.text.strip() or len(self.text) > 4096:
                raise ValueError("Text messages require 1..4096 characters and no media")
        else:
            if not self.media_id:
                raise ValueError("Attachments require media_id")
            if self.type == MessageType.audio and self.text is not None:
                raise ValueError("Audio does not accept captions")
            if self.text is not None and (not self.text.strip() or len(self.text) > 1024):
                raise ValueError("Caption must contain 1..1024 characters")
        return self


class MessageAccepted(Contract):
    id: UUID
    status: MessageStatus


class MessageView(Contract):
    id: UUID
    instance_id: UUID
    recipient: str
    type: MessageType
    text: str | None
    media_id: UUID | None
    status: MessageStatus
    error: str | None
    attempts: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    evidence: dict | None


class InstanceView(Contract):
    id: UUID
    name: str
    adb_serial: str
    appium_url: str
    system_port: int
    status: InstanceStatus
    phone_number: str | None
    created_at: datetime
    updated_at: datetime
