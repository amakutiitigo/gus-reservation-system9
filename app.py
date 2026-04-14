from flask import Flask, render_template, request, redirect, session, jsonify, send_file
from datetime import datetime, timedelta
import sqlite3
import io
import os
from openpyxl import Workbook

from datetime import timezone
JST = timezone(timedelta(hours=9))

app = Flask(__name__)

app.secret_key = "supersecretkey"
app.permanent_session_lifetime = timedelta(days=7)

# ---------------- DB ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "reservation.db")

print("DB PATH =", DB_FILE)

# ---------------- DB初期化 ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        time TEXT,
        consumer_code TEXT,
        name TEXT,
        phone TEXT,
        address TEXT,
        action TEXT,
        is_deleted INTEGER DEFAULT 0,
        created_at TEXT
        )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS blocked_times (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        start_time TEXT,
        end_time TEXT
    )
    """)

    conn.commit()
    conn.close()
init_db()

# ---------------- トップ ----------------
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        code = request.form.get('consumer_code')

        if not code:
            return "消費者コードを入力してください"

        session['code'] = code
        action = request.form.get('action')

        if action == "新規":
            return redirect('/new')
        elif action == "変更":
            return redirect('/edit')
        elif action == "削除":
            return redirect('/delete')

    return render_template('index.html')

# ---------------- ログイン ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == "20100401":
            session['login'] = True
            return redirect('/admin_menu')
        return render_template('login.html', error="パスワードが違います")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ---------------- 管理者メイン画面 ----------------
@app.route('/admin_menu')
def admin_menu():
    if not session.get('login'):
        return redirect('/login')
    return render_template('admin_menu.html')

# ---------------- admin（★ここ改修） ----------------
@app.route('/admin')
def admin():
    if not session.get('login'):
        return redirect('/login')

    code = request.args.get('code', '')
    name = request.args.get('name', '')

    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    created_from = request.args.get('created_from', '')
    created_to = request.args.get('created_to', '')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    query = """
        SELECT id,date,time,consumer_code,name,phone,address,action,created_at
        FROM reservations
        WHERE is_deleted = 0
    """

    params = []

    if code:
        query += " AND consumer_code LIKE ?"
        params.append(f"%{code}%")

    if name:
        query += " AND name LIKE ?"
        params.append(f"%{name}%")

    # 予約日（期間）
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)

    if date_to:
        query += " AND date <= ?"
        params.append(date_to)

    # 申込日（期間）
    if created_from:
        query += " AND date(created_at) >= ?"
        params.append(created_from)

    if created_to:
        query += " AND date(created_at) <= ?"
        params.append(created_to)

    query += " ORDER BY created_at DESC"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    return render_template("admin.html", reservations=rows)

    # 申込日（created_atは日時なので日付だけで検索）
    if created_at:
        query += " AND date(created_at) = ?"
        params.append(created_at)

    query += " ORDER BY created_at DESC"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    return render_template("admin.html", reservations=rows)

@app.route('/admin_delete', methods=['POST'])
def admin_delete():

    reservation_id = request.form.get('id')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        UPDATE reservations
        SET before_action = COALESCE(action, '新規'),
            is_deleted = 1,
            action = '削除'
        WHERE id = ?
    """, (reservation_id,))

    conn.commit()
    conn.close()

    return redirect('/admin')

@app.route('/admin_deleted')
def admin_deleted():
    if not session.get('login'):
        return redirect('/login')

    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    name = request.args.get('name', '')
    code = request.args.get('code', '')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    query = """
        SELECT id,date,time,consumer_code,name,phone,address,action,created_at
        FROM reservations
        WHERE is_deleted = 1
    """

    params = []

    if date_from:
        query += " AND date >= ?"
        params.append(date_from)

    if date_to:
        query += " AND date <= ?"
        params.append(date_to)

    if name:
        query += " AND name LIKE ?"
        params.append(f"%{name}%")

    if code:
        query += " AND consumer_code LIKE ?"
        params.append(f"%{code}%")

    query += " ORDER BY created_at DESC"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    # ★時間変換
    new_rows = []
    for r in rows:
        t = r[2][:5]
        h, m = map(int, t.split(":"))

        end_h = h
        end_m = m + 30
        if end_m >= 60:
            end_h += 1
            end_m -= 60

        time_range = f"{t}～{str(end_h).zfill(2)}:{str(end_m).zfill(2)}"

        new_rows.append((
            r[0], r[1], time_range,
            r[3], r[4], r[5], r[6], r[7], r[8]
        ))

    return render_template("admin_deleted.html", reservations=new_rows)

@app.route('/admin_restore', methods=['POST'])
def admin_restore():
    print("RESTORE POST:", request.form)
    if not session.get('login'):
        return redirect('/login')

    reservation_id = request.form.get('id')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # ★これが正解
    c.execute("""
        UPDATE reservations
        SET is_deleted = 0,
            action = before_action
        WHERE id = ?
    """, (reservation_id,))

    conn.commit()
    conn.close()

    return redirect('/admin_deleted')

@app.route('/admin_restore_multi', methods=['POST'])
def admin_restore_multi():
    if not session.get('login'):
        return redirect('/login')

    ids = request.form.getlist('ids')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for i in ids:
        c.execute("""
            UPDATE reservations
            SET is_deleted = 0
            WHERE id = ?
        """, (i,))

    conn.commit()
    conn.close()

    return redirect('/admin_deleted')


@app.route('/admin_bulk_delete', methods=['POST'])
def admin_bulk_delete():
    if not session.get('login'):
        return redirect('/login')

    ids = request.form.getlist('ids')

    if not ids:
        return redirect('/admin_deleted')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for i in ids:
        c.execute("""
            DELETE FROM reservations
            WHERE id = ?
        """, (i,))

    conn.commit()
    conn.close()

    return redirect('/admin_deleted')

# ---------------- admin_block ----------------
@app.route('/admin_block')
def admin_block():
    if not session.get('login'):
        return redirect('/login')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        SELECT id, date, start_time, end_time
        FROM blocked_times
        ORDER BY date DESC, start_time
    """)
    rows = c.fetchall()
    conn.close()

    return render_template("admin_block.html", blocks=rows)


@app.route('/add_block', methods=['POST'])
def add_block():

    if not session.get('login'):
        return redirect('/login')

    date = request.form['date']
    start = request.form['start_time']
    end = request.form['end_time']

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        INSERT INTO blocked_times (date, start_time, end_time)
        VALUES (?,?,?)
    """, (date, start, end))

    conn.commit()
    conn.close()

    return redirect('/admin_block')

@app.route('/delete_block/<int:block_id>')
def delete_block(block_id):

    if not session.get('login'):
        return redirect('/login')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("DELETE FROM blocked_times WHERE id=?", (block_id,))

    conn.commit()
    conn.close()

    return redirect('/admin_block')

# ---------------- new ----------------
@app.route('/new')
def new():
    if not session.get('code'):
        return redirect('/')

    # ★ダミーじゃなく「安全な初期値」を渡す
    data = ("", "", "", "", "", "", "")

    return render_template("new.html", data=data)

    code = request.form.get('consumer_code')

    if not code or not code.isdigit() or len(code) != 11:
        return "消費者コードは11桁の数字で入力してください"

# ---------------- get_times ----------------
@app.route('/get_times')
def get_times():

    date = request.args.get('date')
    if not date:
        return jsonify([])

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # ①予約取得
    c.execute("""
        SELECT time, action
        FROM reservations
        WHERE date=?
    """, (date,))
    rows = c.fetchall()

    reserved = set()
    for t, action in rows:
        if action != "削除":
            reserved.add(t[:5])

    # ②ブロック取得
    c.execute("""
        SELECT start_time, end_time
        FROM blocked_times
        WHERE date=?
    """, (date,))
    blocks = c.fetchall()

    conn.close()

    # ★ここが本質（今から24時間）
    limit_time = datetime.now(JST) + timedelta(hours=24)

    # ④時間生成
    slots = []

    start = datetime.strptime("09:30", "%H:%M")
    end = datetime.strptime("16:30", "%H:%M")

    while start <= end:

        t = start.strftime("%H:%M")
        current_dt = datetime.strptime(
            date + " " + t,
            "%Y-%m-%d %H:%M"
        ).replace(tzinfo=JST)

        # ①予約済みチェック
        if t in reserved:
            start += timedelta(minutes=30)
            continue

        # ②ブロックチェック
        blocked = False

        for b_start, b_end in blocks:
            bs = datetime.strptime(date + " " + b_start, "%Y-%m-%d %H:%M")
            be = datetime.strptime(date + " " + b_end, "%Y-%m-%d %H:%M")

            # 日跨ぎ対応
            if be <= bs:
                be += timedelta(days=1)

            if bs <= current_dt < be:
                blocked = True
                break

        if blocked:
            start += timedelta(minutes=30)
            continue

        # ★③24時間ルール（ここだけ）
        # if current_dt < limit_time:
        #     start += timedelta(minutes=30)
        #     continue

        # OK
        slots.append(t)

        start += timedelta(minutes=30)

    return jsonify(slots)


@app.route('/confirm', methods=['POST'])
def confirm():

    data = {
        "date": request.form.get("date"),
        "time": request.form.get("time"),
        "name": request.form.get("name"),
        "phone": request.form.get("phone"),
            "address": request.form.get("address")
    }

    return render_template("confirm.html", data=data)

# ---------------- create ----------------
@app.route('/create_confirm', methods=['POST'])
def create_confirm():

    data = request.form
    code = session.get('code')

    if not code:
        return "ログイン情報なし"

    target_dt = datetime.strptime(
        data['date'] + " " + data['time'][:5],
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=JST)

    # ★ここが本質（今から24時間）
    limit_time = datetime.now(JST) + timedelta(hours=24)

    if target_dt < limit_time:
        return "24時間後以降の予約しかできません"

    # ★通常処理
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        INSERT INTO reservations
        (date,time,consumer_code,name,phone,address,action,created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        data['date'],
        data['time'][:5],
        code,
        data['name'],
        data['phone'],
        data['address'],
        "新規",
        datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return "予約完了"

# ---------------- edit ----------------
@app.route('/edit')
def edit():
    code = session.get('code')

    if not code:
        return redirect('/')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        SELECT id,date,time,name,phone,address
        FROM reservations
        WHERE consumer_code=?
        ORDER BY id DESC
        LIMIT 1
    """, (code,))

    data = c.fetchone()
    current_time = data[2][:5]
    current_date = data[1]

    if not data:
        return "予約データがありません"

    return render_template("edit.html", data=data)

@app.route('/edit_confirm', methods=['POST'])
def edit_confirm():

    data = {
        "date": request.form.get("date"),
        "time": request.form.get("time"),
        "name": request.form.get("name"),
        "phone": request.form.get("phone"),
        "address": request.form.get("address")
    }

    return render_template("edit_confirm.html", data=data)

# ---------------- edit_save ----------------
@app.route('/edit_save', methods=['POST'])
def edit_save():
    data = request.form
    code = session.get('code')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        INSERT INTO reservations
        (date,time,consumer_code,name,phone,address,action,created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        data['date'],
        data['time'][:5],
        code,
        data['name'],
        data['phone'],
        data['address'],
        "変更",
        datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return "変更完了"

# ---------------- delete ----------------
@app.route('/delete')
def delete():
    code = session.get('code')

    if not code:
        return redirect('/')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        SELECT id,date,time,name,phone,address,is_deleted
        FROM reservations
        WHERE consumer_code=? AND is_deleted=0
        ORDER BY id DESC
        LIMIT 1
    """, (code,))

    row = c.fetchone()
    conn.close()

    if not row:
        return render_template("delete.html", data=None)

    # ★ここから置き換え
    if not row or not row[2]:
        return render_template("delete.html", data=None)

    try:
        start = datetime.strptime(row[2][:5], "%H:%M")
        end = start + timedelta(minutes=30)
        time_range = f"{start.strftime('%H:%M')}～{end.strftime('%H:%M')}"
    except:
        time_range = row[2] or ""
# ★ここまで

    data = (row[0], row[1], time_range, row[3], row[4], row[5])

    return render_template("delete.html", data=data)

@app.route('/delete', methods=['POST'])
def delete_post():
    code = session.get('code')

    if not code:
        return redirect('/')

    date = request.form.get('date')
    time = request.form.get('time')
    name = request.form.get('name')
    phone = request.form.get('phone')
    address = request.form.get('address')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        INSERT INTO reservations
        (date,time,consumer_code,name,phone,address,action,created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        date,
        time,
        code,
        name,
        phone,
        address,
        "削除",
        datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return "削除完了"

# ---------------- excel出力 ----------------
@app.route('/export_excel')
def export_excel():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        SELECT date,time,created_at,consumer_code,name,address,phone,action
        FROM reservations
        ORDER BY created_at DESC
    """)

    rows = c.fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "予約一覧"

    ws.append([
        "予約日",
        "予約時間",
        "申込日時",
        "消費者コード",
        "氏名",
        "住所",
        "電話番号",
        "状態"
    ])

    def format_range(t):
        if not t:
            return ""

        t = t[:5]

        h, m = map(int, t.split(":"))
        end_h = h
        end_m = m + 30

        if end_m >= 60:
            end_h += 1
            end_m -= 60

        return f"{t}～{str(end_h).zfill(2)}:{str(end_m).zfill(2)}"

    for r in rows:
        date, time, created_at, code, name, address, phone, action = r

        ws.append([
            date,
            format_range(time),   # ★ここが重要
            created_at,
            code,
            name,
            address,
            phone,
            action
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        download_name="reservations.xlsx",
        as_attachment=True
    )

# ---------------- 起動 ----------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=10000, debug=True)
