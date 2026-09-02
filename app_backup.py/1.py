from flask import Flask, request, jsonify, send_from_directory, render_template, redirect, url_for, session
import joblib
import pandas as pd
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# =====================================================
# SECRET KEY
# =====================================================

app.secret_key = "edurisk-secret-key"


# =====================================================
# DATABASE INITIALIZATION
# =====================================================

def init_db():

    conn = sqlite3.connect("professors.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS professors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            college TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            mobile TEXT NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            professor_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            roll TEXT NOT NULL,
            attendance REAL NOT NULL,
            marks REAL NOT NULL,
            assignments REAL NOT NULL,
            department TEXT,
            notes TEXT,
            FOREIGN KEY (professor_id) REFERENCES professors(id)
        )
    """)

    conn.commit()
    conn.close()


# =====================================================
# LOAD ML MODEL
# =====================================================

try:
    model = joblib.load("student_risk_model.pkl")
    print("ML model loaded successfully")
except Exception as e:
    model = None
    print("ML model loading error:", e)


# =====================================================
# LOGIN CHECK
# =====================================================

def login_required():

    return "professor_id" in session


# =====================================================
# HOME / DASHBOARD
# =====================================================

@app.route("/")
def home():

    if not login_required():
        return redirect(url_for("login"))

    return send_from_directory(".", "index.html")


# =====================================================
# REGISTER
# =====================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        college = request.form.get("college", "").strip()
        email = request.form.get("email", "").strip()
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not college or not email or not mobile or not password:
            return "Please fill all required fields."

        if password != confirm_password:
            return "Passwords do not match!"

        hashed_password = generate_password_hash(password)

        try:

            conn = sqlite3.connect("professors.db")
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO professors
                (name, college, email, mobile, password)
                VALUES (?, ?, ?, ?, ?)
            """, (
                name,
                college,
                email,
                mobile,
                hashed_password
            ))

            conn.commit()
            conn.close()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:

            return "Email already registered!"

    return render_template("register.html")


# =====================================================
# LOGIN
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        conn = sqlite3.connect("professors.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM professors
            WHERE email = ?
        """, (email,))

        professor = cursor.fetchone()

        conn.close()

        if professor and check_password_hash(
            professor[5],
            password
        ):

            session["professor_id"] = professor[0]
            session["professor_name"] = professor[1]

            return redirect(url_for("home"))

        return "Invalid email or password!"

    return render_template("login.html")


# =====================================================
# LOGOUT
# =====================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# =====================================================
# GET STUDENTS
# =====================================================

@app.route("/students", methods=["GET"])
def get_students():

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401

    professor_id = session["professor_id"]

    conn = sqlite3.connect("professors.db")
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            roll,
            attendance,
            marks,
            assignments,
            department,
            notes
        FROM students
        WHERE professor_id = ?
        ORDER BY id DESC
    """, (professor_id,))

    students = [
        dict(row)
        for row in cursor.fetchall()
    ]

    conn.close()

    return jsonify(students)


# =====================================================
# ADD STUDENT
# =====================================================

@app.route("/students", methods=["POST"])
def add_student():

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401

    data = request.get_json()

    if not data:

        return jsonify({
            "error": "No data received"
        }), 400

    required_fields = [
        "name",
        "roll",
        "attendance",
        "marks",
        "assignments",
        "department"
    ]

    for field in required_fields:

        if field not in data:

            return jsonify({
                "error": f"Missing field: {field}"
            }), 400

    try:

        name = str(data["name"]).strip()
        roll = str(data["roll"]).strip()

        attendance = float(data["attendance"])
        marks = float(data["marks"])
        assignments = float(data["assignments"])

        department = str(
            data["department"]
        ).strip()

        notes = str(
            data.get("notes", "")
        ).strip()

        if not 0 <= attendance <= 100:
            return jsonify({
                "error": "Attendance must be between 0 and 100"
            }), 400

        if not 0 <= marks <= 100:
            return jsonify({
                "error": "Marks must be between 0 and 100"
            }), 400

        if not 0 <= assignments <= 100:
            return jsonify({
                "error": "Assignments must be between 0 and 100"
            }), 400

    except ValueError:

        return jsonify({
            "error": "Invalid numeric value"
        }), 400

    professor_id = session["professor_id"]

    conn = sqlite3.connect("professors.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO students
        (
            professor_id,
            name,
            roll,
            attendance,
            marks,
            assignments,
            department,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        professor_id,
        name,
        roll,
        attendance,
        marks,
        assignments,
        department,
        notes
    ))

    student_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Student added successfully",
        "id": student_id
    })


# =====================================================
# DELETE STUDENT
# =====================================================

@app.route("/students/<int:student_id>", methods=["DELETE"])
def delete_student(student_id):

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401

    professor_id = session["professor_id"]

    conn = sqlite3.connect("professors.db")
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM students
        WHERE id = ?
        AND professor_id = ?
    """, (
        student_id,
        professor_id
    ))

    deleted = cursor.rowcount

    conn.commit()
    conn.close()

    if deleted == 0:

        return jsonify({
            "error": "Student not found"
        }), 404

    return jsonify({
        "success": True,
        "message": "Student deleted successfully"
    })


# =====================================================
# UPDATE STUDENT
# =====================================================

@app.route("/students/<int:student_id>", methods=["PUT"])
def update_student(student_id):

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401

    data = request.get_json()

    if not data:

        return jsonify({
            "error": "No data received"
        }), 400

    try:

        name = str(data["name"]).strip()
        roll = str(data["roll"]).strip()

        attendance = float(data["attendance"])
        marks = float(data["marks"])
        assignments = float(data["assignments"])

        department = str(
            data["department"]
        ).strip()

        notes = str(
            data.get("notes", "")
        ).strip()

    except (KeyError, ValueError):

        return jsonify({
            "error": "Invalid student data"
        }), 400

    professor_id = session["professor_id"]

    conn = sqlite3.connect("professors.db")
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE students
        SET
            name = ?,
            roll = ?,
            attendance = ?,
            marks = ?,
            assignments = ?,
            department = ?,
            notes = ?
        WHERE id = ?
        AND professor_id = ?
    """, (
        name,
        roll,
        attendance,
        marks,
        assignments,
        department,
        notes,
        student_id,
        professor_id
    ))

    updated = cursor.rowcount

    conn.commit()
    conn.close()

    if updated == 0:

        return jsonify({
            "error": "Student not found"
        }), 404

    return jsonify({
        "success": True,
        "message": "Student updated successfully"
    })


# =====================================================
# AI / ML PREDICTION
# =====================================================

@app.route("/predict", methods=["POST"])
def predict():

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401

    data = request.get_json()

    if not data:

        return jsonify({
            "error": "No prediction data received"
        }), 400

    try:

        attendance = float(
            data["attendance"]
        )

        score = float(
            data["score"]
        )

        lms = float(
            data["lms"]
        )

    except (KeyError, ValueError):

        return jsonify({
            "error": "Invalid prediction data"
        }), 400


    # =================================================
    # ML PREDICTION
    # =================================================

    try:

        if model is None:

            raise Exception(
                "ML model is not loaded"
            )

        input_data = pd.DataFrame([{

            "attendance": attendance,
            "score": score,
            "lms": lms

        }])

        prediction = model.predict(
            input_data
        )

        risk = str(
            prediction[0]
        )

    except Exception as e:

        print("ML prediction error:", e)

        # Backup risk calculation

        weighted_score = (
            attendance * 0.40
            +
            score * 0.40
            +
            lms * 0.20
        )

        if weighted_score < 55:

            risk = "High"

        elif weighted_score < 75:

            risk = "Medium"

        else:

            risk = "Low"


    # =================================================
    # AI ANALYSIS
    # =================================================

    if risk == "High":

        ai_analysis = f"""
High Academic Risk

This student is at high academic risk because attendance ({attendance}%),
test score ({score}%), and LMS engagement ({lms}%) require significant improvement.

Risk Factors:
1. Low attendance or academic performance.
2. Low LMS/assignment engagement.
3. Student may require immediate academic support.

Recommendations:
1. Attend classes regularly.
2. Improve test preparation.
3. Complete assignments on time.
4. Faculty should monitor the student regularly.
"""

    elif risk == "Medium":

        ai_analysis = f"""
Medium Academic Risk

This student has moderate academic performance. Attendance ({attendance}%),
test score ({score}%), and LMS engagement ({lms}%) should be improved.

Risk Factors:
1. Academic performance needs improvement.
2. Attendance should be more consistent.
3. LMS/assignment activity should improve.

Recommendations:
1. Follow a consistent study schedule.
2. Attend classes regularly.
3. Complete assignments on time.
4. Continue regular faculty monitoring.
"""

    else:

        ai_analysis = f"""
Low Academic Risk

This student is currently performing well academically.

Attendance: {attendance}%
Test Score: {score}%
LMS Engagement: {lms}%

Positive Factors:
1. Good academic performance.
2. Good attendance.
3. Regular LMS/assignment activity.

Recommendations:
1. Maintain current performance.
2. Continue regular study.
3. Continue timely assignment completion.
"""


    return jsonify({

        "success": True,

        "risk": risk,

        "ai_analysis": ai_analysis

    })


# =====================================================
# PROFESSOR PROFILE
# =====================================================

@app.route("/profile", methods=["GET"])
def profile():

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401

    professor_id = session["professor_id"]

    conn = sqlite3.connect("professors.db")
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            college,
            email,
            mobile
        FROM professors
        WHERE id = ?
    """, (professor_id,))

    professor = cursor.fetchone()

    conn.close()

    if not professor:

        return jsonify({
            "error": "Professor not found"
        }), 404

    return jsonify(dict(professor))


# =====================================================
# RUN APPLICATION
# =====================================================

if __name__ == "__main__":

    init_db()

    print("")
    print("====================================")
    print("     EduRisk AI Server Started")
    print("====================================")
    print("Local:   http://127.0.0.1:5000")
    print("Network: http://0.0.0.0:5000")
    print("====================================")
    print("")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )