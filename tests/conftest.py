import os

os.environ.setdefault("API_TOKEN", "unit-tests-only-" + "x" * 32)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config.settings import get_settings
from app.models.entities import Base, Instance
from app.services.database import get_db


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def instance(db):
    obj = Instance(name="QA", adb_serial="emulator-5554", appium_url="http://127.0.0.1:4723")
    db.add(obj)
    db.commit()
    return obj


@pytest.fixture
def settings(tmp_path):
    return get_settings().model_copy(update={
        "incoming_dir": tmp_path / "incoming", "media_dir": tmp_path / "media",
        "screenshot_dir": tmp_path / "screenshots",
    })


@pytest.fixture
def client(db, settings):
    from app.main import create_app
    api = create_app()
    api.dependency_overrides[get_db] = lambda: db
    api.dependency_overrides[get_settings] = lambda: settings
    with TestClient(api) as value:
        value.headers["Authorization"] = "Bearer " + settings.api_token.get_secret_value()
        yield value
