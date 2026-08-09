import os
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


PUBLIC_PATHS = {
    "/health",
}


def _read_expected_token() -> str:
    token = os.getenv("OSIRIS_API_TOKEN", "").strip()

    if len(token) < 40:
        raise RuntimeError(
            "OSIRIS_API_TOKEN is missing or too short. "
            "Set a strong token in the local .env file."
        )

    return token


def _provided_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "").strip()

    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return request.headers.get("x-osiris-api-token", "").strip()


def install_api_auth(app: FastAPI) -> None:
    expected_token = _read_expected_token()

    @app.middleware("http")
    async def require_private_api_token(request: Request, call_next):
        normalized_path = request.url.path.rstrip("/") or "/"

        if request.method == "OPTIONS" or normalized_path in PUBLIC_PATHS:
            response = await call_next(request)
        else:
            provided_token = _provided_token(request)

            if not provided_token or not secrets.compare_digest(
                provided_token,
                expected_token,
            ):
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": "Private OSIRIS API token required."
                    },
                    headers={
                        "WWW-Authenticate": "Bearer",
                        "Cache-Control": "no-store",
                    },
                )

            response = await call_next(request)

        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response
