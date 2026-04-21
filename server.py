from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime, timedelta
import uuid
import json

app = Flask(__name__)
DB_NAME = "licenses.db"


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
    conn.commit()
    conn.close()


def generate_license_key():
    return str(uuid.uuid4()).upper().replace("-", "")[:16]


def get_license(license_key):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT license_key, customer_name, device_ids, max_devices, status, expire_date
        FROM licenses
        WHERE license_key = ?
    """, (license_key,))
    row = cur.fetchone()
    conn.close()
    return row


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


@app.route("/")
def home():
    return "License Server Running"


@app.route("/api/create-license", methods=["POST"])
def create_license():
    data = request.get_json()

    customer_name = data.get("customer_name", "Unknown")
    days = int(data.get("days", 30))
    max_devices = int(data.get("max_devices", 1))

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

    return jsonify({
        "status": "success",
        "license_key": license_key,
        "customer_name": customer_name,
        "expire_date": expire_date,
        "max_devices": max_devices
    })


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

    db_license_key, customer_name, device_ids_json, max_devices, db_status, db_expire_date = lic

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
            "used_devices": len(device_ids)
        })

    if len(device_ids) >= max_devices:
        return jsonify({
            "status": "denied",
            "message": "Device limit reached",
            "customer_name": customer_name,
            "expire_date": db_expire_date
        }), 403

    device_ids.append(device_id)
    save_device_ids(license_key, device_ids)

    return jsonify({
        "status": "active",
        "message": "Activated",
        "customer_name": customer_name,
        "expire_date": db_expire_date,
        "max_devices": max_devices,
        "used_devices": len(device_ids)
    })


init_db()
