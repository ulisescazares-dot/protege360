from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
import psycopg2
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL")
app = Flask(__name__)
app.secret_key = "supersecretkey"

AGENTS = ["agent1", "agent2", "agent3"]
STATUS_OPTIONS = ["Nuevo", "Contactado", "Cotizado", "Cerrado"]

agent_index = 0

# =============================
# BASE DE DATOS
# =============================

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

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
            agent TEXT,
            score INTEGER,
            priority TEXT,
            contacted_at TEXT,
            first_response_minutes INTENGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    # Director
    cursor.execute("SELECT * FROM users WHERE username = ?", ("director",))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("director", generate_password_hash("1234"), "director")
        )

    # Agentes
    for agent in AGENTS:
        cursor.execute("SELECT * FROM users WHERE username = ?", (agent,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (agent, generate_password_hash("1234"), "agent")
            )

    conn.commit()
    conn.close()

init_db()

# =============================
# ROTACIÓN AGENTES
# =============================

def get_next_agent():
    global agent_index
    agent = AGENTS[agent_index % len(AGENTS)]
    agent_index += 1
    return agent




def calculate_score(data):

    budget = data.get("monthly_budget", "")
    product = data.get("product_type", "")
    dependents = data.get("dependents_count", "")

    score = 0

    if "Más de $7,000" in budget:
        score = 90
    elif "$4,000" in budget:
        score = 75
    elif "$2,500" in budget:
        score = 60
    elif "$1,500" in budget:
        score = 45

    # Bonus vida
    if "Seguro de Vida" in product:
        score += 10

    # Bonus dependientes
    if dependents and dependents != "0":
        score += 5

    if score > 100:
        score = 100

    return score



def classify_lead(score):
    if score >= 85:
        return "Caliente"
    elif score >= 65:
        return "Medio"
    else:
        return "Bajo"

# =============================
# CHAT
# =============================

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

    # START
    if state["level"] == "start":
        reply = "Hola 👋 ¿Cuántos años tienes?"
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

    # GMM FLOW
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

    # VIDA FLOW
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
        reply = "Para generar tu resumen, acepta los términos y presiona generar resumen."
        options = ["Generar resumen"]
        state["level"] = "awaiting_summary"

    elif state["level"] == "awaiting_summary":
        if message == "Generar resumen":
            summary = "Resumen de tu perfil:\n\n"
            for k, v in state["data"].items():
                summary += f"{k.replace('_',' ').title()}: {v}\n"

            reply = summary + "\n\nPor favor escribe tu nombre completo."
            state["level"] = "name"
        else:
            reply = "Presiona el botón 'Generar resumen'."

    elif state["level"] == "name":
        state["data"]["name"] = message
        reply = "Escribe tu número de WhatsApp."
        state["level"] = "phone"

    elif state["level"] == "phone":
        state["data"]["phone"] = message

        assigned_agent = get_next_agent()
        
        score = calculate_score(state["data"])
        priority = classify_lead(score)

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO leads (
                name, age, product_type, smoker, payment_frequency,
                monthly_budget, retirement_age, dependents_count,
                retirement_goal, phone, created_at, status, agent, score, priority
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            assigned_agent,
            score,
            priority
        ))

        conn.commit()
        conn.close()

        reply = "Gracias. Un asesor se pondrá en contacto contigo."
        state["level"] = "closed"

    return jsonify({"reply": reply, "options": options, "state": state})



@app.route("/manifest.json")
def manifest():
    return send_from_directory(".", "manifest.json")


# =============================
# LOGIN
# =============================

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

# =============================
# DASHBOARD
# =============================

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    leads = []
    metrics = None

    # ================= DIRECTOR =================
    if session["role"] == "director":

        cursor.execute(
            "SELECT * FROM leads ORDER BY score DESC, created_at DESC"
        )
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

        # 🔥 ALERTAS AUTOMÁTICAS
        from datetime import timedelta

        now = datetime.now()

        cursor.execute("""
            SELECT created_at FROM leads
            WHERE status = 'Nuevo'
        """)
        nuevo_leads = cursor.fetchall()

        overdue = 0

        for lead in nuevo_leads:
            created = datetime.strptime(lead[0], "%Y-%m-%d %H:%M:%S")
            if now - created > timedelta(hours=2):
                overdue += 1

        # Promedio tiempo respuesta por agente
        cursor.execute("""
            SELECT agent, AVG(first_response_minutes)
            FROM leads
            WHERE first_response_minutes IS NOT NULL
            GROUP BY agent
        """)
        response_times = cursor.fetchall()

        metrics = {
            "total": total,
            "closed": closed,
            "close_rate": close_rate,
            "by_agent": by_agent,
            "by_status": by_status,
            "overdue": overdue,
            "response_times": response_times
        }

    # ================= AGENTE =================
    else:
        cursor.execute(
            "SELECT * FROM leads WHERE agent = ? ORDER BY score DESC, created_at DESC",
            (session["username"],)
        )
        leads = cursor.fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        leads=leads,
        role=session["role"],
        username=session["username"],
        status_options=STATUS_OPTIONS,
        metrics=metrics
    )


@app.route("/update_status", methods=["POST"])
def update_status():
    if "username" not in session:
        return redirect(url_for("login"))

    lead_id = request.form["lead_id"]
    new_status = request.form["status"]

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Obtener datos actuales del lead
    cursor.execute("SELECT status, created_at, contacted_at FROM leads WHERE id = ?", (lead_id,))
    lead = cursor.fetchone()

    if not lead:
        conn.close()
        return redirect(url_for("dashboard"))

    current_status = lead[0]
    created_at = lead[1]
    contacted_at = lead[2]

    # Si cambia a Contactado por primera vez
    if new_status == "Contactado" and not contacted_at:
        now = datetime.now()
        created_time = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")

        minutes_diff = int((now - created_time).total_seconds() / 60)

        cursor.execute("""
            UPDATE leads
            SET status = ?, contacted_at = ?, first_response_minutes = ?
            WHERE id = ?
        """, (
            new_status,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            minutes_diff,
            lead_id
        ))
    else:
        # Solo actualizar estado normal
        if session["role"] == "director":
            cursor.execute("UPDATE leads SET status = ? WHERE id = ?", (new_status, lead_id))
        else:
            cursor.execute(
                "UPDATE leads SET status = ? WHERE id = ? AND agent = ?",
                (new_status, lead_id, session["username"])
            )

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


@app.route("/lead/<int:lead_id>")
def lead_detail(lead_id):

    if "username" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if session["role"] == "director":
        cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    else:
        cursor.execute("SELECT * FROM leads WHERE id = ? AND agent = ?",
                       (lead_id, session["username"]))

    lead = cursor.fetchone()
    conn.close()

    if not lead:
        return "Lead no encontrado"

    return render_template(
        "lead_detail.html",
        lead=lead,
        role=session["role"],
        username=session["username"],
        status_options=STATUS_OPTIONS
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

