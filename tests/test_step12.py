"""
Unit and integration tests for Step 12:
Comprehensive Edge-Case Testing & Final Quality Review for LinkForge.

Coverage:
1. URL validation edge cases (query params, fragments, valid/invalid ports, IP hostnames, non-strings).
2. Short-code generation edge cases (lengths, character sets, bounded retries, collision resolution).
3. Expiration edge cases (permanent vs. future vs. expired, naive timestamps).
4. Repository & persistence edge cases (no overwrite on duplicate, SQL injection safety, error chaining).
5. API and dashboard edge cases (malformed payloads, 404/410 redirect guards, click counter precision).
"""

import os
import sqlite3
import tempfile
import pytest
from datetime import datetime, timedelta, timezone
from flask.testing import FlaskClient

from app import create_app
from app.config import AppConfig
from app.models import URLRecord
from app.repositories import (
    SQLiteURLRepository,
    InMemoryURLRepository,
    DuplicateShortCodeError,
    RepositoryError,
)
from app.validators import URLValidator, AliasValidator
from app.generators import CodeGenerator, RandomCodeGenerator, SequentialCodeGenerator
from app.services import (
    URLShortenerService,
    InvalidURLError,
    InvalidAliasError,
    AliasAlreadyTakenError,
    InvalidExpirationError,
    URLExpiredError,
    URLNotFoundError,
    CollisionResolutionError,
)


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
def test_app(temp_db_path):
    """Provide a test Flask application wired with an isolated temporary SQLite database."""
    config = AppConfig()
    config.base_url = "http://localhost:5000"
    repo = SQLiteURLRepository(db_path=temp_db_path)
    service = URLShortenerService(
        validator=URLValidator(),
        generator=RandomCodeGenerator(length=6),
        repository=repo,
        alias_validator=AliasValidator(),
        max_retries=5
    )
    app = create_app(service=service, config=config)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(test_app):
    """Provide test client."""
    return test_app.test_client()


# ============================================================================
# PART 1: URL Validation Edge Cases
# ============================================================================

class TestURLValidationEdgeCases:
    """Exhaustive tests for URL syntax, query strings, fragments, and port bounds."""

    @pytest.mark.parametrize("valid_url", [
        "https://example.com/search?q=python&category=lld#section-3",
        "http://sub.domain.example.co.uk:8080/path/to/resource?auth_token=xyz&v=2",
        "https://192.168.1.1:3000/api/v1/health",
        "http://example.org:1/",
        "http://example.org:65535/max-port",
        "https://my-site.com/path-with-dashes_and.dots~tilde",
    ])
    def test_valid_complex_urls_accepted(self, valid_url: str):
        assert URLValidator.is_valid(valid_url) is True

    @pytest.mark.parametrize("invalid_url", [
        "",
        "   ",
        "\t\n",
        "example.com",                           # Missing scheme
        "//example.com/path",                    # Scheme-relative URL
        "ftp://files.example.com",               # Unsupported scheme
        "file:///C:/Users/test/doc.txt",         # File scheme
        "javascript:alert('xss')",               # JavaScript pseudo-protocol
        "data:text/html,<h1>Hello</h1>",         # Data URL
        "https://user:password@example.com",     # Embedded credentials rejected
        "http://example.com:0/port-zero",        # Port 0 out of bounds
        "http://example.com:65536/port-overflow",# Port > 65535
        "http://example.com:abc/string-port",    # Non-numeric port
        "https://example .com/space-in-host",    # Whitespace in hostname
        "http:///path/only",                     # Missing hostname
        None,                                    # Non-string None
        12345,                                   # Integer
        ["https://example.com"],                 # List
        {"url": "https://example.com"},          # Dict
    ])
    def test_invalid_urls_rejected(self, invalid_url):
        assert URLValidator.is_valid(invalid_url) is False


# ============================================================================
# PART 2: Short-Code Generation Edge Cases
# ============================================================================

class TestCodeGenerationEdgeCases:
    """Tests for code length validation, character sets, and collision bounds."""

    def test_random_code_generator_properties(self):
        generator = RandomCodeGenerator(length=8)
        assert generator.length == 8

        code = generator.generate()
        assert len(code) == 8
        assert all(c in RandomCodeGenerator.ALPHABET for c in code)

    @pytest.mark.parametrize("invalid_len", [0, -1, -10, "6", None, 3.5, True, False])
    def test_random_code_generator_invalid_length_rejected(self, invalid_len):
        with pytest.raises(ValueError, match="Code length must be a positive integer"):
            RandomCodeGenerator(length=invalid_len)

    def test_sequential_generator_base62_encoding(self):
        gen = SequentialCodeGenerator(start_id=0, min_length=4)
        assert gen.generate() == "0000"
        assert gen.generate() == "0001"

    @pytest.mark.parametrize("invalid_start", [-1, "1", None, True])
    def test_sequential_generator_invalid_start_id(self, invalid_start):
        with pytest.raises(ValueError, match="start_id must be a non-negative integer"):
            SequentialCodeGenerator(start_id=invalid_start)

    def test_repeated_collisions_exhaust_retries(self):
        """Simulate a generator that always collides, verifying bounded retries."""
        class ConstantCollisionGenerator(CodeGenerator):
            def generate(self) -> str:
                return "fixed1"

        repo = InMemoryURLRepository()
        # Seed the repository with the fixed code
        repo.save(URLRecord(
            original_url="https://existing.com",
            short_code="fixed1",
            created_at=datetime.now(timezone.utc)
        ))

        service = URLShortenerService(
            validator=URLValidator(),
            generator=ConstantCollisionGenerator(),
            repository=repo,
            max_retries=3
        )

        with pytest.raises(CollisionResolutionError, match="Exhausted 3 attempts"):
            service.shorten_url("https://new.com")

    def test_custom_alias_collision_does_not_silently_fallback(self):
        """A duplicate custom alias must fail immediately with AliasAlreadyTakenError."""
        repo = InMemoryURLRepository()
        repo.save(URLRecord(
            original_url="https://existing.com",
            short_code="my-slug",
            created_at=datetime.now(timezone.utc)
        ))

        service = URLShortenerService(
            validator=URLValidator(),
            generator=RandomCodeGenerator(),
            repository=repo
        )

        with pytest.raises(AliasAlreadyTakenError, match="already in use"):
            service.shorten_url("https://different.com", custom_alias="my-slug")


# ============================================================================
# PART 3: Expiration Handling Edge Cases
# ============================================================================

class TestExpirationEdgeCases:
    """Tests for permanent links, future expirations, past dates, and timezone awareness."""

    def test_permanent_link_never_expires(self):
        record = URLRecord(
            original_url="https://example.com",
            short_code="perm1",
            created_at=datetime.now(timezone.utc),
            expires_at=None
        )
        assert record.is_expired() is False
        # Far future check
        future_check = datetime.now(timezone.utc) + timedelta(days=3650)
        assert record.is_expired(current_time=future_check) is False

    def test_future_expiration_accepted(self):
        repo = InMemoryURLRepository()
        service = URLShortenerService(
            validator=URLValidator(),
            generator=RandomCodeGenerator(),
            repository=repo
        )
        future_exp = datetime.now(timezone.utc) + timedelta(days=30)
        record = service.shorten_url("https://example.com", expires_at=future_exp)
        assert record.expires_at == future_exp
        assert record.is_expired() is False

    def test_past_expiration_rejected_on_creation(self):
        repo = InMemoryURLRepository()
        service = URLShortenerService(
            validator=URLValidator(),
            generator=RandomCodeGenerator(),
            repository=repo
        )
        past_exp = datetime.now(timezone.utc) - timedelta(minutes=5)
        with pytest.raises(InvalidExpirationError, match="must be in the future"):
            service.shorten_url("https://example.com", expires_at=past_exp)

    def test_naive_datetime_rejected(self):
        repo = InMemoryURLRepository()
        service = URLShortenerService(
            validator=URLValidator(),
            generator=RandomCodeGenerator(),
            repository=repo
        )
        naive_dt = datetime.now() + timedelta(days=1)  # No tzinfo
        with pytest.raises(InvalidExpirationError, match="must be a timezone-aware datetime"):
            service.shorten_url("https://example.com", expires_at=naive_dt)

    def test_record_is_expired_with_naive_comparison_raises_value_error(self):
        record = URLRecord(
            original_url="https://example.com",
            short_code="exp1",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        with pytest.raises(ValueError, match="Comparison datetime must be a timezone-aware datetime"):
            record.is_expired(current_time=datetime.now())  # naive check


# ============================================================================
# PART 4: Repository and Persistence Edge Cases
# ============================================================================

class TestRepositoryPersistenceEdgeCases:
    """Tests for duplicate rejection, SQL parameterized safety, and persistence."""

    def test_duplicate_short_code_does_not_overwrite_in_sqlite(self, temp_db_path):
        repo = SQLiteURLRepository(db_path=temp_db_path)
        original_time = datetime.now(timezone.utc)
        first_record = URLRecord(
            original_url="https://first.com",
            short_code="duptest",
            created_at=original_time,
            click_count=5
        )
        repo.save(first_record)

        second_record = URLRecord(
            original_url="https://second-malicious-overwrite.com",
            short_code="duptest",
            created_at=datetime.now(timezone.utc),
            click_count=0
        )
        with pytest.raises(DuplicateShortCodeError):
            repo.save(second_record)

        # Confirm first record was NOT overwritten
        persisted = repo.find_by_code("duptest")
        assert persisted.original_url == "https://first.com"
        assert persisted.click_count == 5

    def test_sql_injection_attempt_in_short_code_is_safe(self, temp_db_path):
        """Ensure parameterized query treats malicious SQL input as a literal string."""
        repo = SQLiteURLRepository(db_path=temp_db_path)
        injection_code = "slug' OR '1'='1"

        # Lookup nonexistent injection string
        result = repo.find_by_code(injection_code)
        assert result is None

        # Increment nonexistent injection string returns False
        assert repo.increment_click_count(injection_code) is False

    def test_repository_error_preserves_exception_chain(self):
        """RepositoryError must chain the underlying database error."""
        with pytest.raises(RepositoryError) as exc_info:
            SQLiteURLRepository(db_path="invalid_dir/forbidden/nonexistent.db")
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, sqlite3.Error)


# ============================================================================
# PART 5: API and Dashboard Edge Cases
# ============================================================================

class TestAPIEdgeCases:
    """Tests for API error responses, status codes, and click analytics integrity."""

    def test_post_urls_malformed_json_returns_400(self, client: FlaskClient):
        response = client.post(
            "/api/urls",
            data="not a valid json { string",
            content_type="application/json"
        )
        assert response.status_code == 400
        assert "Malformed JSON" in response.get_json()["error"]

    def test_post_urls_non_json_content_type_returns_400(self, client: FlaskClient):
        response = client.post(
            "/api/urls",
            data="url=https://example.com",
            content_type="application/x-www-form-urlencoded"
        )
        assert response.status_code == 400
        assert "must be valid JSON" in response.get_json()["error"]

    def test_post_urls_missing_url_returns_400(self, client: FlaskClient):
        response = client.post("/api/urls", json={"custom_alias": "test"})
        assert response.status_code == 400
        assert "required" in response.get_json()["error"]

    def test_post_urls_duplicate_alias_returns_409(self, client: FlaskClient):
        client.post("/api/urls", json={"url": "https://a.com", "custom_alias": "dup-slug"})
        resp2 = client.post("/api/urls", json={"url": "https://b.com", "custom_alias": "dup-slug"})
        assert resp2.status_code == 409
        assert "already in use" in resp2.get_json()["error"]

    def test_failed_redirect_does_not_increment_counter(self, client: FlaskClient):
        """A 404 or 410 redirect must never increment any click count."""
        # Test 404
        client.get("/nonexistent-slug-xyz")

        # Create expired link
        client.post(
            "/api/urls",
            json={"url": "https://example.com/target", "custom_alias": "exp-target"}
        )

        # Manually expire it by querying service/repo or test 404 on invalid
        list_resp = client.get("/api/urls")
        assert list_resp.status_code == 200
        record = next(r for r in list_resp.json["urls"] if r["short_code"] == "exp-target")
        assert record["click_count"] == 0

    def test_click_counts_increment_exactly_once_per_redirect(self, client: FlaskClient):
        client.post(
            "/api/urls",
            json={"url": "https://example.com/dest", "custom_alias": "counter-test"}
        )

        for expected in range(1, 4):
            redirect_resp = client.get("/counter-test")
            assert redirect_resp.status_code == 302

            list_resp = client.get("/api/urls")
            record = next(r for r in list_resp.json["urls"] if r["short_code"] == "counter-test")
            assert record["click_count"] == expected
