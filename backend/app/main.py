"""FastAPI application factory.

Run in development:
    uvicorn backend.app.main:create_app --factory --reload --port 8000
"""
import logging
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from backend.app.api import auth, catalog, evaluate, mars, missions, runs
from backend.app.config import Settings
from backend.app.container import build_container
from backend.app.errors import ApiError

log = logging.getLogger("space_mission")
API_PREFIX = "/api/v1"

def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Space Mission Design Game API", version="0.2.0")
    app.state.container = build_container(settings)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        field = ".".join(str(p) for p in first.get("loc", ()) if p != "body") or None
        return JSONResponse(status_code=422, content={"error": {
            "code": "invalid_request", "message": first.get("msg", "Invalid request."), "field": field}})

    @app.exception_handler(Exception)
    async def internal_error(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content={"error": {
            "code": "internal_error", "message": "Something went wrong on the server.", "field": None}})

    # Earth-observation routes are preserved; the Mars rover API is additive.
    for module in (catalog, evaluate, auth, missions, runs, mars):
        app.include_router(module.router, prefix=API_PREFIX)

    if settings.frontend_dist and settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    return app
