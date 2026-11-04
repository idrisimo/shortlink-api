from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Link
from app.security import hash_key

URL = "https://example.com/some/long/path"


def create(client, auth, **body):
    return client.post("/api/links", json={"url": URL, **body}, headers=auth)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_link_generates_code(client, auth):
    response = create(client, auth)
    assert response.status_code == 201
    data = response.json()
    assert len(data["code"]) == 7
    assert data["short_url"].endswith(f"/{data['code']}")
    assert data["target_url"] == URL
    assert data["expires_at"] is None


def test_create_link_with_custom_alias(client, auth):
    response = create(client, auth, alias="my-link_1")
    assert response.status_code == 201
    assert response.json()["code"] == "my-link_1"


def test_alias_conflict_returns_409(client, auth, other_auth):
    assert create(client, auth, alias="taken").status_code == 201
    response = create(client, other_auth, alias="taken")
    assert response.status_code == 409
    assert "already in use" in response.json()["detail"]


def test_invalid_alias_rejected(client, auth):
    for alias in ("ab", "has space", "bad/slash", "api"):
        assert create(client, auth, alias=alias).status_code == 422, alias


def test_invalid_url_rejected(client, auth):
    for bad in ("ftp://example.com/file", "javascript:alert(1)", "not a url", ""):
        response = client.post("/api/links", json={"url": bad}, headers=auth)
        assert response.status_code == 422, bad


def test_expiry_must_be_in_future(client, auth):
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert create(client, auth, expires_at=past).status_code == 422


def test_auth_required(client):
    assert client.post("/api/links", json={"url": URL}).status_code == 401
    assert client.get("/api/links").status_code == 401
    bad = {"X-API-Key": "sl_nope"}
    assert client.get("/api/links", headers=bad).status_code == 401


def test_keys_are_stored_hashed(client, auth):
    raw = auth["X-API-Key"]
    with client.app.state.session_factory() as db:
        from app.models import ApiKey

        stored = db.scalars(select(ApiKey)).all()
    assert all(k.key_hash != raw for k in stored)
    assert hash_key(raw) in {k.key_hash for k in stored}


def test_redirect_records_click(client, auth):
    code = create(client, auth).json()["code"]
    response = client.get(
        f"/{code}",
        headers={"Referer": "https://news.example/post", "User-Agent": "curl/8.0"},
    )
    assert response.status_code == 307
    assert response.headers["location"] == URL

    stats = client.get(f"/api/links/{code}/stats", headers=auth).json()
    assert stats["total_clicks"] == 1
    assert stats["top_referrers"] == [{"referrer": "https://news.example/post", "clicks": 1}]


def test_unknown_code_is_404(client):
    assert client.get("/doesnotexist").status_code == 404


def test_expired_link_is_404(client, auth):
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    code = create(client, auth, expires_at=future).json()["code"]
    assert client.get(f"/{code}").status_code == 307

    with client.app.state.session_factory() as db:
        link = db.scalar(select(Link).where(Link.code == code))
        link.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    assert client.get(f"/{code}").status_code == 404


def test_get_patch_delete_link(client, auth):
    code = create(client, auth).json()["code"]
    assert client.get(f"/api/links/{code}", headers=auth).json()["code"] == code

    patched = client.patch(
        f"/api/links/{code}", json={"url": "https://example.org/new"}, headers=auth
    )
    assert patched.status_code == 200
    assert patched.json()["target_url"] == "https://example.org/new"
    assert client.get(f"/{code}").headers["location"] == "https://example.org/new"

    assert client.delete(f"/api/links/{code}", headers=auth).status_code == 204
    assert client.get(f"/api/links/{code}", headers=auth).status_code == 404
    assert client.get(f"/{code}").status_code == 404


def test_patch_can_clear_expiry(client, auth):
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    code = create(client, auth, expires_at=future).json()["code"]
    response = client.patch(f"/api/links/{code}", json={"expires_at": None}, headers=auth)
    assert response.json()["expires_at"] is None


def test_ownership_isolation(client, auth, other_auth):
    code = create(client, auth).json()["code"]
    path = f"/api/links/{code}"
    assert client.get(path, headers=other_auth).status_code == 404
    assert client.patch(path, json={"url": URL}, headers=other_auth).status_code == 404
    assert client.delete(path, headers=other_auth).status_code == 404
    assert client.get(f"{path}/stats", headers=other_auth).status_code == 404
    assert client.get("/api/links", headers=other_auth).json()["total"] == 0
    # Still intact for the owner.
    assert client.get(path, headers=auth).status_code == 200


def test_stats_shape_and_counts(client, auth):
    code = create(client, auth).json()["code"]
    for referer in ("https://a.example", "https://a.example", "https://b.example", None):
        headers = {"Referer": referer} if referer else {}
        client.get(f"/{code}", headers=headers)

    stats = client.get(f"/api/links/{code}/stats", headers=auth).json()
    assert stats["total_clicks"] == 4
    assert len(stats["clicks_per_day"]) == 30
    assert stats["clicks_per_day"][-1]["clicks"] == 4
    assert sum(day["clicks"] for day in stats["clicks_per_day"][:-1]) == 0
    assert stats["top_referrers"][0] == {"referrer": "https://a.example", "clicks": 2}
    assert {"referrer": "(direct)", "clicks": 1} in stats["top_referrers"]


def test_rate_limit_on_creation(client, auth, other_auth):
    for _ in range(5):
        assert create(client, auth).status_code == 201
    blocked = create(client, auth)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    # Limits are per key, and reads are not limited.
    assert create(client, other_auth).status_code == 201
    assert client.get("/api/links", headers=auth).status_code == 200


def test_pagination(client, auth, settings):
    settings.rate_limit_max = 100
    client.app.state.rate_limiter.max_requests = 100
    codes = [create(client, auth).json()["code"] for _ in range(7)]

    first = client.get("/api/links?limit=3", headers=auth).json()
    assert first["total"] == 7
    assert len(first["items"]) == 3
    assert first["items"][0]["code"] == codes[-1]  # newest first

    last = client.get("/api/links?limit=3&offset=6", headers=auth).json()
    assert [item["code"] for item in last["items"]] == [codes[0]]

    assert client.get("/api/links?limit=0", headers=auth).status_code == 422
    assert client.get("/api/links?limit=101", headers=auth).status_code == 422


def test_openapi_has_tags(client):
    schema = client.get("/openapi.json").json()
    assert {t["name"] for t in schema["tags"]} >= {"links", "redirect", "meta"}
