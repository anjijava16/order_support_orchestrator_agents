# import pymysql

# conn = pymysql.connect(
#     host="localhost",
#     user="root",
#     password="Maxis@123",
#     database="support_tickets_db",
# )
# cur = conn.cursor()
# cur.execute("SELECT * from ")
# print(cur.fetchone())
# conn.close()

import pymysql
import pickle

conn = pymysql.connect(
    host="localhost",
    user="root",
    password="Maxis@123",
    database="support_tickets_db"
)
cur = conn.cursor()
cur.execute("SELECT checkpoint FROM checkpoints where thread_id='user_134' ")
row = cur.fetchone()
data = pickle.loads(row[0])
print(data)  # now you can see the Python object