from flask import Flask
from flask_mysqldb import MySQL

app = Flask(__name__)
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '@Mypal0411'
app.config['MYSQL_DB'] = 'amc_db'

mysql = MySQL(app)

@app.route('/')
def index():
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT 1")
        return "DB OK"
    except Exception as e:
        return str(e)

if __name__ == '__main__':
    with app.app_context():
        try:
            print("App context connection:", mysql.connection)
        except Exception as e:
            print("Error connecting:", e)
    app.run(port=5001)
