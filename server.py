from flask import Flask, jsonify, render_template_string, request
import json
import sqlite3
from datetime import datetime, timedelta
import uuid


app = Flask(__name__)
DB_NAME = "licenses.db"

LICENSES_ADMIN_TEMPLATE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>لوحة التراخيص</title>
    <style>
        :root {
            color-scheme: light;
            --bg: #f3f0e8;
            --panel: #fffdf8;
            --line: #d8cfbf;
            --text: #1f2937;
            --muted: #6b7280;
            --accent: #0f766e;
            --warn: #b45309;
        }
        body {
            margin: 0;
            font-family: "Segoe UI", Tahoma, sans-serif;
            background: linear-gradient(135deg, #f7f3ea 0%, #ece6d8 100%);
            color: var(--text);
        }
        .page {
            max-width: 1100px;
            margin: 32px auto;
            padding: 0 16px;
        }
        .hero {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 20px 24px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
            margin-bottom: 18px;
        }
        .hero h1 {
            margin: 0 0 8px;
            font-size: 28px;
        }
        .hero p {
            margin: 0;
            color: var(--muted);
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin: 18px 0;
        }
        .stat {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 14px 16px;
        }
        .stat .label {
            color: var(--muted);
            font-size: 13px;
            margin-bottom: 6px;
        }
        .stat .value {
            font-size: 24px;
            font-weight: 700;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 18px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
        }
        th, td {
            padding: 14px 12px;
            border-bottom: 1px solid #eee7da;
            text-align: right;
            vertical-align: top;
        }
        th {
            background: #f6f1e6;
            font-size: 13px;
        }
        tr:last-child td {
            border-bottom: none;
        }
        .devices {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }
        .device {
            background: #e6fffb;
            color: #115e59;
            border: 1px solid #a7f3d0;
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 12px;
        }
        .status {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
            background: #ecfdf5;
            color: #166534;
        }
        .status.expired, .status.blocked {
            background: #fff7ed;
            color: var(--warn);
        }
        .muted {
            color: var(--muted);
        }
        .empty {
            background: var(--panel);
            border: 1px dashed var(--line);
            border-radius: 18px;
            padding: 28px;
            text-align: center;
            color: var(--muted);
        }
        @media (max-width: 800px) {
            table, thead, tbody, th, td, tr {
                display: block;
            }
            thead {
                display: none;
            }
            tr {
                margin-bottom: 12px;
                border-bottom: 1px solid var(--line);
                background: var(--panel);
                border-radius: 16px;
                overflow: hidden;
            }
            td::before {
                content: attr(data-label);
                display: block;
                font-size: 12px;
                color: var(--muted);
                margin-bottom: 4px;
            }
        }
    </style>
</head>
<body>
    <div class="page">
        <section class="hero">
            <h1>لوحة التراخيص والأجهزة المفعلة</h1>
            <p>هذه الصفحة تعرض كل التراخيص مع عدد الأجهزة المرتبطة بكل مفتاح.</p>
        </section>

        <section class="stats">
            <div class="stat">
                <div class="label">عدد التراخيص</div>
                <div class="value">{{ licenses|length }}</div>
            </div>
            <div class="stat">
                <div class="label">إجمالي الأجهزة المفعلة</div>
                <div class="value">{{ total_devices }}</div>
            </div>
            <div class="stat">
                <div class="label">التراخيص النشطة</div>
                <div class="value">{{ active_licenses }}</div>
            </div>
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
                            <span class="device">{{ device_id }}</span>
                            {% endfor %}
                        </div>
                        {% else %}
                        <span class="muted">لا توجد أجهزة بعد</span>
                        {% endif %}
                    </td>
                    <td data-label="الاستخدام">{{ item.used_devices }} / {{ item.max_devices }}</td>
                    <td data-label="الانتهاء">{{ item.expire_date }}</td>
                    <td data-label="الإنشاء">{{ item.created_at or '-' }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="empty">لا توجد تراخيص محفوظة بعد.</div>
        {% endif %}
    </div>
</body>
</html>
"""


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
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
        """
    )
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
    cur.execute(
        """
        SELECT license_key, customer_name, device_ids, max_devices, status, expire_date
        FROM licenses
        WHERE license_key = ?
        """,
        (license_key,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def get_all_licenses():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT license_key, customer_name, device_ids, max_devices, status, expire_date, created_at
        FROM licenses
        ORDER BY id DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def serialize_license_row(row):
    if not row:
        return None

    license_key, customer_name, device_ids_json, max_devices, status, expire_date, *rest = row
    created_at = rest[0] if rest else ""
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
    cur.execute(
        """
        UPDATE licenses
        SET device_ids = ?
        WHERE license_key = ?
        """,
        (json.dumps(device_ids), license_key),
    )
    conn.commit()
    conn.close()


@app.route("/")
def home():
    return "License Server Running"


@app.route("/api/create-license", methods=["POST"])
def create_license():
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
    cur.execute(
        """
        INSERT INTO licenses (
            license_key, customer_name, device_ids, max_devices, status, expire_date, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            license_key,
            customer_name,
            json.dumps(initial_device_ids),
            max_devices,
            "active",
            expire_date,
            created_at,
        ),
    )
    conn.commit()
    conn.close()

    return jsonify(
        {
            "status": "success",
            "license_key": license_key,
            "customer_name": customer_name,
            "expire_date": expire_date,
            "max_devices": max_devices,
            "device_ids": initial_device_ids,
            "used_devices": len(initial_device_ids),
        }
    )


@app.route("/api/licenses", methods=["GET"])
def list_licenses():
    licenses = [serialize_license_row(row) for row in get_all_licenses()]
    return jsonify(
        {
            "status": "success",
            "count": len(licenses),
            "licenses": licenses,
        }
    )


@app.route("/admin/licenses", methods=["GET"])
def licenses_admin_page():
    licenses = [serialize_license_row(row) for row in get_all_licenses()]
    total_devices = sum(item["used_devices"] for item in licenses)
    active_licenses = sum(1 for item in licenses if item["status"] == "active")
    return render_template_string(
        LICENSES_ADMIN_TEMPLATE,
        licenses=licenses,
        total_devices=total_devices,
        active_licenses=active_licenses,
    )


@app.route("/api/license/<license_key>", methods=["GET"])
def get_license_details(license_key):
    row = get_license(license_key)
    if not row:
        return jsonify({"status": "invalid", "message": "License not found"}), 404

    device_ids_json = row[2]
    serializable_row = (
        row[0],
        row[1],
        device_ids_json,
        row[3],
        row[4],
        row[5],
        "",
    )
    return jsonify({"status": "success", "license": serialize_license_row(serializable_row)})


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

    _, customer_name, device_ids_json, max_devices, db_status, db_expire_date = lic

    if db_status != "active":
        return jsonify({"status": "blocked", "message": "License inactive"}), 403

    expire_date = datetime.strptime(db_expire_date, "%Y-%m-%d").date()
    today = datetime.today().date()

    if today > expire_date:
        return jsonify({"status": "expired", "message": "License expired"}), 403

    device_ids = json.loads(device_ids_json) if device_ids_json else []

    if device_id in device_ids:
        return jsonify(
            {
                "status": "active",
                "message": "Valid",
                "customer_name": customer_name,
                "expire_date": db_expire_date,
                "max_devices": max_devices,
                "used_devices": len(device_ids),
            }
        )

    if len(device_ids) >= max_devices:
        return jsonify(
            {
                "status": "denied",
                "message": "Device limit reached",
                "customer_name": customer_name,
                "expire_date": db_expire_date,
            }
        ), 403

    device_ids.append(device_id)
    save_device_ids(license_key, device_ids)

    return jsonify(
        {
            "status": "active",
            "message": "Activated",
            "customer_name": customer_name,
            "expire_date": db_expire_date,
            "max_devices": max_devices,
            "used_devices": len(device_ids),
        }
    )


init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
