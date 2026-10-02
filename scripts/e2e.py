"""Real opt-in sending test. It deliberately sends six messages to --to."""
import argparse
import json
import threading
import time
import uuid
from pathlib import Path

import httpx
from dotenv import dotenv_values


def run_suite(base_url, token, recipient, incoming, language):
    from app.schemas.contracts import MessageCreate
    MessageCreate(to=recipient, text="Mensaje de prueba")
    run_id = uuid.uuid4().hex
    results = []
    stop = threading.Event()
    with httpx.Client(base_url=base_url, headers={"Authorization": "Bearer " + token}, timeout=20) as client:
        client.get("/health").raise_for_status()
        response = client.get("/api/v1/instances")
        response.raise_for_status()
        instances = response.json()
        if len(instances) != 1:
            raise RuntimeError("E2E requires exactly one registered instance")
        instance_id = instances[0]["id"]
        health = client.get(f"/api/v1/instances/{instance_id}/health").json()
        if health["stale"] or health["status"] != "WHATSAPP_READY":
            raise RuntimeError("Wait for fresh WHATSAPP_READY before E2E")
        if health.get("checks", {}).get("ui_language") != language:
            raise RuntimeError("Worker UI_LANGUAGE does not match --language")
        prefix = f"/api/v1/instances/{instance_id}/messages"
        for index, kind in enumerate(["text", "text", "image", "document", "audio", "video"]):
            body = {"to": recipient, "type": kind}
            if kind == "text":
                body["text"] = "Mensaje de prueba"
            else:
                names = {"image": "qa-image.png", "document": "qa-document.txt",
                         "audio": "qa-audio.mp3", "video": "qa-video.mp4"}
                if not (incoming / names[kind]).is_file():
                    raise RuntimeError("Run make_fixtures.py in the shared incoming folder first")
                registered = client.post("/api/v1/media", json={"filename": names[kind], "type": kind})
                registered.raise_for_status()
                body["media_id"] = registered.json()["id"]
                if kind != "audio":
                    body["text"] = "Adjunto de prueba " + run_id[:8]
            headers = {"Idempotency-Key": f"e2e-{run_id}-{index}"}
            created = client.post(prefix, json=body, headers=headers)
            created.raise_for_status()
            uid = created.json()["id"]
            repeated = client.post(prefix, json=body, headers=headers)
            repeated.raise_for_status()
            if repeated.json()["id"] != uid:
                raise AssertionError("Idempotency replay changed message id")
            deadline = time.monotonic() + 480
            while time.monotonic() < deadline:
                result = client.get("/api/v1/messages/" + uid)
                result.raise_for_status()
                state = result.json()
                if state["status"] in {"SENT", "FAILED"}:
                    break
                stop.wait(0.5)
            else:
                raise RuntimeError("E2E timed out while waiting for terminal state")
            results.append({"id": uid, "type": kind, "status": state["status"], "error": state["error"]})
            print(json.dumps(results[-1]))
            if state["status"] != "SENT":
                raise RuntimeError("E2E stopped on failure; inspect evidence before any manual resend")
    return {"run_id": run_id, "language": language, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", required=True)
    parser.add_argument("--language", choices=["es", "en"], required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--incoming-dir", type=Path, default=Path("data/incoming"))
    args = parser.parse_args()
    config = dotenv_values(".env")
    token = config.get("API_TOKEN")
    if not token:
        parser.error("Generate .env with API_TOKEN first")
    report = run_suite(args.base_url, token, args.to, args.incoming_dir, args.language)
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    (output / ("e2e-" + report["run_id"] + ".json")).write_text(json.dumps(report, indent=2))
