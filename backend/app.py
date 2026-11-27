import os
import re
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4

import jwt
import mysql.connector
from dotenv import load_dotenv
from flask import Flask, g, jsonify, request, send_file
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024 + 128 * 1024
CORS(
    app,
    resources={r"/api/*": {"origins": "http://localhost:5173"}},
    allow_headers=["Content-Type", "Authorization"],
)

DB_NAME = os.getenv("MYSQL_DATABASE", "campus_maintenance")
if not re.fullmatch(r"[A-Za-z0-9_]+", DB_NAME):
    raise ValueError("MYSQL_DATABASE may contain only letters, numbers, and underscores.")

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": DB_NAME,
}
JWT_SECRET = os.getenv("JWT_SECRET", "local-development-secret-change-me")
VALID_ROLES = {"student", "maintenance", "admin"}
DEPARTMENTS = (
    "Electrical",
    "Plumbing",
    "HVAC",
    "Carpentry/Furniture",
    "Cleaning",
    "IT",
    "General",
)
VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}
VALID_STATUSES = {"Open", "In Progress", "Resolved"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
IMAGE_EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
TICKET_SELECT = """
    SELECT t.id, t.issue_type, t.department, t.location, t.priority,
      t.description, t.status, t.created_at, t.updated_at,
      (t.image_filename IS NOT NULL) AS has_image,
      u.name AS reporter_name, u.email AS reporter_email
    FROM tickets t JOIN users u ON u.id = t.reporter_id
"""


def database_connection(include_database=True):
    config = DB_CONFIG.copy()
    if not include_database:
        config.pop("database")
    return mysql.connector.connect(**config)


def request_data():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def store_image_file(image_data, content_type):
    extension = IMAGE_EXTENSIONS.get(content_type)
    if not extension:
        raise ValueError("Unsupported image content type.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    image_path = UPLOAD_DIR / filename
    try:
        with image_path.open("xb") as image_file:
            image_file.write(image_data)
    except OSError:
        try:
            image_path.unlink(missing_ok=True)
        except OSError:
            app.logger.exception("Failed to remove incomplete ticket image %s", filename)
        raise
    return filename


def stored_image_path(filename):
    if not isinstance(filename, str) or not re.fullmatch(r"[a-f0-9]{32}\.(?:png|jpg|webp)", filename):
        raise ValueError("Invalid stored image filename.")
    return UPLOAD_DIR / filename


def migrate_legacy_images(cursor, connection):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        cursor.execute(
            "SELECT id, image_data FROM tickets "
            "WHERE image_data IS NOT NULL ORDER BY id LIMIT 1"
        )
        row = cursor.fetchone()
        if not row:
            break
        ticket_id, image_data = row
        content_type = detect_image_content_type(image_data)
        if content_type is None:
            raise RuntimeError(
                f"Cannot migrate ticket {ticket_id}: stored image has an unsupported format."
            )
        filename = store_image_file(image_data, content_type)
        cursor.execute(
            "UPDATE tickets SET image_filename = %s, image_content_type = %s, "
            "image_data = NULL WHERE id = %s",
            (filename, content_type, ticket_id),
        )
        connection.commit()


def initialise_database():
    connection = database_connection(False)
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    finally:
        cursor.close()
        connection.close()

    connection = database_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INT AUTO_INCREMENT PRIMARY KEY,
              name VARCHAR(100) NOT NULL,
              email VARCHAR(190) NOT NULL UNIQUE,
              password_hash VARCHAR(255) NOT NULL,
              role ENUM('student', 'maintenance', 'admin') NOT NULL DEFAULT 'student',
              department VARCHAR(100) DEFAULT NULL,
              created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
              id INT AUTO_INCREMENT PRIMARY KEY,
              reporter_id INT NOT NULL,
              issue_type VARCHAR(100) NOT NULL,
              department VARCHAR(100) NOT NULL DEFAULT 'General',
              location VARCHAR(200) NOT NULL,
              priority ENUM('Low', 'Medium', 'High', 'Critical') NOT NULL DEFAULT 'Medium',
              description TEXT NOT NULL,
              image_filename VARCHAR(100) DEFAULT NULL,
              image_content_type VARCHAR(20) DEFAULT NULL,
              status ENUM('Open', 'In Progress', 'Resolved') NOT NULL DEFAULT 'Open',
              created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              CONSTRAINT fk_ticket_reporter FOREIGN KEY (reporter_id)
                REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
            """
        )
        cursor.execute("SHOW COLUMNS FROM users LIKE 'role'")
        role_column = cursor.fetchone()
        if role_column and "admin" not in role_column[1]:
            cursor.execute(
                "ALTER TABLE users MODIFY COLUMN role "
                "ENUM('student', 'maintenance', 'admin') NOT NULL DEFAULT 'student'"
            )
        cursor.execute("SHOW COLUMNS FROM users LIKE 'department'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE users ADD COLUMN department VARCHAR(100) DEFAULT NULL")
        cursor.execute(
            "UPDATE users SET department = 'General' "
            "WHERE role = 'maintenance' AND department IS NULL"
        )
        cursor.execute("SHOW COLUMNS FROM tickets LIKE 'department'")
        if not cursor.fetchone():
            cursor.execute(
                "ALTER TABLE tickets ADD COLUMN department VARCHAR(100) "
                "NOT NULL DEFAULT 'General' AFTER issue_type"
            )
        for column, definition in (
            ("image_filename", "VARCHAR(100) DEFAULT NULL"),
            ("image_content_type", "VARCHAR(20) DEFAULT NULL"),
        ):
            cursor.execute(f"SHOW COLUMNS FROM tickets LIKE '{column}'")
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE tickets ADD COLUMN {column} {definition}")
        cursor.execute("SHOW COLUMNS FROM tickets LIKE 'image_data'")
        if cursor.fetchone():
            migrate_legacy_images(cursor, connection)
            cursor.execute("ALTER TABLE tickets DROP COLUMN image_data")
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def issue_token(user):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user["id"]),
            "iat": now,
            "exp": now + timedelta(hours=8),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def current_user(required_role=None):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None, (jsonify(message="Please sign in to continue."), 401)
    try:
        payload = jwt.decode(header[7:], JWT_SECRET, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError):
        return None, (jsonify(message="Your session has expired. Please sign in again."), 401)
    connection = database_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, role, department FROM users WHERE id = %s",
            (user_id,),
        )
        user = cursor.fetchone()
    finally:
        cursor.close()
        connection.close()
    if not user or user["role"] not in VALID_ROLES:
        return None, (jsonify(message="Your session is invalid. Please sign in again."), 401)
    if required_role and user["role"] != required_role:
        return None, (jsonify(message="You do not have access to this resource."), 403)
    return user, None


def require_role(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user, error = current_user(role)
            if error:
                return error
            g.user = user
            return view(*args, **kwargs)

        return wrapped

    return decorator


def ticket_dict(row):
    return {
        "id": row["id"],
        "issueType": row["issue_type"],
        "department": row["department"],
        "location": row["location"],
        "priority": row["priority"],
        "description": row["description"],
        "status": row["status"],
        "hasImage": bool(row["has_image"]),
        "createdAt": row["created_at"].isoformat(),
        "updatedAt": row["updated_at"].isoformat(),
        "reporterName": row.get("reporter_name"),
        "reporterEmail": row.get("reporter_email"),
    }


@app.get("/api/health")
def health():
    return jsonify(status="ok")


@app.post("/api/auth/register")
def register():
    data = request_data()
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    role = data.get("role")
    department = data.get("department")
    if (
        not name
        or len(name) > 100
        or len(email) > 190
        or len(password) < 8
        or not isinstance(role, str)
        or role not in VALID_ROLES
        or (
            role == "maintenance"
            and (not isinstance(department, str) or department not in DEPARTMENTS)
        )
    ):
        return jsonify(
            message="Enter a name, valid email, password of at least 8 characters, account type, and maintenance department if applicable."
        ), 400
    if not re.fullmatch(r"[^@\s]+@iiitl\.ac\.in", email):
        return jsonify(message="Sign-up is limited to email addresses ending in @iiitl.ac.in."), 400
    if role != "maintenance":
        department = None

    connection = database_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify(message="An account with that email already exists."), 409
        cursor.execute(
            "INSERT INTO users (name, email, password_hash, role, department) "
            "VALUES (%s, %s, %s, %s, %s)",
            (name, email, generate_password_hash(password), role, department),
        )
        connection.commit()
        user = {
            "id": cursor.lastrowid,
            "name": name,
            "email": email,
            "role": role,
            "department": department,
        }
        return jsonify(
            message="Account created.",
            token=issue_token(user),
            user={key: user[key] for key in ("name", "email", "role", "department")},
        ), 201
    except mysql.connector.IntegrityError as error:
        if error.errno == 1062:
            return jsonify(message="An account with that email already exists."), 409
        raise
    finally:
        cursor.close()
        connection.close()


@app.post("/api/auth/login")
def login():
    data = request_data()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    department = data.get("department")
    if not email or not password:
        return jsonify(message="Enter your email and password."), 400

    connection = database_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, name, email, password_hash, role, department "
            "FROM users WHERE email = %s",
            (email,),
        )
        user = cursor.fetchone()
    finally:
        cursor.close()
        connection.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify(message="Incorrect email or password."), 401
    if user["role"] == "maintenance":
        if not isinstance(department, str) or department not in DEPARTMENTS:
            return jsonify(message="Select your assigned maintenance department."), 400
        if user["department"] != department:
            return jsonify(message="Incorrect email, password, or department."), 401
    return jsonify(
        message="Welcome back.",
        token=issue_token(user),
        user={key: user[key] for key in ("name", "email", "role", "department")},
    )


@app.get("/api/tickets")
def list_tickets():
    user, error = current_user()
    if error:
        return error

    connection = database_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        query = TICKET_SELECT
        conditions = []
        params = []
        if user["role"] == "student":
            conditions.append("t.reporter_id = %s")
            params.append(user["id"])
        elif user["role"] == "maintenance":
            conditions.append("t.department = %s")
            params.append(user["department"])
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        cursor.execute(query + " ORDER BY t.created_at DESC", tuple(params))
        tickets = [ticket_dict(row) for row in cursor.fetchall()]
        return jsonify(tickets=tickets)
    finally:
        cursor.close()
        connection.close()


@app.post("/api/tickets")
@require_role("student")
def create_ticket():
    data = request.form if request.mimetype == "multipart/form-data" else request_data()
    issue_type = str(data.get("issueType", "")).strip()
    location = str(data.get("location", "")).strip()
    description = str(data.get("description", "")).strip()
    department = data.get("department")
    priority = data.get("priority", "Medium")
    image_file = request.files.get("image") if request.mimetype == "multipart/form-data" else None
    image_data = None
    image_content_type = None
    if image_file and image_file.filename:
        image_data = image_file.stream.read(MAX_IMAGE_SIZE + 1)
        if len(image_data) > MAX_IMAGE_SIZE:
            return jsonify(message="The image must be 5 MB or smaller."), 413
        image_content_type = detect_image_content_type(image_data)
        if image_content_type is None:
            return jsonify(message="Upload a valid JPEG, PNG, or WebP image."), 400
    if (
        not issue_type
        or len(issue_type) > 100
        or not location
        or len(location) > 200
        or not description
        or not isinstance(department, str)
        or department not in DEPARTMENTS
        or not isinstance(priority, str)
        or priority not in VALID_PRIORITIES
    ):
        return jsonify(message="Complete every ticket field with a valid priority."), 400

    connection = database_connection()
    cursor = connection.cursor(dictionary=True)
    image_filename = None
    try:
        image_filename = store_image_file(image_data, image_content_type) if image_data is not None else None
        cursor.execute(
            """
            INSERT INTO tickets (
              reporter_id, issue_type, department, location, priority, description,
              image_filename, image_content_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                g.user["id"], issue_type, department, location, priority, description,
                image_filename, image_content_type,
            ),
        )
        ticket_id = cursor.lastrowid
        connection.commit()
    except Exception:
        if image_filename:
            try:
                stored_image_path(image_filename).unlink(missing_ok=True)
            except OSError:
                app.logger.exception("Failed to remove unreferenced ticket image %s", image_filename)
        raise
    finally:
        cursor.close()
        connection.close()

    connection = database_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(TICKET_SELECT + " WHERE t.id = %s", (ticket_id,))
        ticket = ticket_dict(cursor.fetchone())
        return jsonify(message="Maintenance ticket created.", ticket=ticket), 201
    finally:
        cursor.close()
        connection.close()


@app.patch("/api/tickets/<int:ticket_id>/status")
@require_role("maintenance")
def update_status(ticket_id):
    status = request_data().get("status")
    if not isinstance(status, str) or status not in VALID_STATUSES:
        return jsonify(message="Choose a valid ticket status."), 400

    connection = database_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "UPDATE tickets SET status = %s WHERE id = %s AND department = %s",
            (status, ticket_id, g.user["department"]),
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "SELECT id FROM tickets WHERE id = %s AND department = %s",
                (ticket_id, g.user["department"]),
            )
            if not cursor.fetchone():
                return jsonify(message="Ticket not found in your department."), 404
        connection.commit()
        cursor.execute(TICKET_SELECT + " WHERE t.id = %s", (ticket_id,))
        return jsonify(message="Ticket updated.", ticket=ticket_dict(cursor.fetchone()))
    finally:
        cursor.close()
        connection.close()


def detect_image_content_type(image_data):
    if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(image_data) >= 12 and image_data[:4] == b"RIFF" and image_data[8:12] == b"WEBP":
        return "image/webp"
    return None


@app.get("/api/tickets/<int:ticket_id>/image")
def ticket_image(ticket_id):
    user, error = current_user()
    if error:
        return error

    query = (
        "SELECT image_filename, image_content_type FROM tickets "
        "WHERE id = %s AND image_filename IS NOT NULL"
    )
    params = [ticket_id]
    if user["role"] == "student":
        query += " AND reporter_id = %s"
        params.append(user["id"])
    elif user["role"] == "maintenance":
        query += " AND department = %s"
        params.append(user["department"])

    connection = database_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(query, tuple(params))
        image = cursor.fetchone()
    finally:
        cursor.close()
        connection.close()

    if not image:
        return jsonify(message="Image not found."), 404
    try:
        image_path = stored_image_path(image["image_filename"])
    except ValueError:
        app.logger.error("Invalid image filename stored for ticket %s.", ticket_id)
        return jsonify(message="Stored image path is invalid."), 500
    if not image_path.is_file():
        app.logger.error("Image file for ticket %s is missing from disk.", ticket_id)
        return jsonify(message="Stored image file is missing."), 500
    response = send_file(image_path, mimetype=image["image_content_type"], conditional=False)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.errorhandler(mysql.connector.Error)
def mysql_error(error):
    app.logger.exception("MySQL operation failed")
    return jsonify(
        message="Database connection failed. Check backend/.env, MySQL permissions, and that MySQL is running."
    ), 500


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify(message="The uploaded image must be 5 MB or smaller."), 413


if __name__ == "__main__":
    initialise_database()
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
