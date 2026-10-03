"""
AMC Test Account Seeder
Inserts all official roles with emp_id=jay2006, password=123456
and a citizen with mobile=1111111111, password=123456
"""
import MySQLdb
from werkzeug.security import generate_password_hash

# --- DB CONFIG (must match app.py) ---
DB_HOST   = 'localhost'
DB_USER   = 'root'
DB_PASS   = '@Mypal0411'
DB_NAME   = 'amc_db'

conn = MySQLdb.connect(host=DB_HOST, user=DB_USER, passwd=DB_PASS, db=DB_NAME)
cur  = conn.cursor()

PASS   = generate_password_hash('123456')
EMP_ID = 'jay2006'

# ---- OFFICIALS ----
officials = [
    ('System Manager',            EMP_ID, 'system_manager',          'sysmanager@amc.gov.in'),
    ('Commissioner',              EMP_ID, 'commissioner',             'commissioner@amc.gov.in'),
    ('Deputy Commissioner',       EMP_ID, 'deputy_commissioner',      'dc@amc.gov.in'),
    ('Assistant Commissioner',    EMP_ID, 'assistant_commissioner',   'ac@amc.gov.in'),
    ('Head of Department (HOD)',  EMP_ID, 'hod',                      'hod@amc.gov.in'),
    ('Personal Assistant (PA)',   EMP_ID, 'pa',                       'pa@amc.gov.in'),
]

print("Inserting / updating officials...")
for full_name, emp_id, role, email in officials:
    # Delete existing record for this role to avoid duplicates
    cur.execute("DELETE FROM officials WHERE role = %s", (role,))
    cur.execute(
        "INSERT INTO officials (full_name, emp_id, role, email, password) VALUES (%s,%s,%s,%s,%s)",
        (full_name, emp_id, role, email, PASS)
    )
    print(f"  [OK]  {role:30s}  emp_id={emp_id}")

# ---- CITIZEN ----
CIT_MOBILE = '1111111111'
CIT_PASS   = generate_password_hash('123456')

try:
    cur.execute(
        "INSERT INTO citizens (full_name, mobile, password) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE password=%s",
        ('Test Citizen', CIT_MOBILE, CIT_PASS, CIT_PASS)
    )
    print(f"\n  [OK]  Citizen  mobile={CIT_MOBILE}")
except Exception as e:
    print(f"\n  [SKIP] Citizen: {e}")

conn.commit()
cur.close()
conn.close()

print("""
==============================================
  ALL TEST ACCOUNTS CREATED SUCCESSFULLY!
==============================================

  OFFICIAL LOGIN (any role):
    Employee ID : jay2006
    Password    : 123456

  CITIZEN LOGIN:
    Mobile      : 1111111111
    Password    : 123456
==============================================
""")
