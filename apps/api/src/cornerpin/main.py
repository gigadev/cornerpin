from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from cornerpin.core import accounts, storage
from cornerpin.core.auth import routes as auth_routes
from cornerpin.core.config import get_settings
from cornerpin.core.outbox import InProcessRunner
from cornerpin.listings import media_routes
from cornerpin.listings import routes as listings_routes
from cornerpin.notifications import handlers as notification_handlers

# Importing a module that defines outbox handlers registers them.
OUTBOX_HANDLER_MODULES = (notification_handlers, storage)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class Health(BaseModel):
    status: str


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    runner = InProcessRunner() if get_settings().outbox_runner == "inprocess" else None
    if runner:
        runner.start()
    yield
    if runner:
        runner.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Cornerpin API", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def reject_cross_origin_writes(  # pyright: ignore[reportUnusedFunction]
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Cookie-authenticated writes must come from the web origin. SameSite=Lax cookies
        already stop most cross-site posts; this closes the rest."""
        origin = request.headers.get("origin")
        if (
            request.method in UNSAFE_METHODS
            and origin is not None
            and origin != get_settings().web_origin
        ):
            return JSONResponse({"detail": "Cross-origin request refused"}, status_code=403)
        return await call_next(request)

    v1 = APIRouter(prefix="/v1")

    @v1.get("/health", tags=["meta"])
    def health() -> Health:  # pyright: ignore[reportUnusedFunction]
        return Health(status="ok")

    v1.include_router(auth_routes.router)
    v1.include_router(accounts.router)
    v1.include_router(listings_routes.router)
    v1.include_router(media_routes.router)
    app.include_router(v1)
    return app


app = create_app()
