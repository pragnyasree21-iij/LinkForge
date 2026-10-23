"""
Unit tests for the AppConfig Singleton pattern.
"""

import pytest
from app.config import AppConfig


@pytest.fixture(autouse=True)
def reset_config_singleton():
    """Ensure every test runs with a fresh AppConfig singleton state."""
    AppConfig._reset_instance()
    yield
    AppConfig._reset_instance()


class TestAppConfigSingleton:
    """Tests verifying the Singleton behavior and defaults of AppConfig."""

    def test_default_configuration_values(self):
        """Verify that default settings match project requirements."""
        config = AppConfig.get_instance()
        assert config.base_url == "http://localhost:5000"
        assert config.default_code_length == 6
        assert config.max_generation_attempts == 5
        assert config.generator_type == "random"
        assert config.db_path == "linkforge.db"

    def test_singleton_returns_exact_same_instance(self):
        """
        Verify object identity: Multiple calls to AppConfig() and AppConfig.get_instance()
        must return the exact same instance in memory (pointer identity via 'is').
        """
        config_1 = AppConfig()
        config_2 = AppConfig()
        config_3 = AppConfig.get_instance()

        assert config_1 is config_2
        assert config_2 is config_3
        assert id(config_1) == id(config_2) == id(config_3)

    def test_subsequent_constructor_calls_do_not_overwrite_state(self):
        """
        Verify that once initialized, subsequent calls to AppConfig with different
        arguments do not mutate the existing singleton instance.
        """
        config_original = AppConfig(default_code_length=10)
        assert config_original.default_code_length == 10

        # Attempt to create another with length 20
        config_ignored = AppConfig(default_code_length=20)
        assert config_ignored is config_original
        assert config_ignored.default_code_length == 10

    def test_reset_instance_allows_clean_reinitialization(self):
        """
        Verify that _reset_instance allows fresh initialization for testing isolation.
        """
        config_a = AppConfig(base_url="http://test-a.com")
        assert config_a.base_url == "http://test-a.com"

        AppConfig._reset_instance()

        config_b = AppConfig(base_url="http://test-b.com")
        assert config_b.base_url == "http://test-b.com"
        assert config_b is not config_a
