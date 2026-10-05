from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine

# Outside /api on purpose: Render's health check calls the service directly, without Vercel's
# origin-secret header.
router = APIRouter(tags=["probes"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    # Liveness only. Never touches the database, so a health check can't wake Neon or spend
    # its compute hours.
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> JSONResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            {"status": "unavailable"}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    return JSONResponse({"status": "ok"})
