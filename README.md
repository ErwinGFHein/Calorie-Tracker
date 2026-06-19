# Self-Hosted Minimalist Calorie & Macro Tracker

A lightweight, anti-bloat, self-hosted Calorie and Macro Tracker designed to run seamlessly on home hardware (e.g., Raspberry Pi, home server) and accessed securely over private networks (e.g., Tailscale). 

This application uses an **HTML-First, Server-Side Rendered (SSR)** model. Interactive DOM updates are managed dynamically using HTMX, keeping client-side state to a absolute minimum.

---

## 🚀 Key Features

- **Tab 1: Dashboard**
  - High-level progress tracker measuring daily intake against your custom goals.
  - Quick-log console with autocomplete food database lookup.
  - Inline custom catalog food creations directly from the log console.
  - Daily intake logs grouped chronologically with instant item deleting.
- **Tab 2: Calendar Performance Journal**
  - Default weekly overview showing card metrics and logs summaries.
  - Monthly calendar performance grid with colored score levels.
  - GitHub-style Yearly Consistency Heatmap plotting intake score results for the last 365 days.
  - Multi-mode views evaluating performance by Calories goals, Macro goals, or a combined Average score.
- **Tab 3: Config**
  - Dedicated configuration center to update daily Calories, Protein, Carbohydrates, and Fats targets.
  - General Food Catalog panel to register custom food items into the lookup database.

---

## 🛠️ Technology Stack

- **Backend**: Python 3.11+ / FastAPI
- **Database**: SQLite (Pure SQL connections via Python's native `sqlite3` driver)
- **Frontend**: HTML5, Jinja2 template engine, and Tailwind CSS (v4 CDN)
- **Dynamic Swaps**: HTMX (AJAX DOM swaps without full-page reloads)
- **Containerization**: Docker (Multi-architecture support for `amd64`/`arm64`)

---

## 💻 Local Development

1. **Clone the repository**:
   ```bash
   git clone https://github.com/ErwinGFHein/Calorie-Tracker.git
   cd Calorie-Tracker
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the server in development (reload) mode**:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

4. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your web browser.

---

## 🐳 Docker Deployment

The application is built for containerized environments, ensuring the SQLite database is persisted outside the container runtime.

### Pulling from GitHub Container Registry (GHCR)

You can run the pre-built multi-architecture image directly:
```bash
docker run -d \
  --name calorie-tracker \
  -p 8000:8000 \
  -v calorie_tracker_data:/data \
  ghcr.io/erwingfhein/calorie-tracker:latest
```

### Local Build

To compile the image locally (supporting `amd64` and `arm64`):
```bash
docker build -t calorie-tracker .
docker run -d -p 8000:8000 -v calorie_tracker_data:/data calorie-tracker
```

---

## ☸️ Docker Compose (Recommended)

To run the stack with persistent volumes and automatic restart configurations, a `docker-compose.yml` manifest is provided in the repository root.

### Running with Docker Compose

1. Start the service:
   ```bash
   docker compose up -d
   ```

2. The service is now live on [http://localhost:8000](http://localhost:8000).

3. To stop the service:
   ```bash
   docker compose down
   ```

### Manifest Details (`docker-compose.yml`)

```yaml
version: '3.8'

services:
  calorie-tracker:
    image: ghcr.io/erwingfhein/calorie-tracker:latest
    build:
      context: .
      dockerfile: Dockerfile
    container_name: calorie-tracker
    ports:
      - "8000:8000"
    volumes:
      - calorie_tracker_data:/data
    restart: unless-stopped
    environment:
      - DATABASE_PATH=/data/tracker.db

volumes:
  calorie_tracker_data:
    driver: local
```
