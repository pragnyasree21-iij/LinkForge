# LinkForge — Smart URL Shortener & Click Analytics

A clean, production-grade URL Shortener and Click Analytics platform built with Python, Flask, and SQLite. Designed with Low-Level Design (LLD) best practices, object-oriented architecture, SOLID principles, and proven design patterns.

---

## 1. Project Overview

**LinkForge** solves the problem of sharing, shortening, and managing unwieldy URLs while providing real-time, persistent click analytics. Unlike basic script-level URL shorteners, LinkForge is engineered with a modular, decoupled architecture where validation, code generation, persistence, business logic orchestration, and HTTP presentation are isolated into dedicated, testable components.

---

## 2. Key Features

- **Robust URL Validation:** Strict structural validation for HTTP/HTTPS protocols, hostname requirements, port boundaries (1–65535), and prevention of embedded credentials and unsupported schemes (`ftp://`, `javascript:`, `file:`).
- **Custom Alias Support:** User-defined slugs with length constraints (3–30 chars), whitelisted characters (`[A-Za-z0-9_-]`), and system reserved keyword protection (`admin`, `api`, `health`, `static`, etc.).
- **Timezone-Aware Expiration:** Optional expiration dates enforced strictly in UTC; expired links automatically return HTTP 410 (Gone) and cease redirecting.
- **Interchangeable Code Generation:** Pluggable generation strategies using the **Strategy Pattern** (Cryptographic Random vs. Base62 Sequential Counter).
- **Atomic Click Analytics:** Real-time redirect counting executed atomically via SQL (`click_count = click_count + 1`), preventing race conditions and persisting across server restarts.
- **Persistent SQLite Storage:** Durable relational storage with foreign/unique constraint safety, parameterized queries, and scoped connection lifecycles.
- **Interactive Web Dashboard:** Clean, responsive SaaS dashboard built with semantic HTML5, Vanilla CSS, and Vanilla JavaScript with live statistics, instant copy-to-clipboard, and client-side search filtering.

---

## 3. Technology Stack

- **Language:** Python 3.12+
- **Web Framework:** Flask (Blueprint architecture, Application Factory)
- **Database:** SQLite3 (parameterized queries, ACID compliant)
- **Frontend:** Jinja2 Templates, HTML5, Vanilla CSS (Glassmorphism & Dark Theme), Vanilla JavaScript (Async/Await, Clipboard API)
- **Testing:** Pytest (184 automated tests with 100% pass rate)

---

## 4. Project Folder Structure

```text
URL Shortner/
├── app/
│   ├── __init__.py           # Application Factory (create_app)
│   ├── config.py             # Singleton configuration management (AppConfig)
│   ├── factories.py          # CodeGeneratorFactory for strategy instantiation
│   ├── generators.py         # Strategy Pattern: CodeGenerator, Random & Sequential
│   ├── models.py             # Domain Model: URLRecord dataclass with is_expired()
│   ├── repositories.py       # Repository Pattern: URLRepository, InMemory & SQLite
│   ├── routes.py             # Flask Blueprint routes (GET /, /health, /api/urls, /<slug>)
│   ├── services.py           # Application Service: URLShortenerService orchestrator
│   ├── validators.py         # SRP Validators: URLValidator and AliasValidator
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css     # Dark theme design system & responsive styling
│   │   └── js/
│   │       └── dashboard.js  # Dashboard UI logic, analytics computation, clipboard
│   └── templates/
│       └── index.html        # Glassmorphic SaaS dashboard interface
├── tests/
│   ├── test_config.py        # Config singleton tests
│   ├── test_factories.py     # Strategy factory tests
│   ├── test_generators.py    # Random & Base62 generator tests
│   ├── test_repository.py    # In-memory repository tests
│   ├── test_routes.py        # HTTP API & redirect integration tests
│   ├── test_services.py      # Core service business logic & collision retries
│   ├── test_sqlite_repository.py # SQLite persistent repository tests
│   ├── test_step8.py         # Custom aliases and link expiration tests
│   ├── test_step11.py        # Dashboard & click tracking integration tests
│   └── test_step12.py        # Comprehensive edge-case & boundary tests
├── linkforge.db              # SQLite development database
├── main.py                   # CLI demonstration script
├── run.py                    # Local web server startup script
├── README.md                 # Complete project documentation
├── INTERVIEW_PREPARATION.md  # Detailed LLD placement interview preparation
└── .gitignore                # Python and IDE ignore rules
```

---

## 5. Architecture and Request Flow

LinkForge follows a layered **Clean Architecture** separating concerns:

```
[ Client / Browser ]
         │ HTTP Request
         ▼
[ Flask Routes Layer (app/routes.py) ]
         │ DTO / Parameters
         ▼
[ Service Layer (app/services.py: URLShortenerService) ]
 ├── Validates URL (app/validators.py: URLValidator)
 ├── Validates Alias (app/validators.py: AliasValidator)
 ├── Generates Slug (app/generators.py: CodeGenerator)
 └── Persists Entity (app/repositories.py: URLRepository)
         ▼
[ Persistence Layer (SQLite / In-Memory Database) ]
```

### URL Shortening Flow (`POST /api/urls`)
1. Client submits target URL, optional custom alias, and optional ISO-8601 expiration.
2. Route parses JSON and calls `service.shorten_url(...)`.
3. `URLValidator` verifies scheme, network location, hostname, credentials, and port boundaries.
4. If a custom alias is provided, `AliasValidator` checks character constraints and reserved words; duplicate collisions raise `AliasAlreadyTakenError` (HTTP 409).
5. If no alias is provided, `CodeGenerator` generates a unique slug. If an accidental collision occurs, the service retries up to `max_retries` attempts.
6. The service constructs a UTC `URLRecord` and calls `repository.save(record)`.
7. Route responds with HTTP 201 Created and the JSON payload.

### URL Redirection & Click Analytics Flow (`GET /<short_code>`)
1. Visitor navigates to short link (e.g., `http://localhost:5000/my-slug`).
2. Route invokes `service.get_original_url("my-slug")`.
3. `repository.find_by_code("my-slug")` looks up the entity. If missing, raises `URLNotFoundError` (HTTP 404).
4. `record.is_expired()` checks current UTC time against `expires_at`. If expired, raises `URLExpiredError` (HTTP 410).
5. Only upon verifying the link is active and valid, `repository.increment_click_count("my-slug")` atomically executes:
   ```sql
   UPDATE urls SET click_count = click_count + 1 WHERE short_code = ?
   ```
6. Route returns an HTTP 302 Temporary Redirect to `record.original_url`.

---

## 6. Design Patterns & SOLID Principles

### Design Patterns
1. **Strategy Pattern:**
   - Interface: `CodeGenerator`
   - Concrete Strategies: `RandomCodeGenerator` (cryptographic Base62 via `secrets`), `SequentialCodeGenerator` (Base62 counter).
   - Benefit: Changing the slug generation algorithm requires zero changes to the service layer.
2. **Factory Pattern:**
   - Class: `CodeGeneratorFactory`
   - Benefit: Centralizes configuration resolution, validation of generator types, and strategy instantiation.
3. **Repository Pattern:**
   - Interface: `URLRepository`
   - Implementations: `InMemoryURLRepository` (fast testing), `SQLiteURLRepository` (durable storage).
   - Benefit: Decouples domain logic from SQL query syntax and storage engine specifics.
4. **Dependency Injection:**
   - `URLShortenerService` receives `URLValidator`, `CodeGenerator`, and `URLRepository` via its constructor (`__init__`).
   - Benefit: Simplifies mocking and isolated unit testing.
5. **Singleton Pattern:**
   - Class: `AppConfig`
   - Benefit: Provides centralized global configuration defaults. Includes `_reset_instance()` for test isolation.

### SOLID Principles
- **Single Responsibility Principle (SRP):** Each module has exactly one reason to change. `URLValidator` checks URLs, `SQLiteURLRepository` runs queries, `URLShortenerService` coordinates workflow.
- **Open/Closed Principle (OCP):** New generator algorithms or repositories can be introduced by subclassing abstractions without modifying existing classes.
- **Liskov Substitution Principle (LSP):** `InMemoryURLRepository` and `SQLiteURLRepository` can be substituted interchangeably without altering application behavior.
- **Interface Segregation Principle (ISP):** Abstractions define only the lean, necessary methods required by consumers (`generate()` for generators; `save()`, `find_by_code()`, `delete()`, `list_all()`, `increment_click_count()` for repositories).
- **Dependency Inversion Principle (DIP):** High-level services depend on abstract contracts (`CodeGenerator`, `URLRepository`), not concrete low-level implementations.

---

## 7. Database Schema

Managed via SQLite in `linkforge.db`:

```sql
CREATE TABLE IF NOT EXISTS urls (
    short_code TEXT PRIMARY KEY,
    original_url TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    click_count INTEGER NOT NULL DEFAULT 0
);
```

- `short_code`: Primary key. Uniqueness enforced at the database engine level.
- `original_url`: Target destination string.
- `created_at`: ISO-8601 UTC timestamp.
- `expires_at`: Optional ISO-8601 UTC expiration timestamp (NULL for permanent links).
- `click_count`: Non-negative integer counter, incremented atomically upon successful redirection.

---

## 8. API Endpoints

### 1. Dashboard UI
- **URL:** `GET /`
- **Response:** `200 OK` (Renders HTML SaaS Dashboard)

### 2. Health Check
- **URL:** `GET /health`
- **Response:** `200 OK`
  ```json
  {
    "app": "LinkForge",
    "status": "ok",
    "version": "1.0.0"
  }
  ```

### 3. Create Short URL
- **URL:** `POST /api/urls`
- **Headers:** `Content-Type: application/json`
- **Request Body:**
  ```json
  {
    "url": "https://example.com/very/long/destination/url",
    "custom_alias": "my-custom-slug",
    "expires_at": "2026-12-31T23:59:59+00:00"
  }
  ```
  *(Note: `custom_alias` and `expires_at` are optional).*
- **Response (201 Created):**
  ```json
  {
    "click_count": 0,
    "created_at": "2026-10-23T15:00:00+00:00",
    "expires_at": "2026-12-31T23:59:59+00:00",
    "original_url": "https://example.com/very/long/destination/url",
    "short_code": "my-custom-slug",
    "short_url": "http://localhost:5000/my-custom-slug",
    "status": "active"
  }
  ```
- **Error Responses:**
  - `400 Bad Request`: Malformed JSON, invalid URL syntax, or past expiration date.
  - `409 Conflict`: Custom alias already registered.
  - `500 Internal Server Error`: Unhandled database or system failure.

### 4. List All URLs
- **URL:** `GET /api/urls`
- **Response (200 OK):**
  ```json
  {
    "count": 1,
    "urls": [
      {
        "click_count": 5,
        "created_at": "2026-10-23T15:00:00+00:00",
        "expires_at": null,
        "is_expired": false,
        "original_url": "https://example.com/very/long/destination/url",
        "short_code": "my-custom-slug",
        "short_url": "http://localhost:5000/my-custom-slug"
      }
    ]
  }
  ```

### 5. Follow Short Link (Redirect)
- **URL:** `GET /<short_code>`
- **Response:**
  - `302 Found`: Redirects browser to `original_url` and increments `click_count` by 1.
  - `404 Not Found`: Short code does not exist.
  - `410 Gone`: Short link has expired.

---

## 9. Installation & Setup (Windows)

### Prerequisites
- Python 3.12 or newer installed on Windows.

### 1. Clone or Open Project
```powershell
cd "c:\Users\pragn\OneDrive\Documents\Projects\URL Shortner"
```

### 2. Set Up Virtual Environment (Optional but Recommended)
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```powershell
pip install flask pytest
```

---

## 10. Database Configuration

LinkForge automatically creates and initializes `linkforge.db` in the workspace root on first startup. No manual SQL migrations or database provisioning commands are required.

To customize the database filename or location, update `AppConfig`:
```python
from app.config import AppConfig

config = AppConfig(db_path="my_custom_db.db")
```

---

## 11. Running Application & Tests

### Run the Interactive Web Server
```powershell
python run.py
```
Open your web browser and visit: **`http://localhost:5000/`**

### Run CLI Demonstration
```powershell
python main.py
```

### Run Full Test Suite
```powershell
python -m pytest -v
```

---

## 12. Example Usage Walkthrough

### Shorten a URL via PowerShell `curl` / `Invoke-RestMethod`
```powershell
Invoke-RestMethod -Uri "http://localhost:5000/api/urls" -Method POST -ContentType "application/json" -Body '{"url": "https://github.com/torvalds/linux", "custom_alias": "torvalds-linux"}'
```

### Test Redirection in Browser or Terminal
Visit:
```text
http://localhost:5000/torvalds-linux
```
The browser will instantly redirect to `https://github.com/torvalds/linux`, and its click count in `http://localhost:5000/` will reflect the visit.

---

## 13. Current Limitations & Future Improvements

### Current Limitations:
1. **Single-Node Storage:** SQLite is optimized for single-process writes and local development; it does not support high-concurrency multi-region deployments.
2. **Basic Click Metrics:** Clicks are tracked via an aggregate integer counter; detailed dimensions (unique visitors, IP geolocation, referrers, device user-agents) are not recorded.
3. **No Authentication:** All links are public; there is no tenant isolation, user login, or API key authentication.

### Future Improvements:
1. **Distributed Caching (Redis):** Cache active short-code resolutions in memory to achieve sub-millisecond redirect latencies and offload database reads.
2. **Asynchronous Click Ingestion:** Buffer click events into a message queue (Kafka or RabbitMQ) and process batch increments worker-side to maintain zero-latency redirects under heavy loads.
3. **PostgreSQL Migration:** Swap `SQLiteURLRepository` with a `PostgresURLRepository` implementation for multi-node connection pooling.
4. **User Authentication & Role-Based Access Control:** Add JWT-based authentication to manage personal links and private team dashboards.
