from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import joblib
import pandas as pd
import psycopg2
import threading
import requests
import os
import smtplib
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from email.message import EmailMessage
import secrets
from datetime import datetime, timedelta

# =====================================================
# LOAD ENVIRONMENT VARIABLES
# =====================================================

load_dotenv()


# =====================================================
# EMAIL FUNCTION
# =====================================================

def send_inquiry_email(name, email, message):
    resend_api_key = os.environ.get("RESEND_API_KEY")

    if not resend_api_key:
        raise Exception("RESEND_API_KEY is not configured")

    msg = {
        "from": "EduRisk AI <onboarding@resend.dev>",
        "to": [os.environ.get("EMAIL_RECEIVER")],
        "subject": "New EduRisk AI Inquiry",
        "html": f"""
        <h2>New EduRisk AI Inquiry</h2>

        <p><strong>Name:</strong> {name}</p>
        <p><strong>Email:</strong> {email}</p>

        <p><strong>Inquiry Message:</strong></p>
        <p>{message}</p>

        <p><strong>Status:</strong> Pending</p>
        """
    }

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json"
        },
        json=msg,
        timeout=10
    )

    if response.status_code >= 400:
        raise Exception(
            f"Resend API Error {response.status_code}: {response.text}"
        )

    print("RESEND EMAIL SENT:", response.text)

def send_inquiry_email_background(name, email, message):
    try:
        send_inquiry_email(name, email, message)
        print("INQUIRY EMAIL SENT")
    except Exception as e:
        print("INQUIRY EMAIL ERROR:", repr(e))

# =====================================================
# FLASK APP
# =====================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "edurisk-secret-key-change-this"
)


# =====================================================
# DATABASE
# =====================================================

def get_db():

    return psycopg2.connect(
        os.environ.get("DATABASE_URL"),
        cursor_factory=RealDictCursor
    )


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
# PASSWORD RESET OTP
# =====================================================

def generate_reset_otp():
    return str(secrets.randbelow(900000) + 100000)

# =====================================================
# HOME
# =====================================================

@app.route("/")
def home():

    if not login_required():

        return redirect(url_for("login"))

    return render_template("index.html")


# =====================================================
# INQUIRY
# =====================================================

@app.route("/inquiry", methods=["POST"])
def submit_inquiry():

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401

    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip()
    message = str(data.get("message", "")).strip()

    if not name or not email or not message:

        return jsonify({
            "error": "All fields are required"
        }), 400

    conn = get_db()

    try:

        cursor = conn.cursor()

        # Save inquiry in Supabase
        cursor.execute(
            """
            INSERT INTO inquiries
            (
                professor_id,
                name,
                email,
                message
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                session["professor_id"],
                name,
                email,
                message
            )
        )

        conn.commit()

    except Exception as e:

        conn.rollback()

        print("Inquiry database error:", repr(e))

        return jsonify({
            "error": "Failed to save inquiry: " + str(e)
        }), 500

    finally:

        conn.close()


    # =================================================
    # SEND EMAIL
    # =================================================

    try:
        threading.Thread(
            target=send_inquiry_email_background,
            args=(name, email, message),
            daemon=True
        ).start()

        email_status = "EMAIL_QUEUED"

    except Exception as e:
        print("INQUIRY EMAIL THREAD ERROR:", repr(e))
        email_status = "EMAIL_ERROR"

    return jsonify({
        "success": True,
        "message": "Inquiry submitted successfully! | " + email_status
    })

# =====================================================
# REGISTER
# =====================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        college = request.form.get(
            "college",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        mobile = request.form.get(
            "mobile",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )


        if not name or not college or not email or not mobile or not password:

            return "All fields are required!", 400


        if password != confirm_password:

            return "Passwords do not match!", 400


        hashed_password = generate_password_hash(password)

        conn = None

        try:

            conn = get_db()

            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO professors
                (
                    name,
                    college,
                    email,
                    mobile,
                    password
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    name,
                    college,
                    email,
                    mobile,
                    hashed_password
                )
            )

            conn.commit()

            return redirect(
                url_for("login")
            )


        except psycopg2.IntegrityError:

            if conn:

                conn.rollback()

            return "Email already registered!", 409


        except Exception as e:

            if conn:

                conn.rollback()

            print(
                "Registration error:",
                repr(e)
            )

            return (
                "Registration failed: " + str(e),
                500
            )


        finally:

            if conn:

                conn.close()


    return render_template(
        "register.html"
    )

# =====================================================
# FORGOT PASSWORD
# =====================================================

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        mobile = request.form.get(
            "mobile",
            ""
        ).strip()

        if not mobile:

            return "Mobile number is required!", 400

        conn = get_db()

        try:

            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, mobile
                FROM professors
                WHERE mobile = %s
                """,
                (mobile,)
            )

            professor = cursor.fetchone()

        finally:

            conn.close()

        if professor is None:

            return "Registered mobile number not found!", 404

        # Generate 6-digit OTP
        otp = generate_reset_otp()

        print("PASSWORD RESET OTP:", otp)

        # OTP valid for 10 minutes
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        otp_hash = generate_password_hash(otp)

        conn = get_db()

        try:

            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO password_reset_otps
                (
                    professor_id,
                    mobile,
                    otp_hash,
                    expires_at
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    professor["id"],
                    mobile,
                    otp_hash,
                    expires_at
                )
            )

            conn.commit()

        except Exception as e:

            conn.rollback()

            print(
                "OTP database error:",
                repr(e)
            )

            return "Failed to create OTP: " + str(e), 500

        finally:

            conn.close()

        return "OTP generated successfully. Continue to OTP verification."

    return render_template(
        "forgot_password.html"
    )
# =====================================================
# VERIFY PASSWORD RESET OTP
# =====================================================

@app.route("/verify-reset-otp", methods=["POST"])
def verify_reset_otp():

    data = request.get_json(silent=True) or {}

    mobile = str(
        data.get("mobile", "")
    ).strip()

    otp = str(
        data.get("otp", "")
    ).strip()

    if not mobile or not otp:

        return jsonify({
            "error": "Mobile number and OTP are required"
        }), 400

    conn = get_db()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM password_reset_otps
            WHERE mobile = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (mobile,)
        )

        reset_data = cursor.fetchone()

    finally:

        conn.close()

    if reset_data is None:

        return jsonify({
            "error": "OTP not found"
        }), 404

    if datetime.utcnow() > reset_data["expires_at"].replace(
        tzinfo=None
    ):

        return jsonify({
            "error": "OTP has expired"
        }), 400

    if reset_data["attempts"] >= 5:

        return jsonify({
            "error": "Too many OTP attempts"
        }), 429

    if not check_password_hash(
        reset_data["otp_hash"],
        otp
    ):

        conn = get_db()

        try:

            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE password_reset_otps
                SET attempts = attempts + 1
                WHERE id = %s
                """,
                (reset_data["id"],)
            )

            conn.commit()

        finally:

            conn.close()

        return jsonify({
            "error": "Invalid OTP"
        }), 400

    conn = get_db()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE password_reset_otps
            SET verified = TRUE
            WHERE id = %s
            """,
            (reset_data["id"],)
        )

        conn.commit()

    finally:

        conn.close()

    session["password_reset_id"] = reset_data["id"]

    return jsonify({
        "success": True,
        "message": "OTP verified successfully"
    })
# =====================================================
# RESET PASSWORD PAGE
# =====================================================

@app.route("/reset-password-page")
def reset_password_page():

    reset_id = session.get("password_reset_id")

    if not reset_id:

        return redirect(
            url_for("forgot_password")
        )

    conn = get_db()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT verified
            FROM password_reset_otps
            WHERE id = %s
            """,
            (reset_id,)
        )

        reset_data = cursor.fetchone()

    finally:

        conn.close()


    if not reset_data or not reset_data["verified"]:

        session.pop(
            "password_reset_id",
            None
        )

        return redirect(
            url_for("forgot_password")
        )


    return render_template(
        "reset_password.html"
    )
# =====================================================
# RESET PASSWORD
# =====================================================

@app.route("/reset-password", methods=["POST"])
def reset_password():

    data = request.get_json(silent=True) or {}

    new_password = str(
        data.get("new_password", "")
    ).strip()

    confirm_password = str(
        data.get("confirm_password", "")
    ).strip()

    if not new_password or not confirm_password:

        return jsonify({
            "error": "New password and confirm password are required"
        }), 400

    if new_password != confirm_password:

        return jsonify({
            "error": "Passwords do not match"
        }), 400

    if len(new_password) < 6:

        return jsonify({
            "error": "Password must be at least 6 characters"
        }), 400

    reset_id = session.get("password_reset_id")

    if not reset_id:

        return jsonify({
            "error": "OTP verification required"
        }), 401

    conn = get_db()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT professor_id, verified
            FROM password_reset_otps
            WHERE id = %s
            """,
            (reset_id,)
        )

        reset_data = cursor.fetchone()

        if reset_data is None:

            return jsonify({
                "error": "Password reset request not found"
            }), 404

        if not reset_data["verified"]:

            return jsonify({
                "error": "OTP verification required"
            }), 401

        hashed_password = generate_password_hash(
            new_password
        )

        cursor.execute(
            """
            UPDATE professors
            SET password = %s
            WHERE id = %s
            """,
            (
                hashed_password,
                reset_data["professor_id"]
            )
        )

        conn.commit()

    except Exception as e:

        conn.rollback()

        print(
            "Password reset error:",
            repr(e)
        )

        return jsonify({
            "error": "Failed to reset password: " + str(e)
        }), 500

    finally:

        conn.close()

    session.pop(
        "password_reset_id",
        None
    )

    return jsonify({
        "success": True,
        "message": "Password reset successfully. Please login."
    })
# =====================================================
# LOGIN
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )


        conn = get_db()

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM professors
            WHERE email = %s
            """,
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

            return redirect(
                url_for("home")
            )


        return "Invalid email or password!", 401


    return render_template(
        "login.html"
    )


# =====================================================
# LOGOUT
# =====================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


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

    cursor.execute(
        """
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
        WHERE professor_id = %s
        ORDER BY id DESC
        """,
        (professor_id,)
    )


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


    data = request.get_json(
        silent=True
    ) or {}


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

        name = str(
            data["name"]
        ).strip()

        roll = str(
            data["roll"]
        ).strip()

        attendance = float(
            data["attendance"]
        )

        marks = float(
            data["marks"]
        )

        assignments = float(
            data["assignments"]
        )

        department = str(
            data["department"]
        ).strip()

        notes = str(
            data.get("notes", "")
        ).strip()


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


    try:

        cursor.execute(
            """
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
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            RETURNING id
            """,
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
        )


        student_id = cursor.fetchone()["id"]

        conn.commit()


    except Exception as e:

        conn.rollback()

        print(
            "Add student error:",
            repr(e)
        )

        return jsonify({
            "error": "Failed to add student: " + str(e)
        }), 500


    finally:

        conn.close()


    return jsonify({

        "success": True,

        "message": "Student added successfully",

        "id": student_id

    })


# =====================================================
# EDIT STUDENT
# =====================================================

@app.route(
    "/students/<int:student_id>",
    methods=["PUT"]
)
def edit_student(student_id):

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401


    data = request.get_json(
        silent=True
    ) or {}


    try:

        name = str(
            data["name"]
        ).strip()

        roll = str(
            data["roll"]
        ).strip()

        attendance = float(
            data["attendance"]
        )

        marks = float(
            data["marks"]
        )

        assignments = float(
            data["assignments"]
        )

        department = str(
            data["department"]
        ).strip()

        notes = str(
            data.get("notes", "")
        ).strip()


    except (
        KeyError,
        ValueError,
        TypeError
    ):

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


    try:

        cursor.execute(
            """
            UPDATE students

            SET
                name = %s,
                roll = %s,
                attendance = %s,
                marks = %s,
                assignments = %s,
                department = %s,
                notes = %s

            WHERE
                id = %s
                AND professor_id = %s
            """,
            (
                name,
                roll,
                attendance,
                marks,
                assignments,
                department,
                notes,
                student_id,
                professor_id
            )
        )


        updated = cursor.rowcount

        conn.commit()


    except Exception as e:

        conn.rollback()

        print(
            "Edit student error:",
            repr(e)
        )

        return jsonify({
            "error": "Failed to update student: " + str(e)
        }), 500


    finally:

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

@app.route(
    "/students/<int:student_id>",
    methods=["DELETE"]
)
def delete_student(student_id):

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401


    professor_id = session["professor_id"]

    conn = get_db()

    cursor = conn.cursor()


    try:

        cursor.execute(
            """
            DELETE FROM students

            WHERE
                id = %s
                AND professor_id = %s
            """,
            (
                student_id,
                professor_id
            )
        )


        deleted = cursor.rowcount

        conn.commit()


    except Exception as e:

        conn.rollback()

        print(
            "Delete student error:",
            repr(e)
        )

        return jsonify({
            "error": "Failed to delete student: " + str(e)
        }), 500


    finally:

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
# AI PREDICTION
# =====================================================

@app.route(
    "/predict",
    methods=["POST"]
)
def predict():

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401


    if model is None:

        return jsonify({
            "error": "AI model is not available. Check student_risk_model.pkl"
        }), 500


    data = request.get_json(
        silent=True
    ) or {}


    student_id = data.get(
        "student_id"
    )


    if student_id is None:

        return jsonify({
            "error": "Student ID is required"
        }), 400


    try:

        student_id = int(
            student_id
        )

    except (
        ValueError,
        TypeError
    ):

        return jsonify({
            "error": "Invalid student ID"
        }), 400


    professor_id = session["professor_id"]

    conn = get_db()

    cursor = conn.cursor()


    cursor.execute(
        """
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
            id = %s
            AND professor_id = %s
        """,
        (
            student_id,
            professor_id
        )
    )


    student = cursor.fetchone()

    conn.close()


    if student is None:

        return jsonify({
            "error": "Student not found or access denied"
        }), 404


    attendance = float(
        student["attendance"]
    )

    marks = float(
        student["marks"]
    )

    assignments = float(
        student["assignments"]
    )


    # =================================================
    # MODEL INPUT
    # =================================================

    input_data = pd.DataFrame([
        {
            "attendance": attendance,
            "score": marks,
            "lms": assignments
        }
    ])


    # =================================================
    # AI MODEL PREDICTION
    # =================================================

    try:

        prediction = model.predict(
            input_data
        )

        risk = str(
            prediction[0]
        ).strip()


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


    # =================================================
    # SAVE PREDICTION HISTORY
    # =================================================

    history_conn = get_db()

    history_cursor = history_conn.cursor()


    try:

        history_cursor.execute(
            """
            INSERT INTO prediction_history
            (
                student_id,
                professor_id,
                risk,
                attendance,
                marks,
                assignments
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                student["id"],
                professor_id,
                risk,
                attendance,
                marks,
                assignments
            )
        )


        history_conn.commit()


    except Exception as e:

        history_conn.rollback()

        print(
            "Prediction history error:",
            repr(e)
        )

        return jsonify({
            "error": "Failed to save prediction history: " + str(e)
        }), 500


    finally:

        history_conn.close()


    # =================================================
    # PERSONALIZED RECOMMENDATIONS
    # =================================================

    recommendations = []


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

@app.route(
    "/prediction-history/<int:student_id>",
    methods=["GET"]
)
def prediction_history(student_id):

    if not login_required():

        return jsonify({
            "error": "Please login first"
        }), 401


    professor_id = session["professor_id"]

    conn = get_db()

    cursor = conn.cursor()


    cursor.execute(
        """
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
            student_id = %s
            AND professor_id = %s

        ORDER BY id DESC
        """,
        (
            student_id,
            professor_id
        )
    )


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

    print("")

    print(
        "======================================"
    )

    print(
        " EduRisk AI Server Started"
    )

    print(
        " Local:   http://127.0.0.1:5000"
    )

    print(
        " Network: http://0.0.0.0:5000"
    )

    print(
        "======================================"
    )

    print("")


    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )