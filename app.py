from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_session import Session
import json
import random
import time
import os
from datetime import datetime
import sqlite3

app = Flask(__name__)
app.secret_key = 'jamb-cbt-secret-key-2025'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
app.config['SESSION_PERMANENT'] = False
Session(app)

DB_PATH = 'exam_results.db'

def init_db():
    """Initialize the database with required tables"""
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
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def load_questions(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def float_safe(val):
    try:
        return float(str(val).strip())
    except:
        return str(val).strip()

@app.route('/')
def index():
    session.clear()
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
        return redirect(url_for('index'))
    
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
        return redirect(url_for('index'))
    
    selected_subjects = request.form.getlist('subjects')
    
    if "Use of English" not in selected_subjects:
        selected_subjects.append("Use of English")
    
    if len(selected_subjects) < 1:
        all_subjects = [
            "Use of English", "Mathematics", "Literature in English",
            "Government", "Economics", "Commerce",
            "Physics", "Chemistry", "Biology",
            "Principles of Accounts", "Christian Religious Studies"
        ]
        error = "Please select at least 1 subject"
        return render_template('subject_selection.html', subjects=all_subjects, error=error)
    
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
            num_questions = 60 if subj == "Use of English" else 40
            subject_questions[subj] = random.sample(qs, min(num_questions, len(qs)))
            subject_answers[subj] = [None] * len(subject_questions[subj])
            print(f"Loaded {num_questions} questions for {subj} from {len(qs)} available")
    
    session['subject_questions'] = subject_questions
    session['subject_answers'] = subject_answers
    session['start_time'] = time.time()
    session['exam_duration'] = 7200
    session['current_subject'] = selected_subjects[0]
    session['current_question'] = 0
    
    return redirect(url_for('exam'))

@app.route('/exam')
def exam():
    if 'student_info' not in session:
        return redirect(url_for('index'))
    
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
        return redirect(url_for('index'))
    
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
        question_num = int(request.form.get('question_num'))
        session['current_question'] = question_num
    elif action == 'switch_subject':
        new_subject = request.form.get('subject')
        session['current_subject'] = new_subject
        session['current_question'] = 0
    elif action == 'prev_subject':
        current_idx = subjects.index(current_subject)
        if current_idx > 0:
            session['current_subject'] = subjects[current_idx - 1]
            session['current_question'] = 0
    elif action == 'next_subject':
        current_idx = subjects.index(current_subject)
        if current_idx < len(subjects) - 1:
            session['current_subject'] = subjects[current_idx + 1]
            session['current_question'] = 0
    
    session.modified = True
    return redirect(url_for('exam'))

@app.route('/submit', methods=['POST'])
def submit():
    if 'student_info' not in session:
        return redirect(url_for('index'))
    
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
    c.execute('UPDATE exam_attempts SET total_score = ?, total_questions = ?, percentage = ? WHERE id = ?',
             (total_score, total_questions, percentage, attempt_id))
    
    conn.commit()
    conn.close()
    
    session['results'] = results
    session['submitted'] = True
    
    return redirect(url_for('results'))

@app.route('/results')
def results():
    if 'student_info' not in session or 'results' not in session:
        return redirect(url_for('index'))
    
    return render_template('results.html',
                         student_info=session['student_info'],
                         results=session['results'])

@app.route('/correction')
def correction():
    if 'student_info' not in session or 'results' not in session:
        return redirect(url_for('index'))
    
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
        return redirect(url_for('index'))
    
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

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
