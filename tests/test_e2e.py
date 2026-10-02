import os
from pathlib import Path

import pytest

from scripts.e2e import run_suite


@pytest.mark.e2e
def test_authenticated_android():
    recipient = os.environ.get("E2E_RECIPIENT")
    if not recipient:
        pytest.skip("Set E2E_RECIPIENT only for an intentional real WhatsApp sending test")
    token = os.environ.get("E2E_API_TOKEN")
    assert token, "Set E2E_API_TOKEN"
    report = run_suite(os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000"), token, recipient,
                       Path(os.environ.get("E2E_INCOMING_DIR", "data/incoming")),
                       os.environ.get("E2E_LANGUAGE", "es"))
    assert len(report["results"]) == 6
