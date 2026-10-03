# AMC Project (Appointment Management)

## Overview
This project is a Flask + MySQL appointment management system for a municipal corporation (AMC). It includes:

- Citizen appointment booking
- PA review of appointments
- Commissioner dashboard and stats
- System manager account management

## Getting started (local development)

1. **Create a virtual environment**

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows
# or
source .venv/bin/activate       # macOS / Linux
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Create `.env`**

Copy `.env.example` to `.env` and set your values.

4. **Create the database**

Run:

```bash
python create_database.py
```

5. **Run the app**

```bash
python app.py
```

Then open: http://127.0.0.1:5000

---

## Deployment (Docker)

Build and start services:

```bash
docker-compose up --build
```

This will start:
- MySQL (on port `3306`)
- Flask app (on port `5000`)

---

## Accounts

- System Manager: use the seeded account from `fix_db.py` (`jay2006` / `123456`)

---

## Improvements Implemented
- Environment variable configuration (no hardcoded secrets)
- Role-based API access control (`@role_required(...)`)
- Secure session cookies
- Docker + Compose + Gunicorn setup
- Requirements file

---

## Next Suggested Enhancements
- Add migrations via Alembic
- Improve API error handling + validation
- Add CSRF protection for JSON endpoints
- Add audit log for appointment actions
