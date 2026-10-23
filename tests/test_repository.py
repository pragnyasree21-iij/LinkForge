"""
Unit tests for URLRepository abstraction and InMemoryURLRepository.
"""

import pytest
from app.models import URLRecord
from app.repositories import URLRepository, InMemoryURLRepository, DuplicateShortCodeError


class TestURLRepositoryAbstraction:
    """Verifies the abstract contract of URLRepository."""

    def test_cannot_instantiate_abstract_repository(self):
        """Ensure URLRepository cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class URLRepository"):
            URLRepository()  # type: ignore[abstract]


class TestInMemoryURLRepository:
    """Tests for InMemoryURLRepository."""

    @pytest.fixture
    def repo(self) -> InMemoryURLRepository:
        """Provide a fresh, isolated in-memory repository for each test."""
        return InMemoryURLRepository()

    @pytest.fixture
    def sample_record(self) -> URLRecord:
        """Provide a sample URLRecord."""
        return URLRecord(
            original_url="https://docs.python.org/3/",
            short_code="py-docs"
        )

    def test_save_and_retrieve_record(self, repo: InMemoryURLRepository, sample_record: URLRecord):
        """Verify that a saved record can be retrieved by its short code."""
        repo.save(sample_record)
        found = repo.find_by_code("py-docs")

        assert found is not None
        assert found.short_code == "py-docs"
        assert found.original_url == "https://docs.python.org/3/"
        assert found == sample_record

    def test_find_by_code_returns_none_for_unknown_code(self, repo: InMemoryURLRepository):
        """Verify that searching for an unregistered short code returns None."""
        assert repo.find_by_code("nonexistent") is None

    def test_rejects_duplicate_short_code(self, repo: InMemoryURLRepository, sample_record: URLRecord):
        """Verify that saving a duplicate short code raises DuplicateShortCodeError."""
        repo.save(sample_record)

        duplicate_record = URLRecord(
            original_url="https://different-destination.com",
            short_code="py-docs"  # Same code!
        )

        with pytest.raises(DuplicateShortCodeError, match="already registered"):
            repo.save(duplicate_record)

    def test_duplicate_save_does_not_overwrite_original_record(
        self, repo: InMemoryURLRepository, sample_record: URLRecord
    ):
        """Verify that a rejected duplicate does not modify or overwrite the original record."""
        repo.save(sample_record)

        duplicate_record = URLRecord(
            original_url="https://malicious-hijack.com",
            short_code="py-docs"
        )

        with pytest.raises(DuplicateShortCodeError):
            repo.save(duplicate_record)

        # Confirm the stored record is still the original untouched one
        persisted = repo.find_by_code("py-docs")
        assert persisted is not None
        assert persisted.original_url == "https://docs.python.org/3/"
        assert persisted.original_url != "https://malicious-hijack.com"

    def test_delete_existing_record_returns_true(
        self, repo: InMemoryURLRepository, sample_record: URLRecord
    ):
        """Verify that deleting an existing record removes it and returns True."""
        repo.save(sample_record)
        assert len(repo) == 1

        deleted = repo.delete("py-docs")
        assert deleted is True
        assert len(repo) == 0
        assert repo.find_by_code("py-docs") is None

    def test_delete_nonexistent_code_returns_false(self, repo: InMemoryURLRepository):
        """Verify that attempting to delete a nonexistent short code returns False."""
        assert repo.delete("ghost-code") is False
