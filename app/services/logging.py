import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        fields = {
            "timestamp": datetime.now(timezone.utc).isoformat(), "level": record.levelname,
            "instance_id": getattr(record, "instance_id", None),
            "message_id": getattr(record, "message_id", None),
            "operation": getattr(record, "operation", record.name),
            "duration_ms": getattr(record, "duration_ms", None),
            "result": getattr(record, "result", record.getMessage()),
            "error": getattr(record, "error", None),
        }
        return json.dumps(fields)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    # Driver exceptions and wire requests can contain message text or base64 media.
    for name in ["selenium", "urllib3", "httpx", "httpcore", "celery", "uvicorn.access"]:
        logging.getLogger(name).setLevel(logging.CRITICAL)


def event(operation, result, *, instance_id=None, message_id=None, error=None, duration_ms=None):
    logging.getLogger("gateway").info(result, extra={
        "operation": operation, "result": result,
        "instance_id": str(instance_id) if instance_id else None,
        "message_id": str(message_id) if message_id else None,
        "error": error, "duration_ms": duration_ms,
    })
