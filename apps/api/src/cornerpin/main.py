from fastapi import APIRouter, FastAPI
from pydantic import BaseModel


class Health(BaseModel):
    status: str


def create_app() -> FastAPI:
    app = FastAPI(title="Cornerpin API", version="0.1.0")
    v1 = APIRouter(prefix="/v1")

    @v1.get("/health", response_model=Health, tags=["meta"])
    def health() -> Health:  # pyright: ignore[reportUnusedFunction]
        return Health(status="ok")

    app.include_router(v1)
    return app


app = create_app()
