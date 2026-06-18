"""
MIRA AI/ML Health Risk Service
================================
A standalone Flask microservice that plays the role of the "external AI/ML
Health API" required by the task brief. The main MIRA application calls this
service over HTTP (REST, JSON in/out) every time a patient record is
created or updated, exactly like it would call a third-party health API.

Why a real microservice instead of a hard-coded "if glucose > X" inline in
the main app?
  - It keeps the AI/ML logic decoupled from the CRUD app, so it can be
    swapped for a hosted model (e.g. a scikit-learn model behind an
    endpoint, or a commercial Health API) without touching app.py.
  - It demonstrates genuine API integration: a real HTTP call, a JSON
    contract, status codes, and error handling on the client side.
  - It is small enough to explain confidently end-to-end in the demo video.

Model approach
--------------
The engine combines transparent clinical reference-range rules (the kind
used in real triage/decision-support tools) with a simple weighted risk
score, so the output is deterministic, explainable, and not a black box.
This is intentional: a junior-level health prediction task benefits far
more from a model whose reasoning you can defend on camera than from an
opaque library you cannot explain.

Endpoints
---------
GET  /health                -> liveness check
POST /api/predict           -> body: {glucose, haemoglobin, cholesterol,
                                       date_of_birth (optional)}
                                returns: {remarks, risk_level, findings}
"""

from datetime import datetime, date
from flask import Flask, request, jsonify

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Clinical reference ranges (adult, general population, mg/dL and g/dL).
# These mirror commonly published lab reference ranges. They are simplified
# for an assignment-scale demo and are NOT a substitute for medical advice.
# ---------------------------------------------------------------------------
RANGES = {
    "glucose": {  # fasting, mg/dL
        "low": (0, 70),
        "normal": (70, 99),
        "prediabetic": (99, 126),
        "high": (126, float("inf")),
    },
    "cholesterol": {  # total cholesterol, mg/dL
        "normal": (0, 200),
        "borderline": (200, 240),
        "high": (240, float("inf")),
    },
    "haemoglobin": {  # g/dL, unisex simplified band
        "low": (0, 12.0),
        "normal": (12.0, 16.5),
        "high": (16.5, float("inf")),
    },
}


def _band(value, ranges):
    for label, (lo, hi) in ranges.items():
        if lo <= value < hi:
            return label
    return "unknown"


def _age_from_dob(dob_str):
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except (ValueError, TypeError):
        return None


def assess(glucose, haemoglobin, cholesterol, date_of_birth=None):
    """Core prediction logic: returns a structured risk assessment."""
    findings = []
    score = 0

    glucose_band = _band(glucose, RANGES["glucose"])
    if glucose_band == "high":
        findings.append("Elevated fasting glucose suggestive of diabetes risk")
        score += 3
    elif glucose_band == "prediabetic":
        findings.append("Borderline glucose level, consistent with prediabetic range")
        score += 2
    elif glucose_band == "low":
        findings.append("Glucose level below normal range (hypoglycemic range)")
        score += 2

    chol_band = _band(cholesterol, RANGES["cholesterol"])
    if chol_band == "high":
        findings.append("High total cholesterol, increased cardiovascular risk")
        score += 3
    elif chol_band == "borderline":
        findings.append("Borderline-high cholesterol")
        score += 1

    hb_band = _band(haemoglobin, RANGES["haemoglobin"])
    if hb_band == "low":
        findings.append("Low haemoglobin, possible anaemia indicator")
        score += 2
    elif hb_band == "high":
        findings.append("Elevated haemoglobin, advise clinical follow-up")
        score += 1

    age = _age_from_dob(date_of_birth) if date_of_birth else None
    if age is not None and age >= 50:
        score += 1  # age-related risk weighting

    if score >= 5:
        risk_level = "High"
    elif score >= 2:
        risk_level = "Moderate"
    else:
        risk_level = "Low"

    if not findings:
        remarks = "All values within normal range. No significant risk indicators detected."
    else:
        remarks = f"{risk_level} risk — " + "; ".join(findings) + "."

    return {
        "remarks": remarks,
        "risk_level": risk_level,
        "findings": findings,
        "bands": {
            "glucose": glucose_band,
            "cholesterol": chol_band,
            "haemoglobin": hb_band,
        },
    }


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "mira-ai-health-service"})


@app.post("/api/predict")
def predict():
    data = request.get_json(silent=True) or {}

    required = ["glucose", "haemoglobin", "cholesterol"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        glucose = float(data["glucose"])
        haemoglobin = float(data["haemoglobin"])
        cholesterol = float(data["cholesterol"])
    except (TypeError, ValueError):
        return jsonify({"error": "glucose, haemoglobin and cholesterol must be numeric"}), 400

    result = assess(
        glucose=glucose,
        haemoglobin=haemoglobin,
        cholesterol=cholesterol,
        date_of_birth=data.get("date_of_birth"),
    )
    return jsonify(result), 200


if __name__ == "__main__":
    # Runs on a separate port from the main MIRA app so the two communicate
    # over real HTTP, like a client app talking to an external Health API.
    app.run(host="0.0.0.0", port=5001, debug=False)
