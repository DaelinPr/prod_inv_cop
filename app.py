from flask import Flask, render_template, request, redirect, url_for, send_file
import io, openpyxl
import os
import psycopg2
from urllib.parse import urlparse
import time

app = Flask(__name__)

# Функция для получения DATABASE_URL
def get_database_url():
    # Railway автоматически создает DATABASE_URL
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        # Если нет DATABASE_URL, проверяем другие возможные имена
        database_url = os.environ.get('POSTGRESQL_URL') or os.environ.get('POSTGRES_URL')
    
    if not database_url:
        raise Exception("DATABASE_URL not found in environment variables")
    
    # Исправляем URL для psycopg2
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    return database_url

# Функция для подключения к БД
def get_db_connection():
    database_url = get_database_url()
    print(f"Connecting to database with URL: {database_url.split('@')[0]}...@...")  # Логируем без пароля
    
    conn = psycopg2.connect(database_url)
    return conn

# --- Инициализация базы ---
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        print("Creating tables...")
        # Создаем таблицы
        cur.execute('''CREATE TABLE IF NOT EXISTS rooms
                     (id SERIAL PRIMARY KEY,
                      name TEXT,
                      number TEXT,
                      floor TEXT,
                      teacher TEXT,
                      capacity INTEGER)''')
        
        cur.execute('''CREATE TABLE IF NOT EXISTS items
                     (id SERIAL PRIMARY KEY,
                      room_id INTEGER REFERENCES rooms(id),
                      name TEXT,
                      inventory_number TEXT,
                      status TEXT)''')

        conn.commit()
        cur.close()
        conn.close()
        print("Database initialized successfully!")
        return True
        
    except Exception as e:
        print(f"Database initialization failed: {e}")
        return False

# Попытаемся инициализировать БД при старте
print("Starting application...")
print("Available environment variables:", [k for k in os.environ.keys() if 'DATABASE' in k or 'POSTGRES' in k])

# Пытаемся инициализировать БД с повторными попытками
for i in range(5):
    print(f"Database initialization attempt {i+1}/5")
    if init_db():
        break
    time.sleep(3)
else:
    print("Failed to initialize database after 5 attempts")

# --- Главная страница ---
@app.route("/")
def home():
    return render_template("home.html")

# --- Список кабинетов ---
@app.route("/rooms")
def rooms():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        filters = []
        params = []

        name = request.args.get("name")
        number = request.args.get("number")
        floor = request.args.get("floor")
        teacher = request.args.get("teacher")
        capacity_min = request.args.get("capacity_min")
        capacity_max = request.args.get("capacity_max")

        if name:
            filters.append("name ILIKE %s")
            params.append(f"%{name}%")
        if number:
            filters.append("number ILIKE %s")
            params.append(f"%{number}%")
        if floor:
            filters.append("floor ILIKE %s")
            params.append(f"%{floor}%")
        if teacher:
            filters.append("teacher ILIKE %s")
            params.append(f"%{teacher}%")
        if capacity_min:
            filters.append("capacity >= %s")
            params.append(capacity_min)
        if capacity_max:
            filters.append("capacity <= %s")
            params.append(capacity_max)

        query = "SELECT * FROM rooms"
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY number"

        cur.execute(query, params)
        rooms_data = cur.fetchall()

        # Преобразуем в список словарей для удобства
        rooms = []
        for room in rooms_data:
            rooms.append({
                'id': room[0],
                'name': room[1],
                'number': room[2],
                'floor': room[3],
                'teacher': room[4],
                'capacity': room[5]
            })

        cur.close()
        conn.close()
        
        return render_template("rooms.html", rooms=rooms,
                               name=name or "",
                               number=number or "",
                               floor=floor or "",
                               teacher=teacher or "",
                               capacity_min=capacity_min or "",
                               capacity_max=capacity_max or "")
                               
    except Exception as e:
        return f"Ошибка базы данных: {str(e)}", 500

# --- Добавление кабинета ---
@app.route("/rooms/add", methods=["GET", "POST"])
def add_room():
    if request.method == "POST":
        try:
            name = request.form["name"]
            number = request.form["number"]
            floor = request.form["floor"]
            teacher = request.form["teacher"]
            capacity = request.form["capacity"]

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO rooms (name, number, floor, teacher, capacity) VALUES (%s, %s, %s, %s, %s)",
                (name, number, floor, teacher, capacity)
            )
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for("rooms"))
        except Exception as e:
            return f"Ошибка при добавлении кабинета: {str(e)}", 500
    return render_template("add_room.html")

# --- Просмотр кабинета и его инвентаря ---
@app.route("/rooms/<int:room_id>")
def room_detail(room_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM rooms WHERE id=%s", (room_id,))
        room_data = cur.fetchone()
        cur.execute("SELECT * FROM items WHERE room_id=%s", (room_id,))
        items_data = cur.fetchall()
        
        cur.close()
        conn.close()
        
        if room_data:
            room = {
                'id': room_data[0],
                'name': room_data[1],
                'number': room_data[2],
                'floor': room_data[3],
                'teacher': room_data[4],
                'capacity': room_data[5]
            }
            
            items = []
            for item in items_data:
                items.append({
                    'id': item[0],
                    'room_id': item[1],
                    'name': item[2],
                    'inventory_number': item[3],
                    'status': item[4]
                })
            
            return render_template("room_detail.html", room=room, items=items)
        else:
            return "Кабинет не найден", 404
    except Exception as e:
        return f"Ошибка базы данных: {str(e)}", 500

# --- Удаление кабинета ---
@app.route("/rooms/<int:room_id>/delete")
def delete_room(room_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM items WHERE room_id=%s", (room_id,))
        cur.execute("DELETE FROM rooms WHERE id=%s", (room_id,))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for("rooms"))
    except Exception as e:
        return f"Ошибка при удалении: {str(e)}", 500

# --- Добавление инвентаря ---
@app.route("/rooms/<int:room_id>/add_item", methods=["GET", "POST"])
def add_item(room_id):
    if request.method == "POST":
        try:
            name = request.form["name"]
            inventory_number = request.form["inventory_number"]
            status = request.form["status"]

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO items (room_id, name, inventory_number, status) VALUES (%s, %s, %s, %s)",
                      (room_id, name, inventory_number, status))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for("room_detail", room_id=room_id))
        except Exception as e:
            return f"Ошибка при добавлении: {str(e)}", 500
    return render_template("add_item.html", room_id=room_id)

# --- Удаление предмета ---
@app.route("/items/<int:item_id>/delete/<int:room_id>")
def delete_item(item_id, room_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM items WHERE id=%s", (item_id,))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for("room_detail", room_id=room_id))
    except Exception as e:
        return f"Ошибка при удалении: {str(e)}", 500

# --- Редактирование кабинета ---
@app.route("/rooms/<int:room_id>/edit", methods=["GET", "POST"])
def edit_room(room_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if request.method == "POST":
            name = request.form["name"]
            number = request.form["number"]
            floor = request.form["floor"]
            teacher = request.form["teacher"]
            capacity = request.form["capacity"]

            cur.execute("""UPDATE rooms 
                         SET name=%s, number=%s, floor=%s, teacher=%s, capacity=%s 
                         WHERE id=%s""",
                      (name, number, floor, teacher, capacity, room_id))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for("rooms"))

        cur.execute("SELECT * FROM rooms WHERE id=%s", (room_id,))
        room_data = cur.fetchone()
        cur.close()
        conn.close()
        
        if room_data:
            room = {
                'id': room_data[0],
                'name': room_data[1],
                'number': room_data[2],
                'floor': room_data[3],
                'teacher': room_data[4],
                'capacity': room_data[5]
            }
            return render_template("edit_room.html", room=room)
        else:
            return "Кабинет не найден", 404
    except Exception as e:
        return f"Ошибка базы данных: {str(e)}", 500

# --- Редактирование инвентаря ---
@app.route("/items/<int:item_id>/edit/<int:room_id>", methods=["GET", "POST"])
def edit_item(item_id, room_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if request.method == "POST":
            name = request.form["name"]
            inventory_number = request.form["inventory_number"]
            status = request.form["status"]

            cur.execute("""UPDATE items 
                         SET name=%s, inventory_number=%s, status=%s 
                         WHERE id=%s""",
                      (name, inventory_number, status, item_id))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for("room_detail", room_id=room_id))

        cur.execute("SELECT * FROM items WHERE id=%s", (item_id,))
        item_data = cur.fetchone()
        cur.close()
        conn.close()
        
        if item_data:
            item = {
                'id': item_data[0],
                'room_id': item_data[1],
                'name': item_data[2],
                'inventory_number': item_data[3],
                'status': item_data[4]
            }
            return render_template("edit_item.html", item=item, room_id=room_id)
        else:
            return "Предмет не найден", 404
    except Exception as e:
        return f"Ошибка базы данных: {str(e)}", 500

# --- Просмотр всего инвентаря ---
@app.route("/items")
def all_items():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        filters = []
        params = []

        name = request.args.get("name")
        inventory_number = request.args.get("inventory_number")
        status = request.args.get("status")
        room_name = request.args.get("room_name")
        room_number = request.args.get("room_number")

        if name:
            filters.append("items.name ILIKE %s")
            params.append(f"%{name}%")
        if inventory_number:
            filters.append("items.inventory_number ILIKE %s")
            params.append(f"%{inventory_number}%")
        if status:
            filters.append("items.status = %s")
            params.append(status)
        if room_name:
            filters.append("rooms.name ILIKE %s")
            params.append(f"%{room_name}%")
        if room_number:
            filters.append("rooms.number ILIKE %s")
            params.append(f"%{room_number}%")

        query = """SELECT items.id, items.name, items.inventory_number, items.status,
                          rooms.name, rooms.number, items.room_id
                   FROM items
                   JOIN rooms ON items.room_id = rooms.id"""
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY rooms.number"

        cur.execute(query, params)
        items_data = cur.fetchall()
        cur.close()
        conn.close()

        items = []
        for item in items_data:
            items.append({
                'id': item[0],
                'name': item[1],
                'inventory_number': item[2],
                'status': item[3],
                'room_name': item[4],
                'room_number': item[5],
                'room_id': item[6]
            })

        return render_template("all_items.html", items=items,
                               name=name or "",
                               inventory_number=inventory_number or "",
                               status=status or "",
                               room_name=room_name or "",
                               room_number=room_number or "")
    except Exception as e:
        return f"Ошибка базы данных: {str(e)}", 500

# --- Экспорт ---
@app.route("/rooms/export")
def export_rooms():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM rooms ORDER BY number")
        rooms_data = cur.fetchall()
        cur.close()
        conn.close()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Кабинеты"

        headers = ["ID", "Название", "Номер", "Этаж", "Учитель", "Вместимость"]
        ws.append(headers)

        for r in rooms_data:
            ws.append(list(r))

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(output,
                         as_attachment=True,
                         download_name="rooms.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        return f"Ошибка при экспорте: {str(e)}", 500

@app.route("/items/export")
def export_items():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""SELECT items.id, items.name, items.inventory_number, items.status,
                              rooms.name, rooms.number
                       FROM items
                       JOIN rooms ON items.room_id = rooms.id
                       ORDER BY rooms.number""")
        items_data = cur.fetchall()
        cur.close()
        conn.close()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Инвентарь"

        headers = ["ID", "Название", "Инв. номер", "Статус", "Кабинет", "Номер кабинета"]
        ws.append(headers)

        for i in items_data:
            ws.append(list(i))

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(output,
                         as_attachment=True,
                         download_name="items.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        return f"Ошибка при экспорте: {str(e)}", 500

# --- Страница статуса для отладки ---
@app.route("/debug")
def debug():
    env_vars = {}
    for key, value in os.environ.items():
        if any(db_key in key.upper() for db_key in ['DATABASE', 'POSTGRES', 'URL']):
            if 'PASSWORD' in key.upper() or 'SECRET' in key.upper():
                env_vars[key] = '***HIDDEN***'
            else:
                env_vars[key] = value
    
    return {
        "status": "running", 
        "environment_variables": env_vars,
        "database_url_exists": 'DATABASE_URL' in os.environ
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
