Software Requirements Specification (SRS)
Project Name: Self-Hosted Minimalist Calorie Tracker
1. Overview & Objectives
This document defines the architecture and implementation guidelines for a single-user, minimalist Calorie and Macro Logging application. The primary design philosophy is anti-bloat: zero advertisements, zero upselling, minimal client-side state, and an HTML-first deployment.
The application runs as a lightweight, containerized web service designed to be self-hosted on private local hardware (e.g., Raspberry Pi) and accessed via a secure private network overlay (e.g., Tailscale).
2. Technology Stack & Environment
Backend Framework:Python 3.11+/FastAPI
Native execution, asynchronous capability, robust form data parsing.
Database:SQLite
Zero-configuration, single-file storage, atomic, transactional.
Frontend UI Engine: HTMX (via CDN)
Enables dynamic DOM swaps using raw HTML, eliminating JSON APIs and JS build tools.
Styling:Tailwind CSS (via CDN)
Rapid, utility-first responsive styling without local CSS compilation.
Template Engine:Jinja2
Native FastAPI integration for rendering server-side HTML snippets.
Deployment Target:Docker (linux/arm64 and linux/amd64)
Single-stage, minimal runtime container.
3. Core Functional Requirements
3.1 Food Database & Quick Input
Users must be able to add new foods into a persistent lookup catalog with fields for name, calories, protein, carbohydrates, fats, and default serving unit.
The logging interface must provide an inline search bar that queries the lookup database as the user types, using dynamic partial matching (LIKE %query%).
Users select a food item from the search results, input the specific quantity consumed, and submit to log the entry instantly.
3.2 Intake Log History
The app must display a chronological view of logged food entries.
Log entries must be grouped or aggregated by date to show a comprehensive history panel.
3.3 Target Goals & Color Coding
The application evaluates daily calorie and macro intake totals against user-defined static constants (e.g., Daily Calorie Target).
The log history view must conditionally style days based on performance:
Under/On Target: Clean green visual cue.
Over Target: Noticeable amber or red warning color block.
4. System Architecture & Component Communication
The application uses an HTML-First, Server-Side Rendered (SSR) model enhanced by HTMX. Rather than serving a JavaScript bundle that requests JSON and mounts elements client-side, the server acts as the single source of truth for both data and presentation.
5. Database Schema
The database consists of two relational tables hosted within a single tracker.db file.
CREATE TABLE IF NOT EXISTS foods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    calories REAL NOT NULL,
    protein REAL DEFAULT 0,
    carbs REAL DEFAULT 0,
    fat REAL DEFAULT 0,
    unit TEXT DEFAULT 'g'
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    food_id INTEGER NOT NULL,
    quantity REAL NOT NULL,
    timestamp TEXT NOT NULL, -- Stored as ISO8601 string (YYYY-MM-DD HH:MM:SS)
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE
);

6. Directory Layout & Context Map
calorie-tracker/
├── app/
│   ├── __init__.py
│   ├── main.py          # Application entry point, routing, configuration constants
│   ├── database.py      # SQLite connection manager, raw SQL execution routines
│   ├── templates/       # HTML template ecosystem
│   │   ├── base.html    # Base global layout (includes HTMX & Tailwind scripts)
│   │   ├── index.html   # Core application dashboard view
│   │   ├── history.html # Isolated history log component (for HTMX target updates)
│   │   └── search.html  # Isolated food lookup result component
│   └── static/
│       └── css/         # Custom CSS overrides
├── data/
│   └── tracker.db       # SQLite runtime file (Explicitly excluded from git tracking)
├── Dockerfile           # Python slim production environment container configuration
└── requirements.txt     # Locked production dependencies
7. API & Route Specification
GET /
Description: Renders the main interface layout (index.html).
Processing: Queries database for the current day's logs and aggregated history totals. Evaluates performance against static targets.
Returns: Full HTML page.
POST /search
Description: Provides live search filtering for the food lookup database.
Trigger: HTMX input event keyup changed delay:300ms.
Payload: Form parameter search_query (string).
Returns: Raw HTML fragment (search.html) containing an updated <li> array of match candidates.
POST /food/add
Description: Registers an entirely new food product into the database.
Payload: Standard form fields (name, calories, protein, carbs, fat, unit).
Processing: Executes SQL insertion statement.
Returns: Triggers a clean state change or direct redirect back to dashboard.
POST /log/add
Description: Registers a consumption entry for a historical log.
Payload: Standard form fields (food_id, quantity).
Processing: Automatically inserts entry using current timestamp. Recalculates day metrics.
Returns: Raw HTML fragment containing the newly updated dashboard metrics panel and history panel (history.html), forcing HTMX to swap out the stale dashboard nodes.
8. Guardrails & Execution Instructions for Code Assist
Strict Dependency Isolation: Do not introduce object-relational mapping libraries (such as SQLAlchemy or Tortoise). Use pure, raw parameterized SQL operations using the native sqlite3 driver.
No JSON Payloads: All input endpoints must strictly parse incoming structures via Form(...) variables (python-multipart). Client interactions must transmit values natively through standard HTML forms managed by HTMX attributes (hx-post, hx-target, hx-swap).
State Limitation: Do not write any local UI component tracking arrays, local storage parameters, or frontend framework states. All application state is explicitly read from and written to the SQLite database.
Docker Resilience: Ensure the data path configuration points cleanly to /data/tracker.db to allow effortless local volume overrides on the Docker daemon runtime host.