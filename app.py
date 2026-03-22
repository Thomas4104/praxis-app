from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

DB_PATH = '/home/ubuntu/praxis-app/praxis.db'

client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

SYSTEM_PROMPT = """Du bist der KI-Assistent einer Praxis-Planungssoftware fuer Physiotherapie, Psychotherapie und Aerzte in der Schweiz.

Du hilfst bei:
- Terminplanung
- Patientenverwaltung
- Abrechnung
- Buchhaltung
- HR und Personalverwaltung

Antworte immer auf Deutsch. Sei freundlich, professionell und praezise.
Wenn du etwas nicht weisst oder eine Funktion noch nicht verfuegbar ist, sage das ehrlich.
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    existing = conn.execute('SELECT id FROM users WHERE username = ?', ('admin',)).fetchone()
    if not existing:
        conn.execute('INSERT INTO users (username, password_hash, name) VALUES (?, ?, ?)',
                     ('admin', generate_password_hash('admin123'), 'Administrator'))
    conn.commit()
    conn.close()


class User(UserMixin):
    def __init__(self, id, username, name):
        self.id = id
        self.username = username
        self.name = name


@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user['id'], user['username'], user['name'])
    return None


@app.route('/')
@login_required
def home():
    conn = get_db()
    messages = conn.execute(
        'SELECT role, content, created_at FROM chat_messages WHERE user_id = ? ORDER BY created_at ASC LIMIT 50',
        (current_user.id,)
    ).fetchall()
    conn.close()
    return render_template('dashboard.html', user=current_user, messages=messages)


@app.route('/chat', methods=['POST'])
@login_required
def chat():
    user_message = request.json.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'Keine Nachricht'}), 400

    conn = get_db()

    conn.execute('INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)',
                 (current_user.id, 'user', user_message))

    history = conn.execute(
        'SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY created_at ASC LIMIT 20',
        (current_user.id,)
    ).fetchall()

    api_messages = [{'role': msg['role'], 'content': msg['content']} for msg in history]

    try:
        response = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=api_messages
        )
        assistant_message = response.content[0].text
    except Exception as e:
        assistant_message = f'Fehler bei der KI-Anfrage: {str(e)}'

    conn.execute('INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)',
                 (current_user.id, 'assistant', assistant_message))
    conn.commit()
    conn.close()

    return jsonify({'response': assistant_message})


@app.route('/chat/clear', methods=['POST'])
@login_required
def clear_chat():
    conn = get_db()
    conn.execute('DELETE FROM chat_messages WHERE user_id = ?', (current_user.id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            login_user(User(user['id'], user['username'], user['name']))
            return redirect(url_for('home'))
        flash('Benutzername oder Passwort falsch')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


init_db()

if __name__ == '__main__':
    app.run()
