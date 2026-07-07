from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
import sqlite3, hashlib, os, random, string
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.urandom(24)

DB_PATH     = os.path.join(os.path.dirname(__file__), 'instance', 'platform.db')
UPLOAD_DIR  = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT UNIQUE NOT NULL,
            password  TEXT NOT NULL,
            role      TEXT NOT NULL CHECK(role IN ('teacher','student')),
            full_name TEXT
        );

        CREATE TABLE IF NOT EXISTS exams (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            description TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            is_active   INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS questions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id    INTEGER NOT NULL,
            text       TEXT NOT NULL,
            option_a   TEXT NOT NULL,
            option_b   TEXT NOT NULL,
            option_c   TEXT NOT NULL,
            option_d   TEXT NOT NULL,
            answer     TEXT NOT NULL CHECK(answer IN ('a','b','c','d')),
            image_path TEXT DEFAULT NULL,
            marks      INTEGER DEFAULT 1,
            FOREIGN KEY(exam_id) REFERENCES exams(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id   INTEGER NOT NULL,
            exam_id      INTEGER NOT NULL,
            score        INTEGER NOT NULL,
            total        INTEGER NOT NULL,
            submitted_at TEXT DEFAULT (datetime('now')),
            UNIQUE(student_id, exam_id),
            FOREIGN KEY(student_id) REFERENCES users(id),
            FOREIGN KEY(exam_id)    REFERENCES exams(id)
        );

        CREATE TABLE IF NOT EXISTS answers (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            question_id   INTEGER NOT NULL,
            chosen        TEXT,
            FOREIGN KEY(submission_id) REFERENCES submissions(id)
        );
        """)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(questions)").fetchall()]
        if 'marks' not in cols:
            conn.execute("ALTER TABLE questions ADD COLUMN marks INTEGER DEFAULT 1")
            conn.commit()
        
        # migrate: add image_path if missing (for existing DBs)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(questions)").fetchall()]
        if 'image_path' not in cols:
            conn.execute("ALTER TABLE questions ADD COLUMN image_path TEXT DEFAULT NULL")
            conn.commit()

        teacher = conn.execute("SELECT id FROM users WHERE role='teacher'").fetchone()
        if not teacher:
            conn.execute(
                "INSERT INTO users (username,password,role,full_name) VALUES (?,?,?,?)",
                ("teacher", hash_pw("teacher123"), "teacher", "الأستاذ")
            )
            conn.commit()

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def gen_password(n=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def save_image(file_obj, prefix='img'):
    """Save uploaded image, return relative path or None."""
    if not file_obj or file_obj.filename == '':
        return None
    if not allowed_file(file_obj.filename):
        return None
    ext      = file_obj.filename.rsplit('.', 1)[1].lower()
    fname    = f"{prefix}_{random.randint(100000,999999)}.{ext}"
    file_obj.save(os.path.join(UPLOAD_DIR, fname))
    return f"uploads/{fname}"   # relative to static/

# ─────────────────────────────────────────────
# AUTH DECORATORS
# ─────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*a, **kw)
    return w

def teacher_required(f):
    @wraps(f)
    def w(*a, **kw):
        if session.get('role') != 'teacher':
            return redirect(url_for('login'))
        return f(*a, **kw)
    return w

def student_required(f):
    @wraps(f)
    def w(*a, **kw):
        if session.get('role') != 'student':
            return redirect(url_for('login'))
        return f(*a, **kw)
    return w

# ─────────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────────
@app.route('/', methods=['GET','POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','').strip()
        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE username=? AND password=?",
                (u, hash_pw(p))
            ).fetchone()
        if user:
            session.update(user_id=user['id'], username=user['username'],
                           role=user['role'], full_name=user['full_name'])
            return redirect(url_for('dashboard'))
        error = "اسم المستخدم أو كلمة المرور غير صحيحة"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return redirect(url_for('teacher_dashboard' if session['role'] == 'teacher' else 'student_dashboard'))

# ─────────────────────────────────────────────
# TEACHER ROUTES
# ─────────────────────────────────────────────
@app.route('/teacher')
@teacher_required
def teacher_dashboard():
    with get_db() as db:
        students = db.execute("SELECT * FROM users WHERE role='student' ORDER BY id DESC").fetchall()
        exams    = db.execute("SELECT * FROM exams ORDER BY created_at DESC").fetchall()
    return render_template('teacher_dashboard.html', students=students, exams=exams)

# ── Students ──
@app.route('/teacher/students/create', methods=['POST'])
@teacher_required
def create_student():
    full_name = request.form.get('full_name','').strip()
    username  = request.form.get('username','').strip()
    password  = request.form.get('password','').strip() or gen_password()
    if not full_name or not username:
        flash('الاسم واسم المستخدم مطلوبان', 'error')
        return redirect(url_for('teacher_dashboard'))
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO users (username,password,role,full_name) VALUES (?,?,?,?)",
                (username, hash_pw(password), 'student', full_name)
            )
            db.commit()
        flash(f'تم إنشاء الحساب | المستخدم: {username} | كلمة المرور: {password}', 'success')
    except sqlite3.IntegrityError:
        flash('اسم المستخدم موجود مسبقاً', 'error')
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/students/delete/<int:sid>', methods=['POST'])
@teacher_required
def delete_student(sid):
    with get_db() as db:
        db.execute("DELETE FROM users WHERE id=? AND role='student'", (sid,))
        db.commit()
    flash('تم حذف الطالب', 'success')
    return redirect(url_for('teacher_dashboard'))

# ── Exams ──
def _parse_questions(form, files, eid, db):
    """Insert questions (with optional images) for a given exam id."""
    i = 1
    while f'q{i}_text' in form:
        text = form.get(f'q{i}_text','').strip()
        a    = form.get(f'q{i}_a','').strip()
        b    = form.get(f'q{i}_b','').strip()
        c    = form.get(f'q{i}_c','').strip()
        d    = form.get(f'q{i}_d','').strip()
        ans  = form.get(f'q{i}_answer','').strip()
        img  = save_image(files.get(f'q{i}_image'), prefix=f'q{eid}_{i}')
        img   = save_image(files.get(f'q{i}_image'), prefix=f'q{eid}_{i}')
        marks = int(form.get(f'q{i}_marks', 1) or 1)
        if text and a and b and c and d and ans in ('a','b','c','d'):
            db.execute(
                "INSERT INTO questions "
                "(exam_id,text,option_a,option_b,option_c,option_d,answer,image_path,marks) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (eid, text, a, b, c, d, ans, img, marks)
            )
        i += 1

@app.route('/teacher/exams/create', methods=['GET','POST'])
@teacher_required
def create_exam():
    if request.method == 'POST':
        title = request.form.get('title','').strip()
        desc  = request.form.get('description','').strip()
        if not title:
            flash('عنوان الامتحان مطلوب', 'error')
            return redirect(url_for('create_exam'))
        with get_db() as db:
            cur = db.execute("INSERT INTO exams (title,description) VALUES (?,?)", (title, desc))
            eid = cur.lastrowid
            _parse_questions(request.form, request.files, eid, db)
            db.commit()
        flash('تم إنشاء الامتحان بنجاح', 'success')
        return redirect(url_for('teacher_dashboard'))
    return render_template('create_exam.html')

@app.route('/teacher/exams/<int:eid>/edit', methods=['GET','POST'])
@teacher_required
def edit_exam(eid):
    with get_db() as db:
        exam      = db.execute("SELECT * FROM exams WHERE id=?", (eid,)).fetchone()
        questions = db.execute("SELECT * FROM questions WHERE exam_id=? ORDER BY id", (eid,)).fetchall()
        if not exam:
            return redirect(url_for('teacher_dashboard'))
        if request.method == 'POST':
            title = request.form.get('title','').strip()
            desc  = request.form.get('description','').strip()
            db.execute("UPDATE exams SET title=?,description=? WHERE id=?", (title, desc, eid))
            # delete old images from disk
            for q in questions:
                if q['image_path']:
                    old = os.path.join(app.static_folder, q['image_path'])
                    if os.path.exists(old):
                        os.remove(old)
            db.execute("DELETE FROM questions WHERE exam_id=?", (eid,))
            _parse_questions(request.form, request.files, eid, db)
            db.commit()
            flash('تم تحديث الامتحان', 'success')
            return redirect(url_for('teacher_dashboard'))
    return render_template('edit_exam.html', exam=exam, questions=questions)

@app.route('/teacher/exams/<int:eid>/toggle', methods=['POST'])
@teacher_required
def toggle_exam(eid):
    with get_db() as db:
        e = db.execute("SELECT is_active FROM exams WHERE id=?", (eid,)).fetchone()
        if e:
            db.execute("UPDATE exams SET is_active=? WHERE id=?", (0 if e['is_active'] else 1, eid))
            db.commit()
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/exams/<int:eid>/delete', methods=['POST'])
@teacher_required
def delete_exam(eid):
    with get_db() as db:
        qs = db.execute("SELECT image_path FROM questions WHERE exam_id=?", (eid,)).fetchall()
        for q in qs:
            if q['image_path']:
                p = os.path.join(app.static_folder, q['image_path'])
                if os.path.exists(p):
                    os.remove(p)
        db.execute("DELETE FROM exams WHERE id=?", (eid,))
        db.commit()
    flash('تم حذف الامتحان', 'success')
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/exams/<int:eid>/results')
@teacher_required
def exam_results(eid):
    with get_db() as db:
        exam    = db.execute("SELECT * FROM exams WHERE id=?", (eid,)).fetchone()
        results = db.execute("""
            SELECT u.full_name, u.username, s.score, s.total, s.submitted_at
            FROM submissions s JOIN users u ON s.student_id=u.id
            WHERE s.exam_id=? ORDER BY s.submitted_at DESC
        """, (eid,)).fetchall()
    return render_template('exam_results.html', exam=exam, results=results)

# ─────────────────────────────────────────────
# STUDENT ROUTES
# ─────────────────────────────────────────────
@app.route('/student')
@student_required
def student_dashboard():
    sid = session['user_id']
    with get_db() as db:
        exams  = db.execute("SELECT * FROM exams WHERE is_active=1 ORDER BY created_at DESC").fetchall()
        done   = {r['exam_id'] for r in db.execute(
            "SELECT exam_id FROM submissions WHERE student_id=?", (sid,)).fetchall()}
        scores = {r['exam_id']: r for r in db.execute(
            "SELECT * FROM submissions WHERE student_id=?", (sid,)).fetchall()}
    return render_template('student_dashboard.html', exams=exams, done=done, scores=scores)

@app.route('/student/exam/<int:eid>', methods=['GET','POST'])
@student_required
def take_exam(eid):
    sid = session['user_id']
    with get_db() as db:
        exam = db.execute("SELECT * FROM exams WHERE id=? AND is_active=1", (eid,)).fetchone()
        if not exam:
            return redirect(url_for('student_dashboard'))
        sub = db.execute(
            "SELECT * FROM submissions WHERE student_id=? AND exam_id=?", (sid, eid)
        ).fetchone()
        if sub:
            return redirect(url_for('exam_result', eid=eid))
        questions = db.execute("SELECT * FROM questions WHERE exam_id=? ORDER BY id", (eid,)).fetchall()
        if request.method == 'POST':
            score   = 0
            sub_cur = db.execute(
                "INSERT INTO submissions (student_id,exam_id,score,total) VALUES (?,?,0,?)",
                (sid, eid, sum(q['marks'] for q in questions))
                
            )
            sub_id = sub_cur.lastrowid
            for q in questions:
                chosen = request.form.get(f'q{q["id"]}', '')
                if chosen == q['answer']:
                    score += q['marks']
                
                
                db.execute(
                    "INSERT INTO answers (submission_id,question_id,chosen) VALUES (?,?,?)",
                    (sub_id, q['id'], chosen)
                )
            db.execute("UPDATE submissions SET score=? WHERE id=?", (score, sub_id))
            db.commit()
            return redirect(url_for('exam_result', eid=eid))
    return render_template('take_exam.html', exam=exam, questions=questions)

@app.route('/student/exam/<int:eid>/result')
@student_required
def exam_result(eid):
    sid = session['user_id']
    with get_db() as db:
        exam = db.execute("SELECT * FROM exams WHERE id=?", (eid,)).fetchone()
        sub  = db.execute(
            "SELECT * FROM submissions WHERE student_id=? AND exam_id=?", (sid, eid)
        ).fetchone()
        if not sub:
            return redirect(url_for('student_dashboard'))
        answers = db.execute("""
            SELECT a.chosen,
                   q.id AS qid, q.text, q.answer,
                   q.option_a, q.option_b, q.option_c, q.option_d,
                   q.image_path
            FROM answers a
            JOIN questions q ON a.question_id = q.id
            WHERE a.submission_id = ?
            ORDER BY q.id
        """, (sub['id'],)).fetchall()
    return render_template('exam_result.html', exam=exam, sub=sub, answers=answers)

# ─────────────────────────────────────────────
if __name__ == '__main__':
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db()
    app.run(debug=True)
