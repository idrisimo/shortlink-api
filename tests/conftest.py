from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import create_api_key


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        rate_limit_max=5,
        rate_limit_window_seconds=60,
    )


@pytest.fixture
def client(settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client
    app.state.engine.dispose()


def _issue_key(client: TestClient, name: str) -> dict[str, str]:
    with client.app.state.session_factory() as db:
        return {"X-API-Key": create_api_key(db, name)}


@pytest.fixture
def auth(client) -> dict[str, str]:
    return _issue_key(client, "alice")


@pytest.fixture
def other_auth(client) -> dict[str, str]:
    return _issue_key(client, "bob")
