from sqlalchemy import select, update, delete, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import User, Track, Playlist

from typing import List


async def create_user(session: AsyncSession, tg_id: int, username: str = None) -> User:
    user = await get_user(session, tg_id)
    if user:
        # Обновляем username если изменился
        if username and user.username != username:
            user.username = username
            await session.commit()
        return user

    user = User(tg_id=tg_id, username=username)
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

async def create_playlist_and_set_active(session: AsyncSession, tg_id: int, kind: str, title: str) -> Playlist:
    """Создаёт плейлист в БД и сразу делает его активным"""
    user = await get_user(session, tg_id)
    if not user:
        raise ValueError("User not found")

    await session.execute(
        update(Playlist).where(Playlist.user_id == user.id).values(is_active=False)
    )

    new_playlist = Playlist(user_id=user.id, kind=kind, title=title, is_active=True)
    session.add(new_playlist)
    await session.commit()
    await session.refresh(new_playlist)
    return new_playlist


async def sync_playlists(session: AsyncSession, tg_id: int, yandex_playlists: list) -> None:
    """
    yandex_playlists: список объектов Playlist из библиотеки yandex_music
    """
    user = await get_user(session, tg_id)
    if not user:
        return

    for pl in yandex_playlists:
        
        stmt = select(Playlist).where(
            Playlist.user_id == user.id,
            Playlist.kind == str(pl.kind)
        )
        result = await session.execute(stmt)
        existing_playlist = result.scalar_one_or_none()

        if existing_playlist:
            existing_playlist.title = pl.title
        else:
            new_pl = Playlist(
                user_id=user.id,
                kind=str(pl.kind),
                title=pl.title,
                is_active=False
            )
            session.add(new_pl)
    
    await session.commit()

async def get_user_playlists(session: AsyncSession, tg_id: int) -> List[Playlist]:
    query = (
        select(Playlist)
        .join(User)
        .where(User.tg_id == tg_id)
        .order_by(Playlist.id)
    )
    result = await session.execute(query)
    return list(result.scalars().all())

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
    
async def add_track(session: AsyncSession, tg_id: int, artist: str, title: str) -> None:
    user = await get_user(session, tg_id)
    if not user:
        return

    track = Track(user_id=user.id, artist=artist, title=title)
    session.add(track)

    await session.execute(
        update(User)
        .where(User.id == user.id)
        .values(track_count=User.track_count + 1)
    )
    
    await session.commit()

async def get_global_stats(session: AsyncSession):
    """Возвращает (количество юзеров, количество загруженных треков)"""
    users_count = await session.scalar(select(func.count(User.id)))
    tracks_count = await session.scalar(select(func.count(Track.id)))
    return users_count, tracks_count

async def get_top_users(session: AsyncSession, limit: int = 10, offset: int = 0):
    """Возвращает топ юзеров по количеству загрузок"""
    query = select(User).where(User.track_count > 0).order_by(User.track_count.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    return result.scalars().all()

async def get_last_tracks(session: AsyncSession, limit: int = 10, offset: int = 0):
    """Возвращает последние загруженные треки вместе с инфой о юзере"""
    from sqlalchemy.orm import selectinload
    query = select(Track).options(selectinload(Track.user)).order_by(Track.id.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    return result.scalars().all()