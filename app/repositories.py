"""
Repository abstractions and in-memory storage for LinkForge URL Shortener.

This module implements the Repository Pattern to mediate between the domain
layer and data mapping layers, adhering to the Dependency Inversion Principle (DIP).
"""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from typing import Generator
from app.models import URLRecord


class RepositoryError(Exception):
    """Base exception for repository-related failures."""
    pass


class DuplicateShortCodeError(RepositoryError):
    """
    Raised when attempting to insert a URLRecord whose short_code is already registered.
    Prevents silent collision and accidental data overwriting.
    """
    pass


class URLRepository(ABC):
    """
    Abstract contract for URLRecord persistence operations.

    By depending on this interface rather than a concrete storage engine,
    business logic remains agnostic of whether data is stored in memory,
    SQLite, PostgreSQL, or Redis.
    """

    @abstractmethod
    def save(self, record: URLRecord) -> None:
        """
        Persist a new URLRecord.

        Args:
            record (URLRecord): The domain entity to store.

        Raises:
            DuplicateShortCodeError: If a record with the same short_code already exists.
        """
        pass

    @abstractmethod
    def find_by_code(self, short_code: str) -> URLRecord | None:
        """
        Look up a URLRecord by its unique short code.

        Args:
            short_code (str): The alphanumeric code to look up.

        Returns:
            URLRecord | None: The matching record if found; None otherwise.
        """
        pass

    @abstractmethod
    def delete(self, short_code: str) -> bool:
        """
        Remove a URLRecord by its short code.

        Args:
            short_code (str): The alphanumeric code of the record to delete.

        Returns:
            bool: True if the record existed and was deleted; False if not found.
        """
        pass


    @abstractmethod
    def list_all(self) -> list[URLRecord]:
        """
        Retrieve all stored URL records.

        Returns:
            list[URLRecord]: List of all domain entities in storage.
        """
        pass

    @abstractmethod
    def increment_click_count(self, short_code: str) -> bool:
        """
        Increment the click counter for the specified short code.

        Args:
            short_code (str): The identifier of the URLRecord to update.

        Returns:
            bool: True if the record was found and updated, False otherwise.
        """
        pass


class InMemoryURLRepository(URLRepository):
    """
    In-memory implementation of URLRepository using a Python dictionary.

    Characteristics:
        - O(1) average-time complexity for lookups, insertions, and deletions.
        - Volatile: all data is lost when the application process terminates.
        - Perfect for unit testing, fast prototyping, and local development.
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory hash store."""
        self._storage: dict[str, URLRecord] = {}

    def save(self, record: URLRecord) -> None:
        """
        Save a URLRecord to memory.

        Raises:
            DuplicateShortCodeError: If `record.short_code` already exists in storage.
        """
        if record.short_code in self._storage:
            raise DuplicateShortCodeError(
                f"Conflict: Short code '{record.short_code}' is already registered."
            )
        self._storage[record.short_code] = record

    def find_by_code(self, short_code: str) -> URLRecord | None:
        """Retrieve a URLRecord by its short_code, or None if not found."""
        return self._storage.get(short_code)

    def delete(self, short_code: str) -> bool:
        """Delete a record by its short_code. Return True if deleted, False otherwise."""
        if short_code in self._storage:
            del self._storage[short_code]
            return True
        return False

    def list_all(self) -> list[URLRecord]:
        """Retrieve all stored URL records."""
        return list(self._storage.values())

    def increment_click_count(self, short_code: str) -> bool:
        """Increment click count for an in-memory record."""
        record = self._storage.get(short_code)
        if record is not None:
            record.click_count += 1
            return True
        return False

    def __len__(self) -> int:
        """Return the count of stored records."""
        return len(self._storage)


class SQLiteURLRepository(URLRepository):
    """
    Persistent SQLite implementation of URLRepository.

    Characteristics:
        - Durable: Data persists across application and server restarts.
        - Relational Integrity: Enforces unique short_code constraints at the database engine level.
        - Injection-Safe: Strictly uses parameterized queries.
        - Thread-Safe: Opens per-operation scoped connections to prevent multi-threading errors.
    """

    def __init__(self, db_path: str = "linkforge.db") -> None:
        """
        Initialize the SQLite repository.

        Args:
            db_path (str): Filepath to the SQLite database file, or ':memory:'.
        """
        self._db_path = db_path
        self._init_db()

    @property
    def db_path(self) -> str:
        """Return the configured SQLite database file path."""
        return self._db_path

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager yielding a configured SQLite connection and ensuring it is closed.

        Yields:
            sqlite3.Connection: Scoped SQLite connection instance.
        """
        try:
            conn = sqlite3.connect(self._db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as err:
            raise RepositoryError(f"Failed to connect to SQLite database at '{self._db_path}': {err}") from err

        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create the urls table if it does not already exist."""
        schema = """
            CREATE TABLE IF NOT EXISTS urls (
                short_code TEXT PRIMARY KEY,
                original_url TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                click_count INTEGER NOT NULL DEFAULT 0
            )
        """
        try:
            with self._get_connection() as conn:
                conn.execute(schema)
        except sqlite3.Error as err:
            raise RepositoryError(f"Database schema initialization failed: {err}") from err

    def save(self, record: URLRecord) -> None:
        """
        Persist a URLRecord to SQLite.

        Raises:
            DuplicateShortCodeError: If short_code violates the PRIMARY KEY constraint.
            RepositoryError: For any other database I/O or syntax errors.
        """
        created_at_iso = record.created_at.astimezone(timezone.utc).isoformat()
        expires_at_iso = (
            record.expires_at.astimezone(timezone.utc).isoformat()
            if record.expires_at is not None
            else None
        )

        query = """
            INSERT INTO urls (short_code, original_url, created_at, expires_at, click_count)
            VALUES (?, ?, ?, ?, ?)
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    query,
                    (
                        record.short_code,
                        record.original_url,
                        created_at_iso,
                        expires_at_iso,
                        record.click_count,
                    ),
                )
        except sqlite3.IntegrityError as err:
            # Database engine enforced uniqueness constraint violation
            raise DuplicateShortCodeError(
                f"Conflict: Short code '{record.short_code}' is already registered in SQLite."
            ) from err
        except sqlite3.Error as err:
            raise RepositoryError(f"Failed to save URLRecord to SQLite: {err}") from err

    def find_by_code(self, short_code: str) -> URLRecord | None:
        """
        Look up a URLRecord by its short code.

        Returns:
            URLRecord | None: The matching record if found; None otherwise.
        """
        query = """
            SELECT short_code, original_url, created_at, expires_at, click_count
            FROM urls
            WHERE short_code = ?
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, (short_code,))
                row = cursor.fetchone()
                if row is None:
                    return None

                created_at = datetime.fromisoformat(row["created_at"])
                expires_at = (
                    datetime.fromisoformat(row["expires_at"])
                    if row["expires_at"] is not None
                    else None
                )

                return URLRecord(
                    original_url=row["original_url"],
                    short_code=row["short_code"],
                    created_at=created_at,
                    expires_at=expires_at,
                    click_count=row["click_count"],
                )
        except sqlite3.Error as err:
            raise RepositoryError(f"Failed to query SQLite for code '{short_code}': {err}") from err

    def delete(self, short_code: str) -> bool:
        """
        Delete a URLRecord by its short code.

        Returns:
            bool: True if a record was deleted, False if no matching record existed.
        """
        query = "DELETE FROM urls WHERE short_code = ?"
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, (short_code,))
                return cursor.rowcount > 0
        except sqlite3.Error as err:
            raise RepositoryError(f"Failed to delete short code '{short_code}' from SQLite: {err}") from err

    def list_all(self) -> list[URLRecord]:
        """
        Retrieve all URL records ordered by creation date descending.

        Returns:
            list[URLRecord]: List of all persisted domain entities.
        """
        query = """
            SELECT short_code, original_url, created_at, expires_at, click_count
            FROM urls
            ORDER BY created_at DESC
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query)
                records: list[URLRecord] = []
                for row in cursor.fetchall():
                    created_at = datetime.fromisoformat(row["created_at"])
                    expires_at = (
                        datetime.fromisoformat(row["expires_at"])
                        if row["expires_at"] is not None
                        else None
                    )
                    records.append(
                        URLRecord(
                            original_url=row["original_url"],
                            short_code=row["short_code"],
                            created_at=created_at,
                            expires_at=expires_at,
                            click_count=row["click_count"],
                        )
                    )
                return records
        except sqlite3.Error as err:
            raise RepositoryError(f"Failed to list records from SQLite: {err}") from err

    def increment_click_count(self, short_code: str) -> bool:
        """
        Atomically increment the click count in SQLite.

        Args:
            short_code (str): The short slug to increment.

        Returns:
            bool: True if the record was found and updated, False otherwise.
        """
        query = "UPDATE urls SET click_count = click_count + 1 WHERE short_code = ?"
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, (short_code,))
                return cursor.rowcount > 0
        except sqlite3.Error as err:
            raise RepositoryError(f"Failed to increment click count for '{short_code}': {err}") from err

    def __len__(self) -> int:
        """Return total count of persisted records."""
        query = "SELECT COUNT(*) FROM urls"
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query)
                return int(cursor.fetchone()[0])
        except sqlite3.Error as err:
            raise RepositoryError(f"Failed to count records in SQLite: {err}") from err

