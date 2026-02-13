from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "super_secret_key"

AGENTS = ["Ana", "Luis", "Marco"]
agent_index = 0

STATUS_OPTIONS = ["Nuevo", "Contactado", "Cotizado", "Cerrado", "Perdido"]

# -------------------------
# DATABASE SETUP
# -------------------------

def init_db():
    def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # ===== TABLA LEADS NUEVA =====
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

    # ===== CREAR DIRECTOR =====
    cursor.execute("SELECT * FROM users WHERE username = ?", ("director",))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (username, password, role)
            VALUES (?, ?, ?)
        """, ("director", generate_password_hash("1234"), "director"))

    # ===== CREAR AGENTES =====
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
# ROTACIÓN AGENTES
# -------------------------

def get_next_agent():
    global agent_index
    agent = AGENTS[agent_index % len(AGENTS)]
    agent_index += 1
    return agent

# -------------------------
# CHAT
# -------------------------

@app.route("/")
def home():
    return render_template("chat.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    state = data.get("state", {"level": "start", "data": {}})

    reply = ""
    options = []

    # ================= START =================
    if state["level"] == "start":
        reply = ("Hola 👋\n\n"
                 "Soy el asistente digital de protección financiera.\n"
                 "En menos de 3 minutos puedo ayudarte a identificar la estrategia adecuada para ti.\n\n"
                 "Para comenzar, ¿cuántos años tienes?")
        state["level"] = "age"

    # ================= AGE =================
    elif state["level"] == "age":
        try:
            age = int(message)
            state["data"]["age"] = age
            reply = "¿Hay personas que dependan económicamente de ti?"
            options = ["Sí", "No"]
            state["level"] = "dependents"
        except:
            reply = "Por favor ingresa tu edad en números."

    # ================= DEPENDENTS =================
    elif state["level"] == "dependents":
        state["data"]["dependents"] = message
        reply = "¿Qué te preocupa más actualmente?"
        options = [
            "Proteger a mi familia",
            "Gastos médicos",
            "Ambas",
            "No estoy seguro"
        ]
        state["level"] = "priority"

    # ================= PRIORITY =================
    elif state["level"] == "priority":
        state["data"]["priority"] = message
        reply = ("De manera aproximada, ¿qué monto mensual estarías dispuesto a invertir en tu protección?")
        options = [
            "$1,500 – $2,500",
            "$2,500 – $4,000",
            "$4,000 – $7,000",
            "Más de $7,000"
        ]
        state["level"] = "budget"

    # ================= BUDGET =================
    elif state["level"] == "budget":
        state["data"]["budget"] = message

        dependents = state["data"]["dependents"]
        priority = state["data"]["priority"]

        if priority == "Proteger a mi familia":
            product = "MetaLife"
        elif priority == "Gastos médicos":
            product = "MedicaLife"
        elif priority == "Ambas":
            product = "MetaLife + MedicaLife"
        else:
            if dependents == "Sí":
                product = "MetaLife"
            else:
                product = "MedicaLife"

        state["data"]["recommended_product"] = product

        reply = (f"Resultado de Evaluación:\n\n"
                 f"Producto Recomendado: {product}\n\n"
                 "Con base en tu perfil y el monto que deseas invertir, "
                 "existe una estrategia de protección adecuada para ti.\n\n"
                 "¿Cómo prefieres continuar?")

        options = [
            "Quiero que me contacten",
            {
                "label": "Contactar ahora por WhatsApp",
                "url": "https://wa.me/5216646346643"
            }
        ]

        state["level"] = "decision"

    # ================= DECISION =================
    elif state["level"] == "decision":

        if message == "Quiero que me contacten":
            reply = "Perfecto. Por favor escribe tu nombre completo."
            state["level"] = "name"

    # ================= NAME =================
    elif state["level"] == "name":
        state["data"]["name"] = message
        reply = "Ahora escribe tu número de WhatsApp para que podamos contactarte."
        state["level"] = "phone"

    # ================= PHONE =================
    elif state["level"] == "phone":
        state["data"]["phone"] = message

        assigned_agent = get_next_agent()

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO leads (name, age, children, score, phone, created_at, status, agent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state["data"]["name"],
            state["data"].get("age", 0),
            state["data"].get("dependents", ""),
            0,
            state["data"]["phone"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Nuevo",
            assigned_agent
        ))

        conn.commit()
        conn.close()

        reply = ("Gracias.\n\n"
                 "Tu información ha sido enviada correctamente.\n"
                 "Un asesor se pondrá en contacto contigo en breve.")

        state["level"] = "closed"

    return jsonify({
        "reply": reply,
        "options": options,
        "state": state
    })


# -------------------------
# LOGIN (SEGURO)
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
