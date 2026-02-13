from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"

AGENTS = ["agent1", "agent2", "agent3"]
STATUS_OPTIONS = ["Nuevo", "Contactado", "Cotizado", "Cerrado"]

agent_index = 0

# =========================
# BASE DE DATOS
# =========================

def init_db():
    conn = sqlite3.connect("database.db")
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
            agent TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()

# =========================
# ROTACIÓN AGENTE
# =========================

def get_next_agent():
    global agent_index
    agent = AGENTS[agent_index % len(AGENTS)]
    agent_index += 1
    return agent

# =========================
# HOME
# =========================

@app.route("/")
def home():
    return render_template("chat.html")

# =========================
# CHAT INTELIGENTE
# =========================

@app.route("/chat", methods=["POST"])
def chat():

    data = request.json
    message = data.get("message", "")
    state = data.get("state", {"level": "start", "data": {}})

    reply = ""
    options = []

    # ---------------- START ----------------
    if state["level"] == "start":
        reply = "Hola 👋\n\n¿Cuántos años tienes?"
        state["level"] = "age"

    # ---------------- EDAD ----------------
    elif state["level"] == "age":
        try:
            state["data"]["age"] = int(message)
            reply = "¿Qué estás buscando?"
            options = ["Gastos Médicos (MedicaLife)", "Seguro de Vida (MetaLife)"]
            state["level"] = "product_type"
        except:
            reply = "Por favor escribe tu edad en números."

    # ---------------- PRODUCTO ----------------
    elif state["level"] == "product_type":
        state["data"]["product_type"] = message

        if "Gastos Médicos" in message:
            reply = "¿Fumas?"
            options = ["Sí", "No"]
            state["level"] = "smoker"
        else:
            reply = "¿A qué edad te gustaría retirarte?"
            state["level"] = "retirement_age"

    # ---------------- GMM ----------------
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

    # ---------------- VIDA ----------------
    elif state["level"] == "retirement_age":
        state["data"]["retirement_age"] = message
        reply = "¿Cuántas personas dependen de ti?"
        state["level"] = "dependents_count"

    elif state["level"] == "dependents_count":
        state["data"]["dependents_count"] = message
        reply = "¿Cuánto te gustaría invertir al mes?"
        options = ["$1,500 – $2,500", "$2,500 – $4,000", "$4,000 – $7,000", "Más de $7,000"]
        state["level"] = "monthly_budget"

    # ---------------- PRESUPUESTO ----------------
    elif state["level"] == "monthly_budget":
        state["data"]["monthly_budget"] = message

        reply = (
            "Perfecto.\n\n"
            "Para generar tu resumen personalizado debes aceptar "
            "los términos y condiciones.\n\n"
            "Presiona el botón para continuar."
        )

        options = ["Generar resumen"]
        state["level"] = "generate_summary"

    # ---------------- GENERAR RESUMEN ----------------
    elif state["level"] == "generate_summary":
        summary = "📋 Resumen de tu perfil:\n\n"
        for k, v in state["data"].items():
            summary += f"{k.replace('_',' ').title()}: {v}\n"

        reply = summary + "\n\nEscribe tu nombre completo."
        state["level"] = "name"

    # ---------------- NOMBRE ----------------
    elif state["level"] == "name":
        state["data"]["name"] = message
        reply = "Escribe tu número de WhatsApp."
        state["level"] = "phone"

    # ---------------- TELÉFONO ----------------
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
            state["data"].get("name", ""),
            state["data"].get("age", 0),
            state["data"].get("product_type", ""),
            state["data"].get("smoker", ""),
            state["data"].get("payment_frequency", ""),
            state["data"].get("monthly_budget", ""),
            state["data"].get("retirement_age", ""),
            state["data"].get("dependents_count", ""),
            state["data"].get("retirement_goal", ""),
            state["data"].get("phone", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Nuevo",
            assigned_agent
        ))

        conn.commit()
        conn.close()

        reply = "Gracias 🙌 Un asesor se pondrá en contacto contigo."
        state["level"] = "closed"

    return jsonify({
        "reply": reply,
        "options": options,
        "state": state
    })


if __name__ == "__main__":
    app.run(debug=True)
