import time

from app.ratelimit import SlidingWindowRateLimiter
from app.services.codes import is_valid_alias, user_agent_family


def test_rate_limiter_window_slides():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.2)
    assert limiter.check("k") == 0
    assert limiter.check("k") == 0
    assert limiter.check("k") > 0
    time.sleep(0.25)
    assert limiter.check("k") == 0


def test_alias_validation():
    assert is_valid_alias("good-alias_1")
    assert not is_valid_alias("API")
    assert not is_valid_alias("x")


def test_user_agent_family():
    assert user_agent_family("curl/8.4.0") == "curl"
    assert user_agent_family("Mozilla/5.0 Chrome/120 Safari/537.36") == "Chrome"
    assert user_agent_family("Mozilla/5.0 Chrome/120 Safari/537.36 Edg/120") == "Edge"
    assert user_agent_family(None) == "Other"
