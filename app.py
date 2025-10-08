from flask import Flask, render_template, request, redirect, url_for, send_file
import io, openpyxl
import os
import psycopg2
import time
import atexit
import threading

app = Flask(__name__)

# Глобальные переменные для управления состоянием БД
db_connection = None
db_initialized = False
db_init_lock = threading.Lock()

def get_db_connection():
    global db_connection, db_initialized
    
    # Если соединение уже установлено, возвращаем его
    if db_connection and not db_connection.closed:
        return db_connection
    
    # Получаем DATABASE_URL из переменных окружения
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        # Проверяем альтернативные имена переменных
        database_url = os.environ.get('POSTGRES_URL') or os.environ.get('PG_URL')
    
    if not database_url:
        raise Exception("DATABASE_URL not found in environment variables")
    
    # Исправляем URL для psycopg2
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    print(f"Connecting to database...")
    db_connection = psycopg2.connect(database_url)
    db_initialized = True
    print("Database connection established!")
    
    # Регистрируем закрытие соединения при выходе
    atexit.register(close_db_connection)
    
    return db_connection

def close_db_connection():
    global db_connection
    if db_connection and not db_connection.closed:
        db_connection.close()
        print("Database connection closed")

def init_db():
    global db_initialized
    
    with db_init_lock:
        if db_initialized:
            return True
            
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
            print("Database initialized successfully")
            return True
            
        except Exception as e:
            print(f"Database initialization failed: {e}")
            return False

def ensure_db_ready():
    """Обеспечивает готовность БД с повторными попытками"""
    max_retries = 12  # 60 секунд максимум
    retry_delay = 5   # 5 секунд между попытками
    
    for attempt in range(max_retries):
        try:
            if init_db():
                return True
        except Exception as e:
            print(f"Database connection attempt {attempt + 1}/{max_retries} failed: {e}")
            
        if attempt < max_retries - 1:
            print(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    
    return False

# Декоратор для автоматической проверки БД
def with_db(f):
    def decorated_function(*args, **kwargs):
        if not ensure_db_ready():
            return "База данных временно недоступна. Пожалуйста, попробуйте позже.", 503
        try:
            return f(*args, **kwargs)
        except psycopg2.OperationalError as e:
            print(f"Database error: {e}")
            return "Ошибка базы данных. Пожалуйста, попробуйте позже.", 503
        except Exception as e:
            print(f"Unexpected error: {e}")
            return "Внутренняя ошибка сервера.", 500
    decorated_function.__name__ = f.__name__
    return decorated_function

# Попытка инициализации БД при старте (не блокирующая)
def initialize_in_background():
    def init_task():
        time.sleep(2)  # Ждем немного перед первой попыткой
        ensure_db_ready()
    
    thread = threading.Thread(target=init_task)
    thread.daemon = True
    thread.start()

# Запускаем фоновую инициализацию
initialize_in_background()

# --- Маршруты приложения ---

@app.route("/")
@with_db
def home():
    return render_template("home.html")

@app.route("/rooms")
@with_db
def rooms():
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
    return render_template("rooms.html", rooms=rooms,
                           name=name or "",
                           number=number or "",
                           floor=floor or "",
                           teacher=teacher or "",
                           capacity_min=capacity_min or "",
                           capacity_max=capacity_max or "")

@app.route("/rooms/add", methods=["GET", "POST"])
@with_db
def add_room():
    if request.method == "POST":
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
        return redirect(url_for("rooms"))
    return render_template("add_room.html")

@app.route("/rooms/<int:room_id>")
@with_db
def room_detail(room_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM rooms WHERE id=%s", (room_id,))
    room_data = cur.fetchone()
    cur.execute("SELECT * FROM items WHERE room_id=%s", (room_id,))
    items_data = cur.fetchall()
    
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
        
        cur.close()
        return render_template("room_detail.html", room=room, items=items)
    else:
        cur.close()
        return "Кабинет не найден", 404

@app.route("/rooms/<int:room_id>/delete")
@with_db
def delete_room(room_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE room_id=%s", (room_id,))
    cur.execute("DELETE FROM rooms WHERE id=%s", (room_id,))
    conn.commit()
    cur.close()
    return redirect(url_for("rooms"))

@app.route("/rooms/<int:room_id>/add_item", methods=["GET", "POST"])
@with_db
def add_item(room_id):
    if request.method == "POST":
        name = request.form["name"]
        inventory_number = request.form["inventory_number"]
        status = request.form["status"]

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO items (room_id, name, inventory_number, status) VALUES (%s, %s, %s, %s)",
                  (room_id, name, inventory_number, status))
        conn.commit()
        cur.close()
        return redirect(url_for("room_detail", room_id=room_id))
    return render_template("add_item.html", room_id=room_id)

@app.route("/items/<int:item_id>/delete/<int:room_id>")
@with_db
def delete_item(item_id, room_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE id=%s", (item_id,))
    conn.commit()
    cur.close()
    return redirect(url_for("room_detail", room_id=room_id))

@app.route("/rooms/<int:room_id>/edit", methods=["GET", "POST"])
@with_db
def edit_room(room_id):
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
        return redirect(url_for("rooms"))

    cur.execute("SELECT * FROM rooms WHERE id=%s", (room_id,))
    room_data = cur.fetchone()
    cur.close()
    
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

@app.route("/items/<int:item_id>/edit/<int:room_id>", methods=["GET", "POST"])
@with_db
def edit_item(item_id, room_id):
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
        return redirect(url_for("room_detail", room_id=room_id))

    cur.execute("SELECT * FROM items WHERE id=%s", (item_id,))
    item_data = cur.fetchone()
    cur.close()
    
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

@app.route("/items")
@with_db
def all_items():
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

# Экспорт маршруты (упрощенные версии)
@app.route("/rooms/export")
@with_db
def export_rooms():
    return "Экспорт будет доступен после настройки базы данных", 503

@app.route("/items/export")
@with_db
def export_items():
    return "Экспорт будет доступен после настройки базы данных", 503

if __name__ == '__main__':
    print("Starting Flask application...")
    print("Environment variables:", list(os.environ.keys()))
    
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting server on port {port}")
    
    app.run(host='0.0.0.0', port=port, debug=False)
