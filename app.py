from flask import Flask, request, jsonify, session, send_from_directory
from flask_mysqldb import MySQL
from config import Config
from werkzeug.utils import secure_filename
import os
import time

app = Flask(__name__)
app.secret_key = "edusphere-secret-key-2026"
app.config.from_object(Config)

mysql = MySQL(app)

# =========================================================
# FRONTEND PATH
# =========================================================

BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads", "cvs")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_CV_EXTENSIONS = {"pdf", "doc", "docx"}


def allowed_cv(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_CV_EXTENSIONS
    )


# =========================================================
# FRONTEND ROUTES
# =========================================================

@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "login.html")


@app.route("/<path:filename>")
def frontend(filename):
    file_path = os.path.join(BASE_DIR, filename)

    if os.path.isfile(file_path):
        return send_from_directory(BASE_DIR, filename)

    return jsonify({"message": "Page not found"}), 404


@app.route("/uploads/cvs/<path:filename>")
def uploaded_cv(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# =========================================================
# LOGIN
# =========================================================

@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.get_json() or {}

        username = (
            data.get("username")
            or data.get("email")
            or ""
        ).strip()

        password = (
            data.get("password")
            or ""
        ).strip()

        selected_role = (
            data.get("role")
            or ""
        ).strip().lower()

        if not username or not password:
            return jsonify({
                "success": False,
                "message": "Username/email and password are required"
            }), 400

        cur = mysql.connection.cursor()

        # -------------------------------------------------
        # LOGIN BY EMAIL
        # -------------------------------------------------

        cur.execute("""
            SELECT
                id,
                name,
                email,
                password,
                role
            FROM users
            WHERE email=%s
            LIMIT 1
        """, (username,))

        user = cur.fetchone()

        # -------------------------------------------------
        # LOGIN BY TEACHER EMPLOYEE ID
        # -------------------------------------------------

        if not user:
            cur.execute("""
                SELECT
                    u.id,
                    u.name,
                    u.email,
                    u.password,
                    u.role
                FROM users u
                INNER JOIN teachers t
                    ON t.user_id=u.id
                WHERE t.employee_id=%s
                AND u.role='teacher'
                LIMIT 1
            """, (username,))

            user = cur.fetchone()

        # -------------------------------------------------
        # USER NOT FOUND
        # -------------------------------------------------

        if not user:
            cur.close()

            return jsonify({
                "success": False,
                "message": "Invalid username/email or password"
            }), 401

        # -------------------------------------------------
        # PASSWORD CHECK
        # -------------------------------------------------

        if password != user[3]:
            cur.close()

            return jsonify({
                "success": False,
                "message": "Invalid username/email or password"
            }), 401

        # -------------------------------------------------
        # ROLE CHECK
        # -------------------------------------------------

        if selected_role and user[4].lower() != selected_role:
            cur.close()

            return jsonify({
                "success": False,
                "message": "The selected portal does not match this account."
            }), 403

        # -------------------------------------------------
        # SAVE SESSION
        # -------------------------------------------------

        session["user_id"] = user[0]
        session["username"] = user[2]
        session["role"] = user[4]

        cur.close()

        return jsonify({
            "success": True,
            "message": "Login successful",
            "user": {
                "id": user[0],
                "name": user[1],
                "email": user[2],
                "username": user[2],
                "role": user[4]
            }
        }), 200

    except Exception as e:

        print("LOGIN ERROR:", e)

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "success": False,
            "message": "Login failed",
            "error": str(e)
        }), 500


# =========================================================
# CURRENT USER
# =========================================================

@app.route("/api/me", methods=["GET"])
def current_user():

    if "user_id" not in session:
        return jsonify({
            "logged_in": False
        }), 401

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                id,
                name,
                email,
                role
            FROM users
            WHERE id=%s
            LIMIT 1
        """, (session["user_id"],))

        user = cur.fetchone()
        cur.close()

        if not user:
            session.clear()

            return jsonify({
                "logged_in": False
            }), 401

        return jsonify({
            "logged_in": True,
            "user": {
                "id": user[0],
                "name": user[1],
                "email": user[2],
                "role": user[3]
            }
        })

    except Exception as e:
        return jsonify({
            "message": "Unable to get current user",
            "error": str(e)
        }), 500


# =========================================================
# LOGOUT
# =========================================================

@app.route("/api/logout", methods=["POST"])
def logout():

    session.clear()

    return jsonify({
        "message": "Logout successful"
    })


# =========================================================
# DASHBOARD STATS
# =========================================================

@app.route("/api/dashboard/stats", methods=["GET"])
def dashboard_stats():

    try:
        cur = mysql.connection.cursor()

        cur.execute("SELECT COUNT(*) FROM students")
        students = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM teachers")
        teachers = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM classes")
        classes = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*)
            FROM admissions
            WHERE status='Pending'
        """)
        pending_admissions = cur.fetchone()[0]

        cur.close()

        return jsonify({
            "students": students,
            "teachers": teachers,
            "classes": classes,
            "pending_admissions": pending_admissions
        })

    except Exception as e:
        return jsonify({
            "message": "Failed to load dashboard statistics",
            "error": str(e)
        }), 500


# =========================================================
# STUDENTS
# =========================================================

@app.route("/api/students", methods=["GET"])
def get_students():

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                s.id,
                s.admission_no,
                s.name,
                s.father_name,
                s.gender,
                s.date_of_birth,
                s.phone,
                s.address,
                s.class_id,
                s.parent_id,
                c.class_name,
                c.section,
                s.created_at
            FROM students s
            LEFT JOIN classes c
                ON s.class_id=c.id
            ORDER BY s.id DESC
        """)

        rows = cur.fetchall()
        cur.close()

        students = []

        for row in rows:
            students.append({
                "id": row[0],
                "admission_no": row[1],
                "name": row[2],
                "father_name": row[3],
                "gender": row[4],
                "date_of_birth": str(row[5]) if row[5] else None,
                "phone": row[6],
                "address": row[7],
                "class_id": row[8],
                "parent_id": row[9],
                "class_name": row[10],
                "section": row[11],
                "created_at": str(row[12]) if row[12] else None
            })

        return jsonify(students)

    except Exception as e:
        return jsonify({
            "message": "Failed to load students",
            "error": str(e)
        }), 500


@app.route("/api/students", methods=["POST"])
def add_student():

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO students
            (
                admission_no,
                name,
                father_name,
                gender,
                date_of_birth,
                phone,
                address,
                class_id,
                parent_id
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            data.get("admission_no"),
            data.get("name"),
            data.get("father_name"),
            data.get("gender"),
            data.get("date_of_birth") or None,
            data.get("phone"),
            data.get("address"),
            data.get("class_id") or None,
            data.get("parent_id") or None
        ))

        mysql.connection.commit()

        student_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Student added successfully",
            "id": student_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add student",
            "error": str(e)
        }), 500


@app.route("/api/students/<int:student_id>", methods=["PUT"])
def update_student(student_id):

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            UPDATE students
            SET
                admission_no=%s,
                name=%s,
                father_name=%s,
                gender=%s,
                date_of_birth=%s,
                phone=%s,
                address=%s,
                class_id=%s,
                parent_id=%s
            WHERE id=%s
        """, (
            data.get("admission_no"),
            data.get("name"),
            data.get("father_name"),
            data.get("gender"),
            data.get("date_of_birth") or None,
            data.get("phone"),
            data.get("address"),
            data.get("class_id") or None,
            data.get("parent_id") or None,
            student_id
        ))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Student updated successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to update student",
            "error": str(e)
        }), 500


@app.route("/api/students/<int:student_id>", methods=["DELETE"])
def delete_student(student_id):

    try:
        cur = mysql.connection.cursor()

        cur.execute(
            "DELETE FROM students WHERE id=%s",
            (student_id,)
        )

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Student deleted successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to delete student",
            "error": str(e)
        }), 500


# =========================================================
# TEACHERS
# =========================================================

@app.route("/api/teachers", methods=["GET"])
def get_teachers():

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                id,
                employee_id,
                name,
                email,
                phone,
                subject,
                qualification,
                user_id,
                created_at
            FROM teachers
            ORDER BY id DESC
        """)

        rows = cur.fetchall()
        cur.close()

        teachers = []

        for row in rows:
            teachers.append({
                "id": row[0],
                "employee_id": row[1],
                "name": row[2],
                "email": row[3],
                "phone": row[4],
                "subject": row[5],
                "qualification": row[6],
                "user_id": row[7],
                "created_at": str(row[8]) if row[8] else None
            })

        return jsonify(teachers)

    except Exception as e:
        return jsonify({
            "message": "Failed to load teachers",
            "error": str(e)
        }), 500


@app.route("/api/teachers", methods=["POST"])
def add_teacher():

    try:
        data = request.get_json() or {}

        employee_id = data.get("employee_id")
        name = data.get("name")

        if not employee_id or not name:
            return jsonify({
                "message": "Employee ID and name are required"
            }), 400

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT id
            FROM teachers
            WHERE employee_id=%s
            LIMIT 1
        """, (employee_id,))

        if cur.fetchone():
            cur.close()

            return jsonify({
                "message": "Employee ID already exists"
            }), 400

        email = (
            data.get("email")
            or employee_id.lower() + "@edusphere.local"
        )

        cur.execute("""
            SELECT id
            FROM users
            WHERE email=%s
            LIMIT 1
        """, (email,))

        existing_user = cur.fetchone()

        if existing_user:
            cur.close()

            return jsonify({
                "message": "Email already exists"
            }), 400

        password = data.get("password") or "teacher123"

        cur.execute("""
            INSERT INTO users
            (
                name,
                email,
                password,
                role
            )
            VALUES (%s,%s,%s,'teacher')
        """, (
            name,
            email,
            password
        ))

        user_id = cur.lastrowid

        cur.execute("""
            INSERT INTO teachers
            (
                employee_id,
                name,
                email,
                phone,
                subject,
                qualification,
                user_id
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            employee_id,
            name,
            email,
            data.get("phone"),
            data.get("subject"),
            data.get("qualification"),
            user_id
        ))

        mysql.connection.commit()

        teacher_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Teacher added successfully",
            "id": teacher_id,
            "login_email": email,
            "password": password
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add teacher",
            "error": str(e)
        }), 500


@app.route("/api/teachers/<int:teacher_id>", methods=["PUT"])
def update_teacher(teacher_id):

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT user_id
            FROM teachers
            WHERE id=%s
            LIMIT 1
        """, (teacher_id,))

        teacher = cur.fetchone()

        if not teacher:
            cur.close()

            return jsonify({
                "message": "Teacher not found"
            }), 404

        user_id = teacher[0]

        email = data.get("email")

        if not email:
            email = (
                data.get("employee_id", "").lower()
                + "@edusphere.local"
            )

        if user_id:

            cur.execute("""
                UPDATE users
                SET
                    name=%s,
                    email=%s
                WHERE id=%s
            """, (
                data.get("name"),
                email,
                user_id
            ))

        else:

            password = data.get("password") or "teacher123"

            cur.execute("""
                INSERT INTO users
                (
                    name,
                    email,
                    password,
                    role
                )
                VALUES (%s,%s,%s,'teacher')
            """, (
                data.get("name"),
                email,
                password
            ))

            user_id = cur.lastrowid

        cur.execute("""
            UPDATE teachers
            SET
                employee_id=%s,
                name=%s,
                email=%s,
                phone=%s,
                subject=%s,
                qualification=%s,
                user_id=%s
            WHERE id=%s
        """, (
            data.get("employee_id"),
            data.get("name"),
            email,
            data.get("phone"),
            data.get("subject"),
            data.get("qualification"),
            user_id,
            teacher_id
        ))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Teacher updated successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to update teacher",
            "error": str(e)
        }), 500


@app.route("/api/teachers/<int:teacher_id>", methods=["DELETE"])
def delete_teacher(teacher_id):

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT user_id
            FROM teachers
            WHERE id=%s
        """, (teacher_id,))

        teacher = cur.fetchone()

        if not teacher:
            cur.close()

            return jsonify({
                "message": "Teacher not found"
            }), 404

        user_id = teacher[0]

        cur.execute(
            "DELETE FROM teachers WHERE id=%s",
            (teacher_id,)
        )

        if user_id:
            cur.execute(
                "DELETE FROM users WHERE id=%s",
                (user_id,)
            )

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Teacher deleted successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to delete teacher",
            "error": str(e)
        }), 500


# =========================================================
# CLASSES
# =========================================================

@app.route("/api/classes", methods=["GET"])
def get_classes():

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                c.id,
                c.class_name,
                c.section,
                c.class_teacher_id,
                t.name,
                c.created_at
            FROM classes c
            LEFT JOIN teachers t
                ON c.class_teacher_id=t.id
            ORDER BY c.id DESC
        """)

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:
            result.append({
                "id": row[0],
                "class_name": row[1],
                "section": row[2],
                "class_teacher_id": row[3],
                "teacher_name": row[4],
                "created_at": str(row[5]) if row[5] else None
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "message": "Failed to load classes",
            "error": str(e)
        }), 500


@app.route("/api/classes", methods=["POST"])
def add_class():

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO classes
            (
                class_name,
                section,
                class_teacher_id
            )
            VALUES (%s,%s,%s)
        """, (
            data.get("class_name"),
            data.get("section"),
            data.get("class_teacher_id") or None
        ))

        mysql.connection.commit()

        class_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Class added successfully",
            "id": class_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add class",
            "error": str(e)
        }), 500


@app.route("/api/classes/<int:class_id>", methods=["PUT"])
def update_class(class_id):

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            UPDATE classes
            SET
                class_name=%s,
                section=%s,
                class_teacher_id=%s
            WHERE id=%s
        """, (
            data.get("class_name"),
            data.get("section"),
            data.get("class_teacher_id") or None,
            class_id
        ))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Class updated successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to update class",
            "error": str(e)
        }), 500


@app.route("/api/classes/<int:class_id>", methods=["DELETE"])
def delete_class(class_id):

    try:
        cur = mysql.connection.cursor()

        cur.execute(
            "DELETE FROM classes WHERE id=%s",
            (class_id,)
        )

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Class deleted successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to delete class",
            "error": str(e)
        }), 500


# =========================================================
# ATTENDANCE
# =========================================================

@app.route("/api/attendance", methods=["GET"])
def get_attendance():

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                a.id,
                a.student_id,
                s.name,
                s.admission_no,
                a.attendance_date,
                a.status,
                a.created_at
            FROM attendance a
            INNER JOIN students s
                ON a.student_id=s.id
            ORDER BY a.attendance_date DESC, a.id DESC
        """)

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:
            result.append({
                "id": row[0],
                "student_id": row[1],
                "student_name": row[2],
                "admission_no": row[3],
                "attendance_date": str(row[4]) if row[4] else None,
                "status": row[5],
                "created_at": str(row[6]) if row[6] else None
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "message": "Failed to load attendance",
            "error": str(e)
        }), 500


@app.route("/api/attendance", methods=["POST"])
def add_attendance():

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO attendance
            (
                student_id,
                attendance_date,
                status
            )
            VALUES (%s,%s,%s)
        """, (
            data.get("student_id"),
            data.get("attendance_date"),
            data.get("status")
        ))

        mysql.connection.commit()

        attendance_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Attendance added successfully",
            "id": attendance_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add attendance",
            "error": str(e)
        }), 500


@app.route("/api/attendance/<int:attendance_id>", methods=["PUT"])
def update_attendance(attendance_id):

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            UPDATE attendance
            SET
                student_id=%s,
                attendance_date=%s,
                status=%s
            WHERE id=%s
        """, (
            data.get("student_id"),
            data.get("attendance_date"),
            data.get("status"),
            attendance_id
        ))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Attendance updated successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to update attendance",
            "error": str(e)
        }), 500


@app.route("/api/attendance/<int:attendance_id>", methods=["DELETE"])
def delete_attendance(attendance_id):

    try:
        cur = mysql.connection.cursor()

        cur.execute(
            "DELETE FROM attendance WHERE id=%s",
            (attendance_id,)
        )

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Attendance deleted successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to delete attendance",
            "error": str(e)
        }), 500


# =========================================================
# HOMEWORK
# =========================================================

@app.route("/api/homework", methods=["GET"])
def get_homework():

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                h.id,
                h.class_id,
                c.class_name,
                c.section,
                h.subject,
                h.title,
                h.description,
                h.due_date,
                h.created_at
            FROM homework h
            LEFT JOIN classes c
                ON h.class_id=c.id
            ORDER BY h.id DESC
        """)

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:
            result.append({
                "id": row[0],
                "class_id": row[1],
                "class_name": row[2],
                "section": row[3],
                "subject": row[4],
                "title": row[5],
                "description": row[6],
                "due_date": str(row[7]) if row[7] else None,
                "created_at": str(row[8]) if row[8] else None
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "message": "Failed to load homework",
            "error": str(e)
        }), 500


@app.route("/api/homework", methods=["POST"])
def add_homework():

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO homework
            (
                class_id,
                subject,
                title,
                description,
                due_date
            )
            VALUES (%s,%s,%s,%s,%s)
        """, (
            data.get("class_id"),
            data.get("subject"),
            data.get("title"),
            data.get("description"),
            data.get("due_date") or None
        ))

        mysql.connection.commit()

        homework_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Homework added successfully",
            "id": homework_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add homework",
            "error": str(e)
        }), 500


@app.route("/api/homework/<int:homework_id>", methods=["PUT"])
def update_homework(homework_id):

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            UPDATE homework
            SET
                class_id=%s,
                subject=%s,
                title=%s,
                description=%s,
                due_date=%s
            WHERE id=%s
        """, (
            data.get("class_id"),
            data.get("subject"),
            data.get("title"),
            data.get("description"),
            data.get("due_date") or None,
            homework_id
        ))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Homework updated successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to update homework",
            "error": str(e)
        }), 500


@app.route("/api/homework/<int:homework_id>", methods=["DELETE"])
def delete_homework(homework_id):

    try:
        cur = mysql.connection.cursor()

        cur.execute(
            "DELETE FROM homework WHERE id=%s",
            (homework_id,)
        )

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Homework deleted successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to delete homework",
            "error": str(e)
        }), 500


# =========================================================
# SYLLABUS
# =========================================================

@app.route("/api/syllabus", methods=["GET"])
def get_syllabus():

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                sy.id,
                sy.class_id,
                c.class_name,
                c.section,
                sy.subject,
                sy.title,
                sy.description,
                sy.start_date,
                sy.end_date,
                sy.created_at
            FROM syllabus sy
            LEFT JOIN classes c
                ON sy.class_id=c.id
            ORDER BY sy.id DESC
        """)

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:
            result.append({
                "id": row[0],
                "class_id": row[1],
                "class_name": row[2],
                "section": row[3],
                "subject": row[4],
                "title": row[5],
                "description": row[6],
                "start_date": str(row[7]) if row[7] else None,
                "end_date": str(row[8]) if row[8] else None,
                "created_at": str(row[9]) if row[9] else None
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "message": "Failed to load syllabus",
            "error": str(e)
        }), 500


@app.route("/api/syllabus", methods=["POST"])
def add_syllabus():

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO syllabus
            (
                class_id,
                subject,
                title,
                description,
                start_date,
                end_date
            )
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            data.get("class_id"),
            data.get("subject"),
            data.get("title"),
            data.get("description"),
            data.get("start_date") or None,
            data.get("end_date") or None
        ))

        mysql.connection.commit()

        syllabus_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Syllabus added successfully",
            "id": syllabus_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add syllabus",
            "error": str(e)
        }), 500


@app.route("/api/syllabus/<int:syllabus_id>", methods=["PUT"])
def update_syllabus(syllabus_id):

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            UPDATE syllabus
            SET
                class_id=%s,
                subject=%s,
                title=%s,
                description=%s,
                start_date=%s,
                end_date=%s
            WHERE id=%s
        """, (
            data.get("class_id"),
            data.get("subject"),
            data.get("title"),
            data.get("description"),
            data.get("start_date") or None,
            data.get("end_date") or None,
            syllabus_id
        ))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Syllabus updated successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to update syllabus",
            "error": str(e)
        }), 500


@app.route("/api/syllabus/<int:syllabus_id>", methods=["DELETE"])
def delete_syllabus(syllabus_id):

    try:
        cur = mysql.connection.cursor()

        cur.execute(
            "DELETE FROM syllabus WHERE id=%s",
            (syllabus_id,)
        )

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Syllabus deleted successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to delete syllabus",
            "error": str(e)
        }), 500


# =========================================================
# DATE SHEET
# =========================================================

@app.route("/api/date-sheet", methods=["GET"])
def get_date_sheet():

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                d.id,
                d.class_id,
                c.class_name,
                c.section,
                d.subject,
                d.exam_date,
                d.exam_time,
                d.room,
                d.created_at
            FROM date_sheet d
            LEFT JOIN classes c
                ON d.class_id=c.id
            ORDER BY d.exam_date ASC, d.id ASC
        """)

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:
            result.append({
                "id": row[0],
                "class_id": row[1],
                "class_name": row[2],
                "section": row[3],
                "subject": row[4],
                "exam_date": str(row[5]) if row[5] else None,
                "exam_time": row[6],
                "room": row[7],
                "created_at": str(row[8]) if row[8] else None
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "message": "Failed to load date sheet",
            "error": str(e)
        }), 500


@app.route("/api/date-sheet", methods=["POST"])
def add_date_sheet():

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO date_sheet
            (
                class_id,
                subject,
                exam_date,
                exam_time,
                room
            )
            VALUES (%s,%s,%s,%s,%s)
        """, (
            data.get("class_id"),
            data.get("subject"),
            data.get("exam_date"),
            data.get("exam_time"),
            data.get("room")
        ))

        mysql.connection.commit()

        date_sheet_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Date sheet added successfully",
            "id": date_sheet_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add date sheet",
            "error": str(e)
        }), 500


@app.route("/api/date-sheet/<int:date_sheet_id>", methods=["PUT"])
def update_date_sheet(date_sheet_id):

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            UPDATE date_sheet
            SET
                class_id=%s,
                subject=%s,
                exam_date=%s,
                exam_time=%s,
                room=%s
            WHERE id=%s
        """, (
            data.get("class_id"),
            data.get("subject"),
            data.get("exam_date"),
            data.get("exam_time"),
            data.get("room"),
            date_sheet_id
        ))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Date sheet updated successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to update date sheet",
            "error": str(e)
        }), 500


@app.route("/api/date-sheet/<int:date_sheet_id>", methods=["DELETE"])
def delete_date_sheet(date_sheet_id):

    try:
        cur = mysql.connection.cursor()

        cur.execute(
            "DELETE FROM date_sheet WHERE id=%s",
            (date_sheet_id,)
        )

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Date sheet deleted successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to delete date sheet",
            "error": str(e)
        }), 500


# =========================================================
# RESULTS
# =========================================================

@app.route("/api/results", methods=["GET"])
def get_results():

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                r.id,
                r.student_id,
                s.name,
                s.admission_no,
                r.subject,
                r.total_marks,
                r.obtained_marks,
                r.grade,
                r.remarks,
                r.created_at
            FROM results r
            INNER JOIN students s
                ON r.student_id=s.id
            ORDER BY r.id DESC
        """)

        rows = cur.fetchall()
        cur.close()

        results = []

        for row in rows:
            results.append({
                "id": row[0],
                "student_id": row[1],
                "student_name": row[2],
                "admission_no": row[3],
                "subject": row[4],
                "total_marks": row[5],
                "obtained_marks": row[6],
                "grade": row[7],
                "remarks": row[8],
                "created_at": str(row[9]) if row[9] else None
            })

        return jsonify(results)

    except Exception as e:
        return jsonify({
            "message": "Failed to load results",
            "error": str(e)
        }), 500


@app.route("/api/results", methods=["POST"])
def add_result():

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO results
            (
                student_id,
                subject,
                total_marks,
                obtained_marks,
                grade,
                remarks
            )
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            data.get("student_id"),
            data.get("subject"),
            data.get("total_marks", 100),
            data.get("obtained_marks", 0),
            data.get("grade"),
            data.get("remarks")
        ))

        mysql.connection.commit()

        result_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Result added successfully",
            "id": result_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add result",
            "error": str(e)
        }), 500


@app.route("/api/results/<int:result_id>", methods=["PUT"])
def update_result(result_id):

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            UPDATE results
            SET
                student_id=%s,
                subject=%s,
                total_marks=%s,
                obtained_marks=%s,
                grade=%s,
                remarks=%s
            WHERE id=%s
        """, (
            data.get("student_id"),
            data.get("subject"),
            data.get("total_marks", 100),
            data.get("obtained_marks", 0),
            data.get("grade"),
            data.get("remarks"),
            result_id
        ))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Result updated successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to update result",
            "error": str(e)
        }), 500


@app.route("/api/results/<int:result_id>", methods=["DELETE"])
def delete_result(result_id):

    try:
        cur = mysql.connection.cursor()

        cur.execute(
            "DELETE FROM results WHERE id=%s",
            (result_id,)
        )

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Result deleted successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to delete result",
            "error": str(e)
        }), 500


# =========================================================
# FEES
# =========================================================

@app.route("/api/fees", methods=["GET"])
def get_fees():

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                f.id,
                f.student_id,
                s.name,
                s.admission_no,
                f.fee_month,
                f.amount,
                f.paid_amount,
                f.status,
                f.due_date,
                f.created_at
            FROM fees f
            INNER JOIN students s
                ON f.student_id=s.id
            ORDER BY f.id DESC
        """)

        rows = cur.fetchall()
        cur.close()

        fees = []

        for row in rows:
            fees.append({
                "id": row[0],
                "student_id": row[1],
                "student_name": row[2],
                "admission_no": row[3],
                "fee_month": row[4],
                "amount": float(row[5]),
                "paid_amount": float(row[6]),
                "status": row[7],
                "due_date": str(row[8]) if row[8] else None,
                "created_at": str(row[9]) if row[9] else None
            })

        return jsonify(fees)

    except Exception as e:
        return jsonify({
            "message": "Failed to load fees",
            "error": str(e)
        }), 500


@app.route("/api/fees", methods=["POST"])
def add_fee():

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO fees
            (
                student_id,
                fee_month,
                amount,
                paid_amount,
                status,
                due_date
            )
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            data.get("student_id"),
            data.get("fee_month"),
            data.get("amount", 0),
            data.get("paid_amount", 0),
            data.get("status", "Unpaid"),
            data.get("due_date") or None
        ))

        mysql.connection.commit()

        fee_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Fee added successfully",
            "id": fee_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add fee",
            "error": str(e)
        }), 500


@app.route("/api/fees/<int:fee_id>", methods=["PUT"])
def update_fee(fee_id):

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            UPDATE fees
            SET
                student_id=%s,
                fee_month=%s,
                amount=%s,
                paid_amount=%s,
                status=%s,
                due_date=%s
            WHERE id=%s
        """, (
            data.get("student_id"),
            data.get("fee_month"),
            data.get("amount", 0),
            data.get("paid_amount", 0),
            data.get("status", "Unpaid"),
            data.get("due_date") or None,
            fee_id
        ))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Fee updated successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to update fee",
            "error": str(e)
        }), 500


@app.route("/api/fees/<int:fee_id>", methods=["DELETE"])
def delete_fee(fee_id):

    try:
        cur = mysql.connection.cursor()

        cur.execute(
            "DELETE FROM fees WHERE id=%s",
            (fee_id,)
        )

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Fee deleted successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to delete fee",
            "error": str(e)
        }), 500


# =========================================================
# NOTICES
# =========================================================

@app.route("/api/notices", methods=["GET"])
def get_notices():

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                id,
                title,
                message,
                notice_date,
                audience,
                created_at
            FROM notices
            ORDER BY id DESC
        """)

        rows = cur.fetchall()
        cur.close()

        notices = []

        for row in rows:
            notices.append({
                "id": row[0],
                "title": row[1],
                "message": row[2],
                "notice_date": str(row[3]) if row[3] else None,
                "audience": row[4],
                "created_at": str(row[5]) if row[5] else None
            })

        return jsonify(notices)

    except Exception as e:
        return jsonify({
            "message": "Failed to load notices",
            "error": str(e)
        }), 500


@app.route("/api/notices", methods=["POST"])
def add_notice():

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO notices
            (
                title,
                message,
                notice_date,
                audience
            )
            VALUES (%s,%s,%s,%s)
        """, (
            data.get("title"),
            data.get("message"),
            data.get("notice_date") or None,
            data.get("audience", "All")
        ))

        mysql.connection.commit()

        notice_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Notice added successfully",
            "id": notice_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add notice",
            "error": str(e)
        }), 500


@app.route("/api/notices/<int:notice_id>", methods=["PUT"])
def update_notice(notice_id):

    try:
        data = request.get_json() or {}

        cur = mysql.connection.cursor()

        cur.execute("""
            UPDATE notices
            SET
                title=%s,
                message=%s,
                notice_date=%s,
                audience=%s
            WHERE id=%s
        """, (
            data.get("title"),
            data.get("message"),
            data.get("notice_date") or None,
            data.get("audience", "All"),
            notice_id
        ))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Notice updated successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to update notice",
            "error": str(e)
        }), 500


@app.route("/api/notices/<int:notice_id>", methods=["DELETE"])
def delete_notice(notice_id):

    try:
        cur = mysql.connection.cursor()

        cur.execute(
            "DELETE FROM notices WHERE id=%s",
            (notice_id,)
        )

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Notice deleted successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to delete notice",
            "error": str(e)
        }), 500


# =========================================================
# ADMISSIONS
# =========================================================

@app.route("/api/admissions", methods=["GET"])
def get_admissions():

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                id,
                student_name,
                father_name,
                email,
                phone,
                date_of_birth,
                gender,
                class_applied,
                address,
                previous_school,
                cv_filename,
                application_date,
                status,
                created_at
            FROM admissions
            ORDER BY id DESC
        """)

        rows = cur.fetchall()
        cur.close()

        admissions = []

        for row in rows:
            admissions.append({
                "id": row[0],
                "student_name": row[1],
                "father_name": row[2],
                "email": row[3],
                "phone": row[4],
                "date_of_birth": str(row[5]) if row[5] else None,
                "gender": row[6],
                "class_applied": row[7],
                "address": row[8],
                "previous_school": row[9],
                "cv_filename": row[10],
                "cv_url": (
                    "/uploads/cvs/" + row[10]
                    if row[10]
                    else None
                ),
                "application_date": str(row[11]) if row[11] else None,
                "status": row[12],
                "created_at": str(row[13]) if row[13] else None
            })

        return jsonify(admissions)

    except Exception as e:
        return jsonify({
            "message": "Failed to load admissions",
            "error": str(e)
        }), 500


@app.route("/api/admissions", methods=["POST"])
def add_admission():

    try:
        form = request.form

        student_name = form.get("student_name")

        if not student_name:
            return jsonify({
                "message": "Student name is required"
            }), 400

        cv = request.files.get("cv")
        cv_filename = None

        if cv and cv.filename:

            if not allowed_cv(cv.filename):
                return jsonify({
                    "message": "Only PDF, DOC and DOCX files are allowed"
                }), 400

            original_name = secure_filename(cv.filename)

            cv_filename = (
                str(int(time.time()))
                + "_"
                + original_name
            )

            cv.save(
                os.path.join(
                    UPLOAD_FOLDER,
                    cv_filename
                )
            )

        application_date = (
            form.get("application_date")
            or None
        )

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO admissions
            (
                student_name,
                father_name,
                email,
                phone,
                date_of_birth,
                gender,
                class_applied,
                address,
                previous_school,
                cv_filename,
                application_date,
                status
            )
            VALUES
            (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
        """, (
            student_name,
            form.get("father_name"),
            form.get("email"),
            form.get("phone"),
            form.get("date_of_birth") or None,
            form.get("gender"),
            form.get("class_applied"),
            form.get("address"),
            form.get("previous_school"),
            cv_filename,
            application_date,
            "Pending"
        ))

        mysql.connection.commit()

        admission_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Admission submitted successfully",
            "id": admission_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        print("ADMISSION ERROR:", e)

        return jsonify({
            "message": "Failed to submit admission",
            "error": str(e)
        }), 500


@app.route("/api/admissions/<int:admission_id>", methods=["DELETE"])
def delete_admission(admission_id):

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT cv_filename
            FROM admissions
            WHERE id=%s
        """, (admission_id,))

        admission = cur.fetchone()

        if not admission:
            cur.close()

            return jsonify({
                "message": "Admission not found"
            }), 404

        cv_filename = admission[0]

        cur.execute("""
            DELETE FROM admissions
            WHERE id=%s
        """, (admission_id,))

        mysql.connection.commit()

        cur.close()

        if cv_filename:

            cv_path = os.path.join(
                UPLOAD_FOLDER,
                cv_filename
            )

            if os.path.exists(cv_path):
                os.remove(cv_path)

        return jsonify({
            "message": "Admission deleted successfully"
        })

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to delete admission",
            "error": str(e)
        }), 500


# =========================================================
# TEACHER PORTAL HELPER
# =========================================================

def get_logged_in_teacher():

    if "user_id" not in session:
        return None

    if session.get("role") != "teacher":
        return None

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT
            t.id,
            t.employee_id,
            t.name,
            t.email,
            t.phone,
            t.subject,
            t.qualification,
            t.user_id
        FROM teachers t
        WHERE t.user_id=%s
        LIMIT 1
    """, (session["user_id"],))

    teacher = cur.fetchone()

    cur.close()

    return teacher


# =========================================================
# TEACHER PROFILE
# =========================================================

@app.route("/api/teacher/profile", methods=["GET"])
def teacher_profile():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        return jsonify({
            "id": teacher[0],
            "employee_id": teacher[1],
            "name": teacher[2],
            "email": teacher[3],
            "phone": teacher[4],
            "subject": teacher[5],
            "qualification": teacher[6],
            "user_id": teacher[7]
        })

    except Exception as e:
        return jsonify({
            "message": "Failed to load teacher profile",
            "error": str(e)
        }), 500


# =========================================================
# TEACHER DASHBOARD
# =========================================================

@app.route("/api/teacher/dashboard", methods=["GET"])
def teacher_dashboard():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        teacher_id = teacher[0]

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT COUNT(*)
            FROM classes
            WHERE class_teacher_id=%s
        """, (teacher_id,))

        class_count = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*)
            FROM students s
            INNER JOIN classes c
                ON s.class_id=c.id
            WHERE c.class_teacher_id=%s
        """, (teacher_id,))

        student_count = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*)
            FROM homework h
            INNER JOIN classes c
                ON h.class_id=c.id
            WHERE c.class_teacher_id=%s
        """, (teacher_id,))

        homework_count = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*)
            FROM syllabus sy
            INNER JOIN classes c
                ON sy.class_id=c.id
            WHERE c.class_teacher_id=%s
        """, (teacher_id,))

        syllabus_count = cur.fetchone()[0]

        cur.close()

        return jsonify({
            "teacher": {
                "id": teacher[0],
                "name": teacher[2],
                "employee_id": teacher[1],
                "subject": teacher[5]
            },
            "classes": class_count,
            "students": student_count,
            "homework": homework_count,
            "syllabus": syllabus_count
        })

    except Exception as e:
        return jsonify({
            "message": "Failed to load teacher dashboard",
            "error": str(e)
        }), 500


# =========================================================
# TEACHER CLASSES
# =========================================================

@app.route("/api/teacher/classes", methods=["GET"])
def teacher_classes():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                c.id,
                c.class_name,
                c.section,
                c.class_teacher_id,
                c.teacher_id,
                (
                    SELECT COUNT(*)
                    FROM students s
                    WHERE s.class_id = c.id
                ) AS student_count
            FROM classes c
            WHERE c.class_teacher_id = %s
               OR c.teacher_id = %s
            ORDER BY c.id DESC
        """, (teacher[0], teacher[0]))

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:

            result.append({
                "id": row[0],
                "class_name": row[1],
                "section": row[2],
                "class_teacher_id": row[3],
                "teacher_id": row[4],
                "student_count": row[5],
                "is_class_teacher": row[3] == teacher[0]
            })

        return jsonify(result)

    except Exception as e:

        print("TEACHER CLASSES ERROR:", e)

        return jsonify({
            "message": "Failed to load teacher classes",
            "error": str(e)
        }), 500


# =========================================================
# TEACHER STUDENTS
# =========================================================

@app.route("/api/teacher/students", methods=["GET"])
def teacher_students():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                s.id,
                s.admission_no,
                s.name,
                s.father_name,
                s.gender,
                s.date_of_birth,
                s.phone,
                s.address,
                s.class_id,
                c.class_name,
                c.section
            FROM students s
            INNER JOIN classes c
                ON s.class_id=c.id
            WHERE c.class_teacher_id=%s
            ORDER BY s.name ASC
        """, (teacher[0],))

        rows = cur.fetchall()
        cur.close()

        students = []

        for row in rows:
            students.append({
                "id": row[0],
                "admission_no": row[1],
                "name": row[2],
                "father_name": row[3],
                "gender": row[4],
                "date_of_birth": str(row[5]) if row[5] else None,
                "phone": row[6],
                "address": row[7],
                "class_id": row[8],
                "class_name": row[9],
                "section": row[10]
            })

        return jsonify(students)

    except Exception as e:
        return jsonify({
            "message": "Failed to load teacher students",
            "error": str(e)
        }), 500


# =========================================================
# TEACHER HOMEWORK
# =========================================================

@app.route("/api/teacher/homework", methods=["GET"])
def teacher_get_homework():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                h.id,
                h.class_id,
                c.class_name,
                c.section,
                h.subject,
                h.title,
                h.description,
                h.due_date,
                h.created_at
            FROM homework h
            INNER JOIN classes c
                ON h.class_id=c.id
            WHERE c.class_teacher_id=%s
            ORDER BY h.id DESC
        """, (teacher[0],))

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:
            result.append({
                "id": row[0],
                "class_id": row[1],
                "class_name": row[2],
                "section": row[3],
                "subject": row[4],
                "title": row[5],
                "description": row[6],
                "due_date": str(row[7]) if row[7] else None,
                "created_at": str(row[8]) if row[8] else None
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "message": "Failed to load teacher homework",
            "error": str(e)
        }), 500


@app.route("/api/teacher/homework", methods=["POST"])
def teacher_add_homework():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        data = request.get_json() or {}

        class_id = data.get("class_id")

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT id
            FROM classes
            WHERE id=%s
            AND class_teacher_id=%s
        """, (
            class_id,
            teacher[0]
        ))

        if not cur.fetchone():
            cur.close()

            return jsonify({
                "message": "You are not assigned to this class"
            }), 403

        cur.execute("""
            INSERT INTO homework
            (
                class_id,
                subject,
                title,
                description,
                due_date
            )
            VALUES (%s,%s,%s,%s,%s)
        """, (
            class_id,
            data.get("subject"),
            data.get("title"),
            data.get("description"),
            data.get("due_date") or None
        ))

        mysql.connection.commit()

        homework_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Homework added successfully",
            "id": homework_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add homework",
            "error": str(e)
        }), 500


# =========================================================
# TEACHER SYLLABUS
# =========================================================

@app.route("/api/teacher/syllabus", methods=["GET"])
def teacher_get_syllabus():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                sy.id,
                sy.class_id,
                c.class_name,
                c.section,
                sy.subject,
                sy.title,
                sy.description,
                sy.start_date,
                sy.end_date,
                sy.created_at
            FROM syllabus sy
            INNER JOIN classes c
                ON sy.class_id=c.id
            WHERE c.class_teacher_id=%s
            ORDER BY sy.id DESC
        """, (teacher[0],))

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:
            result.append({
                "id": row[0],
                "class_id": row[1],
                "class_name": row[2],
                "section": row[3],
                "subject": row[4],
                "title": row[5],
                "description": row[6],
                "start_date": str(row[7]) if row[7] else None,
                "end_date": str(row[8]) if row[8] else None,
                "created_at": str(row[9]) if row[9] else None
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "message": "Failed to load teacher syllabus",
            "error": str(e)
        }), 500


@app.route("/api/teacher/syllabus", methods=["POST"])
def teacher_add_syllabus():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        data = request.get_json() or {}

        class_id = data.get("class_id")

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT id
            FROM classes
            WHERE id=%s
            AND class_teacher_id=%s
        """, (
            class_id,
            teacher[0]
        ))

        if not cur.fetchone():
            cur.close()

            return jsonify({
                "message": "You are not assigned to this class"
            }), 403

        cur.execute("""
            INSERT INTO syllabus
            (
                class_id,
                subject,
                title,
                description,
                start_date,
                end_date
            )
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            class_id,
            data.get("subject"),
            data.get("title"),
            data.get("description"),
            data.get("start_date") or None,
            data.get("end_date") or None
        ))

        mysql.connection.commit()

        syllabus_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Syllabus added successfully",
            "id": syllabus_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add syllabus",
            "error": str(e)
        }), 500


# =========================================================
# TEACHER ATTENDANCE
# =========================================================

@app.route("/api/teacher/attendance", methods=["GET"])
def teacher_get_attendance():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                a.id,
                a.student_id,
                s.name,
                s.admission_no,
                s.class_id,
                c.class_name,
                c.section,
                a.attendance_date,
                a.status
            FROM attendance a
            INNER JOIN students s
                ON a.student_id=s.id
            INNER JOIN classes c
                ON s.class_id=c.id
            WHERE c.class_teacher_id=%s
            ORDER BY a.attendance_date DESC, a.id DESC
        """, (teacher[0],))

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:
            result.append({
                "id": row[0],
                "student_id": row[1],
                "student_name": row[2],
                "admission_no": row[3],
                "class_id": row[4],
                "class_name": row[5],
                "section": row[6],
                "attendance_date": str(row[7]),
                "status": row[8]
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "message": "Failed to load teacher attendance",
            "error": str(e)
        }), 500


@app.route("/api/teacher/attendance", methods=["POST"])
def teacher_add_attendance():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        data = request.get_json() or {}

        student_id = data.get("student_id")

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT s.id
            FROM students s
            INNER JOIN classes c
                ON s.class_id=c.id
            WHERE s.id=%s
            AND c.class_teacher_id=%s
        """, (
            student_id,
            teacher[0]
        ))

        if not cur.fetchone():
            cur.close()

            return jsonify({
                "message": "This student is not in your assigned class"
            }), 403

        cur.execute("""
            INSERT INTO attendance
            (
                student_id,
                attendance_date,
                status
            )
            VALUES (%s,%s,%s)
        """, (
            student_id,
            data.get("attendance_date"),
            data.get("status")
        ))

        mysql.connection.commit()

        attendance_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Attendance added successfully",
            "id": attendance_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add attendance",
            "error": str(e)
        }), 500


# =========================================================
# TEACHER RESULTS
# =========================================================

@app.route("/api/teacher/results", methods=["GET"])
def teacher_get_results():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                r.id,
                r.student_id,
                s.name,
                s.admission_no,
                s.class_id,
                c.class_name,
                c.section,
                r.subject,
                r.total_marks,
                r.obtained_marks,
                r.grade,
                r.remarks
            FROM results r
            INNER JOIN students s
                ON r.student_id=s.id
            INNER JOIN classes c
                ON s.class_id=c.id
            WHERE c.class_teacher_id=%s
            ORDER BY r.id DESC
        """, (teacher[0],))

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:
            result.append({
                "id": row[0],
                "student_id": row[1],
                "student_name": row[2],
                "admission_no": row[3],
                "class_id": row[4],
                "class_name": row[5],
                "section": row[6],
                "subject": row[7],
                "total_marks": row[8],
                "obtained_marks": row[9],
                "grade": row[10],
                "remarks": row[11]
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "message": "Failed to load teacher results",
            "error": str(e)
        }), 500


@app.route("/api/teacher/results", methods=["POST"])
def teacher_add_result():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        data = request.get_json() or {}

        student_id = data.get("student_id")

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT s.id
            FROM students s
            INNER JOIN classes c
                ON s.class_id=c.id
            WHERE s.id=%s
            AND c.class_teacher_id=%s
        """, (
            student_id,
            teacher[0]
        ))

        if not cur.fetchone():
            cur.close()

            return jsonify({
                "message": "This student is not in your assigned class"
            }), 403

        cur.execute("""
            INSERT INTO results
            (
                student_id,
                subject,
                total_marks,
                obtained_marks,
                grade,
                remarks
            )
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            student_id,
            data.get("subject"),
            data.get("total_marks", 100),
            data.get("obtained_marks", 0),
            data.get("grade"),
            data.get("remarks")
        ))

        mysql.connection.commit()

        result_id = cur.lastrowid

        cur.close()

        return jsonify({
            "message": "Result added successfully",
            "id": result_id
        }), 201

    except Exception as e:

        try:
            mysql.connection.rollback()
        except:
            pass

        return jsonify({
            "message": "Failed to add result",
            "error": str(e)
        }), 500


# =========================================================
# TEACHER DATE SHEET
# =========================================================

@app.route("/api/teacher/date-sheet", methods=["GET"])
def teacher_date_sheet():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                d.id,
                d.class_id,
                c.class_name,
                c.section,
                d.subject,
                d.exam_date,
                d.exam_time,
                d.room
            FROM date_sheet d
            INNER JOIN classes c
                ON d.class_id=c.id
            WHERE c.class_teacher_id=%s
            ORDER BY d.exam_date ASC
        """, (teacher[0],))

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:
            result.append({
                "id": row[0],
                "class_id": row[1],
                "class_name": row[2],
                "section": row[3],
                "subject": row[4],
                "exam_date": str(row[5]) if row[5] else None,
                "exam_time": row[6],
                "room": row[7]
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "message": "Failed to load teacher date sheet",
            "error": str(e)
        }), 500


# =========================================================
# TEACHER NOTICES
# =========================================================

@app.route("/api/teacher/notices", methods=["GET"])
def teacher_notices():

    try:
        teacher = get_logged_in_teacher()

        if not teacher:
            return jsonify({
                "message": "Teacher login required"
            }), 401

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT
                id,
                title,
                message,
                notice_date,
                audience,
                created_at
            FROM notices
            WHERE audience='All'
               OR audience='Teacher'
               OR audience='Teachers'
            ORDER BY id DESC
        """)

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:
            result.append({
                "id": row[0],
                "title": row[1],
                "message": row[2],
                "notice_date": str(row[3]) if row[3] else None,
                "audience": row[4],
                "created_at": str(row[5]) if row[5] else None
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "message": "Failed to load teacher notices",
            "error": str(e)
        }), 500


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)