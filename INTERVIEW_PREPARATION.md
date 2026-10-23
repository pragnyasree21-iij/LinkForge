# LinkForge — Placement Interview Preparation Guide

This document contains in-depth, beginner-friendly answers to core software engineering and Low-Level Design (LLD) interview questions based on the real implementation of **LinkForge — Smart URL Shortener**.

---

### 1. What problem does LinkForge solve?
**Answer:**
Long, parameter-heavy URLs are unwieldy to share, prone to truncation in messaging platforms, and impossible to memorize. **LinkForge** solves this by:
1. Transforming long destination URLs into concise, readable short links (e.g., `http://localhost:5000/xyz123` or custom slugs like `http://localhost:5000/my-portfolio`).
2. Providing real-time, persistent click tracking to measure link engagement.
3. Enabling link lifecycle management through optional UTC expiration dates.
4. Serving an interactive SaaS dashboard where users can create, search, and monitor links.

---

### 2. Why did you choose Python and Flask?
**Answer:**
- **Python:** Offers clear syntax, first-class object-oriented programming, standard dataclasses (`@dataclass`), and rich standard libraries (e.g., `secrets`, `urllib.parse`, `sqlite3`, `datetime`). It allows candidates to demonstrate core architectural concepts—like design patterns and SOLID principles—without boilerplate distraction.
- **Flask:** A lightweight, unopinionated micro-framework. Unlike Django, which prescribes an ORM and specific directory structure, Flask allows us to structure our own clean architecture:
  - We use the **Application Factory Pattern** (`create_app`) for seamless test isolation.
  - We use **Flask Blueprints** (`create_routes_blueprint`) to decouple HTTP transport and status codes from business logic.

---

### 3. Explain the complete request flow when a user shortens a URL.
**Answer:**
1. **HTTP Ingestion:** The client sends an HTTP `POST /api/urls` containing a JSON payload (`url`, optional `custom_alias`, optional `expires_at`).
2. **Controller/Route Layer:** The route in `app/routes.py` validates that the request is JSON, parses fields, and forwards them to `URLShortenerService.shorten_url()`.
3. **URL Validation:** The injected `URLValidator` verifies the destination URL syntax (checks scheme is `http`/`https`, requires valid hostname, validates port range 1–65535, rejects embedded credentials).
4. **Expiration Validation:** If `expires_at` is provided, the service verifies it is a timezone-aware UTC datetime and strictly in the future.
5. **Code Assignment:**
   - *If custom alias is provided:* `AliasValidator` checks length (3–30 chars), whitelisted characters, and blacklisted keywords (`admin`, `api`, `health`). If valid, the service attempts to save it. If taken, it raises `AliasAlreadyTakenError` (HTTP 409).
   - *If random code is requested:* The injected `CodeGenerator` produces a 6-character Base62 string.
6. **Collision Handling:** The service attempts to save the record in `URLRepository`. If a random code collides with an existing one, a bounded retry loop runs (up to `max_retries = 5`) to generate a new candidate slug.
7. **Persistence:** The repository serializes the `URLRecord` domain model into SQLite via parameterized SQL (`INSERT INTO urls ...`).
8. **HTTP Response:** The route formats the saved entity and returns HTTP 201 Created with the full short URL and metadata.

---

### 4. Why did you use the Strategy Pattern?
**Answer:**
The **Strategy Pattern** defines a family of algorithms, encapsulates each one, and makes them interchangeable at runtime.
- **In LinkForge:** Short-code generation algorithms vary depending on requirements:
  - `RandomCodeGenerator` picks cryptographically secure random characters from Base62 using Python's `secrets` module (unpredictable, ideal for public links).
  - `SequentialCodeGenerator` encodes an incrementing integer into Base62 (compact, deterministic, ideal for predictable testing).
- **Benefit:** `URLShortenerService` depends solely on the abstract contract `CodeGenerator.generate()`. If we want to introduce a hash-based generator (e.g., MurmurHash or SHA-256 slice), we create a new subclass of `CodeGenerator` without touching a single line of business logic in `URLShortenerService` (adhering to Open/Closed Principle).

---

### 5. What is the Factory Pattern doing here?
**Answer:**
The **Factory Pattern** (`CodeGeneratorFactory`) centralizes the instantiation logic of code generation strategies.
- **In LinkForge:** Instead of hardcoding `RandomCodeGenerator(length=6)` inside `create_app` or `URLShortenerService`, callers ask `CodeGeneratorFactory.create()`.
- **Benefit:** It handles default configuration fallback (reading `generator_type` and `default_code_length` from `AppConfig`), normalizes input strings, and validates that requested generator types exist. If an invalid type is requested, it raises a clean `UnsupportedGeneratorError`.

---

### 6. Why use the Repository Pattern?
**Answer:**
The **Repository Pattern** acts as an in-memory collection interface for domain entities, separating domain logic from the underlying database technology.
- **In LinkForge:**
  - `URLRepository` defines abstract operations: `save()`, `find_by_code()`, `delete()`, `list_all()`, and `increment_click_count()`.
  - `InMemoryURLRepository` uses a Python dictionary for sub-millisecond, volatile unit testing without touching disk.
  - `SQLiteURLRepository` handles durable SQL storage with schema creation and connection management.
- **Benefit:** The service layer (`URLShortenerService`) has no knowledge of SQL queries, table names, or database drivers. Swapping SQLite for PostgreSQL or MongoDB would only require writing a new repository class.

---

### 7. How does Dependency Injection help testing?
**Answer:**
**Dependency Injection (DI)** means an object receives its dependencies from the outside rather than creating them internally (`new` or hardcoded instantiation).
- **In LinkForge:** `URLShortenerService` constructor accepts:
  ```python
  def __init__(self, validator, generator, repository, max_retries, alias_validator):
  ```
- **Testing Benefit:**
  - In unit tests (`test_services.py`), we inject `InMemoryURLRepository()` and a deterministic mock generator. Tests run in under 0.01 seconds without disk I/O, file locks, or database cleanup.
  - To test collision handling, we easily inject a test generator that deliberately outputs duplicate strings and verify that the retry limit triggers `CollisionResolutionError`.

---

### 8. How is the Singleton used, and what are its limitations?
**Answer:**
- **How it is used:** `AppConfig` uses the **Singleton Pattern** via `__new__` and `get_instance()` to guarantee that configuration settings (`base_url`, `default_code_length`, `db_path`) are loaded consistently across the application.
- **Benefits:** Prevents re-parsing environment variables or creating conflicting config objects in memory.
- **Limitations & Concerns:**
  1. *Global Mutable State:* Singletons introduce hidden dependencies across modules and can cause test contamination if one test mutates a config setting.
  2. *Multithreading:* In concurrent environments, singletons require thread synchronization locks during initialization.
  3. *LinkForge Mitigation:* We provided a `_reset_instance()` helper used exclusively in test fixtures to restore clean state between test runs.

---

### 9. How do you prevent duplicate short codes?
**Answer:**
Duplicate prevention is enforced at two distinct layers:
1. **Application Layer (Retry Loop):** When generating random codes, `URLShortenerService` catches `DuplicateShortCodeError` from the repository and retries up to 5 times with a newly generated code.
2. **Database Engine Layer (PRIMARY KEY Constraint):** The SQLite schema declares `short_code TEXT PRIMARY KEY`. If two concurrent threads attempt to insert the same slug simultaneously, the database engine rejects the second insert with a unique constraint violation (`sqlite3.IntegrityError`), which our repository translates into `DuplicateShortCodeError`.

---

### 10. How do you handle expired links?
**Answer:**
1. **Creation Time:** When a user passes `expires_at`, the service validates that the timestamp is timezone-aware (UTC) and strictly greater than `datetime.now(timezone.utc)`. Past timestamps are rejected with HTTP 400 (`InvalidExpirationError`).
2. **Redirection Time:** When `GET /<short_code>` is requested, `URLRecord.is_expired()` compares the current UTC time against `record.expires_at`.
3. **If Expired:**
   - The service raises `URLExpiredError`.
   - The route handler catches this and returns **HTTP 410 (Gone)**.
   - The click counter is **NOT** incremented.
   - The original destination URL is never revealed.

---

### 11. How are click counts stored and updated?
**Answer:**
- **Storage:** Stored as an integer column `click_count` in the `urls` table (defaulting to 0).
- **Atomic Update:** During `GET /<short_code>`, after verifying the link exists and is not expired, `repository.increment_click_count(short_code)` executes an atomic SQL update:
  ```sql
  UPDATE urls SET click_count = click_count + 1 WHERE short_code = ?
  ```
- **Why Atomic?** Updating directly in the database engine avoids read-modify-write race conditions where two simultaneous requests read count `5` and both overwrite it with `6`. With `click_count = click_count + 1`, the database serializes increments so the final count is correctly `7`.

---

### 12. Why use SQLite instead of a dictionary for persistent storage?
**Answer:**
- **Durability (ACID):** A Python dictionary lives entirely in process RAM. If the application crashes, restarts, or deploys an update, all link records and click counts are permanently lost. SQLite writes transactions to disk using a write-ahead log/journal.
- **Relational Integrity:** SQLite enforces constraints (`PRIMARY KEY`, `NOT NULL`, data types) at the engine level.
- **Concurrency & Memory:** In-memory dictionaries consume server RAM proportional to dataset size. SQLite handles indexes on disk and caches pages efficiently.

---

### 13. How does the application follow SOLID principles?
**Answer:**
- **S (Single Responsibility):** Each class has one focus: `URLValidator` (URL structure), `AliasValidator` (slug rules), `RandomCodeGenerator` (string generation), `SQLiteURLRepository` (SQL queries), `URLShortenerService` (workflow orchestration).
- **O (Open/Closed):** We can add new generator algorithms (e.g., UUID or Hash) or new databases (e.g., Redis or Postgres) without modifying `URLShortenerService`.
- **L (Liskov Substitution):** `InMemoryURLRepository` and `SQLiteURLRepository` can replace `URLRepository` anywhere without altering expected behavior or breaking contracts.
- **I (Interface Segregation):** Interfaces are compact. `CodeGenerator` has 1 method (`generate`). `URLRepository` has 5 focused methods.
- **D (Dependency Inversion):** `URLShortenerService` depends on abstract base classes (`URLRepository`, `CodeGenerator`), not concrete SQLite or generator classes.

---

### 14. What happens if two users generate the same short code?
**Answer:**
- **If both are random codes:**
  1. The first user's transaction inserts the code into SQLite and succeeds.
  2. The second user's insert triggers `sqlite3.IntegrityError`, caught by `SQLiteURLRepository` and raised as `DuplicateShortCodeError`.
  3. The `URLShortenerService` catches `DuplicateShortCodeError`, logs a collision retry, generates a new random code, and saves successfully. The second user never notices.
- **If a user requests a custom alias that already exists:**
  1. The repository raises `DuplicateShortCodeError`.
  2. The service raises `AliasAlreadyTakenError`.
  3. The API immediately returns **HTTP 409 Conflict** with `"Custom alias 'xyz' is already in use."`. It does *not* silently overwrite the existing link or generate an unwanted random code.

---

### 15. How would you improve the system for thousands of concurrent users?
**Answer:**
*(Note: Distinguishing current implementation from production scale-up)*
1. **Read/Write Ratio:** URL shorteners have a heavy read-to-write ratio (typically 100:1 reads vs. writes).
2. **Redis In-Memory Caching:** Place a Redis cache in front of the database. When `GET /<short_code>` arrives, check Redis first (`O(1)` memory lookup, sub-millisecond response). Cache popular links with TTL.
3. **Asynchronous Click Buffering:** Instead of writing to the database on every redirect, publish a click event to a message queue (Kafka, RabbitMQ, or Redis Streams). Background Celery workers can aggregate and batch-update click counts every 10 seconds.
4. **Database Scaling:** Migrate from single-file SQLite to a managed PostgreSQL cluster with read replicas.
5. **Horizontal Scaling:** Deploy stateless Flask workers behind an Nginx reverse proxy or cloud load balancer (AWS ALB / Cloudflare).

---

### 16. What are the current scalability limitations?
**Answer:**
1. **SQLite File Locks:** SQLite locks the database file during write operations (`BEGIN IMMEDIATE`). Under high write concurrency (thousands of simultaneous link creations), requests would experience database lock contention (`database is locked`).
2. **Synchronous Clicks:** Every redirect triggers a synchronous disk update query before issuing the 302 redirect. Under heavy traffic, disk I/O latency could slow down redirects.
3. **Single Process Memory for Sequential Generator:** `SequentialCodeGenerator` tracks counters in memory; in a multi-worker WSGI deployment (Gunicorn), each worker would have independent counters, causing cross-worker collisions. (Hence, `RandomCodeGenerator` is the default).

---

### 17. How would you add authentication and user-specific links?
**Answer:**
1. **User Entity:** Create a `User` model (`id`, `email`, `password_hash`, `created_at`).
2. **Relational Schema:** Add a `user_id` foreign key column to the `urls` table:
   ```sql
   ALTER TABLE urls ADD COLUMN user_id INTEGER REFERENCES users(id);
   ```
3. **JWT / Session Authentication:** Use Flask-JWT-Extended or secure HTTP-only session cookies.
4. **Protected Endpoints:** Add an `@auth_required` decorator to `POST /api/urls` and `GET /api/urls`.
5. **Tenant Isolation:** Modify `list_all()` in `URLRepository` to support `list_by_user(user_id)`.

---

### 18. How would you add Redis caching safely?
**Answer:**
1. **Implement Cache-Aside Pattern:**
   - In `service.get_original_url(short_code)`:
     1. Query Redis for key `url:{short_code}`.
     2. If found (Cache Hit), return destination URL immediately.
     3. If missing (Cache Miss), query `URLRepository`. If found and not expired, write to Redis with a TTL (e.g., 24 hours), then return.
2. **Cache Invalidation:**
   - When a link is deleted or expires, call `redis.delete(f"url:{short_code}")`.
3. **Safety for Expiration:** Do not cache expired links. If a link has an expiration timestamp, set the Redis TTL equal to `remaining_seconds = expires_at - now_utc`.

---

### 19. How would you deploy this application?
**Answer:**
1. **WSGI Application Server:** Run Flask behind **Gunicorn** or **uWSGI** with multiple worker processes:
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 run:app
   ```
2. **Reverse Proxy & SSL:** Place **Nginx** in front of Gunicorn to handle SSL termination (Let's Encrypt), static asset caching (`/static/`), and DDoS rate limiting.
3. **Containerization:** Package into a lightweight Docker image (`python:3.12-slim`).
4. **Orchestration:** Deploy onto AWS ECS, Kubernetes, or Render with automated health check monitoring via `GET /health`.

---

### 20. What was the most important design decision in the project?
**Answer:**
The most important design decision was **adopting Dependency Injection with abstract Repository and Strategy interfaces before writing any Flask or SQLite code**.
- By establishing `URLRepository` and `CodeGenerator` as abstract contracts first:
  - We were able to write 100+ comprehensive unit tests that ran instantaneously in memory.
  - When we swapped in-memory storage for SQLite in Step 9, and added click tracking in Step 11, **zero lines of business logic** in `URLShortenerService` had to be rewritten or broken.
  - It cleanly separated HTTP concerns (status codes, JSON serialization) from domain rules (expiration, alias length, collision retries), making the codebase maintainable, resilient, and ready for production expansion.
