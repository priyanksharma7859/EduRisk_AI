from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import joblib
import pandas as pd
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = "edurisk-secret-key-change-this"

DB_NAME = "professors.db"


# =====================================================
# DATABASE
# =====================================================

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
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
            FOREIGN KEY (professor_id)
            REFERENCES professors(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prediction_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            professor_id INTEGER NOT NULL,
            risk TEXT NOT NULL,
            attendance REAL NOT NULL,
            marks REAL NOT NULL,
            assignments REAL NOT NULL,
            predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id),
            FOREIGN KEY (professor_id) REFERENCES professors(id)
        )
    """)
    conn.commit()
    conn.close()


# =====================================================
# LOAD AI MODEL
# =====================================================

try:
    model = joblib.load("student_risk_model.pkl")
    print("AI model loaded successfully")
except Exception as e:
    print("ML model loading error:", e)
    model = None


# =====================================================
# LOGIN REQUIRED
# =====================================================

def login_required():
    return "professor_id" in session


# =====================================================
# HOME
# =====================================================

@app.route("/")
def home():

    if not login_required():
        return redirect(url_for("login"))

    return render_template("index.html")


# =====================================================
# REGISTER
# =====================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        college = request.form.get("college", "").strip()
        email = request.form.get("email", "").strip().lower()
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not college or not email or not mobile or not password:
            return "All fields are required!", 400

        if password != confirm_password:
            return "Passwords do not match!", 400

        hashed_password = generate_password_hash(password)

        try:

            conn = get_db()
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
            return "Email already registered!", 409

    return render_template("register.html")


# =====================================================
# LOGIN
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM professors WHERE email = ?",
            (email,)
        )

        professor = cursor.fetchone()
        conn.close()

        if professor and check_password_hash(
            professor["password"],
            password
        ):

            session.clear()

            session["professor_id"] = professor["id"]
            session["professor_name"] = professor["name"]

            return redirect(url_for("home"))

        return "Invalid email or password!", 401

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

    conn = get_db()
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

    data = request.get_json(silent=True) or {}

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

        department = str(data["department"]).strip()
        notes = str(data.get("notes", "")).strip()

    except (ValueError, TypeError):

        return jsonify({
            "error": "Invalid student data"
        }), 400

    if not name or not roll:

        return jsonify({
            "error": "Name and roll number are required"
        }), 400

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

    professor_id = session["professor_id"]

    conn = get_db()
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

    conn.commit()

    student_id = cursor.lastrowid

    conn.close()

    return jsonify({
        "success": True,
        "message": "Student added successfully",
        "id": student_id
    })


# =====================================================
# EDIT STUDENT
# =====================================================

@app.route("/students/<int:student_id>", methods=["PUT"])
def edit_student(student_id):

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401

    data = request.get_json(silent=True) or {}

    try:

        name = str(data["name"]).strip()
        roll = str(data["roll"]).strip()

        attendance = float(data["attendance"])
        marks = float(data["marks"])
        assignments = float(data["assignments"])

        department = str(data["department"]).strip()
        notes = str(data.get("notes", "")).strip()

    except (KeyError, ValueError, TypeError):

        return jsonify({
            "error": "Invalid student data"
        }), 400

    if not name or not roll:

        return jsonify({
            "error": "Name and roll number are required"
        }), 400

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

    professor_id = session["professor_id"]

    conn = get_db()
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
        WHERE
            id = ?
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

    conn.commit()

    updated = cursor.rowcount

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
# DELETE STUDENT
# =====================================================

@app.route("/students/<int:student_id>", methods=["DELETE"])
def delete_student(student_id):

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401

    professor_id = session["professor_id"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM students
        WHERE
            id = ?
            AND professor_id = ?
    """, (
        student_id,
        professor_id
    ))

    conn.commit()

    deleted = cursor.rowcount

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
# AI PREDICTION + PERSONALIZED RECOMMENDATIONS
# =====================================================

@app.route("/predict", methods=["POST"])
def predict():

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401

    if model is None:

        return jsonify({
            "error": "AI model is not available. Check student_risk_model.pkl"
        }), 500

    data = request.get_json(silent=True) or {}

    student_id = data.get("student_id")

    if student_id is None:

        return jsonify({
            "error": "Student ID is required"
        }), 400

    try:

        student_id = int(student_id)

    except (ValueError, TypeError):

        return jsonify({
            "error": "Invalid student ID"
        }), 400

    professor_id = session["professor_id"]

    conn = get_db()
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
        WHERE
            id = ?
            AND professor_id = ?
    """, (
        student_id,
        professor_id
    ))

    student = cursor.fetchone()

    conn.close()

    if student is None:

        return jsonify({
            "error": "Student not found or access denied"
        }), 404

    attendance = float(student["attendance"])
    marks = float(student["marks"])
    assignments = float(student["assignments"])


    # =================================================
    # MODEL INPUT
    # =================================================

    input_data = pd.DataFrame([{
        "attendance": attendance,
        "score": marks,
        "lms": assignments
    }])


    # =================================================
    # AI MODEL PREDICTION
    # =================================================

    try:

        prediction = model.predict(input_data)

        risk = str(prediction[0]).strip()

        if risk.lower() == "high":

            risk = "High"

        elif risk.lower() == "medium":

            risk = "Medium"

        elif risk.lower() == "low":

            risk = "Low"

        else:

            risk = risk.title()

    except Exception as e:

        print(
            "Prediction error:",
            repr(e)
        )

        return jsonify({
            "error": "AI prediction failed: " + str(e)
        }), 500

    # =====================================================
    # SAVE AI PREDICTION HISTORY
    # =====================================================

    history_conn = get_db()
    history_cursor = history_conn.cursor()

    history_cursor.execute("""
        INSERT INTO prediction_history
        (
            student_id,
            professor_id,
            risk,
            attendance,
            marks,
            assignments
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        student["id"],
        professor_id,
        risk,
        attendance,
        marks,
        assignments
    ))

    history_conn.commit()
    history_conn.close()

    # =================================================
    # PERSONALIZED RECOMMENDATIONS
    # =================================================

    recommendations = []


    # Attendance recommendation
    if attendance < 60:

        recommendations.append(
            "Attendance is very low. Attend classes regularly and improve attendance immediately."
        )

    elif attendance < 75:

        recommendations.append(
            "Attendance is below the preferred level. Try to attend classes more consistently."
        )

    else:

        recommendations.append(
            "Attendance is good. Continue maintaining regular class attendance."
        )


    # Marks recommendation
    if marks < 50:

        recommendations.append(
            "Marks are low. Follow a daily study schedule and focus on weak subjects."
        )

    elif marks < 70:

        recommendations.append(
            "Marks are moderate. Increase revision and practice previous examination questions."
        )

    else:

        recommendations.append(
            "Academic marks are good. Continue regular revision and practice."
        )


    # Assignment recommendation
    if assignments < 50:

        recommendations.append(
            "Assignment completion is low. Complete pending assignments as early as possible."
        )

    elif assignments < 75:

        recommendations.append(
            "Assignment completion can be improved. Submit assignments on time."
        )

    else:

        recommendations.append(
            "Assignment completion is good. Continue submitting work on time."
        )


    # =================================================
    # RISK-BASED AI ANALYSIS
    # =================================================

    if risk == "High":

        ai_analysis = f"""
High Academic Risk

This student requires immediate academic attention.

Attendance: {attendance}%
Test Score: {marks}%
Assignment/LMS: {assignments}%

Personalized AI Recommendations:

• {recommendations[0]}
• {recommendations[1]}
• {recommendations[2]}

Immediate Action:

Faculty should monitor this student regularly and provide early academic intervention.
"""

    elif risk == "Medium":

        ai_analysis = f"""
Medium Academic Risk

This student needs regular monitoring and academic improvement.

Attendance: {attendance}%
Test Score: {marks}%
Assignment/LMS: {assignments}%

Personalized AI Recommendations:

• {recommendations[0]}
• {recommendations[1]}
• {recommendations[2]}

Recommended Action:

Monitor academic progress regularly and provide support where required.
"""

    else:

        ai_analysis = f"""
Low Academic Risk

This student is currently performing well.

Attendance: {attendance}%
Test Score: {marks}%
Assignment/LMS: {assignments}%

Personalized AI Recommendations:

• {recommendations[0]}
• {recommendations[1]}
• {recommendations[2]}

Recommended Action:

Maintain the current academic performance and continue regular study habits.
"""


    # =================================================
    # RESPONSE
    # =================================================

    return jsonify({

        "success": True,

        "student_id": student["id"],

        "student_name": student["name"],

        "roll": student["roll"],

        "attendance": attendance,

        "marks": marks,

        "assignments": assignments,

        "risk": risk,

        "ai_analysis": ai_analysis,

        "recommendations": recommendations

    })

# =====================================================
# AI PREDICTION HISTORY
# =====================================================

@app.route("/prediction-history/<int:student_id>", methods=["GET"])
def prediction_history(student_id):

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401

    professor_id = session["professor_id"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            student_id,
            risk,
            attendance,
            marks,
            assignments,
            predicted_at
        FROM prediction_history
        WHERE
            student_id = ?
            AND professor_id = ?
        ORDER BY id DESC
    """, (
        student_id,
        professor_id
    ))

    history = [
        dict(row)
        for row in cursor.fetchall()
    ]

    conn.close()

    return jsonify(history)

# =====================================================
# START SERVER
# =====================================================

if __name__ == "__main__":

    init_db()

    print("")
    print("======================================")
    print(" EduRisk AI Server Started")
    print(" Local:   http://127.0.0.1:5000")
    print(" Network: http://0.0.0.0:5000")
    print("======================================")
    print("")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )