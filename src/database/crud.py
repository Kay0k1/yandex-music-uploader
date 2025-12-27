from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, Track, Playlist

from typing import List


async def create_user(session: AsyncSession, tg_id: int) -> User:
    user = await get_user(session, tg_id)
    if user:
        return user

    user = User(tg_id=tg_id)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

async def get_user(session: AsyncSession, tg_id: int) -> User | None:
    query = select(User).where(User.tg_id == tg_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()

async def set_token(session: AsyncSession, tg_id: int, token: str) -> str:
    stmt = (
        update(User)
        .where(User.tg_id == tg_id)
        .values(token=token)
    )
    await session.execute(stmt)
    await session.commit()

async def get_token(session: AsyncSession, tg_id: int) -> str | None:
    query = select(User.token).where(User.tg_id == tg_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()

async def create_playlist(session: AsyncSession, tg_id: int, kind: str, title: str) -> Playlist:
    user = await get_user(session, tg_id)
    if not user:
        raise ValueError("User not found")

    await session.execute(
        update(Playlist).where(Playlist.user_id == user.id).values(is_active=False)
    )

    new_playlist = Playlist(user_id=user.id, kind=kind, title=title, is_active=False)
    session.add(new_playlist)
    await session.commit()
    await session.refresh(new_playlist)
    return new_playlist

async def get_user_playlists(session: AsyncSession, tg_id: int) -> List[Playlist]:
    query = (
        select(Playlist)
        .join(User)
        .where(User.tg_id == tg_id)
    )
    result = await session.execute(query)
    return result

async def get_active_playlist(session: AsyncSession, tg_id: int) -> Playlist | None:
    query = (
        select(Playlist)
        .join(User)
        .where(User.tg_id == tg_id, Playlist.is_active == True)
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()

async def update_playlist_title(session: AsyncSession, playlist_id: int, new_title: str) -> None:
    stmt = (
        update(Playlist)
        .where(Playlist.id == playlist_id)
        .values(title=new_title)
    )
    await session.execute(stmt)
    await session.commit()

async def delete_playlist(session: AsyncSession, playlist_id: int) -> None:
    stmt = delete(Playlist).where(Playlist.id == playlist_id)
    await session.execute(stmt)
    await session.commit()
    
async def set_active_playlist(session: AsyncSession, tg_id: int, playlist_id: int) -> None:
    user = await get_user(session, tg_id)
    if not user:
        return

    await session.execute(
        update(Playlist)
        .where(Playlist.user_id == user.id)
        .values(is_active=False)
    )

    await session.execute(
        update(Playlist)
        .where(Playlist.id == playlist_id, Playlist.user_id == user.id)
        .values(is_active=True)
    )

    await session.commit()
    
async def add_track(session: AsyncSession, tg_id: int, title: str) -> None:
    user = await get_user(session, tg_id)
    if user:
        track = Track(user_id=user.id, title=title)
        session.add(track)
        await session.commit()
