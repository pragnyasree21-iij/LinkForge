"""
Unit tests for short-code generator strategies.
"""

import pytest
import string
from app.generators import CodeGenerator, RandomCodeGenerator, SequentialCodeGenerator


class TestCodeGeneratorAbstraction:
    """Tests verifying the abstract contract of CodeGenerator."""

    def test_cannot_instantiate_abstract_base_class(self):
        """Verify that CodeGenerator cannot be directly instantiated."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class CodeGenerator"):
            CodeGenerator()  # type: ignore[abstract]


class TestRandomCodeGenerator:
    """Tests for the RandomCodeGenerator strategy."""

    def test_default_length_is_six(self):
        """Verify that the default code length is 6."""
        generator = RandomCodeGenerator()
        assert generator.length == 6
        code = generator.generate()
        assert len(code) == 6

    def test_custom_length_generation(self):
        """Verify that custom positive lengths produce matching string lengths."""
        for length in (4, 8, 12, 16):
            generator = RandomCodeGenerator(length=length)
            code = generator.generate()
            assert len(code) == length

    def test_uses_only_allowed_alphanumeric_characters(self):
        """Verify that codes contain only A-Z, a-z, and 0-9."""
        generator = RandomCodeGenerator(length=20)
        allowed_chars = set(string.ascii_letters + string.digits)
        for _ in range(50):
            code = generator.generate()
            assert all(char in allowed_chars for char in code), f"Invalid character in {code}"

    @pytest.mark.parametrize("invalid_length", [0, -1, -10, "six", None, True, False])
    def test_rejects_invalid_lengths(self, invalid_length):
        """Verify that zero, negative, or non-integer lengths raise ValueError."""
        with pytest.raises(ValueError, match="positive integer"):
            RandomCodeGenerator(length=invalid_length)  # type: ignore[arg-type]

    def test_generates_diverse_codes(self):
        """
        Verify that multiple invocations produce varied codes.
        Note: While random collision is statistically possible over large samples,
        generating 10 six-character Base62 codes (out of 56.8 billion combinations)
        should produce distinct values.
        """
        generator = RandomCodeGenerator()
        codes = {generator.generate() for _ in range(10)}
        assert len(codes) == 10, "Expected 10 unique codes from 10 random generations."


class TestSequentialCodeGenerator:
    """Tests for the SequentialCodeGenerator strategy."""

    def test_sequential_predictable_generation(self):
        """Verify sequential counter advancement."""
        generator = SequentialCodeGenerator(start_id=0, min_length=4)
        assert generator.generate() == "0000"
        assert generator.generate() == "0001"
        assert generator.generate() == "0002"

    def test_base62_encoding_progression(self):
        """Verify transitions across Base62 alphabet boundaries."""
        # '0'-'9' (indices 0-9), 'A'-'Z' (indices 10-35), 'a'-'z' (indices 36-61)
        generator = SequentialCodeGenerator(start_id=9, min_length=1)
        assert generator.generate() == "9"
        assert generator.generate() == "A"

    @pytest.mark.parametrize("invalid_start", [-1, "zero", None, True])
    def test_rejects_invalid_start_id(self, invalid_start):
        """Verify negative or invalid start_id raises ValueError."""
        with pytest.raises(ValueError, match="non-negative integer"):
            SequentialCodeGenerator(start_id=invalid_start)  # type: ignore[arg-type]

    @pytest.mark.parametrize("invalid_min_len", [0, -5, "four", False])
    def test_rejects_invalid_min_length(self, invalid_min_len):
        """Verify non-positive min_length raises ValueError."""
        with pytest.raises(ValueError, match="positive integer"):
            SequentialCodeGenerator(min_length=invalid_min_len)  # type: ignore[arg-type]
