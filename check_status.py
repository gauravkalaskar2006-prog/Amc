import MySQLdb

conn = MySQLdb.connect(host='localhost', user='root', passwd='@Mypal0411', db='amc_db')
cur = conn.cursor(MySQLdb.cursors.DictCursor)
cur.execute('SELECT DISTINCT status, COUNT(*) AS cnt FROM appointments GROUP BY status')
print(cur.fetchall())
cur.close()
conn.close()
