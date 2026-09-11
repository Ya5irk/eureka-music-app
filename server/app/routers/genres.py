from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Genre
from app.schemas import GenreOut

router = APIRouter(tags=["genres"])


@router.get("/genres", response_model=list[GenreOut])
async def list_genres(db: AsyncSession = Depends(get_db)) -> list[Genre]:
    result = await db.execute(select(Genre).order_by(Genre.name))
    return list(result.scalars().all())
