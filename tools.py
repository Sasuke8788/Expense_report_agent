import os
import smtplib
import json
import base64
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fpdf import FPDF
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# ---------------------------------------------------------------------------
# 1. SIMULATED LOCAL DATABASE
# ---------------------------------------------------------------------------
# A hardcoded list of dicts standing in for a real receipts database/API
# (constraint: "No Database APIs"), so the demo never depends on a live
# connection. NOTE the Taj Hotels row: `amount` is deliberately `None` —
# that's what guarantees the Anomaly Handler branch is reachable whenever
# you demo with Aditi Sharma / 2026-07.
# `receipt_id` is the supporting document reference; the Domino's row has
# `None` there, so the assistant can also report "missing supporting info".
# Expense records are stored in SQLite. The database is seeded with synthetic
# enterprise records by database.py on first startup.
from database import get_expenses as _db_get_expenses, available_months as _db_available_months
MOCK_RECEIPTS = []  # retained only for backward-compatible imports

CANADA_DATASTORE_URL = (
    "https://open.canada.ca/data/api/3/action/datastore_search"
)
CANADA_RESOURCE_ID = "8282db2a-878f-475c-af10-ad56aa8fa72c"


def fetch_canada_expenses(limit: int = 100, offset: int = 0, query: str = "") -> dict:
    """Fetch records from the Government of Canada datastore resource."""
    params = {
        "resource_id": CANADA_RESOURCE_ID,
        "limit": max(1, min(int(limit), 1000)),
        "offset": max(0, int(offset)),
    }

    request = urllib.request.Request(
        f"{CANADA_DATASTORE_URL}?{urllib.parse.urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "ExpenseFlow/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Canada datastore returned HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach the Canada datastore: {exc.reason}") from exc

    if not payload.get("success"):
        raise RuntimeError(payload.get("error", "Canada datastore query failed"))

    result = payload["result"]
    records = result.get("records", [])
    if query.strip():
        needle = query.strip().lower()
        field = ""
        if ":" in needle:
            field, needle = (part.strip() for part in needle.split(":", 1))
        field_aliases = {
            "title": ("title_en", "title_fr"),
            "name": ("name",),
            "destination": ("destination_en", "destination_fr"),
        }
        searchable_fields = field_aliases.get(field)
        if searchable_fields:
            records = [
                record for record in records
                if any(needle in str(record.get(key) or "").lower() for key in searchable_fields)
            ]
        else:
            records = [
                record for record in records
                if any(needle in str(value).lower() for value in record.values())
            ]

    return {
        "resource_id": result["resource_id"],
        "total": result.get("total"),
        "records": records,
        "fields": result.get("fields", []),
    }



def get_mock_expenses(employee_name: str, target_month: str) -> list:
    """Retrieve persistent expense records for an employee and YYYY-MM month."""
    return _db_get_expenses(employee_name, target_month)



def get_available_months(employee_name: str) -> list:
    """Return months with records for this employee."""
    return _db_available_months(employee_name)



# ---------------------------------------------------------------------------
# 2. PDF GENERATION
# ---------------------------------------------------------------------------
def generate_pdf(
    employee_name: str,
    target_month: str,
    category_totals: dict,
    grand_total: float,
    discrepancy_note: str = "",
    output_dir: str | None = None,
) -> str:
    """
    Renders the finished expense report as a real, physical PDF file using
    fpdf2 (the maintained fork of the original `fpdf` library — it keeps
    the same `from fpdf import FPDF` import for backward compatibility).

    Returns the absolute path of the generated PDF, which the Compiler &
    Delivery node then hands to send_expense_email() as an attachment and
    to app.py for the Streamlit download button.
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "data", "generated_reports")
    os.makedirs(output_dir, exist_ok=True)
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Travel Expense Report", ln=True)

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Employee: {employee_name}", ln=True)
    pdf.cell(0, 8, f"Month: {target_month}", ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Category Breakdown", ln=True)
    pdf.set_font("Helvetica", "", 11)
    for category, total in category_totals.items():
        pdf.cell(0, 7, f"{category}: Rs. {total:,.2f}", ln=True)

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Grand Total: Rs. {grand_total:,.2f}", ln=True)

    # Only render the "Flagged for Review" block when there's actually a
    # discrepancy note to show — keeps clean-run PDFs uncluttered.
    if discrepancy_note:
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(200, 30, 30)
        pdf.cell(0, 8, "Flagged for Review", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, discrepancy_note)

    safe_name = employee_name.strip().replace(" ", "_")
    filename = f"expense_report_{safe_name}_{target_month}.pdf"
    output_path = os.path.join(output_dir, filename)
    pdf.output(output_path)
    return output_path


# ---------------------------------------------------------------------------
# 3. EMAIL DELIVERY
# ---------------------------------------------------------------------------
def send_expense_email(
    receiver_email: str,
    pdf_path: str,
    employee_name: str,
    target_month: str,
) -> dict:
    """
    Sends the generated PDF as an email attachment via Gmail's SMTP relay
    (smtp.gmail.com, port 587, STARTTLS) using ONLY Python's standard
    library — `smtplib` for the connection, `email.mime` for building a
    multipart message with an attachment. No third-party mail SDK needed.

    Reads sender credentials from environment variables (loaded from .env
    by expense_agent.py's `load_dotenv()`):
        SENDER_EMAIL        - the Gmail address sending the report
        EMAIL_APP_PASSWORD  - a Gmail "App Password", NOT the normal
                               account password (Gmail requires 2FA + an
                               App Password for third-party SMTP login)

    The whole call is wrapped in try/except so a viva demo with missing or
    incorrect credentials — or simply no internet in the exam hall — still
    finishes gracefully instead of crashing Streamlit. The returned dict
    tells the UI exactly what happened either way.
    """
    sender_email = os.getenv("SENDER_EMAIL", "").strip()
    app_password = os.getenv("EMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    resend_api_key = os.getenv("RESEND_API_KEY", "").strip()
    resend_from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev").strip()

    if resend_api_key:
        if not resend_from_email:
            return {
                "success": False,
                "message": "RESEND_FROM_EMAIL is not set.",
            }
        try:
            with open(pdf_path, "rb") as attachment_file:
                pdf_base64 = base64.b64encode(attachment_file.read()).decode("ascii")
            payload = {
                "from": resend_from_email,
                "to": [receiver_email],
                "subject": f"Travel Expense Report — {employee_name} — {target_month}",
                "text": (
                    "Dear Finance Team,\n\n"
                    f"Please find attached the travel expense report for {employee_name} for {target_month}.\n\n"
                    "Please review the attached report and follow the standard expense-processing procedure.\n"
                    "Any items marked 'Needs Review' require verification of the supporting information.\n\n"
                    "Kind regards,\nExpense Operations"
                ),
                "attachments": [{
                    "filename": os.path.basename(pdf_path),
                    "content": pdf_base64,
                }],
            }
            request = urllib.request.Request(
                "https://api.resend.com/emails",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "ExpenseFlow/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("id"):
                return {"success": True, "message": f"Email sent to {receiver_email}."}
            return {"success": False, "message": f"Hosted email API rejected the request: {result}"}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            return {
                "success": False,
                "message": f"Hosted email API returned HTTP {exc.code}: {body[:300]}",
            }
        except urllib.error.URLError as exc:
            return {
                "success": False,
                "message": f"Hosted email API could not be reached: {exc.reason}",
            }

    if not sender_email or not app_password or "your_" in sender_email or "your_" in app_password:
        return {
            "success": False,
            "message": "SENDER_EMAIL / EMAIL_APP_PASSWORD not set in .env — email not sent.",
        }

    if not sender_email.lower().endswith("@gmail.com"):
        return {
            "success": False,
            "message": "SENDER_EMAIL must be a Gmail address.",
        }

    if len(app_password) != 16:
        return {
            "success": False,
            "message": "EMAIL_APP_PASSWORD must be a 16-character Gmail App Password. Do not use the normal account password.",
        }

    try:
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = receiver_email
        message["Subject"] = f"Travel Expense Report — {employee_name} — {target_month}"

        # Fixed professional template; only employee and reporting month vary.
        body = (
            "Dear Finance Team,\n\n"
            f"Please find attached the travel expense report for {employee_name} for {target_month}.\n\n"
            "Please review the attached report and follow the standard expense-processing procedure. "
            "Any items marked 'Needs Review' require verification of the supporting information.\n\n"
            "Kind regards,\nExpense Operations"
        )
        message.attach(MIMEText(body, "plain"))

        with open(pdf_path, "rb") as f:
            attachment = MIMEBase("application", "octet-stream")
            attachment.set_payload(f.read())
        encoders.encode_base64(attachment)
        attachment.add_header(
            "Content-Disposition",
            f"attachment; filename={os.path.basename(pdf_path)}",
        )
        message.attach(attachment)

        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
                server.starttls()
                server.login(sender_email, app_password)
                server.send_message(message)
        except (smtplib.SMTPServerDisconnected, TimeoutError, OSError):
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
                server.login(sender_email, app_password)
                server.send_message(message)

        return {"success": True, "message": f"Email sent to {receiver_email}."}

    except smtplib.SMTPAuthenticationError as exc:
        return {
            "success": False,
            "message": "Gmail rejected the credentials. Enable 2-Step Verification and generate a 16-character Gmail App Password.",
        }
    except smtplib.SMTPRecipientsRefused:
        return {
            "success": False,
            "message": "Gmail rejected the recipient address.",
        }
    except (smtplib.SMTPServerDisconnected, TimeoutError, OSError) as exc:
        return {
            "success": False,
            "message": (
                "Gmail SMTP could not be reached from this deployment host "
                f"(network error: {exc}). Render free web services block outbound "
                "SMTP ports 25, 465, and 587; upgrade the Render instance or configure "
                "RESEND_API_KEY for HTTPS email delivery."
            ),
        }
    except Exception as exc:
        return {"success": False, "message": f"Email send failed: {exc}"}


# ---------------------------------------------------------------------------
# 4. CONFIRMED DELIVERY (Jury 2)
# ---------------------------------------------------------------------------
def send_confirmed_email(
    receiver_email: str,
    pdf_path: str,
    employee_name: str,
    target_month: str,
    demo_mode: bool = False,
) -> dict:
    """
    The ONLY place the app triggers an email, and it is only ever called
    after the employee explicitly confirms (button click or typing "yes").

    - demo_mode=True  -> nothing is sent; we return an honest "simulated"
                         result so the demo works offline / without
                         credentials and never claims a real send.
    - demo_mode=False -> calls the real Gmail SMTP sender above.

    Always returns {"success": bool, "status": "sent"|"failed"|"simulated",
    "message": str} so the UI can show the true outcome.
    """
    if demo_mode:
        return {
            "success": False,
            "status": "simulated",
            "message": f"Demo mode: email to {receiver_email} was NOT actually sent (simulated).",
        }
    result = send_expense_email(receiver_email, pdf_path, employee_name, target_month)
    result["status"] = "sent" if result["success"] else "failed"
    return result
