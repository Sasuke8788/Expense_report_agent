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

Do not use the normal Gmail sign-in password. Gmail App Password values may
include spaces in `.env` or Render; the application removes them before login.

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
The employee list is generated from the Government of Canada travel-expense
dataset. Every dataset employee uses the `DEMO_EMPLOYEE_PASSWORD` value:

- Employee name: for example `Aaron McCrorie`
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

Expense records are synchronized from the Government of Canada's open
`datastore_search` resource
`8282db2a-878f-475c-af10-ad56aa8fa72c`. The sync runs once when the database
is empty or still contains the former synthetic employee records. Set
`FORCE_CANADA_DATASET_SYNC=1` to force a resync, or
`CANADA_DATASET_ENABLED=0` to disable live synchronization.

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

## Vercel deployment

The deployed React frontend is:

```text
https://expense-report-agent-sigma.vercel.app
```

The FastAPI backend must be deployed separately on Render or Railway. Vercel
hosts `frontend/` only.

### Deploy FastAPI on Render

Create a Render **Web Service** from this repository and use:

- Branch: `main`
- Root Directory: leave blank
- Runtime: `Python 3`
- Build Command: `pip install -r requirements.txt`
- Start Command: `python -m uvicorn api:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/api/health`

Add the following variables in Render:

```text
DATABASE_URL=your_neon_connection_string
SENDER_EMAIL=your_gmail_address@gmail.com
EMAIL_APP_PASSWORD=your_16_character_gmail_app_password
GROQ_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=your_groq_api_key
DEMO_EMPLOYEE_PASSWORD=employee123
EMPLOYER_EMAIL=your_employer_email
EMPLOYER_PASSWORD=your_employer_password
FRONTEND_URL=https://expense-report-agent-sigma.vercel.app
```

After the Render service deploys, copy its public HTTPS URL, for example:

```text
https://your-service-name.onrender.com
```

Verify it at:

```text
https://your-service-name.onrender.com/api/health
```

In Vercel:

1. Import the GitHub repository.
2. Set **Root Directory** to `frontend`.
3. Set **Framework Preset** to Vite.
4. Set **Build Command** to `npm run build`.
5. Set **Output Directory** to `dist`.
6. Add this environment variable:

```text
VITE_API_URL=https://your-service-name.onrender.com
```

Do not append `/api`; the frontend adds `/api` automatically.

After deploying the backend, add its HTTPS URL as `VITE_API_URL` in Vercel,
redeploy the frontend, and test login before share-time.

## Troubleshooting

- For the deployed app, open `https://expense-report-agent-sigma.vercel.app`.
- If login or data fails, check `/api/health` on the Render backend.
- If browser requests are blocked, verify Render `FRONTEND_URL` exactly matches
  `https://expense-report-agent-sigma.vercel.app` with no trailing slash.
- If Vercel shows the localhost API or cannot connect, update
  `VITE_API_URL` and redeploy Vercel.
- If the UI cannot reach the API, confirm port `8000` is running.
- If port `8000` or `5173` is occupied, stop the existing process or change
  the port.
- If Gmail reports authentication failure, verify 2-Step Verification and use
  a 16-character Gmail App Password.
- Render free web services block outbound SMTP ports 25, 465, and 587. If the
  deployed service shows "Network is unreachable", upgrade the Render instance
  or configure `RESEND_API_KEY` for HTTPS email delivery. `SENDER_EMAIL` must
  contain a sender address verified by the hosted email provider.
- If Neon connection fails, verify `DATABASE_URL` and `sslmode=require`.
- Live Groq features require `GROQ_API_KEY`; demo mode does not.
