"""
Short-code generation strategies for LinkForge URL Shortener.

This module implements the Strategy Design Pattern for short-code creation.
The abstract base class defines the strategy contract, allowing interchangeable
generation algorithms (e.g., cryptographic random vs. sequential counter) without
modifying client code.
"""

from abc import ABC, abstractmethod
import secrets
import string


class CodeGenerator(ABC):
    """
    Abstract Strategy defining the contract for short-code generators.

    Any generator strategy in LinkForge must inherit from this class and
    implement the `generate()` method.
    """

    @abstractmethod
    def generate(self) -> str:
        """
        Generate a short code string.

        Returns:
            str: The generated short code identifier.
        """
        pass


class RandomCodeGenerator(CodeGenerator):
    """
    Concrete Strategy that produces cryptographically secure, random short codes.

    Uses Python's `secrets` module to pick characters uniformly from a URL-safe
    Base62 alphabet (uppercase letters, lowercase letters, and digits).
    """

    DEFAULT_LENGTH: int = 6
    ALPHABET: str = string.ascii_letters + string.digits  # 62 characters (A-Z, a-z, 0-9)

    def __init__(self, length: int = DEFAULT_LENGTH) -> None:
        """
        Initialize the random generator with a configurable code length.

        Args:
            length (int): Desired character length of generated codes. Must be positive.

        Raises:
            ValueError: If length is not a positive integer.
        """
        if not isinstance(length, int) or isinstance(length, bool) or length <= 0:
            raise ValueError(f"Code length must be a positive integer, got: {length!r}")

        self._length: int = length

    @property
    def length(self) -> int:
        """Return the configured short code length."""
        return self._length

    def generate(self) -> str:
        """
        Generate a cryptographically secure random alphanumeric short code.

        Returns:
            str: A random string of the configured length.
        """
        return "".join(secrets.choice(self.ALPHABET) for _ in range(self._length))


class SequentialCodeGenerator(CodeGenerator):
    """
    Concrete Strategy that generates short codes by Base62-encoding an incrementing integer.

    Note on Production Use & Limitations:
        - Predictability: Attackers can easily guess sequential short codes (e.g., 000001, 000002).
        - Distributed Collisions: In multi-worker or multi-server deployments, separate in-memory
          counters would produce conflicting codes without a centralized sequence coordinator.
        - Primarily used for deterministic testing and educational demonstration of Base62 encoding.
    """

    DEFAULT_MIN_LENGTH: int = 6
    ALPHABET: str = string.digits + string.ascii_uppercase + string.ascii_lowercase

    def __init__(self, start_id: int = 1, min_length: int = DEFAULT_MIN_LENGTH) -> None:
        """
        Initialize the sequential generator.

        Args:
            start_id (int): Initial integer counter (non-negative).
            min_length (int): Minimum string length, zero-padded with the first alphabet character.

        Raises:
            ValueError: If start_id is negative or min_length is not positive.
        """
        if not isinstance(start_id, int) or isinstance(start_id, bool) or start_id < 0:
            raise ValueError(f"start_id must be a non-negative integer, got: {start_id!r}")

        if not isinstance(min_length, int) or isinstance(min_length, bool) or min_length <= 0:
            raise ValueError(f"min_length must be a positive integer, got: {min_length!r}")

        self._counter: int = start_id
        self._min_length: int = min_length

    @property
    def current_id(self) -> int:
        """Return the current counter value without incrementing."""
        return self._counter

    def generate(self) -> str:
        """
        Encode the current counter to Base62, then increment the internal counter.

        Returns:
            str: The Base62-encoded representation of the current counter.
        """
        current = self._counter
        self._counter += 1

        if current == 0:
            code = self.ALPHABET[0]
        else:
            base = len(self.ALPHABET)
            digits = []
            num = current
            while num > 0:
                num, rem = divmod(num, base)
                digits.append(self.ALPHABET[rem])
            code = "".join(reversed(digits))

        # Pad with leading character if shorter than min_length
        return code.rjust(self._min_length, self.ALPHABET[0])
