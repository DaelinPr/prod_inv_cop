from flask import Flask, render_template, request, redirect, url_for, send_file
import sqlite3, io, openpyxl


app = Flask(__name__)

# --- Инициализация базы ---
def init_db():
    conn = sqlite3.connect("equipment.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS rooms
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT,
                  number TEXT,
                  floor TEXT,
                  teacher TEXT,
                  capacity INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  room_id INTEGER,
                  name TEXT,
                  inventory_number TEXT,
                  status TEXT,
                  FOREIGN KEY(room_id) REFERENCES rooms(id))''')

    conn.commit()
    conn.close()


# --- Главная страница ---
@app.route("/")
def home():
    return render_template("home.html")


# --- Список кабинетов ---
@app.route("/rooms")
def rooms():
    filters = []
    params = []

    name = request.args.get("name")
    number = request.args.get("number")
    floor = request.args.get("floor")
    teacher = request.args.get("teacher")
    capacity_min = request.args.get("capacity_min")
    capacity_max = request.args.get("capacity_max")

    if name:
        filters.append("name LIKE ?")
        params.append(f"%{name}%")
    if number:
        filters.append("number LIKE ?")
        params.append(f"%{number}%")
    if floor:
        filters.append("floor LIKE ?")
        params.append(f"%{floor}%")
    if teacher:
        filters.append("teacher LIKE ?")
        params.append(f"%{teacher}%")
    if capacity_min:
        filters.append("capacity >= ?")
        params.append(capacity_min)
    if capacity_max:
        filters.append("capacity <= ?")
        params.append(capacity_max)

    query = "SELECT * FROM rooms"
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY number"

    conn = sqlite3.connect("equipment.db")
    c = conn.cursor()
    c.execute(query, params)
    rooms = c.fetchall()
    conn.close()

    return render_template("rooms.html", rooms=rooms,
                           name=name or "",
                           number=number or "",
                           floor=floor or "",
                           teacher=teacher or "",
                           capacity_min=capacity_min or "",
                           capacity_max=capacity_max or "")




# --- Добавление кабинета ---
@app.route("/rooms/add", methods=["GET", "POST"])
def add_room():
    if request.method == "POST":
        name = request.form["name"]
        number = request.form["number"]
        floor = request.form["floor"]
        teacher = request.form["teacher"]
        capacity = request.form["capacity"]

        conn = sqlite3.connect("equipment.db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO rooms (name, number, floor, teacher, capacity) VALUES (?, ?, ?, ?, ?)",
            (name, number, floor, teacher, capacity)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("rooms"))
    return render_template("add_room.html")


# --- Просмотр кабинета и его инвентаря ---
@app.route("/rooms/<int:room_id>")
def room_detail(room_id):
    conn = sqlite3.connect("equipment.db")
    c = conn.cursor()
    c.execute("SELECT * FROM rooms WHERE id=?", (room_id,))
    room = c.fetchone()
    c.execute("SELECT * FROM items WHERE room_id=?", (room_id,))
    items = c.fetchall()
    conn.close()
    return render_template("room_detail.html", room=room, items=items)


# --- Удаление кабинета ---
@app.route("/rooms/<int:room_id>/delete")
def delete_room(room_id):
    conn = sqlite3.connect("equipment.db")
    c = conn.cursor()
    c.execute("DELETE FROM items WHERE room_id=?", (room_id,))
    c.execute("DELETE FROM rooms WHERE id=?", (room_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("rooms"))

# --- Добавление инвентаря ---
@app.route("/rooms/<int:room_id>/add_item", methods=["GET", "POST"])
def add_item(room_id):
    if request.method == "POST":
        name = request.form["name"]
        inventory_number = request.form["inventory_number"]
        status = request.form["status"]

        conn = sqlite3.connect("equipment.db")
        c = conn.cursor()
        c.execute("INSERT INTO items (room_id, name, inventory_number, status) VALUES (?, ?, ?, ?)",
                  (room_id, name, inventory_number, status))
        conn.commit()
        conn.close()
        return redirect(url_for("room_detail", room_id=room_id))
    return render_template("add_item.html", room_id=room_id)


# --- Удаление предмета ---
@app.route("/items/<int:item_id>/delete/<int:room_id>")
def delete_item(item_id, room_id):
    conn = sqlite3.connect("equipment.db")
    c = conn.cursor()
    c.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("room_detail", room_id=room_id))


# --- Редактирование кабинета ---
@app.route("/rooms/<int:room_id>/edit", methods=["GET", "POST"])
def edit_room(room_id):
    conn = sqlite3.connect("equipment.db")
    c = conn.cursor()
    if request.method == "POST":
        name = request.form["name"]
        number = request.form["number"]
        floor = request.form["floor"]
        teacher = request.form["teacher"]
        capacity = request.form["capacity"]

        c.execute("""UPDATE rooms 
                     SET name=?, number=?, floor=?, teacher=?, capacity=? 
                     WHERE id=?""",
                  (name, number, floor, teacher, capacity, room_id))
        conn.commit()
        conn.close()
        return redirect(url_for("rooms"))

    c.execute("SELECT * FROM rooms WHERE id=?", (room_id,))
    room = c.fetchone()
    conn.close()
    return render_template("edit_room.html", room=room)


# --- Редактирование инвентаря ---
@app.route("/items/<int:item_id>/edit/<int:room_id>", methods=["GET", "POST"])
def edit_item(item_id, room_id):
    conn = sqlite3.connect("equipment.db")
    c = conn.cursor()
    if request.method == "POST":
        name = request.form["name"]
        inventory_number = request.form["inventory_number"]
        status = request.form["status"]

        c.execute("""UPDATE items 
                     SET name=?, inventory_number=?, status=? 
                     WHERE id=?""",
                  (name, inventory_number, status, item_id))
        conn.commit()
        conn.close()
        return redirect(url_for("room_detail", room_id=room_id))

    c.execute("SELECT * FROM items WHERE id=?", (item_id,))
    item = c.fetchone()
    conn.close()
    return render_template("edit_item.html", item=item, room_id=room_id)


# --- Просмотри всего инвентаря ---
@app.route("/items")
def all_items():
    filters = []
    params = []

    name = request.args.get("name")
    inventory_number = request.args.get("inventory_number")
    status = request.args.get("status")
    room_name = request.args.get("room_name")
    room_number = request.args.get("room_number")

    if name:
        filters.append("items.name LIKE ?")
        params.append(f"%{name}%")
    if inventory_number:
        filters.append("items.inventory_number LIKE ?")
        params.append(f"%{inventory_number}%")
    if status:
        filters.append("items.status = ?")
        params.append(status)
    if room_name:
        filters.append("rooms.name LIKE ?")
        params.append(f"%{room_name}%")
    if room_number:
        filters.append("rooms.number LIKE ?")
        params.append(f"%{room_number}%")

    query = """SELECT items.id, items.name, items.inventory_number, items.status,
                      rooms.name, rooms.number, items.room_id
               FROM items
               JOIN rooms ON items.room_id = rooms.id"""
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY rooms.number"

    conn = sqlite3.connect("equipment.db")
    c = conn.cursor()
    c.execute(query, params)
    items = c.fetchall()
    conn.close()

    return render_template("all_items.html", items=items,
                           name=name or "",
                           inventory_number=inventory_number or "",
                           status=status or "",
                           room_name=room_name or "",
                           room_number=room_number or "")


@app.route("/rooms/export")
def export_rooms():
    filters = []
    params = []

    name = request.args.get("name")
    number = request.args.get("number")
    floor = request.args.get("floor")
    teacher = request.args.get("teacher")
    capacity_min = request.args.get("capacity_min")
    capacity_max = request.args.get("capacity_max")

    if name:
        filters.append("name LIKE ?")
        params.append(f"%{name}%")
    if number:
        filters.append("number LIKE ?")
        params.append(f"%{number}%")
    if floor:
        filters.append("floor LIKE ?")
        params.append(f"%{floor}%")
    if teacher:
        filters.append("teacher LIKE ?")
        params.append(f"%{teacher}%")
    if capacity_min:
        filters.append("capacity >= ?")
        params.append(capacity_min)
    if capacity_max:
        filters.append("capacity <= ?")
        params.append(capacity_max)

    query = "SELECT * FROM rooms"
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY number"

    conn = sqlite3.connect("equipment.db")
    c = conn.cursor()
    c.execute(query, params)
    rooms = c.fetchall()
    conn.close()

    # Создаём Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Кабинеты"

    headers = ["ID", "Название", "Номер", "Этаж", "Учитель", "Вместимость"]
    ws.append(headers)

    for r in rooms:
        ws.append(r)

    # Отправляем файл
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(output,
                     as_attachment=True,
                     download_name="rooms.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/items/export")
def export_items():
    filters = []
    params = []

    name = request.args.get("name")
    inventory_number = request.args.get("inventory_number")
    status = request.args.get("status")
    room_name = request.args.get("room_name")
    room_number = request.args.get("room_number")

    if name:
        filters.append("items.name LIKE ?")
        params.append(f"%{name}%")
    if inventory_number:
        filters.append("items.inventory_number LIKE ?")
        params.append(f"%{inventory_number}%")
    if status:
        filters.append("items.status = ?")
        params.append(status)
    if room_name:
        filters.append("rooms.name LIKE ?")
        params.append(f"%{room_name}%")
    if room_number:
        filters.append("rooms.number LIKE ?")
        params.append(f"%{room_number}%")

    query = """SELECT items.id, items.name, items.inventory_number, items.status,
                      rooms.name, rooms.number
               FROM items
               JOIN rooms ON items.room_id = rooms.id"""
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY rooms.number"

    conn = sqlite3.connect("equipment.db")
    c = conn.cursor()
    c.execute(query, params)
    items = c.fetchall()
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Инвентарь"

    headers = ["ID", "Название", "Инв. номер", "Статус", "Кабинет", "Номер кабинета"]
    ws.append(headers)

    for i in items:
        ws.append(i)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(output,
                     as_attachment=True,
                     download_name="items.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")





if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
