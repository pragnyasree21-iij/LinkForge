"""
Unit and integration tests for Step 11:
LinkForge Frontend Dashboard & Click Analytics.

Tests:
1. Dashboard page (`GET /`) loads successfully and serves semantic HTML.
2. The URL creation interface and static assets are served correctly.
3. A successful redirect increments the click count exactly once.
4. Multiple successful redirects increment the counter accurately.
5. The click count persists after SQLite repository is reopened.
6. Unknown short codes return 404 and do not increment any counter.
7. Expired links return 410 and do not increment any counter.
8. Dashboard statistics accurately reflect repository records and click sums.
9. InMemory and SQLite repository implementations adhere to the click increment contract.
"""

import os
import tempfile
import pytest
from datetime import datetime, timedelta, timezone
from flask.testing import FlaskClient

from app import create_app
from app.config import AppConfig
from app.models import URLRecord
from app.repositories import InMemoryURLRepository, SQLiteURLRepository
from app.validators import URLValidator, AliasValidator
from app.generators import RandomCodeGenerator
from app.services import URLShortenerService


@pytest.fixture
def temp_db_path():
    """Create and yield an isolated temporary SQLite database path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture
def test_client(temp_db_path):
    """Create a Flask test client configured with an isolated SQLite database."""
    config = AppConfig()
    config.base_url = "http://localhost:5000"
    
    repo = SQLiteURLRepository(db_path=temp_db_path)
    validator = URLValidator()
    alias_validator = AliasValidator()
    generator = RandomCodeGenerator(length=6)
    service = URLShortenerService(
        repository=repo,
        validator=validator,
        alias_validator=alias_validator,
        generator=generator,
        max_retries=5
    )
    
    app = create_app(config=config, service=service)
    app.config["TESTING"] = True
    return app.test_client()


class TestDashboardFrontend:
    """Test dashboard template rendering and static asset delivery."""

    def test_dashboard_page_loads_successfully(self, test_client: FlaskClient):
        """GET / should render the HTML dashboard with HTTP 200."""
        response = test_client.get("/")
        assert response.status_code == 200
        assert response.content_type.startswith("text/html")
        html_data = response.get_data(as_text=True)
        assert "LinkForge" in html_data
        assert "URL Dashboard" in html_data
        assert "Shorten a New URL" in html_data
        assert "My Links" in html_data
        assert "statTotalLinks" in html_data
        assert "statTotalClicks" in html_data

    def test_url_creation_interface_elements_present(self, test_client: FlaskClient):
        """Verify essential form controls and IDs are rendered in the dashboard."""
        response = test_client.get("/")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'id="shortenForm"' in html
        assert 'id="urlInput"' in html
        assert 'id="aliasInput"' in html
        assert 'id="expiresInput"' in html
        assert 'id="submitBtn"' in html
        assert 'id="searchInput"' in html
        assert 'id="linksTableBody"' in html

    def test_static_assets_served_correctly(self, test_client: FlaskClient):
        """Verify style.css and dashboard.js can be requested and served."""
        css_resp = test_client.get("/static/css/style.css")
        assert css_resp.status_code == 200
        assert "LinkForge Design System" in css_resp.get_data(as_text=True)

        js_resp = test_client.get("/static/js/dashboard.js")
        assert js_resp.status_code == 200
        assert "LinkForge Frontend Dashboard Logic" in js_resp.get_data(as_text=True)


class TestClickAnalytics:
    """Test real click tracking during redirects and persistence."""

    def test_successful_redirect_increments_click_count_exactly_once(self, test_client: FlaskClient):
        """A valid redirect must increase click_count from 0 to 1."""
        # 1. Create short URL
        create_resp = test_client.post(
            "/api/urls",
            json={"url": "https://example.com/target-page", "custom_alias": "click-test-1"}
        )
        assert create_resp.status_code == 201
        assert create_resp.json["click_count"] == 0

        # 2. Issue redirect request
        redir_resp = test_client.get("/click-test-1")
        assert redir_resp.status_code == 302
        assert redir_resp.headers["Location"] == "https://example.com/target-page"

        # 3. Verify click count in listing
        list_resp = test_client.get("/api/urls")
        assert list_resp.status_code == 200
        records = list_resp.json["urls"]
        matched = next(r for r in records if r["short_code"] == "click-test-1")
        assert matched["click_count"] == 1

    def test_multiple_redirects_increment_counter_accurately(self, test_client: FlaskClient):
        """Multiple redirects must increment click_count once per successful redirect."""
        test_client.post(
            "/api/urls",
            json={"url": "https://example.com/multi-click", "custom_alias": "multi-click"}
        )

        for _ in range(7):
            resp = test_client.get("/multi-click")
            assert resp.status_code == 302

        list_resp = test_client.get("/api/urls")
        matched = next(r for r in list_resp.json["urls"] if r["short_code"] == "multi-click")
        assert matched["click_count"] == 7

    def test_unknown_short_code_does_not_increment_counter(self, test_client: FlaskClient):
        """Requesting an unknown short code returns 404 and affects no records."""
        resp = test_client.get("/nonexistent-slug")
        assert resp.status_code == 404

        list_resp = test_client.get("/api/urls")
        assert list_resp.json["count"] == 0

    def test_expired_link_does_not_increment_counter(self, temp_db_path):
        """An expired short code returns 410 and click_count remains untouched."""
        repo = SQLiteURLRepository(db_path=temp_db_path)
        past_time = datetime.now(timezone.utc) - timedelta(hours=2)
        expired_record = URLRecord(
            original_url="https://example.com/expired-page",
            short_code="expired-link",
            created_at=datetime.now(timezone.utc) - timedelta(hours=5),
            expires_at=past_time,
            click_count=0
        )
        repo.save(expired_record)

        config = AppConfig()
        service = URLShortenerService(
            repository=repo,
            validator=URLValidator(),
            alias_validator=AliasValidator(),
            generator=RandomCodeGenerator()
        )
        app = create_app(config=config, service=service)
        client = app.test_client()

        # Attempt redirect
        resp = client.get("/expired-link")
        assert resp.status_code == 410

        # Check counter remains 0
        persisted = repo.find_by_code("expired-link")
        assert persisted is not None
        assert persisted.click_count == 0

    def test_click_count_persists_after_sqlite_repository_reopened(self, temp_db_path):
        """Clicks incremented must persist when SQLite repository is reopened."""
        repo1 = SQLiteURLRepository(db_path=temp_db_path)
        record = URLRecord(
            original_url="https://example.com/persistent-clicks",
            short_code="persist-slug",
            created_at=datetime.now(timezone.utc),
            click_count=0
        )
        repo1.save(record)

        service1 = URLShortenerService(
            repository=repo1,
            validator=URLValidator(),
            alias_validator=AliasValidator(),
            generator=RandomCodeGenerator()
        )
        app1 = create_app(config=AppConfig(), service=service1)
        client1 = app1.test_client()

        # Perform 3 redirects
        for _ in range(3):
            res = client1.get("/persist-slug")
            assert res.status_code == 302

        # Reopen SQLite repository with a completely fresh instance
        repo2 = SQLiteURLRepository(db_path=temp_db_path)
        reloaded = repo2.find_by_code("persist-slug")
        assert reloaded is not None
        assert reloaded.click_count == 3


class TestDashboardStatisticsCalculations:
    """Verify aggregated statistics calculations against actual records."""

    def test_dashboard_statistics_match_records(self, test_client: FlaskClient):
        """Total links, active links, expired links, and click totals must sum correctly."""
        # 1. Active link with 3 clicks
        test_client.post(
            "/api/urls",
            json={"url": "https://example.com/active-1", "custom_alias": "act-1"}
        )
        for _ in range(3):
            test_client.get("/act-1")

        # 2. Active link with 2 clicks
        test_client.post(
            "/api/urls",
            json={"url": "https://example.com/active-2", "custom_alias": "act-2"}
        )
        for _ in range(2):
            test_client.get("/act-2")

        # 3. Active link with 0 clicks
        test_client.post(
            "/api/urls",
            json={"url": "https://example.com/active-3", "custom_alias": "act-3"}
        )

        resp = test_client.get("/api/urls")
        assert resp.status_code == 200
        data = resp.json
        urls = data["urls"]
        assert len(urls) == 3

        total_clicks = sum(u["click_count"] for u in urls)
        active_count = sum(1 for u in urls if not u["is_expired"])
        expired_count = sum(1 for u in urls if u["is_expired"])

        assert total_clicks == 5
        assert active_count == 3
        assert expired_count == 0


class TestRepositoryClickIncrementContract:
    """Verify both repository implementations conform to increment_click_count."""

    def test_in_memory_repository_increment_click_count(self):
        repo = InMemoryURLRepository()
        record = URLRecord(
            original_url="https://example.com",
            short_code="mem1",
            created_at=datetime.now(timezone.utc),
            click_count=0
        )
        repo.save(record)

        assert repo.increment_click_count("mem1") is True
        assert repo.find_by_code("mem1").click_count == 1

        assert repo.increment_click_count("mem1") is True
        assert repo.find_by_code("mem1").click_count == 2

        # Non-existent returns False
        assert repo.increment_click_count("missing") is False

    def test_sqlite_repository_increment_click_count(self, temp_db_path):
        repo = SQLiteURLRepository(db_path=temp_db_path)
        record = URLRecord(
            original_url="https://example.com",
            short_code="sql1",
            created_at=datetime.now(timezone.utc),
            click_count=0
        )
        repo.save(record)

        assert repo.increment_click_count("sql1") is True
        assert repo.find_by_code("sql1").click_count == 1

        assert repo.increment_click_count("sql1") is True
        assert repo.find_by_code("sql1").click_count == 2

        # Non-existent returns False
        assert repo.increment_click_count("missing") is False
