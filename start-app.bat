@echo off
cd /d "%~dp0"
start "ExpenseFlow Backend" cmd /k call "%~dp0start-backend.bat"
start "ExpenseFlow Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"
