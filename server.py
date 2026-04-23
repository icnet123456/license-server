from flask import Flask, request, jsonify, render_template_string, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from functools import wraps
import os
import json
import uuid

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "7"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "12345678")


class License(db.Model):
    __tablename__ = "licenses"

    id = db.Column(db.Integer, primary_key=True)
    license_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    customer_name = db.Column(db.String(120), nullable=True)
    expire_date = db.Column(db.Date, nullable=False)
    max_devices = db.Column(db.Integer, nullable=False, default=1)
    used_devices = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(32), nullable=False, default="active")
    device_ids = db.Column(db.Text, nullable=False, default="[]")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def device_list(self):
        try:
            data = json.loads(self.device_ids or "[]")
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            pass
        return []

    def set_device_list(self, items):
        clean = []
        seen = set()
        for item in items:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            clean.append(text)
        self.device_ids = json.dumps(clean, ensure_ascii=False)
        self.used_devices = len(clean)


class Trial(db.Model):
    __tablename__ = "trials"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    start_date = db.Column(db.Date, nullable=False)
    expire_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(32), nullable=False, default="trial")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


def today_utc():
    return datetime.utcnow().date()


def generate_key():
    return str(uuid.uuid4()).replace("-", "").upper()[:16]


def check_auth(username, password):
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD


def authenticate():
    return Response(
        "يجب تسجيل الدخول أولاً",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'},
    )


def require_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return func(*args, **kwargs)
    return wrapper


def serialize_license(lic: License):
    return {
        "license_key": lic.license_key,
        "customer_name": lic.customer_name or "",
        "expire_date": str(lic.expire_date),
        "max_devices": lic.max_devices,
        "used_devices": lic.used_devices,
        "status": lic.status,
        "device_ids": lic.device_list(),
        "created_at": lic.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def serialize_trial(trial: Trial):
    return {
        "device_id": trial.device_id,
        "start_date": str(trial.start_date),
        "expire_date": str(trial.expire_date),
        "status": trial.status,
        "created_at": trial.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


with app.app_context():
    db.create_all()


@app.route("/")
def home():
    return "License Server Running"


@app.route("/debug-db")
@require_auth
def debug_db():
    return jsonify({
        "database_url_exists": bool(DATABASE_URL),
        "trial_days": TRIAL_DAYS,
        "admin_username": ADMIN_USERNAME,
        "driver": "psycopg3",
    })


@app.route("/api/create-license", methods=["POST"])
@require_auth
def api_create_license():
    data = request.get_json(silent=True) or {}

    customer_name = str(data.get("customer_name", "Unknown")).strip() or "Unknown"

    try:
        days = int(data.get("days", 30))
        max_devices = int(data.get("max_devices", 1))
    except Exception:
        return jsonify({"status": "error", "message": "days / max_devices must be integers"}), 400

    if days <= 0:
        return jsonify({"status": "error", "message": "days must be greater than zero"}), 400
    if max_devices <= 0:
        return jsonify({"status": "error", "message": "max_devices must be greater than zero"}), 400

    device_id = str(data.get("device_id", "")).strip()
    raw_device_ids = data.get("device_ids", [])
    initial_devices = []

    if device_id:
        initial_devices.append(device_id)

    if isinstance(raw_device_ids, list):
        initial_devices.extend(raw_device_ids)

    clean_devices = []
    seen = set()
    for item in initial_devices:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        clean_devices.append(text)

    if len(clean_devices) > max_devices:
        return jsonify({"status": "error", "message": "initial devices exceed max_devices"}), 400

    lic = License(
        license_key=generate_key(),
        customer_name=customer_name,
        expire_date=today_utc() + timedelta(days=days),
        max_devices=max_devices,
        status="active",
    )
    lic.set_device_list(clean_devices)

    db.session.add(lic)
    db.session.commit()

    return jsonify({
        "status": "success",
        "license_key": lic.license_key,
        "customer_name": lic.customer_name,
        "expire_date": str(lic.expire_date),
        "max_devices": lic.max_devices,
        "used_devices": lic.used_devices,
        "device_ids": lic.device_list(),
        "created_at": lic.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/check-license", methods=["POST"])
def api_check_license():
    data = request.get_json(silent=True) or {}

    license_key = str(data.get("license_key", "")).strip()
    device_id = str(data.get("device_id", "")).strip()

    if not license_key:
        return jsonify({"status": "error", "message": "license_key required"}), 400
    if not device_id:
        return jsonify({"status": "error", "message": "device_id required"}), 400

    lic = License.query.filter_by(license_key=license_key).first()
    if not lic:
        return jsonify({"status": "invalid", "message": "License not found"}), 404

    if lic.status != "active":
        return jsonify({"status": "blocked", "message": "License inactive"}), 403

    if today_utc() > lic.expire_date:
        return jsonify({
            "status": "expired",
            "message": "License expired",
            "expire_date": str(lic.expire_date),
        }), 403

    devices = lic.device_list()

    if device_id in devices:
        return jsonify({
            "status": "active",
            "message": "Valid",
            "customer_name": lic.customer_name,
            "expire_date": str(lic.expire_date),
            "max_devices": lic.max_devices,
            "used_devices": len(devices),
        })

    if len(devices) >= lic.max_devices:
        return jsonify({
            "status": "denied",
            "message": "Device limit reached",
            "customer_name": lic.customer_name,
            "expire_date": str(lic.expire_date),
            "max_devices": lic.max_devices,
            "used_devices": len(devices),
        }), 403

    devices.append(device_id)
    lic.set_device_list(devices)
    db.session.commit()

    return jsonify({
        "status": "active",
        "message": "Activated",
        "customer_name": lic.customer_name,
        "expire_date": str(lic.expire_date),
        "max_devices": lic.max_devices,
        "used_devices": lic.used_devices,
    })


@app.route("/api/check-device", methods=["POST"])
def api_check_device():
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "")).strip()

    if not device_id:
        return jsonify({"status": "error", "message": "device_id required"}), 400

    active_licenses = License.query.filter(
        License.status == "active",
        License.expire_date >= today_utc(),
    ).all()

    for lic in active_licenses:
        if device_id in lic.device_list():
            return jsonify({
                "status": "active",
                "message": "Device is activated",
                "customer_name": lic.customer_name,
                "license_key": lic.license_key,
                "expire_date": str(lic.expire_date),
                "max_devices": lic.max_devices,
                "used_devices": lic.used_devices,
            })

    return jsonify({
        "status": "inactive",
        "message": "Device is not activated",
    }), 404


@app.route("/api/start-trial", methods=["POST"])
def api_start_trial():
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "")).strip()

    if not device_id:
        return jsonify({"status": "error", "message": "device_id required"}), 400

    trial = Trial.query.filter_by(device_id=device_id).first()

    if not trial:
        trial = Trial(
            device_id=device_id,
            start_date=today_utc(),
            expire_date=today_utc() + timedelta(days=TRIAL_DAYS),
            status="trial",
        )
        db.session.add(trial)
        db.session.commit()

    if today_utc() > trial.expire_date:
        trial.status = "expired"
        db.session.commit()
        return jsonify({
            "status": "expired",
            "message": "Trial expired",
            "expire_date": str(trial.expire_date),
            "days_left": 0,
        }), 403

    days_left = max(0, (trial.expire_date - today_utc()).days)
    return jsonify({
        "status": "trial",
        "message": "Trial active",
        "expire_date": str(trial.expire_date),
        "days_left": days_left,
        "trial_days": TRIAL_DAYS,
        "created_at": trial.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/check-trial", methods=["POST"])
def api_check_trial():
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "")).strip()

    if not device_id:
        return jsonify({"status": "error", "message": "device_id required"}), 400

    trial = Trial.query.filter_by(device_id=device_id).first()
    if not trial:
        return jsonify({
            "status": "inactive",
            "message": "Trial not found",
        }), 404

    if today_utc() > trial.expire_date:
        trial.status = "expired"
        db.session.commit()
        return jsonify({
            "status": "expired",
            "message": "Trial expired",
            "expire_date": str(trial.expire_date),
            "days_left": 0,
        }), 403

    days_left = max(0, (trial.expire_date - today_utc()).days)
    return jsonify({
        "status": "trial",
        "message": "Trial active",
        "expire_date": str(trial.expire_date),
        "days_left": days_left,
        "trial_days": TRIAL_DAYS,
        "created_at": trial.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    })


ADMIN_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>لوحة إدارة التراخيص</title>
    <style>
        body { font-family: Tahoma, Arial, sans-serif; background:#f6f3eb; margin:0; padding:20px; color:#222; }
        .wrap { max-width:1200px; margin:auto; }
        .card { background:#fff; border:1px solid #ddd; border-radius:14px; padding:18px; margin-bottom:18px; box-shadow:0 4px 14px rgba(0,0,0,.05); }
        h1,h2 { margin-top:0; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; }
        input, button { width:100%; padding:10px 12px; border-radius:10px; border:1px solid #ccc; font-family:inherit; font-size:14px; }
        button { background:#0f766e; color:#fff; border:none; cursor:pointer; font-weight:bold; }
        .danger { background:#b91c1c; }
        .warn { background:#b45309; }
        .muted { color:#666; }
        .flash { background:#ecfdf5; border:1px solid #bbf7d0; color:#166534; padding:10px 12px; border-radius:10px; margin-bottom:12px; }
        table { width:100%; border-collapse:collapse; }
        th, td { padding:10px; border-bottom:1px solid #eee; text-align:right; vertical-align:top; }
        th { background:#f0ebe0; }
        .tag { display:inline-block; padding:4px 10px; border-radius:999px; background:#e8f7ee; color:#166534; font-size:12px; margin:2px 0; }
        .trial { background:#e8f0ff; color:#1d4ed8; }
        .blocked { background:#fff3cd; color:#8a6d3b; }
        .device-box { margin-bottom:8px; }
        form.inline { display:inline-block; margin:4px 0; }
    </style>
</head>
<body>
<div class="wrap">
    <h1>لوحة إدارة التراخيص</h1>

    {% if message %}
        <div class="flash">{{ message }}</div>
    {% endif %}

    <div class="card">
        <h2>إنشاء ترخيص جديد</h2>
        <form method="post" action="{{ url_for('admin_create_license') }}">
            <div class="grid">
                <div><input name="customer_name" placeholder="اسم العميل" required></div>
                <div><input name="days" type="number" min="1" value="30" placeholder="عدد الأيام" required></div>
                <div><input name="max_devices" type="number" min="1" value="1" placeholder="عدد الأجهزة" required></div>
                <div><button type="submit">إنشاء الترخيص</button></div>
            </div>
        </form>
    </div>

    <div class="card">
        <h2>التراخيص</h2>
        {% if licenses %}
        <table>
            <tr>
                <th>الكود</th>
                <th>العميل</th>
                <th>الانتهاء</th>
                <th>الحالة</th>
                <th>الأجهزة</th>
                <th>الاستخدام</th>
                <th>إدارة</th>
            </tr>
            {% for l in licenses %}
            <tr>
                <td><strong>{{ l.license_key }}</strong></td>
                <td>{{ l.customer_name or '-' }}</td>
                <td>{{ l.expire_date }}</td>
                <td>
                    {% if l.status == 'active' %}
                        <span class="tag">{{ l.status }}</span>
                    {% else %}
                        <span class="tag blocked">{{ l.status }}</span>
                    {% endif %}
                </td>
                <td>
                    {% if l.device_ids %}
                        {% for d in l.device_ids %}
                            <div class="device-box">
                                <span class="tag">{{ d }}</span>
                                <form method="post" action="{{ url_for('admin_remove_device') }}" class="inline">
                                    <input type="hidden" name="license_key" value="{{ l.license_key }}">
                                    <input type="hidden" name="device_id" value="{{ d }}">
                                    <button class="danger" type="submit">حذف الجهاز</button>
                                </form>
                            </div>
                        {% endfor %}
                    {% else %}
                        <span class="muted">لا توجد أجهزة</span>
                    {% endif %}
                </td>
                <td>{{ l.used_devices }} / {{ l.max_devices }}</td>
                <td>
                    <form method="post" action="{{ url_for('admin_reset_devices') }}" class="inline">
                        <input type="hidden" name="license_key" value="{{ l.license_key }}">
                        <button class="warn" type="submit">تصفير الأجهزة</button>
                    </form>

                    <form method="post" action="{{ url_for('admin_toggle_license') }}" class="inline">
                        <input type="hidden" name="license_key" value="{{ l.license_key }}">
                        <input type="hidden" name="new_status" value="{{ 'blocked' if l.status == 'active' else 'active' }}">
                        <button type="submit">{{ 'إيقاف' if l.status == 'active' else 'تفعيل' }}</button>
                    </form>

                    <form method="post" action="{{ url_for('admin_update_max_devices') }}" class="inline">
                        <input type="hidden" name="license_key" value="{{ l.license_key }}">
                        <input type="number" name="max_devices" min="1" value="{{ l.max_devices }}" style="width:90px;">
                        <button type="submit">تحديث الأجهزة</button>
                    </form>

                    <form method="post" action="{{ url_for('admin_delete_license') }}" class="inline" onsubmit="return confirm('هل تريد حذف الترخيص؟');">
                        <input type="hidden" name="license_key" value="{{ l.license_key }}">
                        <button class="danger" type="submit">حذف الترخيص</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
            <p class="muted">لا توجد تراخيص بعد.</p>
        {% endif %}
    </div>

    <div class="card">
        <h2>الأجهزة التجريبية</h2>
        {% if trials %}
        <table>
            <tr>
                <th>معرف الجهاز</th>
                <th>بداية التجربة</th>
                <th>نهاية التجربة</th>
                <th>الحالة</th>
                <th>الإنشاء</th>
            </tr>
            {% for t in trials %}
            <tr>
                <td>{{ t.device_id }}</td>
                <td>{{ t.start_date }}</td>
                <td>{{ t.expire_date }}</td>
                <td><span class="tag trial">{{ t.status }}</span></td>
                <td>{{ t.created_at }}</td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
            <p class="muted">لا توجد أجهزة Trial بعد.</p>
        {% endif %}
    </div>
</div>
</body>
</html>
"""


@app.route("/admin/licenses", methods=["GET"])
@require_auth
def admin_licenses():
    message = request.args.get("message", "")
    licenses = [serialize_license(x) for x in License.query.order_by(License.id.desc()).all()]
    trials = [serialize_trial(x) for x in Trial.query.order_by(Trial.id.desc()).all()]
    return render_template_string(ADMIN_TEMPLATE, licenses=licenses, trials=trials, message=message)


@app.route("/admin/create-license", methods=["POST"])
@require_auth
def admin_create_license():
    customer_name = str(request.form.get("customer_name", "Unknown")).strip() or "Unknown"

    try:
        days = int(request.form.get("days", 30))
        max_devices = int(request.form.get("max_devices", 1))
    except Exception:
        return redirect(url_for("admin_licenses", message="days / max_devices غير صحيحة"))

    if days <= 0 or max_devices <= 0:
        return redirect(url_for("admin_licenses", message="عدد الأيام والأجهزة يجب أن يكون أكبر من صفر"))

    lic = License(
        license_key=generate_key(),
        customer_name=customer_name,
        expire_date=today_utc() + timedelta(days=days),
        max_devices=max_devices,
        used_devices=0,
        status="active",
        device_ids="[]",
    )
    db.session.add(lic)
    db.session.commit()

    return redirect(url_for("admin_licenses", message=f"تم إنشاء الترخيص: {lic.license_key}"))


@app.route("/admin/remove-device", methods=["POST"])
@require_auth
def admin_remove_device():
    license_key = str(request.form.get("license_key", "")).strip()
    device_id = str(request.form.get("device_id", "")).strip()

    lic = License.query.filter_by(license_key=license_key).first()
    if not lic:
        return redirect(url_for("admin_licenses", message="الترخيص غير موجود"))

    devices = lic.device_list()
    if device_id in devices:
        devices.remove(device_id)
        lic.set_device_list(devices)
        db.session.commit()

    return redirect(url_for("admin_licenses", message="تم حذف الجهاز"))


@app.route("/admin/reset-devices", methods=["POST"])
@require_auth
def admin_reset_devices():
    license_key = str(request.form.get("license_key", "")).strip()

    lic = License.query.filter_by(license_key=license_key).first()
    if not lic:
        return redirect(url_for("admin_licenses", message="الترخيص غير موجود"))

    lic.set_device_list([])
    db.session.commit()
    return redirect(url_for("admin_licenses", message="تم تصفير الأجهزة"))


@app.route("/admin/toggle-license", methods=["POST"])
@require_auth
def admin_toggle_license():
    license_key = str(request.form.get("license_key", "")).strip()
    new_status = str(request.form.get("new_status", "blocked")).strip()

    lic = License.query.filter_by(license_key=license_key).first()
    if not lic:
        return redirect(url_for("admin_licenses", message="الترخيص غير موجود"))

    if new_status not in ("active", "blocked"):
        new_status = "blocked"

    lic.status = new_status
    db.session.commit()
    return redirect(url_for("admin_licenses", message=f"تم تغيير الحالة إلى {new_status}"))


@app.route("/admin/update-max-devices", methods=["POST"])
@require_auth
def admin_update_max_devices():
    license_key = str(request.form.get("license_key", "")).strip()

    try:
        max_devices = int(request.form.get("max_devices", 1))
    except Exception:
        return redirect(url_for("admin_licenses", message="عدد الأجهزة غير صحيح"))

    if max_devices <= 0:
        return redirect(url_for("admin_licenses", message="عدد الأجهزة يجب أن يكون أكبر من صفر"))

    lic = License.query.filter_by(license_key=license_key).first()
    if not lic:
        return redirect(url_for("admin_licenses", message="الترخيص غير موجود"))

    lic.max_devices = max_devices
    db.session.commit()
    return redirect(url_for("admin_licenses", message="تم تحديث عدد الأجهزة"))


@app.route("/admin/delete-license", methods=["POST"])
@require_auth
def admin_delete_license():
    license_key = str(request.form.get("license_key", "")).strip()

    lic = License.query.filter_by(license_key=license_key).first()
    if not lic:
        return redirect(url_for("admin_licenses", message="الترخيص غير موجود"))

    db.session.delete(lic)
    db.session.commit()
    return redirect(url_for("admin_licenses", message="تم حذف الترخيص"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
