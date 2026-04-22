from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import uuid

app = Flask(__name__)

# ================= DATABASE =================
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ================= MODELS =================

class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_key = db.Column(db.String(64), unique=True)
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

# ================= INIT =================
with app.app_context():
    db.create_all()

# ================= HELPERS =================
def generate_key():
    return str(uuid.uuid4()).replace("-", "").upper()[:16]

# ================= API =================

@app.route("/api/create-license", methods=["POST"])
def create_license():
    data = request.json

    key = generate_key()
    days = int(data.get("days", 30))

    lic = License(
        license_key=key,
        customer_name=data.get("customer_name"),
        expire_date=datetime.utcnow().date() + timedelta(days=days),
        max_devices=int(data.get("max_devices", 1)),
        used_devices=0
    )

    db.session.add(lic)
    db.session.commit()

    return jsonify({
        "status": "success",
        "license_key": key,
        "expire_date": str(lic.expire_date),
        "max_devices": lic.max_devices,
        "used_devices": 0
    })


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

    device = Device.query.filter_by(device_id=device_id, license_key=key).first()

    if not device:
        if lic.used_devices >= lic.max_devices:
            return jsonify({"status": "error", "message": "device limit reached"})

        db.session.add(Device(device_id=device_id, license_key=key))
        lic.used_devices += 1
        db.session.commit()

    return jsonify({
        "status": "success",
        "expire_date": str(lic.expire_date),
        "used_devices": lic.used_devices,
        "max_devices": lic.max_devices
    })


@app.route("/api/check-trial", methods=["POST"])
def check_trial():
    data = request.json
    device_id = data.get("device_id")

    trial = Trial.query.filter_by(device_id=device_id).first()

    if not trial:
        trial = Trial(
            device_id=device_id,
            start_date=datetime.utcnow().date(),
            expire_date=datetime.utcnow().date() + timedelta(days=7)
        )
        db.session.add(trial)
        db.session.commit()

    if datetime.utcnow().date() > trial.expire_date:
        return jsonify({"status": "expired"})

    return jsonify({
        "status": "active",
        "expire_date": str(trial.expire_date)
    })


# ================= ADMIN HTML =================

TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl">
<head>
<meta charset="utf-8">
<title>لوحة التراخيص</title>
<style>
body {font-family: Arial; background:#f5f5f5; padding:20px;}
.card {background:#fff; padding:15px; border-radius:10px; margin-bottom:20px;}
table {width:100%; border-collapse: collapse;}
th, td {padding:10px; border-bottom:1px solid #ddd;}
th {background:#eee;}
</style>
</head>
<body>

<h1>لوحة التراخيص</h1>

<div class="card">
<h2>إنشاء ترخيص</h2>
<form method="post">
<input name="name" placeholder="اسم العميل"><br><br>
<input name="days" placeholder="عدد الأيام" value="30"><br><br>
<input name="devices" placeholder="عدد الأجهزة" value="1"><br><br>
<button type="submit">إنشاء</button>
</form>
</div>

<div class="card">
<h2>التراخيص</h2>
<table>
<tr><th>الكود</th><th>العميل</th><th>الانتهاء</th><th>الأجهزة</th></tr>
{% for l in licenses %}
<tr>
<td>{{l.license_key}}</td>
<td>{{l.customer_name}}</td>
<td>{{l.expire_date}}</td>
<td>{{l.used_devices}} / {{l.max_devices}}</td>
</tr>
{% endfor %}
</table>
</div>

<div class="card">
<h2>التجارب</h2>
<table>
<tr><th>الجهاز</th><th>الانتهاء</th></tr>
{% for t in trials %}
<tr>
<td>{{t.device_id}}</td>
<td>{{t.expire_date}}</td>
</tr>
{% endfor %}
</table>
</div>

</body>
</html>
"""

@app.route("/admin/licenses", methods=["GET", "POST"])
def admin_ui():
    if request.method == "POST":
        name = request.form.get("name")
        days = int(request.form.get("days", 30))
        devices = int(request.form.get("devices", 1))

        lic = License(
            license_key=generate_key(),
            customer_name=name,
            expire_date=datetime.utcnow().date() + timedelta(days=days),
            max_devices=devices,
            used_devices=0
        )
        db.session.add(lic)
        db.session.commit()

        return redirect(url_for("admin_ui"))

    licenses = License.query.all()
    trials = Trial.query.all()

    return render_template_string(TEMPLATE, licenses=licenses, trials=trials)


# ================= ROOT =================
@app.route("/")
def home():
    return "Server Running"

# ================= RUN =================
if __name__ == "__main__":
    app.run()
