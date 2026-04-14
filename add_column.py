import sqlite3

conn = sqlite3.connect("reservation.db")
c = conn.cursor()

# すでにあるとエラーになるので安全版
try:
    c.execute("ALTER TABLE reservations ADD COLUMN before_action TEXT")
    print("追加成功")
except sqlite3.OperationalError as e:
    print("すでに存在してる可能性:", e)

conn.commit()
conn.close()