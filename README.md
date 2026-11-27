# Campus Maintenance

A standalone campus maintenance system extracted from OptiCampus. The frontend is React with JavaScript and Vite; the API is Python/Flask; user accounts and maintenance tickets are stored in local MySQL.

## What it includes

- Student registration/login, issue reporting, and status tracking for their own tickets
- Maintenance accounts assigned to a department, with department-only ticket access
- Admin registration/login, with access to all issues and their reporting students
- Department selection for issue routing and maintenance sign-in
- Optional JPEG, PNG, or WebP ticket images stored under `backend/uploads/` and shown to authorized users
- Image filenames and content types stored in MySQL; image bytes are stored on disk
- MySQL database/table creation on the first API start
- Automatic migration of existing MySQL users and tickets to the role/department schema
- Eight-hour signed login tokens and salted password hashes

## Prerequisites

- Node.js 20.19+ (or 22.12+)
- Python 3.10+
- MySQL 8 running locally
- A MySQL account that can create a database and tables

## Run on Windows

### 1. Configure MySQL

From the project directory, create the backend environment file:

```powershell
Copy-Item backend\.env.example backend\.env
```

Edit `backend\.env` and set `MYSQL_USER`, `MYSQL_PASSWORD`, and a private random `JWT_SECRET` to values for your local setup. The configured MySQL account must be allowed to create the `campus_maintenance` database and its tables. Keep this file private; it is ignored by Git.

### 2. Start the API

Open a terminal in the project directory:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

The API listens on `http://127.0.0.1:5000`. On first startup, it creates the database and tables. Check `http://127.0.0.1:5000/api/health` for the API health response.

### 3. Start the Vite frontend

Open a second terminal in the project directory:

```powershell
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite, normally `http://localhost:5173`. Vite forwards `/api` requests to the Flask API.

## First use

Only `@iiitl.ac.in` email addresses can be used to create accounts. Choose an account type only during account creation. Sign in with your email and password; maintenance staff also select their assigned department. Students choose the responsible department and may attach one JPEG, PNG, or WebP image up to 5 MB to a report. Image files are saved in `backend/uploads/`; the database stores only each generated filename and content type. Register as an Admin to view all issues and the student who reported each one. Admin and maintenance accounts can be created through the registration form for local development.

Admin registration is open as configured for this local project. Anyone who can reach the app can create an admin account, so do not expose it to a public network without restricting account creation.

On startup, existing image bytes in the MySQL `tickets.image_data` column are migrated to `backend/uploads/`, and the legacy BLOB column is removed after migration.

## API routes

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/tickets` (own tickets for students; assigned department for maintenance; all tickets for admins)
- `POST /api/tickets` (students, including a responsible department)
- `GET /api/tickets/<id>/image` (ticket owner, assigned maintenance department, or admin)
- `PATCH /api/tickets/<id>/status` (maintenance, limited to its department)

The backend tests can be run from `backend` with `python -m unittest`.
