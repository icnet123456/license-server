from flask import Flask, request, jsonify, render_template_string, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from datetime import datetime, timedelta, date
from functools import wraps
import os
import json
import uuid
import traceback

app = Flask(__name__)
app.config["PROPAGATE_EXCEPTIONS"] = True

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "3"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "12345678")


class License(db.Model):
    __tablename__ = "licenses"

    id = db.Column(db.Integer, primary_key=True)
    license_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    customer_name = db.Column(db.String(120), nullable=True)
    expire_date = db.Column(db.Date, nullable=True)
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
            text_value = str(item or "").strip()
            if not text_value or text_value in seen:
                continue
            seen.add(text_value)
            clean.append(text_value)
        self.device_ids = json.dumps(clean, ensure_ascii=False)
        self.used_devices = len(clean)


class Trial(db.Model):
    __tablename__ = "trials"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    start_date = db.Column(db.Date, nullable=True)
    expire_date = db.Column(db.Date, nullable=True)
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


def safe_datetime_text(value):
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def safe_date_text(value):
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def serialize_license(lic: License):
    return {
        "license_key": lic.license_key,
        "customer_name": lic.customer_name or "",
        "expire_date": safe_date_text(lic.expire_date),
        "max_devices": int(lic.max_devices or 1),
        "used_devices": int(lic.used_devices or 0),
        "status": lic.status or "active",
        "device_ids": lic.device_list(),
        "created_at": safe_datetime_text(lic.created_at),
    }


def serialize_trial(trial: Trial):
    return {
        "device_id": trial.device_id,
        "start_date": safe_date_text(trial.start_date),
        "expire_date": safe_date_text(trial.expire_date),
        "status": trial.status or "trial",
        "created_at": safe_datetime_text(trial.created_at),
    }


def migrate_legacy_tables():
    with db.engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS licenses (
                id SERIAL PRIMARY KEY,
                license_key VARCHAR(64) UNIQUE NOT NULL,
                customer_name VARCHAR(120),
                expire_date DATE,
                max_devices INTEGER DEFAULT 1,
                used_devices INTEGER DEFAULT 0,
                status VARCHAR(32) DEFAULT 'active',
                device_ids TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        license_columns = {
            row[0]
            for row in conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'licenses'
            """)).fetchall()
        }

        if "customer_name" not in license_columns:
            conn.execute(text("ALTER TABLE licenses ADD COLUMN customer_name VARCHAR(120)"))
        if "expire_date" not in license_columns:
            conn.execute(text("ALTER TABLE licenses ADD COLUMN expire_date DATE"))
        if "max_devices" not in license_columns:
            conn.execute(text("ALTER TABLE licenses ADD COLUMN max_devices INTEGER DEFAULT 1"))
        if "used_devices" not in license_columns:
            conn.execute(text("ALTER TABLE licenses ADD COLUMN used_devices INTEGER DEFAULT 0"))
        if "status" not in license_columns:
            conn.execute(text("ALTER TABLE licenses ADD COLUMN status VARCHAR(32) DEFAULT 'active'"))
        if "device_ids" not in license_columns:
            conn.execute(text("ALTER TABLE licenses ADD COLUMN device_ids TEXT DEFAULT '[]'"))
        if "created_at" not in license_columns:
            conn.execute(text("ALTER TABLE licenses ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))

        conn.execute(text("UPDATE licenses SET max_devices = 1 WHERE max_devices IS NULL"))
        conn.execute(text("UPDATE licenses SET used_devices = 0 WHERE used_devices IS NULL"))
        conn.execute(text("UPDATE licenses SET status = 'active' WHERE status IS NULL"))
        conn.execute(text("UPDATE licenses SET device_ids = '[]' WHERE device_ids IS NULL"))
        conn.execute(text("UPDATE licenses SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS trials (
                id SERIAL PRIMARY KEY,
                device_id VARCHAR(128) UNIQUE NOT NULL,
                start_date DATE,
                expire_date DATE,
                status VARCHAR(32) DEFAULT 'trial',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        trial_columns = {
            row[0]
            for row in conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'trials'
            """)).fetchall()
        }

        if "start_date" not in trial_columns:
            conn.execute(text("ALTER TABLE trials ADD COLUMN start_date DATE"))
        if "expire_date" not in trial_columns:
            conn.execute(text("ALTER TABLE trials ADD COLUMN expire_date DATE"))
        if "status" not in trial_columns:
            conn.execute(text("ALTER TABLE trials ADD COLUMN status VARCHAR(32) DEFAULT 'trial'"))
        if "created_at" not in trial_columns:
            conn.execute(text("ALTER TABLE trials ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))

        conn.execute(text("UPDATE trials SET status = 'trial' WHERE status IS NULL"))
        conn.execute(text("UPDATE trials SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))


with app.app_context():
    db.create_all()
    migrate_legacy_tables()


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


@app.route("/admin/health")
@require_auth
def admin_health():
    try:
        licenses_count = License.query.count()
        trials_count = Trial.query.count()

        sample_license = License.query.order_by(License.id.desc()).first()
        sample_trial = Trial.query.order_by(Trial.id.desc()).first()

        return jsonify({
            "status": "ok",
            "database_url_exists": bool(DATABASE_URL),
            "driver": "psycopg3",
            "trial_days": TRIAL_DAYS,
            "licenses_count": licenses_count,
            "trials_count": trials_count,
            "sample_license": serialize_license(sample_license) if sample_license else None,
            "sample_trial": serialize_trial(sample_trial) if sample_trial else None,
        })
    except Exception as exc:
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


@app.route("/api/create-license", methods=["POST"])
@require_auth
def api_create_license():
    try:
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
            text_value = str(item or "").strip()
            if not text_value or text_value in seen:
                continue
            seen.add(text_value)
            clean_devices.append(text_value)

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
            "expire_date": safe_date_text(lic.expire_date),
            "max_devices": lic.max_devices,
            "used_devices": lic.used_devices,
            "device_ids": lic.device_list(),
            "created_at": safe_datetime_text(lic.created_at),
        })
    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


@app.route("/api/check-license", methods=["POST"])
def api_check_license():
    try:
        data = request.get_json(silent=True) or {}

        license_key = str(data.get("license_key", "")).strip()
        device_id = str(data.get("device_id", "")).strip()

        if not license_key or not device_id:
            return jsonify({"status": "error", "message": "license_key and device_id required"}), 400

        lic = License.query.filter_by(license_key=license_key).first()
        if not lic:
            return jsonify({"status": "invalid", "message": "License not found"}), 404

        if (lic.status or "active") != "active":
            return jsonify({"status": "blocked", "message": "License inactive"}), 403

        if lic.expire_date and today_utc() > lic.expire_date:
            return jsonify({
                "status": "expired",
                "message": "License expired",
                "expire_date": safe_date_text(lic.expire_date),
            }), 403

        devices = lic.device_list()

        if device_id in devices:
            return jsonify({
                "status": "active",
                "message": "Valid",
                "customer_name": lic.customer_name,
                "expire_date": safe_date_text(lic.expire_date),
                "max_devices": lic.max_devices,
                "used_devices": len(devices),
            })

        if len(devices) >= int(lic.max_devices or 1):
            return jsonify({
                "status": "denied",
                "message": "Device limit reached",
                "customer_name": lic.customer_name,
                "expire_date": safe_date_text(lic.expire_date),
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
            "expire_date": safe_date_text(lic.expire_date),
            "max_devices": lic.max_devices,
            "used_devices": lic.used_devices,
        })
    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


@app.route("/api/check-device", methods=["POST"])
def api_check_device():
    try:
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
                    "expire_date": safe_date_text(lic.expire_date),
                    "max_devices": lic.max_devices,
                    "used_devices": lic.used_devices,
                })

        return jsonify({
            "status": "inactive",
            "message": "Device is not activated",
        }), 404
    except Exception as exc:
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


@app.route("/api/start-trial", methods=["POST"])
def api_start_trial():
    try:
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

        if trial.expire_date and today_utc() > trial.expire_date:
            trial.status = "expired"
            db.session.commit()
            return jsonify({
                "status": "expired",
                "message": "Trial expired",
                "expire_date": safe_date_text(trial.expire_date),
                "days_left": 0,
            }), 403

        days_left = max(0, (trial.expire_date - today_utc()).days)
        return jsonify({
            "status": "trial",
            "message": "Trial active",
            "expire_date": safe_date_text(trial.expire_date),
            "days_left": days_left,
            "trial_days": TRIAL_DAYS,
            "created_at": safe_datetime_text(trial.created_at),
        })
    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


@app.route("/api/check-trial", methods=["POST"])
def api_check_trial():
    try:
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

        if trial.expire_date and today_utc() > trial.expire_date:
            trial.status = "expired"
            db.session.commit()
            return jsonify({
                "status": "expired",
                "message": "Trial expired",
                "expire_date": safe_date_text(trial.expire_date),
                "days_left": 0,
            }), 403

        days_left = max(0, (trial.expire_date - today_utc()).days)
        return jsonify({
            "status": "trial",
            "message": "Trial active",
            "expire_date": safe_date_text(trial.expire_date),
            "days_left": days_left,
            "trial_days": TRIAL_DAYS,
            "created_at": safe_datetime_text(trial.created_at),
        })
    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


ADMIN_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>لوحة إدارة التراخيص</title>
    <style>
        :root{
            --bg:#f7f4ee;
            --panel:#fffdf9;
            --line:#e7dfd2;
            --text:#1f2937;
            --muted:#6b7280;
            --accent:#0f766e;
            --accent-dark:#0b5f58;
            --danger:#b91c1c;
            --warn:#c07a12;
            --shadow:0 8px 24px rgba(15,23,42,.06);
            --radius:16px;
        }
        *{box-sizing:border-box}
        body{
            font-family:Tahoma, Arial, sans-serif;
            background:linear-gradient(180deg,#fbf8f3 0%, #f4efe5 100%);
            margin:0;
            padding:14px;
            color:var(--text);
        }
        .wrap{
            max-width:1180px;
            margin:auto;
        }
        .header{
            margin-bottom:14px;
        }
        .header h1{
            margin:0 0 6px;
            font-size:24px;
            font-weight:700;
        }
        .header p{
            margin:0;
            color:var(--muted);
            font-size:14px;
        }
        .card{
            background:var(--panel);
            border:1px solid var(--line);
            border-radius:var(--radius);
            padding:14px;
            margin-bottom:14px;
            box-shadow:var(--shadow);
        }
        h2{
            margin:0 0 12px;
            font-size:18px;
            font-weight:700;
        }
        .grid{
            display:grid;
            grid-template-columns:repeat(4, minmax(0,1fr));
            gap:10px;
        }
        input, button{
            width:100%;
            min-height:42px;
            padding:10px 12px;
            border-radius:12px;
            border:1px solid #d8cfc2;
            font-family:inherit;
            font-size:14px;
        }
        input{
            background:#fff;
            color:var(--text);
        }
        input:focus{
            outline:none;
            border-color:#7cb8b1;
            box-shadow:0 0 0 3px rgba(15,118,110,.10);
        }
        button{
            background:var(--accent);
            color:#fff;
            border:none;
            cursor:pointer;
            font-weight:700;
            transition:.15s ease;
        }
        button:hover{
            background:var(--accent-dark);
        }
        .danger{background:var(--danger)}
        .danger:hover{background:#991b1b}
        .warn{background:var(--warn)}
        .warn:hover{background:#a16207}
        .muted{
            color:var(--muted);
            font-size:13px;
        }
        .flash{
            background:#ecfdf5;
            border:1px solid #bbf7d0;
            color:#166534;
            padding:10px 12px;
            border-radius:12px;
            margin-bottom:12px;
            font-size:14px;
        }
        .table-wrap{
            overflow-x:auto;
            -webkit-overflow-scrolling:touch;
            border-radius:12px;
        }
        table{
            width:100%;
            border-collapse:collapse;
            min-width:860px;
        }
        th, td{
            padding:10px 8px;
            border-bottom:1px solid #efe8db;
            text-align:right;
            vertical-align:top;
            font-size:13px;
        }
        th{
            background:#f6f1e7;
            color:#374151;
            font-weight:700;
            position:sticky;
            top:0;
        }
        .tag{
            display:inline-block;
            padding:4px 9px;
            border-radius:999px;
            background:#e7f8f4;
            color:#0f766e;
            font-size:12px;
            margin:2px 0;
            line-height:1.6;
            word-break:break-all;
        }
        .trial{
            background:#e8f0ff;
            color:#1d4ed8;
        }
        .blocked{
            background:#fff3cd;
            color:#8a6d3b;
        }
        .device-box{
            margin-bottom:6px;
        }
        form.inline{
            display:inline-block;
            margin:4px 0 0;
        }
        .actions{
            display:flex;
            flex-wrap:wrap;
            gap:6px;
            min-width:250px;
        }
        .actions form.inline{
            margin:0;
        }
        .actions button,
        .actions input{
            width:auto;
        }

        @media (max-width: 900px){
            .grid{
                grid-template-columns:repeat(2, minmax(0,1fr));
            }
            .header h1{
                font-size:21px;
            }
        }

        @media (max-width: 640px){
            body{
                padding:10px;
            }
            .card{
                padding:12px;
                border-radius:14px;
            }
            .grid{
                grid-template-columns:1fr;
            }
            .header h1{
                font-size:19px;
            }
            .header p{
                font-size:13px;
            }
            h2{
                font-size:16px;
            }
            input, button{
                min-height:44px;
                font-size:14px;
            }
            table{
                min-width:720px;
            }
            th, td{
                font-size:12px;
                padding:9px 7px;
            }
            .tag{
                font-size:11px;
            }
        }
    </style>
</head>
<body>
<div class="wrap">
    <div class="header">
        <h1>لوحة إدارة التراخيص</h1>
        <p>واجهة خفيفة ومرنة ومتوافقة مع الجوال. مدة التجربة الحالية: {{ trial_days }} أيام.</p>
    </div>

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
        <div class="table-wrap">
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
                        <div class="actions">
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
                                <input type="number" name="max_devices" min="1" value="{{ l.max_devices }}" style="width:78px;">
                                <button type="submit">تحديث</button>
                            </form>

                            <form method="post" action="{{ url_for('admin_delete_license') }}" class="inline" onsubmit="return confirm('هل تريد حذف الترخيص؟');">
                                <input type="hidden" name="license_key" value="{{ l.license_key }}">
                                <button class="danger" type="submit">حذف</button>
                            </form>
                        </div>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
        {% else %}
            <p class="muted">لا توجد تراخيص بعد.</p>
        {% endif %}
    </div>

    <div class="card">
        <h2>الأجهزة التجريبية</h2>
        {% if trials %}
        <div class="table-wrap">
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
        </div>
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
    try:
        message = request.args.get("message", "")
        licenses = [serialize_license(x) for x in License.query.order_by(License.id.desc()).all()]
        trials = [serialize_trial(x) for x in Trial.query.order_by(Trial.id.desc()).all()]
        return render_template_string(
            ADMIN_TEMPLATE,
            licenses=licenses,
            trials=trials,
            message=message,
            trial_days=TRIAL_DAYS,
        )
    except Exception as exc:
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


@app.route("/admin/create-license", methods=["POST"])
@require_auth
def admin_create_license():
    try:
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
    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


@app.route("/admin/remove-device", methods=["POST"])
@require_auth
def admin_remove_device():
    try:
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
    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


@app.route("/admin/reset-devices", methods=["POST"])
@require_auth
def admin_reset_devices():
    try:
        license_key = str(request.form.get("license_key", "")).strip()

        lic = License.query.filter_by(license_key=license_key).first()
        if not lic:
            return redirect(url_for("admin_licenses", message="الترخيص غير موجود"))

        lic.set_device_list([])
        db.session.commit()
        return redirect(url_for("admin_licenses", message="تم تصفير الأجهزة"))
    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


@app.route("/admin/toggle-license", methods=["POST"])
@require_auth
def admin_toggle_license():
    try:
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
    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


@app.route("/admin/update-max-devices", methods=["POST"])
@require_auth
def admin_update_max_devices():
    try:
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
    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


@app.route("/admin/delete-license", methods=["POST"])
@require_auth
def admin_delete_license():
    try:
        license_key = str(request.form.get("license_key", "")).strip()

        lic = License.query.filter_by(license_key=license_key).first()
        if not lic:
            return redirect(url_for("admin_licenses", message="الترخيص غير موجود"))

        db.session.delete(lic)
        db.session.commit()
        return redirect(url_for("admin_licenses", message="تم حذف الترخيص"))
    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(),
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
