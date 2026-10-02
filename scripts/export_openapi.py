import json
from pathlib import Path

from app.config.settings import get_settings
from app.main import create_app


if __name__ == "__main__":
    settings = get_settings().model_copy(update={"debug_automation": True})
    schema = create_app(settings).openapi()
    schema["info"]["description"] += " Debug routes require DEBUG_AUTOMATION=true at runtime."
    Path("docs/openapi.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
