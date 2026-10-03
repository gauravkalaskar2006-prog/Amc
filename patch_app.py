"""
Patch script: inserts new API routes into app.py
Run once, then restart the Flask server.
"""
import re

APP_FILE = r'c:\Users\user\OneDrive\Desktop\AMC_Project\app.py'

NEW_ROUTES = '''
# ---------------- DEPUTY COMMISSIONER: STATS + APPOINTMENTS ----------------
@app.route('/api/dc/stats')
def get_dc_stats():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM appointments")
    total = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE status IN ('Confirmed','Completed')")
    confirmed = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE status IN ('Rejected','Cancelled')")
    rejected = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE status LIKE '%Pending%'")
    pending = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE status='Rescheduled'")
    rescheduled = cursor.fetchone()['c']
    cursor.close()
    return jsonify({"total": total, "confirmed": confirmed, "rejected": rejected,
                    "pending": pending, "rescheduled": rescheduled})

@app.route('/api/dc/appointments')
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
def get_ac_stats():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM appointments")
    total = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE status IN ('Confirmed','Completed')")
    confirmed = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE status IN ('Rejected','Cancelled')")
    rejected = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE status LIKE '%Pending%'")
    pending = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE status='Rescheduled'")
    rescheduled = cursor.fetchone()['c']
    cursor.close()
    return jsonify({"total": total, "confirmed": confirmed, "rejected": rejected,
                    "pending": pending, "rescheduled": rescheduled})

@app.route('/api/ac/appointments')
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
def get_hod_stats():
    dept = session.get('department', '')
    cursor = mysql.connection.cursor()
    if dept:
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE department=%s", (dept,))
        total = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE department=%s AND status IN ('Confirmed','Completed')", (dept,))
        confirmed = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE department=%s AND status IN ('Rejected','Cancelled')", (dept,))
        rejected = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE department=%s AND status LIKE '%Pending%'", (dept,))
        pending = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE department=%s AND status='Rescheduled'", (dept,))
        rescheduled = cursor.fetchone()['c']
        cursor.execute("SELECT * FROM appointments WHERE department=%s ORDER BY created_at DESC", (dept,))
    else:
        cursor.execute("SELECT COUNT(*) as c FROM appointments"); total = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE status IN ('Confirmed','Completed')"); confirmed = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE status IN ('Rejected','Cancelled')"); rejected = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE status LIKE '%Pending%'"); pending = cursor.fetchone()['c']
        cursor.execute("SELECT COUNT(*) as c FROM appointments WHERE status='Rescheduled'"); rescheduled = cursor.fetchone()['c']
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

'''

with open(APP_FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# Check if already patched
if '/api/dc/stats' in content:
    print('[SKIP] Routes already present in app.py')
else:
    # Also fix session guards on dashboard routes
    content = content.replace(
        '@app.route("/assistant-commissioner-dashboard")\ndef assistant_dashboard():\n    return render_template("assistant_commissioner_dashboard.html")',
        '@app.route("/assistant-commissioner-dashboard")\ndef assistant_dashboard():\n    if \'role\' not in session or session[\'role\'] != \'assistant_commissioner\':\n        return redirect(url_for(\'home\'))\n    return render_template("assistant_commissioner_dashboard.html")'
    )
    content = content.replace(
        '@app.route(\"/hod-dashboard\")\ndef hod_dashboard():\n    return render_template(\"hod_dashboard.html\")',
        '@app.route(\"/hod-dashboard\")\ndef hod_dashboard():\n    if \'role\' not in session or session[\'role\'] != \'hod\':\n        return redirect(url_for(\'home\'))\n    return render_template(\"hod_dashboard.html\")'
    )
    content = content.replace(
        '@app.route(\"/pa-dashboard\")\ndef pa_dashboard():\n    return render_template(\"pa_dashboard.html\")',
        '@app.route(\"/pa-dashboard\")\ndef pa_dashboard():\n    if \'role\' not in session or session[\'role\'] != \'pa\':\n        return redirect(url_for(\'home\'))\n    return render_template(\"pa_dashboard.html\")'
    )
    # Also fix Deputy Commissioner session guard
    content = content.replace(
        '@app.route(\"/deputy-commissioner-dashboard\")\ndef deputy_commissioner_dashboard():\n    return render_template(\"deputy_commissioner_dashboard.html\",',
        '@app.route(\"/deputy-commissioner-dashboard\")\ndef deputy_commissioner_dashboard():\n    if \'role\' not in session or session[\'role\'] != \'deputy_commissioner\':\n        return redirect(url_for(\'home\'))\n    return render_template(\"deputy_commissioner_dashboard.html\",'
    )

    # Also fix officials SELECT to include department
    content = content.replace(
        'cursor.execute("SELECT id, full_name, emp_id, role, email FROM officials ORDER BY role")',
        'cursor.execute("SELECT id, full_name, emp_id, role, email, department FROM officials ORDER BY role")'
    )
    content = content.replace(
        "            'department': '',",
        "            'department': o.get('department') or '',",
        1
    )

    # Insert new routes before the FORWARD API section
    content = content.replace(
        '# ---------------- FORWARD API ----------------',
        NEW_ROUTES + '# ---------------- FORWARD API ----------------',
        1
    )

    with open(APP_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    print('[OK] app.py patched with new routes and session guards')

# Verify
with open(APP_FILE, 'r', encoding='utf-8') as f:
    c = f.read()
print('DC stats route present:', '/api/dc/stats' in c)
print('AC stats route present:', '/api/ac/stats' in c)
print('HOD stats route present:', '/api/hod/stats' in c)
print('PA date route present:', '/api/pa/appointments-by-date' in c)
print('AC session guard:', "session['role'] != 'assistant_commissioner'" in c)
print('HOD session guard:', "session['role'] != 'hod'" in c)
