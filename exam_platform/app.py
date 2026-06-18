from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from functools import wraps
import sqlite3, hashlib, os, random, string

app = Flask(__name__)
app.secret_key = os.urandom(24)
DB_PATH = "exam_platform.db"

# ── Database ──────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('teacher','student')),
        full_name TEXT,
        created_at TEXT DEFAULT (datetime('now')))""")
    c.execute("""CREATE TABLE IF NOT EXISTS exams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')))""")
    c.execute("""CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER NOT NULL,
        question_text TEXT NOT NULL,
        option_a TEXT NOT NULL, option_b TEXT NOT NULL,
        option_c TEXT NOT NULL, option_d TEXT NOT NULL,
        correct_answer TEXT NOT NULL CHECK(correct_answer IN ('a','b','c','d')),
        order_num INTEGER DEFAULT 0,
        FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL, exam_id INTEGER NOT NULL,
        score INTEGER NOT NULL, total INTEGER NOT NULL,
        submitted_at TEXT DEFAULT (datetime('now')),
        UNIQUE(student_id, exam_id),
        FOREIGN KEY (student_id) REFERENCES users(id),
        FOREIGN KEY (exam_id) REFERENCES exams(id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id INTEGER NOT NULL, question_id INTEGER NOT NULL,
        selected_answer TEXT NOT NULL,
        FOREIGN KEY (submission_id) REFERENCES submissions(id))""")
    # حساب الأستاذ الافتراضي
    c.execute("INSERT OR IGNORE INTO users (username,password_hash,role,full_name) VALUES (?,?,?,?)",
              ("teacher", hash_password("teacher123"), "teacher", "الأستاذ"))
    conn.commit()
    conn.close()

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

# ── Auth Decorators ───────────────────────────
def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if "user_id" not in session: return redirect(url_for("login"))
        return f(*a, **kw)
    return d

def teacher_required(f):
    @wraps(f)
    def d(*a, **kw):
        if "user_id" not in session: return redirect(url_for("login"))
        if session.get("role") != "teacher": return redirect(url_for("student_dashboard"))
        return f(*a, **kw)
    return d

def student_required(f):
    @wraps(f)
    def d(*a, **kw):
        if "user_id" not in session: return redirect(url_for("login"))
        if session.get("role") != "student": return redirect(url_for("teacher_dashboard"))
        return f(*a, **kw)
    return d

# ── Auth Routes ───────────────────────────────
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("teacher_dashboard" if session["role"]=="teacher" else "student_dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if "user_id" in session: return redirect(url_for("index"))
    if request.method == "POST":
        u, p = request.form.get("username","").strip(), request.form.get("password","").strip()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=? AND password_hash=?",
                            (u, hash_password(p))).fetchone()
        conn.close()
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            return redirect(url_for("teacher_dashboard" if user["role"]=="teacher" else "student_dashboard"))
        flash("اسم المستخدم أو كلمة المرور غير صحيحة", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ── Teacher Routes ────────────────────────────
@app.route("/teacher")
@teacher_required
def teacher_dashboard():
    conn = get_db()
    exams = conn.execute("""
        SELECT e.*, COUNT(DISTINCT q.id) as question_count,
               COUNT(DISTINCT s.id) as submission_count
        FROM exams e
        LEFT JOIN questions q ON q.exam_id=e.id
        LEFT JOIN submissions s ON s.exam_id=e.id
        GROUP BY e.id ORDER BY e.created_at DESC""").fetchall()
    students = conn.execute("SELECT * FROM users WHERE role='student' ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("teacher_dashboard.html", exams=exams, students=students)

@app.route("/teacher/students/create", methods=["POST"])
@teacher_required
def create_student():
    full_name = request.form.get("full_name","").strip()
    username  = request.form.get("username","").strip()
    password  = request.form.get("password","").strip()
    if not all([full_name, username, password]):
        flash("يرجى تعبئة جميع الحقول", "error")
        return redirect(url_for("teacher_dashboard"))
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username,password_hash,role,full_name) VALUES (?,?,?,?)",
                     (username, hash_password(password), "student", full_name))
        conn.commit()
        flash(f"✅ تم إنشاء حساب '{full_name}' بنجاح", "success")
    except sqlite3.IntegrityError:
        flash("اسم المستخدم مستخدم مسبقاً", "error")
    finally:
        conn.close()
    return redirect(url_for("teacher_dashboard"))

@app.route("/teacher/students/delete/<int:sid>", methods=["POST"])
@teacher_required
def delete_student(sid):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=? AND role='student'", (sid,))
    conn.commit(); conn.close()
    flash("تم حذف الطالب", "success")
    return redirect(url_for("teacher_dashboard"))

@app.route("/teacher/exams/create", methods=["GET","POST"])
@teacher_required
def create_exam():
    if request.method == "POST":
        title = request.form.get("title","").strip()
        desc  = request.form.get("description","").strip()
        active = 1 if request.form.get("is_active") else 0
        if not title:
            flash("أدخل عنوان الامتحان", "error")
            return render_template("exam_form.html", exam=None)
        conn = get_db()
        cur = conn.execute("INSERT INTO exams (title,description,is_active) VALUES (?,?,?)",
                           (title, desc, active))
        eid = cur.lastrowid
        conn.commit(); conn.close()
        flash("تم إنشاء الامتحان، أضف الأسئلة الآن", "success")
        return redirect(url_for("edit_exam", exam_id=eid))
    return render_template("exam_form.html", exam=None)

@app.route("/teacher/exams/<int:exam_id>/edit", methods=["GET","POST"])
@teacher_required
def edit_exam(exam_id):
    conn = get_db()
    if request.method == "POST":
        title = request.form.get("title","").strip()
        desc  = request.form.get("description","").strip()
        active = 1 if request.form.get("is_active") else 0
        conn.execute("UPDATE exams SET title=?,description=?,is_active=? WHERE id=?",
                     (title, desc, active, exam_id))
        conn.commit()
        flash("تم التحديث", "success")
    exam = conn.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()
    questions = conn.execute("SELECT * FROM questions WHERE exam_id=? ORDER BY order_num", (exam_id,)).fetchall()
    conn.close()
    if not exam:
        flash("الامتحان غير موجود", "error")
        return redirect(url_for("teacher_dashboard"))
    return render_template("exam_form.html", exam=exam, questions=questions)

@app.route("/teacher/exams/<int:exam_id>/delete", methods=["POST"])
@teacher_required
def delete_exam(exam_id):
    conn = get_db()
    conn.execute("DELETE FROM exams WHERE id=?", (exam_id,))
    conn.commit(); conn.close()
    flash("تم حذف الامتحان", "success")
    return redirect(url_for("teacher_dashboard"))

@app.route("/teacher/exams/<int:exam_id>/questions/add", methods=["POST"])
@teacher_required
def add_question(exam_id):
    data = request.get_json()
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM questions WHERE exam_id=?", (exam_id,)).fetchone()[0]
    conn.execute("""INSERT INTO questions
        (exam_id,question_text,option_a,option_b,option_c,option_d,correct_answer,order_num)
        VALUES (?,?,?,?,?,?,?,?)""",
        (exam_id, data["question_text"], data["option_a"], data["option_b"],
         data["option_c"], data["option_d"], data["correct_answer"], count+1))
    conn.commit(); conn.close()
    return jsonify({"success": True})

@app.route("/teacher/questions/<int:qid>/delete", methods=["POST"])
@teacher_required
def delete_question(qid):
    conn = get_db()
    conn.execute("DELETE FROM questions WHERE id=?", (qid,))
    conn.commit(); conn.close()
    return jsonify({"success": True})

@app.route("/teacher/exams/<int:exam_id>/results")
@teacher_required
def exam_results(exam_id):
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()
    results = conn.execute("""
        SELECT u.full_name, u.username, s.score, s.total, s.submitted_at,
               ROUND(s.score*100.0/s.total,1) as percentage
        FROM submissions s JOIN users u ON u.id=s.student_id
        WHERE s.exam_id=? ORDER BY s.submitted_at DESC""", (exam_id,)).fetchall()
    conn.close()
    return render_template("exam_results.html", exam=exam, results=results)

# ── Student Routes ────────────────────────────
@app.route("/student")
@student_required
def student_dashboard():
    conn = get_db()
    exams = conn.execute("""
        SELECT e.*, COUNT(q.id) as question_count,
               s.score, s.total, s.submitted_at
        FROM exams e
        LEFT JOIN questions q ON q.exam_id=e.id
        LEFT JOIN submissions s ON s.exam_id=e.id AND s.student_id=?
        WHERE e.is_active=1
        GROUP BY e.id ORDER BY e.created_at DESC""", (session["user_id"],)).fetchall()
    conn.close()
    return render_template("student_dashboard.html", exams=exams)

@app.route("/student/exam/<int:exam_id>")
@student_required
def take_exam(exam_id):
    conn = get_db()
    existing = conn.execute("SELECT * FROM submissions WHERE student_id=? AND exam_id=?",
                            (session["user_id"], exam_id)).fetchone()
    if existing:
        conn.close(); flash("لقد قدمت هذا الامتحان مسبقاً", "info")
        return redirect(url_for("student_dashboard"))
    exam = conn.execute("SELECT * FROM exams WHERE id=? AND is_active=1", (exam_id,)).fetchone()
    if not exam:
        conn.close(); flash("الامتحان غير متاح", "error")
        return redirect(url_for("student_dashboard"))
    questions = conn.execute("SELECT * FROM questions WHERE exam_id=? ORDER BY order_num", (exam_id,)).fetchall()
    conn.close()
    return render_template("take_exam.html", exam=exam, questions=questions)

@app.route("/student/exam/<int:exam_id>/submit", methods=["POST"])
@student_required
def submit_exam(exam_id):
    conn = get_db()
    if conn.execute("SELECT * FROM submissions WHERE student_id=? AND exam_id=?",
                    (session["user_id"], exam_id)).fetchone():
        conn.close(); return jsonify({"error": "submitted_already"}), 400
    questions = conn.execute("SELECT * FROM questions WHERE exam_id=?", (exam_id,)).fetchall()
    answers = request.get_json()
    score = 0
    cur = conn.execute("INSERT INTO submissions (student_id,exam_id,score,total) VALUES (?,?,?,?)",
                       (session["user_id"], exam_id, 0, len(questions)))
    sid = cur.lastrowid
    for q in questions:
        selected = answers.get(str(q["id"]), "")
        if selected == q["correct_answer"]: score += 1
        conn.execute("INSERT INTO answers (submission_id,question_id,selected_answer) VALUES (?,?,?)",
                     (sid, q["id"], selected))
    conn.execute("UPDATE submissions SET score=? WHERE id=?", (score, sid))
    conn.commit(); conn.close()
    total = len(questions)
    return jsonify({"score": score, "total": total,
                    "percentage": round(score*100/total, 1) if total else 0})

@app.route("/api/generate-credentials")
@teacher_required
def generate_credentials():
    u = "std_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    p = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    return jsonify({"username": u, "password": p})

if __name__ == "__main__":
    init_db()
    print("\n✅ المنصة جاهزة!")
    print("🔑 دخول الأستاذ: username=teacher | password=teacher123")
    print("🌐 http://127.0.0.1:5000\n")
    app.run(debug=True)