"""
Unit tests for URLShortenerService.
Demonstrates deterministic testing using test doubles and dependency injection.
"""

import pytest
from app.models import URLRecord
from app.validators import URLValidator
from app.generators import CodeGenerator
from app.repositories import URLRepository, InMemoryURLRepository, DuplicateShortCodeError
from app.services import (
    URLShortenerService,
    InvalidURLError,
    URLNotFoundError,
    CollisionResolutionError,
)


class DeterministicCodeGenerator(CodeGenerator):
    """
    Test double (stub/fake) for CodeGenerator.
    Yields predefined codes sequentially for deterministic collision testing.
    """

    def __init__(self, codes: list[str]) -> None:
        self._codes: list[str] = list(codes)
        self._call_count: int = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def generate(self) -> str:
        self._call_count += 1
        if not self._codes:
            raise RuntimeError("Exhausted predefined test codes.")
        return self._codes.pop(0)


class FailingRepository(URLRepository):
    """
    Test double for simulating fatal non-collision storage failures
    (e.g., disk full, network timeout).
    """

    def save(self, record: URLRecord) -> None:
        raise OSError("Simulated hardware I/O error while writing to disk.")

    def find_by_code(self, short_code: str) -> URLRecord | None:
        return None

    def delete(self, short_code: str) -> bool:
        return False

    def list_all(self) -> list[URLRecord]:
        return []

    def increment_click_count(self, short_code: str) -> bool:
        return False


class TestURLShortenerService:
    """Test suite covering the complete workflow of URLShortenerService."""

    @pytest.fixture
    def validator(self) -> URLValidator:
        return URLValidator()

    @pytest.fixture
    def repository(self) -> InMemoryURLRepository:
        return InMemoryURLRepository()

    def test_shorten_valid_url_success(self, validator: URLValidator, repository: InMemoryURLRepository):
        """Verify that a valid URL is shortened, saved, and returned."""
        generator = DeterministicCodeGenerator(["code123"])
        service = URLShortenerService(validator, generator, repository)

        record = service.shorten_url("https://www.python.org")

        assert isinstance(record, URLRecord)
        assert record.original_url == "https://www.python.org"
        assert record.short_code == "code123"
        assert record.click_count == 0
        assert record.expires_at is None
        assert record.created_at.tzinfo is not None

        # Confirm the record was actually persisted to the repository
        saved = repository.find_by_code("code123")
        assert saved == record

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "",
            "   ",
            "not-a-url",
            "ftp://example.com",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "https://user:pass@example.com",
            "https://example.com:99999",
            123,
            None,
        ],
    )
    def test_shorten_invalid_url_raises_invalid_url_error(
        self, validator: URLValidator, repository: InMemoryURLRepository, invalid_url
    ):
        """Verify that any invalid URL raises InvalidURLError without calling generator or repo."""
        generator = DeterministicCodeGenerator(["dummy"])
        service = URLShortenerService(validator, generator, repository)

        with pytest.raises(InvalidURLError, match="Invalid URL provided"):
            service.shorten_url(invalid_url)  # type: ignore[arg-type]

        # Ensure generator was never called for invalid inputs
        assert generator.call_count == 0

    def test_get_original_url_success(self, validator: URLValidator, repository: InMemoryURLRepository):
        """Verify that an existing short code returns the original long URL."""
        generator = DeterministicCodeGenerator(["target1"])
        service = URLShortenerService(validator, generator, repository)

        service.shorten_url("https://fastapi.tiangolo.com")
        retrieved_url = service.get_original_url("target1")

        assert retrieved_url == "https://fastapi.tiangolo.com"

    def test_get_original_url_unknown_code_raises_url_not_found_error(
        self, validator: URLValidator, repository: InMemoryURLRepository
    ):
        """Verify that looking up a nonexistent code raises URLNotFoundError."""
        generator = DeterministicCodeGenerator(["dummy"])
        service = URLShortenerService(validator, generator, repository)

        with pytest.raises(URLNotFoundError, match="does not exist"):
            service.get_original_url("unknown99")

    def test_collision_triggers_retry_and_succeeds(
        self, validator: URLValidator, repository: InMemoryURLRepository
    ):
        """
        Verify that when a generated code already exists in the repository,
        the service catches DuplicateShortCodeError and retries with a new code.
        """
        # Pre-seed the repository with an existing record using code 'collide1'
        repository.save(
            URLRecord(original_url="https://existing-site.com", short_code="collide1")
        )

        # Generator produces 'collide1' first (will collide), then 'unique2' (succeeds)
        generator = DeterministicCodeGenerator(["collide1", "unique2"])
        service = URLShortenerService(validator, generator, repository, max_retries=3)

        record = service.shorten_url("https://new-destination.com")

        assert record.short_code == "unique2"
        assert generator.call_count == 2
        # Verify original record was unharmed
        assert repository.find_by_code("collide1").original_url == "https://existing-site.com"

    def test_repeated_collisions_exhaust_retries_and_raise_exception(
        self, validator: URLValidator, repository: InMemoryURLRepository
    ):
        """
        Verify that if all collision retry attempts fail, CollisionResolutionError is raised.
        """
        # Pre-seed repository with colliding code
        repository.save(
            URLRecord(original_url="https://existing-site.com", short_code="collideX")
        )

        # Generator yields colliding code 3 times
        generator = DeterministicCodeGenerator(["collideX", "collideX", "collideX"])
        service = URLShortenerService(validator, generator, repository, max_retries=3)

        with pytest.raises(CollisionResolutionError, match="Exhausted 3 attempts"):
            service.shorten_url("https://another-site.com")

        assert generator.call_count == 3

    def test_non_collision_repository_error_is_not_swallowed(
        self, validator: URLValidator
    ):
        """
        Verify that unrelated repository errors (like I/O or network failures)
        propagate immediately and are NOT caught as collision retries.
        """
        generator = DeterministicCodeGenerator(["code123"])
        failing_repo = FailingRepository()
        service = URLShortenerService(validator, generator, failing_repo, max_retries=5)

        with pytest.raises(OSError, match="Simulated hardware I/O error"):
            service.shorten_url("https://valid-target.com")

        # Must have failed on the very first attempt without looping through retries
        assert generator.call_count == 1
