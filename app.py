from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash, send_from_directory, Response, make_response
from werkzeug.utils import secure_filename
from functools import wraps
import uuid
from flask_session import Session
from flask_socketio import SocketIO, emit, join_room as sio_join, leave_room as sio_leave
import json
import random
import time
import os
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import sqlite3
import bcrypt
import urllib.request
import urllib.error
from openai import OpenAI

# the newest OpenAI model is "gpt-5" which was released August 7, 2025.
# do not change this unless explicitly requested by the user
_ai_client = None

def get_ai_client():
    global _ai_client
    if _ai_client is None:
        _ai_client = OpenAI(
            api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
            base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
        )
    return _ai_client

app = Flask(__name__)
app.secret_key = 'tau-online-study-secret-key-2025'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
app.config['SESSION_PERMANENT'] = False
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
Session(app)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading', logger=False, engineio_logger=False)

# ── Socket room tracking (sid → room info) ─────────────────────────────────────
socket_rooms = {}  # request.sid -> {code, name, email}

def _maybe_expire_room(code):
    """Auto-delete room + messages when the last member disconnects."""
    if not code:
        return
    still_in = [s for s, info in socket_rooms.items() if info.get('code') == code]
    if still_in:
        return
    try:
        db = get_mongo()
        if db is not None:
            db.rooms.delete_one({'code': code})
            db.messages.delete_many({'room_code': code})
        else:
            conn = get_db()
            conn.execute('DELETE FROM rooms WHERE code = ?', (code,))
            conn.execute('DELETE FROM room_messages WHERE room_code = ?', (code,))
            conn.commit()
            conn.close()
        print(f'[Room] {code} auto-expired — all members left')
    except Exception as e:
        print(f'[Room] expire error for {code}: {e}')

# ── MongoDB Setup ──────────────────────────────────────────────────────────────
mongo_client = None
mongo_db = None

def get_mongo():
    global mongo_client, mongo_db
    if mongo_db is not None:
        return mongo_db
    uri = os.environ.get('MONGODB_URI')
    if not uri:
        return None
    try:
        from pymongo import MongoClient
        mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ping')
        db_name = os.environ.get('MONGODB_DB_NAME', 'tau_study')
        mongo_db = mongo_client[db_name]
        # Ensure unique index on email
        mongo_db.users.create_index('email', unique=True)
        print("✅ Connected to MongoDB")
        return mongo_db
    except Exception as e:
        print(f"⚠️  MongoDB unavailable: {e}")
        return None

# ── SQLite fallback ────────────────────────────────────────────────────────────
DB_PATH = 'exam_results.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  regno TEXT NOT NULL UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS exam_attempts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  student_id INTEGER NOT NULL,
                  exam_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  total_score REAL,
                  total_questions INTEGER,
                  percentage REAL,
                  FOREIGN KEY(student_id) REFERENCES students(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS subject_scores
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  attempt_id INTEGER NOT NULL,
                  subject TEXT,
                  score INTEGER,
                  total INTEGER,
                  FOREIGN KEY(attempt_id) REFERENCES exam_attempts(id))''')
    # Local users table (fallback when MongoDB is unavailable)
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  full_name TEXT NOT NULL,
                  email TEXT NOT NULL UNIQUE,
                  password_hash TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    # Group study rooms
    c.execute('''CREATE TABLE IF NOT EXISTS rooms
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  code TEXT NOT NULL UNIQUE,
                  creator_email TEXT,
                  creator_name TEXT,
                  password_hash TEXT,
                  has_password INTEGER DEFAULT 0,
                  members TEXT DEFAULT '[]',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS room_messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  msg_id TEXT NOT NULL UNIQUE,
                  room_code TEXT NOT NULL,
                  data TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    # Password reset tokens
    c.execute('''CREATE TABLE IF NOT EXISTS password_reset_tokens
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT NOT NULL,
                  token TEXT NOT NULL UNIQUE,
                  expires_at TEXT NOT NULL,
                  used INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ── Auth helpers ───────────────────────────────────────────────────────────────
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def send_reset_email(to_email, reset_url):
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', '587'))
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_password = os.environ.get('SMTP_PASSWORD', '')

    if not smtp_user or not smtp_password:
        print(f'⚠️  Email not configured. Reset URL for {to_email}: {reset_url}')
        return False

    subject = 'Reset your Beyond The Classroom password'
    html_body = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;background:#05060f;color:#f0f0f8;padding:40px;border-radius:16px;">
      <div style="text-align:center;margin-bottom:32px;">
        <div style="display:inline-block;background:linear-gradient(135deg,#137a13,#1aaa1a);padding:14px 22px;border-radius:12px;font-size:1.3rem;font-weight:700;color:white;letter-spacing:1px;">BTC</div>
        <h2 style="margin:18px 0 6px;font-size:1.5rem;">Reset Your Password</h2>
        <p style="color:#8888aa;font-size:0.9rem;">Beyond The Classroom</p>
      </div>
      <p style="color:#ccc;line-height:1.6;">We received a request to reset the password for your account. Click the button below to choose a new password.</p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{reset_url}" style="background:linear-gradient(135deg,#137a13,#1aaa1a);color:white;padding:14px 32px;border-radius:10px;text-decoration:none;font-weight:600;font-size:1rem;display:inline-block;">Reset Password</a>
      </div>
      <p style="color:#8888aa;font-size:0.82rem;line-height:1.6;">This link will expire in <strong style="color:#f0f0f8;">1 hour</strong>. If you didn't request a password reset, you can safely ignore this email.</p>
      <hr style="border:none;border-top:1px solid rgba(255,255,255,0.1);margin:24px 0;">
      <p style="color:#4a4a6a;font-size:0.75rem;text-align:center;">If the button doesn't work, copy and paste this link:<br><span style="color:#1aaa1a;word-break:break-all;">{reset_url}</span></p>
    </div>
    """
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f'Beyond The Classroom <{smtp_user}>'
        msg['To'] = to_email
        msg.attach(MIMEText(html_body, 'html'))
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
        print(f'✅ Reset email sent to {to_email}')
        return True
    except Exception as e:
        print(f'⚠️  Failed to send reset email: {e}')
        return False

def create_user(full_name, email, password):
    hashed = hash_password(password)
    db = get_mongo()
    if db is not None:
        try:
            db.users.insert_one({
                'full_name': full_name,
                'email': email,
                'password_hash': hashed,
                'created_at': datetime.utcnow()
            })
            return True, None
        except Exception as e:
            if 'duplicate' in str(e).lower() or 'E11000' in str(e):
                return False, 'An account with this email already exists.'
            return False, str(e)
    else:
        # SQLite fallback
        try:
            conn = get_db()
            conn.execute(
                'INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)',
                (full_name, email, hashed)
            )
            conn.commit()
            conn.close()
            return True, None
        except sqlite3.IntegrityError:
            return False, 'An account with this email already exists.'

def find_user_by_email(email):
    db = get_mongo()
    if db is not None:
        return db.users.find_one({'email': email})
    else:
        conn = get_db()
        row = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

# ── Misc helpers ───────────────────────────────────────────────────────────────
def load_questions(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def float_safe(val):
    try:
        return float(str(val).strip())
    except:
        return str(val).strip()

def logged_in():
    return 'user' in session

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not logged_in():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

ADMIN_CREDENTIALS = {
    'okeyodekingdavid@gmail.com': '@King2024',
    'calebodusolu@gmail.com': 'qFVj8nvsaZfTFa6@@'
}

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def home():
    resp = make_response(render_template('home.html', user=session.get('user'), is_admin=session.get('admin_logged_in', False)))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

# ── Auth ───────────────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET'])
def login():
    if logged_in():
        return redirect(url_for('home'))
    tab = request.args.get('tab', 'login')
    return render_template('login.html', tab=tab)

@app.route('/signup', methods=['GET'])
def signup():
    return redirect(url_for('login', tab='signup'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

# ── API Proxy → Node.js backend on port 8000 ──────────────────────────────────
@app.route('/api/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def api_proxy(path):
    target_url = f'http://localhost:8000/api/{path}'
    method = request.method
    body = request.get_data()
    headers = {k: v for k, v in request.headers if k.lower() not in ('host', 'content-length')}
    if request.args:
        from urllib.parse import urlencode
        target_url += '?' + urlencode(request.args)
    try:
        req = urllib.request.Request(target_url, data=body if body else None, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
            status = resp.status
            resp_headers = dict(resp.headers)
    except urllib.error.HTTPError as e:
        content = e.read()
        status = e.code
        resp_headers = {}
    except Exception as e:
        return jsonify({'success': False, 'message': 'Auth service unavailable. Please try again shortly.'}), 503
    from flask import Response
    excluded = {'transfer-encoding', 'connection', 'content-encoding'}
    clean_headers = {k: v for k, v in resp_headers.items() if k.lower() not in excluded}
    return Response(content, status=status, headers=clean_headers)

# ── Password Reset ─────────────────────────────────────────────────────────────
RESET_COOLDOWN_SECONDS = 120  # 2-minute cooldown between reset email requests

@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'success': False, 'message': 'Email is required.'}), 400

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)
    now = datetime.utcnow()
    cooldown_cutoff = now - timedelta(seconds=RESET_COOLDOWN_SECONDS)
    user_found = False

    db = get_mongo()
    if db is not None:
        user = db.users.find_one({'email': email})
        if user:
            user_found = True
            recent = db.password_reset_tokens.find_one({
                'email': email,
                'created_at': {'$gt': cooldown_cutoff}
            })
            if recent:
                seconds_left = RESET_COOLDOWN_SECONDS - int((now - recent['created_at']).total_seconds())
                return jsonify({'success': False, 'message': f'Please wait {seconds_left} seconds before requesting another reset email.'}), 429
            db.password_reset_tokens.delete_many({'email': email})
            db.password_reset_tokens.create_index('expires_at', expireAfterSeconds=0)
            db.password_reset_tokens.insert_one({
                'email': email,
                'token': token,
                'expires_at': expires_at,
                'used': False,
                'created_at': now
            })
    else:
        conn = get_db()
        c = conn.cursor()
        user = c.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user:
            user_found = True
            recent = c.execute(
                'SELECT created_at FROM password_reset_tokens WHERE email = ? AND used = 0 ORDER BY created_at DESC LIMIT 1',
                (email,)
            ).fetchone()
            if recent:
                created_at = datetime.fromisoformat(recent['created_at'])
                elapsed = (now - created_at).total_seconds()
                if elapsed < RESET_COOLDOWN_SECONDS:
                    seconds_left = int(RESET_COOLDOWN_SECONDS - elapsed)
                    conn.close()
                    return jsonify({'success': False, 'message': f'Please wait {seconds_left} seconds before requesting another reset email.'}), 429
            c.execute('DELETE FROM password_reset_tokens WHERE email = ?', (email,))
            c.execute('INSERT INTO password_reset_tokens (email, token, expires_at) VALUES (?, ?, ?)',
                      (email, token, expires_at.isoformat()))
        conn.commit()
        conn.close()

    if user_found:
        reset_url = request.host_url.rstrip('/') + f'/reset-password/{token}'
        send_reset_email(email, reset_url)

    return jsonify({'success': True, 'message': 'If that email is registered, a reset link has been sent.'})


@app.route('/reset-password/<token>', methods=['GET'])
def reset_password_page(token):
    return render_template('reset_password.html', token=token)


@app.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get('token', '').strip()
    new_password = data.get('password', '')

    if not token or not new_password or len(new_password) < 8:
        return jsonify({'success': False, 'message': 'Invalid request.'}), 400

    new_hash = hash_password(new_password)
    now = datetime.utcnow()

    db = get_mongo()
    if db is not None:
        record = db.password_reset_tokens.find_one({
            'token': token,
            'used': False,
            'expires_at': {'$gt': now}
        })
        if not record:
            return jsonify({'success': False, 'message': 'This reset link is invalid or has expired.'}), 400
        db.users.update_one(
            {'email': record['email']},
            {'$set': {'password': new_hash, 'password_hash': new_hash}}
        )
        db.password_reset_tokens.update_one({'token': token}, {'$set': {'used': True}})
    else:
        conn = get_db()
        c = conn.cursor()
        record = c.execute(
            'SELECT * FROM password_reset_tokens WHERE token = ? AND used = 0 AND expires_at > ?',
            (token, now.isoformat())
        ).fetchone()
        if not record:
            conn.close()
            return jsonify({'success': False, 'message': 'This reset link is invalid or has expired.'}), 400
        c.execute('UPDATE users SET password_hash = ? WHERE email = ?', (new_hash, record['email']))
        c.execute('UPDATE password_reset_tokens SET used = 1 WHERE token = ?', (token,))
        conn.commit()
        conn.close()

    return jsonify({'success': True, 'message': 'Password updated successfully. You can now log in.'})


# ── Auth sync: JS calls this after JWT login to set Flask session ──────────────
@app.route('/auth/sync', methods=['POST'])
def auth_sync():
    data = request.get_json(silent=True) or {}
    user = data.get('user', {})
    if user:
        email = user.get('email', '')
        session['user'] = {
            'full_name': user.get('name', ''),
            'email': email
        }
        if email.lower() in ADMIN_CREDENTIALS:
            session['admin_logged_in'] = True
            session['admin_email'] = email.lower()
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'No user data'}), 400

# ── Exam registration ──────────────────────────────────────────────────────────
@app.route('/register-exam')
def register_page():
    session.pop('student_info', None)
    session['mode'] = 'exam'
    return render_template('registration.html')

@app.route('/practice')
def subject_selection_home():
    return render_template('practice_home.html')

@app.route('/practice/register')
def practice_register():
    session.pop('student_info', None)
    session['mode'] = 'practice'
    return render_template('registration.html')

@app.route('/register', methods=['POST'])
def register():
    name = request.form.get('name', '').strip()
    regno = request.form.get('regno', '').strip()
    if not name or not regno:
        return render_template('registration.html', error="Please enter both Name and Registration Number")
    session['student_info'] = {'name': name, 'regno': regno}
    return redirect(url_for('subject_selection'))

# ── University Course Catalogue ─────────────────────────────────────────────────
UNIVERSITY_COURSES = {
    'JAMB Preparation': {
        'All Subjects': {
            'UTME': [
                {'name': 'Biology', 'file': 'biology.json'},
                {'name': 'Chemistry', 'file': 'chemistry.json'},
                {'name': 'Physics', 'file': 'physics.json'},
                {'name': 'Mathematics', 'file': 'mathematics.json'},
                {'name': 'Use of English', 'file': 'use_of_english.json'},
                {'name': 'Government', 'file': 'government.json'},
                {'name': 'Economics', 'file': 'economics.json'},
                {'name': 'Commerce', 'file': 'commerce.json'},
                {'name': 'Literature in English', 'file': 'literature_in_english.json'},
                {'name': 'Christian Religious Studies', 'file': 'christian_religious_studies.json'},
                {'name': 'Principles of Accounts', 'file': 'principles_of_accounts.json'},
            ],
        },
    },
    'Faculty of Science': {
        'Computer Science': {
            '100': [
                {'name': 'Introduction to Programming', 'file': 'courses/cs_intro_programming.json'},
                {'name': 'Computer Fundamentals', 'file': 'courses/cs_computer_fundamentals.json'},
                {'name': 'Logic & Problem Solving', 'file': 'courses/cs_logic.json'},
                {'name': 'Mathematics I (Calculus)', 'file': 'courses/mth_calculus1.json'},
                {'name': 'Use of English', 'file': 'use_of_english.json'},
            ],
            '200': [
                {'name': 'Data Structures & Algorithms', 'file': 'courses/cs_data_structures.json'},
                {'name': 'Object-Oriented Programming', 'file': 'courses/cs_oop.json'},
                {'name': 'Computer Architecture', 'file': 'courses/cs_computer_architecture.json'},
                {'name': 'Discrete Mathematics', 'file': 'courses/cs_discrete_math.json'},
                {'name': 'Statistics for Computing', 'file': 'courses/mth_intro_stats.json'},
            ],
            '300': [
                {'name': 'Operating Systems', 'file': 'courses/cs_operating_systems.json'},
                {'name': 'Database Management Systems', 'file': 'courses/cs_database.json'},
                {'name': 'Computer Networks', 'file': 'courses/cs_networks.json'},
                {'name': 'Software Engineering', 'file': 'courses/cs_software_engineering.json'},
                {'name': 'Theory of Computation', 'file': 'courses/cs_theory_computation.json'},
            ],
            '400': [
                {'name': 'Artificial Intelligence', 'file': 'courses/cs_artificial_intelligence.json'},
                {'name': 'Machine Learning', 'file': 'courses/cs_machine_learning.json'},
                {'name': 'Cybersecurity', 'file': 'courses/cs_cybersecurity.json'},
                {'name': 'Compiler Design', 'file': 'courses/cs_compiler_design.json'},
                {'name': 'Distributed Systems', 'file': 'courses/cs_distributed_systems.json'},
            ],
        },
        'Mathematics': {
            '100': [
                {'name': 'Calculus I', 'file': 'courses/mth_calculus1.json'},
                {'name': 'Algebra & Trigonometry', 'file': 'courses/mth_algebra.json'},
                {'name': 'Introduction to Statistics', 'file': 'courses/mth_intro_stats.json'},
                {'name': 'Logic & Set Theory', 'file': 'courses/cs_logic.json'},
            ],
            '200': [
                {'name': 'Calculus II', 'file': 'courses/mth_calculus2.json'},
                {'name': 'Linear Algebra', 'file': 'courses/mth_linear_algebra.json'},
                {'name': 'Probability Theory', 'file': 'courses/mth_probability.json'},
                {'name': 'Differential Equations', 'file': 'courses/mth_differential_eq.json'},
            ],
            '300': [
                {'name': 'Real Analysis', 'file': 'courses/mth_real_analysis.json'},
                {'name': 'Abstract Algebra', 'file': 'courses/mth_abstract_algebra.json'},
                {'name': 'Numerical Methods', 'file': 'courses/mth_numerical.json'},
                {'name': 'Mathematical Statistics', 'file': 'courses/mth_intro_stats.json'},
            ],
            '400': [
                {'name': 'Operations Research', 'file': 'courses/mth_operations_research.json'},
                {'name': 'Graph Theory', 'file': 'courses/cs_discrete_math.json'},
                {'name': 'Functional Analysis', 'file': 'courses/mth_real_analysis.json'},
            ],
        },
        'Physics': {
            '100': [
                {'name': 'Classical Mechanics', 'file': 'courses/phy_mechanics.json'},
                {'name': 'Properties of Matter & Waves', 'file': 'courses/phy_waves.json'},
                {'name': 'Mathematics I', 'file': 'courses/mth_calculus1.json'},
            ],
            '200': [
                {'name': 'Electromagnetism', 'file': 'courses/phy_electromagnetism.json'},
                {'name': 'Thermodynamics', 'file': 'courses/phy_thermodynamics.json'},
                {'name': 'Modern Physics', 'file': 'courses/phy_modern.json'},
            ],
            '300': [
                {'name': 'Quantum Mechanics', 'file': 'courses/phy_quantum.json'},
                {'name': 'Solid State Physics', 'file': 'courses/phy_solid_state.json'},
                {'name': 'Optics', 'file': 'courses/phy_waves.json'},
            ],
            '400': [
                {'name': 'Nuclear Physics', 'file': 'courses/phy_nuclear.json'},
                {'name': 'Electronics', 'file': 'courses/eee_electronics1.json'},
                {'name': 'Statistical Mechanics', 'file': 'courses/phy_thermodynamics.json'},
            ],
        },
        'Chemistry': {
            '100': [
                {'name': 'General Chemistry I', 'file': 'courses/chm_general1.json'},
                {'name': 'Inorganic Chemistry I', 'file': 'courses/chm_inorganic1.json'},
            ],
            '200': [
                {'name': 'Organic Chemistry I', 'file': 'courses/chm_organic1.json'},
                {'name': 'Physical Chemistry I', 'file': 'courses/chm_physical1.json'},
                {'name': 'Analytical Chemistry', 'file': 'courses/chm_analytical.json'},
            ],
            '300': [
                {'name': 'Organic Chemistry II', 'file': 'courses/chm_organic2.json'},
                {'name': 'Physical Chemistry II', 'file': 'courses/chm_physical1.json'},
                {'name': 'Industrial Chemistry', 'file': 'courses/chm_general1.json'},
            ],
            '400': [
                {'name': 'Spectroscopy', 'file': 'courses/chm_analytical.json'},
                {'name': 'Environmental Chemistry', 'file': 'courses/chm_physical1.json'},
            ],
        },
        'Biology': {
            '100': [
                {'name': 'Cell Biology & Genetics Intro', 'file': 'courses/bio_general1.json'},
                {'name': 'Botany I', 'file': 'courses/bio_botany1.json'},
                {'name': 'Zoology I', 'file': 'courses/bio_zoology1.json'},
            ],
            '200': [
                {'name': 'Genetics', 'file': 'courses/bio_genetics.json'},
                {'name': 'Ecology & Evolution', 'file': 'courses/bio_ecology.json'},
                {'name': 'Microbiology Intro', 'file': 'courses/bio_microbiology.json'},
            ],
            '300': [
                {'name': 'Microbiology', 'file': 'courses/bio_microbiology.json'},
                {'name': 'Physiology', 'file': 'courses/med_physiology1.json'},
                {'name': 'Molecular Biology', 'file': 'courses/bio_genetics.json'},
            ],
            '400': [
                {'name': 'Immunology', 'file': 'courses/bio_microbiology.json'},
                {'name': 'Biotechnology', 'file': 'courses/bio_genetics.json'},
            ],
        },
    },
    'Faculty of Engineering': {
        'Electrical/Electronics Engineering': {
            '100': [
                {'name': 'Engineering Mathematics I', 'file': 'courses/mth_calculus1.json'},
                {'name': 'Circuit Theory I', 'file': 'courses/eee_circuit_theory.json'},
                {'name': 'Introduction to Engineering', 'file': 'courses/eng_intro.json'},
            ],
            '200': [
                {'name': 'Circuit Theory II', 'file': 'courses/eee_circuit_theory.json'},
                {'name': 'Electronics I', 'file': 'courses/eee_electronics1.json'},
                {'name': 'Signals & Systems', 'file': 'courses/eee_signals.json'},
            ],
            '300': [
                {'name': 'Control Systems', 'file': 'courses/eee_control_systems.json'},
                {'name': 'Digital Electronics', 'file': 'courses/eee_digital.json'},
                {'name': 'Power Systems I', 'file': 'courses/eee_power1.json'},
            ],
            '400': [
                {'name': 'Telecommunications', 'file': 'courses/eee_telecoms.json'},
                {'name': 'Power Electronics', 'file': 'courses/eee_power1.json'},
                {'name': 'Embedded Systems', 'file': 'courses/cs_computer_architecture.json'},
            ],
        },
        'Mechanical Engineering': {
            '100': [
                {'name': 'Engineering Mathematics I', 'file': 'courses/mth_calculus1.json'},
                {'name': 'Engineering Statics', 'file': 'courses/mec_statics.json'},
                {'name': 'Introduction to Engineering', 'file': 'courses/eng_intro.json'},
            ],
            '200': [
                {'name': 'Thermodynamics I', 'file': 'courses/phy_thermodynamics.json'},
                {'name': 'Dynamics', 'file': 'courses/phy_mechanics.json'},
                {'name': 'Strength of Materials', 'file': 'courses/mec_statics.json'},
            ],
            '300': [
                {'name': 'Fluid Mechanics', 'file': 'courses/mec_fluid.json'},
                {'name': 'Heat Transfer', 'file': 'courses/phy_thermodynamics.json'},
                {'name': 'Machine Design', 'file': 'courses/mec_statics.json'},
            ],
            '400': [
                {'name': 'Manufacturing Engineering', 'file': 'courses/eng_intro.json'},
                {'name': 'Robotics & Automation', 'file': 'courses/cs_artificial_intelligence.json'},
            ],
        },
        'Civil Engineering': {
            '100': [
                {'name': 'Engineering Mathematics I', 'file': 'courses/mth_calculus1.json'},
                {'name': 'Introduction to Civil Engineering', 'file': 'courses/eng_intro.json'},
            ],
            '200': [
                {'name': 'Structural Mechanics', 'file': 'courses/mec_statics.json'},
                {'name': 'Surveying', 'file': 'courses/eng_intro.json'},
                {'name': 'Fluid Mechanics', 'file': 'courses/mec_fluid.json'},
            ],
            '300': [
                {'name': 'Reinforced Concrete Design', 'file': 'courses/mec_statics.json'},
                {'name': 'Soil Mechanics', 'file': 'courses/mec_fluid.json'},
                {'name': 'Transportation Engineering', 'file': 'courses/eng_intro.json'},
            ],
            '400': [
                {'name': 'Foundation Engineering', 'file': 'courses/mec_statics.json'},
                {'name': 'Environmental Engineering', 'file': 'courses/chm_physical1.json'},
            ],
        },
        'Computer Engineering': {
            '100': [
                {'name': 'Introduction to Programming', 'file': 'courses/cs_intro_programming.json'},
                {'name': 'Circuit Theory I', 'file': 'courses/eee_circuit_theory.json'},
                {'name': 'Engineering Mathematics I', 'file': 'courses/mth_calculus1.json'},
            ],
            '200': [
                {'name': 'Data Structures', 'file': 'courses/cs_data_structures.json'},
                {'name': 'Digital Electronics', 'file': 'courses/eee_digital.json'},
                {'name': 'Computer Architecture', 'file': 'courses/cs_computer_architecture.json'},
            ],
            '300': [
                {'name': 'Operating Systems', 'file': 'courses/cs_operating_systems.json'},
                {'name': 'Computer Networks', 'file': 'courses/cs_networks.json'},
                {'name': 'Microprocessors & Interfacing', 'file': 'courses/cs_computer_architecture.json'},
            ],
            '400': [
                {'name': 'Software Engineering', 'file': 'courses/cs_software_engineering.json'},
                {'name': 'VLSI Design', 'file': 'courses/eee_digital.json'},
                {'name': 'Cybersecurity', 'file': 'courses/cs_cybersecurity.json'},
            ],
        },
    },
    'Faculty of Social Sciences': {
        'Economics': {
            '100': [
                {'name': 'Principles of Economics', 'file': 'courses/eco_principles.json'},
                {'name': 'Introduction to Statistics', 'file': 'courses/mth_intro_stats.json'},
                {'name': 'History of Economic Thought', 'file': 'courses/eco_history.json'},
            ],
            '200': [
                {'name': 'Microeconomics I', 'file': 'courses/eco_micro.json'},
                {'name': 'Macroeconomics I', 'file': 'courses/eco_macro.json'},
                {'name': 'Mathematical Economics', 'file': 'courses/mth_intro_stats.json'},
            ],
            '300': [
                {'name': 'Microeconomics II', 'file': 'courses/eco_micro.json'},
                {'name': 'International Economics', 'file': 'courses/eco_international.json'},
                {'name': 'Public Finance', 'file': 'courses/eco_public_finance.json'},
            ],
            '400': [
                {'name': 'Money & Banking', 'file': 'courses/eco_money_banking.json'},
                {'name': 'Development Economics', 'file': 'courses/eco_development.json'},
                {'name': 'Econometrics', 'file': 'courses/mth_intro_stats.json'},
            ],
        },
        'Political Science': {
            '100': [
                {'name': 'Introduction to Political Science', 'file': 'courses/pol_intro.json'},
                {'name': 'Nigerian Government & Politics', 'file': 'government.json'},
            ],
            '200': [
                {'name': 'Comparative Politics', 'file': 'courses/pol_intro.json'},
                {'name': 'Political Theory', 'file': 'courses/pol_intro.json'},
            ],
            '300': [
                {'name': 'International Relations', 'file': 'courses/pol_intro.json'},
                {'name': 'Public Administration', 'file': 'courses/pol_intro.json'},
            ],
            '400': [
                {'name': 'Nigerian Foreign Policy', 'file': 'courses/pol_intro.json'},
                {'name': 'Research Methods', 'file': 'courses/mth_intro_stats.json'},
            ],
        },
        'Mass Communication': {
            '100': [
                {'name': 'Introduction to Mass Communication', 'file': 'courses/com_intro.json'},
                {'name': 'Media Writing', 'file': 'courses/com_intro.json'},
            ],
            '200': [
                {'name': 'Print Journalism', 'file': 'courses/com_intro.json'},
                {'name': 'Broadcast Journalism', 'file': 'courses/com_intro.json'},
            ],
            '300': [
                {'name': 'Public Relations', 'file': 'courses/com_intro.json'},
                {'name': 'Advertising', 'file': 'courses/com_intro.json'},
            ],
            '400': [
                {'name': 'Media Management', 'file': 'courses/com_intro.json'},
                {'name': 'Digital Media & New Technologies', 'file': 'courses/com_intro.json'},
            ],
        },
        'Sociology': {
            '100': [
                {'name': 'Introduction to Sociology', 'file': 'courses/soc_intro.json'},
                {'name': 'Social Psychology', 'file': 'courses/soc_intro.json'},
            ],
            '200': [
                {'name': 'Social Research Methods', 'file': 'courses/mth_intro_stats.json'},
                {'name': 'Sociological Theory', 'file': 'courses/soc_intro.json'},
            ],
            '300': [
                {'name': 'Sociology of Development', 'file': 'courses/eco_development.json'},
                {'name': 'Urban Sociology', 'file': 'courses/soc_intro.json'},
            ],
            '400': [
                {'name': 'Gender Studies', 'file': 'courses/soc_intro.json'},
                {'name': 'Applied Sociology', 'file': 'courses/soc_intro.json'},
            ],
        },
    },
    'Faculty of Management Sciences': {
        'Accounting': {
            '100': [
                {'name': 'Financial Accounting I', 'file': 'courses/acc_financial1.json'},
                {'name': 'Business Mathematics', 'file': 'courses/mth_intro_stats.json'},
                {'name': 'Principles of Economics', 'file': 'courses/eco_principles.json'},
                {'name': 'Use of English', 'file': 'use_of_english.json'},
            ],
            '200': [
                {'name': 'Financial Accounting II', 'file': 'courses/acc_financial2.json'},
                {'name': 'Cost & Management Accounting', 'file': 'courses/acc_cost.json'},
                {'name': 'Taxation I', 'file': 'courses/acc_tax.json'},
                {'name': 'Business Law', 'file': 'courses/law_contract.json'},
            ],
            '300': [
                {'name': 'Auditing & Assurance', 'file': 'courses/acc_auditing.json'},
                {'name': 'Advanced Financial Accounting', 'file': 'courses/acc_financial2.json'},
                {'name': 'Management Accounting', 'file': 'courses/acc_cost.json'},
                {'name': 'Taxation II', 'file': 'courses/acc_tax.json'},
            ],
            '400': [
                {'name': 'Financial Management', 'file': 'courses/acc_fin_mgmt.json'},
                {'name': 'Advanced Auditing', 'file': 'courses/acc_auditing.json'},
                {'name': 'Public Sector Accounting', 'file': 'courses/acc_financial1.json'},
                {'name': 'Forensic Accounting', 'file': 'courses/acc_auditing.json'},
            ],
        },
        'Business Administration': {
            '100': [
                {'name': 'Introduction to Business', 'file': 'courses/bus_intro.json'},
                {'name': 'Business Mathematics', 'file': 'courses/mth_intro_stats.json'},
                {'name': 'Principles of Economics', 'file': 'courses/eco_principles.json'},
            ],
            '200': [
                {'name': 'Organisational Behaviour', 'file': 'courses/bus_org_behaviour.json'},
                {'name': 'Business Statistics', 'file': 'courses/mth_intro_stats.json'},
                {'name': 'Financial Accounting', 'file': 'courses/acc_financial1.json'},
            ],
            '300': [
                {'name': 'Strategic Management', 'file': 'courses/bus_strategic.json'},
                {'name': 'Human Resource Management', 'file': 'courses/bus_hrm.json'},
                {'name': 'Marketing Management', 'file': 'courses/bus_marketing.json'},
            ],
            '400': [
                {'name': 'Entrepreneurship', 'file': 'courses/bus_entrepreneurship.json'},
                {'name': 'Corporate Finance', 'file': 'courses/acc_fin_mgmt.json'},
                {'name': 'Operations Management', 'file': 'courses/bus_intro.json'},
            ],
        },
        'Banking & Finance': {
            '100': [
                {'name': 'Principles of Economics', 'file': 'courses/eco_principles.json'},
                {'name': 'Introduction to Banking', 'file': 'courses/eco_money_banking.json'},
                {'name': 'Financial Mathematics', 'file': 'courses/mth_intro_stats.json'},
            ],
            '200': [
                {'name': 'Money & Capital Markets', 'file': 'courses/eco_money_banking.json'},
                {'name': 'Commercial Banking', 'file': 'courses/eco_money_banking.json'},
                {'name': 'Financial Accounting', 'file': 'courses/acc_financial1.json'},
            ],
            '300': [
                {'name': 'Investment & Portfolio Management', 'file': 'courses/acc_fin_mgmt.json'},
                {'name': 'Bank Credit & Risk Management', 'file': 'courses/eco_money_banking.json'},
                {'name': 'Public Finance', 'file': 'courses/eco_public_finance.json'},
            ],
            '400': [
                {'name': 'International Finance', 'file': 'courses/eco_international.json'},
                {'name': 'Central Banking & Monetary Policy', 'file': 'courses/eco_macro.json'},
            ],
        },
        'Marketing': {
            '100': [
                {'name': 'Principles of Marketing', 'file': 'courses/bus_marketing.json'},
                {'name': 'Introduction to Business', 'file': 'courses/bus_intro.json'},
            ],
            '200': [
                {'name': 'Consumer Behaviour', 'file': 'courses/bus_marketing.json'},
                {'name': 'Marketing Research', 'file': 'courses/mth_intro_stats.json'},
            ],
            '300': [
                {'name': 'Advertising & Promotion', 'file': 'courses/bus_marketing.json'},
                {'name': 'Sales Management', 'file': 'courses/bus_marketing.json'},
            ],
            '400': [
                {'name': 'Digital Marketing', 'file': 'courses/bus_marketing.json'},
                {'name': 'International Marketing', 'file': 'courses/eco_international.json'},
            ],
        },
    },
    'Faculty of Law': {
        'Law': {
            '100': [
                {'name': 'Introduction to Law & Legal Method', 'file': 'courses/law_intro.json'},
                {'name': 'Constitutional Law I', 'file': 'courses/law_constitutional.json'},
                {'name': 'Nigerian Legal System', 'file': 'courses/law_intro.json'},
                {'name': 'Use of English', 'file': 'use_of_english.json'},
            ],
            '200': [
                {'name': 'Law of Contract', 'file': 'courses/law_contract.json'},
                {'name': 'Law of Tort', 'file': 'courses/law_tort.json'},
                {'name': 'Criminal Law I', 'file': 'courses/law_criminal.json'},
                {'name': 'Administrative Law', 'file': 'courses/law_intro.json'},
            ],
            '300': [
                {'name': 'Company Law', 'file': 'courses/law_company.json'},
                {'name': 'Evidence Law', 'file': 'courses/law_evidence.json'},
                {'name': 'Land Law', 'file': 'courses/law_intro.json'},
                {'name': 'Family Law', 'file': 'courses/law_intro.json'},
            ],
            '400': [
                {'name': 'Commercial Law', 'file': 'courses/law_contract.json'},
                {'name': 'Jurisprudence & Legal Theory', 'file': 'courses/law_intro.json'},
                {'name': 'International Law', 'file': 'courses/law_intro.json'},
                {'name': 'Labour Law', 'file': 'courses/law_intro.json'},
            ],
            '500': [
                {'name': 'Legal Drafting & Conveyancing', 'file': 'courses/law_intro.json'},
                {'name': 'Alternative Dispute Resolution', 'file': 'courses/law_intro.json'},
            ],
        },
    },
    'Faculty of Medicine & Health Sciences': {
        'Medicine & Surgery (MBBS)': {
            '100': [
                {'name': 'Human Anatomy I', 'file': 'courses/med_anatomy1.json'},
                {'name': 'Human Physiology I', 'file': 'courses/med_physiology1.json'},
                {'name': 'Biochemistry I', 'file': 'courses/med_biochem1.json'},
                {'name': 'Introduction to Medical Sciences', 'file': 'courses/med_intro.json'},
            ],
            '200': [
                {'name': 'Human Anatomy II', 'file': 'courses/med_anatomy1.json'},
                {'name': 'Human Physiology II', 'file': 'courses/med_physiology1.json'},
                {'name': 'Biochemistry II', 'file': 'courses/med_biochem1.json'},
                {'name': 'Histology & Embryology', 'file': 'courses/med_anatomy1.json'},
            ],
            '300': [
                {'name': 'Pathology', 'file': 'courses/med_pathology.json'},
                {'name': 'Microbiology & Parasitology', 'file': 'courses/med_microbiology.json'},
                {'name': 'Pharmacology I', 'file': 'courses/med_pharmacology.json'},
                {'name': 'Medical Ethics', 'file': 'courses/med_intro.json'},
            ],
            '400': [
                {'name': 'Medicine & Surgery I', 'file': 'courses/med_medicine1.json'},
                {'name': 'Paediatrics', 'file': 'courses/med_medicine1.json'},
                {'name': 'Obstetrics & Gynaecology', 'file': 'courses/med_medicine1.json'},
                {'name': 'Community Medicine', 'file': 'courses/med_medicine1.json'},
            ],
            '500': [
                {'name': 'Advanced Medicine & Surgery', 'file': 'courses/med_medicine1.json'},
                {'name': 'Psychiatry', 'file': 'courses/med_medicine1.json'},
            ],
        },
        'Pharmacy': {
            '100': [
                {'name': 'General Chemistry', 'file': 'courses/chm_general1.json'},
                {'name': 'Human Anatomy & Physiology', 'file': 'courses/med_physiology1.json'},
                {'name': 'Introduction to Pharmacy', 'file': 'courses/med_intro.json'},
            ],
            '200': [
                {'name': 'Pharmaceutical Chemistry I', 'file': 'courses/chm_organic1.json'},
                {'name': 'Pharmacology I', 'file': 'courses/med_pharmacology.json'},
                {'name': 'Pharmaceutics I', 'file': 'courses/med_pharmacology.json'},
            ],
            '300': [
                {'name': 'Medicinal Chemistry', 'file': 'courses/chm_organic1.json'},
                {'name': 'Pharmacology II', 'file': 'courses/med_pharmacology.json'},
                {'name': 'Clinical Pharmacy', 'file': 'courses/med_medicine1.json'},
            ],
            '400': [
                {'name': 'Pharmacokinetics', 'file': 'courses/med_pharmacology.json'},
                {'name': 'Hospital & Clinical Pharmacy', 'file': 'courses/med_medicine1.json'},
                {'name': 'Pharmaceutical Microbiology', 'file': 'courses/med_microbiology.json'},
            ],
            '500': [
                {'name': 'Pharmacy Practice', 'file': 'courses/med_medicine1.json'},
            ],
        },
        'Nursing Science': {
            '100': [
                {'name': 'Anatomy & Physiology for Nurses', 'file': 'courses/med_physiology1.json'},
                {'name': 'Introduction to Nursing', 'file': 'courses/med_intro.json'},
                {'name': 'Microbiology for Nursing', 'file': 'courses/med_microbiology.json'},
            ],
            '200': [
                {'name': 'Medical-Surgical Nursing I', 'file': 'courses/med_medicine1.json'},
                {'name': 'Community Health Nursing', 'file': 'courses/med_medicine1.json'},
                {'name': 'Pharmacology for Nurses', 'file': 'courses/med_pharmacology.json'},
            ],
            '300': [
                {'name': 'Paediatric Nursing', 'file': 'courses/med_medicine1.json'},
                {'name': 'Psychiatric Nursing', 'file': 'courses/med_medicine1.json'},
                {'name': 'Midwifery I', 'file': 'courses/med_medicine1.json'},
            ],
            '400': [
                {'name': 'Critical Care Nursing', 'file': 'courses/med_medicine1.json'},
                {'name': 'Nursing Management', 'file': 'courses/bus_hrm.json'},
                {'name': 'Research in Nursing', 'file': 'courses/mth_intro_stats.json'},
            ],
        },
        'Medical Laboratory Science': {
            '100': [
                {'name': 'General Biology', 'file': 'courses/bio_general1.json'},
                {'name': 'General Chemistry', 'file': 'courses/chm_general1.json'},
                {'name': 'Introduction to MLS', 'file': 'courses/med_intro.json'},
            ],
            '200': [
                {'name': 'Clinical Chemistry I', 'file': 'courses/med_biochem1.json'},
                {'name': 'Haematology I', 'file': 'courses/med_anatomy1.json'},
                {'name': 'Medical Microbiology', 'file': 'courses/med_microbiology.json'},
            ],
            '300': [
                {'name': 'Clinical Chemistry II', 'file': 'courses/med_biochem1.json'},
                {'name': 'Blood Banking & Transfusion', 'file': 'courses/med_anatomy1.json'},
                {'name': 'Histopathology', 'file': 'courses/med_pathology.json'},
            ],
            '400': [
                {'name': 'Molecular Diagnostics', 'file': 'courses/bio_genetics.json'},
                {'name': 'Parasitology & Entomology', 'file': 'courses/med_microbiology.json'},
                {'name': 'Quality Control in Laboratory', 'file': 'courses/mth_intro_stats.json'},
            ],
        },
    },
    'Faculty of Education': {
        'Education (Computer Science)': {
            '100': [
                {'name': 'Introduction to Education', 'file': 'courses/edu_intro.json'},
                {'name': 'Introduction to Programming', 'file': 'courses/cs_intro_programming.json'},
                {'name': 'Psychology of Learning', 'file': 'courses/edu_intro.json'},
            ],
            '200': [
                {'name': 'Data Structures', 'file': 'courses/cs_data_structures.json'},
                {'name': 'Curriculum Studies', 'file': 'courses/edu_intro.json'},
                {'name': 'Teaching Methods', 'file': 'courses/edu_intro.json'},
            ],
            '300': [
                {'name': 'Database Management', 'file': 'courses/cs_database.json'},
                {'name': 'Educational Technology', 'file': 'courses/edu_intro.json'},
            ],
            '400': [
                {'name': 'Artificial Intelligence', 'file': 'courses/cs_artificial_intelligence.json'},
                {'name': 'Educational Administration', 'file': 'courses/edu_intro.json'},
            ],
        },
        'Education (Mathematics)': {
            '100': [
                {'name': 'Introduction to Education', 'file': 'courses/edu_intro.json'},
                {'name': 'Calculus I', 'file': 'courses/mth_calculus1.json'},
            ],
            '200': [
                {'name': 'Linear Algebra', 'file': 'courses/mth_linear_algebra.json'},
                {'name': 'Teaching Methods in Mathematics', 'file': 'courses/edu_intro.json'},
            ],
            '300': [
                {'name': 'Abstract Algebra', 'file': 'courses/mth_abstract_algebra.json'},
                {'name': 'Educational Technology', 'file': 'courses/edu_intro.json'},
            ],
            '400': [
                {'name': 'Operations Research', 'file': 'courses/mth_operations_research.json'},
                {'name': 'Educational Administration', 'file': 'courses/edu_intro.json'},
            ],
        },
        'Education (English)': {
            '100': [
                {'name': 'Introduction to Education', 'file': 'courses/edu_intro.json'},
                {'name': 'Introduction to Linguistics', 'file': 'use_of_english.json'},
            ],
            '200': [
                {'name': 'English Literature I', 'file': 'literature_in_english.json'},
                {'name': 'Teaching Methods in English', 'file': 'courses/edu_intro.json'},
            ],
            '300': [
                {'name': 'Stylistics & Creative Writing', 'file': 'literature_in_english.json'},
                {'name': 'Educational Technology', 'file': 'courses/edu_intro.json'},
            ],
            '400': [
                {'name': 'Language Testing & Assessment', 'file': 'use_of_english.json'},
                {'name': 'Educational Administration', 'file': 'courses/edu_intro.json'},
            ],
        },
    },
    'Landmark University': {
        'Computer Science': {
            '100': [
                {'name': 'Introduction to Computing', 'file': 'courses/cs_intro_programming.json'},
                {'name': 'Mathematics I', 'file': 'courses/mth_calculus1.json'},
                {'name': 'Logic & Problem Solving', 'file': 'courses/cs_logic.json'},
            ],
            '200': [
                {'name': 'Data Structures & Algorithms', 'file': 'courses/cs_data_structures.json'},
                {'name': 'Database Systems', 'file': 'courses/cs_database.json'},
                {'name': 'Object-Oriented Programming', 'file': 'courses/cs_oop.json'},
            ],
            '300': [
                {'name': 'Operating Systems', 'file': 'courses/cs_operating_systems.json'},
                {'name': 'Computer Networks', 'file': 'courses/cs_networks.json'},
                {'name': 'Software Engineering', 'file': 'courses/cs_software_engineering.json'},
            ],
            '400': [
                {'name': 'Artificial Intelligence', 'file': 'courses/cs_artificial_intelligence.json'},
                {'name': 'Cybersecurity', 'file': 'courses/cs_cybersecurity.json'},
                {'name': 'Final Year Project', 'file': 'courses/cs_software_engineering.json'},
            ],
        },
        'Agricultural Science': {
            '100': [
                {'name': 'Introduction to Agriculture', 'file': 'courses/bio_general1.json'},
                {'name': 'General Chemistry', 'file': 'courses/chm_general1.json'},
                {'name': 'General Biology', 'file': 'courses/bio_general1.json'},
            ],
            '200': [
                {'name': 'Soil Science', 'file': 'courses/bio_ecology.json'},
                {'name': 'Crop Physiology', 'file': 'courses/bio_genetics.json'},
                {'name': 'Agricultural Economics', 'file': 'courses/eco_micro1.json'},
            ],
            '300': [
                {'name': 'Crop Production', 'file': 'courses/bio_genetics.json'},
                {'name': 'Animal Production', 'file': 'courses/med_physiology.json'},
                {'name': 'Farm Management', 'file': 'courses/bus_management.json'},
            ],
            '400': [
                {'name': 'Agricultural Extension', 'file': 'courses/edu_intro.json'},
                {'name': 'Research Methods', 'file': 'courses/mth_intro_stats.json'},
            ],
        },
        'Chemical Engineering': {
            '100': [
                {'name': 'Engineering Mathematics', 'file': 'courses/mth_calculus1.json'},
                {'name': 'General Chemistry', 'file': 'courses/chm_general1.json'},
                {'name': 'Introduction to Engineering', 'file': 'courses/eng_electrical1.json'},
            ],
            '200': [
                {'name': 'Physical Chemistry', 'file': 'courses/chm_physical.json'},
                {'name': 'Organic Chemistry', 'file': 'courses/chm_organic1.json'},
                {'name': 'Fluid Mechanics', 'file': 'courses/eng_fluid.json'},
            ],
            '300': [
                {'name': 'Heat & Mass Transfer', 'file': 'courses/phy_thermodynamics.json'},
                {'name': 'Chemical Reaction Engineering', 'file': 'courses/chm_physical.json'},
                {'name': 'Process Control', 'file': 'courses/eng_instrumentation.json'},
            ],
            '400': [
                {'name': 'Plant Design', 'file': 'courses/eng_fluid.json'},
                {'name': 'Petroleum Refining', 'file': 'courses/eng_electrical1.json'},
            ],
        },
    },
    'Obafemi Awolowo University (OAU)': {
        'Medicine & Surgery': {
            '100': [
                {'name': 'General Biology', 'file': 'courses/bio_general1.json'},
                {'name': 'General Chemistry', 'file': 'courses/chm_general1.json'},
                {'name': 'Physics', 'file': 'courses/phy_mechanics.json'},
            ],
            '200': [
                {'name': 'Anatomy I', 'file': 'courses/med_anatomy1.json'},
                {'name': 'Biochemistry', 'file': 'courses/med_biochem1.json'},
                {'name': 'Physiology', 'file': 'courses/med_physiology.json'},
            ],
            '300': [
                {'name': 'Pathology', 'file': 'courses/med_pathology.json'},
                {'name': 'Medical Microbiology', 'file': 'courses/med_microbiology.json'},
                {'name': 'Pharmacology', 'file': 'courses/med_pharmacology.json'},
            ],
            '400': [
                {'name': 'Internal Medicine', 'file': 'courses/med_medicine1.json'},
                {'name': 'Surgery', 'file': 'courses/med_medicine1.json'},
                {'name': 'Obstetrics & Gynaecology', 'file': 'courses/med_medicine1.json'},
            ],
        },
        'Law': {
            '100': [
                {'name': 'Nigerian Legal System', 'file': 'courses/law_legal_system.json'},
                {'name': 'Law of Contract', 'file': 'courses/law_contract.json'},
            ],
            '200': [
                {'name': 'Constitutional Law', 'file': 'courses/law_constitutional.json'},
                {'name': 'Criminal Law', 'file': 'courses/law_criminal.json'},
                {'name': 'Law of Tort', 'file': 'courses/law_contract.json'},
            ],
            '300': [
                {'name': 'Commercial Law', 'file': 'courses/law_legal_system.json'},
                {'name': 'Land Law', 'file': 'courses/law_legal_system.json'},
                {'name': 'Equity & Trusts', 'file': 'courses/law_constitutional.json'},
            ],
            '400': [
                {'name': 'International Law', 'file': 'courses/law_constitutional.json'},
                {'name': 'Human Rights Law', 'file': 'courses/law_constitutional.json'},
            ],
            '500': [
                {'name': 'Legal Drafting', 'file': 'courses/law_legal_system.json'},
                {'name': 'Clinical Legal Education', 'file': 'courses/law_contract.json'},
            ],
        },
        'Economics': {
            '100': [
                {'name': 'Principles of Economics', 'file': 'courses/eco_micro1.json'},
                {'name': 'Mathematics for Economists', 'file': 'courses/mth_calculus1.json'},
            ],
            '200': [
                {'name': 'Microeconomics I', 'file': 'courses/eco_micro1.json'},
                {'name': 'Macroeconomics I', 'file': 'courses/eco_macro1.json'},
                {'name': 'Statistics for Economists', 'file': 'courses/mth_intro_stats.json'},
            ],
            '300': [
                {'name': 'Econometrics', 'file': 'courses/eco_econometrics.json'},
                {'name': 'Development Economics', 'file': 'courses/eco_development.json'},
                {'name': 'Public Finance', 'file': 'courses/eco_development.json'},
            ],
            '400': [
                {'name': 'International Economics', 'file': 'courses/eco_macro1.json'},
                {'name': 'Research Project', 'file': 'courses/mth_intro_stats.json'},
            ],
        },
        'Computer Science & Engineering': {
            '100': [
                {'name': 'Introduction to Programming', 'file': 'courses/cs_intro_programming.json'},
                {'name': 'Engineering Mathematics I', 'file': 'courses/mth_calculus1.json'},
                {'name': 'Digital Logic', 'file': 'courses/cs_computer_architecture.json'},
            ],
            '200': [
                {'name': 'Data Structures', 'file': 'courses/cs_data_structures.json'},
                {'name': 'Computer Organization', 'file': 'courses/cs_computer_architecture.json'},
                {'name': 'Discrete Structures', 'file': 'courses/cs_discrete_math.json'},
            ],
            '300': [
                {'name': 'Operating Systems', 'file': 'courses/cs_operating_systems.json'},
                {'name': 'Computer Networks', 'file': 'courses/cs_networks.json'},
                {'name': 'Software Engineering', 'file': 'courses/cs_software_engineering.json'},
            ],
            '400': [
                {'name': 'Artificial Intelligence', 'file': 'courses/cs_artificial_intelligence.json'},
                {'name': 'Distributed Systems', 'file': 'courses/cs_distributed_systems.json'},
                {'name': 'Final Year Project', 'file': 'courses/cs_software_engineering.json'},
            ],
        },
    },
    'Veritas University': {
        'Philosophy': {
            '100': [
                {'name': 'Introduction to Philosophy', 'file': 'courses/edu_intro.json'},
                {'name': 'Logic & Critical Thinking', 'file': 'courses/cs_logic.json'},
                {'name': 'Use of English', 'file': 'use_of_english.json'},
            ],
            '200': [
                {'name': 'Ethics & Moral Philosophy', 'file': 'courses/edu_intro.json'},
                {'name': 'Epistemology', 'file': 'courses/edu_intro.json'},
                {'name': 'African Philosophy', 'file': 'courses/edu_intro.json'},
            ],
            '300': [
                {'name': 'Metaphysics', 'file': 'courses/edu_intro.json'},
                {'name': 'Philosophy of Religion', 'file': 'courses/edu_intro.json'},
                {'name': 'Social & Political Philosophy', 'file': 'courses/law_constitutional.json'},
            ],
            '400': [
                {'name': 'Research Methods in Philosophy', 'file': 'courses/mth_intro_stats.json'},
                {'name': 'Contemporary Philosophy', 'file': 'courses/edu_intro.json'},
            ],
        },
        'Accounting': {
            '100': [
                {'name': 'Principles of Accounting', 'file': 'courses/bus_accounting.json'},
                {'name': 'Business Mathematics', 'file': 'courses/mth_calculus1.json'},
                {'name': 'Introduction to Business', 'file': 'courses/bus_management.json'},
            ],
            '200': [
                {'name': 'Financial Accounting', 'file': 'courses/bus_accounting.json'},
                {'name': 'Cost Accounting', 'file': 'courses/bus_accounting.json'},
                {'name': 'Business Law', 'file': 'courses/law_contract.json'},
            ],
            '300': [
                {'name': 'Management Accounting', 'file': 'courses/bus_management.json'},
                {'name': 'Auditing & Assurance', 'file': 'courses/bus_accounting.json'},
                {'name': 'Taxation', 'file': 'courses/bus_accounting.json'},
            ],
            '400': [
                {'name': 'Advanced Financial Accounting', 'file': 'courses/bus_accounting.json'},
                {'name': 'Corporate Governance', 'file': 'courses/bus_management.json'},
            ],
        },
        'Mass Communication': {
            '100': [
                {'name': 'Introduction to Mass Communication', 'file': 'courses/edu_intro.json'},
                {'name': 'Communication Theory', 'file': 'courses/edu_intro.json'},
            ],
            '200': [
                {'name': 'Print Journalism', 'file': 'courses/edu_intro.json'},
                {'name': 'Broadcast Journalism', 'file': 'courses/edu_intro.json'},
                {'name': 'Media Writing', 'file': 'use_of_english.json'},
            ],
            '300': [
                {'name': 'Public Relations', 'file': 'courses/bus_management.json'},
                {'name': 'Advertising', 'file': 'courses/bus_management.json'},
                {'name': 'Digital Media', 'file': 'courses/cs_intro_programming.json'},
            ],
            '400': [
                {'name': 'Media Law & Ethics', 'file': 'courses/law_constitutional.json'},
                {'name': 'Research Project', 'file': 'courses/mth_intro_stats.json'},
            ],
        },
    },
    'Oxford University': {
        'Computer Science': {
            '1st Year': [
                {'name': 'Introduction to Programming (Python & Java)', 'file': 'courses/cs_intro_programming.json'},
                {'name': 'Discrete Mathematics', 'file': 'courses/cs_discrete_math.json'},
                {'name': 'Digital Systems', 'file': 'courses/cs_computer_architecture.json'},
                {'name': 'Linear Algebra', 'file': 'courses/mth_linear_algebra.json'},
            ],
            '2nd Year': [
                {'name': 'Algorithms', 'file': 'courses/cs_data_structures.json'},
                {'name': 'Computer Architecture', 'file': 'courses/cs_computer_architecture.json'},
                {'name': 'Models of Computation', 'file': 'courses/cs_theory_computation.json'},
                {'name': 'Probability & Statistics', 'file': 'courses/mth_intro_stats.json'},
            ],
            '3rd Year': [
                {'name': 'Machine Learning', 'file': 'courses/cs_machine_learning.json'},
                {'name': 'Computer Security', 'file': 'courses/cs_cybersecurity.json'},
                {'name': 'Compilers', 'file': 'courses/cs_compiler_design.json'},
                {'name': 'Distributed Systems', 'file': 'courses/cs_distributed_systems.json'},
            ],
            '4th Year': [
                {'name': 'Advanced Machine Learning', 'file': 'courses/cs_machine_learning.json'},
                {'name': 'Computer Vision', 'file': 'courses/cs_artificial_intelligence.json'},
                {'name': 'Research Project', 'file': 'courses/cs_software_engineering.json'},
            ],
        },
        'Physics': {
            '1st Year': [
                {'name': 'Classical Mechanics', 'file': 'courses/phy_mechanics.json'},
                {'name': 'Electricity & Magnetism', 'file': 'courses/phy_electricity.json'},
                {'name': 'Mathematics for Physics I', 'file': 'courses/mth_calculus1.json'},
            ],
            '2nd Year': [
                {'name': 'Quantum Mechanics', 'file': 'courses/phy_modern.json'},
                {'name': 'Statistical Mechanics', 'file': 'courses/phy_waves.json'},
                {'name': 'Mathematical Methods II', 'file': 'courses/mth_linear_algebra.json'},
            ],
            '3rd Year': [
                {'name': 'Particle Physics', 'file': 'courses/phy_modern.json'},
                {'name': 'Condensed Matter Physics', 'file': 'courses/phy_waves.json'},
                {'name': 'Astrophysics', 'file': 'courses/phy_mechanics.json'},
            ],
            '4th Year': [
                {'name': 'Advanced Quantum Field Theory', 'file': 'courses/phy_modern.json'},
                {'name': 'Research Project', 'file': 'courses/cs_software_engineering.json'},
            ],
        },
        'Mathematics': {
            '1st Year': [
                {'name': 'Analysis I', 'file': 'courses/mth_calculus1.json'},
                {'name': 'Linear Algebra', 'file': 'courses/mth_linear_algebra.json'},
                {'name': 'Abstract Algebra', 'file': 'courses/mth_abstract_algebra.json'},
            ],
            '2nd Year': [
                {'name': 'Real Analysis', 'file': 'courses/mth_calculus1.json'},
                {'name': 'Differential Equations', 'file': 'courses/mth_calculus1.json'},
                {'name': 'Topology', 'file': 'courses/mth_abstract_algebra.json'},
            ],
            '3rd Year': [
                {'name': 'Number Theory', 'file': 'courses/mth_abstract_algebra.json'},
                {'name': 'Probability Theory', 'file': 'courses/mth_intro_stats.json'},
                {'name': 'Numerical Analysis', 'file': 'courses/mth_operations_research.json'},
            ],
            '4th Year': [
                {'name': 'Mathematical Research', 'file': 'courses/mth_operations_research.json'},
                {'name': 'Algebraic Geometry', 'file': 'courses/mth_abstract_algebra.json'},
            ],
        },
    },
}


@app.route('/subject_selection')
def subject_selection():
    if 'student_info' not in session:
        return redirect(url_for('home'))
    return render_template('subject_selection.html',
                           courses_json=json.dumps(UNIVERSITY_COURSES),
                           mode=session.get('mode', 'exam'))

@app.route('/select_subjects', methods=['POST'])
def select_subjects():
    if 'student_info' not in session:
        return redirect(url_for('home'))

    def _render_err(msg):
        return render_template('subject_selection.html',
                               courses_json=json.dumps(UNIVERSITY_COURSES),
                               error=msg, mode=session.get('mode', 'exam'))

    course_name = request.form.get('course_name', '').strip()
    course_file = request.form.get('course_file', '').strip()
    if not course_name or not course_file:
        return _render_err('Please select a course to begin.')
    if '..' in course_file or course_file.startswith('/'):
        return _render_err('Invalid course selection.')

    try:
        num_questions = int(request.form.get('num_questions', 30))
        if num_questions not in (10, 20, 30, 45, 60):
            num_questions = 30
    except (ValueError, TypeError):
        num_questions = 30

    try:
        time_limit_min = int(request.form.get('time_limit', 60))
        if time_limit_min not in (15, 30, 60):
            time_limit_min = 60
    except (ValueError, TypeError):
        time_limit_min = 60

    if not os.path.exists(course_file):
        return _render_err(f'Questions for "{course_name}" are not yet available. Please choose another course.')

    qs = load_questions(course_file)
    count = min(num_questions, len(qs))
    if count == 0:
        return _render_err(f'No questions found for "{course_name}". Please choose another course.')

    subject_questions = {course_name: random.sample(qs, count)}
    subject_answers   = {course_name: [None] * count}

    session['subject_questions'] = subject_questions
    session['subject_answers']   = subject_answers
    session['start_time']        = time.time()
    if session.get('mode') == 'practice':
        session['exam_duration'] = 99 * 3600
    else:
        session['exam_duration'] = time_limit_min * 60
    session['exam_settings']     = {'time_limit_min': time_limit_min, 'num_questions': num_questions}
    session['current_subject']   = course_name
    session['current_question']  = 0
    return redirect(url_for('exam'))


@app.route('/exam')
def exam():
    if 'student_info' not in session:
        return redirect(url_for('home'))
    current_subject = session.get('current_subject', 'Use of English')
    current_question = session.get('current_question', 0)
    subject_questions = session['subject_questions']
    subject_answers = session['subject_answers']
    questions = subject_questions[current_subject]
    answers = subject_answers[current_subject]
    elapsed = int(time.time() - session['start_time'])
    remaining = max(0, session['exam_duration'] - elapsed)
    answered_count = sum(1 for a in answers if a is not None)
    return render_template('exam.html',
                           student_info=session['student_info'],
                           subjects=list(subject_questions.keys()),
                           current_subject=current_subject,
                           current_question=current_question,
                           question=questions[current_question],
                           total_questions=len(questions),
                           answers=answers,
                           answered_count=answered_count,
                           time_remaining=remaining,
                           mode=session.get('mode', 'exam'))

@app.route('/answer', methods=['POST'])
def answer():
    if 'student_info' not in session:
        return jsonify({'error': 'Session expired'}), 401
    current_subject = session['current_subject']
    current_question = session['current_question']
    option_index = int(request.form.get('option'))
    session['subject_answers'][current_subject][current_question] = option_index
    session.modified = True
    return jsonify({'success': True})

@app.route('/practice/feedback', methods=['POST'])
def practice_feedback():
    if 'student_info' not in session:
        return jsonify({'error': 'Session expired'}), 401
    current_subject = session['current_subject']
    current_question = session['current_question']
    option_index = int(request.form.get('option'))
    # Store answer in session so final score can be computed
    session['subject_answers'][current_subject][current_question] = option_index
    session.modified = True
    qs = session['subject_questions'][current_subject]
    q = qs[current_question]
    correct_answer = q.get('Answer', '')
    selected_option = q['Options'][option_index]
    # Determine if answer is correct
    is_correct = False
    try:
        if float_safe(selected_option) == float_safe(correct_answer):
            is_correct = True
    except:
        if str(selected_option).strip() == str(correct_answer).strip():
            is_correct = True
    # Find index of correct option
    correct_index = None
    for idx, opt in enumerate(q.get('Options', [])):
        try:
            match = float_safe(opt) == float_safe(correct_answer)
        except:
            match = str(opt).strip() == str(correct_answer).strip()
        if match:
            correct_index = idx
            break
    # Get AI explanation
    explanation = f"The correct answer is: {correct_answer}."
    try:
        client_obj = get_ai_client()
        options_text = '\n'.join([f"{chr(65+i)}. {opt}" for i, opt in enumerate(q.get('Options', []))])
        prompt = (
            f"Question: {q['Question']}\n"
            f"Options:\n{options_text}\n"
            f"Correct Answer: {correct_answer}\n\n"
            f"In 2-3 short sentences, explain why \"{correct_answer}\" is correct. Be concise and educational."
        )
        resp = client_obj.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=200
        )
        explanation = resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI explanation error: {e}")
    return jsonify({
        'success': True,
        'is_correct': is_correct,
        'correct_index': correct_index,
        'selected_index': option_index,
        'explanation': explanation
    })

@app.route('/navigate', methods=['POST'])
def navigate():
    if 'student_info' not in session:
        return redirect(url_for('home'))
    action = request.form.get('action')
    current_subject = session['current_subject']
    current_question = session['current_question']
    subjects = list(session['subject_questions'].keys())
    if action == 'next':
        if current_question < len(session['subject_questions'][current_subject]) - 1:
            session['current_question'] = current_question + 1
    elif action == 'prev':
        if current_question > 0:
            session['current_question'] = current_question - 1
    elif action == 'goto':
        session['current_question'] = int(request.form.get('question_num'))
    elif action == 'switch_subject':
        session['current_subject'] = request.form.get('subject')
        session['current_question'] = 0
    elif action == 'prev_subject':
        idx = subjects.index(current_subject)
        if idx > 0:
            session['current_subject'] = subjects[idx - 1]
            session['current_question'] = 0
    elif action == 'next_subject':
        idx = subjects.index(current_subject)
        if idx < len(subjects) - 1:
            session['current_subject'] = subjects[idx + 1]
            session['current_question'] = 0
    session.modified = True
    return redirect(url_for('exam'))

@app.route('/submit', methods=['POST'])
def submit():
    if 'student_info' not in session:
        return redirect(url_for('home'))
    results = []
    total_score = 0
    total_questions = 0
    for subj in session['subject_questions']:
        qs = session['subject_questions'][subj]
        ans = session['subject_answers'][subj]
        score = 0
        for i, a in enumerate(ans):
            if a is not None:
                correct = qs[i].get("Answer", "")
                selected = qs[i]["Options"][a]
                try:
                    if float_safe(selected) == float_safe(correct):
                        score += 1
                except:
                    if str(selected).strip() == str(correct).strip():
                        score += 1
        total_score += score
        total_questions += len(qs)
        percent = (score / len(qs) * 100) if qs else 0
        results.append((subj, score, len(qs), percent))
    percentage = (total_score / total_questions * 100) if total_questions > 0 else 0

    # Only persist results for exam mode (not practice)
    if session.get('mode') != 'practice':
        name = session['student_info']['name']
        regno = session['student_info']['regno']
        init_db()
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO students (name, regno) VALUES (?, ?)', (name, regno))
        c.execute('SELECT id FROM students WHERE regno = ?', (regno,))
        student_id = c.fetchone()[0]
        c.execute('INSERT INTO exam_attempts (student_id) VALUES (?)', (student_id,))
        attempt_id = c.lastrowid
        for subj, score, total, percent in [(r[0], r[1], r[2], r[3]) for r in results]:
            c.execute('INSERT INTO subject_scores (attempt_id, subject, score, total) VALUES (?, ?, ?, ?)',
                      (attempt_id, subj, score, total))
        c.execute('UPDATE exam_attempts SET total_score=?, total_questions=?, percentage=? WHERE id=?',
                  (total_score, total_questions, percentage, attempt_id))
        conn.commit()
        conn.close()
        db = get_mongo()
        if db:
            try:
                db.exam_results.insert_one({
                    'name': name, 'regno': regno,
                    'results': [{'subject': s, 'score': sc, 'total': t, 'percent': p}
                                 for s, sc, t, p in results],
                    'total_score': total_score, 'total_questions': total_questions,
                    'percentage': percentage, 'exam_date': datetime.utcnow()
                })
            except Exception as e:
                print(f"MongoDB save error: {e}")

    session['results'] = results
    session['submitted'] = True
    return redirect(url_for('results'))

@app.route('/results')
def results():
    if 'student_info' not in session or 'results' not in session:
        return redirect(url_for('home'))
    return render_template('results.html',
                           student_info=session['student_info'],
                           results=session['results'],
                           mode=session.get('mode', 'exam'))

@app.route('/correction')
def correction():
    if 'student_info' not in session or 'results' not in session:
        return redirect(url_for('home'))
    current_subject = request.args.get('subject', 'Use of English')
    subjects_list = list(session['subject_questions'].keys())
    current_subject_idx = subjects_list.index(current_subject) if current_subject in subjects_list else 0
    questions = session['subject_questions'][current_subject]
    answers = session['subject_answers'][current_subject]
    questions_with_answers = []
    for i, q in enumerate(questions):
        correct_answer = q.get("Answer", "")
        user_choice = answers[i]
        options_data = []
        for idx, opt in enumerate(q.get("Options", [])):
            is_correct = False
            try:
                if float_safe(opt) == float_safe(correct_answer):
                    is_correct = True
            except:
                if str(opt).strip() == str(correct_answer).strip():
                    is_correct = True
            options_data.append({
                'text': opt,
                'is_correct': is_correct,
                'is_user_choice': user_choice == idx
            })
        questions_with_answers.append({
            'number': i + 1,
            'question': q['Question'],
            'options': options_data
        })
    return render_template('correction.html',
                           student_info=session['student_info'],
                           subjects=subjects_list,
                           current_subject=current_subject,
                           current_subject_idx=current_subject_idx,
                           questions=questions_with_answers)

@app.route('/my_results')
def my_results():
    if 'student_info' not in session:
        return redirect(url_for('home'))
    init_db()
    conn = get_db()
    c = conn.cursor()
    regno = session['student_info']['regno']
    c.execute('SELECT id FROM students WHERE regno = ?', (regno,))
    student = c.fetchone()
    if not student:
        conn.close()
        return render_template('my_results.html', attempts=[], student_info=session['student_info'])
    c.execute('''SELECT id, exam_date, total_score, total_questions, percentage
                 FROM exam_attempts WHERE student_id = ? ORDER BY exam_date DESC''', (student['id'],))
    attempts = c.fetchall()
    conn.close()
    return render_template('my_results.html', attempts=attempts, student_info=session['student_info'])

@app.route('/time_check')
def time_check():
    if 'start_time' not in session:
        return jsonify({'remaining': 0})
    elapsed = int(time.time() - session['start_time'])
    remaining = max(0, session['exam_duration'] - elapsed)
    return jsonify({'remaining': remaining})

# ══════════════════════════════════════════════════════════════════════════════
# PAST QUESTIONS ROUTES
# ══════════════════════════════════════════════════════════════════════════════

PAST_QUESTIONS_SCHOOLS = [
    "Thomas Adewunmi University",
]

PAST_QUESTIONS_DEPARTMENTS = {
    "Thomas Adewunmi University": [
        "Faculty of Sciences",
        "Faculty of Engineering",
        "Faculty of Arts",
        "Faculty of Social Sciences",
        "Faculty of Law",
        "Faculty of Medicine and Health Sciences",
        "Faculty of Education",
        "Faculty of Business Administration",
        "Faculty of Agriculture",
        "Faculty of Environmental Sciences",
        "Faculty of Computing and Applied Science",
    ]
}

PAST_QUESTIONS_COURSES = {
    "Faculty of Sciences": [
        "Physics", "Chemistry", "Biology", "Mathematics",
        "Computer Science", "Statistics", "Biochemistry",
        "Microbiology", "Geology", "Industrial Chemistry",
    ],
    "Faculty of Engineering": [
        "Civil Engineering", "Electrical/Electronic Engineering",
        "Mechanical Engineering", "Chemical Engineering",
        "Computer Engineering", "Agricultural Engineering",
        "Petroleum Engineering", "Mechatronics Engineering",
    ],
    "Faculty of Arts": [
        "English and Literary Studies", "History and International Studies",
        "Philosophy", "Fine and Applied Arts", "Theatre Arts",
        "Music", "Religious Studies", "Linguistics",
        "French", "Arabic Studies",
    ],
    "Faculty of Social Sciences": [
        "Economics", "Political Science", "Sociology",
        "Psychology", "Mass Communication", "Geography",
        "International Relations", "Criminology and Security Studies",
    ],
    "Faculty of Law": [
        "Law",
    ],
    "Faculty of Medicine and Health Sciences": [
        "Medicine and Surgery", "Nursing Science",
        "Medical Laboratory Science", "Physiotherapy",
        "Pharmacy", "Radiography", "Public Health",
        "Optometry", "Dentistry",
    ],
    "Faculty of Education": [
        "Education / Mathematics", "Education / English",
        "Education / Biology", "Education / Chemistry",
        "Education / Physics", "Education / Economics",
        "Adult Education", "Educational Administration",
        "Guidance and Counselling", "Library Science",
    ],
    "Faculty of Business Administration": [
        "Business Administration", "Accounting",
        "Banking and Finance", "Marketing",
        "Public Administration", "Entrepreneurship",
        "Insurance", "Office and Information Management",
    ],
    "Faculty of Agriculture": [
        "Agronomy", "Animal Science",
        "Fisheries and Aquaculture", "Forestry and Wood Technology",
        "Agricultural Economics", "Food Science and Technology",
        "Soil Science", "Agricultural Extension",
    ],
    "Faculty of Environmental Sciences": [
        "Architecture", "Urban and Regional Planning",
        "Estate Management", "Quantity Surveying",
        "Building Technology", "Surveying and Geoinformatics",
    ],
    "Faculty of Computing and Applied Science": [],
}

LEVEL_SPECIFIC_COURSES = {
    ("Faculty of Computing and Applied Science", "200 Level"): [
        # Harmattan Semester
        "COS 201 - Computer Programming I",
        "SEN 201 - Introduction to Software Engineering",
        "MTH 201 - Mathematical Methods I",
        "ENT 211 - Entrepreneurship and Innovation",
        "TAU-CSC 201 - Systems Analysis and Design",
        "TAU-CSC 207 - PC and Mobile Devices: Installation, Maintenance and Upgrade",
        "CSC 203 - Discrete Structures",
        "IFT 211 - Digital Logic Design",
        "CSC 299 - SIWES I",
        "TAU 201 - Saylor Academy: Upper-Intermediate English (ESL 003)",
        # Rain Semester
        "COS 202 - Computer Programming II",
        "IFT 212 - Computer Architecture and Organization",
        "MTH 202 - Elementary Differential Equations",
        "GST 212 - Philosophy, Logic and Human Existence",
        "TAU-CSC 208 - Desktop Publishing",
        "TAU-CSC 210 - Multimedia Creation and Editing",
        "DSA 108 - Photography",
        "TAU 202 - Saylor Academy: Advanced English (ESL 004)",
    ],
    ("Faculty of Computing and Applied Science", "300 Level"): [
        # Harmattan Semester
        "CSC 301 - Data Structures",
        "CSC 309 - Artificial Intelligence",
        "CYB 201 - Introduction to Cyber Security and Strategy",
        "ICT 305 - Data Communication System and Network",
        "TAU-CSC 307 - Mobile App Development with C#",
        "TAU-CSC 311 - Object Oriented Programming with Java",
        "TAU-CSC 313 - Troubleshooting and Repairs of Computer Systems and Mobile Devices",
        "TAU-EDX 301 - Saylor Academy: Business-Proficient English (ESL 005)",
        "TAU-EDX 303 - Creative Innovative Teams with Design Thinking",
        # Rain Semester
        "CSC 308 - Operating Systems",
        "CSC 322 - Computer Science Innovation and New Technology",
        "CSC 399 - SIWES II",
        "DTS 304 - Data Management I",
        "ENT 312 - Venture Creation",
        "GST 312 - Peace and Conflict Resolution",
        "TAU-SEN 306 - Advanced Web Development",
        "TAU-ENT 108 - Photography",
        "TAU-EDX 302 - Resuming, Networking and Interviewing Skills",
        "TAU-EDX 306 - Innovation and Entrepreneurship",
    ],
}

LEVELS_6 = ["100 Level", "200 Level", "300 Level", "400 Level", "500 Level", "600 Level"]
LEVELS_7 = ["100 Level", "200 Level", "300 Level", "400 Level", "500 Level", "600 Level", "700 Level"]
LEVELS_STD = ["100 Level", "200 Level", "300 Level", "400 Level", "500 Level"]

SIX_LEVEL_COURSES = {"Law", "Physiotherapy"}
SEVEN_LEVEL_COURSES = {"Medicine and Surgery", "Dentistry", "Optometry"}


def get_levels_for_course(course):
    if course in SEVEN_LEVEL_COURSES:
        return LEVELS_7
    if course in SIX_LEVEL_COURSES:
        return LEVELS_6
    return LEVELS_STD


@app.route('/past-questions')
@login_required
def past_questions_home():
    return render_template('past_questions_home.html')


@app.route('/past-questions/school')
@login_required
def past_questions_school():
    mode = request.args.get('mode', 'access')
    return render_template('past_questions_school.html', schools=PAST_QUESTIONS_SCHOOLS, mode=mode)


@app.route('/past-questions/level')
@login_required
def past_questions_level():
    school = request.args.get('school', '')
    mode = request.args.get('mode', 'access')
    if not school or school not in PAST_QUESTIONS_SCHOOLS:
        return redirect(url_for('past_questions_home'))
    return render_template('past_questions_level.html', school=school, levels=LEVELS_7, mode=mode)


@app.route('/past-questions/department')
@login_required
def past_questions_department():
    school = request.args.get('school', '')
    level = request.args.get('level', '')
    mode = request.args.get('mode', 'access')
    if not school or school not in PAST_QUESTIONS_SCHOOLS or not level:
        return redirect(url_for('past_questions_home'))
    departments = PAST_QUESTIONS_DEPARTMENTS.get(school, [])
    return render_template('past_questions_department.html', school=school, level=level, departments=departments, mode=mode)


@app.route('/past-questions/course')
@login_required
def past_questions_course():
    school = request.args.get('school', '')
    level = request.args.get('level', '')
    department = request.args.get('department', '')
    mode = request.args.get('mode', 'access')
    if not school or not level or not department:
        return redirect(url_for('past_questions_home'))
    courses = LEVEL_SPECIFIC_COURSES.get(
        (department, level),
        PAST_QUESTIONS_COURSES.get(department, [])
    )
    return render_template('past_questions_course.html', school=school, level=level, department=department, courses=courses, mode=mode)


@app.route('/past-questions/upload-submit', methods=['GET', 'POST'])
@login_required
def past_questions_upload_submit():
    school = request.args.get('school', '') or request.form.get('school', '')
    level = request.args.get('level', '') or request.form.get('level', '')
    department = request.args.get('department', '') or request.form.get('department', '')
    course = request.args.get('course', '') or request.form.get('course', '')
    if not school or not level or not department or not course:
        return redirect(url_for('past_questions_home'))

    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        file = request.files.get('file')
        if file and file.filename:
            ext = os.path.splitext(secure_filename(file.filename))[1].lower()
            unique_name = f"{uuid.uuid4().hex}{ext}"
            upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'pq')
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, unique_name))
            db = get_mongo()
            if db is not None:
                db['past_question_files'].insert_one({
                    'school': school,
                    'level': level,
                    'department': department,
                    'course': course,
                    'filename': unique_name,
                    'original_name': file.filename,
                    'upload_date': datetime.utcnow().isoformat(),
                    'file_type': file.content_type or 'application/octet-stream'
                })
            if is_xhr:
                return jsonify({'success': True, 'message': 'File uploaded successfully!'})
            flash('File uploaded successfully!', 'success')
        else:
            if is_xhr:
                return jsonify({'success': False, 'error': 'Please select a file to upload.'}), 400
            flash('Please select a file to upload.', 'error')
        return redirect(url_for('past_questions_upload_submit',
                                school=school, level=level, department=department, course=course))

    return render_template('past_questions_upload_submit.html',
                           school=school, level=level, department=department, course=course)


@app.route('/past-questions/view')
@login_required
def past_questions_view():
    school = request.args.get('school', '')
    level = request.args.get('level', '')
    department = request.args.get('department', '')
    course = request.args.get('course', '')
    if not school or not level or not department or not course:
        return redirect(url_for('past_questions_home'))
    files = []
    db = get_mongo()
    if db is not None:
        results = db['past_question_files'].find(
            {'school': school, 'level': level, 'department': department, 'course': course},
            {'_id': 0}
        )
        files = list(results)
    return render_template('past_questions_view.html',
                           school=school, level=level, department=department, course=course, files=files)


@app.route('/past-questions/files/<path:filename>')
@login_required
def past_questions_file(filename):
    upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'pq')
    return send_from_directory(upload_dir, filename)


# ── Admin ──────────────────────────────────────────────────────────────────────
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if email in ADMIN_CREDENTIALS and ADMIN_CREDENTIALS[email] == password:
            session['admin_logged_in'] = True
            session['admin_email'] = email
            return redirect(url_for('admin_dashboard'))
        error = 'Invalid email or password. Please try again.'
    return render_template('admin_login.html', error=error)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_email', None)
    return redirect(url_for('admin_login'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    db = get_mongo()
    files = []
    user_count = 0
    file_count = 0
    if db is not None:
        raw = list(db['past_question_files'].find({}))
        for f in raw:
            f['_id'] = str(f['_id'])
        files = raw
        file_count = len(files)
        user_count = db['users'].count_documents({})
    return render_template('admin_dashboard.html',
                           files=files, file_count=file_count,
                           user_count=user_count,
                           admin_email=session.get('admin_email', ''))


@app.route('/admin/delete-file', methods=['POST'])
@admin_required
def admin_delete_file():
    from bson import ObjectId
    file_id = request.form.get('file_id', '')
    filename = request.form.get('filename', '')
    db = get_mongo()
    if db is not None and file_id:
        try:
            db['past_question_files'].delete_one({'_id': ObjectId(file_id)})
        except Exception:
            pass
    if filename:
        fpath = os.path.join(app.root_path, 'static', 'uploads', 'pq', filename)
        if os.path.exists(fpath):
            os.remove(fpath)
    flash('File deleted.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/api/ai-chat', methods=['POST'])
@login_required
def ai_chat():
    data = request.get_json(silent=True) or {}
    messages = data.get('messages', [])
    if not messages:
        return jsonify({'error': 'No messages provided'}), 400
    safe_messages = [
        {'role': m['role'], 'content': m['content']}
        for m in messages
        if m.get('role') in ('user', 'assistant') and m.get('content')
    ]
    system_msg = {
        'role': 'system',
        'content': (
            'You are a helpful AI study assistant for Beyond The Classroom (BTC), a Nigerian educational platform. '
            'You answer academic questions clearly and thoroughly, help explain concepts, '
            'solve problems step by step, and assist with exam practice questions for UTME, university courses, and more. '
            'Be concise yet thorough, and use a friendly, encouraging tone.'
        )
    }
    try:
        response = get_ai_client().chat.completions.create(
            model='gpt-5',
            messages=[system_msg] + safe_messages,
            max_completion_tokens=8192,
        )
        reply = response.choices[0].message.content or ''
        return jsonify({'reply': reply})
    except Exception as e:
        err = str(e)
        if 'FREE_CLOUD_BUDGET_EXCEEDED' in err:
            return jsonify({'error': 'FREE_CLOUD_BUDGET_EXCEEDED'}), 429
        return jsonify({'error': 'AI service error. Please try again.'}), 500


# ── Direct Messages ─────────────────────────────────────────────────────────────
def save_dm(from_email, from_name, to_email, to_name, text):
    msg_id = str(uuid.uuid4())
    db = get_mongo()
    if db is not None:
        db.direct_messages.insert_one({
            'id': msg_id,
            'from_email': from_email,
            'from_name': from_name,
            'to_email': to_email,
            'to_name': to_name,
            'text': text,
            'timestamp': datetime.utcnow().isoformat(),
            'read': False
        })
    return msg_id

def get_dms_between(user1, user2):
    db = get_mongo()
    if db is not None:
        msgs = list(db.direct_messages.find({
            '$or': [
                {'from_email': user1, 'to_email': user2},
                {'from_email': user2, 'to_email': user1},
            ]
        }).sort('timestamp', 1).limit(300))
        for m in msgs:
            m['_id'] = str(m.get('_id', ''))
        db.direct_messages.update_many(
            {'to_email': user1, 'from_email': user2, 'read': False},
            {'$set': {'read': True}}
        )
        return msgs
    return []

def get_inbox_conversations(user_email):
    db = get_mongo()
    if db is not None:
        all_msgs = list(db.direct_messages.find({
            '$or': [{'from_email': user_email}, {'to_email': user_email}]
        }).sort('timestamp', -1).limit(500))
        seen = {}
        for m in all_msgs:
            partner = m['to_email'] if m['from_email'] == user_email else m['from_email']
            partner_name = m['to_name'] if m['from_email'] == user_email else m['from_name']
            if partner not in seen:
                unread = m.get('to_email') == user_email and not m.get('read', True)
                seen[partner] = {
                    'email': partner,
                    'name': partner_name,
                    'last_msg': m.get('text', ''),
                    'timestamp': m.get('timestamp', ''),
                    'unread': unread
                }
        return list(seen.values())
    return []

@app.route('/messages')
@login_required
def inbox():
    user = session.get('user', {})
    conversations = get_inbox_conversations(user.get('email', ''))
    return render_template('inbox.html', conversations=conversations, user=user)

@app.route('/messages/<path:partner_email>')
@login_required
def direct_message_page(partner_email):
    user = session.get('user', {})
    msgs = get_dms_between(user.get('email', ''), partner_email)
    partner_name = request.args.get('name', '').strip() or partner_email
    for m in msgs:
        if m.get('from_email') == partner_email:
            partner_name = m.get('from_name', partner_email)
            break
        if m.get('to_email') == partner_email:
            partner_name = m.get('to_name', partner_email)
            break
    return render_template('direct_message.html', messages=msgs,
                           partner_email=partner_email, partner_name=partner_name, user=user)

@app.route('/messages/send', methods=['POST'])
@login_required
def send_dm():
    user = session.get('user', {})
    data = request.get_json(silent=True) or {}
    to_email = data.get('to_email', '').strip()
    to_name = data.get('to_name', '').strip()
    text = data.get('text', '').strip()
    if not to_email or not text:
        return jsonify({'success': False, 'error': 'Missing fields'}), 400
    msg_id = save_dm(user.get('email', ''), user.get('full_name', 'Unknown'), to_email, to_name or to_email, text)
    return jsonify({'success': True, 'id': msg_id, 'timestamp': datetime.utcnow().isoformat()})

@app.route('/messages/unread-count')
@login_required
def dm_unread_count():
    user = session.get('user', {})
    db = get_mongo()
    count = 0
    if db is not None:
        count = db.direct_messages.count_documents({'to_email': user.get('email', ''), 'read': False})
    return jsonify({'count': count})


init_db()
get_mongo()

# ── Group Study ────────────────────────────────────────────────────────────────
def generate_room_code():
    return str(random.randint(100000, 999999))

def get_room(code):
    db = get_mongo()
    if db is not None:
        r = db.rooms.find_one({'code': code})
        if r: r['_id'] = str(r['_id'])
        return r
    conn = get_db()
    row = conn.execute('SELECT * FROM rooms WHERE code = ?', (code,)).fetchone()
    conn.close()
    if not row: return None
    d = dict(row)
    d['members'] = json.loads(d.get('members', '[]'))
    return d

def save_room_message(msg):
    db = get_mongo()
    if db is not None:
        db.messages.insert_one({**msg})
    else:
        conn = get_db()
        conn.execute('INSERT OR IGNORE INTO room_messages (msg_id, room_code, data) VALUES (?,?,?)',
                     (msg['id'], msg['room_code'], json.dumps(msg)))
        conn.commit(); conn.close()

def get_room_messages(code):
    db = get_mongo()
    if db is not None:
        msgs = list(db.messages.find({'room_code': code}).sort('timestamp', 1).limit(300))
        for m in msgs: m['_id'] = str(m.get('_id', ''))
        return msgs
    conn = get_db()
    rows = conn.execute('SELECT data FROM room_messages WHERE room_code=? ORDER BY created_at LIMIT 300', (code,)).fetchall()
    conn.close()
    return [json.loads(r['data']) for r in rows]

@app.route('/group-study')
@login_required
def group_study():
    return render_template('group_study.html')

@app.route('/group-study/new')
@login_required
def group_study_create_page():
    return render_template('create_room.html')

@app.route('/group-study/join-room')
@login_required
def group_study_join_page():
    return render_template('join_room.html')

@app.route('/group-study/create', methods=['POST'])
@login_required
def create_room_api():
    data = request.get_json(silent=True) or {}
    code = generate_room_code()
    db = get_mongo()
    if db is not None:
        while db.rooms.find_one({'code': code}): code = generate_room_code()
    password = data.get('password', '').strip()
    password_hash = hash_password(password) if password else None
    user = session.get('user', {})
    member = {'email': user.get('email',''), 'name': user.get('full_name',''), 'joined_at': datetime.utcnow().isoformat()}
    room = {'code': code, 'creator_email': user.get('email',''), 'creator_name': user.get('full_name',''),
            'password_hash': password_hash, 'has_password': bool(password),
            'members': [member], 'created_at': datetime.utcnow()}
    if db is not None:
        db.rooms.insert_one(room)
    else:
        conn = get_db()
        conn.execute('INSERT INTO rooms (code,creator_email,creator_name,password_hash,has_password,members) VALUES (?,?,?,?,?,?)',
                     (code, user.get('email',''), user.get('full_name',''), password_hash, int(bool(password)), json.dumps([member])))
        conn.commit(); conn.close()
    return jsonify({'success': True, 'code': code})

@app.route('/group-study/join', methods=['POST'])
@login_required
def join_room_api():
    data = request.get_json(silent=True) or {}
    code = data.get('code', '').strip()
    password = data.get('password', '').strip()
    room = get_room(code)
    if not room: return jsonify({'success': False, 'message': 'Room not found. Check the code and try again.'}), 404
    if room.get('has_password'):
        ph = room.get('password_hash', '')
        if not password or not bcrypt.checkpw(password.encode(), ph.encode()):
            return jsonify({'success': False, 'message': 'Incorrect password.'}), 401
    return jsonify({'success': True, 'code': code})

ROOM_ALLOWED_EXT = {'jpg','jpeg','png','gif','webp','pdf','doc','docx','ppt','pptx','xls','xlsx','txt','zip','webm','ogg','mp4','mp3','m4a'}
ROOM_IMAGE_EXT   = {'jpg','jpeg','png','gif','webp'}
ROOM_AUDIO_EXT   = {'webm','ogg','mp4','mp3','m4a'}

@app.route('/group-study/room/<code>/upload', methods=['POST'])
@login_required
def room_upload(code):
    room = get_room(code)
    if not room:
        return jsonify({'success': False, 'error': 'Room not found'}), 404
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    f = request.files['file']
    if not f or f.filename == '':
        return jsonify({'success': False, 'error': 'Empty file'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ROOM_ALLOWED_EXT:
        return jsonify({'success': False, 'error': f'File type .{ext} not allowed'}), 400
    from werkzeug.utils import secure_filename
    safe = secure_filename(f.filename)
    uid = str(uuid.uuid4())[:8]
    unique_name = f"{uid}_{safe}"
    upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'rooms', code)
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, unique_name)
    f.save(save_path)
    file_size = os.path.getsize(save_path)
    file_kind = 'image' if ext in ROOM_IMAGE_EXT else 'audio' if ext in ROOM_AUDIO_EXT else 'pdf' if ext == 'pdf' else 'doc'
    file_url = url_for('static', filename=f'uploads/rooms/{code}/{unique_name}')
    return jsonify({
        'success': True,
        'file_url': file_url,
        'file_name': f.filename,
        'file_size': file_size,
        'file_kind': file_kind,
        'ext': ext
    })

@app.route('/group-study/room/<code>')
@login_required
def room_page(code):
    room = get_room(code)
    if not room: return redirect(url_for('group_study'))
    user = session.get('user', {})
    db = get_mongo()
    member = {'email': user.get('email',''), 'name': user.get('full_name',''), 'joined_at': datetime.utcnow().isoformat()}
    if db is not None:
        emails = [m.get('email') for m in room.get('members', [])]
        if user.get('email') not in emails:
            db.rooms.update_one({'code': code}, {'$push': {'members': member}})
    messages = get_room_messages(code)
    room_members = room.get('members', [])
    return render_template('room.html', room=room, user=user, messages=messages, room_members=room_members)

# ── Group Study SocketIO handlers ───────────────────────────────────────────────
@socketio.on('join')
def on_join(data):
    code = data.get('code'); name = data.get('name'); email = data.get('email')
    socket_rooms[request.sid] = {'code': code, 'name': name, 'email': email}
    sio_join(code)
    emit('user_joined', {'name': name, 'email': email}, to=code, include_self=False)

@socketio.on('leave')
def on_leave(data):
    code = data.get('code'); name = data.get('name')
    socket_rooms.pop(request.sid, None)
    sio_leave(code)
    emit('user_left', {'name': name}, to=code, include_self=False)
    _maybe_expire_room(code)

@socketio.on('disconnect')
def on_disconnect():
    info = socket_rooms.pop(request.sid, None)
    if info:
        code = info.get('code')
        emit('user_left', {'name': info.get('name', '')}, to=code, include_self=False)
        _maybe_expire_room(code)

@socketio.on('mark_seen')
def on_mark_seen(data):
    code = data.get('code'); msg_id = data.get('msg_id')
    emit('message_seen', {'msg_id': msg_id}, to=code, include_self=False)

@socketio.on('message')
def on_message(data):
    code = data.get('code', '')
    text = data.get('text', '').strip()
    msg_type = data.get('type', 'text')
    # File messages may have empty text — allow them through
    if not text and msg_type != 'file': return
    msg = {'id': str(uuid.uuid4()), 'room_code': code, 'text': text,
           'sender': data.get('sender'), 'sender_email': data.get('sender_email'),
           'timestamp': datetime.utcnow().isoformat(), 'type': msg_type,
           'reply_to': data.get('reply_to'), 'reactions': {}, 'pinned': False,
           'starred_by': [], 'deleted': False, 'forwarded': data.get('forwarded', False)}
    # Pass through file metadata if present
    if msg_type == 'file':
        for field in ('file_url', 'file_name', 'file_size', 'file_kind', 'ext'):
            if field in data: msg[field] = data[field]
    save_room_message(msg)
    emit('message', msg, to=code)
    if '@all' in text.lower():
        emit('mention_all', {'sender': data.get('sender'), 'room_code': code, 'msg_id': msg['id']}, to=code, include_self=False)
    if text.strip().lower().startswith('@ai '):
        question = text[4:].strip()
        try:
            ai_resp = get_ai_client().chat.completions.create(
                model='gpt-5',
                messages=[{'role':'system','content':'You are BTC AI, a helpful study assistant in a group study room. Be concise and helpful.'},
                          {'role':'user','content': question}],
                max_completion_tokens=1024)
            ai_text = ai_resp.choices[0].message.content or 'I could not generate a response.'
        except Exception as e:
            print(f'[BTC AI Error] {type(e).__name__}: {e}')
            err_str = str(e)
            if 'api_key' in err_str.lower() or 'authentication' in err_str.lower() or 'unauthorized' in err_str.lower():
                ai_text = '⚠️ BTC AI needs the OpenAI integration configured. Please ask the admin to add the OpenAI integration in the project settings.'
            elif 'budget' in err_str.lower() or 'quota' in err_str.lower() or 'limit' in err_str.lower():
                ai_text = '⚠️ BTC AI usage limit reached. Please try again later.'
            else:
                ai_text = f'⚠️ BTC AI error: {err_str[:120]}'
        ai_msg = {'id': str(uuid.uuid4()), 'room_code': code, 'text': ai_text,
                  'sender': 'BTC AI', 'sender_email': 'ai@btc',
                  'timestamp': datetime.utcnow().isoformat(), 'type': 'ai',
                  'reply_to': {'id': msg['id'], 'text': text, 'sender': data.get('sender')},
                  'reactions': {}, 'pinned': False, 'starred_by': [], 'deleted': False, 'forwarded': False}
        save_room_message(ai_msg)
        emit('message', ai_msg, to=code)

@socketio.on('typing')
def on_typing(data): emit('typing', {'name': data.get('name')}, to=data.get('code'), include_self=False)

@socketio.on('stop_typing')
def on_stop_typing(data): emit('stop_typing', {'name': data.get('name')}, to=data.get('code'), include_self=False)

@socketio.on('react')
def on_react(data):
    code = data.get('code'); msg_id = data.get('msg_id'); emoji = data.get('emoji'); uemail = data.get('email')
    db = get_mongo()
    if db is not None:
        msg = db.messages.find_one({'id': msg_id, 'room_code': code})
        if msg:
            reactions = msg.get('reactions', {})
            if emoji not in reactions: reactions[emoji] = []
            if uemail in reactions[emoji]: reactions[emoji].remove(uemail)
            else: reactions[emoji].append(uemail)
            if not reactions[emoji]: del reactions[emoji]
            db.messages.update_one({'id': msg_id}, {'$set': {'reactions': reactions}})
            emit('reaction_updated', {'msg_id': msg_id, 'reactions': reactions}, to=code)

@socketio.on('pin_message')
def on_pin(data):
    code = data.get('code'); msg_id = data.get('msg_id')
    db = get_mongo()
    if db is not None:
        db.messages.update_one({'id': msg_id}, {'$set': {'pinned': True}})
        emit('message_pinned', {'msg_id': msg_id}, to=code)

@socketio.on('delete_message')
def on_delete(data):
    code = data.get('code'); msg_id = data.get('msg_id'); uemail = data.get('email')
    db = get_mongo()
    if db is not None:
        msg = db.messages.find_one({'id': msg_id})
        if msg and msg.get('sender_email') == uemail:
            db.messages.update_one({'id': msg_id}, {'$set': {'deleted': True, 'text': 'This message was deleted'}})
            emit('message_deleted', {'msg_id': msg_id}, to=code)

@socketio.on('star_message')
def on_star(data):
    code = data.get('code'); msg_id = data.get('msg_id'); uemail = data.get('email')
    db = get_mongo()
    if db is not None:
        msg = db.messages.find_one({'id': msg_id})
        if msg:
            starred = msg.get('starred_by', [])
            if uemail in starred: starred.remove(uemail); is_starred = False
            else: starred.append(uemail); is_starred = True
            db.messages.update_one({'id': msg_id}, {'$set': {'starred_by': starred}})
            emit('message_starred', {'msg_id': msg_id, 'starred': is_starred, 'email': uemail}, to=code)

@socketio.on('get_members')
def on_get_members(data):
    room = get_room(data.get('code', ''))
    members = room.get('members', []) if room else []
    emit('room_members', {'members': members})

# ── WebRTC call relay ──────────────────────────────────────────────────────────
@socketio.on('call_offer')
def on_call_offer(data):
    emit('call_offer', data, to=data.get('code'), include_self=False)

@socketio.on('call_answer')
def on_call_answer(data):
    emit('call_answer', data, to=data.get('code'), include_self=False)

@socketio.on('ice_candidate')
def on_ice_candidate(data):
    emit('ice_candidate', data, to=data.get('code'), include_self=False)

@socketio.on('call_ended')
def on_call_ended(data):
    emit('call_ended', data, to=data.get('code'), include_self=False)

@socketio.on('remove_member')
def on_remove_member(data):
    code = data.get('code', '')
    target_email = data.get('email', '')
    requester_email = data.get('requester_email', '')
    room = get_room(code)
    if not room:
        return
    if room.get('creator_email') != requester_email:
        return
    db = get_mongo()
    if db is not None:
        db.rooms.update_one({'code': code}, {'$pull': {'members': {'email': target_email}}})
    else:
        conn = get_db()
        row = conn.execute('SELECT members FROM rooms WHERE code = ?', (code,)).fetchone()
        if row:
            members = json.loads(row['members'])
            members = [m for m in members if m.get('email') != target_email]
            conn.execute('UPDATE rooms SET members = ? WHERE code = ?', (json.dumps(members), code))
            conn.commit()
        conn.close()
    emit('member_removed', {'email': target_email, 'by': requester_email}, to=code)


init_db()
get_mongo()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
