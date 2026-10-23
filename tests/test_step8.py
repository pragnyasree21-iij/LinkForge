"""
Unit tests for Step 8: Expiration, Custom Aliases, and Edge-Case Handling.
"""

from datetime import datetime, timedelta, timezone
import pytest

from app.models import URLRecord
from app.validators import URLValidator, AliasValidator
from app.generators import CodeGenerator, RandomCodeGenerator
from app.repositories import InMemoryURLRepository
from app.services import (
    URLShortenerService,
    InvalidURLError,
    InvalidAliasError,
    AliasAlreadyTakenError,
    InvalidExpirationError,
    URLExpiredError,
    URLNotFoundError,
)


class DummyCodeGenerator(CodeGenerator):
    """Predictable generator for testing."""

    def __init__(self, code: str = "gen123") -> None:
        self.code = code

    def generate(self) -> str:
        return self.code


@pytest.fixture
def service() -> URLShortenerService:
    return URLShortenerService(
        validator=URLValidator(),
        generator=DummyCodeGenerator("fixed1"),
        repository=InMemoryURLRepository(),
    )


class TestAliasValidator:
    """Tests for AliasValidator."""

    @pytest.mark.parametrize(
        "valid_alias",
        ["my-portfolio", "project_2026", "link123", "abc", "A_B-c-99"],
    )
    def test_valid_aliases(self, valid_alias: str):
        assert AliasValidator.is_valid(valid_alias) is True

    @pytest.mark.parametrize(
        "invalid_alias",
        [
            "",
            "   ",
            "ab",  # too short (< 3)
            "a" * 31,  # too long (> 30)
            "has space",
            "special!char",
            "slash/in/slug",
            "dot.in.slug",
            "admin",  # reserved
            "ADMIN",  # reserved (case-insensitive)
            "api",  # reserved
            "health",  # reserved
            "static",  # reserved
            123,  # non-string
            None,  # non-string
        ],
    )
    def test_invalid_aliases(self, invalid_alias):
        assert AliasValidator.is_valid(invalid_alias) is False  # type: ignore[arg-type]


class TestExpirationHandling:
    """Tests for link expiration and timestamps."""

    def test_create_link_without_expiration(self, service: URLShortenerService):
        """Links without expiration never expire."""
        record = service.shorten_url("https://python.org")
        assert record.expires_at is None
        assert record.is_expired() is False
        assert service.get_original_url(record.short_code) == "https://python.org"

    def test_create_link_with_future_expiration(self, service: URLShortenerService):
        """Links with future expiration remain active."""
        future_time = datetime.now(timezone.utc) + timedelta(days=7)
        record = service.shorten_url("https://python.org", expires_at=future_time)

        assert record.expires_at == future_time
        assert record.is_expired() is False
        assert service.get_original_url(record.short_code) == "https://python.org"

    def test_reject_past_expiration(self, service: URLShortenerService):
        """Reject expiration timestamps already in the past."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        with pytest.raises(InvalidExpirationError, match="must be in the future"):
            service.shorten_url("https://python.org", expires_at=past_time)

    def test_reject_naive_datetime(self, service: URLShortenerService):
        """Reject naive datetimes missing timezone information."""
        naive_time = datetime.now() + timedelta(days=1)  # No tzinfo!
        with pytest.raises(InvalidExpirationError, match="must be a timezone-aware datetime"):
            service.shorten_url("https://python.org", expires_at=naive_time)

    def test_reject_non_datetime_type(self, service: URLShortenerService):
        """Reject non-datetime types passed as expires_at."""
        with pytest.raises(InvalidExpirationError, match="must be an instance of datetime"):
            service.shorten_url("https://python.org", expires_at="2026-12-31")  # type: ignore[arg-type]

    def test_retrieve_expired_link_raises_url_expired_error(self, service: URLShortenerService):
        """When an expiration date is reached, retrieval raises URLExpiredError."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        record = service.shorten_url("https://python.org", expires_at=future_time)

        # Simulate accessing after expiration using current_time parameter
        simulated_future = future_time + timedelta(seconds=1)
        with pytest.raises(URLExpiredError, match="has expired"):
            service.get_original_url(record.short_code, current_time=simulated_future)


class TestCustomAliases:
    """Tests for custom alias creation and conflict handling."""

    def test_create_with_valid_custom_alias(self, service: URLShortenerService):
        """User can specify their own custom alias."""
        record = service.shorten_url("https://github.com", custom_alias="my-repo_2026")
        assert record.short_code == "my-repo_2026"
        assert service.get_original_url("my-repo_2026") == "https://github.com"

    @pytest.mark.parametrize(
        "bad_alias",
        ["", "a", "ab", "a" * 35, "bad alias", "admin", "API", "static", "login"],
    )
    def test_create_with_invalid_alias_raises_invalid_alias_error(
        self, service: URLShortenerService, bad_alias: str
    ):
        with pytest.raises(InvalidAliasError, match="Invalid custom alias"):
            service.shorten_url("https://github.com", custom_alias=bad_alias)

    def test_duplicate_custom_alias_raises_alias_already_taken_error(
        self, service: URLShortenerService
    ):
        """If an alias is taken, raise AliasAlreadyTakenError immediately without retrying."""
        service.shorten_url("https://first.com", custom_alias="taken-slug")

        with pytest.raises(AliasAlreadyTakenError, match="already in use"):
            service.shorten_url("https://second.com", custom_alias="taken-slug")

        # Confirm original destination is unchanged
        assert service.get_original_url("taken-slug") == "https://first.com"


class TestEdgeCases:
    """Tests for all other edge cases."""

    def test_deleted_link_raises_url_not_found(self, service: URLShortenerService):
        """Deleting a short link causes subsequent lookups to raise URLNotFoundError."""
        record = service.shorten_url("https://deleteme.com", custom_alias="to-delete")
        assert service.get_original_url("to-delete") == "https://deleteme.com"

        # Delete from repository
        service._repository.delete("to-delete")

        with pytest.raises(URLNotFoundError):
            service.get_original_url("to-delete")
