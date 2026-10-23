"""
Flask HTTP routes and error handlers for LinkForge URL Shortener.

Exposes REST API endpoints and HTTP 302 redirection while delegating all
business workflows to the injected URLShortenerService.
"""

from datetime import datetime
from flask import Flask, Blueprint, request, jsonify, redirect, Response, render_template
from app.config import AppConfig
from app.services import (
    URLShortenerService,
    InvalidURLError,
    InvalidAliasError,
    AliasAlreadyTakenError,
    InvalidExpirationError,
    URLExpiredError,
    URLNotFoundError,
    CollisionResolutionError,
)
from app.repositories import RepositoryError


def create_routes_blueprint(service: URLShortenerService, config: AppConfig) -> Blueprint:
    """
    Create a Flask Blueprint bound to the provided service and config.

    Args:
        service (URLShortenerService): The application service orchestrating business logic.
        config (AppConfig): Application configuration containing base_url, etc.

    Returns:
        Blueprint: Configured Flask blueprint with all LinkForge endpoints.
    """
    bp = Blueprint("linkforge", __name__)

    @bp.route("/", methods=["GET"])
    def dashboard():
        """
        Render the interactive LinkForge Frontend Dashboard.
        """
        return render_template("index.html")

    @bp.route("/health", methods=["GET"])
    def health_check() -> Response:
        """
        Health check endpoint.
        Returns HTTP 200 indicating service readiness.
        """
        return jsonify({
            "status": "ok",
            "app": "LinkForge",
            "version": "1.0.0"
        }), 200

    @bp.route("/api/urls", methods=["POST"])
    def create_short_url() -> Response:
        """
        Create a new shortened URL.

        Request JSON:
            {
                "url": "https://example.com/long/path",
                "custom_alias": "optional-custom-slug",
                "expires_at": "2026-12-31T23:59:59+00:00"  (optional ISO-8601 string)
            }

        Returns:
            HTTP 201: URLRecord created successfully.
            HTTP 400: Malformed JSON, missing URL, invalid URL, or invalid expiration.
            HTTP 409: Custom alias collision (already in use).
            HTTP 500: Server or database error.
        """
        if not request.is_json:
            return jsonify({"error": "Request body must be valid JSON."}), 400

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Malformed JSON payload. Expected a JSON object."}), 400

        target_url = payload.get("url")
        if not target_url or not isinstance(target_url, str) or not target_url.strip():
            return jsonify({"error": "Field 'url' is required and must be a non-empty string."}), 400

        custom_alias = payload.get("custom_alias")
        if custom_alias is not None:
            if not isinstance(custom_alias, str):
                return jsonify({"error": "Field 'custom_alias' must be a string."}), 400
            custom_alias = custom_alias.strip()

        # Parse optional ISO-8601 expiration timestamp
        expires_at_raw = payload.get("expires_at")
        parsed_expiration = None
        if expires_at_raw is not None:
            if not isinstance(expires_at_raw, str):
                return jsonify({"error": "Field 'expires_at' must be an ISO-8601 formatted string."}), 400
            try:
                parsed_expiration = datetime.fromisoformat(expires_at_raw)
            except ValueError:
                return jsonify({
                    "error": "Invalid expiration timestamp format. Valid ISO-8601 string expected (e.g., '2026-12-31T23:59:59+00:00')."
                }), 400

        # Delegate business logic to URLShortenerService
        try:
            record = service.shorten_url(
                original_url=target_url.strip(),
                custom_alias=custom_alias,
                expires_at=parsed_expiration
            )
            short_url = f"{config.base_url}/{record.short_code}"

            return jsonify({
                "short_url": short_url,
                "short_code": record.short_code,
                "original_url": record.original_url,
                "created_at": record.created_at.isoformat(),
                "expires_at": record.expires_at.isoformat() if record.expires_at else None,
                "click_count": record.click_count,
                "status": "active"
            }), 201

        except (InvalidURLError, InvalidAliasError, InvalidExpirationError) as err:
            return jsonify({"error": str(err)}), 400
        except AliasAlreadyTakenError as err:
            return jsonify({"error": str(err)}), 409
        except CollisionResolutionError as err:
            return jsonify({"error": str(err)}), 500
        except RepositoryError:
            return jsonify({"error": "A persistence database error occurred."}), 500
        except Exception:
            # Shield internal stack trace from client response
            return jsonify({"error": "An unexpected internal server error occurred."}), 500

    @bp.route("/api/urls", methods=["GET"])
    def list_urls() -> Response:
        """
        List all shortened URLs in the repository.

        Returns:
            HTTP 200: JSON list of records.
        """
        try:
            records = service.list_urls()
            url_list = []
            for r in records:
                url_list.append({
                    "short_code": r.short_code,
                    "short_url": f"{config.base_url}/{r.short_code}",
                    "original_url": r.original_url,
                    "created_at": r.created_at.isoformat(),
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                    "click_count": r.click_count,
                    "is_expired": r.is_expired()
                })

            return jsonify({
                "count": len(url_list),
                "urls": url_list
            }), 200
        except RepositoryError:
            return jsonify({"error": "A persistence database error occurred."}), 500
        except Exception:
            return jsonify({"error": "An unexpected internal server error occurred."}), 500

    @bp.route("/<short_code>", methods=["GET"])
    def redirect_to_url(short_code: str) -> Response:
        """
        Resolve a short code and issue an HTTP 302 Temporary Redirect to the original URL.

        Returns:
            HTTP 302: Redirect to original destination.
            HTTP 404: If short_code does not exist.
            HTTP 410: If short_code has expired.
            HTTP 500: Database failure.
        """
        try:
            destination_url = service.get_original_url(short_code)
            return redirect(destination_url, code=302)
        except URLNotFoundError as err:
            return jsonify({"error": str(err)}), 404
        except URLExpiredError as err:
            return jsonify({"error": str(err)}), 410
        except RepositoryError:
            return jsonify({"error": "A persistence database error occurred."}), 500
        except Exception:
            return jsonify({"error": "An unexpected internal server error occurred."}), 500

    return bp
