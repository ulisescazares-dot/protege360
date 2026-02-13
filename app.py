from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"

# -------------------------
# CONFIGURACIÓN
# -------------------------

AGENTS = ["agent1", "agent2", "agent3"]
STATUS_OPTIONS = ["Nuevo", "Contactado", "Cotizado", "Cerrado"]

agent_index = 0

# -------------------------
# BASE DE DATOS
# -------------------------

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # ===== TABLA LEADS =====
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            age INTEGER,
            product_type TEXT,
            smoker TEXT,
            payment_frequency TEXT,
            monthly_budget TEXT,
            retirement_age TEXT,
            dependents_count TEXT,
            retirement_goal TEXT,
            phone TEXT,
            created_at TEXT,
            status TEXT,
            agent TEXT
        )
    """)

    # ===== TABLA USERS =====
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    # Crear director si no existe
    cursor.execute("SELECT * FROM users WHERE username = ?", ("director",))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (username, password, role)
            VALUES (?, ?, ?)
        """, ("director", generate_password_hash("1234"), "director"))

    # Crear agentes si no existen
    for agent in AGENTS:
        cursor.execute("SELECT * FROM users WHERE username = ?", (agent,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO users (username, password, role)
                VALUES (?, ?, ?)
            """, (agent, generate_password_hash("1234"), "agent"))

    conn.commit()
    conn.close()

init_db()

# -------------------------
# ROTACIÓN DE AGENTES
# -------------------------

def get_next_agent():
    global agent_index
    agent = AGENTS[agent_index % len(AGENTS)]
    agent_index += 1
    return agent

# -------------------------
# RUTA PRINCIPAL
# -------------------------

@app.route("/")
def home():
    return render_template("chat.html")

# -------------------------
# CHAT INTELIGENTE
# -------------------------

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    state = data.get("state", {"level": "start", "data": {}})

    reply = ""
    options = []

    # START
    if state["level"] == "start":
        reply = "Hola 👋\n\n¿Cuántos años tienes?"
        state["level"] = "age"

    elif state["level"] == "age":
        try:
            state["data"]["age"] = int(message)
            reply = "¿Qué estás buscando?"
            options = ["Gastos Médicos (MedicaLife)", "Seguro de Vida (MetaLife)"]
            state["level"] = "product_type"
        except:
            reply = "Por favor escribe tu edad en números."

    elif state["level"] == "product_type":
        state["data"]["product_type"] = message

        if "Gastos Médicos" in message:
            reply = "¿Fumas?"
            options = ["Sí", "No"]
            state["level"] = "smoker"
        else:
            reply = "¿A qué edad te gustaría retirarte?"
            state["level"] = "retirement_age"

    # -------- GMM --------
    elif state["level"] == "smoker":
        state["data"]["smoker"] = message
        reply = "¿Cómo prefieres pagar tu plan?"
        options = ["Mensual", "Trimestral", "Semestral", "Anual"]
        state["level"] = "payment_frequency"

    elif state["level"] == "payment_frequency":
        state["data"]["payment_frequency"] = message
        reply = "¿Cuánto podrías invertir al mes?"
        options = ["$1,500 – $2,500", "$2,500 – $4,000", "$4,000 – $7,000", "Más de $7,000"]
        state["level"] = "monthly_budget"

    # -------- VIDA --------
    elif state["level"] == "retirement_age":
        state["data"]["retirement_age"] = message
        reply = "¿Cuántas personas dependen de ti?"
        state["level"] = "dependents_count"

    elif state["level"] == "dependents_count":
        state["data"]["dependents_count"] = message
        reply = "¿Cuánto te gustaría invertir al mes?"
        options = ["$1,500 – $2,500", "$2,500 – $4,000", "$4,000 – $7,000", "Más de $7,000"]
        state["level"] = "monthly_budget"

    elif state["level"] == "monthly_budget":
        state["data"]["monthly_budget"] = message

        if "Seguro de Vida" in state["data"]["product_type"]:
            reply = "¿Con cuánto te gustaría retirarte?"
            state["level"] = "retirement_goal"
        else:
            state["level"] = "summary"

    elif state["level"] == "retirement_goal":
        state["data"]["retirement_goal"] = message
        state["level"] = "summary"

    # -------- RESUMEN --------
    elif state["level"] == "summary":
        summary = "Resumen de tu perfil:\n\n"
        for k, v in state["data"].items():
            summary += f"{k.replace('_',' ').title()}: {v}\n"

        reply = summary + "\nPor favor escribe tu nombre completo."
        state["level"] = "name"

    elif state["level"] == "name":
        state["data"]["name"] = message
        reply = "Escribe tu número de WhatsApp."
        state["level"] = "phone"

    elif state["level"] == "phone":
        state["data"]["phone"] = message
        assigned_agent = get_next_agent()

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO leads (
                name, age, product_type, smoker, payment_frequency,
                monthly_budget, retirement_age, dependents_count,
                retirement_goal, phone, created_at, status, agent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state["data"].get("name"),
            state["data"].get("age"),
            state["data"].get("product_type"),
            state["data"].get("smoker"),
            state["data"].get("payment_frequency"),
            state["data"].get("monthly_budget"),
            state["data"].get("retirement_age"),
            state["data"].get("dependents_count"),
            state["data"].get("retirement_goal"),
            state["data"].get("phone"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Nuevo",
            assigned_agent
        ))

        conn.commit()
        conn.close()

        reply = "Gracias. Un asesor se pondrá en contacto contigo."
        state["level"] = "closed"

    return jsonify({"reply": reply, "options": options, "state": state})

# -------------------------
# LOGIN
# -------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT username, password, role FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session["username"] = user[0]
            session["role"] = user[2]
            return redirect(url_for("dashboard"))
        else:
            return "Credenciales incorrectas"

    return render_template("login.html")

# -------------------------
# DASHBOARD
# -------------------------

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    metrics = None

    if session["role"] == "director":
        cursor.execute("SELECT * FROM leads")
        leads = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) FROM leads")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'Cerrado'")
        closed = cursor.fetchone()[0]

        close_rate = round((closed / total) * 100, 2) if total > 0 else 0

        cursor.execute("SELECT agent, COUNT(*) FROM leads GROUP BY agent")
        by_agent = cursor.fetchall()

        cursor.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")
        by_status = cursor.fetchall()

        metrics = {
            "total": total,
            "closed": closed,
            "close_rate": close_rate,
            "by_agent": by_agent,
            "by_status": by_status
        }

    else:
        cursor.execute("SELECT * FROM leads WHERE agent = ?", (session["username"],))
        leads = cursor.fetchall()

    conn.close()

    return render_template("dashboard.html",
                           leads=leads,
                           role=session["role"],
                           username=session["username"],
                           status_options=STATUS_OPTIONS,
                           metrics=metrics)

# -------------------------
# UPDATE STATUS
# -------------------------

@app.route("/update_status", methods=["POST"])
def update_status():
    if "username" not in session:
        return redirect(url_for("login"))

    lead_id = request.form["lead_id"]
    new_status = request.form["status"]

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if session["role"] == "director":
        cursor.execute("UPDATE leads SET status = ? WHERE id = ?", (new_status, lead_id))
    else:
        cursor.execute("UPDATE leads SET status = ? WHERE id = ? AND agent = ?",
                       (new_status, lead_id, session["username"]))

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))

# -------------------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -------------------------

if __name__ == "__main__":
    app.run(debug=True)
