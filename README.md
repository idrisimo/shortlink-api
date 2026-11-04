# shortlink-api

[![CI](https://github.com/idrisimo/shortlink-api/actions/workflows/ci.yml/badge.svg)](https://github.com/idrisimo/shortlink-api/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A small, self-hostable URL shortener REST API with click analytics. Create short links (with optional custom aliases and expiry), share them, and see how they perform: total clicks, a 30-day timeline and top referrers. Built with FastAPI, SQLAlchemy 2.0 and SQLite, with no external services required.

## Features

- Create, list, update and delete short links, with random codes or validated custom aliases
- Optional link expiry; expired links return `404`
- `307` redirects that record a click (timestamp, referrer, user-agent family)
- Per-link analytics: total clicks, clicks per day for the last 30 days, top referrers
- API-key auth via `X-API-Key`; keys are stored as SHA-256 hashes and links are owned by a key
- In-memory sliding-window rate limit on link creation (returns `429` with `Retry-After`)
- http/https-only URL validation, consistent JSON error bodies
- Interactive OpenAPI docs at `/docs`
- Dockerfile (non-root) and docker-compose, GitHub Actions CI on Python 3.11-3.13

## Quickstart

### Local

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env

python -m app.manage create-key my-laptop    # prints your API key once
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the interactive API docs.

### Docker

```bash
docker compose up --build
docker compose exec api python -m app.manage create-key my-laptop
```

Data is kept in the `shortlink-data` volume.

## Example requests

All examples below were captured from a running instance (`BASE_URL=http://localhost:8123`).

```bash
export KEY=sl_...   # from `python -m app.manage create-key`
```

Create a link with a custom alias:

```console
$ curl -X POST localhost:8123/api/links \
    -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"url":"https://example.com/docs/getting-started?ref=readme","alias":"launch"}'
{"code":"launch","short_url":"http://localhost:8123/launch","target_url":"https://example.com/docs/getting-started?ref=readme","created_at":"2026-11-04T02:34:39.826976Z","expires_at":null}
```

Alias conflict:

```console
$ curl -X POST localhost:8123/api/links -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"url":"https://example.com/other","alias":"launch"}'
{"detail":"Alias already in use"}
```

Only http/https URLs are accepted (`422`):

```console
$ curl -X POST localhost:8123/api/links -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"url":"ftp://example.com/x"}'
{"detail":[{"type":"url_scheme","loc":["body","url"],"msg":"URL scheme should be 'http' or 'https'","input":"ftp://example.com/x","ctx":{"expected_schemes":"'http' or 'https'"}}]}
```

Missing key (`401`):

```console
$ curl -X POST localhost:8123/api/links -H "Content-Type: application/json" -d '{"url":"https://example.com"}'
{"detail":"Missing X-API-Key header"}
```

Follow the link (records a click):

```console
$ curl -i -H "Referer: https://news.ycombinator.com/" localhost:8123/launch
HTTP/1.1 307 Temporary Redirect
```

Stats (after three visits, two from Hacker News and one direct; `clicks_per_day` shortened here, the API returns all 30 days):

```console
$ curl localhost:8123/api/links/launch/stats -H "X-API-Key: $KEY"
{
  "code": "launch",
  "total_clicks": 3,
  "clicks_per_day": [
    { "date": "2026-10-06", "clicks": 0 },
    "...",
    { "date": "2026-11-04", "clicks": 3 }
  ],
  "top_referrers": [
    { "referrer": "https://news.ycombinator.com/", "clicks": 2 },
    { "referrer": "(direct)", "clicks": 1 }
  ]
}
```

List your links (paginated with `limit` and `offset`):

```console
$ curl "localhost:8123/api/links?limit=5" -H "X-API-Key: $KEY"
{"items":[{"code":"launch","short_url":"http://localhost:8123/launch","target_url":"https://example.com/docs/getting-started?ref=readme","created_at":"2026-11-04T02:34:39.826976Z","expires_at":null}],"total":1,"limit":5,"offset":0}
```

## Endpoints

| Method | Path | Auth | Description |
| ------ | ---- | ---- | ----------- |
| `POST` | `/api/links` | key | Create a link (optional `alias`, `expires_at`); rate limited |
| `GET` | `/api/links` | key | List your links (`limit` 1-100, `offset`) |
| `GET` | `/api/links/{code}` | key | Get one of your links |
| `PATCH` | `/api/links/{code}` | key | Change `url` and/or `expires_at` |
| `DELETE` | `/api/links/{code}` | key | Delete a link and its clicks |
| `GET` | `/api/links/{code}/stats` | key | Total clicks, last 30 days, top referrers |
| `GET` | `/{code}` | none | `307` redirect to the target; records a click |
| `GET` | `/health` | none | Liveness check |

Links owned by another key return `404`, so their existence is not leaked.

## Configuration

Set via environment variables or a `.env` file (see `.env.example`).

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `DATABASE_URL` | `sqlite:///./shortlink.db` | SQLAlchemy database URL |
| `BASE_URL` | `http://localhost:8000` | Prefix used to build `short_url` |
| `CODE_LENGTH` | `7` | Length of generated codes |
| `RATE_LIMIT_MAX` | `10` | Link creations allowed per key per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Sliding window size |

## Architecture

```
app/
  main.py          app factory: wires settings, DB, rate limiter, routers
  config.py        pydantic-settings configuration
  db.py            engine/session helpers, declarative Base, get_db dependency
  models.py        typed SQLAlchemy 2.0 models: ApiKey, Link, Click
  schemas.py       Pydantic v2 request/response models with OpenAPI examples
  security.py      key generation, SHA-256 hashing, X-API-Key dependency
  ratelimit.py     sliding-window limiter + FastAPI dependency
  manage.py        CLI: create-key
  routers/         links.py (JSON API), redirect.py (public /{code})
  services/codes.py  code generation, alias rules, user-agent classification
```

- **App factory.** `create_app(settings)` owns its engine and rate limiter on `app.state`, which is what lets every test run against its own temporary SQLite database.
- **Keys.** Raw keys are shown once at creation and only their SHA-256 hash is stored. Keys are high-entropy random tokens, so a fast hash is appropriate.
- **Rate limiting.** A per-key deque of timestamps in process memory. It is simple and dependency-free, but not shared between workers; use Redis or a gateway for multi-process deployments.
- **Routing.** The catch-all `/{code}` router is registered last so it never shadows `/api/*`, `/health` or `/docs`; those names are also reserved as aliases.
- **Timestamps.** Stored as UTC and returned with a `Z` suffix; SQLite loses tzinfo, so values are normalised on the way out.

## Running tests

```bash
pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
```

## Roadmap

- Alembic migrations
- Per-key rate limit overrides and a Redis-backed limiter
- Click aggregation table for high-traffic links
- QR code endpoint
- Bulk link creation and CSV export of stats

## License

[MIT](LICENSE) (c) 2026 Idris Silva
