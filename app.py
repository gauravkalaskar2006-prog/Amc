import os
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import random
from datetime import datetime, timedelta
import MySQLdb.cursors
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load .env variables (optional)
load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION ---
app.secret_key = os.getenv("SECRET_KEY", "secret123")
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() in ('1', 'true', 'yes')

# MySQL Config (recommended to set via environment variables)
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD', '@Mypal0411')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB', 'amc_db')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# --- EMAIL CONFIG (Update with your credentials) ---
EMAIL_SENDER = os.getenv('EMAIL_SENDER', 'your_email@gmail.com')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', 'your_app_password_here')
EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'False').lower() in ('1', 'true', 'yes')
ANALYTICS_SCHEMA_READY = False


def role_required(*roles):
    """Decorator to require a specific role (or roles) for access."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if 'role' not in session:
                return jsonify({"success": False, "message": "Authentication required"}), 401
            if session.get('role') not in roles:
                return jsonify({"success": False, "message": "Access denied"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def login_required(fn):
    """Decorator to require a login for API endpoints."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session and 'citizen_id' not in session:
            return jsonify({"success": False, "message": "Authentication required"}), 401
        return fn(*args, **kwargs)
    return wrapper

def normalize_appt_time_for_db(value):
    """Convert UI time formats to DB-safe HH:MM:SS."""
    if value is None:
        raise ValueError("Time slot is required")

    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        hours = (total_seconds // 3600) % 24
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    if hasattr(value, "strftime"):
        return value.strftime("%H:%M:%S")

    text = str(value).strip()
    if not text:
        raise ValueError("Time slot is required")

    # Booking UI sends ranges like "10:00 AM - 11:00 AM"; store start time.
    if "-" in text:
        text = text.split("-", 1)[0].strip()

    for fmt in ("%I:%M %p", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M:%S")
        except ValueError:
            continue

    raise ValueError(f"Invalid time format: {value}")

def format_appt_time_for_ui(value):
    """Convert DB time values to readable strings for frontend/API output."""
    if value is None:
        return ""

    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        hours = (total_seconds // 3600) % 24
        minutes = (total_seconds % 3600) // 60
        return datetime.strptime(f"{hours:02d}:{minutes:02d}", "%H:%M").strftime("%I:%M %p")

    if hasattr(value, "strftime"):
        return value.strftime("%I:%M %p")

    text = str(value).strip()
    if not text:
        return ""
    if "AM" in text.upper() or "PM" in text.upper() or "-" in text:
        return text

    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).strftime("%I:%M %p")
        except ValueError:
            continue

    return text

def to_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default

def to_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def ensure_appointment_analytics_columns():
    """Ensure runtime analytics columns exist for decision-time reporting."""
    cursor = mysql.connection.cursor()
    altered = False
    try:
        cursor.execute("SHOW COLUMNS FROM appointments LIKE 'first_decision_at'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE appointments ADD COLUMN first_decision_at DATETIME NULL AFTER status")
            altered = True

        cursor.execute("SHOW COLUMNS FROM appointments LIKE 'status_updated_at'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE appointments ADD COLUMN status_updated_at DATETIME NULL AFTER first_decision_at")
            altered = True

        # Backfill timestamps for existing records so analytics is immediately usable.
        cursor.execute("""
            UPDATE appointments
            SET first_decision_at = COALESCE(first_decision_at, created_at)
            WHERE LOWER(status) IN ('confirmed', 'rejected', 'cancelled', 'completed', 'rescheduled')
              AND first_decision_at IS NULL
        """)
        if cursor.rowcount:
            altered = True

        cursor.execute("""
            UPDATE appointments
            SET status_updated_at = COALESCE(status_updated_at, created_at)
            WHERE status_updated_at IS NULL
        """)
        if cursor.rowcount:
            altered = True

        if altered:
            mysql.connection.commit()
    finally:
        cursor.close()

@app.before_request
def ensure_runtime_schema():
    global ANALYTICS_SCHEMA_READY
    if ANALYTICS_SCHEMA_READY:
        return
    try:
        ensure_appointment_analytics_columns()
        ANALYTICS_SCHEMA_READY = True
    except Exception as e:
        # Keep the app running even if schema migration cannot run.
        print(f"Schema ensure warning: {e}")

def build_commissioner_analytics(cursor):
    """Build advanced operational analytics for commissioner dashboard."""
    threshold_days = 3
    today = datetime.now().date()

    cursor.execute("""
        SELECT
            SUM(CASE WHEN TIMESTAMPDIFF(DAY, created_at, NOW()) <= 1 THEN 1 ELSE 0 END) AS d0_1,
            SUM(CASE WHEN TIMESTAMPDIFF(DAY, created_at, NOW()) BETWEEN 2 AND 3 THEN 1 ELSE 0 END) AS d2_3,
            SUM(CASE WHEN TIMESTAMPDIFF(DAY, created_at, NOW()) >= 4 THEN 1 ELSE 0 END) AS d4_plus,
            COUNT(*) AS total_pending
        FROM appointments
        WHERE LOWER(status) LIKE '%%pending%%'
    """)
    aging_row = cursor.fetchone() or {}
    pending_aging = {
        "d0_1": to_int(aging_row.get("d0_1")),
        "d2_3": to_int(aging_row.get("d2_3")),
        "d4_plus": to_int(aging_row.get("d4_plus")),
        "total": to_int(aging_row.get("total_pending")),
    }

    cursor.execute("""
        SELECT
            AVG(TIMESTAMPDIFF(MINUTE, created_at, first_decision_at)) AS avg_minutes,
            COUNT(*) AS samples
        FROM appointments
        WHERE first_decision_at IS NOT NULL
    """)
    avg_row = cursor.fetchone() or {}
    avg_minutes = to_float(avg_row.get("avg_minutes"))
    avg_hours = round(avg_minutes / 60, 2) if avg_minutes is not None else None
    avg_label = "N/A" if avg_hours is None else (f"{avg_hours} hrs" if avg_hours >= 1 else f"{round(avg_minutes, 1)} min")

    cursor.execute("""
        SELECT
            SUM(CASE WHEN LOWER(status) IN ('confirmed', 'completed') THEN 1 ELSE 0 END) AS accepted_count,
            SUM(CASE WHEN LOWER(status) IN ('rejected', 'cancelled') THEN 1 ELSE 0 END) AS rejected_count
        FROM appointments
    """)
    rates_row = cursor.fetchone() or {}
    accepted_count = to_int(rates_row.get("accepted_count"))
    rejected_count = to_int(rates_row.get("rejected_count"))
    total_decided = accepted_count + rejected_count
    approval_rate = round((accepted_count / total_decided) * 100, 1) if total_decided else 0.0
    rejection_rate = round((rejected_count / total_decided) * 100, 1) if total_decided else 0.0

    cursor.execute("""
        SELECT
            COALESCE(NULLIF(department, ''), 'Unassigned') AS department,
            COUNT(*) AS pending
        FROM appointments
        WHERE LOWER(status) LIKE '%%pending%%'
        GROUP BY COALESCE(NULLIF(department, ''), 'Unassigned')
        ORDER BY pending DESC, department ASC
        LIMIT 10
    """)
    backlog_rows = cursor.fetchall() or []
    backlog_by_department = [{
        "department": row.get("department") or "Unassigned",
        "pending": to_int(row.get("pending"))
    } for row in backlog_rows]

    cursor.execute("""
        SELECT
            COALESCE(NULLIF(reschedule_reason, ''), 'No reason provided') AS reason,
            COUNT(*) AS count
        FROM appointments
        WHERE status = 'Rescheduled'
        GROUP BY COALESCE(NULLIF(reschedule_reason, ''), 'No reason provided')
        ORDER BY count DESC, reason ASC
        LIMIT 8
    """)
    reschedule_rows = cursor.fetchall() or []
    reschedule_reasons = [{
        "reason": row.get("reason") or "No reason provided",
        "count": to_int(row.get("count"))
    } for row in reschedule_rows]

    cursor.execute("""
        SELECT appt_time, COUNT(*) AS count
        FROM appointments
        WHERE appt_time IS NOT NULL
          AND status NOT IN ('Rejected', 'Cancelled')
        GROUP BY appt_time
        ORDER BY appt_time ASC
    """)
    slot_rows = cursor.fetchall() or []
    slot_utilization = [{
        "slot": format_appt_time_for_ui(row.get("appt_time")),
        "count": to_int(row.get("count"))
    } for row in slot_rows]

    cursor.execute("""
        SELECT
            SUM(CASE WHEN TIMESTAMPDIFF(DAY, created_at, NOW()) > %s THEN 1 ELSE 0 END) AS breached_count,
            SUM(CASE WHEN TIMESTAMPDIFF(DAY, created_at, NOW()) <= %s THEN 1 ELSE 0 END) AS on_track_count
        FROM appointments
        WHERE status LIKE '%%Pending%%'
    """, (threshold_days, threshold_days))
    sla_row = cursor.fetchone() or {}
    breached_count = to_int(sla_row.get("breached_count"))
    on_track_count = to_int(sla_row.get("on_track_count"))

    cursor.execute("""
        SELECT id, token, visitor_name, department, created_at,
               TIMESTAMPDIFF(DAY, created_at, NOW()) AS age_days
        FROM appointments
        WHERE status LIKE '%%Pending%%'
          AND TIMESTAMPDIFF(DAY, created_at, NOW()) > %s
        ORDER BY created_at ASC
        LIMIT 10
    """, (threshold_days,))
    breach_items_rows = cursor.fetchall() or []
    breach_items = []
    for row in breach_items_rows:
        created_at = row.get("created_at")
        breach_items.append({
            "id": row.get("id"),
            "token": row.get("token"),
            "name": row.get("visitor_name"),
            "department": row.get("department") or "Unassigned",
            "ageDays": to_int(row.get("age_days")),
            "createdAt": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
        })

    cursor.execute("""
        SELECT DATE(created_at) AS day, COUNT(*) AS count
        FROM appointments
        WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 13 DAY)
        GROUP BY DATE(created_at)
        ORDER BY day ASC
    """)
    daily_rows = cursor.fetchall() or []
    daily_map = {}
    for row in daily_rows:
        day = row.get("day")
        key = day.isoformat() if hasattr(day, "isoformat") else str(day)
        daily_map[key] = to_int(row.get("count"))

    daily_trend = []
    start_day = today - timedelta(days=13)
    for i in range(14):
        day = start_day + timedelta(days=i)
        key = day.isoformat()
        daily_trend.append({
            "date": key,
            "label": day.strftime("%d %b"),
            "count": daily_map.get(key, 0)
        })

    cursor.execute("""
        SELECT
            DATE_SUB(DATE(created_at), INTERVAL WEEKDAY(created_at) DAY) AS week_start,
            COUNT(*) AS count
        FROM appointments
        WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 11 WEEK)
        GROUP BY DATE_SUB(DATE(created_at), INTERVAL WEEKDAY(created_at) DAY)
        ORDER BY week_start ASC
    """)
    weekly_rows = cursor.fetchall() or []
    weekly_map = {}
    for row in weekly_rows:
        week_start = row.get("week_start")
        key = week_start.isoformat() if hasattr(week_start, "isoformat") else str(week_start)
        weekly_map[key] = to_int(row.get("count"))

    weekly_trend = []
    current_week_start = today - timedelta(days=today.weekday())
    start_week = current_week_start - timedelta(weeks=11)
    for i in range(12):
        week_start = start_week + timedelta(weeks=i)
        key = week_start.isoformat()
        weekly_trend.append({
            "weekStart": key,
            "label": week_start.strftime("%d %b"),
            "count": weekly_map.get(key, 0)
        })

    return {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "pendingAging": pending_aging,
        "avgDecision": {
            "minutes": round(avg_minutes, 1) if avg_minutes is not None else None,
            "hours": avg_hours,
            "label": avg_label,
            "sampleSize": to_int(avg_row.get("samples"))
        },
        "rates": {
            "acceptedCount": accepted_count,
            "rejectedCount": rejected_count,
            "totalDecided": total_decided,
            "approvalRate": approval_rate,
            "rejectionRate": rejection_rate
        },
        "backlogByDepartment": backlog_by_department,
        "rescheduleReasons": reschedule_reasons,
        "slotUtilization": slot_utilization,
        "sla": {
            "thresholdDays": threshold_days,
            "breachedCount": breached_count,
            "onTrackCount": on_track_count,
            "breachedItems": breach_items
        },
        "trends": {
            "daily": daily_trend,
            "weekly": weekly_trend
        }
    }

def send_confirmation_email(to_email, citizen_name, token, appt_date, appt_time):
    """Send appointment confirmation email to citizen."""
    if not EMAIL_ENABLED or not to_email:
        return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"AMC Appointment Confirmed - Token {token}"
        msg['From'] = EMAIL_SENDER
        msg['To'] = to_email

        html_body = f"""
        <html><body>
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;border:1px solid #e0e0e0;border-radius:8px;">
            <div style="background:#2563eb;color:white;padding:20px;border-radius:8px 8px 0 0;text-align:center;">
                <h1 style="margin:0;">&#127970; Amravati Municipal Corporation</h1>
                <p style="margin:5px 0 0;">Appointment Confirmed</p>
            </div>
            <div style="padding:30px;">
                <p>Dear <strong>{citizen_name}</strong>,</p>
                <p>Your appointment with the Municipal Commissioner has been <strong style="color:green;">CONFIRMED</strong>.</p>
                <table style="width:100%;border-collapse:collapse;margin:20px 0;">
                    <tr style="background:#f3f4f6;"><td style="padding:10px;font-weight:bold;">Token Number</td><td style="padding:10px;">{token}</td></tr>
                    <tr><td style="padding:10px;font-weight:bold;">Date</td><td style="padding:10px;">{appt_date}</td></tr>
                    <tr style="background:#f3f4f6;"><td style="padding:10px;font-weight:bold;">Time Slot</td><td style="padding:10px;">{appt_time}</td></tr>
                </table>
                <p style="color:#666;">Please bring a valid government ID and arrive 15 minutes before your appointment time.</p>
                <p>For queries, contact: <a href="mailto:info@amc.gov.in">info@amc.gov.in</a></p>
            </div>
            <div style="background:#f3f4f6;padding:10px;text-align:center;border-radius:0 0 8px 8px;font-size:12px;color:#666;">
                &copy; 2026 Amravati Municipal Corporation | Digital India
            </div>
        </div>
        </body></html>
        """
        msg.attach(MIMEText(html_body, 'html'))

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Email send failed: {e}")

# ---------------- NAVIGATION ROUTES ----------------
@app.route("/")
def home():
    return render_template("main_home.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/services")
def services():
    return render_template("services.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

# ---------------- DASHBOARDS ----------------
@app.route("/commissioner-dashboard")
def commissioner_dashboard():
    if 'role' in session and session['role'] == 'commissioner':
        return render_template("commissioner_dashboard.html")
    return redirect(url_for('home'))

@app.route("/assistant-commissioner-dashboard")
def assistant_dashboard():
    if 'role' not in session or session['role'] != 'assistant_commissioner':
        return redirect(url_for('home'))
    return render_template("assistant_commissioner_dashboard.html")

@app.route("/deputy-commissioner-dashboard")
def deputy_commissioner_dashboard():
    if 'role' not in session or session['role'] != 'deputy_commissioner':
        return redirect(url_for('home'))
    return render_template("deputy_commissioner_dashboard.html", hod={"name": session.get('name')})

@app.route("/hod-dashboard")
def hod_dashboard():
    if 'role' not in session or session['role'] != 'hod':
        return redirect(url_for('home'))
    return render_template("hod_dashboard.html")

@app.route("/pa-dashboard")
def pa_dashboard():
    if 'role' not in session or session['role'] != 'pa':
        return redirect(url_for('home'))
    return render_template("pa_dashboard.html")

@app.route("/system-manager-dashboard")
def system_manager():
    if 'role' in session and session['role'] == 'system_manager':
        return render_template("system_manager.html")
    return redirect(url_for('home'))

@app.route("/people-dashboard")
def people_dashboard():
    if 'citizen_id' not in session:
        return redirect(url_for("home"))
    return render_template("people_dashboard.html")


# ---------------- OFFICIAL LOGIN (Main Page) ----------------
@app.route('/official-login', methods=['POST'])
def official_login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        role = data.get('role')
        emp_id = data.get('emp_id')
        password = data.get('password')

        if not role or not emp_id or not password:
            return jsonify({"success": False, "message": "Missing credentials"}), 400

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM officials WHERE emp_id = %s AND role = %s", (emp_id, role))
        user = cursor.fetchone()
        cursor.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['full_name']
            session['email'] = user.get('email', '')
            return jsonify({"success": True, "redirect": f"/{role.replace('_', '-')}-dashboard"})
        else:
            return jsonify({"success": False, "message": "Invalid Credentials"}), 401
    except Exception as e:
        print(f"Official login error: {str(e)}")
        return jsonify({"success": False, "message": "Server error. Please try again."}), 500

# ---------------- CITIZEN REGISTRATION ----------------
@app.route("/citizen-register", methods=["GET", "POST"])
def citizen_register():
    if request.method == "POST":
        name = request.form.get("name")
        mobile = request.form.get("mobile")
        password = request.form.get("password")

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM citizens WHERE mobile = %s", (mobile,))
        existing = cursor.fetchone()

        if existing:
            return "Mobile number already registered!", 400

        hashed_pw = generate_password_hash(password)

        cursor.execute("INSERT INTO citizens (full_name, mobile, password) VALUES (%s, %s, %s)",
                       (name, mobile, hashed_pw))
        mysql.connection.commit()
        cursor.close()

        return redirect(url_for("home"))

    return render_template("citizen_register.html")

# ---------------- CITIZEN LOGIN ----------------
@app.route("/citizen-login", methods=["POST"])
def citizen_login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        mobile = data.get("mobile")
        password = data.get("password")

        if not mobile or not password:
            return jsonify({"success": False, "message": "Missing credentials"}), 400

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM citizens WHERE mobile = %s", (mobile,))
        user = cursor.fetchone()
        cursor.close()

        if user and check_password_hash(user['password'], password):
            session['citizen_id'] = user['id']
            session['citizen_name'] = user['full_name']
            return jsonify({"success": True, "message": "Login successful"})
        else:
            return jsonify({"success": False, "message": "Invalid Mobile or Password"}), 401
    except Exception as e:
        print(f"Citizen login error: {str(e)}")
        return jsonify({"success": False, "message": "Server error. Please try again."}), 500

# ---------------- FORGOT PASSWORD ----------------
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        return "Password reset link sent (Simulation)"
    return render_template('forgot_password.html')

# ---------------- RESET PASSWORD ----------------
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    return render_template('reset_password.html')

# ---------------- CITIZEN: BOOK APPOINTMENT ----------------
@app.route('/api/citizen/book', methods=['POST'])
@login_required
def book_appointment():
    if 'citizen_id' not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    token = "AMC-" + str(random.randint(10000, 99999))

    required_fields = ["name", "mobile", "department", "date", "time", "reason", "photo"]
    missing = [field for field in required_fields if not str(data.get(field, "")).strip()]
    if missing:
        return jsonify({"success": False, "message": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        people_count = int(data.get("people", 1))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid people count"}), 400

    if people_count < 1:
        return jsonify({"success": False, "message": "People count must be at least 1"}), 400

    try:
        db_time = normalize_appt_time_for_db(data.get("time"))
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400

    member_names_list = data.get('memberNames', [])
    if not isinstance(member_names_list, list):
        member_names_list = []
    member_names_str = ', '.join([str(m).strip() for m in member_names_list if str(m).strip()])

    cursor = mysql.connection.cursor()
    try:
        cursor.execute("""
            INSERT INTO appointments
            (citizen_id, token, visitor_name, mobile, department, appt_date, appt_time,
             reason, people_count, other_visitors, photo_data, status, leader_aadhaar, member_names, status_updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pending PA Review', %s, %s, NOW())
        """, (
            session['citizen_id'], token, data['name'], data['mobile'], data['department'],
            data['date'], db_time, data['reason'], people_count,
            data.get('otherVisitors', ''), data['photo'],
            data.get('leaderAadhaar', ''), member_names_str
        ))
        mysql.connection.commit()
        return jsonify({"success": True, "token": token})
    except Exception as e:
        mysql.connection.rollback()
        print(f"Booking error: {e}")
        return jsonify({"success": False, "message": "Failed to book appointment. Please verify date/time and try again."}), 500
    finally:
        cursor.close()

# ---------------- CITIZEN: GET MY APPOINTMENTS ----------------
@app.route('/api/citizen/appointments')
@login_required
def my_appointments():
    if 'citizen_id' not in session:
        return jsonify([])

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM appointments WHERE citizen_id = %s ORDER BY created_at DESC", (session['citizen_id'],))
    appointments = cursor.fetchall()
    cursor.close()

    data = []
    for appt in appointments:
        data.append({
            "id": appt['id'],
            "token": appt['token'],
            "department": appt['department'],
            "date": str(appt['appt_date']),
            "time": format_appt_time_for_ui(appt.get('appt_time')),
            "status": appt['status'],
            "photo": appt['photo_data'],
            "reason": appt['reason'],
            "peopleCount": appt['people_count'],
            "otherVisitors": appt.get('other_visitors', ''),
            "memberNames": appt.get('member_names', ''),
            "leaderAadhaar": appt.get('leader_aadhaar', ''),
            "rescheduleReason": appt.get('reschedule_reason', ''),
            "rejectionReason": appt.get('rejection_reason', ''),
        })
    return jsonify(data)

# ---------------- CITIZEN: GET PROFILE ----------------
@app.route('/api/citizen/profile')
@login_required
def get_citizen_profile():
    if 'citizen_id' not in session: return jsonify({})

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT full_name, mobile, address, profile_pic FROM citizens WHERE id=%s", (session['citizen_id'],))
    user = cursor.fetchone()
    cursor.close()

    return jsonify({
        "name": user['full_name'],
        "mobile": user['mobile'],
        "address": user['address'],
        "photo": user['profile_pic']
    })

# ---------------- OFFICIAL REGISTER (System Manager Only) ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    # Restrict to System Manager session only
    if 'role' not in session or session['role'] != 'system_manager':
        return redirect(url_for('home'))

    if request.method == "POST":
        full_name = request.form.get("full_name")
        emp_id = request.form.get("emp_id")
        role = request.form.get("role")
        email = request.form.get("email")
        password = request.form.get("password")

        if not all([full_name, emp_id, role, email, password]):
            return render_template("create_account_all.html", error="All fields are required")

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT id FROM officials WHERE emp_id = %s", (emp_id,))
        if cursor.fetchone():
            cursor.close()
            return render_template("create_account_all.html", error=f"Employee ID '{emp_id}' is already registered!")

        hashed_pw = generate_password_hash(password)

        try:
            cursor.execute("""
                INSERT INTO officials (full_name, emp_id, role, email, password)
                VALUES (%s, %s, %s, %s, %s)
            """, (full_name, emp_id, role, email, hashed_pw))
            mysql.connection.commit()
            return redirect(url_for("system_manager"))
        except Exception as e:
            err_msg = str(e)
            if "Duplicate entry" in err_msg:
                err_msg = f"Employee ID '{emp_id}' or Email is already taken."
            return render_template("create_account_all.html", error=err_msg)
        finally:
            cursor.close()

    return render_template("create_account_all.html")

# ---------------- SYSTEM MANAGER: GET ALL OFFICIALS ----------------
@app.route('/api/system/officials', methods=['GET'])
@role_required('system_manager')
def get_all_officials():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id, full_name, emp_id, role, email, department FROM officials ORDER BY role")
    officials = cursor.fetchall()
    cursor.close()
    result = []
    for o in officials:
        result.append({
            'id': o['id'],
            'name': o['full_name'],
            'username': o['emp_id'],
            'full_name': o['full_name'],
            'emp_id': o['emp_id'],
            'role': o['role'],
            'email': o['email'] or '',
            'department': o.get('department') or '',
        })
    return jsonify({'officials': result, 'total': len(result)})

# ---------------- SYSTEM MANAGER: CREATE OFFICIAL ----------------
@app.route('/api/system/officials/create', methods=['POST'])
@role_required('system_manager')
def create_official():
    data = request.get_json()
    # Accept both aliased and original field names
    full_name = (data.get('name') or data.get('full_name', '')).strip()
    emp_id = (data.get('username') or data.get('emp_id', '')).strip()
    role = data.get('role', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()

    if not all([full_name, emp_id, role, password]):
        return jsonify({"success": False, "msg": "Name, username, role and password are required"}), 400

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id FROM officials WHERE emp_id = %s", (emp_id,))
    if cursor.fetchone():
        cursor.close()
        return jsonify({"success": False, "msg": f"Username '{emp_id}' already exists"}), 400

    hashed_pw = generate_password_hash(password)
    try:
        cursor.execute("""
            INSERT INTO officials (full_name, emp_id, role, email, password)
            VALUES (%s, %s, %s, %s, %s)
        """, (full_name, emp_id, role, email, hashed_pw))
        mysql.connection.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500
    finally:
        cursor.close()

# ---------------- SYSTEM MANAGER: UPDATE OFFICIAL ----------------
@app.route('/api/system/officials/update', methods=['POST'])
@role_required('system_manager')
def update_official():
    data = request.get_json()
    official_id = data.get('id')
    # Accept both aliased and original field names
    full_name = (data.get('name') or data.get('full_name', '')).strip()
    emp_id = (data.get('username') or data.get('emp_id', '')).strip()
    role = data.get('role', '').strip()
    email = data.get('email', '').strip()

    if not official_id:
        return jsonify({"success": False, "msg": "Missing official ID"}), 400

    cursor = mysql.connection.cursor()
    try:
        cursor.execute("""
            UPDATE officials SET full_name=%s, emp_id=%s, role=%s, email=%s WHERE id=%s
        """, (full_name, emp_id, role, email, official_id))
        mysql.connection.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500
    finally:
        cursor.close()

# ---------------- SYSTEM MANAGER: RESET PASSWORD ----------------
@app.route('/api/system/reset-password', methods=['POST'])
@role_required('system_manager')
def reset_official_password():
    data = request.get_json()
    official_id = data.get('id')
    emp_id_username = data.get('username', '')
    new_password = data.get('password', '')

    if not new_password or len(new_password) < 8:
        return jsonify({"success": False, "msg": "Password must be at least 8 characters"}), 400

    hashed_pw = generate_password_hash(new_password)
    cursor = mysql.connection.cursor()
    try:
        if official_id:
            cursor.execute("UPDATE officials SET password=%s WHERE id=%s", (hashed_pw, official_id))
        else:
            cursor.execute("UPDATE officials SET password=%s WHERE emp_id=%s", (hashed_pw, emp_id_username))
        mysql.connection.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500
    finally:
        cursor.close()

# ---------------- SYSTEM MANAGER: DELETE OFFICIAL ----------------
@app.route('/api/system/officials/delete', methods=['POST'])
@role_required('system_manager')
def delete_official():
    data = request.get_json() or {}
    try:
        official_id = int(data.get('id', 0))
    except (TypeError, ValueError):
        return jsonify({"success": False, "msg": "Invalid official ID"}), 400

    if official_id <= 0:
        return jsonify({"success": False, "msg": "Missing ID"}), 400

    # Prevent deleting the currently logged-in system manager
    if session.get('user_id') == official_id:
        return jsonify({"success": False, "msg": "Cannot delete the logged-in account"}), 400

    cursor = mysql.connection.cursor()
    try:
        cursor.execute("DELETE FROM officials WHERE id=%s", (official_id,))
        if cursor.rowcount == 0:
            return jsonify({"success": False, "msg": "Official not found"}), 404
        mysql.connection.commit()
        return jsonify({"success": True})
    except Exception as e:
        # Log error server-side, but return a safe message
        print(f"Error deleting official {official_id}: {e}")
        return jsonify({"success": False, "msg": "Error deleting official"}), 500
    finally:
        cursor.close()

# ---------------- COMMISSIONER: GET REAL STATS ----------------
@app.route('/api/commissioner/stats')
# @role_required('commissioner')
def get_commissioner_stats():
    cursor = mysql.connection.cursor()

    # Total all-time appointments
    cursor.execute("SELECT COUNT(*) as count FROM appointments")
    total = cursor.fetchone()['count']

    # Accepted includes confirmed and completed.
    cursor.execute("SELECT COUNT(*) as count FROM appointments WHERE LOWER(status) IN ('confirmed', 'completed')")
    accepted = cursor.fetchone()['count']

    # Rejected/Cancelled
    cursor.execute("SELECT COUNT(*) as count FROM appointments WHERE LOWER(status) IN ('rejected', 'cancelled')")
    rejected = cursor.fetchone()['count']

    # Rescheduled
    cursor.execute("SELECT COUNT(*) as count FROM appointments WHERE LOWER(status) = 'rescheduled'")
    rescheduled = cursor.fetchone()['count']

    # Pending
    cursor.execute("SELECT COUNT(*) as count FROM appointments WHERE LOWER(status) LIKE '%%pending%%'")
    pending = cursor.fetchone()['count']

    # Recent appointments list
    cursor.execute("""
        SELECT * FROM appointments
        ORDER BY created_at DESC
        LIMIT 50
    """)
    rows = cursor.fetchall()

    analytics = build_commissioner_analytics(cursor)
    cursor.close()

    appt_list = []
    for r in rows:
        appt_list.append({
            "id": r['id'],
            "name": r['visitor_name'],
            "dept": r['department'],
            "detail": r['reason'],
            "time": format_appt_time_for_ui(r.get('appt_time')),
            "token": r['token'],
            "status": r['status'],
            "date": str(r['appt_date']),
            "createdAt": r['created_at'].isoformat() if hasattr(r.get('created_at'), "isoformat") else str(r.get('created_at')),
            "rescheduleReason": r.get('reschedule_reason', ''),
            "rejectionReason": r.get('rejection_reason', ''),
        })

    return jsonify({
        "total": total,
        "accepted": accepted,
        "rejected": rejected,
        "rescheduled": rescheduled,
        "pending": pending,
        "appointments": appt_list,
        "analytics": analytics
    })

# ---------------- COMMISSIONER: GET TOKEN LISTS ----------------
@app.route('/api/commissioner/tokens')
@role_required('commissioner')
def get_commissioner_tokens():
    cursor = mysql.connection.cursor()

    cursor.execute("""
        SELECT id, token, visitor_name, department, appt_date, appt_time, status, reschedule_reason, rejection_reason
        FROM appointments WHERE status = 'Confirmed'
        ORDER BY appt_date DESC
    """)
    confirmed = cursor.fetchall()

    cursor.execute("""
        SELECT id, token, visitor_name, department, appt_date, appt_time, status, reschedule_reason, rejection_reason
        FROM appointments WHERE status = 'Rescheduled'
        ORDER BY appt_date DESC
    """)
    rescheduled = cursor.fetchall()

    cursor.execute("""
        SELECT id, token, visitor_name, department, appt_date, appt_time, status, reschedule_reason, rejection_reason
        FROM appointments WHERE status LIKE '%%Pending%%'
        ORDER BY created_at DESC
    """)
    pending = cursor.fetchall()

    cursor.execute("""
        SELECT id, token, visitor_name, department, appt_date, appt_time, status, reschedule_reason, rejection_reason
        FROM appointments WHERE status IN ('Rejected', 'Cancelled')
        ORDER BY created_at DESC
    """)
    rejected = cursor.fetchall()

    cursor.close()

    def fmt(rows):
        out = []
        for r in rows:
            out.append({
                "id": r['id'],
                "token": r['token'],
                "name": r['visitor_name'],
                "dept": r['department'],
                "date": str(r['appt_date']),
                "time": format_appt_time_for_ui(r.get('appt_time')),
                "status": r['status'],
                "rescheduleReason": r.get('reschedule_reason', ''),
                "rejectionReason": r.get('rejection_reason', ''),
            })
        return out

    return jsonify({
        "confirmed": fmt(confirmed),
        "rescheduled": fmt(rescheduled),
        "pending": fmt(pending),
        "rejected": fmt(rejected)
    })

# ---------------- PA: GET APPOINTMENTS ----------------
@app.route('/api/pa/appointments')
@role_required('pa')
def get_all_appointments():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM appointments ORDER BY created_at DESC")
    rows = cursor.fetchall()
    cursor.close()

    data = []
    for r in rows:
        data.append({
            "id": r['id'],
            "token": r['token'],
            "name": r['visitor_name'],
            "department": r['department'],
            "reason": r['reason'],
            "date": str(r['appt_date']),
            "time": format_appt_time_for_ui(r.get('appt_time')),
            "status": r['status'],
            "rescheduleReason": r.get('reschedule_reason', ''),
            "rejectionReason": r.get('rejection_reason', ''),
            "photo": r['photo_data'],
            "memberNames": r.get('member_names', ''),
            "peopleCount": r.get('people_count', 1),
        })
    return jsonify(data)

# ---------------- STATUS NORMALIZER (helper) ----------------
def normalize_status(value):
    if not value:
        return value
    v = str(value).strip().lower()
    mapping = {
        'confirmed': 'Confirmed',
        'cancelled': 'Rejected',
        'rejected': 'Rejected',
        'rescheduled': 'Rescheduled',
        'pending pa review': 'Pending PA Review',
        'pending': 'Pending'
    }
    return mapping.get(v, value)


# ---------------- PA / ALL OFFICIALS: UPDATE STATUS ----------------
@app.route('/api/pa/update', methods=['POST'])
@role_required('pa', 'commissioner', 'assistant_commissioner', 'deputy_commissioner', 'hod')
def update_appt_status():
    data = request.get_json(silent=True) or {}
    appt_id = data.get('id')
    status = normalize_status(data.get('status'))

    if not appt_id or not status:
        return jsonify({"success": False, "message": "Missing appointment id or status"}), 400

    cursor = mysql.connection.cursor()
    try:
        if status == 'Rescheduled':
            new_date = data.get('date')
            new_time = data.get('time')
            reason = data.get('rescheduleReason', '')

            if not new_date or not new_time:
                return jsonify({"success": False, "message": "Reschedule date and time are required"}), 400

            try:
                db_time = normalize_appt_time_for_db(new_time)
            except ValueError as e:
                return jsonify({"success": False, "message": str(e)}), 400

            cursor.execute("""
                UPDATE appointments
                SET status=%s, appt_date=%s, appt_time=%s, reschedule_reason=%s,
                    status_updated_at=NOW(),
                    first_decision_at=COALESCE(first_decision_at, NOW())
                WHERE id=%s
            """, (status, new_date, db_time, reason, appt_id))

        elif status in ('Rejected', 'Cancelled'):
            rejection_reason = data.get('rejectionReason', '')
            cursor.execute("""
                UPDATE appointments
                SET status=%s, rejection_reason=%s,
                    status_updated_at=NOW(),
                    first_decision_at=COALESCE(first_decision_at, NOW())
                WHERE id=%s
            """, (status, rejection_reason, appt_id))

        elif status == 'Confirmed':
            cursor.execute("""
                UPDATE appointments
                SET status=%s,
                    status_updated_at=NOW(),
                    first_decision_at=COALESCE(first_decision_at, NOW())
                WHERE id=%s
            """, (status, appt_id))
            # Fetch appointment + citizen email for notification
            cursor.execute("""
                SELECT a.token, a.visitor_name, a.appt_date, a.appt_time, c.full_name, c.mobile
                FROM appointments a
                LEFT JOIN citizens c ON a.citizen_id = c.id
                WHERE a.id = %s
            """, (appt_id,))
            appt = cursor.fetchone()
            if appt:
                # Try to get citizen email if available
                cursor.execute("SELECT email FROM citizens WHERE mobile = %s", (appt.get('mobile', ''),))
                cit = cursor.fetchone()
                citizen_email = cit['email'] if cit and cit.get('email') else None
                send_confirmation_email(
                    citizen_email,
                    appt['visitor_name'],
                    appt['token'],
                    str(appt['appt_date']),
                    format_appt_time_for_ui(appt.get('appt_time'))
                )
        else:
            cursor.execute("""
                UPDATE appointments
                SET status=%s, status_updated_at=NOW()
                WHERE id=%s
            """, (status, appt_id))

        mysql.connection.commit()
        return jsonify({"success": True})
    except Exception as e:
        mysql.connection.rollback()
        print(f"Appointment update error: {e}")
        return jsonify({"success": False, "message": "Failed to update appointment"}), 500
    finally:
        cursor.close()

# ---------------- COMMISSIONER/HOD: GET TASKS ----------------
@app.route("/api/tasks")
@role_required('commissioner', 'assistant_commissioner', 'deputy_commissioner', 'hod')
def get_tasks():
    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT * FROM appointments
        WHERE status IN ('Confirmed', 'Completed')
        ORDER BY appt_date DESC
    """)
    rows = cursor.fetchall()
    cursor.close()

    tasks = []
    for r in rows:
        tasks.append({
            "id": r['id'],
            "token": r['token'],
            "name": r['visitor_name'],
            "department": r['department'],
            "reason": r['reason'],
            "detail": r['reason'],
            "status": r['status'],
            "date": str(r['appt_date'])
        })
    return jsonify(tasks)

# ---------------- MARK TASK COMPLETE ----------------
@app.route("/api/task/complete", methods=["POST"])
@role_required('commissioner', 'assistant_commissioner', 'deputy_commissioner', 'hod')
def complete_task():
    data = request.get_json() or {}
    ids = data.get("ids")

    if not ids:
        single = data.get("id")
        if single is None:
            return jsonify({"success": False, "error": "Missing id(s)"}), 400
        ids = [single]

    ids = list(ids)
    placeholders = ",".join(["%s"] * len(ids))

    cursor = mysql.connection.cursor()
    cursor.execute(
        f"""
        UPDATE appointments
        SET status='Completed',
            status_updated_at=NOW(),
            first_decision_at=COALESCE(first_decision_at, NOW())
        WHERE id IN ({placeholders})
        """,
        tuple(ids)
    )
    mysql.connection.commit()
    cursor.close()

    return jsonify({"success": True})


# ---------------- DEPUTY COMMISSIONER: STATS + APPOINTMENTS ----------------
@app.route('/api/dc/stats')
@role_required('deputy_commissioner')
def get_dc_stats():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM appointments")
    total = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE LOWER(status) IN ('confirmed','completed')")
    confirmed = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE LOWER(status) IN ('rejected','cancelled')")
    rejected = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE LOWER(status) LIKE '%%pending%%'")
    pending = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE LOWER(status) = 'rescheduled'")
    rescheduled = cursor.fetchone()['c']
    cursor.close()
    return jsonify({"total": total, "confirmed": confirmed, "rejected": rejected,
                    "pending": pending, "rescheduled": rescheduled})

@app.route('/api/dc/appointments')
@role_required('deputy_commissioner')
def get_dc_appointments():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM appointments ORDER BY created_at DESC")
    rows = cursor.fetchall()
    cursor.close()
    data = []
    for r in rows:
        data.append({
            "id": r['id'], "token": r['token'], "name": r['visitor_name'],
            "department": r['department'], "reason": r['reason'],
            "date": str(r['appt_date']),
            "time": format_appt_time_for_ui(r.get('appt_time')),
            "status": r['status'],
            "peopleCount": r.get('people_count', 1),
            "rescheduleReason": r.get('reschedule_reason', ''),
            "rejectionReason": r.get('rejection_reason', ''),
        })
    return jsonify(data)

# ---------------- ASSISTANT COMMISSIONER: STATS + APPOINTMENTS ----------------
@app.route('/api/ac/stats')
@role_required('assistant_commissioner')
def get_ac_stats():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM appointments")
    total = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE LOWER(status) IN ('confirmed','completed')")
    confirmed = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE LOWER(status) IN ('rejected','cancelled')")
    rejected = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE LOWER(status) LIKE '%%pending%%'")
    pending = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE LOWER(status) = 'rescheduled'")
    rescheduled = cursor.fetchone()['c']
    cursor.close()
    return jsonify({"total": total, "confirmed": confirmed, "rejected": rejected,
                    "pending": pending, "rescheduled": rescheduled})

@app.route('/api/ac/appointments')
@role_required('assistant_commissioner')
def get_ac_appointments():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM appointments ORDER BY created_at DESC")
    rows = cursor.fetchall()
    cursor.close()
    data = []
    for r in rows:
        data.append({
            "id": r['id'], "token": r['token'], "name": r['visitor_name'],
            "department": r['department'], "reason": r['reason'],
            "date": str(r['appt_date']),
            "time": format_appt_time_for_ui(r.get('appt_time')),
            "status": r['status'],
            "peopleCount": r.get('people_count', 1),
            "rescheduleReason": r.get('reschedule_reason', ''),
            "rejectionReason": r.get('rejection_reason', ''),
        })
    return jsonify(data)

# ---------------- HOD: STATS (department-filtered) ----------------
@app.route('/api/hod/stats')
@role_required('hod')
def get_hod_stats():
    dept = session.get('department', '')
    cursor = mysql.connection.cursor()
    if dept:
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE department=%s", (dept,))
        total = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE department=%s AND LOWER(status) IN ('confirmed','completed')", (dept,))
        confirmed = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE department=%s AND LOWER(status) IN ('rejected','cancelled')", (dept,))
        rejected = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE department=%s AND LOWER(status) LIKE '%%pending%%'", (dept,))
        pending = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE department=%s AND LOWER(status) = 'rescheduled'", (dept,))
        rescheduled = cursor.fetchone()['c']
        cursor.execute("SELECT * FROM appointments WHERE department=%s ORDER BY created_at DESC", (dept,))
    else:
        cursor.execute("SELECT COUNT(*) as c FROM appointments"); total = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE LOWER(status) IN ('confirmed','completed')"); confirmed = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE LOWER(status) IN ('rejected','cancelled')"); rejected = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE LOWER(status) LIKE '%%pending%%'"); pending = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE LOWER(status) = 'rescheduled'"); rescheduled = cursor.fetchone()['c']
        cursor.execute("SELECT * FROM appointments ORDER BY created_at DESC")
    rows = cursor.fetchall()
    cursor.close()
    appt_list = [{"id": r['id'], "token": r['token'], "name": r['visitor_name'],
                  "department": r['department'], "reason": r['reason'],
                  "date": str(r['appt_date']), "time": format_appt_time_for_ui(r.get('appt_time')),
                  "status": r['status']} for r in rows]
    return jsonify({"total": total, "confirmed": confirmed, "rejected": rejected,
                    "pending": pending, "rescheduled": rescheduled,
                    "department": dept, "appointments": appt_list})

# ---------------- PA: APPOINTMENTS BY DATE ----------------
@app.route('/api/pa/appointments-by-date')
@role_required('pa')
def get_appointments_by_date():
    date_str = request.args.get('date', '')
    cursor = mysql.connection.cursor()
    if date_str:
        cursor.execute("SELECT * FROM appointments WHERE appt_date=%s ORDER BY appt_time ASC", (date_str,))
    else:
        cursor.execute("SELECT * FROM appointments WHERE appt_date=CURDATE() ORDER BY appt_time ASC")
    rows = cursor.fetchall()
    cursor.close()
    data = []
    for r in rows:
        data.append({
            "id": r['id'], "token": r['token'], "name": r['visitor_name'],
            "department": r['department'], "reason": r['reason'],
            "date": str(r['appt_date']), "time": format_appt_time_for_ui(r.get('appt_time')),
            "status": r['status'], "peopleCount": r.get('people_count', 1),
        })
    return jsonify(data)

# ---------------- FORWARD API ----------------
@app.route("/api/forward", methods=["POST"])
@role_required('commissioner', 'assistant_commissioner', 'deputy_commissioner', 'hod')
def forward_item():
    data = request.get_json()
    item_id = data.get("id")
    dept = data.get("dept")

    if not item_id or not dept:
        return jsonify({"success": False, "error": "Missing data"}), 400

    cursor = mysql.connection.cursor()
    cursor.execute("""
        UPDATE appointments
        SET department=%s, status='Completed',
            status_updated_at=NOW(),
            first_decision_at=COALESCE(first_decision_at, NOW())
        WHERE id=%s
    """, (dept, item_id))
    mysql.connection.commit()
    cursor.close()

    return jsonify({"success": True, "message": "Item forwarded and marked as Completed"})

# ---------------- FEEDBACK ----------------
@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        category = request.form.get("category")
        message = request.form.get("message")

        cursor = mysql.connection.cursor()
        cursor.execute("INSERT INTO feedback (name, email, category, message) VALUES (%s,%s,%s,%s)",
                       (name, email, category, message))
        mysql.connection.commit()
        cursor.close()

        return "<h3>Thank you! Feedback submitted. <a href='/'>Go Home</a></h3>"

    return render_template("feedback.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

if __name__ == "__main__":
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ('1', 'true', 'yes')
    app.run(host='0.0.0.0', debug=debug_mode)
