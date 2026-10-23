"""
Core application service layer for LinkForge URL Shortener.

This module orchestrates business workflows (validation, code generation, persistence,
collision resolution, custom aliases, and expiration lifecycle) relying on injected abstractions.
"""

from datetime import datetime, timezone
from app.models import URLRecord
from app.validators import URLValidator, AliasValidator
from app.generators import CodeGenerator
from app.repositories import URLRepository, DuplicateShortCodeError


class ServiceError(Exception):
    """Base exception for all service-layer domain errors."""
    pass


class InvalidURLError(ServiceError):
    """Raised when an input URL fails syntax or security validation."""
    pass


class InvalidAliasError(ServiceError):
    """Raised when a custom alias is empty, malformed, too short/long, or reserved."""
    pass


class AliasAlreadyTakenError(ServiceError):
    """Raised when a user-requested custom alias is already registered in the repository."""
    pass


class InvalidExpirationError(ServiceError):
    """Raised when an expiration timestamp is naive, malformed, or in the past."""
    pass


class URLExpiredError(ServiceError):
    """Raised when attempting to access a short link whose expiration timestamp has passed."""
    pass


class URLNotFoundError(ServiceError):
    """Raised when looking up an unregistered or nonexistent short code."""
    pass


class CollisionResolutionError(ServiceError):
    """Raised when unique code generation fails after exhausting max retries."""
    pass


class URLShortenerService:
    """
    Application Service coordinating the end-to-end URL shortening lifecycle.

    Design Principles:
        - Dependency Injection: Injected with validator, generator, and repository.
        - Single Responsibility: Orchestrates domain flow; does not parse URLs,
          generate random bytes, or manage SQL queries directly.
        - Dependency Inversion: Depends on abstract interfaces (CodeGenerator, URLRepository).
    """

    DEFAULT_MAX_RETRIES: int = 5

    def __init__(
        self,
        validator: URLValidator,
        generator: CodeGenerator,
        repository: URLRepository,
        max_retries: int = DEFAULT_MAX_RETRIES,
        alias_validator: AliasValidator | None = None,
    ) -> None:
        """
        Initialize the service with explicit dependencies.

        Args:
            validator (URLValidator): Strategy/service for checking destination URL syntax.
            generator (CodeGenerator): Strategy for generating short-code identifiers.
            repository (URLRepository): Persistence gateway for storing/retrieving records.
            max_retries (int): Maximum generation attempts when collisions occur.
            alias_validator (AliasValidator | None): Validator for custom user aliases.
        """
        self._validator: URLValidator = validator
        self._generator: CodeGenerator = generator
        self._repository: URLRepository = repository
        self._max_retries: int = max_retries
        self._alias_validator: AliasValidator = alias_validator or AliasValidator()

    def shorten_url(
        self,
        original_url: str,
        custom_alias: str | None = None,
        expires_at: datetime | None = None,
    ) -> URLRecord:
        """
        Shorten a given long URL and persist the resulting record.

        Workflow:
            1. Validate URL syntax and security constraints.
            2. Validate optional expiration timestamp (must be timezone-aware and in the future).
            3. If a custom alias is supplied:
               - Validate alias constraints (length, character set, reserved words).
               - Attempt to save with custom alias.
               - If duplicate, raise AliasAlreadyTakenError (DO NOT retry as random).
            4. If no custom alias is supplied:
               - Generate candidate code via injected CodeGenerator.
               - Construct URLRecord with timezone-aware UTC creation timestamp.
               - Attempt to persist via repository.
               - Retry on collision up to max_retries.
            5. Propagate any non-collision repository errors immediately.

        Args:
            original_url (str): The destination URL to shorten.
            custom_alias (str | None): Optional user-defined short slug.
            expires_at (datetime | None): Optional timezone-aware UTC expiration timestamp.

        Returns:
            URLRecord: The successfully persisted URL domain entity.

        Raises:
            InvalidURLError: If destination URL is malformed or invalid.
            InvalidExpirationError: If expiration timestamp is naive or in the past.
            InvalidAliasError: If custom alias violates syntax or reserved rules.
            AliasAlreadyTakenError: If custom alias already exists in storage.
            CollisionResolutionError: If random code generation exhausts max retries.
        """
        # 1. Validate original URL
        if not self._validator.is_valid(original_url):
            raise InvalidURLError(f"Invalid URL provided: {original_url!r}")

        # 2. Validate expiration timestamp if supplied
        if expires_at is not None:
            if not isinstance(expires_at, datetime):
                raise InvalidExpirationError("expires_at must be an instance of datetime.")
            if expires_at.tzinfo is None or expires_at.tzinfo.utcoffset(expires_at) is None:
                raise InvalidExpirationError(
                    "expires_at must be a timezone-aware datetime (UTC recommended)."
                )
            if expires_at <= datetime.now(timezone.utc):
                raise InvalidExpirationError(
                    f"Expiration timestamp must be in the future, got: {expires_at.isoformat()}"
                )

        # 3. Handle custom alias branch
        if custom_alias is not None:
            if not self._alias_validator.is_valid(custom_alias):
                raise InvalidAliasError(
                    f"Invalid custom alias '{custom_alias}'. Must be 3-30 characters "
                    "(letters, digits, hyphens, underscores) and not a system-reserved keyword."
                )

            record = URLRecord(
                original_url=original_url,
                short_code=custom_alias,
                created_at=datetime.now(timezone.utc),
                expires_at=expires_at,
            )
            try:
                self._repository.save(record)
                return record
            except DuplicateShortCodeError:
                raise AliasAlreadyTakenError(f"Custom alias '{custom_alias}' is already in use.")

        # 4. Handle random generation branch with retry loop
        for attempt in range(1, self._max_retries + 1):
            short_code = self._generator.generate()
            record = URLRecord(
                original_url=original_url,
                short_code=short_code,
                created_at=datetime.now(timezone.utc),
                expires_at=expires_at,
            )
            try:
                self._repository.save(record)
                return record
            except DuplicateShortCodeError:
                # Collision detected on random code: retry with new candidate
                continue

        raise CollisionResolutionError(
            f"Exhausted {self._max_retries} attempts to generate a unique short code."
        )

    def get_original_url(self, short_code: str, current_time: datetime | None = None) -> str:
        """
        Retrieve the destination URL for a registered short code.

        Args:
            short_code (str): The short code slug.
            current_time (datetime | None): Optional reference time for testing expiration.

        Returns:
            str: The corresponding original long URL.

        Raises:
            URLNotFoundError: If the short code does not exist in the repository.
            URLExpiredError: If the short code has passed its expiration deadline.
        """
        record = self._repository.find_by_code(short_code)
        if record is None:
            raise URLNotFoundError(f"Short code '{short_code}' does not exist.")

        if record.is_expired(current_time=current_time):
            raise URLExpiredError(
                f"Short link '{short_code}' has expired on {record.expires_at.isoformat() if record.expires_at else 'unknown'}."
            )

        # Atomically increment click count for successful, non-expired redirection
        self._repository.increment_click_count(short_code)

        return record.original_url

    def list_urls(self) -> list[URLRecord]:
        """
        Retrieve all URL records through the persistence layer.

        Returns:
            list[URLRecord]: Collection of all stored URL records.
        """
        return self._repository.list_all()
