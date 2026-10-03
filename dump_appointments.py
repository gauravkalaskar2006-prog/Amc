import MySQLdb

conn = MySQLdb.connect(host='localhost', user='root', passwd='@Mypal0411', db='amc_db')
cur = conn.cursor(MySQLdb.cursors.DictCursor)
cur.execute('SELECT id, token, visitor_name, appt_date, appt_time, status, created_at FROM appointments ORDER BY created_at DESC LIMIT 20')
rows = cur.fetchall()
for r in rows:
    print(r)
cur.close()
conn.close()
