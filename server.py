from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import uuid

app = Flask(__name__)

# ================== DATABASE ==================
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ================== MODELS ==================

class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_key = db.Column(db.String(64), unique=True, nullable=False)
    customer_name = db.Column(db.String(100))
    expire_date = db.Column(db.Date)
    max_devices = db.Column(db.Integer, default=1)
    used_devices = db.Column(db.Integer, default=0)

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(100))
    license_key = db.Column(db.String(64))

class Trial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(100), unique=True)
    start_date = db.Column(db.Date)
    expire_date = db.Column(db.Date)

# ================== INIT ==================

with app.app_context():
    db.create_all()

# ================== HELPERS ==================

def generate_license_key():
    return str(uuid.uuid4()).replace("-", "").upper()[:20]

# ================== API ==================

# ✅ إنشاء ترخيص
@app.route("/api/create-license", methods=["POST"])
def create_license():
    data = request.json

    key = generate_license_key()
    days = int(data.get("days", 30))

    new_license = License(
        license_key=key,
        customer_name=data.get("customer_name"),
        expire_date=datetime.utcnow().date() + timedelta(days=days),
        max_devices=int(data.get("max_devices", 1)),
        used_devices=0
    )

    db.session.add(new_license)
    db.session.commit()

    return jsonify({
        "status": "success",
        "license_key": key,
        "expire_date": str(new_license.expire_date),
        "max_devices": new_license.max_devices,
        "used_devices": 0
    })


# ✅ تحقق من الترخيص
@app.route("/api/validate-license", methods=["POST"])
def validate_license():
    data = request.json
    key = data.get("license_key")
    device_id = data.get("device_id")

    lic = License.query.filter_by(license_key=key).first()

    if not lic:
        return jsonify({"status": "error", "message": "license not found"})

    if datetime.utcnow().date() > lic.expire_date:
        return jsonify({"status": "error", "message": "expired"})

    device = Device.query.filter_by(
        device_id=device_id,
        license_key=key
    ).first()

    if not device:
        if lic.used_devices >= lic.max_devices:
            return jsonify({"status": "error", "message": "device limit reached"})

        new_device = Device(device_id=device_id, license_key=key)
        db.session.add(new_device)
        lic.used_devices += 1
        db.session.commit()

    return jsonify({
        "status": "success",
        "expire_date": str(lic.expire_date),
        "used_devices": lic.used_devices,
        "max_devices": lic.max_devices
    })


# ✅ التحقق من النسخة التجريبية
@app.route("/api/check-trial", methods=["POST"])
def check_trial():
    data = request.json
    device_id = data.get("device_id")

    trial = Trial.query.filter_by(device_id=device_id).first()

    # إذا لا يوجد → أنشئ تجربة
    if not trial:
        trial = Trial(
            device_id=device_id,
            start_date=datetime.utcnow().date(),
            expire_date=datetime.utcnow().date() + timedelta(days=7)
        )
        db.session.add(trial)
        db.session.commit()

    # تحقق من الانتهاء
    if datetime.utcnow().date() > trial.expire_date:
        return jsonify({"status": "expired"})

    return jsonify({
        "status": "active",
        "expire_date": str(trial.expire_date)
    })


# ================== ADMIN ==================

@app.route("/admin")
def admin():
    licenses = License.query.all()
    trials = Trial.query.all()

    return {
        "licenses": [
            {
                "key": l.license_key,
                "expire": str(l.expire_date),
                "devices": f"{l.used_devices}/{l.max_devices}"
            } for l in licenses
        ],
        "trials": [
            {
                "device": t.device_id,
                "expire": str(t.expire_date)
            } for t in trials
        ]
    }

# ================== RUN ==================

if __name__ == "__main__":
    app.run()
