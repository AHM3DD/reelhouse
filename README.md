# Reelhouse

A server-rendered movie community. Discover films with real data from TMDB, rate them 1–10, keep favorites and a watchlist, discuss them in comments, and browse other members' profiles. A JWT-protected REST API exposes the same features to API clients.

## Stack

| Layer | Choice |
|---|---|
| Backend | Django 5.2 LTS (ORM, auth, forms, migrations, admin) |
| API | Django REST Framework + Simple JWT |
| Database | PostgreSQL 17 (Docker) |
| Frontend | Django templates, Tailwind CSS (standalone CLI, no Node.js), HTMX, a little vanilla JS |
| Movie data | The Movie Database (TMDB) API v3 |
| Serving | Gunicorn + WhiteNoise |
| Cache | Django `DatabaseCache` in PostgreSQL. It's shared by all workers, survives restarts and needs no Redis. |
| Runtime | Docker + Docker Compose |

## Project layout

```
config/            settings (base / development / production / test), root URLs, WSGI
core/              health check, HTMX helpers, rate limiting, form styling, UI template tags, wait_for_db
accounts/          custom User (case-insensitive unique email/username), profiles, avatars, auth views
movies/            TMDB client (tmdb.py), Movie snapshot model, discovery/search/detail views
community/         comments, ratings, favorites, watchlist: models, services (business rules), HTMX views
api/               DRF serializers/views, JWT endpoints
templates/         base layout, reusable partials, pages, error pages
static/            src/input.css (Tailwind source), js/app.js, vendored htmx, images
docker/            entrypoint.py (wait for DB → migrate → exec command)
```

### Key design decisions

- **TMDB data is fetched, not mirrored.** Responses are cached twice: a fresh copy (15 min – 24 h, depending on the endpoint) and a stale copy kept for 7 days. If TMDB times out, rate-limits us (429) or returns 5xx, the client pauses requests briefly and serves the stale copy, marked in the UI as possibly out of date. If no copy exists, the page shows a friendly unavailable state.
- **A local `Movie` row is created only when a user interacts with a film** (comment, rating, favorite, list). The row stores a small snapshot (title, poster, year…) so profiles and collections render without calling TMDB, and the TMDB id is validated before anything is stored.
- **Community scores and TMDB scores are always shown separately**, with their own labels and icons.
- **Browser pages use session auth with CSRF.** JWTs are only for API clients and are never stored in `localStorage`.
- **Integrity rules live in the database:** unique (user, movie) for ratings, favorites and list entries; a CHECK constraint keeping ratings within 1–10; non-empty comments; case-insensitive unique email and username.
- **Every HTMX endpoint also works without JavaScript** (normal POST + redirect).

## Prerequisites

Docker Desktop (or Docker Engine) with Docker Compose v2. Python and PostgreSQL do **not** need to be installed on the host.

## Initial setup

```bash
cp .env.example .env
# Edit .env: set DJANGO_SECRET_KEY, POSTGRES_PASSWORD and TMDB_API_KEY
docker compose up --build
```

Open http://localhost:8888. On startup the web container waits for PostgreSQL, applies migrations and creates the cache table. Set `DJANGO_MIGRATE_ON_START=0` to run migrations manually instead.

### Getting a TMDB API key

1. Create a free account at https://www.themoviedb.org/signup.
2. Go to **Settings → API** (https://www.themoviedb.org/settings/api) and request a developer key.
3. Copy the **API Key (v3 auth)** value into `TMDB_API_KEY` in `.env`.

The key stays on the server: it is never rendered into HTML, sent to the browser or written to logs.

## Environment variables

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Required. Production refuses to start unless it's ≥ 40 random characters. |
| `DJANGO_DEBUG` | Development only. Production always runs with `DEBUG=False`. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated origins, e.g. `https://movies.example.com`. |
| `JWT_SIGNING_KEY` | Optional separate JWT key (defaults to the secret key). |
| `DJANGO_MIGRATE_ON_START` | `1` to migrate on container start. |
| `DJANGO_ADMIN_URL` | Admin path prefix (default `admin/`). |
| `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SECURE_COOKIES`, `DJANGO_SECURE_HSTS_SECONDS` | HTTPS hardening (production; on by default). |
| `DJANGO_BEHIND_PROXY` | `True` behind a TLS-terminating proxy (trusts `X-Forwarded-Proto`/`-For`). |
| `DJANGO_SERVE_MEDIA` | Let Django serve uploaded avatars in production. |
| `GUNICORN_WORKERS` | Gunicorn worker count. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Database credentials (used by both containers). |
| `POSTGRES_HOST`, `POSTGRES_PORT` | `db` / `5433` inside Compose (the database container listens on this port; it is not published to the host). |
| `TMDB_API_KEY` | TMDB v3 API key. |
| `TMDB_LANGUAGE`, `TMDB_REGION`, `TMDB_TIMEOUT` | Locale, optional region for upcoming/now playing, request timeout in seconds. |
| `WEB_PORT` | Host port (default 8888). |

## Docker commands

`compose.yaml` is the production-style base. `compose.override.yaml` is merged automatically and switches to development mode: `runserver` with auto-reload, a source bind mount, and a Tailwind watcher service (`css`).

| Task | Command |
|---|---|
| Start (dev, foreground) | `docker compose up --build` |
| Start (dev, background) | `docker compose up -d --build` |
| Start production-style | `docker compose -f compose.yaml up -d --build` |
| Follow logs | `docker compose logs -f web` |
| Run migrations | `docker compose exec web python manage.py migrate` |
| Create migrations after model changes | `docker compose exec web python manage.py makemigrations` |
| Create an admin user | `docker compose exec web python manage.py createsuperuser` |
| Run tests | `docker compose exec web python manage.py test` |
| Django shell | `docker compose exec web python manage.py shell` |
| Clean up expired JWTs | `docker compose exec web python manage.py flushexpiredtokens` |
| Stop containers (data is kept) | `docker compose down` |

> ⚠️ Do **not** use `docker compose down -v` as a normal stop command. `-v` deletes the `postgres_data` and `media` volumes, which means every account, comment, rating and avatar.

The admin site is at `/admin/` (or your `DJANGO_ADMIN_URL`). Only staff/superusers can log in.

## Database backup and restore

PostgreSQL has no published port. Backups go through the `db` container:

```bash
mkdir -p backups

# Backup (custom format, compressed)
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > backups/reelhouse-$(date +%F).dump

# Restore (replaces existing objects in the database)
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < backups/reelhouse-YYYY-MM-DD.dump
```

On Windows, run these from Git Bash or WSL rather than PowerShell, which re-encodes binary pipes. In Git Bash, prefix the media `docker run` commands below with `MSYS_NO_PATHCONV=1` and use `"$(pwd -W)/backups"`. Otherwise Git Bash rewrites the container paths.

**Uploaded media** (avatars) live in the `reelhouse_media` volume and are *not* included in the database dump:

```bash
# Backup media
docker run --rm -v reelhouse_media:/media -v "$PWD/backups":/backup alpine tar czf /backup/media.tgz -C /media .
# Restore media
docker run --rm -v reelhouse_media:/media -v "$PWD/backups":/backup alpine tar xzf /backup/media.tgz -C /media
```

## Tests

```bash
docker compose exec web python manage.py test
```

Tests use their own settings (`config.settings.test`): a temporary PostgreSQL test database, an in-memory cache and **mocked TMDB HTTP calls**, so no API key or network access is needed. They cover registration and login, JWT obtain/refresh/rotation/blacklisting, authorization (editing or deleting someone else's comments, profiles, favorites or ratings), rating and favorite uniqueness, database constraints, avatar validation, TMDB caching, timeouts, rate limits, stale fallbacks, search and filters, empty states, XSS escaping and rate limiting.

## REST API and JWT

Base URL: `/api/`. `GET /api/` lists the endpoints.

| Method | Endpoint | Auth |
|---|---|---|
| POST | `/api/auth/token/` `{username, password}` → `{access, refresh}` | public (throttled 10/min) |
| POST | `/api/auth/token/refresh/` `{refresh}` → new `{access, refresh}` | public |
| POST | `/api/auth/token/blacklist/` `{refresh}` (logout) | public |
| GET/PATCH | `/api/me/` (PATCH can change `bio` only) | JWT |
| GET/POST | `/api/me/favorites/` `{tmdb_id}` | JWT |
| DELETE | `/api/me/favorites/<tmdb_id>/` | JWT |
| GET | `/api/movies/search/?q=` | public |
| GET | `/api/movies/<tmdb_id>/` (TMDB data + community stats) | public |
| GET/POST | `/api/movies/<tmdb_id>/comments/` | GET public, POST JWT (throttled) |
| GET/PATCH/DELETE | `/api/comments/<id>/` | write: author only |
| GET/PUT/DELETE | `/api/movies/<tmdb_id>/rating/` `{score: 1-10}` | JWT (own rating) |
| GET | `/api/users/<username>/` (public profile, no email) | public |

**How tokens work:** the access token is valid for 15 minutes. Send it as `Authorization: Bearer <access>`. The refresh token is valid for 7 days. Each refresh returns a *new* refresh token and blacklists the old one (rotation), so a refresh token can be used only once. Blacklisting a refresh token logs that client out. Tokens are signed with HS256 using `JWT_SIGNING_KEY` (or `DJANGO_SECRET_KEY`). Lifetimes can be changed with `JWT_ACCESS_MINUTES` and `JWT_REFRESH_DAYS`.

```bash
curl -s -X POST localhost:8888/api/auth/token/ -H 'Content-Type: application/json' \
     -d '{"username":"alice","password":"..."}'
curl -s localhost:8888/api/me/favorites/ -H "Authorization: Bearer $ACCESS"
curl -s -X PUT localhost:8888/api/movies/27205/rating/ -H "Authorization: Bearer $ACCESS" \
     -H 'Content-Type: application/json' -d '{"score": 9}'
```

Store tokens in your client's secure storage (Keychain, Keystore, server-side session), not in browser `localStorage`. The website itself never uses JWTs.

## Security notes

- CSRF protection on every form and HTMX request (the token is sent in the `X-CSRFToken` header). Logout is POST-only.
- Ownership is checked on the server for every write. Other users' comments return 403. Ratings, favorites and lists are always scoped to the logged-in user.
- User content is auto-escaped. Comment input is normalized (control characters stripped, length limited).
- Avatars: up to 2 MB, JPEG/PNG/WebP/GIF only, verified with Pillow, then **re-encoded** to a 400×400 WebP. This strips EXIF/GPS data and anything hidden in the file.
- Rate limits: login 10 per 5 minutes per IP, registration 10/hour per IP, comments 6/minute per user (website). The API has its own throttles: 10/min for token endpoints, 10/min for comment creation, plus global anon/user throttles.
- Public profiles never expose email addresses.
- Production settings enforce `DEBUG=False`, refuse missing or weak secret keys, and enable an HTTPS redirect, secure cookies and HSTS by default. They also set `X-Frame-Options: DENY`, `nosniff` and a strict referrer policy.
- No raw SQL is used.

## Production deployment checklist

1. Put a TLS-terminating reverse proxy (Caddy, nginx, Traefik or a cloud load balancer) in front of port 8888 and set `DJANGO_BEHIND_PROXY=True`.
2. Set `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` (with `https://`), and a strong `DJANGO_SECRET_KEY` / `POSTGRES_PASSWORD`. Keep `DJANGO_SECURE_SSL_REDIRECT=True` and `DJANGO_SECURE_COOKIES=True`.
3. Start with `docker compose -f compose.yaml up -d --build`. Containers restart automatically (`unless-stopped`) and the web container has a health check (`/healthz/`).
4. Run `docker compose -f compose.yaml exec web python manage.py check --deploy`.
5. Schedule regular database **and** media backups (see above) and test restores.
6. At larger scale, serve `/media/` from the proxy or object storage (`DJANGO_SERVE_MEDIA=False`), and consider moving the cache to Redis.
7. Show the TMDB attribution (already in the footer), as required by the TMDB terms.
