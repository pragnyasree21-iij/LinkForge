"""
Domain models for LinkForge URL Shortener.

This module defines core business entities that encapsulate data and behavior
independent of external frameworks, databases, or user interfaces.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class URLRecord:
    """
    Domain Entity representing a shortened URL mapping.

    Attributes:
        original_url (str): The target destination URL that the user wants to shorten.
        short_code (str): The unique alphanumeric slug assigned to this URL.
        created_at (datetime): The timestamp when the short URL was created in UTC.
        expires_at (datetime | None): Optional UTC expiration timestamp. If None,
                                      the link never expires.
        click_count (int): Counter tracking the number of times this short link has
                           been accessed/redirected. Defaults to 0.
    """

    original_url: str
    short_code: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    click_count: int = 0

    def is_expired(self, current_time: datetime | None = None) -> bool:
        """
        Check whether the shortened URL has expired.

        Timezone Behavior:
            All datetime comparisons are performed in UTC. If expires_at is None,
            the URL is considered permanent and this method returns False.
            If expires_at is set, it is compared against current_time (or current UTC time).

        Args:
            current_time (datetime | None): Optional datetime used as the reference point
                                            (useful for testing). Defaults to UTC now.

        Returns:
            bool: True if expires_at is set and current_time >= expires_at; False otherwise.
        """
        if self.expires_at is None:
            return False

        if self.expires_at.tzinfo is None or self.expires_at.tzinfo.utcoffset(self.expires_at) is None:
            raise ValueError("Record expires_at must be a timezone-aware datetime.")

        now = current_time if current_time is not None else datetime.now(timezone.utc)
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise ValueError("Comparison datetime must be a timezone-aware datetime.")

        return now >= self.expires_at
