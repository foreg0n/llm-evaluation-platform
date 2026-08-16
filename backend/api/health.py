from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db_session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    database: str


@router.get("/health", response_model=HealthResponse)
async def health_check(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> HealthResponse:
    """Report readiness after verifying the database connection."""

    await session.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="reachable")
