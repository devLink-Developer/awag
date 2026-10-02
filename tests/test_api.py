import uuid

import pytest
from sqlalchemy import func, select

from app.models.entities import Message, Outbox


def test_create_and_replay(client, instance, db):
    url = f"/api/v1/instances/{instance.id}/messages"
    body = {"to": "+5491112345678", "text": "Hola 😀\nQA"}
    first = client.post(url, json=body, headers={"Idempotency-Key": "qa-1"})
    second = client.post(url, json=body, headers={"Idempotency-Key": "qa-1"})
    assert first.status_code == 202
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["status"] == "QUEUED"
    assert db.scalar(select(func.count()).select_from(Message)) == 1
    assert db.scalar(select(func.count()).select_from(Outbox)) == 1
    assert client.get("/api/v1/messages/" + first.json()["id"]).json()["text"] == body["text"]
    assert client.post(url, json={**body, "text": "Otra cosa"},
                       headers={"Idempotency-Key": "qa-1"}).status_code == 409


@pytest.mark.parametrize("body", [
    {"to": "5491112345678", "text": "Hola"}, {"to": "+5491112345678", "text": " "},
    {"to": "+5491112345678", "text": "x" * 4097},
    {"to": "+5491112345678", "type": "image"},
    {"to": "+5491112345678", "type": "audio", "media_id": str(uuid.uuid4()), "text": "caption"},
    {"to": "+5491112345678", "text": "ok", "shell": "bad"},
])
def test_invalid_messages(client, instance, body):
    assert client.post(f"/api/v1/instances/{instance.id}/messages", json=body).status_code == 422


def test_auth_and_debug_disabled(client, instance):
    assert client.get("/api/v1/instances", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert client.get(f"/api/v1/instances/{instance.id}/screenshot").status_code == 404
    assert client.get(f"/api/v1/instances/{instance.id}/activity").status_code == 404
    assert client.get("/api/v1/instances").json()[0]["id"] == str(instance.id)
    assert client.get(f"/api/v1/instances/{instance.id}/health").json()["stale"]


def test_missing_objects(client):
    uid = uuid.uuid4()
    assert client.get(f"/api/v1/messages/{uid}").status_code == 404
    assert client.post(f"/api/v1/instances/{uid}/messages",
                       json={"to": "+5491112345678", "text": "QA"}).status_code == 404
