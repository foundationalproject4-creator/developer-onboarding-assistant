# Developer Onboarding Assistant — Backend

FastAPI backend for the IBM Bob 2.0 Hackathon project.

---

## Requirements

- Python 3.11+
- pip

---

## Setup

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Running the server

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

Interactive docs (Swagger UI): `http://localhost:8000/docs`

---

## Endpoints

| Method | Path       | Description                          |
|--------|------------|--------------------------------------|
| GET    | `/`        | Confirms the backend is running      |
| GET    | `/health`  | Returns health status and version    |
| POST   | `/analyze` | Accepts `repo_path`, starts analysis |

### POST `/analyze` — request body

```json
{
  "repo_path": "/path/to/repository"
}
```

### POST `/analyze` — example response

```json
{
  "message": "Repository analysis started",
  "repo_path": "/path/to/repository"
}
```

---

## Extending — connecting the Repository Analyzer

The `analyze` endpoint in [`main.py`](main.py) contains a clearly marked `TODO`
comment where the Repository Analyzer module (implemented separately) should be
wired in:

```python
# TODO: invoke the Repository Analyzer once Meith's module is ready.
```

Replace that comment with the call to the analyzer and return its result.

---

## Project structure

```
backend/
├── main.py           # FastAPI application (routes, models, entry point)
├── requirements.txt  # Pinned runtime dependencies
└── README.md         # This file
```
