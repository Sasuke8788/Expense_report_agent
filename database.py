from __future__ import annotations

import os
import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_PATH = Path(os.getenv("EXPENSE_DB_PATH", ROOT / "data" / "expenses.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

EMPLOYEES = [
    ("Aditi Sharma", "Product Engineering", "aditi.sharma@example.com"),
    ("Rohan Mehta", "Sales", "rohan.mehta@example.com"),
    ("Priya Nair", "Finance", "priya.nair@example.com"),
    ("Arjun Desai", "Customer Success", "arjun.desai@example.com"),
    ("Meera Iyer", "Product Engineering", "meera.iyer@example.com"),
    ("Kabir Shah", "Marketing", "kabir.shah@example.com"),
]
VENDORS = [
    ("IndiGo Airlines", "Flight booking", "Flights", 4500),
    ("Cafe Coffee Day", "Client lunch", "Meals", 850),
    ("Taj Hotels", "Business accommodation", "Lodging", 6200),
    ("Uber", "Airport transfer", "Transport", 620),
    ("Domino's Pizza", "Team dinner", "Meals", 1200),
    ("Ola Cabs", "Client visit cab", "Transport", 540),
    ("Vistara", "Business flight", "Flights", 7100),
    ("The Leela", "Hotel stay", "Lodging", 6100),
    ("Blue Tokai", "Client coffee", "Meals", 480),
    ("Airport Express", "Airport transit", "Transport", 350),
    ("Air India", "Return flight", "Flights", 6800),
    ("Lemon Tree Hotels", "Business accommodation", "Lodging", 3900),
    ("Barista", "Team meeting refreshments", "Meals", 620),
    ("Meru Cabs", "Office to client site", "Transport", 430),
]

def _make_engine() -> tuple[Engine | None, bool]:
    if IS_POSTGRES:
        url = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1).replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
        try:
            engine = create_engine(
                url,
                pool_pre_ping=True,
                pool_recycle=300,
                pool_size=5,
                max_overflow=10,
            )
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return engine, True
        except (OperationalError, ImportError):
            return None, False

    url = f"sqlite:///{DB_PATH.as_posix()}"
    return create_engine(url, connect_args={"check_same_thread": False, "timeout": 10}), False

ENGINE, POSTGRES_AVAILABLE = _make_engine()
if ENGINE is None:
    url = f"sqlite:///{DB_PATH.as_posix()}"
    ENGINE = create_engine(url, connect_args={"check_same_thread": False, "timeout": 10})
    POSTGRES_AVAILABLE = False

@contextmanager
def connect() -> Iterator:
    with ENGINE.begin() as connection:
        yield connection

def init_db() -> None:
    if POSTGRES_AVAILABLE:
        schema = """
        CREATE TABLE IF NOT EXISTS employees(
          id BIGSERIAL PRIMARY KEY,
          name TEXT NOT NULL UNIQUE,
          department TEXT NOT NULL,
          email TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS expenses(
          id BIGSERIAL PRIMARY KEY,
          employee_name TEXT NOT NULL,
          expense_date TEXT NOT NULL,
          vendor TEXT NOT NULL,
          description TEXT NOT NULL,
          category TEXT NOT NULL,
          amount NUMERIC(12,2),
          receipt_id TEXT,
          review_note TEXT,
          updated_at TIMESTAMPTZ,
          FOREIGN KEY(employee_name) REFERENCES employees(name)
        );
        CREATE TABLE IF NOT EXISTS reports(
          id BIGSERIAL PRIMARY KEY,
          employee_name TEXT NOT NULL,
          target_month TEXT NOT NULL,
          version INTEGER NOT NULL,
          pdf_path TEXT NOT NULL,
          grand_total NUMERIC(12,2) NOT NULL,
          needs_review BOOLEAN NOT NULL,
          status TEXT NOT NULL DEFAULT 'Generated',
          email_status TEXT NOT NULL DEFAULT 'Not sent',
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(employee_name,target_month,version)
        );
        CREATE INDEX IF NOT EXISTS idx_expenses_employee_month
          ON expenses(employee_name, expense_date);
        CREATE TABLE IF NOT EXISTS login_accounts(
          employee_name TEXT PRIMARY KEY,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'employee',
          email TEXT
        );
        CREATE TABLE IF NOT EXISTS login_sessions(
          token_hash TEXT PRIMARY KEY,
          employee_name TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'employee',
          expires_at TIMESTAMPTZ NOT NULL
        );
        """
    else:
        schema = """
        CREATE TABLE IF NOT EXISTS employees(
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL UNIQUE,
          department TEXT NOT NULL,
          email TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS expenses(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          employee_name TEXT NOT NULL,
          expense_date TEXT NOT NULL,
          vendor TEXT NOT NULL,
          description TEXT NOT NULL,
          category TEXT NOT NULL,
          amount REAL,
          receipt_id TEXT,
          review_note TEXT,
          updated_at TEXT,
          FOREIGN KEY(employee_name) REFERENCES employees(name)
        );
        CREATE TABLE IF NOT EXISTS reports(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          employee_name TEXT NOT NULL,
          target_month TEXT NOT NULL,
          version INTEGER NOT NULL,
          pdf_path TEXT NOT NULL,
          grand_total REAL NOT NULL,
          needs_review INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'Generated',
          email_status TEXT NOT NULL DEFAULT 'Not sent',
          created_at TEXT NOT NULL,
          UNIQUE(employee_name,target_month,version)
        );
        CREATE TABLE IF NOT EXISTS login_accounts(
          employee_name TEXT PRIMARY KEY,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'employee',
          email TEXT
        );
        CREATE TABLE IF NOT EXISTS login_sessions(
          token_hash TEXT PRIMARY KEY,
          employee_name TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'employee',
          expires_at TEXT NOT NULL
        );
        """

    with connect() as c:
        for statement in schema.split(";"):
            if statement.strip():
                c.execute(text(statement))

        if POSTGRES_AVAILABLE:
            c.execute(text("ALTER TABLE login_accounts ADD COLUMN IF NOT EXISTS role TEXT"))
            c.execute(text("ALTER TABLE login_accounts ADD COLUMN IF NOT EXISTS email TEXT"))
            c.execute(text("UPDATE login_accounts SET role = 'employee' WHERE role IS NULL"))
            c.execute(text("ALTER TABLE login_accounts ALTER COLUMN role SET DEFAULT 'employee'"))
            c.execute(text("""
                DO $$
                DECLARE constraint_name text;
                BEGIN
                  SELECT conname INTO constraint_name
                  FROM pg_constraint
                  WHERE conrelid = 'login_sessions'::regclass
                    AND contype = 'f'
                    AND pg_get_constraintdef(oid) LIKE '%employee_name%employees%';
                  IF constraint_name IS NOT NULL THEN
                    EXECUTE 'ALTER TABLE login_sessions DROP CONSTRAINT ' || quote_ident(constraint_name);
                  END IF;
                END $$;
            """))
            c.execute(text("ALTER TABLE login_sessions ADD COLUMN IF NOT EXISTS role TEXT"))
            c.execute(text("UPDATE login_sessions SET role = 'employee' WHERE role IS NULL"))
            c.execute(text("ALTER TABLE login_sessions ALTER COLUMN role SET DEFAULT 'employee'"))

        employee_count = c.execute(text("SELECT COUNT(*) FROM employees")).scalar_one()
        if employee_count == 0:
            c.execute(
                text("INSERT INTO employees(name, department, email) VALUES (:name, :department, :email)"),
                [{"name": name, "department": department, "email": email} for name, department, email in EMPLOYEES],
            )

        expense_count = c.execute(text("SELECT COUNT(*) FROM expenses")).scalar_one()
        if expense_count == 0:
            rows = []
            months = [(2026, month) for month in range(1, 10)]
            eid = 1000
            for emp_idx, (employee, _department, _email) in enumerate(EMPLOYEES):
                for year, month in months:
                    for j in range(4):
                        vendor, description, category, base = VENDORS[(emp_idx * 2 + j + month) % len(VENDORS)]
                        day = min(3 + j * 5, 28)
                        amount = round(base * (0.82 + ((emp_idx + j + month) % 7) * 0.07), 2)
                        receipt = f"RCPT-{eid}"
                        if employee == "Aditi Sharma" and month == 7 and j == 2:
                            amount = None
                        if employee == "Aditi Sharma" and month == 7 and j == 3:
                            receipt = None
                        if employee == "Rohan Mehta" and month == 6 and j == 1:
                            receipt = None
                        rows.append({
                            "employee": employee,
                            "date": f"{year}-{month:02d}-{day:02d}",
                            "vendor": vendor,
                            "description": description,
                            "category": category,
                            "amount": amount,
                            "receipt": receipt,
                        })
                        eid += 1
            c.execute(
                text("""INSERT INTO expenses
                    (employee_name, expense_date, vendor, description, category, amount, receipt_id, review_note, updated_at)
                    VALUES (:employee, :date, :vendor, :description, :category, :amount, :receipt, NULL, NULL)"""),
                rows,
            )

        account_count = c.execute(text("SELECT COUNT(*) FROM login_accounts")).scalar_one()
        if account_count == 0:
            demo_password = os.getenv("DEMO_EMPLOYEE_PASSWORD", "employee123")
            password_hash = hashlib.pbkdf2_hmac(
                "sha256", demo_password.encode(), b"expenseflow-demo-v1", 120_000
            ).hex()
            c.execute(
                text("""INSERT INTO login_accounts(employee_name, password_hash)
                        SELECT name, :password_hash FROM employees"""),
                {"password_hash": password_hash},
            )
        employer_email = os.getenv("EMPLOYER_EMAIL", "").strip().lower()
        employer_password = os.getenv("EMPLOYER_PASSWORD", "")
        if employer_email and employer_password:
            employer_hash = hashlib.pbkdf2_hmac(
                "sha256", employer_password.encode(), b"expenseflow-demo-v1", 120_000
            ).hex()
            c.execute(text("""
                INSERT INTO login_accounts(employee_name, password_hash, role, email)
                VALUES ('Finance Employer', :password_hash, 'employer', :email)
                ON CONFLICT (employee_name) DO UPDATE
                SET password_hash = EXCLUDED.password_hash,
                    role = 'employer',
                    email = EXCLUDED.email
            """) if POSTGRES_AVAILABLE else text("""
                INSERT INTO login_accounts(employee_name, password_hash, role, email)
                VALUES ('Finance Employer', :password_hash, 'employer', :email)
                ON CONFLICT(employee_name) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    role = 'employer',
                    email = excluded.email
            """), {"password_hash": employer_hash, "email": employer_email})

init_db()

def employees():
    with connect() as c:
        rows = c.execute(text("SELECT name, department, email FROM employees ORDER BY name")).mappings()
        return [dict(row) for row in rows]

def get_expenses(employee_name: str, target_month: str):
    with connect() as c:
        rows = c.execute(text("""
            SELECT id, employee_name AS employee, expense_date AS date, vendor, description,
                   category, amount, receipt_id, review_note
            FROM expenses
            WHERE lower(employee_name) = lower(:employee)
              AND substr(expense_date, 1, 7) = :month
            ORDER BY expense_date, id
        """), {"employee": employee_name, "month": target_month}).mappings()
        result = []
        for row in rows:
            item = dict(row)
            if item["amount"] is not None:
                item["amount"] = float(item["amount"])
            result.append(item)
        return result

def available_months(employee_name: str):
    with connect() as c:
        rows = c.execute(text("""
            SELECT DISTINCT substr(expense_date, 1, 7) AS month
            FROM expenses
            WHERE lower(employee_name) = lower(:employee)
            ORDER BY month DESC
        """), {"employee": employee_name}).scalars()
        return list(rows)

def update_expenses(changes, employee_name: str | None = None):
    updated = []
    with connect() as c:
        for item in changes:
            expense_id = int(item["id"])
            params = {"id": expense_id}
            employee_sql = ""
            if employee_name:
                employee_sql = " AND lower(employee_name) = lower(:employee)"
                params["employee"] = employee_name
            row = c.execute(text(f"SELECT id FROM expenses WHERE id = :id{employee_sql}"), params).first()
            if not row:
                raise ValueError(f"Expense record {expense_id} does not exist.")
            amount = item.get("amount")
            if amount is not None:
                amount = float(amount)
                if amount <= 0:
                    raise ValueError("Amounts must be greater than zero.")
            c.execute(text("""
                UPDATE expenses
                SET amount = :amount,
                    receipt_id = :receipt,
                    review_note = :note,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {
                "amount": amount,
                "receipt": item.get("receipt_id") or None,
                "note": item.get("review_note") or None,
                "id": expense_id,
            })
            updated.append(expense_id)
    return updated

def save_report(employee: str, month: str, pdf_path: str, total: float, needs_review: bool):
    with connect() as c:
        version = c.execute(text("""
            SELECT COALESCE(MAX(version), 0) + 1
            FROM reports
            WHERE employee_name = :employee AND target_month = :month
        """), {"employee": employee, "month": month}).scalar_one()
        timestamp_sql = "CURRENT_TIMESTAMP" if POSTGRES_AVAILABLE else "datetime('now')"
        returning_sql = "RETURNING id" if POSTGRES_AVAILABLE else ""
        result = c.execute(text(f"""
            INSERT INTO reports(
                employee_name, target_month, version, pdf_path, grand_total,
                needs_review, status, email_status, created_at
            )
            VALUES(
                :employee, :month, :version, :pdf_path, :total,
                :needs_review, :status, 'Not sent', {timestamp_sql}
            )
            {returning_sql}
        """), {
            "employee": employee,
            "month": month,
            "version": version,
            "pdf_path": pdf_path,
            "total": total,
            "needs_review": needs_review,
            "status": "Needs Review" if needs_review else "Ready",
        })
        report_id = result.scalar_one() if POSTGRES_AVAILABLE else result.lastrowid

    return {
        "id": report_id,
        "employee_name": employee,
        "target_month": month,
        "version": version,
        "pdf_path": pdf_path,
        "grand_total": float(total),
        "needs_review": bool(needs_review),
        "status": "Needs Review" if needs_review else "Ready",
        "email_status": "Not sent",
    }

def list_reports(employee: str | None = None):
    with connect() as c:
        if employee:
            rows = c.execute(text("""
                SELECT * FROM reports
                WHERE lower(employee_name) = lower(:employee)
                ORDER BY created_at DESC, id DESC
            """), {"employee": employee}).mappings()
        else:
            rows = c.execute(text("""
                SELECT * FROM reports
                ORDER BY created_at DESC, id DESC
            """)).mappings()
        return [dict(row) for row in rows]

def get_report(report_id: int):
    with connect() as c:
        row = c.execute(text("SELECT * FROM reports WHERE id = :id"), {"id": int(report_id)}).mappings().first()
        return dict(row) if row else None

def set_email_status(report_id: int, status: str):
    with connect() as c:
        c.execute(text("UPDATE reports SET email_status = :status WHERE id = :id"), {
            "status": status,
            "id": int(report_id),
        })

def save_report_pdf_path(report_id: int, pdf_path: str):
    with connect() as c:
        c.execute(text("UPDATE reports SET pdf_path = :pdf_path WHERE id = :id"), {
            "pdf_path": pdf_path,
            "id": int(report_id),
        })

def authenticate_employee(employee_name: str, password: str):
    with connect() as c:
        row = c.execute(text("""
            SELECT password_hash, role, email FROM login_accounts
            WHERE lower(employee_name) = lower(:employee)
               OR lower(email) = lower(:employee)
        """), {"employee": employee_name}).first()
        if not row:
            return None
        expected = row[0]
        supplied = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), b"expenseflow-demo-v1", 120_000
        ).hex()
        if not hmac.compare_digest(expected, supplied):
            return None
        if row[1] == "employer":
            return {"name": "Finance Employer", "role": "employer", "email": row[2]}
        employee = c.execute(text("""
            SELECT name, department, email FROM employees
            WHERE lower(name) = lower(:employee)
        """), {"employee": employee_name}).mappings().first()
        if not employee:
            return None
        result = dict(employee)
        result["role"] = "employee"
        return result

def create_session(employee_name: str, role: str = "employee"):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connect() as c:
        if POSTGRES_AVAILABLE:
            expires_sql = "CURRENT_TIMESTAMP + INTERVAL '12 hours'"
        else:
            expires_sql = "datetime('now', '+12 hours')"
        c.execute(text(f"""
            INSERT INTO login_sessions(token_hash, employee_name, role, expires_at)
            VALUES (:token_hash, :employee, :role, {expires_sql})
        """), {"token_hash": token_hash, "employee": employee_name, "role": role})
    return token

def get_session_employee(token: str | None):
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connect() as c:
        if POSTGRES_AVAILABLE:
            condition = "expires_at > CURRENT_TIMESTAMP"
        else:
            condition = "expires_at > datetime('now')"
        row = c.execute(text(f"""
            SELECT employee_name, role FROM login_sessions
            WHERE token_hash = :token_hash
              AND {condition}
        """), {"token_hash": token_hash}).first()
        return (row[0], row[1]) if row else None

def delete_session(token: str | None):
    if not token:
        return
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connect() as c:
        c.execute(text("DELETE FROM login_sessions WHERE token_hash = :token_hash"),
                  {"token_hash": token_hash})

def delete_report(report_id: int, employee_name: str):
    with connect() as c:
        row = c.execute(text("""
            SELECT id, pdf_path FROM reports
            WHERE id = :id AND lower(employee_name) = lower(:employee)
        """), {"id": int(report_id), "employee": employee_name}).first()
        if not row:
            return False
        c.execute(text("DELETE FROM reports WHERE id = :id"), {"id": int(report_id)})
    pdf_path = row[1]
    try:
        Path(pdf_path).unlink(missing_ok=True)
    except OSError:
        pass
    return True
