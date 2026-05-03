from flask import Flask, jsonify, render_template_string, request, redirect, url_for
import json
import os
import sqlite3
from datetime import datetime, timedelta
import uuid

app = Flask(__name__)
DB_NAME = "licenses.db"
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "7"))
API_VERSION = "1.1.0"
DEPLOY_ENV = os.getenv("RENDER_ENVIRONMENT", "local")
DEPLOY_COMMIT = os.getenv("RENDER_GIT_COMMIT", "local")

LICENSES_ADMIN_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>لوحة إدارة التراخيص</title>
    <style>
        :root {
            color-scheme: light;
            --bg: #f6f3eb;
            --panel: #fffdf8;
            --line: #ddd3c3;
            --text: #1f2937;
            --muted: #6b7280;
            --accent: #0f766e;
            --danger: #b91c1c;
            --warn: #b45309;
            --ok: #166534;
        }
        * {
            box-sizing: border-box;
        }
        body {
            margin: 0;
            font-family: "Segoe UI", Tahoma, sans-serif;
            background: linear-gradient(135deg, #f8f4ea 0%, #ece5d6 100%);
            color: var(--text);
        }
        .page {
            max-width: 1250px;
            margin: 24px auto;
            padding: 0 16px 40px;
        }
        .hero, .card, table {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 18px;
            box-shadow: 0 10px 30px rgba(0,0,0,.05);
        }
        .hero {
            padding: 22px;
            margin-bottom: 16px;
        }
        .hero h1 {
            margin: 0 0 6px;
            font-size: 30px;
        }
        .hero p {
            margin: 0;
            color: var(--muted);
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin: 16px 0;
        }
        .stat {
            padding: 16px;
        }
        .stat .label {
            color: var(--muted);
            font-size: 13px;
            margin-bottom: 8px;
        }
        .stat .value {
            font-size: 24px;
            font-weight: 700;
        }
        .card {
            padding: 18px;
            margin: 16px 0;
        }
        .card h2 {
            margin-top: 0;
            margin-bottom: 14px;
            font-size: 22px;
        }
        form.inline {
            display: inline;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
        }
        input, select, button {
            width: 100%;
            padding: 11px 12px;
            border-radius: 12px;
            border: 1px solid #d8cfbf;
            font-size: 14px;
            font-family: inherit;
        }
        input:focus, select:focus {
            outline: none;
            border-color: var(--accent);
        }
        button {
            cursor: pointer;
            background: var(--accent);
            color: white;
            border: none;
            font-weight: 700;
        }
        button:hover {
            opacity: .95;
        }
        .btn-danger {
            background: var(--danger);
        }
        .btn-warn {
            background: var(--warn);
        }
        .btn-ok {
            background: var(--ok);
        }
        .btn-muted {
            background: #475569;
        }
        .actions {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .actions form {
            margin: 0;
        }
        .actions button {
            width: auto;
            min-width: 120px;
            padding: 9px 12px;
            font-size: 13px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            overflow: hidden;
        }
        th, td {
            padding: 13px 10px;
            border-bottom: 1px solid #eee7da;
            text-align: right;
            vertical-align: top;
            font-size: 14px;
        }
        th {
            background: #f6f0e5;
            font-size: 13px;
        }
        tr:last-child td {
            border-bottom: none;
        }
        .devices {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .device-row {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }
        .device-tag {
            background: #ecfeff;
            color: #155e75;
            border: 1px solid #a5f3fc;
            border-radius: 999px;
            padding: 5px 10px;
            font-size: 12px;
            word-break: break-all;
        }
        .status {
            display: inline-block;
            padding: 6px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
        }
        .status.active {
            background: #ecfdf5;
            color: #166534;
        }
        .status.blocked {
            background: #fef2f2;
            color: #991b1b;
        }
        .status.expired, .status.denied {
            background: #fff7ed;
            color: #b45309;
        }
        .muted {
            color: var(--muted);
        }
        .top-tools {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 14px;
        }
        .top-tools a {
            text-decoration: none;
            background: #334155;
            color: white;
            padding: 10px 14px;
            border-radius: 12px;
            font-size: 14px;
        }
        .flash {
            padding: 12px 14px;
            border-radius: 12px;
            margin-bottom: 12px;
            background: #ecfdf5;
            color: #166534;
            border: 1px solid #bbf7d0;
        }
        @media (max-width: 900px) {
            table, thead, tbody, th, td, tr {
                display: block;
            }
            thead {
                display: none;
            }
            tr {
                margin-bottom: 14px;
                background: var(--panel);
                border-bottom: 1px solid var(--line);
            }
            td::before {
                content: attr(data-label);
                display: block;
                color: var(--muted);
                font-size: 12px;
                margin-bottom: 4px;
            }
        }
    </style>
</head>
<body>
    <div class="page">
        <section class="hero">
            <h1>لوحة إدارة التراخيص</h1>
            <p>إدارة كاملة للمفاتيح، الأجهزة المفعلة، عدد الأجهزة المسموح، وحالة كل ترخيص.</p>
            <div class="top-tools">
                <a href="/admin/licenses">تحديث الصفحة</a>
                <a href="/api/licenses" target="_blank">عرض JSON</a>
            </div>
        </section>

        {% if message %}
        <div class="flash">{{ message }}</div>
        {% endif %}

        <section class="stats">
            <div class="card stat">
                <div class="label">عدد التراخيص</div>
                <div class="value">{{ licenses|length }}</div>
            </div>
            <div class="card stat">
                <div class="label">الأجهزة المفعلة</div>
                <div class="value">{{ total_devices }}</div>
            </div>
            <div class="card stat">
                <div class="label">التراخيص النشطة</div>
                <div class="value">{{ active_licenses }}</div>
            </div>
            <div class="card stat">
                <div class="label">التراخيص الموقوفة</div>
                <div class="value">{{ blocked_licenses }}</div>
            </div>
        </section>

        <section class="card">
            <h2>إنشاء ترخيص جديد</h2>
            <form method="post" action="/admin/create-license">
                <div class="grid">
                    <div>
                        <input type="text" name="customer_name" placeholder="اسم العميل" required>
                    </div>
                    <div>
                        <input type="number" name="days" placeholder="عدد الأيام" value="30" min="1" required>
                    </div>
                    <div>
                        <input type="number" name="max_devices" placeholder="عدد الأجهزة" value="1" min="1" required>
                    </div>
                    <div>
                        <button type="submit">إنشاء الترخيص</button>
                    </div>
                </div>
            </form>
        </section>

        {% if licenses %}
        <table>
            <thead>
                <tr>
                    <th>المفتاح</th>
                    <th>العميل</th>
                    <th>الحالة</th>
                    <th>الأجهزة</th>
                    <th>الاستخدام</th>
                    <th>الانتهاء</th>
                    <th>الإنشاء</th>
                    <th>الإدارة</th>
                </tr>
            </thead>
            <tbody>
                {% for item in licenses %}
                <tr>
                    <td data-label="المفتاح"><strong>{{ item.license_key }}</strong></td>
                    <td data-label="العميل">{{ item.customer_name or '-' }}</td>
                    <td data-label="الحالة">
                        <span class="status {{ item.status }}">{{ item.status }}</span>
                    </td>
                    <td data-label="الأجهزة">
                        {% if item.device_ids %}
                        <div class="devices">
                            {% for device_id in item.device_ids %}
                            <div class="device-row">
                                <span class="device-tag">{{ device_id }}</span>
                                <form class="inline" method="post" action="/admin/remove-device">
                                    <input type="hidden" name="license_key" value="{{ item.license_key }}">
                                    <input type="hidden" name="device_id" value="{{ device_id }}">
                                    <button type="submit" class="btn-danger">حذف هذا الجهاز</button>
                                </form>
                            </div>
                            {% endfor %}
                        </div>
                        {% else %}
                        <span class="muted">لا توجد أجهزة بعد</span>
                        {% endif %}
                    </td>
                    <td data-label="الاستخدام">{{ item.used_devices }} / {{ item.max_devices }}</td>
                    <td data-label="الانتهاء">{{ item.expire_date }}</td>
                    <td data-label="الإنشاء">{{ item.created_at or '-' }}</td>
                    <td data-label="الإدارة">
                        <div class="actions">
                            <form method="post" action="/admin/toggle-license">
                                <input type="hidden" name="license_key" value="{{ item.license_key }}">
                                <input type="hidden" name="new_status" value="{{ 'blocked' if item.status == 'active' else 'active' }}">
                                <button type="submit" class="{{ 'btn-warn' if item.status == 'active' else 'btn-ok' }}">
                                    {{ 'إيقاف' if item.status == 'active' else 'تفعيل' }}
                                </button>
                            </form>

                            <form method="post" action="/admin/reset-devices">
                                <input type="hidden" name="license_key" value="{{ item.license_key }}">
                                <button type="submit" class="btn-muted">تصفير الأجهزة</button>
                            </form>

                            <form method="post" action="/admin/delete-license" onsubmit="return confirm('هل تريد حذف الترخيص نهائيًا؟');">
                                <input type="hidden" name="license_key" value="{{ item.license_key }}">
                                <button type="submit" class="btn-danger">حذف الترخيص</button>
                            </form>

                            <form method="post" action="/admin/update-max-devices">
                                <input type="hidden" name="license_key" value="{{ item.license_key }}">
                                <input type="number" name="max_devices" value="{{ item.max_devices }}" min="1" style="width: 100px;">
                                <button type="submit">تحديث الأجهزة</button>
                            </form>
                        </div>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <section class="card">
            <div class="muted">لا توجد تراخيص محفوظة بعد.</div>
        </section>
        {% endif %}
    </div>
</body>
</html>
"""


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE NOT NULL,
            customer_name TEXT,
            device_ids TEXT,
            max_devices INTEGER DEFAULT 1,
            status TEXT NOT NULL,
            expire_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL,
            expire_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def generate_license_key():
    return str(uuid.uuid4()).upper().replace("-", "")[:16]


def normalize_device_ids(raw_device_id=None, raw_device_ids=None):
    device_ids = []

    if isinstance(raw_device_ids, list):
        device_ids.extend(raw_device_ids)
    elif isinstance(raw_device_ids, str) and raw_device_ids.strip():
        device_ids.append(raw_device_ids)

    if isinstance(raw_device_id, str) and raw_device_id.strip():
        device_ids.append(raw_device_id)

    normalized = []
    seen = set()
    for item in device_ids:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)

    return normalized


def get_license(license_key):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT license_key, customer_name, device_ids, max_devices, status, expire_date, created_at
        FROM licenses
        WHERE license_key = ?
    """, (license_key,))
    row = cur.fetchone()
    conn.close()
    return row


def get_all_licenses():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT license_key, customer_name, device_ids, max_devices, status, expire_date, created_at
        FROM licenses
        ORDER BY id DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def find_license_by_device(device_id):
    normalized_device_id = str(device_id or "").strip()
    if not normalized_device_id:
        return None

    for row in get_all_licenses():
        device_ids_json = row[2]
        device_ids = json.loads(device_ids_json) if device_ids_json else []
        if normalized_device_id in device_ids:
            return row
    return None


def get_trial(device_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT device_id, status, expire_date, created_at
        FROM trials
        WHERE device_id = ?
        """,
        (device_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def create_trial(device_id, days=TRIAL_DAYS):
    expire_date = (datetime.today() + timedelta(days=days)).strftime("%Y-%m-%d")
    created_at = datetime.today().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO trials (device_id, status, expire_date, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (device_id, "active", expire_date, created_at),
    )
    conn.commit()
    conn.close()
    return get_trial(device_id)


def serialize_license_row(row):
    if not row:
        return None

    license_key, customer_name, device_ids_json, max_devices, status, expire_date, created_at = row
    device_ids = json.loads(device_ids_json) if device_ids_json else []
    return {
        "license_key": license_key,
        "customer_name": customer_name,
        "device_ids": device_ids,
        "used_devices": len(device_ids),
        "max_devices": max_devices,
        "status": status,
        "expire_date": expire_date,
        "created_at": created_at,
    }


def save_device_ids(license_key, device_ids):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        UPDATE licenses
        SET device_ids = ?
        WHERE license_key = ?
    """, (json.dumps(device_ids), license_key))
    conn.commit()
    conn.close()


def update_license_status(license_key, new_status):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        UPDATE licenses
        SET status = ?
        WHERE license_key = ?
    """, (new_status, license_key))
    conn.commit()
    conn.close()


def update_max_devices_value(license_key, max_devices):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        UPDATE licenses
        SET max_devices = ?
        WHERE license_key = ?
    """, (max_devices, license_key))
    conn.commit()
    conn.close()


def delete_license(license_key):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM licenses WHERE license_key = ?", (license_key,))
    conn.commit()
    conn.close()


def check_database_health():
    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        conn.close()
        return True
    except Exception:
        return False


def get_server_meta():
    return {
        "service": "CardGenerator License Server",
        "api_version": API_VERSION,
        "environment": DEPLOY_ENV,
        "commit": DEPLOY_COMMIT,
        "trial_days": TRIAL_DAYS,
        "database": DB_NAME,
        "features": [
            "license_activation",
            "device_activation_lookup",
            "trial_start",
            "trial_check",
            "admin_dashboard",
        ],
    }


@app.route("/")
def home():
    return "License Server Running"


@app.route("/health", methods=["GET"])
@app.route("/healthz", methods=["GET"])
def health_check():
    database_ok = check_database_health()
    payload = {
        "status": "ok" if database_ok else "degraded",
        "database_ok": database_ok,
        "server_time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        **get_server_meta(),
    }
    return jsonify(payload), 200 if database_ok else 503


@app.route("/api/meta", methods=["GET"])
def api_meta():
    return jsonify({
        "status": "success",
        **get_server_meta(),
    })


@app.route("/admin", methods=["GET"])
def admin_home():
    return redirect(url_for("admin_licenses"))


@app.route("/api/create-license", methods=["POST"])
def api_create_license():
    data = request.get_json() or {}

    customer_name = str(data.get("customer_name", "Unknown") or "Unknown").strip()
    days = int(data.get("days", 30))
    max_devices = int(data.get("max_devices", 1))
    initial_device_ids = normalize_device_ids(
        raw_device_id=data.get("device_id"),
        raw_device_ids=data.get("device_ids"),
    )

    if days <= 0:
        return jsonify({"status": "error", "message": "days must be greater than zero"}), 400
    if max_devices <= 0:
        return jsonify({"status": "error", "message": "max_devices must be greater than zero"}), 400
    if len(initial_device_ids) > max_devices:
        return jsonify({"status": "error", "message": "initial devices exceed max_devices"}), 400

    license_key = generate_license_key()
    expire_date = (datetime.today() + timedelta(days=days)).strftime("%Y-%m-%d")
    created_at = datetime.today().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO licenses (
            license_key, customer_name, device_ids, max_devices, status, expire_date, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        license_key,
        customer_name,
        json.dumps(initial_device_ids),
        max_devices,
        "active",
        expire_date,
        created_at
    ))
    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "license_key": license_key,
        "customer_name": customer_name,
        "expire_date": expire_date,
        "max_devices": max_devices,
        "device_ids": initial_device_ids,
        "used_devices": len(initial_device_ids),
    })


@app.route("/api/start-trial", methods=["POST"])
def api_start_trial():
    data = request.get_json() or {}
    device_id = str(data.get("device_id", "") or "").strip()

    if not device_id:
        return jsonify({"status": "error", "message": "Missing device_id"}), 400

    trial = get_trial(device_id)
    if not trial:
        trial = create_trial(device_id)

    _, db_status, db_expire_date, db_created_at = trial
    today = datetime.today().date()
    expire_date = datetime.strptime(db_expire_date, "%Y-%m-%d").date()

    if db_status != "active":
        return jsonify({
            "status": "blocked",
            "message": "Trial inactive",
            "expire_date": db_expire_date,
            "created_at": db_created_at,
        }), 403

    if today > expire_date:
        return jsonify({
            "status": "expired",
            "message": "Trial expired",
            "expire_date": db_expire_date,
            "created_at": db_created_at,
            "trial_days": TRIAL_DAYS,
        }), 403

    days_left = max(0, (expire_date - today).days)
    return jsonify({
        "status": "trial",
        "message": "Trial active",
        "expire_date": db_expire_date,
        "created_at": db_created_at,
        "trial_days": TRIAL_DAYS,
        "days_left": days_left,
        "device_id": device_id,
    })


@app.route("/api/check-trial", methods=["POST"])
def api_check_trial():
    data = request.get_json() or {}
    device_id = str(data.get("device_id", "") or "").strip()

    if not device_id:
        return jsonify({"status": "error", "message": "Missing device_id"}), 400

    trial = get_trial(device_id)
    if not trial:
        return jsonify({"status": "not_found", "message": "Trial not found"}), 404

    _, db_status, db_expire_date, db_created_at = trial
    today = datetime.today().date()
    expire_date = datetime.strptime(db_expire_date, "%Y-%m-%d").date()

    if db_status != "active":
        return jsonify({
            "status": "blocked",
            "message": "Trial inactive",
            "expire_date": db_expire_date,
            "created_at": db_created_at,
        }), 403

    if today > expire_date:
        return jsonify({
            "status": "expired",
            "message": "Trial expired",
            "expire_date": db_expire_date,
            "created_at": db_created_at,
            "trial_days": TRIAL_DAYS,
        }), 403

    days_left = max(0, (expire_date - today).days)
    return jsonify({
        "status": "trial",
        "message": "Trial active",
        "expire_date": db_expire_date,
        "created_at": db_created_at,
        "trial_days": TRIAL_DAYS,
        "days_left": days_left,
        "device_id": device_id,
    })


@app.route("/api/licenses", methods=["GET"])
def api_list_licenses():
    licenses = [serialize_license_row(row) for row in get_all_licenses()]
    return jsonify({"status": "success", "count": len(licenses), "licenses": licenses})


@app.route("/api/check-license", methods=["POST"])
def check_license():
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No data"}), 400

    license_key = data.get("license_key")
    device_id = data.get("device_id")

    if not license_key or not device_id:
        return jsonify({"status": "error", "message": "Missing data"}), 400

    lic = get_license(license_key)
    if not lic:
        return jsonify({"status": "invalid", "message": "License not found"}), 404

    _, customer_name, device_ids_json, max_devices, db_status, db_expire_date, _created_at = lic

    if db_status != "active":
        return jsonify({"status": "blocked", "message": "License inactive"}), 403

    expire_date = datetime.strptime(db_expire_date, "%Y-%m-%d").date()
    today = datetime.today().date()

    if today > expire_date:
        return jsonify({"status": "expired", "message": "License expired"}), 403

    device_ids = json.loads(device_ids_json) if device_ids_json else []

    if device_id in device_ids:
        return jsonify({
            "status": "active",
            "message": "Valid",
            "customer_name": customer_name,
            "expire_date": db_expire_date,
            "max_devices": max_devices,
            "used_devices": len(device_ids),
        })

    if len(device_ids) >= max_devices:
        return jsonify({
            "status": "denied",
            "message": "Device limit reached",
            "customer_name": customer_name,
            "expire_date": db_expire_date,
        }), 403

    device_ids.append(device_id)
    save_device_ids(license_key, device_ids)

    return jsonify({
        "status": "active",
        "message": "Activated",
        "customer_name": customer_name,
        "expire_date": db_expire_date,
        "max_devices": max_devices,
        "used_devices": len(device_ids),
    })


@app.route("/api/check-device", methods=["POST"])
def check_device_activation():
    data = request.get_json() or {}
    device_id = str(data.get("device_id", "") or "").strip()

    if not device_id:
        return jsonify({"status": "error", "message": "Missing device_id"}), 400

    lic = find_license_by_device(device_id)
    if not lic:
        return jsonify({"status": "not_found", "message": "Device is not linked to any license"}), 404

    _license_key, customer_name, device_ids_json, max_devices, db_status, db_expire_date, _created_at = lic

    if db_status != "active":
        return jsonify({
            "status": "blocked",
            "message": "License inactive",
            "customer_name": customer_name,
            "expire_date": db_expire_date,
        }), 403

    expire_date = datetime.strptime(db_expire_date, "%Y-%m-%d").date()
    today = datetime.today().date()
    if today > expire_date:
        return jsonify({
            "status": "expired",
            "message": "License expired",
            "customer_name": customer_name,
            "expire_date": db_expire_date,
        }), 403

    device_ids = json.loads(device_ids_json) if device_ids_json else []
    return jsonify({
        "status": "active",
        "message": "Device activation valid",
        "customer_name": customer_name,
        "expire_date": db_expire_date,
        "max_devices": max_devices,
        "used_devices": len(device_ids),
        "device_id": device_id,
    })


@app.route("/admin/licenses", methods=["GET"])
def admin_licenses():
    message = request.args.get("message", "")
    licenses = [serialize_license_row(row) for row in get_all_licenses()]
    total_devices = sum(item["used_devices"] for item in licenses)
    active_licenses = sum(1 for item in licenses if item["status"] == "active")
    blocked_licenses = sum(1 for item in licenses if item["status"] == "blocked")

    return render_template_string(
        LICENSES_ADMIN_TEMPLATE,
        licenses=licenses,
        total_devices=total_devices,
        active_licenses=active_licenses,
        blocked_licenses=blocked_licenses,
        message=message,
    )


@app.route("/admin/create-license", methods=["POST"])
def admin_create_license():
    customer_name = str(request.form.get("customer_name", "Unknown") or "Unknown").strip()
    days = int(request.form.get("days", 30))
    max_devices = int(request.form.get("max_devices", 1))

    if days <= 0:
        return redirect(url_for("admin_licenses", message="عدد الأيام يجب أن يكون أكبر من صفر"))
    if max_devices <= 0:
        return redirect(url_for("admin_licenses", message="عدد الأجهزة يجب أن يكون أكبر من صفر"))

    license_key = generate_license_key()
    expire_date = (datetime.today() + timedelta(days=days)).strftime("%Y-%m-%d")
    created_at = datetime.today().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO licenses (
            license_key, customer_name, device_ids, max_devices, status, expire_date, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        license_key,
        customer_name,
        json.dumps([]),
        max_devices,
        "active",
        expire_date,
        created_at
    ))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_licenses", message=f"تم إنشاء الترخيص: {license_key}"))


@app.route("/admin/remove-device", methods=["POST"])
def admin_remove_device():
    license_key = request.form.get("license_key")
    device_id = request.form.get("device_id")

    lic = get_license(license_key)
    if not lic:
        return redirect(url_for("admin_licenses", message="الترخيص غير موجود"))

    device_ids = json.loads(lic[2]) if lic[2] else []

    if device_id in device_ids:
        device_ids.remove(device_id)
        save_device_ids(license_key, device_ids)

    return redirect(url_for("admin_licenses", message="تم حذف الجهاز"))


@app.route("/admin/reset-devices", methods=["POST"])
def admin_reset_devices():
    license_key = request.form.get("license_key")
    save_device_ids(license_key, [])
    return redirect(url_for("admin_licenses", message="تم تصفير الأجهزة"))


@app.route("/admin/toggle-license", methods=["POST"])
def admin_toggle_license():
    license_key = request.form.get("license_key")
    new_status = request.form.get("new_status", "blocked")

    if new_status not in ["active", "blocked"]:
        new_status = "blocked"

    update_license_status(license_key, new_status)
    return redirect(url_for("admin_licenses", message=f"تم تغيير الحالة إلى {new_status}"))


@app.route("/admin/update-max-devices", methods=["POST"])
def admin_update_max_devices():
    license_key = request.form.get("license_key")
    max_devices = int(request.form.get("max_devices", 1))

    if max_devices <= 0:
        return redirect(url_for("admin_licenses", message="عدد الأجهزة يجب أن يكون أكبر من صفر"))

    update_max_devices_value(license_key, max_devices)
    return redirect(url_for("admin_licenses", message="تم تحديث عدد الأجهزة"))


@app.route("/admin/delete-license", methods=["POST"])
def admin_delete_license():
    license_key = request.form.get("license_key")
    delete_license(license_key)
    return redirect(url_for("admin_licenses", message="تم حذف الترخيص"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
