# Development Plan: Minimalist Calorie Tracker

### Phase 1: Environment Setup & Project Scaffolding
**Goal:** Establish the project structure and install core dependencies.
1. **Directory Structure:** Create the folder hierarchy defined in the spec (`app/`, `app/templates/`, `app/static/css/`, `data/`).
2. **Dependencies:** Create `requirements.txt`. We will need `fastapi`, `uvicorn` (for the ASGI server), `jinja2` (for HTML templating), and `python-multipart` (essential for parsing the strict `Form(...)` payloads required by the spec).
3. **App Entry Point:** Initialize `app/main.py` with a basic FastAPI application instance, static file mounting, and Jinja2 template directory configuration.

### Phase 2: Database Layer (Strictly Raw SQL)
**Goal:** Implement the database connection and schema initialization without using an ORM.
1. **Connection Manager:** Create `app/database.py`. Write a utility function to get a database connection to `../data/tracker.db`, ensuring it has `check_same_thread=False` if using SQLite concurrently, and configures row factory for dict-like access.
2. **Schema Initialization:** Write an `init_db()` function containing the two `CREATE TABLE IF NOT EXISTS` statements (`foods` and `logs`) exactly as defined in the spec.
3. **Lifecycle Event:** Hook `init_db()` into the FastAPI startup lifecycle in `main.py` to ensure the database is ready the moment the container starts.

### Phase 3: Frontend Shell & Templating Engine
**Goal:** Build the UI foundation using Jinja2, Tailwind CSS, and HTMX.
1. **Base Layout:** Create `app/templates/base.html`. Inject the CDNs for HTMX and Tailwind CSS. Define the main `{% block content %}`.
2. **Dashboard View:** Create `app/templates/index.html`. Scaffold the daily intake overview, the "Add Food" form, and the log history container.
3. **Component Templates:** Create empty or mock versions of `history.html` and `search.html`. These will act as our HTMX swap targets.

### Phase 4: Core Feature Implementation (API & HTMX Wiring)
**Goal:** Connect the backend routes to the frontend forms using server-side rendering.
1. **GET `/` (Dashboard):**
   - Calculate today's total calories and macros using raw SQL aggregation on the `logs` table joined with `foods`.
   - Evaluate totals against the user-defined constants (e.g., Daily Calorie Target).
   - Render `index.html` with the calculated metrics and conditionally apply Tailwind classes (green/amber/red) for target goals.
2. **POST `/food/add` (Food Database):**
   - Parse `Form(...)` fields.
   - Execute a parameterized SQL `INSERT INTO foods ...`.
   - Return an HTMX redirect or a fresh render of the dashboard.
3. **POST `/search` (Live Lookup):**
   - Accept the `search_query` form data.
   - Execute a `LIKE %?%` query on the `foods` table.
   - Render and return `search.html` containing an `<li>` array of clickable results.
4. **POST `/log/add` (Intake Logging):**
   - Parse `food_id` and `quantity`.
   - Generate an ISO8601 timestamp and execute an `INSERT INTO logs ...`.
   - Re-calculate the daily metrics and render just the updated `history.html` snippet, allowing HTMX to swap it seamlessly into the DOM.

### Phase 5: Containerization & Deployment
**Goal:** Ensure the app is production-ready for a private server setup (e.g., Raspberry Pi via Tailscale).
1. **Dockerfile:** Write a minimal, single-stage Dockerfile using `python:3.11-slim`. 
2. **Data Volumes:** Configure the Dockerfile to expose the `/data` directory. Ensure the internal app points exactly to `/data/tracker.db`.
3. **Multi-Architecture Setup:** Ensure the Dockerfile does not rely on x86-specific binaries so it can be built and deployed for both `linux/amd64` and `linux/arm64` environments.
