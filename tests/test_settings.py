import pytest
from pydantic import ValidationError

from app.config.settings import Settings


def test_startup_validation_cannot_print_credentials():
    with pytest.raises(ValidationError) as caught:
        Settings(api_token="short-secret", database_url="postgresql://user:private-password@localhost/db")
    diagnostic = str(caught.value)
    assert "API_TOKEN" in diagnostic
    assert "short-secret" not in diagnostic
    assert "private-password" not in diagnostic
