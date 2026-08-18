import os
import secrets
import base64
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen


def create_app():
    try:
        from fastapi import FastAPI
        from fastapi import Request
        from fastapi.responses import FileResponse
        from fastapi.responses import JSONResponse
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

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        detail = "Server error while processing the request. Check Vercel runtime logs."
        if os.environ.get("DEBUG_ERRORS") == "1":
            detail = f"Server error: {type(exc).__name__}: {exc}"
        return JSONResponse(
            status_code=500,
            content={"detail": detail},
        )

    @app.middleware("http")
    async def require_private_login(request: Request, call_next):
        supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY")
        supabase_auth_enabled = bool(supabase_url and supabase_anon_key)
        username = os.environ.get("APP_USERNAME")
        password = os.environ.get("APP_PASSWORD")
        is_vercel = bool(os.environ.get("VERCEL"))
        public_path = (
            request.url.path == "/"
            or request.url.path == "/health"
            or request.url.path == "/auth/config"
            or request.url.path.startswith("/static/")
        )

        if public_path:
            return await call_next(request)

        if supabase_auth_enabled:
            allowed_emails = {
                email.strip().lower()
                for email in os.environ.get("ALLOWED_EMAILS", "").split(",")
                if email.strip()
            }
            if is_vercel and not allowed_emails:
                return PlainTextResponse(
                    "PreciseHub is locked because ALLOWED_EMAILS is not configured.",
                    status_code=503,
                )

            auth_header = request.headers.get("authorization", "")
            token = auth_header.partition("Bearer ")[2]
            if not token:
                return PlainTextResponse("Login required.", status_code=401)

            user = _supabase_user(supabase_url, supabase_anon_key, token)
            if user is None:
                return PlainTextResponse("Invalid login session.", status_code=401)

            user_email = (user.get("email") or "").lower()
            if allowed_emails and user_email not in allowed_emails:
                return PlainTextResponse("This email is not allowed to use PreciseHub.", status_code=403)

            if _jwt_aal(token) != "aal2":
                return PlainTextResponse("Multi-factor authentication is required.", status_code=403)

            request.state.user_email = user_email
            return await call_next(request)

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

    @app.get("/auth/config", include_in_schema=False)
    def auth_config() -> dict[str, str | bool]:
        supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
        return {
            "enabled": bool(supabase_url and supabase_anon_key),
            "supabase_url": supabase_url,
            "supabase_anon_key": supabase_anon_key,
        }

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


def _supabase_user(supabase_url: str, supabase_anon_key: str, token: str) -> dict | None:
    request = UrlRequest(
        f"{supabase_url}/auth/v1/user",
        headers={
            "apikey": supabase_anon_key,
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None


def _jwt_aal(token: str) -> str:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")))
        return decoded.get("aal", "aal1")
    except Exception:
        return "aal1"
