import hashlib
import os

import pytest
from PIL import Image

from app.models.entities import MessageType
from app.schemas.contracts import MediaRegister
from app.services.errors import GatewayError
from app.services.media import register_media


def test_snapshot_and_image(client, settings, instance):
    settings.incoming_dir.mkdir()
    source = settings.incoming_dir / "foto.png"
    Image.new("RGB", (8, 8), "red").save(source)
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    response = client.post("/api/v1/media", json={"filename": "foto.png", "type": "image"})
    assert response.status_code == 201
    media = response.json()
    source.unlink()
    assert media["sha256"] == expected
    assert media["mime_type"] == "image/png"
    assert (settings.media_dir / (media["id"] + ".png")).exists()
    assert client.post(f"/api/v1/instances/{instance.id}/messages", json={
        "to": "+5491112345678", "type": "image", "media_id": media["id"], "text": "Foto",
    }).status_code == 202
    assert client.post(f"/api/v1/instances/{instance.id}/messages", json={
        "to": "+5491112345678", "type": "document", "media_id": media["id"],
    }).status_code == 422


@pytest.mark.parametrize("name", ["../file.txt", "x/y", "x\\y", "C:file.txt", ".", ".."])
def test_traversal(client, name):
    assert client.post("/api/v1/media", json={"filename": name, "type": "document"}).status_code == 422


def test_size_and_invalid(client, settings):
    settings.incoming_dir.mkdir()
    (settings.incoming_dir / "bad.png").write_bytes(b"not an image")
    assert client.post("/api/v1/media", json={"filename": "bad.png", "type": "image"}).status_code == 422
    settings.document_limit_bytes = 5
    assert client.post("/api/v1/media", json={"filename": "bad.png", "type": "document"}).status_code == 413
    assert not list(settings.media_dir.iterdir())
    assert client.post("/api/v1/media", json={"filename": "absent", "type": "document"}).status_code == 404


def test_symlink_rejected(db, settings):
    settings.incoming_dir.mkdir()
    target = settings.incoming_dir / "target.txt"
    target.write_text("test")
    try:
        os.symlink(target, settings.incoming_dir / "link.txt")
    except OSError:
        pytest.skip("Windows account cannot create symlinks")
    with pytest.raises(GatewayError, match="FILE_NOT_REGULAR"):
        register_media(db, settings, MediaRegister(filename="link.txt", type=MessageType.document))


def test_source_changes_during_copy(db, settings, monkeypatch):
    import app.services.media as media_module
    settings.incoming_dir.mkdir()
    source = settings.incoming_dir / "changing.txt"
    source.write_bytes(b"original")
    real_fstat = media_module.os.fstat
    calls = 0
    def changing_fstat(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            source.write_bytes(b"changed content")
        return real_fstat(fd)
    monkeypatch.setattr(media_module.os, "fstat", changing_fstat)
    with pytest.raises(GatewayError, match="FILE_CHANGED"):
        register_media(db, settings, MediaRegister(filename="changing.txt", type=MessageType.document))
    assert not list(settings.media_dir.iterdir())
