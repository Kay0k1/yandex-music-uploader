import os
from sqlalchemy import BigInteger, String, Integer, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@db:5432/your_database_name")
engine = create_async_engine(url=DATABASE_URL)

async_session = async_sessionmaker(engine)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    token: Mapped[str] = mapped_column(String, nullable=False)
    playlist_kind: Mapped[str] = mapped_column(String, nullable=False)
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    
    tracks: Mapped[list["Track"]] = relationship(back_populates="user", cascade="all, delete-orphan")
        
        
class Track(Base):
    __tablename__ = 'tracks'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String, nullable=False)
    
    user: Mapped["User"] = relationship(back_populates="tracks")

async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
