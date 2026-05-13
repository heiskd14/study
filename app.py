from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash, send_from_directory, Response, make_response
from werkzeug.utils import secure_filename
from functools import wraps
import uuid
from flask_session import Session
import json
import random
import time
import os
from datetime import datetime
import sqlite3
import bcrypt
import urllib.request
import urllib.error

app = Flask(__name__)
app.secret_key = 'tau-online-study-secret-key-2025'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
app.config['SESSION_PERMANENT'] = False
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
Session(app)

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
    resp = make_response(render_template('home.html', user=session.get('user')))
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

# ── Auth sync: JS calls this after JWT login to set Flask session ──────────────
@app.route('/auth/sync', methods=['POST'])
def auth_sync():
    data = request.get_json(silent=True) or {}
    user = data.get('user', {})
    if user:
        session['user'] = {
            'full_name': user.get('name', ''),
            'email': user.get('email', '')
        }
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'No user data'}), 400

# ── Exam registration ──────────────────────────────────────────────────────────
@app.route('/register-exam')
def register_page():
    session.pop('student_info', None)
    return render_template('registration.html')

@app.route('/practice')
def subject_selection_home():
    session.pop('student_info', None)
    return render_template('registration.html')

@app.route('/register', methods=['POST'])
def register():
    name = request.form.get('name', '').strip()
    regno = request.form.get('regno', '').strip()
    if not name or not regno:
        return render_template('registration.html', error="Please enter both Name and Registration Number")
    session['student_info'] = {'name': name, 'regno': regno}
    return redirect(url_for('subject_selection'))

@app.route('/subject_selection')
def subject_selection():
    if 'student_info' not in session:
        return redirect(url_for('home'))
    all_subjects = [
        "Use of English", "Mathematics", "Literature in English",
        "Government", "Economics", "Commerce",
        "Physics", "Chemistry", "Biology",
        "Principles of Accounts", "Christian Religious Studies"
    ]
    return render_template('subject_selection.html', subjects=all_subjects)

@app.route('/select_subjects', methods=['POST'])
def select_subjects():
    if 'student_info' not in session:
        return redirect(url_for('home'))

    all_subjects = [
        "Use of English", "Mathematics", "Literature in English",
        "Government", "Economics", "Commerce",
        "Physics", "Chemistry", "Biology",
        "Principles of Accounts", "Christian Religious Studies"
    ]

    selected_subjects = request.form.getlist('subjects')
    if len(selected_subjects) < 1:
        return render_template('subject_selection.html', subjects=all_subjects,
                               error="Please select at least 1 subject")

    # Read user selections with safe fallbacks
    try:
        time_limit_min = int(request.form.get('time_limit', 60))
        if time_limit_min not in (15, 30, 60):
            time_limit_min = 60
    except (ValueError, TypeError):
        time_limit_min = 60

    try:
        num_questions = int(request.form.get('num_questions', 30))
        if num_questions not in (20, 30, 45, 60):
            num_questions = 30
    except (ValueError, TypeError):
        num_questions = 30

    subject_files = {
        "Use of English": "use_of_english.json",
        "Mathematics": "mathematics.json",
        "Literature in English": "literature_in_english.json",
        "Government": "government.json",
        "Economics": "economics.json",
        "Commerce": "commerce.json",
        "Physics": "physics.json",
        "Chemistry": "chemistry.json",
        "Biology": "biology.json",
        "Principles of Accounts": "principles_of_accounts.json",
        "Christian Religious Studies": "christian_religious_studies.json"
    }

    subject_questions = {}
    subject_answers = {}
    for subj in selected_subjects:
        file = subject_files.get(subj)
        if file and os.path.exists(file):
            qs = load_questions(file)
            count = min(num_questions, len(qs))
            subject_questions[subj] = random.sample(qs, count)
            subject_answers[subj] = [None] * count

    session['subject_questions'] = subject_questions
    session['subject_answers'] = subject_answers
    session['start_time'] = time.time()
    session['exam_duration'] = time_limit_min * 60
    session['exam_settings'] = {'time_limit_min': time_limit_min, 'num_questions': num_questions}
    session['current_subject'] = selected_subjects[0]
    session['current_question'] = 0
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
                           time_remaining=remaining)

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
    init_db()
    conn = get_db()
    c = conn.cursor()
    name = session['student_info']['name']
    regno = session['student_info']['regno']
    c.execute('INSERT OR IGNORE INTO students (name, regno) VALUES (?, ?)', (name, regno))
    c.execute('SELECT id FROM students WHERE regno = ?', (regno,))
    student_id = c.fetchone()[0]
    results = []
    total_score = 0
    total_questions = 0
    c.execute('INSERT INTO exam_attempts (student_id) VALUES (?)', (student_id,))
    attempt_id = c.lastrowid
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
        c.execute('INSERT INTO subject_scores (attempt_id, subject, score, total) VALUES (?, ?, ?, ?)',
                  (attempt_id, subj, score, len(qs)))
        total_score += score
        total_questions += len(qs)
        percent = (score / len(qs) * 100) if qs else 0
        results.append((subj, score, len(qs), percent))
    percentage = (total_score / total_questions * 100) if total_questions > 0 else 0
    c.execute('UPDATE exam_attempts SET total_score=?, total_questions=?, percentage=? WHERE id=?',
              (total_score, total_questions, percentage, attempt_id))
    conn.commit()
    conn.close()

    # Also save to MongoDB if available
    db = get_mongo()
    if db:
        try:
            db.exam_results.insert_one({
                'name': name,
                'regno': regno,
                'results': [{'subject': s, 'score': sc, 'total': t, 'percent': p}
                             for s, sc, t, p in results],
                'total_score': total_score,
                'total_questions': total_questions,
                'percentage': percentage,
                'exam_date': datetime.utcnow()
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
                           results=session['results'])

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
    "Faculty of Computing and Applied Science": [
        "Computer Science", "Information Technology",
        "Software Engineering", "Cyber Security",
        "Data Science and Analytics", "Artificial Intelligence",
        "Information Systems", "Computer Applications",
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
    courses = PAST_QUESTIONS_COURSES.get(department, [])
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


init_db()
get_mongo()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
