from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import psycopg2
import os
import random
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

AGENTS = ["agent1", "agent2", "agent3"]
STATUS_OPTIONS = ["Nuevo", "Contactado", "Cotizado", "Cerrado"]

# =========================
# CONEXIÓN DB
# =========================

def get_connection():
    return psycopg2.connect(DATABASE_URL)

# =========================
# INIT DB (POSTGRES)
# =========================

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id SERIAL PRIMARY KEY,
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
        created_at TIMESTAMP,
        status TEXT,
        agent TEXT,
        score INTEGER,
        priority TEXT,
        contacted_at TIMESTAMP,
        first_response_minutes INTEGER
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    );
    """)

    # Crear director
    cursor.execute("SELECT * FROM users WHERE username = %s", ("director",))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            ("director", generate_password_hash("1234"), "director")
        )

    # Crear agentes
    for agent in AGENTS:
        cursor.execute("SELECT * FROM users WHERE username = %s", (agent,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                (agent, generate_password_hash("1234"), "agent")
            )

    conn.commit()
    conn.close()

init_db()

# =========================
# LÓGICA SCORE
# =========================

def calculate_score(data):
    budget = data.get("monthly_budget", "")
    score = 0

    if "Más de $7,000" in budget:
        score = 90
    elif "$4,000" in budget:
        score = 75
    elif "$2,500" in budget:
        score = 60
    elif "$1,500" in budget:
        score = 45

    if "Seguro de Vida" in data.get("product_type", ""):
        score += 10

    if data.get("dependents_count") and data.get("dependents_count") != "0":
        score += 5

    return min(score, 100)

def classify_lead(score):
    if score >= 85:
        return "Caliente"
    elif score >= 65:
        return "Medio"
    else:
        return "Bajo"

# =========================
# CHAT
# =========================

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
            reply = "Escribe tu edad en números."

    elif state["level"] == "product_type":
        state["data"]["product_type"] = message

        if "Gastos Médicos" in message:
            reply = "¿Fumas?"
            options = ["Sí", "No"]
            state["level"] = "smoker"
        else:
            reply = "¿Cuántas personas dependen de ti?"
            state["level"] = "dependents_count"

    elif state["level"] == "smoker":
        state["data"]["smoker"] = message
        reply = "¿Cuánto podrías invertir al mes?"
        options = ["$1,500 – $2,500", "$2,500 – $4,000", "$4,000 – $7,000", "Más de $7,000"]
        state["level"] = "monthly_budget"

    elif state["level"] == "dependents_count":
        state["data"]["dependents_count"] = message
        reply = "¿Cuánto te gustaría invertir al mes?"
        options = ["$1,500 – $2,500", "$2,500 – $4,000", "$4,000 – $7,000", "Más de $7,000"]
        state["level"] = "monthly_budget"

    elif state["level"] == "monthly_budget":
        state["data"]["monthly_budget"] = message
        reply = "Presiona generar resumen para continuar."
        options = ["Generar resumen"]
        state["level"] = "awaiting_summary"

    elif state["level"] == "awaiting_summary":
        if message == "Generar resumen":
            summary = "\nResumen:\n\n"
            for k, v in state["data"].items():
                summary += f"{k}: {v}\n"
            reply = summary + "\nEscribe tu nombre completo."
            state["level"] = "name"
        else:
            reply = "Presiona el botón."

    elif state["level"] == "name":
        state["data"]["name"] = message
        reply = "Escribe tu número de WhatsApp."
        state["level"] = "phone"

    elif state["level"] == "phone":
        state["data"]["phone"] = message

        assigned_agent = random.choice(AGENTS)

        score = calculate_score(state["data"])
        priority = classify_lead(score)

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO leads (
            name, age, product_type, smoker,
            monthly_budget, dependents_count,
            phone, created_at, status,
            agent, score, priority
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            state["data"].get("name"),
            state["data"].get("age"),
            state["data"].get("product_type"),
            state["data"].get("smoker"),
            state["data"].get("monthly_budget"),
            state["data"].get("dependents_count"),
            state["data"].get("phone"),
            datetime.now(),
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

# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username, password, role FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session["username"] = user[0]
            session["role"] = user[2]
            return redirect(url_for("dashboard"))
        else:
            return "Credenciales incorrectas"

    return render_template("login.html")

# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
def dashboard():

    if "username" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor()

    metrics = {}
    leads = []

    if session["role"] == "director":

        # Leads ordenados
        cursor.execute("SELECT * FROM leads ORDER BY score DESC, created_at DESC")
        leads = cursor.fetchall()

        # Totales
        cursor.execute("SELECT COUNT(*) FROM leads")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'Cerrado'")
        closed = cursor.fetchone()[0]

        close_rate = round((closed / total) * 100, 2) if total > 0 else 0

        # Por agente
        cursor.execute("""
            SELECT agent, COUNT(*)
            FROM leads
            GROUP BY agent
        """)
        by_agent = cursor.fetchall()

        # Por estado
        cursor.execute("""
            SELECT status, COUNT(*)
            FROM leads
            GROUP BY status
        """)
        by_status = cursor.fetchall()

        # 🚨 Leads nuevos > 2h
        cursor.execute("""
            SELECT created_at
            FROM leads
            WHERE status = 'Nuevo'
        """)
        new_leads = cursor.fetchall()

        overdue = 0
        now = datetime.now()

        for row in new_leads:
            if row[0] and now - row[0] > timedelta(hours=2):
                overdue += 1

        # ⏱ Promedio respuesta
        cursor.execute("""
            SELECT agent, AVG(first_response_minutes)
            FROM leads
            WHERE first_response_minutes IS NOT NULL
            GROUP BY agent
        """)
        response_times = cursor.fetchall()

        # =========================
        # RANKING MENSUAL
        # =========================

        cursor.execute("""
            SELECT 
                agent,
                COUNT(*) as total_mes,
                SUM(CASE WHEN status = 'Cerrado' THEN 1 ELSE 0 END) as cerrados_mes
            FROM leads
            WHERE date_trunc('month', created_at) = date_trunc('month', CURRENT_DATE)
            GROUP BY agent
        """)

        ranking_mes_raw = cursor.fetchall()
        ranking_mes = []

        for row in ranking_mes_raw:
            agent = row[0]
            total_mes = row[1]
            cerrados_mes = row[2] or 0

            tasa = round((cerrados_mes / total_mes) * 100, 2) if total_mes > 0 else 0

            ranking_mes.append({
                "agent": agent,
                "total": total_mes,
                "cerrados": cerrados_mes,
                "tasa": tasa
            })

        ranking_mes = sorted(
            ranking_mes,
            key=lambda x: (x["cerrados"], x["tasa"]),
            reverse=True
        )

        # =========================
        # RANKING HISTÓRICO
        # =========================

        cursor.execute("""
            SELECT 
                agent,
                COUNT(*) as total_hist,
                SUM(CASE WHEN status = 'Cerrado' THEN 1 ELSE 0 END) as cerrados_hist,
                AVG(first_response_minutes)
            FROM leads
            GROUP BY agent
        """)

        ranking_hist_raw = cursor.fetchall()
        ranking_hist = []

        for row in ranking_hist_raw:
            agent = row[0]
            total_hist = row[1]
            cerrados_hist = row[2] or 0
            avg_resp = round(row[3], 1) if row[3] else 0

            tasa_hist = round((cerrados_hist / total_hist) * 100, 2) if total_hist > 0 else 0

            ranking_hist.append({
                "agent": agent,
                "total": total_hist,
                "cerrados": cerrados_hist,
                "tasa": tasa_hist,
                "avg_resp": avg_resp
            })

        ranking_hist = sorted(
            ranking_hist,
            key=lambda x: (x["cerrados"], x["tasa"]),
            reverse=True
        )

        metrics = {
            "total": total,
            "closed": closed,
            "close_rate": close_rate,
            "by_agent": by_agent,
            "by_status": by_status,
            "overdue": overdue,
            "response_times": response_times,
            "ranking_mes": ranking_mes,
            "ranking_hist": ranking_hist
        }

    else:
    # Leads del agente
        cursor.execute("""
            SELECT * FROM leads
            WHERE agent = %s
            ORDER BY score DESC, created_at DESC
        """, (session["username"],))
        leads = cursor.fetchall()

    # Total asignados
        cursor.execute("""
            SELECT COUNT(*) FROM leads
            WHERE agent = %s
        """, (session["username"],))
        total_agent = cursor.fetchone()[0]

    # Cerrados
        cursor.execute("""
            SELECT COUNT(*) FROM leads
            WHERE agent = %s AND status = 'Cerrado'
        """, (session["username"],))
        closed_agent = cursor.fetchone()[0]

    # Tasa de cierre
        close_rate_agent = round(
        (closed_agent / total_agent) * 100, 2
    ) if total_agent > 0 else 0

    # Leads nuevos > 2h
        cursor.execute("""
            SELECT created_at FROM leads
            WHERE agent = %s AND status = 'Nuevo'
        """, (session["username"],))

        new_leads = cursor.fetchall()
        overdue_agent = 0
        now = datetime.now()

    total_agent = len(leads)

    closed_agent = len([l for l in leads if l[12] == "Cerrado"])

    close_rate_agent = round((closed_agent / total_agent) * 100, 2) if total_agent > 0 else 0

    overdue_agent = 0
    now = datetime.now()

    for lead in leads:
        if lead[12] == "Nuevo" and lead[11]:
            if now - lead[11] > timedelta(hours=2):
                overdue_agent += 1

    cursor.execute("""
        SELECT AVG(first_response_minutes)
        FROM leads
        WHERE agent = %s AND first_response_minutes IS NOT NULL
    """, (session["username"],))

    avg_resp = cursor.fetchone()[0]
    avg_response_agent = round(avg_resp, 1) if avg_resp else 0

    metrics = {
        "total_agent": total_agent,
        "closed_agent": closed_agent,
        "close_rate_agent": close_rate_agent,
        "overdue_agent": overdue_agent,
        "avg_response_agent": avg_response_agent
    }


    for row in new_leads:
        if row[0] and now - row[0] > timedelta(hours=2):
            overdue_agent += 1

    # Promedio respuesta
        cursor.execute("""
            SELECT AVG(first_response_minutes)
            FROM leads
            WHERE agent = %s AND first_response_minutes IS NOT NULL
        """, (session["username"],))

        avg_response = cursor.fetchone()[0]
        avg_response = round(avg_response, 1) if avg_response else 0

        metrics = {
            "total_agent": total_agent,
            "closed_agent": closed_agent,
            "close_rate_agent": close_rate_agent,
            "overdue_agent": overdue_agent,
            "avg_response_agent": avg_response
    }

        cursor.close()
        conn.close()

    return render_template(
        "dashboard.html",
        leads=leads,
        role=session["role"],
        username=session["username"],
        status_options=STATUS_OPTIONS,
        metrics=metrics
    )



@app.route("/lead/<int:lead_id>")
def lead_detail(lead_id):

    if "username" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor()

    if session["role"] == "director":
        cursor.execute(
            "SELECT * FROM leads WHERE id = %s",
            (lead_id,)
        )
    else:
        cursor.execute(
            "SELECT * FROM leads WHERE id = %s AND agent = %s",
            (lead_id, session["username"])
        )

    lead = cursor.fetchone()

    cursor.close()
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

# =========================

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)

