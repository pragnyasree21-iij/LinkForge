"""
Unit tests for CodeGeneratorFactory.
"""

import pytest
from app.config import AppConfig
from app.generators import CodeGenerator, RandomCodeGenerator, SequentialCodeGenerator
from app.factories import CodeGeneratorFactory, UnsupportedGeneratorError


@pytest.fixture(autouse=True)
def reset_config_singleton():
    """Ensure AppConfig is reset before and after each test."""
    AppConfig._reset_instance()
    yield
    AppConfig._reset_instance()


class TestCodeGeneratorFactory:
    """Tests verifying the Factory pattern implementation in CodeGeneratorFactory."""

    def test_creates_random_generator_by_default(self):
        """Verify that default creation returns a RandomCodeGenerator."""
        generator = CodeGeneratorFactory.create()
        assert isinstance(generator, RandomCodeGenerator)
        assert isinstance(generator, CodeGenerator)
        assert generator.length == 6

    def test_respects_custom_configured_length_for_random_generator(self):
        """Verify that explicit length parameter is honored by the factory."""
        generator = CodeGeneratorFactory.create(generator_type="random", length=12)
        assert isinstance(generator, RandomCodeGenerator)
        assert generator.length == 12
        code = generator.generate()
        assert len(code) == 12

    def test_creates_sequential_generator_when_requested(self):
        """Verify that 'sequential' produces SequentialCodeGenerator."""
        generator = CodeGeneratorFactory.create(generator_type="sequential", length=8)
        assert isinstance(generator, SequentialCodeGenerator)
        assert isinstance(generator, CodeGenerator)
        code = generator.generate()
        assert len(code) == 8

    def test_case_insensitive_and_whitespace_tolerant(self):
        """Verify that generator types like ' RANDOM ' or 'Sequential' work."""
        gen_random = CodeGeneratorFactory.create(generator_type="  RANDOM  ")
        assert isinstance(gen_random, RandomCodeGenerator)

        gen_seq = CodeGeneratorFactory.create(generator_type="Sequential")
        assert isinstance(gen_seq, SequentialCodeGenerator)

    def test_reads_type_from_injected_app_config(self):
        """Verify that factory respects custom AppConfig when passed."""
        custom_config = AppConfig(generator_type="sequential", default_code_length=10)
        generator = CodeGeneratorFactory.create(config=custom_config)
        assert isinstance(generator, SequentialCodeGenerator)
        code = generator.generate()
        assert len(code) == 10

    def test_unsupported_generator_type_raises_clear_exception(self):
        """Verify that unknown generator types raise UnsupportedGeneratorError."""
        with pytest.raises(UnsupportedGeneratorError, match="Unsupported generator type 'quantum'"):
            CodeGeneratorFactory.create(generator_type="quantum")

    def test_created_generator_functions_via_code_generator_abstraction(self):
        """
        Verify that created objects seamlessly interact via the CodeGenerator contract.
        """
        generator = CodeGeneratorFactory.create()
        code_1 = generator.generate()
        code_2 = generator.generate()
        assert isinstance(code_1, str)
        assert len(code_1) == 6
        assert code_1 != code_2  # Random codes should differ
