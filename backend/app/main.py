import os
import secrets
from pathlib import Path


def create_app():
    try:
        from fastapi import FastAPI
        from fastapi import Request
        from fastapi.responses import FileResponse
        from fastapi.responses import PlainTextResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError(
            "FastAPI is required to run the HTTP API. Install backend/requirements.txt first."
        ) from exc

    from app.api.routes.recommendations import router as recommendations_router
    from app.api.dependencies import get_report_service
    from app.services.report_scheduler import start_monthly_report_scheduler

    static_dir = Path(__file__).resolve().parent / "static"

    app = FastAPI(
        title="Travel Card Optimizer",
        version="0.1.0",
        description="Deterministic travel credit-card recommendation backend.",
    )

    @app.middleware("http")
    async def require_private_login(request: Request, call_next):
        username = os.environ.get("APP_USERNAME")
        password = os.environ.get("APP_PASSWORD")
        is_vercel = bool(os.environ.get("VERCEL"))

        if not username or not password:
            if is_vercel:
                return PlainTextResponse(
                    "PreciseHub is locked because APP_USERNAME and APP_PASSWORD are not configured.",
                    status_code=503,
                )
            return await call_next(request)

        provided_username, provided_password = request.headers.get("authorization", "").partition("Basic ")[2], ""
        if provided_username:
            import base64

            try:
                decoded = base64.b64decode(provided_username).decode("utf-8")
                provided_username, _, provided_password = decoded.partition(":")
            except Exception:
                provided_username, provided_password = "", ""

        valid = (
            secrets.compare_digest(provided_username, username)
            and secrets.compare_digest(provided_password, password)
        )
        if not valid:
            return PlainTextResponse(
                "Login required.",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="PreciseHub"'},
            )

        return await call_next(request)

    app.include_router(recommendations_router)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.on_event("startup")
    def start_report_scheduler() -> None:
        if os.environ.get("VERCEL"):
            return
        app.state.report_scheduler_stop = start_monthly_report_scheduler(get_report_service())

    @app.on_event("shutdown")
    def stop_report_scheduler() -> None:
        stop_event = getattr(app.state, "report_scheduler_stop", None)
        if stop_event is not None:
            stop_event.set()

    return app
