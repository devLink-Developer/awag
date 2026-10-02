from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import public, router
from app.config.settings import get_settings
from app.services.errors import GatewayError
from app.services.logging import configure_logging


def create_app(settings=None):
    settings = settings or get_settings()
    configure_logging()
    api = FastAPI(title="Android WhatsApp Automation Gateway", version="0.1.0",
                  description="Laboratorio QA: automatización de la aplicación oficial mediante Android.")

    @api.exception_handler(GatewayError)
    async def gateway_error(request: Request, error: GatewayError):
        return JSONResponse({"detail": {"code": error.code}}, status_code=error.status_code)

    api.include_router(public)
    api.include_router(router)
    if settings.debug_automation:
        from app.api.debug import router as debug_router
        api.include_router(debug_router)
    return api


app = create_app()
