"""
Database Configuration for FastAPI with async SQLAlchemy
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
import os

# Database URL - convert sqlite to async sqlite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./printke.db")

# For PostgreSQL in production:
# DATABASE_URL = "postgresql+asyncpg://user:password@localhost/printke"

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("FLASK_ENV") == "development",
    future=True
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
