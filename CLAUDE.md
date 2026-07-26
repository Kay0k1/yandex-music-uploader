# yandex-music-uploader — Project Context

## What this is
Telegram bot (`@YMuploader_bot`) that lets each user upload their own `.mp3` files into their
own Yandex Music playlists (UGC upload). The user sends an audio file in Telegram; the bot pulls
ID3 tags (artist/title/cover) via mutagen, uploads the track to Yandex's `loader` UGC API, then
renames and sets the cover through Yandex's internal `music.yandex.ru/api/v2/handlers/*` endpoints.

## Stack
- Python 3.11, **aiogram 3.x** (long polling, `MemoryStorage` FSM).
- **PostgreSQL 15** via **SQLAlchemy 2.0 async** + asyncpg.
- **yandex-music 2.2.0** (MarshalX) for the Yandex Music client; raw aiohttp for the UGC upload flow.
- **cryptography (Fernet)** — Yandex tokens encrypted at rest.
- mutagen (ID3 parsing), python-dotenv, aiohttp. Docker + Docker Compose deploy.

## Layout
- `main.py` — entry point (`asyncio.run(main())`): builds `Bot`/`Dispatcher`, registers routers +
  `CheckTokenMiddleware`, runs `async_main()` (creates tables), then `start_polling`.
- `src/database/models.py` — SQLAlchemy models `User`, `Playlist`, `Track`; `async_main()` does
  `create_all` (no Alembic/migrations). Engine reads `DATABASE_URL` at import time.
- `src/database/crud.py` — all DB ops; `set_token`/`get_token` transparently encrypt/decrypt.
- `src/handlers/` — `start`, `auth` (OAuth device flow), `playlist` (`/set_playlist`), `upload`
  (`/add`, `/end`, audio handler), `help`, `admin` (`/admin`: stats, top users, last tracks, broadcast).
- `src/middlewares/auth_middleware.py` — `CheckTokenMiddleware`: blocks all messages except
  `/start`, `/help`, `/auth` until the user has a saved token.
- `src/utils/` — `oauth.py` (Yandex OAuth 2.0 Device Flow), `async_uploader.py` (UGC upload),
  `crypto.py` (Fernet), `metadata.py` (ID3), `texts.py`, `keyboards.py`, `states.py`.
- `src/templates/` — `bot_fallback_cover.png/.svg` fallback cover art.
- Compose services: `bot` (this app), `db` (postgres:15-alpine), `telegram-bot-api`
  (aiogram/telegram-bot-api local server, `TELEGRAM_LOCAL=1`, shared `telegram_data` volume).

## Run
```bash
cp .env.example .env      # then fill it in (see below)
docker compose up -d --build
```
Local dev: `pip install -r requirements.txt`, point `DATABASE_URL` at `localhost`, `python main.py`.
Note: `docker-compose.yml` is gitignored — only `docker-compose.example.yml` is committed
(the committed example has just `bot`+`db`; the local `docker-compose.yml` adds `telegram-bot-api`).

## Conventions & gotchas
- **Config is all env vars** (`os.getenv`), loaded via `load_dotenv()`. Required: `BOT_TOKEN`,
  `DATABASE_URL`, `ENCRYPTION_KEY`, `ADMIN_IDS`. Optional: `TELEGRAM_API_URL`/`_ID`/`_HASH`,
  `YANDEX_CLIENT_ID`/`_SECRET`, `YANDEX_PROXY_URL`. See `.env.example` for shape.
- **ENCRYPTION_KEY is load-bearing**: it is the Fernet key that decrypts every user's Yandex token
  in the DB. Losing/rotating it invalidates all stored tokens. Never commit or log it.
- **Auth = Yandex OAuth 2.0 Device Flow** (`src/utils/oauth.py`), defaulting to public Smart-TV
  `client_id`/`secret` unless overridden. `/auth` polls in a background task and saves the token.
- **Local Telegram Bot API server** (`TELEGRAM_API_URL`) is what enables large uploads — the code
  allows files up to 2 GB (`MAX_FILE_SIZE`); the vanilla Bot API caps at ~20 MB.
- `crypto.decrypt_token` has legacy fallback: non-Fernet (plaintext) tokens are returned as-is and
  rewritten on next auth.
- MemoryStorage FSM → upload-mode state (incl. the decrypted token) is held in memory and lost on
  restart. One active playlist per user is enforced by a partial unique index (`ix_user_active_playlist`).
- Optional outbound proxy for all Yandex calls via `YANDEX_PROXY_URL` (used in `async_uploader.py`
  and `playlist.py`).
- The upload success message injects a hardcoded referral/ad link (`t.me/internet_connected_bot`).
- `backup.sql` / `backup_new.sql` are gitignored PostgreSQL dumps present in the repo root — do NOT
  read/dump them (may contain real encrypted tokens and user data). `get-docker.sh` is the standard
  get.docker.com install helper (gitignored, not part of the app).
- **`.env` in the repo root contains real production secrets** — never read it into output, copy its
  values, or commit it. It is gitignored.

## Related
- Global project map: /root/.claude/CLAUDE.md
- Recall index (memory): /root/.claude/projects/-root-yandex-music-uploader/memory/MEMORY.md
