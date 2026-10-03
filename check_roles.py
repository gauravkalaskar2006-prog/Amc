import MySQLdb

conn = MySQLdb.connect(host='localhost', user='root', passwd='@Mypal0411', db='amc_db')
cur = conn.cursor()
cur.execute("SELECT id, full_name, role FROM officials WHERE role LIKE '%commissioner%'")
print(cur.fetchall())
cur.close()
conn.close()
