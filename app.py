import os
import json
import sqlite3
from flask import Flask, request, jsonify, render_template, session
from datetime import datetime
import uuid
from providers import get_provider

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-production")

DB_PATH = "memory/chat.db"

def init_db():
    os.makedirs("memory", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            name TEXT,
            provider TEXT,
            model TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    conn = get_db()
    sessions = conn.execute(
        "SELECT * FROM sessions ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(s) for s in sessions])

@app.route("/api/sessions", methods=["POST"])
def create_session():
    data = request.json
    sid = str(uuid.uuid4())[:8]
    name = data.get("name", f"Chat {sid}")
    provider = data.get("provider", "openai")
    model = data.get("model", "gpt-4o")
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?)",
        (sid, name, provider, model, now, now)
    )
    conn.commit()
    conn.close()
    return jsonify({"id": sid, "name": name, "provider": provider, "model": model, "created_at": now, "updated_at": now})

@app.route("/api/sessions/<sid>", methods=["DELETE"])
def delete_session(sid):
    conn = get_db()
    conn.execute("DELETE FROM messages WHERE session_id=?", (sid,))
    conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/sessions/<sid>/messages", methods=["GET"])
def get_messages(sid):
    conn = get_db()
    msgs = conn.execute(
        "SELECT * FROM messages WHERE session_id=? ORDER BY id",
        (sid,)
    ).fetchall()
    conn.close()
    return jsonify([dict(m) for m in msgs])

@app.route("/api/sessions/<sid>/chat", methods=["POST"])
def chat(sid):
    data = request.json
    user_msg = data.get("message", "").strip()
    api_key = data.get("api_key", "")

    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    conn = get_db()
    sess = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not sess:
        conn.close()
        return jsonify({"error": "Session not found"}), 404

    history = conn.execute(
        "SELECT role, content FROM messages WHERE session_id=? ORDER BY id",
        (sid,)
    ).fetchall()

    messages = [{"role": r["role"], "content": r["content"]} for r in history]
    messages.append({"role": "user", "content": user_msg})

    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)",
        (sid, "user", user_msg, now)
    )

    try:
        provider = get_provider(sess["provider"])
        reply = provider.chat(
            model=sess["model"],
            messages=messages,
            api_key=api_key
        )
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500

    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)",
        (sid, "assistant", reply, datetime.utcnow().isoformat())
    )
    conn.execute(
        "UPDATE sessions SET updated_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), sid)
    )
    conn.commit()
    conn.close()

    return jsonify({"reply": reply})

@app.route("/api/providers", methods=["GET"])
def list_providers():
    return jsonify([
        {"id": "openai",    "name": "OpenAI",     "models": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]},
        {"id": "anthropic", "name": "Anthropic",  "models": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]},
        {"id": "gemini",    "name": "Google Gemini", "models": ["gemini-2.0-flash", "gemini-1.5-pro"]},
        {"id": "ollama",    "name": "Ollama (local)", "models": ["llama3", "mistral", "phi3", "gemma2"]},
    ])

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
