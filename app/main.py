from fastapi import FastAPI

from app import __version__
from app.config import Settings, get_settings
from app.db import init_db, make_engine, make_session_factory
from app.ratelimit import SlidingWindowRateLimiter
from app.routers import links, redirect

DESCRIPTION = """
A URL shortener with click analytics.

Authenticate with an `X-API-Key` header. Issue a key with
`python -m app.manage create-key <name>`.
"""

TAGS = [
    {"name": "links", "description": "Create, manage and inspect short links (API key required)."},
    {"name": "redirect", "description": "Public short-link redirects. Each visit records a click."},
    {"name": "meta", "description": "Service health."},
]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="shortlink-api",
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        license_info={"name": "MIT"},
    )

    engine = make_engine(settings.database_url)
    init_db(engine)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.rate_limiter = SlidingWindowRateLimiter(
        settings.rate_limit_max, settings.rate_limit_window_seconds
    )

    @app.get("/health", tags=["meta"], summary="Liveness check")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(links.router)
    # Registered last: the catch-all /{code} must not shadow the routes above.
    app.include_router(redirect.router)
    return app


app = create_app()
