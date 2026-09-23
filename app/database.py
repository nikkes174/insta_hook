from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import Settings


class Base(DeclarativeBase):
    pass


def create_database(settings: Settings):
    engine = create_async_engine(settings.database_url, future=True)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db(engine) -> None:
    from .models import ProcessedComment
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
