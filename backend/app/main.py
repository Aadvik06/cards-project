def create_app():
    try:
        from fastapi import FastAPI
    except ImportError as exc:
        raise RuntimeError(
            "FastAPI is required to run the HTTP API. Install backend/requirements.txt first."
        ) from exc

    from app.api.routes.recommendations import router as recommendations_router

    app = FastAPI(
        title="Travel Card Optimizer",
        version="0.1.0",
        description="Deterministic travel credit-card recommendation backend.",
    )
    app.include_router(recommendations_router)
    return app

