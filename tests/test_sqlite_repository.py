"""
Unit and integration tests for SQLiteURLRepository.
Tests persistence, transactions, duplicate prevention, and compatibility with URLShortenerService.
"""

from datetime import datetime, timedelta, timezone
import os
import tempfile
import pytest

from app.models import URLRecord
from app.validators import URLValidator
from app.generators import RandomCodeGenerator
from app.repositories import URLRepository, SQLiteURLRepository, DuplicateShortCodeError
from app.services import URLShortenerService


@pytest.fixture
def temp_db_path():
    """Provide a temporary SQLite database file path cleaned up after test execution."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture
def sqlite_repo(temp_db_path: str) -> SQLiteURLRepository:
    """Provide a fresh SQLiteURLRepository connected to a temporary database file."""
    return SQLiteURLRepository(db_path=temp_db_path)


class TestSQLiteURLRepository:
    """Tests for SQLiteURLRepository implementation."""

    def test_implements_repository_interface(self, sqlite_repo: SQLiteURLRepository):
        """Ensure SQLiteURLRepository fulfills the URLRepository contract."""
        assert isinstance(sqlite_repo, URLRepository)

    def test_save_and_retrieve_record(self, sqlite_repo: SQLiteURLRepository):
        """Verify saving and retrieving a permanent record with UTC timestamps."""
        record = URLRecord(
            original_url="https://www.sqlite.org/index.html",
            short_code="sqlite-home"
        )
        sqlite_repo.save(record)

        retrieved = sqlite_repo.find_by_code("sqlite-home")
        assert retrieved is not None
        assert retrieved.short_code == "sqlite-home"
        assert retrieved.original_url == "https://www.sqlite.org/index.html"
        assert retrieved.click_count == 0
        assert retrieved.expires_at is None
        assert retrieved.created_at.tzinfo is not None
        # ISO timestamp comparison
        assert retrieved.created_at.isoformat() == record.created_at.isoformat()

    def test_save_and_retrieve_with_expiration(self, sqlite_repo: SQLiteURLRepository):
        """Verify expiration timestamps roundtrip accurately with UTC timezone awareness."""
        exp_time = datetime.now(timezone.utc) + timedelta(days=30)
        record = URLRecord(
            original_url="https://temporary-event.com",
            short_code="temp-slug",
            expires_at=exp_time
        )
        sqlite_repo.save(record)

        retrieved = sqlite_repo.find_by_code("temp-slug")
        assert retrieved is not None
        assert retrieved.expires_at is not None
        assert retrieved.expires_at.tzinfo is not None
        assert retrieved.expires_at.isoformat() == exp_time.isoformat()

    def test_find_by_code_returns_none_for_missing(self, sqlite_repo: SQLiteURLRepository):
        """Verify searching for an unregistered short code returns None."""
        assert sqlite_repo.find_by_code("nonexistent") is None

    def test_duplicate_short_code_raises_duplicate_error(self, sqlite_repo: SQLiteURLRepository):
        """Verify that SQLite PRIMARY KEY constraint violation raises DuplicateShortCodeError."""
        record_1 = URLRecord(original_url="https://first.com", short_code="collision-key")
        sqlite_repo.save(record_1)

        record_2 = URLRecord(original_url="https://second.com", short_code="collision-key")
        with pytest.raises(DuplicateShortCodeError, match="already registered"):
            sqlite_repo.save(record_2)

    def test_duplicate_does_not_overwrite_original(self, sqlite_repo: SQLiteURLRepository):
        """Verify that a rejected duplicate does not overwrite the existing record."""
        record_1 = URLRecord(original_url="https://first.com", short_code="protected-key")
        sqlite_repo.save(record_1)

        record_2 = URLRecord(original_url="https://hijack.com", short_code="protected-key")
        with pytest.raises(DuplicateShortCodeError):
            sqlite_repo.save(record_2)

        persisted = sqlite_repo.find_by_code("protected-key")
        assert persisted is not None
        assert persisted.original_url == "https://first.com"
        assert persisted.original_url != "https://hijack.com"

    def test_delete_existing_record_returns_true(self, sqlite_repo: SQLiteURLRepository):
        """Verify deleting an existing record removes it and returns True."""
        record = URLRecord(original_url="https://delete.com", short_code="del-code")
        sqlite_repo.save(record)
        assert len(sqlite_repo) == 1

        assert sqlite_repo.delete("del-code") is True
        assert len(sqlite_repo) == 0
        assert sqlite_repo.find_by_code("del-code") is None

    def test_delete_nonexistent_record_returns_false(self, sqlite_repo: SQLiteURLRepository):
        """Verify deleting a nonexistent short code returns False."""
        assert sqlite_repo.delete("ghost-code") is False

    def test_persistence_across_separate_repository_instances(self, temp_db_path: str):
        """
        CRITICAL TEST: Verify durability across process/instance restarts.
        Instance A writes to the database file.
        Instance B opens the same database file and reads the persisted record.
        """
        # Session A: Save link
        repo_session_a = SQLiteURLRepository(db_path=temp_db_path)
        record = URLRecord(original_url="https://persistent.org", short_code="persist-slug")
        repo_session_a.save(record)
        del repo_session_a  # Simulate application shutdown

        # Session B: Re-open database file (Simulate application startup)
        repo_session_b = SQLiteURLRepository(db_path=temp_db_path)
        retrieved = repo_session_b.find_by_code("persist-slug")
        assert retrieved is not None
        assert retrieved.original_url == "https://persistent.org"
        assert retrieved.short_code == "persist-slug"

    def test_service_works_with_sqlite_dependency_injection(self, temp_db_path: str):
        """
        Verify that URLShortenerService functions seamlessly with SQLiteURLRepository
        injected via Dependency Inversion.
        """
        repo = SQLiteURLRepository(db_path=temp_db_path)
        service = URLShortenerService(
            validator=URLValidator(),
            generator=RandomCodeGenerator(length=6),
            repository=repo
        )

        record = service.shorten_url("https://kernel.org", custom_alias="linux-kernel")
        assert record.short_code == "linux-kernel"

        destination = service.get_original_url("linux-kernel")
        assert destination == "https://kernel.org"
