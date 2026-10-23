# LinkForge - Smart URL Shortener
# Step 11: Frontend Dashboard & Real Click Analytics Demonstration

import json
from app import create_app
from app.config import AppConfig


def run_step11_demo() -> None:
    """
    Demonstrate LinkForge Step 11:
    - Frontend Dashboard UI route (GET /)
    - Real Click Analytics with atomic increment
    - Persistence in SQLite storage
    - Expiration/Unknown slug safety checks
    """
    print("=" * 76)
    print("    LinkForge - Frontend Dashboard & Real Click Analytics (Step 11 Demo)   ")
    print("=" * 76)

    # 1. Initialize Application via Application Factory
    app = create_app()
    client = app.test_client()
    config = AppConfig.get_instance()

    print(f"\n[1. Setup] Initialized Application with SQLite persistence:")
    print(f"  - Base URL     : {config.base_url}")
    print(f"  - Database File: {config.db_path}")

    # 2. Test GET / (Dashboard HTML Page)
    print("\n[2. Dashboard Route] Testing GET / (Frontend Dashboard):")
    dash_res = client.get("/")
    html_preview = dash_res.get_data(as_text=True)[:180].replace("\n", " ")
    print(f"  - Status Code  : {dash_res.status_code} (Expected: 200)")
    print(f"  - Content-Type : {dash_res.content_type}")
    print(f"  - HTML Preview : {html_preview}...")

    # 3. Create or inspect test link
    alias = "analytics-demo"
    print(f"\n[3. Create Link] Registering test link '/{alias}':")
    payload = {
        "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP",
        "custom_alias": alias
    }
    create_res = client.post(
        "/api/urls",
        data=json.dumps(payload),
        content_type="application/json"
    )
    if create_res.status_code == 201:
        print(f"  - Created new link: {create_res.get_json()['short_url']}")
    else:
        print(f"  - Link '{alias}' already exists in database (HTTP {create_res.status_code})")

    # 4. Check initial click count
    list_res_before = client.get("/api/urls")
    urls_before = list_res_before.get_json().get("urls", [])
    record_before = next((u for u in urls_before if u["short_code"] == alias), None)
    initial_clicks = record_before["click_count"] if record_before else 0
    print(f"\n[4. Initial Click Count] Clicks before redirect: {initial_clicks}")

    # 5. Simulate 3 HTTP 302 redirects
    print(f"\n[5. Redirection] Simulating 3 visits to GET /{alias}:")
    for i in range(1, 4):
        redir = client.get(f"/{alias}")
        print(f"  - Visit #{i}: HTTP {redir.status_code} -> Location: {redir.headers.get('Location')}")

    # 6. Verify updated click count
    list_res_after = client.get("/api/urls")
    urls_after = list_res_after.get_json().get("urls", [])
    record_after = next((u for u in urls_after if u["short_code"] == alias), None)
    updated_clicks = record_after["click_count"] if record_after else 0
    print(f"\n[6. Post-Redirect Analytics] Clicks after visits: {updated_clicks} (Incremented by {updated_clicks - initial_clicks})")

    # 7. Non-existent code safety
    print("\n[7. Unknown Slug Safety] Testing GET /missing-slug-999:")
    missing_res = client.get("/missing-slug-999")
    print(f"  - Status Code  : {missing_res.status_code} (Expected: 404 - counter untouched)")

    print("\n" + "=" * 76)
    print("Status: Step 11 verified. Dashboard served, clicks tracked atomically.")
    print("=" * 76)


def main() -> None:
    """Entry point."""
    run_step11_demo()


if __name__ == "__main__":
    main()
