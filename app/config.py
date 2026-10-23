"""
Application configuration for LinkForge URL Shortener.

Implements the Singleton Design Pattern to ensure a single, consistent
configuration object within the running Python process.
"""


class AppConfig:
    """
    Singleton configuration class holding system-wide settings for LinkForge.

    Attributes:
        base_url (str): The root domain or URL prefix used for shortened links.
        default_code_length (int): Standard character length of generated short codes.
        max_generation_attempts (int): Maximum retry attempts when code collisions occur.
        generator_type (str): The default strategy key used by the code generator factory.
    """

    _instance: "AppConfig | None" = None
    _initialized: bool = False

    def __new__(cls, *args, **kwargs) -> "AppConfig":
        """
        Enforce Singleton pattern: Return the existing instance if already created,
        otherwise instantiate a new one.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        default_code_length: int = 6,
        max_generation_attempts: int = 5,
        generator_type: str = "random",
        db_path: str = "linkforge.db",
    ) -> None:
        """
        Initialize configuration attributes. Guards against re-initialization
        on subsequent calls to ensure immutability of settings in production.
        """
        if self._initialized:
            return

        self.base_url: str = base_url
        self.default_code_length: int = default_code_length
        self.max_generation_attempts: int = max_generation_attempts
        self.generator_type: str = generator_type
        self.db_path: str = db_path
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "AppConfig":
        """
        Accessor method to retrieve the single AppConfig instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset_instance(cls) -> None:
        """
        Reset the singleton instance back to None.

        WARNING:
            This method is intended solely for test isolation to prevent
            configuration leakage between test cases. It MUST NOT be called
            in normal production workflows.
        """
        cls._instance = None
        cls._initialized = False
