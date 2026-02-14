from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
import psycopg2
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

# =============================
# CONFIGURACIÓN
# =============================

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
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
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
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    # Crear director si no existe
    cursor.execute("SELECT * FROM users WHERE username = %s", ("director",))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            ("director", generate_password_hash("1234"), "director")
        )

    # Crear agentes si no existen
    for agent in AGENTS:
        cursor.execute("SELECT * FROM users WHERE username = %s", (agent,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                (agent, generate_password_hash("1234"), "agent")
            )

    conn.commit()
    cursor.close()
    conn.close()

init_db()

# =============================
# UTILIDADES
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

    if "Seguro de Vida" in product:
        score += 10

    if dependents and dependents != "0":
        score += 5

    return min(score, 100)

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
        reply = "¿Cuánto puedes invertir al mes?"
        options = ["$1,500 – $2,500", "$2,500 – $4,000", "$4,000 – $7,000", "Más de $7,000"]
        state["level"] = "monthly_budget"

    elif state["level"] == "dependents_count":
        state["data"]["dependents_count"] = message
        reply = "¿Cuánto puedes invertir al mes?"
        options = ["$1,500 – $2,500", "$2,500 – $4,000", "$4,000 – $7,000", "Más de $7,000"]
        state["level"] = "monthly_budget"

    elif state["level"] == "monthly_budget":
        state["data"]["monthly_budget"] = message

        score = calculate_score(state["data"])
        priority = classify_lead(score)

        state["data"]["score"] = score
        state["data"]["priority"] = priority

        reply = f"Resumen:\nScore: {score}\nPrioridad: {priority}\n\nEscribe tu nombre completo."
        state["level"] = "name"

    elif state["level"] == "name":
        state["data"]["name"] = message
        reply = "Escribe tu número de WhatsApp."
        state["level"] = "phone"

    elif state["level"] == "phone":
        state["data"]["phone"] = message

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO leads (
                name, age, product_type, smoker, monthly_budget,
                dependents_count, phone, created_at, status, agent,
                score, priority
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            get_next_agent(),
            state["data"].get("score"),
            state["data"].get("priority")
        ))

        conn.commit()
        cursor.close()
        conn.close()

        reply = "Gracias. Un asesor te contactará pronto."
        state["level"] = "closed"

    return jsonify({"reply": reply, "options": options, "state": state})

# =============================
# SERVIDOR RENDER
# =============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
