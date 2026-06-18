# health-pridiction-crud-app
A health prediction CRUD application built with Flask, SQLite, and a custom AI/ML risk-prediction microservice. Patient blood test data is validated, stored, and assessed for health risk via REST API integration.

## What it does

- Add, view, edit, and delete patient records.
- Store patient data in `mira.db` using SQLite.
- Send blood test values to `ai_service/predictor.py` to generate a health risk
  remark and risk level.
- Search patient records by name.

## Requirements

- Python 3.10 or newer
- `Flask`, `Flask-SQLAlchemy`, and `requests`

Install with:

```bash
pip install -r requirements.txt
```

## Run the app

Start the AI service first:

```bash
python ai_service/predictor.py
```

Then start the main application:

```bash
python app.py
```

Visit `http://127.0.0.1:5000` in your browser.

## Project structure

- `app.py` — main Flask application and SQLite data model
- `ai_service/predictor.py` — separate AI health service for risk assessment
- `templates/` — Jinja2 HTML templates for listing, forms, and details
- `requirements.txt` — Python dependencies
- `README.md` — project documentation

## Notes

- The SQLite database file is created automatically when the app first runs.
- If the AI service is unavailable, the app still allows CRUD operations and
  stores a fallback remark.
- This is a demo application and not intended for real medical use.
