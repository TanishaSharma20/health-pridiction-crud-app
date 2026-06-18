"""
MIRA - Medical Intelligence Robotic Automation
================================================
Main Flask application implementing CRUD for patient health records.
On create/update, it calls the MIRA AI Health Service (a separate Flask
microservice, see ai_service/predictor.py) over HTTP to generate the
"Remarks" field from the submitted blood test values.

Run:
    python app.py
Then visit http://127.0.0.1:5000
(Make sure ai_service/predictor.py is running on port 5001 first.)
"""

import os
import re
from datetime import datetime, date

import requests
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "mira.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "dev-secret-key-change-in-production"

db = SQLAlchemy(app)

AI_SERVICE_URL = os.environ.get("MIRA_AI_SERVICE_URL", "http://127.0.0.1:5001/api/predict")

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    email = db.Column(db.String(120), nullable=False)
    glucose = db.Column(db.Float, nullable=False)
    haemoglobin = db.Column(db.Float, nullable=False)
    cholesterol = db.Column(db.Float, nullable=False)
    remarks = db.Column(db.Text, nullable=True)
    risk_level = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_patient_form(form):
    """Validate submitted form data. Returns (errors: dict, cleaned: dict)."""
    errors = {}
    cleaned = {}

    full_name = (form.get("full_name") or "").strip()
    if not full_name:
        errors["full_name"] = "Full name is required."
    elif len(full_name) < 2:
        errors["full_name"] = "Full name must be at least 2 characters."
    cleaned["full_name"] = full_name

    dob_raw = (form.get("date_of_birth") or "").strip()
    if not dob_raw:
        errors["date_of_birth"] = "Date of birth is required."
    else:
        try:
            dob = datetime.strptime(dob_raw, "%Y-%m-%d").date()
            if dob > date.today():
                errors["date_of_birth"] = "Date of birth cannot be in the future."
            cleaned["date_of_birth"] = dob
        except ValueError:
            errors["date_of_birth"] = "Date of birth must be a valid date (YYYY-MM-DD)."

    email = (form.get("email") or "").strip()
    if not email:
        errors["email"] = "Email address is required."
    elif not EMAIL_REGEX.match(email):
        errors["email"] = "Enter a valid email address."
    cleaned["email"] = email

    for field, label in (
        ("glucose", "Glucose"),
        ("haemoglobin", "Haemoglobin"),
        ("cholesterol", "Cholesterol"),
    ):
        raw = (form.get(field) or "").strip()
        if not raw:
            errors[field] = f"{label} is required."
            continue
        try:
            value = float(raw)
            if value <= 0:
                errors[field] = f"{label} must be a positive number."
            elif value > 2000:
                errors[field] = f"{label} value looks out of range. Please check."
            else:
                cleaned[field] = value
        except ValueError:
            errors[field] = f"{label} must be numeric."

    return errors, cleaned


def get_ai_remarks(glucose, haemoglobin, cholesterol, date_of_birth):
    """Call the external MIRA AI Health Service to get a risk assessment.

    Returns (remarks_text, risk_level). Falls back gracefully if the
    service is unreachable so the CRUD flow never breaks because of it.
    """
    payload = {
        "glucose": glucose,
        "haemoglobin": haemoglobin,
        "cholesterol": cholesterol,
        "date_of_birth": date_of_birth.isoformat() if date_of_birth else None,
    }
    try:
        resp = requests.post(AI_SERVICE_URL, json=payload, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("remarks", "No remarks generated."), data.get("risk_level")
        return f"AI service returned an error (status {resp.status_code}).", None
    except requests.exceptions.RequestException:
        return "AI service unavailable. Remarks could not be generated.", None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    query = (request.args.get("q") or "").strip()
    patients_query = Patient.query
    if query:
        patients_query = patients_query.filter(Patient.full_name.ilike(f"%{query}%"))
    patients = patients_query.order_by(Patient.created_at.desc()).all()
    return render_template("index.html", patients=patients, query=query)


@app.route("/patients/new", methods=["GET", "POST"])
def create_patient():
    if request.method == "POST":
        errors, cleaned = validate_patient_form(request.form)
        if errors:
            return render_template("form.html", errors=errors, patient=request.form, mode="create")

        remarks, risk_level = get_ai_remarks(
            cleaned["glucose"], cleaned["haemoglobin"], cleaned["cholesterol"], cleaned["date_of_birth"]
        )

        patient = Patient(
            full_name=cleaned["full_name"],
            date_of_birth=cleaned["date_of_birth"],
            email=cleaned["email"],
            glucose=cleaned["glucose"],
            haemoglobin=cleaned["haemoglobin"],
            cholesterol=cleaned["cholesterol"],
            remarks=remarks,
            risk_level=risk_level,
        )
        db.session.add(patient)
        db.session.commit()
        flash(f"Record for {patient.full_name} created and AI remarks generated.", "success")
        return redirect(url_for("index"))

    return render_template("form.html", errors={}, patient={}, mode="create")


@app.route("/patients/<int:patient_id>")
def view_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    return render_template("view.html", patient=patient)


@app.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
def edit_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)

    if request.method == "POST":
        errors, cleaned = validate_patient_form(request.form)
        if errors:
            return render_template("form.html", errors=errors, patient=request.form, mode="edit", patient_id=patient_id)

        remarks, risk_level = get_ai_remarks(
            cleaned["glucose"], cleaned["haemoglobin"], cleaned["cholesterol"], cleaned["date_of_birth"]
        )

        patient.full_name = cleaned["full_name"]
        patient.date_of_birth = cleaned["date_of_birth"]
        patient.email = cleaned["email"]
        patient.glucose = cleaned["glucose"]
        patient.haemoglobin = cleaned["haemoglobin"]
        patient.cholesterol = cleaned["cholesterol"]
        patient.remarks = remarks
        patient.risk_level = risk_level
        db.session.commit()
        flash(f"Record for {patient.full_name} updated and remarks regenerated.", "success")
        return redirect(url_for("view_patient", patient_id=patient.id))

    form_data = {
        "full_name": patient.full_name,
        "date_of_birth": patient.date_of_birth.isoformat(),
        "email": patient.email,
        "glucose": patient.glucose,
        "haemoglobin": patient.haemoglobin,
        "cholesterol": patient.cholesterol,
    }
    return render_template("form.html", errors={}, patient=form_data, mode="edit", patient_id=patient_id)


@app.route("/patients/<int:patient_id>/delete", methods=["POST"])
def delete_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    name = patient.full_name
    db.session.delete(patient)
    db.session.commit()
    flash(f"Record for {name} deleted.", "info")
    return redirect(url_for("index"))


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
