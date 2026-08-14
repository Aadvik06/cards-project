from pathlib import Path


def create_app():
    try:
        from fastapi import FastAPI
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError(
            "FastAPI is required to run the HTTP API. Install backend/requirements.txt first."
        ) from exc

    from app.api.routes.recommendations import router as recommendations_router

    static_dir = Path(__file__).resolve().parent / "static"

    app = FastAPI(
        title="Travel Card Optimizer",
        version="0.1.0",
        description="Deterministic travel credit-card recommendation backend.",
    )
    app.include_router(recommendations_router)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
