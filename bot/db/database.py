"""
bot/db/database.py
Async database connection and session management
"""

import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
)

from .models import Base

logger = logging.getLogger(__name__)

# Global engine and session factory
engine: AsyncEngine = None
async_session: async_sessionmaker[AsyncSession] = None


async def init_database(database_url: str, echo: bool = False):
    """
    Initialize database connection and create tables.
    
    Args:
        database_url: PostgreSQL connection string (asyncpg format)
        echo: Whether to log SQL statements
    """
    global engine, async_session
    
    logger.info(f"Initializing database connection: {database_url.split('@')[1] if '@' in database_url else database_url}")
    
    # Create async engine
    engine = create_async_engine(
        database_url,
        echo=echo,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    
    # Create session factory
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    # Create tables (if they don't exist)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database initialized successfully")


async def close_database():
    """Close database connections"""
    global engine
    
    if engine:
        await engine.dispose()
        logger.info("Database connections closed")


@asynccontextmanager
async def get_session():
    """
    Get an async database session.
    
    Usage:
        async with get_session() as session:
            result = await session.execute(query)
    """
    if async_session is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    session = async_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()