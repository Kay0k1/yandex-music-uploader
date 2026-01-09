import os
from sqlalchemy import BigInteger, String, Integer, ForeignKey, Boolean, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine

db_url = os.getenv("DATABASE_URL")
engine = create_async_engine(url=db_url)

async_session = async_sessionmaker(engine)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    token: Mapped[str] = mapped_column(String, nullable=True)
    playlist_kind: Mapped[str] = mapped_column(String, nullable=True)
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    
    playlists: Mapped[list["Playlist"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    
    tracks: Mapped[list["Track"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Playlist(Base):
    __tablename__ = 'playlists'
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    
    kind: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=True)
#   visibility: Mapped[str] = mapped_column(String, nullable=False) TODO: add enums
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    user: Mapped["User"] = relationship(back_populates="playlists")
    
    __table_args__ = (
        Index(
            "ix_user_active_playlist",
            "user_id",
            unique=True,
            postgresql_where=(is_active == True) 
        ),
    )


class Track(Base):
    __tablename__ = 'tracks'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    artist: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    cover: Mapped[str] = mapped_column(String(256), nullable=True)
    
    user: Mapped["User"] = relationship(back_populates="tracks")

async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
