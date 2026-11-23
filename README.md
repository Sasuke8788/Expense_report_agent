# ExpenseFlow — Expense Report Agent

A role-based expense-reporting application with a React UI, FastAPI backend,
Neon PostgreSQL persistence, LangGraph workflows, PDF generation, and Gmail
delivery.

## Features

- Employee and employer login with server-enforced bearer sessions
- Employee users can access only their own expenses and reports
- Employer users can select and manage reports for every employee
- Expense review for missing amounts and receipt/document IDs
- Category analysis and report history
- Versioned PDF report generation
- PDF download and permanent report deletion
- Explicit Gmail recipient entry and send confirmation
- Demo email mode that does not send real mail
- Legacy Streamlit interface retained as an optional fallback

## Project structure

- `api.py` — FastAPI routes and authentication
- `database.py` — PostgreSQL/SQLite schema and database operations
- `expense_agent.py` — LangGraph expense-report workflow
- `analysis_agent.py` — expense analysis
- `tools.py` — PDF and Gmail delivery tools
- `frontend/` — React, TypeScript, and Vite UI
- `app.py` — legacy Streamlit UI
- `start-app.bat` — starts the backend and frontend
- `start-backend.bat` — starts only the backend

## Requirements

- Windows
- Python 3.10 or newer
- Node.js 20 or newer
- Neon PostgreSQL project

## Environment setup

Copy `.env.example` to `.env`:

```bat
copy .env.example .env
```

Configure:

```text
GROQ_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=your_groq_api_key
SENDER_EMAIL=your_gmail_address@gmail.com
EMAIL_APP_PASSWORD=your_16_character_gmail_app_password
DATABASE_URL=postgresql://username:password@host/database?sslmode=require
DEMO_EMPLOYEE_PASSWORD=employee123
EMPLOYER_EMAIL=finance@gmail.com
EMPLOYER_PASSWORD=your_employer_password
```

Never commit `.env`. It is ignored by Git.

### Gmail setup

Real email delivery requires:

1. 2-Step Verification enabled on the sender Gmail account
2. A Gmail App Password created for Mail
3. The sender address in `SENDER_EMAIL`
4. The 16-character App Password in `EMAIL_APP_PASSWORD`
5. A recipient entered as `name@gmail.com` in the send popup

Do not use the normal Gmail sign-in password.

## Start locally

### Recommended

From the project root:

```bat
start-app.bat
```

This starts:

- FastAPI: `http://127.0.0.1:8000`
- React: `http://localhost:5173`
- API documentation: `http://127.0.0.1:8000/docs`

### Backend only

```bat
start-backend.bat
```

### Start with npm

```bat
npm start
npm run backend
```

## Manual startup

Install dependencies:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
cd frontend
npm install
cd ..
```

Start the backend:

```bat
python -m uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in a second terminal:

```bat
cd frontend
npm run dev
```

## Demo accounts

Every seeded employee uses the `DEMO_EMPLOYEE_PASSWORD` value:

- Employee name: for example `Aditi Sharma`
- Password: `employee123`

The employer account uses `EMPLOYER_EMAIL` and `EMPLOYER_PASSWORD` from `.env`.

Employer accounts have organization-wide report access. Employee accounts are
restricted to their own records and reports.

## Database

`database.py` uses `DATABASE_URL` when Neon PostgreSQL is configured. If no
PostgreSQL URL is available, it falls back to local SQLite at
`data/expenses.db`.

Neon is recommended for deployed or shared use because local SQLite files may
not persist across managed hosting restarts.

PDF files are stored in `data/generated_reports/`.

## Core workflow

1. Sign in as an employee or employer.
2. Select an employee and reporting month.
3. Review and correct incomplete expense records.
4. Generate a versioned PDF report.
5. Download or permanently delete a report.
6. To send mail, enter a recipient Gmail address and confirm.

## Streamlit Community Cloud

Deploy `app.py` as the main Streamlit file.

In Streamlit Cloud, open **App settings → Secrets** and add:

```toml
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_API_KEY = "your_groq_api_key"
SENDER_EMAIL = "your_gmail_address@gmail.com"
EMAIL_APP_PASSWORD = "your_16_character_gmail_app_password"
DATABASE_URL = "postgresql://username:password@host/database?sslmode=require"
DEMO_EMPLOYEE_PASSWORD = "employee123"
EMPLOYER_EMAIL = "your_employer_email@gmail.com"
EMPLOYER_PASSWORD = "your_employer_password"
```

Streamlit secrets are separate from `.env` and must never be committed to Git.
Use the Neon pooled `DATABASE_URL` for web queries. PDFs and SQLite data are
temporary on Streamlit Cloud unless moved to persistent object storage.

## Troubleshooting

- If the UI cannot reach the API, confirm port `8000` is running.
- If port `8000` or `5173` is occupied, stop the existing process or change
  the port.
- If Gmail reports authentication failure, verify 2-Step Verification and use
  a 16-character Gmail App Password.
- If Neon connection fails, verify `DATABASE_URL` and `sslmode=require`.
- Live Groq features require `GROQ_API_KEY`; demo mode does not.
