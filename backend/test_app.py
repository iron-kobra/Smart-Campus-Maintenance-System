import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app, detect_image_content_type, issue_token, store_image_file, stored_image_path
from werkzeug.security import generate_password_hash


class MaintenanceApiTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    @patch("app.database_connection")
    def test_login_does_not_require_account_type(self, connect):
        connect.return_value.cursor.return_value.fetchone.return_value = {
            "id": 8,
            "name": "Student",
            "email": "student@example.com",
            "password_hash": generate_password_hash("valid-password"),
            "role": "student",
            "department": None,
        }

        response = self.client.post(
            "/api/auth/login",
            json={"email": "student@example.com", "password": "valid-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["role"], "student")

    @patch("app.database_connection")
    def test_maintenance_login_requires_its_department_not_account_type(self, connect):
        connect.return_value.cursor.return_value.fetchone.return_value = {
            "id": 9,
            "name": "Maintenance",
            "email": "maintenance@example.com",
            "password_hash": generate_password_hash("valid-password"),
            "role": "maintenance",
            "department": "Electrical",
        }

        response = self.client.post(
            "/api/auth/login",
            json={
                "email": "maintenance@example.com",
                "password": "valid-password",
                "department": "Electrical",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["department"], "Electrical")

    def test_image_type_is_detected_from_file_signature(self):
        self.assertEqual(detect_image_content_type(b"\x89PNG\r\n\x1a\nrest"), "image/png")
        self.assertEqual(detect_image_content_type(b"\xff\xd8\xffrest"), "image/jpeg")
        self.assertEqual(detect_image_content_type(b"RIFF1234WEBPrest"), "image/webp")
        self.assertIsNone(detect_image_content_type(b"<svg></svg>"))

    def test_image_is_written_to_disk_with_a_generated_filename(self):
        image_bytes = b"\x89PNG\r\n\x1a\nimage"
        with tempfile.TemporaryDirectory() as directory:
            with patch("app.UPLOAD_DIR", Path(directory)):
                filename = store_image_file(image_bytes, "image/png")
                self.assertRegex(filename, re.compile(r"^[a-f0-9]{32}\.png$"))
                self.assertEqual(stored_image_path(filename).read_bytes(), image_bytes)
                with self.assertRaises(ValueError):
                    stored_image_path("..\\outside.png")

    @patch("app.database_connection")
    def test_invalid_registration_is_rejected_before_database_access(self, connect):
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "Demo User",
                "email": "demo@iiitl.ac.in",
                "password": "short",
                "role": "student",
            },
        )
        self.assertEqual(response.status_code, 400)
        connect.assert_not_called()

    @patch("app.database_connection")
    def test_registration_rejects_other_and_subdomains(self, connect):
        for email in ("user@example.com", "user@dept.iiitl.ac.in", "user@iiitl.ac.in.example.com"):
            with self.subTest(email=email):
                response = self.client.post(
                    "/api/auth/register",
                    json={
                        "name": "Demo User",
                        "email": email,
                        "password": "valid-password",
                        "role": "student",
                    },
                )
                self.assertEqual(response.status_code, 400)
        connect.assert_not_called()

    @patch("app.database_connection")
    def test_registration_accepts_iiitl_domain_case_insensitively(self, connect):
        cursor = connect.return_value.cursor.return_value
        cursor.fetchone.return_value = None
        cursor.lastrowid = 12

        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "IIITL User",
                "email": "User@IIITL.AC.IN",
                "password": "valid-password",
                "role": "student",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["user"]["email"], "user@iiitl.ac.in")
        inserted_user = cursor.execute.call_args_list[1].args[1]
        self.assertEqual(inserted_user[1], "user@iiitl.ac.in")

    @patch("app.database_connection")
    def test_maintenance_registration_requires_a_valid_department(self, connect):
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "Maintenance User",
                "email": "maintenance@example.com",
                "password": "valid-password",
                "role": "maintenance",
                "department": "Unknown",
            },
        )
        self.assertEqual(response.status_code, 400)
        connect.assert_not_called()

    @patch("app.database_connection")
    def test_ticket_list_is_scoped_to_maintenance_department(self, connect):
        cursor = connect.return_value.cursor.return_value
        cursor.fetchone.return_value = {
            "id": 2,
            "role": "maintenance",
            "department": "Electrical",
        }
        cursor.fetchall.return_value = []
        token = issue_token({"id": 2, "role": "maintenance"})

        response = self.client.get(
            "/api/tickets",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"tickets": []})
        ticket_query, ticket_params = cursor.execute.call_args_list[1].args
        self.assertIn("WHERE t.department = %s", ticket_query)
        self.assertEqual(ticket_params, ("Electrical",))

    @patch("app.database_connection")
    def test_admin_ticket_list_is_not_department_or_student_scoped(self, connect):
        cursor = connect.return_value.cursor.return_value
        cursor.fetchone.return_value = {
            "id": 3,
            "role": "admin",
            "department": None,
        }
        cursor.fetchall.return_value = []
        token = issue_token({"id": 3, "role": "admin"})

        response = self.client.get(
            "/api/tickets",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        ticket_query, ticket_params = cursor.execute.call_args_list[1].args
        self.assertNotIn("WHERE", ticket_query)
        self.assertEqual(ticket_params, ())

    @patch("app.database_connection")
    def test_maintenance_status_update_cannot_cross_departments(self, connect):
        cursor = connect.return_value.cursor.return_value
        cursor.fetchone.side_effect = [
            {"id": 2, "role": "maintenance", "department": "Electrical"},
            None,
        ]
        cursor.rowcount = 0
        token = issue_token({"id": 2, "role": "maintenance"})

        response = self.client.patch(
            "/api/tickets/9/status",
            json={"status": "Resolved"},
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 404)
        update_query, update_params = cursor.execute.call_args_list[1].args
        self.assertIn("department = %s", update_query)
        self.assertEqual(update_params, ("Resolved", 9, "Electrical"))

    @patch("app.database_connection")
    def test_non_object_registration_payload_is_rejected(self, connect):
        response = self.client.post("/api/auth/register", json=["not", "an", "object"])
        self.assertEqual(response.status_code, 400)
        connect.assert_not_called()

    def test_ticket_list_requires_login(self):
        response = self.client.get("/api/tickets")
        self.assertEqual(response.status_code, 401)

    @patch("app.database_connection")
    def test_students_cannot_update_ticket_status(self, connect):
        connect.return_value.cursor.return_value.fetchone.return_value = {
            "id": 1,
            "role": "student",
            "department": None,
        }
        token = issue_token({"id": 1, "role": "student"})
        response = self.client.patch(
            "/api/tickets/1/status",
            json={"status": "Resolved"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 403)

    @patch("app.database_connection")
    def test_admin_cannot_update_ticket_status(self, connect):
        connect.return_value.cursor.return_value.fetchone.return_value = {
            "id": 1,
            "role": "admin",
            "department": None,
        }
        token = issue_token({"id": 1, "role": "admin"})

        response = self.client.patch(
            "/api/tickets/1/status",
            json={"status": "Resolved"},
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
