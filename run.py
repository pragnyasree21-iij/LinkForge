"""
Local execution entry point for LinkForge Flask Web Application.

Run via:
    python run.py
"""

from app import create_app
from app.config import AppConfig

app = create_app()

if __name__ == "__main__":
    config = AppConfig.get_instance()
    print("=" * 70)
    print("         LinkForge - Smart URL Shortener Flask Server         ")
    print("=" * 70)
    print(f"  - Server Address : {config.base_url}")
    print(f"  - Dashboard UI   : {config.base_url}/")
    print(f"  - Health Check   : {config.base_url}/health")
    print(f"  - Create API     : POST {config.base_url}/api/urls")
    print(f"  - List API       : GET {config.base_url}/api/urls")
    print("=" * 70)
    app.run(host="127.0.0.1", port=5000, debug=False)
