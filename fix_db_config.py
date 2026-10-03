"""
Database Configuration Helper
Helps you set the correct MySQL root password in app.py
"""
import MySQLdb
import os

print("=" * 60)
print("DATABASE CONFIGURATION HELPER")
print("=" * 60)

# Try with empty password first
passwords_to_try = [
    '',           # Empty password
    'root',       # Common default
    'password',
    '123456',
    'admin',
]

found = False
correct_password = None

for pwd in passwords_to_try:
    try:
        print(f"\n✓ Trying password: '{pwd}'...", end=" ")
        conn = MySQLdb.connect(
            host='localhost',
            user='root',
            passwd=pwd,
            db='amc_db'
        )
        print("SUCCESS!")
        correct_password = pwd
        found = True
        conn.close()
        break
    except MySQLdb.OperationalError as e:
        print("Failed")

if found:
    print("\n" + "=" * 60)
    print(f"✓ Found working password: '{correct_password}'")
    print("=" * 60)
    
    if correct_password != '':
        # Update app.py with the correct password
        with open('app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        old_line = "app.config['MYSQL_PASSWORD'] = ''"
        new_line = f"app.config['MYSQL_PASSWORD'] = '{correct_password}'"
        
        if old_line in content:
            content = content.replace(old_line, new_line)
            with open('app.py', 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"\n✓ Updated app.py with password: '{correct_password}'")
        else:
            print("\n⚠ Could not find password line in app.py")
    else:
        print("\n✓ Password is empty (no update needed)")

else:
    print("\n" + "=" * 60)
    print("✗ Could not connect with any default password")
    print("=" * 60)
    print("\nPlease enter your MySQL root password manually:")
    pwd = input("> ").strip()
    
    try:
        conn = MySQLdb.connect(
            host='localhost',
            user='root',
            passwd=pwd,
            db='amc_db'
        )
        print("✓ Connection successful!")
        
        # Update app.py
        with open('app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        old_line = "app.config['MYSQL_PASSWORD'] = ''"
        new_line = f"app.config['MYSQL_PASSWORD'] = '{pwd}'"
        
        content = content.replace(old_line, new_line)
        with open('app.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Updated app.py with your password")
        conn.close()
    except MySQLdb.OperationalError as e:
        print(f"✗ Connection failed: {e}")

print("\n" + "=" * 60)
print("Run 'python app.py' to start the server")
print("=" * 60)
