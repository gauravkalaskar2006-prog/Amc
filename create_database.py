"""
Create AMC Database and Tables
"""
import os

import MySQLdb
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database credentials (can be configured via environment)
DB_HOST = os.getenv('MYSQL_HOST', 'localhost')
DB_USER = os.getenv('MYSQL_USER', 'root')
DB_PASS = os.getenv('MYSQL_PASSWORD', '@Mypal0411')
DB_NAME = os.getenv('MYSQL_DB', 'amc_db')

try:
    # Connect without specifying database first
    conn = MySQLdb.connect(host=DB_HOST, user=DB_USER, passwd=DB_PASS)
    cursor = conn.cursor()
    
    print("Creating database 'amc_db'...")
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    cursor.execute(f"USE {DB_NAME}")
    
    print("Creating 'officials' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS officials (
        id INT AUTO_INCREMENT PRIMARY KEY,
        full_name VARCHAR(255) NOT NULL,
        emp_id VARCHAR(50) NOT NULL UNIQUE,
        role VARCHAR(100) NOT NULL,
        email VARCHAR(255),
        password VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    print("Creating 'citizens' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS citizens (
        id INT AUTO_INCREMENT PRIMARY KEY,
        full_name VARCHAR(255) NOT NULL,
        mobile VARCHAR(20) NOT NULL UNIQUE,
        email VARCHAR(255),
        password VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    print("Creating 'appointments' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        id INT AUTO_INCREMENT PRIMARY KEY,
        citizen_id INT,
        token VARCHAR(50) UNIQUE,
        visitor_name VARCHAR(255),
        mobile VARCHAR(20),
        department VARCHAR(100),
        appt_date DATE,
        appt_time TIME,
        reason TEXT,
        people_count INT DEFAULT 1,
        other_visitors TEXT,
        photo_data LONGTEXT,
        leader_aadhaar VARCHAR(20),
        member_names TEXT,
        status VARCHAR(50) DEFAULT 'Pending PA Review',
        first_decision_at DATETIME NULL,
        status_updated_at DATETIME NULL,
        rejection_reason TEXT,
        reschedule_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_appt_status (status),
        INDEX idx_appt_created_at (created_at),
        INDEX idx_appt_department_status (department, status),
        INDEX idx_appt_time (appt_time),
        FOREIGN KEY (citizen_id) REFERENCES citizens(id)
    )
    """)
    
    print("Creating 'feedback' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255),
        email VARCHAR(255),
        category VARCHAR(100),
        message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    print("\n✓ Database and tables created successfully!")
    cursor.close()
    
except MySQLdb.OperationalError as e:
    print(f"✗ Database error: {e}")
    exit(1)
except Exception as e:
    print(f"✗ Error: {e}")
    exit(1)
finally:
    try:
        conn.close()
    except:
        pass

print("\nNow running seed_accounts.py to add test data...")
import subprocess
result = subprocess.run(['python', 'seed_accounts.py'], cwd='.', capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("Errors:", result.stderr)

print("\n" + "="*60)
print("✓ Setup Complete! You can now run: python app.py")
print("="*60)
