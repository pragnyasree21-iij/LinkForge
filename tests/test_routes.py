"""
Unit and integration tests for LinkForge Flask API routes and redirection.
Tests health checks, URL shortening, duplicate handling, redirection, and expiration.
"""

from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
import pytest

from app import create_app
from app.config import AppConfig
from app.validators import URLValidator
from app.generators import RandomCodeGenerator
from app.repositories import SQLiteURLRepository
from app.services import URLShortenerService


@pytest.fixture
def temp_db_path():
    """Create a temporary SQLite database file for isolated test execution."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture
def test_app(temp_db_path: str):
    """Provide a test Flask application wired with an isolated temporary SQLite database."""
    config = AppConfig(db_path=temp_db_path)
    repository = SQLiteURLRepository(db_path=temp_db_path)
    service = URLShortenerService(
        validator=URLValidator(),
        generator=RandomCodeGenerator(length=6),
        repository=repository
    )
    app = create_app(service=service, config=config)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(test_app):
    """Provide Flask test client."""
    return test_app.test_client()


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_check_returns_success(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["app"] == "LinkForge"


class TestCreateURLRoute:
    """Tests for POST /api/urls."""

    def test_create_valid_url_returns_201(self, client):
        payload = {"url": "https://www.python.org"}
        response = client.post(
            "/api/urls",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert response.status_code == 201
        data = response.get_json()
        assert "short_code" in data
        assert "short_url" in data
        assert data["original_url"] == "https://www.python.org"
        assert data["status"] == "active"

    def test_create_with_valid_custom_alias(self, client):
        payload = {
            "url": "https://github.com",
            "custom_alias": "my-gh-profile"
        }
        response = client.post(
            "/api/urls",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["short_code"] == "my-gh-profile"
        assert data["original_url"] == "https://github.com"

    def test_missing_url_field_returns_400(self, client):
        payload = {"custom_alias": "something"}
        response = client.post(
            "/api/urls",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "required" in data["error"]

    def test_invalid_url_syntax_returns_400(self, client):
        payload = {"url": "javascript:alert(1)"}
        response = client.post(
            "/api/urls",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "Invalid URL" in data["error"]

    def test_duplicate_custom_alias_returns_409(self, client):
        payload = {"url": "https://first.com", "custom_alias": "shared-slug"}
        res1 = client.post("/api/urls", data=json.dumps(payload), content_type="application/json")
        assert res1.status_code == 201

        payload_dup = {"url": "https://second.com", "custom_alias": "shared-slug"}
        res2 = client.post("/api/urls", data=json.dumps(payload_dup), content_type="application/json")
        assert res2.status_code == 409
        data = res2.get_json()
        assert "already in use" in data["error"]

    def test_malformed_json_returns_400(self, client):
        response = client.post(
            "/api/urls",
            data="not-valid-json",
            content_type="application/json"
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "JSON" in data["error"]

    def test_non_json_content_type_returns_400(self, client):
        response = client.post("/api/urls", data="plain text body")
        assert response.status_code == 400

    def test_invalid_expiration_format_returns_400(self, client):
        payload = {"url": "https://valid.com", "expires_at": "not-a-timestamp"}
        response = client.post("/api/urls", data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 400
        data = response.get_json()
        assert "ISO-8601" in data["error"]


class TestRedirectRoute:
    """Tests for GET /<short_code> HTTP 302 Redirection."""

    def test_valid_short_code_redirects_with_302(self, client):
        # 1. Create a short link
        create_res = client.post(
            "/api/urls",
            data=json.dumps({"url": "https://wikipedia.org", "custom_alias": "wiki-link"}),
            content_type="application/json"
        )
        assert create_res.status_code == 201

        # 2. Access the short link (follow_redirects=False)
        redirect_res = client.get("/wiki-link")
        assert redirect_res.status_code == 302
        assert redirect_res.headers["Location"] == "https://wikipedia.org"

    def test_unknown_short_code_returns_404(self, client):
        response = client.get("/nonexistent-slug")
        assert response.status_code == 404
        data = response.get_json()
        assert "does not exist" in data["error"]

    def test_expired_link_does_not_redirect_returns_410(self, test_app, client):
        # Create a link that expires soon
        future_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        create_res = client.post(
            "/api/urls",
            data=json.dumps({
                "url": "https://expired-soon.com",
                "custom_alias": "expiring-link",
                "expires_at": future_time.isoformat()
            }),
            content_type="application/json"
        )
        assert create_res.status_code == 201

        # Simulate expiration by setting record's expires_at in the past directly in DB
        repo = test_app.config["URL_SERVICE"]._repository
        record = repo.find_by_code("expiring-link")
        record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        # Update record in DB to simulate passage of time
        with repo._get_connection() as conn:
            conn.execute(
                "UPDATE urls SET expires_at = ? WHERE short_code = ?",
                (record.expires_at.isoformat(), "expiring-link")
            )

        # Attempt to access expired link
        get_res = client.get("/expiring-link")
        assert get_res.status_code == 410
        data = get_res.get_json()
        assert "has expired" in data["error"]


class TestListURLsEndpoint:
    """Tests for GET /api/urls."""

    def test_list_urls_returns_existing_links(self, client):
        # Empty list initially
        res0 = client.get("/api/urls")
        assert res0.status_code == 200
        assert res0.get_json()["count"] == 0

        # Create two links
        client.post("/api/urls", data=json.dumps({"url": "https://a.com"}), content_type="application/json")
        client.post("/api/urls", data=json.dumps({"url": "https://b.com"}), content_type="application/json")

        res1 = client.get("/api/urls")
        assert res1.status_code == 200
        data = res1.get_json()
        assert data["count"] == 2
        assert len(data["urls"]) == 2


class TestPersistenceAcrossRestart:
    """Tests persistence across simulated application restarts."""

    def test_links_persist_across_app_restarts(self, temp_db_path: str):
        config = AppConfig(db_path=temp_db_path)

        # App Session 1: Create link
        app1 = create_app(config=config)
        client1 = app1.test_client()
        res1 = client1.post(
            "/api/urls",
            data=json.dumps({"url": "https://persist-test.com", "custom_alias": "persisted-link"}),
            content_type="application/json"
        )
        assert res1.status_code == 201
        del client1
        del app1

        # App Session 2: Fresh app instance pointing to same DB file
        app2 = create_app(config=config)
        client2 = app2.test_client()
        redirect_res = client2.get("/persisted-link")
        assert redirect_res.status_code == 302
        assert redirect_res.headers["Location"] == "https://persist-test.com"
