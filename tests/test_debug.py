from fastapi.testclient import TestClient

from app.config.settings import get_settings
from app.models.entities import InstanceStatus
from app.services.database import get_db


def test_debug_enabled_requires_auth_and_refuses_busy(db, instance, settings):
    from app.main import create_app
    enabled = settings.model_copy(update={"debug_automation": True})
    api = create_app(enabled)
    api.dependency_overrides[get_db] = lambda: db
    api.dependency_overrides[get_settings] = lambda: enabled
    instance.status = InstanceStatus.BUSY
    db.commit()
    with TestClient(api) as client:
        for suffix in ["screenshot", "activity"]:
            url = f"/api/v1/instances/{instance.id}/{suffix}"
            assert client.get(url).status_code == 401
            response = client.get(url, headers={"Authorization": "Bearer " + settings.api_token.get_secret_value()})
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "INSTANCE_BUSY"
