from flask import Flask, jsonify, render_template_string, request, redirect, url_for, Response
from functools import wraps
from datetime import datetime, timedelta
import json
import os
import uuid
import psycopg2
from psycopg2.pool import SimpleConnectionPool

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "12345678")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")


pool = SimpleConnectionPool(
    minconn=1,
    maxconn=5,
    dsn=DATABASE_URL,
)


def get_conn():
    return pool.getconn()


def put_conn(conn):
    if conn:
        pool.putconn(conn)


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


def init_db():
    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                id SERIAL PRIMARY KEY,
                license_key TEXT UNIQUE NOT NULL,
                customer_name TEXT,
                device_ids TEXT NOT NULL DEFAULT '[]',
                max_devices INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',
                expire_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # تحسينات وفهارس
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_licenses_key
            ON licenses (license_key)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_licenses_status
            ON licenses (status)
        """)

        # ترقيات آمنة لو كان الجدول قديم
        cur.execute("""
            ALTER TABLE licenses
            ADD COLUMN IF NOT EXISTS customer_name TEXT
        """)
        cur.execute("""
            ALTER TABLE licenses
            ADD COLUMN IF NOT EXISTS device_ids TEXT NOT NULL DEFAULT '[]'
        """)
        cur.execute("""
            ALTER TABLE licenses
            ADD COLUMN IF NOT EXISTS max_devices INTEGER NOT NULL DEFAULT 1
        """)
        cur.execute("""
            ALTER TABLE licenses
            ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'
        """)
        cur.execute("""
            ALTER TABLE licenses
            ADD COLUMN IF NOT EXISTS expire_date TEXT
        """)
        cur.execute("""
            ALTER TABLE licenses
            ADD COLUMN IF NOT EXISTS created_at TEXT
        """)

        # تنظيف قيم فارغة قديمة
        cur.execute("""
            UPDATE licenses
            SET device_ids = '[]'
            WHERE device_ids IS NULL OR device_ids = ''
        """)
        cur.execute("""
            UPDATE licenses
            SET max_devices = 1
            WHERE max_devices IS NULL OR max_devices < 1
        """)
        cur.execute("""
            UPDATE licenses
            SET status = 'active'
            WHERE status IS NULL OR status = ''
        """)
        cur.execute("""
            UPDATE licenses
            SET created_at = %s
            WHERE created_at IS NULL OR created_at = ''
        """, (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),))

        conn.commit()
    finally:
        if cur:
            cur.close()
        put_conn(conn)


def generate_license_key():
    return str(uuid.uuid4()).upper().replace("-", "")[:16]


def normalize_device_ids(raw_device_id=None, raw_device_ids=None):
    device_ids = []

    if isinstance(raw_device_ids, list):
        device_ids.extend(raw_device_ids)
    elif isinstance(raw_device_ids, str) and raw_device_ids.strip():
        try:
            parsed = json.loads(raw_device_ids)
            if isinstance(parsed, list):
                device_ids.extend(parsed)
            else:
                device_ids.append(raw_device_ids)
        except Exception:
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


def parse_device_ids(device_ids_json):
    if not device_ids_json:
        return []
    try:
        parsed = json.loads(device_ids_json)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        pass
    return []


def get_license(license_key):
    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT license_key, customer_name, device_ids, max_devices, status, expire_date, created_at
            FROM licenses
            WHERE license_key = %s
        """, (license_key,))
        return cur.fetchone()
    finally:
        if cur:
            cur.close()
        put_conn(conn)


def get_all_licenses():
    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT license_key, customer_name, device_ids, max_devices, status, expire_date, created_at
            FROM licenses
            ORDER BY id DESC
        """)
        return cur.fetchall()
    finally:
        if cur:
            cur.close()
        put_conn(conn)


def create_license_record(customer_name, days, max_devices, initial_device_ids=None):
    initial_device_ids = initial_device_ids or []
    license_key = generate_license_key()
    expire_date = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")
    created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO licenses (
                license_key, customer_name, device_ids, max_devices, status, expire_date, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            license_key,
            customer_name,
            json.dumps(initial_device_ids),
            max_devices,
            "active",
            expire_date,
            created_at,
        ))
        conn.commit()
        return {
            "license_key": license_key,
            "customer_name": customer_name,
            "expire_date": expire_date,
            "max_devices": max_devices,
            "device_ids": initial_device_ids,
            "used_devices": len(initial_device_ids),
        }
    finally:
        if cur:
            cur.close()
        put_conn(conn)


def save_device_ids(license_key, device_ids):
    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE licenses
            SET device_ids = %s
            WHERE license_key = %s
        """, (json.dumps(device_ids), license_key))
        conn.commit()
    finally:
        if cur:
            cur.close()
        put_conn(conn)


def update_license_status(license_key, new_status):
    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE licenses
            SET status = %s
            WHERE license_key = %s
        """, (new_status, license_key))
        conn.commit()
    finally:
        if cur:
            cur.close()
        put_conn(conn)


def update_max_devices_value(license_key, max_devices):
    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE licenses
            SET max_devices = %s
            WHERE license_key = %s
        """, (max_devices, license_key))
        conn.commit()
    finally:
        if cur:
            cur.close()
        put_conn(conn)


def delete_license_record(license_key):
    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM licenses WHERE license_key = %s", (license_key,))
        conn.commit()
    finally:
        if cur:
            cur.close()
        put_conn(conn)


def serialize_license_row(row):
    if not row:
        return None

    license_key, customer_name, device_ids_json, max_devices, status, expire_date, created_at = row
    device_ids = parse_device_ids(device_ids_json)

    return {
        "license_key": license_key,
        "customer_name": customer_name,
        "device_ids": device_ids,
        "used_devices": len(device_ids),
        "max_devices": int(max_devices or 1),
        "status": status,
        "expire_date": expire_date,
        "created_at": created_at,
    }


LICENSES_ADMIN_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>لوحة إدارة التراخيص</title>
    <style>
        :root {
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
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Tahoma, Arial, sans-serif;
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
        .hero { padding: 22px; margin-bottom: 16px; }
        .hero h1 { margin: 0 0 6px; font-size: 30px; }
        .hero p { margin: 0; color: var(--muted); }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin: 16px 0;
        }
        .stat { padding: 16px; }
        .stat .label { color: var(--muted); font-size: 13px; margin-bottom: 8px; }
        .stat .value { font-size: 24px; font-weight: 700; }
        .card { padding: 18px; margin: 16px 0; }
        .card h2 { margin-top: 0; margin-bottom: 14px; font-size: 22px; }
        form.inline { display: inline; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
        }
        input, button {
            width: 100%;
            padding: 11px 12px;
            border-radius: 12px;
            border: 1px solid #d8cfbf;
            font-size: 14px;
            font-family: inherit;
        }
        button {
            cursor: pointer;
            background: var(--accent);
            color: white;
            border: none;
            font-weight: 700;
        }
        .btn-danger { background: var(--danger); }
        .btn-warn { background: var(--warn); }
        .btn-ok { background: var(--ok); }
        .btn-muted { background: #475569; }
        .actions {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
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
        th { background: #f6f0e5; font-size: 13px; }
        tr:last-child td { border-bottom: none; }
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
        .status.active { background: #ecfdf5; color: #166534; }
        .status.blocked { background: #fef2f2; color: #991b1b; }
        .status.expired, .status.denied { background: #fff7ed; color: #b45309; }
        .muted { color: var(--muted); }
        .flash {
            padding: 12px 14px;
            border-radius: 12px;
            margin-bottom: 12px;
            background: #ecfdf5;
            color: #166534;
            border: 1px solid #bbf7d0;
            word-break: break-word;
        }
    </style>
</head>
<body>
    <div class="page">
        <section class="hero">
            <h1>لوحة إدارة التراخيص</h1>
            <p>التراخيص محفوظة في PostgreSQL ولن تضيع مع التحديث.</p>
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
                    <div><input type="text" name="customer_name" placeholder="اسم العميل" required></div>
                    <div><input type="number" name="days" placeholder="عدد الأيام" value="30" min="1" required></div>
                    <div><input type="number" name="max_devices" placeholder="عدد الأجهزة" value="1" min="1" required></div>
                    <div><button type="submit">إنشاء الترخيص</button></div>
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
                    <td><strong>{{ item.license_key }}</strong></td>
                    <td>{{ item.customer_name or '-' }}</td>
                    <td><span class="status {{ item.status }}">{{ item.status }}</span></td>
                    <td>
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
                    <td>{{ item.used_devices }} / {{ item.max_devices }}</td>
                    <td>{{ item.expire_date }}</td>
                    <td>{{ item.created_at or '-' }}</td>
                    <td>
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


@app.route("/")
def home():
    return "License Server Running (PostgreSQL)"


@app.route("/debug-db")
@require_auth
def debug_db():
    return jsonify({
        "database_url_exists": bool(DATABASE_URL),
        "database_engine": "postgresql",
        "admin_user": ADMIN_USERNAME,
    })


@app.route("/api/create-license", methods=["POST"])
@require_auth
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

    created = create_license_record(customer_name, days, max_devices, initial_device_ids)
    return jsonify({"status": "success", **created})


@app.route("/api/licenses", methods=["GET"])
@require_auth
def api_list_licenses():
    licenses = [serialize_license_row(row) for row in get_all_licenses()]
    return jsonify({"status": "success", "count": len(licenses), "licenses": licenses})


@app.route("/api/check-license", methods=["POST"])
def check_license():
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No data"}), 400

    license_key = str(data.get("license_key", "")).strip()
    device_id = str(data.get("device_id", "")).strip()

    if not license_key or not device_id:
        return jsonify({"status": "error", "message": "Missing data"}), 400

    lic = get_license(license_key)
    if not lic:
        return jsonify({"status": "invalid", "message": "License not found"}), 404

    _, customer_name, device_ids_json, max_devices, db_status, db_expire_date, _created_at = lic
    device_ids = parse_device_ids(device_ids_json)
    max_devices = int(max_devices or 1)

    if db_status != "active":
        return jsonify({"status": "blocked", "message": "License inactive"}), 403

    expire_date = datetime.strptime(db_expire_date, "%Y-%m-%d").date()
    today = datetime.utcnow().date()

    if today > expire_date:
        return jsonify({"status": "expired", "message": "License expired"}), 403

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


@app.route("/admin/licenses", methods=["GET"])
@require_auth
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
@require_auth
def admin_create_license():
    customer_name = str(request.form.get("customer_name", "Unknown") or "Unknown").strip()
    days = int(request.form.get("days", 30))
    max_devices = int(request.form.get("max_devices", 1))

    if days <= 0:
        return redirect(url_for("admin_licenses", message="عدد الأيام يجب أن يكون أكبر من صفر"))
    if max_devices <= 0:
        return redirect(url_for("admin_licenses", message="عدد الأجهزة يجب أن يكون أكبر من صفر"))

    created = create_license_record(customer_name, days, max_devices, [])
    return redirect(url_for("admin_licenses", message=f"تم إنشاء الترخيص: {created['license_key']}"))


@app.route("/admin/remove-device", methods=["POST"])
@require_auth
def admin_remove_device():
    license_key = request.form.get("license_key", "").strip()
    device_id = request.form.get("device_id", "").strip()

    lic = get_license(license_key)
    if not lic:
        return redirect(url_for("admin_licenses", message="الترخيص غير موجود"))

    device_ids = parse_device_ids(lic[2])

    if device_id in device_ids:
        device_ids.remove(device_id)
        save_device_ids(license_key, device_ids)

    return redirect(url_for("admin_licenses", message="تم حذف الجهاز"))


@app.route("/admin/reset-devices", methods=["POST"])
@require_auth
def admin_reset_devices():
    license_key = request.form.get("license_key", "").strip()
    save_device_ids(license_key, [])
    return redirect(url_for("admin_licenses", message="تم تصفير الأجهزة"))


@app.route("/admin/toggle-license", methods=["POST"])
@require_auth
def admin_toggle_license():
    license_key = request.form.get("license_key", "").strip()
    new_status = request.form.get("new_status", "blocked").strip()

    if new_status not in ["active", "blocked"]:
        new_status = "blocked"

    update_license_status(license_key, new_status)
    return redirect(url_for("admin_licenses", message=f"تم تغيير الحالة إلى {new_status}"))


@app.route("/admin/update-max-devices", methods=["POST"])
@require_auth
def admin_update_max_devices():
    license_key = request.form.get("license_key", "").strip()
    max_devices = int(request.form.get("max_devices", 1))

    if max_devices <= 0:
        return redirect(url_for("admin_licenses", message="عدد الأجهزة يجب أن يكون أكبر من صفر"))

    update_max_devices_value(license_key, max_devices)
    return redirect(url_for("admin_licenses", message="تم تحديث عدد الأجهزة"))


@app.route("/admin/delete-license", methods=["POST"])
@require_auth
def admin_delete_license():
    license_key = request.form.get("license_key", "").strip()
    delete_license_record(license_key)
    return redirect(url_for("admin_licenses", message="تم حذف الترخيص"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
