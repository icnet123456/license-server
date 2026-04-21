from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)
DB_NAME = "licenses.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT UNIQUE NOT NULL,
        device_id TEXT,
        status TEXT NOT NULL,
        expire_date TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def get_license(license_key):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT license_key, device_id, status, expire_date FROM licenses WHERE license_key = ?", (license_key,))
    row = cur.fetchone()
    conn.close()
    return row


def update_device_id(license_key, device_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE licenses SET device_id = ? WHERE license_key = ?", (device_id, license_key))
    conn.commit()
    conn.close()


@app.route("/api/check-license", methods=["POST"])
def check_license():
    data = request.get_json()

    license_key = data.get("license_key")
    device_id = data.get("device_id")

    lic = get_license(license_key)

    if not lic:
        return jsonify({"status": "invalid", "message": "License not found"}), 404

    db_license_key, db_device_id, db_status, db_expire_date = lic

    if db_status != "active":
        return jsonify({"status": "blocked", "message": "License inactive"}), 403

    expire_date = datetime.strptime(db_expire_date, "%Y-%m-%d").date()
    today = datetime.today().date()

    if today > expire_date:
        return jsonify({"status": "expired", "message": "License expired"}), 403

    # أول تفعيل
    if not db_device_id:
        update_device_id(license_key, device_id)
        return jsonify({
            "status": "active",
            "message": "Activated",
            "expire_date": db_expire_date
        })

    # جهاز مختلف
    if db_device_id != device_id:
        return jsonify({
            "status": "denied",
            "message": "Used on another device"
        }), 403

    return jsonify({
        "status": "active",
        "message": "Valid",
        "expire_date": db_expire_date
    })


@app.route("/")
def home():
    return "License Server Running"


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
