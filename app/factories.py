"""
Factory design pattern implementations for LinkForge URL Shortener.

This module provides factories to decouple strategy creation from client code,
allowing dynamic selection and instantiation of generators.
"""

from app.config import AppConfig
from app.generators import CodeGenerator, RandomCodeGenerator, SequentialCodeGenerator


class FactoryError(Exception):
    """Base exception for factory errors."""
    pass


class UnsupportedGeneratorError(FactoryError, ValueError):
    """Raised when an unknown or unsupported generator type is requested."""
    pass


class CodeGeneratorFactory:
    """
    Factory responsible for instantiating CodeGenerator strategy implementations.

    Decouples callers (such as dependency injection roots or services) from the
    concrete class constructors of RandomCodeGenerator or SequentialCodeGenerator.
    """

    SUPPORTED_TYPES: frozenset[str] = frozenset({"random", "sequential"})

    @classmethod
    def create(
        cls,
        generator_type: str | None = None,
        length: int | None = None,
        config: AppConfig | None = None,
    ) -> CodeGenerator:
        """
        Create and return a concrete CodeGenerator implementation.

        Configuration Precedence:
            1. Explicit parameters passed to this method (generator_type, length).
            2. Provided AppConfig instance (if passed explicitly).
            3. Global AppConfig singleton defaults.

        Args:
            generator_type (str | None): Strategy key ('random' or 'sequential').
            length (int | None): Character length for the generator.
            config (AppConfig | None): Optional configuration override.

        Returns:
            CodeGenerator: A concrete instance conforming to the CodeGenerator interface.

        Raises:
            UnsupportedGeneratorError: If the requested generator type is not recognized.
        """
        active_config = config if config is not None else AppConfig.get_instance()

        # Determine strategy type
        raw_type = generator_type if generator_type is not None else active_config.generator_type
        normalized_type = raw_type.strip().lower()

        # Determine length
        code_length = length if length is not None else active_config.default_code_length

        if normalized_type == "random":
            return RandomCodeGenerator(length=code_length)
        elif normalized_type == "sequential":
            return SequentialCodeGenerator(min_length=code_length)
        else:
            supported = ", ".join(sorted(f"'{t}'" for t in cls.SUPPORTED_TYPES))
            raise UnsupportedGeneratorError(
                f"Unsupported generator type '{raw_type}'. Supported types are: {supported}."
            )
