"""
URL validation services for LinkForge URL Shortener.

This module enforces Single Responsibility Principle (SRP) by isolating
all URL syntax and protocol verification logic away from the data models
and external storage layers.
"""

from urllib.parse import urlparse


class URLValidator:
    """
    Validates URL syntax, structure, and supported protocols.

    Security & Scope Note:
        This class performs basic structural/syntactic validation. A syntactically
        valid URL is NOT guaranteed to be safe, online, or free of malicious intent
        (e.g., phishing or malware). It ensures only that the URL meets LinkForge's
        formatting and protocol requirements without initiating network calls.
    """

    ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

    @staticmethod
    def is_valid(url: str) -> bool:
        """
        Validate whether the given URL is a well-formed absolute HTTP or HTTPS URL.

        Validation Rules:
            1. Input must be a string.
            2. Input must not be empty or whitespace-only.
            3. Scheme must be explicitly 'http' or 'https'.
            4. Must have a valid network location (netloc) and hostname.
            5. Hostname must not contain whitespace characters.
            6. Embedded credentials (username/password) are rejected.
            7. If a port is specified, it must be an integer between 1 and 65535.
            8. No network requests are made during validation.

        Args:
            url (str): The URL string to evaluate.

        Returns:
            bool: True if the URL satisfies all syntax and protocol criteria, False otherwise.
        """
        # Rule 1: Non-string inputs are safely rejected
        if not isinstance(url, str):
            return False

        # Rule 2: Reject empty strings or whitespace-only strings
        cleaned_url = url.strip()
        if not cleaned_url:
            return False

        # Parse URL structure safely with urllib.parse
        try:
            parsed = urlparse(cleaned_url)
        except ValueError:
            return False

        # Rule 3: Enforce allowed schemes (HTTP/HTTPS only)
        if not parsed.scheme or parsed.scheme.lower() not in URLValidator.ALLOWED_SCHEMES:
            return False

        # Rule 4: Require network location (authority)
        if not parsed.netloc:
            return False

        # Rule 5 & 7: Extract hostname and port safely with exception handling
        try:
            hostname = parsed.hostname
            port = parsed.port
        except ValueError:
            # Raised by urllib when port is non-numeric or out of range (0-65535)
            return False

        # Rule 4 & 5: Require a non-empty hostname without whitespace
        if not hostname or any(char.isspace() for char in hostname):
            return False

        # Rule 6: Reject embedded credentials (e.g., https://user:pass@example.com)
        if parsed.username is not None or parsed.password is not None:
            return False

        # Rule 7: Enforce valid TCP port range (1 to 65535)
        if port is not None and not (1 <= port <= 65535):
            return False

        return True


class AliasValidator:
    """
    Validates custom short alias strings.

    Enforces length boundaries, character whitelisting, and reserved
    keyword blacklisting to maintain clean routing and URL safety.
    """

    MIN_LENGTH: int = 3
    MAX_LENGTH: int = 30
    ALLOWED_CHARS: frozenset[str] = frozenset(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    )
    RESERVED_ALIASES: frozenset[str] = frozenset(
        {"admin", "api", "health", "static", "login", "metrics", "docs", "swagger", "root", "auth"}
    )

    @classmethod
    def is_valid(cls, alias: str) -> bool:
        """
        Validate whether a custom alias is permissible.

        Validation Rules:
            1. Input must be a string.
            2. Length must be between 3 and 30 characters (inclusive).
            3. Must contain only letters (A-Z, a-z), digits (0-9), hyphens (-), and underscores (_).
            4. Must not be a system-reserved keyword (case-insensitive).

        Args:
            alias (str): The candidate custom slug.

        Returns:
            bool: True if valid, False otherwise.
        """
        if not isinstance(alias, str):
            return False

        cleaned = alias.strip()
        if len(cleaned) < cls.MIN_LENGTH or len(cleaned) > cls.MAX_LENGTH:
            return False

        # Reject reserved routing endpoints
        if cleaned.lower() in cls.RESERVED_ALIASES:
            return False

        # Enforce character whitelist (letters, digits, hyphens, underscores)
        return all(char in cls.ALLOWED_CHARS for char in cleaned)

