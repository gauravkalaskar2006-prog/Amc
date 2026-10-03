"""
AMC DB Fix Script - Run once to fix schema and re-seed accounts
"""
import os

import MySQLdb
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

conn = MySQLdb.connect(
    host=os.getenv('MYSQL_HOST', 'localhost'),
    user=os.getenv('MYSQL_USER', 'root'),
    passwd=os.getenv('MYSQL_PASSWORD', '@Mypal0411'),
    db=os.getenv('MYSQL_DB', 'amc_db')
)
cur = conn.cursor()

print("=== AMC DATABASE FIX ===\n")

# 1. Add department column to officials if missing
try:
    cur.execute("ALTER TABLE officials ADD COLUMN department VARCHAR(255) DEFAULT '' AFTER email")
    conn.commit()
    print("[OK] Added department column to officials table")
except Exception as e:
    print(f"[SKIP] department column: {e}")

# 2. Drop unique constraint on emp_id (it blocks multiple roles with same emp_id)
try:
    cur.execute("SHOW INDEX FROM officials WHERE Key_name = 'emp_id'")
    if cur.fetchone():
        cur.execute("ALTER TABLE officials DROP INDEX emp_id")
        conn.commit()
        print("[OK] Dropped unique index on emp_id")
    else:
        print("[INFO] emp_id unique index already removed")
except Exception as e:
    print(f"[SKIP] emp_id index: {e}")

# 2b. Drop unique constraint on role (so multiple users can share the same role)
try:
    cur.execute("SHOW INDEX FROM officials WHERE Key_name = 'role'")
    if cur.fetchone():
        cur.execute("ALTER TABLE officials DROP INDEX role")
        conn.commit()
        print("[OK] Dropped unique index on role")
    else:
        print("[INFO] role unique index already removed")
except Exception as e:
    print(f"[SKIP] role index: {e}")

# 3. Add a combined unique index (emp_id, role) instead
try:
    cur.execute("ALTER TABLE officials ADD UNIQUE KEY uq_empid_role (emp_id, role)")
    conn.commit()
    print("[OK] Added unique index on (emp_id, role)")
except Exception as e:
    print(f"[SKIP] (emp_id,role) index: {e}")

# 4. Add address and profile_pic columns to citizens if they don't exist
try:
    cur.execute("ALTER TABLE citizens ADD COLUMN address VARCHAR(500) DEFAULT '' AFTER mobile")
    conn.commit()
    print("[OK] Added address column to citizens")
except Exception as e:
    print(f"[SKIP] address column: {e}")

try:
    cur.execute("ALTER TABLE citizens ADD COLUMN email VARCHAR(255) DEFAULT '' AFTER address")
    conn.commit()
    print("[OK] Added email column to citizens")
except Exception as e:
    print(f"[SKIP] citizens.email column: {e}")

try:
    cur.execute("ALTER TABLE citizens ADD COLUMN profile_pic LONGTEXT AFTER email")
    conn.commit()
    print("[OK] Added profile_pic column to citizens")
except Exception as e:
    print(f"[SKIP] profile_pic column: {e}")

# 5. Re-seed all officials (they share emp_id jay2006 but different roles)
print("\n--- Seeding Officials ---")
PASS = generate_password_hash('123456')
EMP_ID = 'jay2006'

officials = [
    ('System Manager',         EMP_ID, 'system_manager',         'sysmanager@amc.gov.in',   ''),
    ('Commissioner',           EMP_ID, 'commissioner',            'commissioner@amc.gov.in',  ''),
    ('Deputy Commissioner',    EMP_ID, 'deputy_commissioner',     'dc@amc.gov.in',            'Zone A'),
    ('Assistant Commissioner', EMP_ID, 'assistant_commissioner',  'ac@amc.gov.in',            ''),
    ('HOD Officer',            EMP_ID, 'hod',                     'hod@amc.gov.in',           'Water Supply Department'),
    ('PA Officer',             EMP_ID, 'pa',                      'pa@amc.gov.in',            ''),
]

for full_name, emp_id, role, email, dept in officials:
    try:
        cur.execute("DELETE FROM officials WHERE role = %s", (role,))
        cur.execute(
            "INSERT INTO officials (full_name, emp_id, role, email, department, password) VALUES (%s,%s,%s,%s,%s,%s)",
            (full_name, emp_id, role, email, dept, PASS)
        )
        conn.commit()
        print(f"  [OK] {role:30s} emp_id={emp_id}")
    except Exception as e:
        print(f"  [FAIL] {role}: {e}")

# 6. Seed citizen
print("\n--- Seeding Citizen ---")
CIT_MOBILE = '1111111111'
CIT_PASS = generate_password_hash('123456')
try:
    cur.execute(
        "INSERT INTO citizens (full_name, mobile, password) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE password=%s",
        ('Test Citizen', CIT_MOBILE, CIT_PASS, CIT_PASS)
    )
    conn.commit()
    print(f"  [OK] Citizen mobile={CIT_MOBILE}")
except Exception as e:
    print(f"  [FAIL] Citizen: {e}")

cur.close()
conn.close()

print("""
==============================================
  DB FIX + SEEDING COMPLETE!
==============================================
  OFFICIAL LOGIN (all roles):
    Employee ID : jay2006
    Password    : 123456

  CITIZEN LOGIN:
    Mobile      : 1111111111
    Password    : 123456
==============================================
""")
