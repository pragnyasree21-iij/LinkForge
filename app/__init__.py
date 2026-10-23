"""
LinkForge application package.
Contains domain models, business logic services, and application factory.
"""

from flask import Flask
from app.config import AppConfig
from app.factories import CodeGeneratorFactory
from app.validators import URLValidator
from app.repositories import SQLiteURLRepository
from app.services import URLShortenerService
from app.routes import create_routes_blueprint


def create_app(
    service: URLShortenerService | None = None,
    config: AppConfig | None = None,
) -> Flask:
    """
    Application Factory for LinkForge.

    Creates and configures a Flask application instance. Allows injecting
    a custom service or config (essential for isolated unit/integration testing).

    Args:
        service (URLShortenerService | None): Optional pre-configured service instance.
        config (AppConfig | None): Optional pre-configured configuration instance.

    Returns:
        Flask: The fully configured Flask application.
    """
    app = Flask(__name__)
    active_config = config or AppConfig.get_instance()

    if service is None:
        generator = CodeGeneratorFactory.create(config=active_config)
        repository = SQLiteURLRepository(db_path=active_config.db_path)
        service = URLShortenerService(
            validator=URLValidator(),
            generator=generator,
            repository=repository,
            max_retries=active_config.max_generation_attempts,
        )

    app.config["URL_SERVICE"] = service
    app.config["APP_CONFIG"] = active_config

    blueprint = create_routes_blueprint(service=service, config=active_config)
    app.register_blueprint(blueprint)

    return app
