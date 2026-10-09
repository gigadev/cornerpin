from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from cornerpin.core import accounts, internal, storage
from cornerpin.core.auth import routes as auth_routes
from cornerpin.core.config import get_settings
from cornerpin.core.housekeeping import run_housekeeping
from cornerpin.core.internal import cloud_tasks_dispatcher
from cornerpin.core.outbox import InProcessRunner, set_dispatcher
from cornerpin.dashboard import routes as dashboard_routes
from cornerpin.decisioning import handlers as decisioning_handlers
from cornerpin.financing import buyer_routes as financing_buyer_routes
from cornerpin.financing import routes as financing_routes
from cornerpin.integrations import handlers as integration_handlers
from cornerpin.integrations import routes as integration_routes
from cornerpin.leads import buyer_routes, lead_routes, owner_routes
from cornerpin.listings import geometry_routes, media_routes, public_files, qr
from cornerpin.listings import routes as listings_routes
from cornerpin.listings.public_graphql import graphql_router
from cornerpin.notifications import handlers as notification_handlers
from cornerpin.notifications import prefs as notification_prefs
from cornerpin.notifications import push
from cornerpin.outreach import handlers as outreach_handlers
from cornerpin.outreach import routes as outreach_routes
from cornerpin.outreach import webhooks as outreach_webhooks

# Importing a module that defines outbox handlers registers them.
OUTBOX_HANDLER_MODULES = (
    notification_handlers,
    storage,
    outreach_handlers,
    integration_handlers,
    decisioning_handlers,
)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class Health(BaseModel):
    status: str


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    runner = None
    if settings.outbox_runner == "inprocess":
        runner = InProcessRunner(hourly=run_housekeeping)
        set_dispatcher(runner)
        runner.start()
    elif settings.outbox_runner == "cloudtasks":
        set_dispatcher(cloud_tasks_dispatcher())
    yield
    set_dispatcher(None)
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
    v1.include_router(geometry_routes.router)
    v1.include_router(public_files.router)
    v1.include_router(qr.router)
    v1.include_router(buyer_routes.router)
    v1.include_router(owner_routes.router)
    v1.include_router(lead_routes.router)
    v1.include_router(dashboard_routes.router)
    v1.include_router(financing_routes.router)
    v1.include_router(financing_buyer_routes.router)
    v1.include_router(notification_prefs.router)
    v1.include_router(push.router)
    v1.include_router(outreach_routes.router)
    v1.include_router(outreach_webhooks.router)
    v1.include_router(integration_routes.router)
    v1.include_router(integration_routes.hidden)
    app.include_router(v1)
    app.include_router(internal.router, include_in_schema=False)
    app.include_router(graphql_router(), prefix="/graphql", include_in_schema=False)
    return app


app = create_app()
