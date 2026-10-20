# Backend

The backend is a Python FastAPI application. It currently provides only a health
endpoint; application features and integrations are planned for later phases.

## Local setup

From the repository root, create and activate a virtual environment:

```powershell
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

If PowerShell does not permit activation, use the environment's interpreter
directly:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Start the API from the `backend` directory:

```powershell
cd backend
python -m uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive API documentation
is at `/docs`. `GET /health` returns `{"status":"ok"}`.
