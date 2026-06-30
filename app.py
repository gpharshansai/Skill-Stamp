from flask import Flask, render_template, request, redirect, session, url_for, send_from_directory
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import uuid

app = Flask(__name__)
app.secret_key = "skillchain_secret"

# File upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def ensure_certificate_columns(cursor_obj, db_obj):
    cursor_obj.execute("SHOW COLUMNS FROM certificate LIKE 'cert_code'")
    if not cursor_obj.fetchone():
        cursor_obj.execute("ALTER TABLE certificate ADD COLUMN cert_code VARCHAR(50) UNIQUE")
        db_obj.commit()

    cursor_obj.execute("SHOW COLUMNS FROM certificate LIKE 'certificate_file_path'")
    if not cursor_obj.fetchone():
        cursor_obj.execute("ALTER TABLE certificate ADD COLUMN certificate_file_path VARCHAR(255)")
        db_obj.commit()

def ensure_job_posting_columns(cursor_obj, db_obj):
    """Ensure required_skills column exists in job_posting table"""
    cursor_obj.execute("SHOW COLUMNS FROM job_posting LIKE 'required_skills'")
    if not cursor_obj.fetchone():
        cursor_obj.execute("ALTER TABLE job_posting ADD COLUMN required_skills LONGTEXT")
        db_obj.commit()

def generate_unique_cert_code(cursor_obj):
    while True:
        cert_code = f"CERT-{uuid.uuid4().hex[:6].upper()}-{uuid.uuid4().hex[:6].upper()}"
        cursor_obj.execute("SELECT certificate_id FROM certificate WHERE cert_code = %s", (cert_code,))
        if not cursor_obj.fetchone():
            return cert_code

def backfill_missing_cert_codes(cursor_obj, db_obj):
    cursor_obj.execute("SELECT certificate_id FROM certificate WHERE cert_code IS NULL OR cert_code = ''")
    missing = cursor_obj.fetchall()
    if not missing:
        return
    for row in missing:
        code = generate_unique_cert_code(cursor_obj)
        cursor_obj.execute(
            "UPDATE certificate SET cert_code = %s WHERE certificate_id = %s",
            (code, row["certificate_id"])
        )
    db_obj.commit()

# Database connection 
db = None
cursor = None

def get_db_connection():
    global db, cursor
    if db is None:
        db = mysql.connector.connect(
            host="localhost",
            port=3306,
            user="root",
            password="root",
            database="skillstamp"
        )
        cursor = db.cursor(dictionary=True)
        ensure_certificate_columns(cursor, db)
        ensure_job_posting_columns(cursor, db)
        backfill_missing_cert_codes(cursor, db)
    return db, cursor

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/userlogin", methods=["GET", "POST"])
def userlogin():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        db, cursor = get_db_connection()
        cursor.execute("SELECT * FROM user WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user and user["password_hash"] and check_password_hash(user["password_hash"], password):
            session["user"] = user["name"]
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Invalid email or password")
    return render_template("login.html")

@app.route("/adminlogin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        try:
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "").strip()
            
            if not email or not password:
                return render_template("login.html", error="Email and password are required")
            
            db, cursor = get_db_connection()
            cursor.execute("SELECT * FROM user WHERE email = %s", (email,))
            user = cursor.fetchone()
            
            if not user:
                return render_template("login.html", error="Invalid email or password")
            
            # Check if user has admin role
            user_role = user.get("role", "").lower()
            if user_role != "admin":
                return render_template("login.html", error="This account is not an admin account. Please login with your appropriate account type.")
            
            # Verify password
            if not user.get("password_hash") or not check_password_hash(user["password_hash"], password):
                return render_template("login.html", error="Invalid email or password")
            
            # Set session
            session["admin"] = user["name"]
            session["user"] = user["name"]
            return redirect(url_for("admin_dashboard"))
        
        except Exception as e:
            return render_template("login.html", error=f"An error occurred: {str(e)}")
    
    return render_template("login.html")

@app.route("/recruiterlogin", methods=["GET", "POST"])
def recruiter_login():
    if request.method == "POST":
        try:
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "").strip()
            
            if not email or not password:
                return render_template("login.html", error="Email and password are required")
            
            db, cursor = get_db_connection()
            cursor.execute("SELECT * FROM user WHERE email = %s", (email,))
            user = cursor.fetchone()
            
            if not user:
                return render_template("login.html", error="Invalid email or password")
            
            # Check if user has recruiter role
            user_role = user.get("role", "").lower()
            if user_role != "recruiter":
                return render_template("login.html", error="This account is not a recruiter account. Please login as a regular user.")
            
            # Verify password
            if not user.get("password_hash") or not check_password_hash(user["password_hash"], password):
                return render_template("login.html", error="Invalid email or password")
            
            # Set session
            session["user"] = user["name"]
            session["recruiter"] = True
            return redirect(url_for("recruiter_dashboard"))
        
        except Exception as e:
            return render_template("login.html", error=f"An error occurred: {str(e)}")
    
    return render_template("login.html")

@app.route("/admin_dashboard")
def admin_dashboard():
    if "admin" in session:
        try:
            db, cursor = get_db_connection()
            # Fetch all certificates with student names
            cursor.execute("""
                SELECT c.certificate_id, c.user_id, u.name as student_name, u.email,
                       c.course_name, c.institution_id, i.name as institution_name,
                       c.issue_date, c.verification_status, c.certificate_file_path, c.cert_code
                FROM certificate c
                JOIN user u ON c.user_id = u.user_id
                LEFT JOIN institution i ON c.institution_id = i.institution_id
                ORDER BY c.certificate_id DESC
            """)
            certificates = cursor.fetchall()
            return render_template("dashboard.html", name=session["admin"], role="admin", 
                                 certificates=certificates, stats={}, jobs=[])
        except Exception as e:
            return render_template("dashboard.html", name=session["admin"], role="admin", 
                                 certificates=[], stats={}, jobs=[], error=str(e))
    return redirect(url_for("admin_login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "").strip()
            role = request.form.get("role", "student")
            
            if not name or not email or not password:
                return render_template("register.html", error="All fields are required")
            
            if role not in ["student", "recruiter", "admin"]:
                role = "student"

            hashed_pw = generate_password_hash(password)

            db, cursor = get_db_connection()
            cursor.execute("""
                INSERT INTO user 
                (name, email, password_hash, role)
                VALUES (%s, %s, %s, %s)
            """, (name, email, hashed_pw, role))
            db.commit()
            
            if role == "recruiter":
                return render_template("success.html", message="Recruiter account created successfully! Please log in.", link_url="/recruiterlogin", link_text="Go to Recruiter Login")
            elif role == "admin":
                return render_template("success.html", message="Admin account created successfully! Please log in.", link_url="/adminlogin", link_text="Go to Admin Login")
            else:
                return redirect(url_for("userlogin"))
        except mysql.connector.IntegrityError:
            return render_template("register.html", error="Email already exists. Please use a different email.")
        except Exception as e:
            return render_template("register.html", error=f"An error occurred: {str(e)}")

    return render_template("register.html")

@app.route("/recruiter-register", methods=["GET", "POST"])
def recruiter_register():
    """Dedicated recruiter registration route"""
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "").strip()
            company = request.form.get("company", "").strip()
            
            if not name or not email or not password:
                return render_template("register.html", error="Name, email, and password are required")
            
            hashed_pw = generate_password_hash(password)

            db, cursor = get_db_connection()
            cursor.execute("""
                INSERT INTO user 
                (name, email, password_hash, role)
                VALUES (%s, %s, %s, 'recruiter')
            """, (name, email, hashed_pw))
            db.commit()
            
            return render_template("success.html", 
                                 message="Recruiter account created successfully! You can now log in.",
                                 link_url="/recruiterlogin",
                                 link_text="Go to Recruiter Login")
        except mysql.connector.IntegrityError:
            return render_template("register.html", error="Email already exists. Please use a different email.")
        except Exception as e:
            return render_template("register.html", error=f"An error occurred: {str(e)}")

    return render_template("register.html", is_recruiter_register=True)

@app.route("/dashboard")
def dashboard():
    if "user" in session:
        try:
            db, cursor = get_db_connection()
            cursor.execute("SELECT user_id FROM user WHERE name = %s", (session["user"],))
            user = cursor.fetchone()

            recent_applications = []
            if user:
                cursor.execute("""
                    SELECT ja.application_id, ja.status, ja.applied_date, jp.title
                    FROM job_application ja
                    JOIN job_posting jp ON ja.job_id = jp.job_id
                    WHERE ja.user_id = %s
                    ORDER BY ja.applied_date DESC
                    LIMIT 5
                """, (user["user_id"],))
                recent_applications = cursor.fetchall()

            return render_template(
                "dashboard.html",
                name=session["user"],
                role="student",
                stats={},
                jobs=[],
                recent_applications=recent_applications
            )
        except Exception:
            return render_template(
                "dashboard.html",
                name=session["user"],
                role="student",
                stats={},
                jobs=[],
                recent_applications=[]
            )
    return redirect(url_for("userlogin"))

@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("admin", None)
    return redirect(url_for("home"))

@app.route("/addcertificate", methods=["GET", "POST"])
def addcertificate():
    if "user" not in session and "admin" not in session:
        return redirect(url_for("userlogin"))
    
    db, cursor = get_db_connection()
    cursor.execute("SELECT institution_id, name FROM institution ORDER BY name ASC")
    institutions = cursor.fetchall()
    
    if request.method == "POST":
        try:
            course_name = request.form.get("course_name")
            institution_name = request.form.get("institution_name")
            issue_date = request.form.get("issue_date")
            verification_status = "pending"
            cert_code = generate_unique_cert_code(cursor)
            certificate_file_path = None

            institution_id = None
            for institution in institutions:
                if institution["name"] == institution_name:
                    institution_id = institution["institution_id"]
                    break
            
            if institution_id is None:
                return render_template(
                    "addcertificate.html",
                    name=session.get("user", session.get("admin", "")),
                    institutions=institutions,
                    error="Please select a valid institution."
                )

            uploaded_file_obj = request.files.get("certificate_file")
            if not uploaded_file_obj or not uploaded_file_obj.filename:
                return render_template(
                    "addcertificate.html",
                    name=session.get("user", session.get("admin", "")),
                    institutions=institutions,
                    error="Please upload a certificate file (PDF, JPG, JPEG, or PNG)."
                )

            if not allowed_file(uploaded_file_obj.filename):
                return render_template(
                    "addcertificate.html",
                    name=session.get("user", session.get("admin", "")),
                    institutions=institutions,
                    error="Invalid file type. Please upload PDF, JPG, JPEG, or PNG."
                )

            safe_name = secure_filename(uploaded_file_obj.filename)
            unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}_{safe_name}"
            full_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
            uploaded_file_obj.save(full_path)
            certificate_file_path = f"uploads/{unique_name}"
            
            # Determine user_id based on session
            if "user" in session:
                cursor.execute("SELECT user_id FROM user WHERE name = %s", (session["user"],))
            else:
                cursor.execute("SELECT user_id FROM user WHERE email = %s", (session.get("admin", ""),))
            
            user = cursor.fetchone()
            
            if user:
                cursor.execute("""
                    INSERT INTO certificate 
                    (user_id, institution_id, course_name, issue_date, verification_status, cert_code, certificate_file_path)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    user["user_id"],
                    institution_id,
                    course_name,
                    issue_date,
                    verification_status,
                    cert_code,
                    certificate_file_path
                ))
                db.commit()
                return redirect(url_for("success"))
        except Exception as e:
            return f"An error occurred: {str(e)}"
    
    return render_template(
        "addcertificate.html",
        name=session.get("user", session.get("admin", "")),
        institutions=institutions
    )

@app.route("/issue", methods=["GET", "POST"])
def issue():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    db, cursor = get_db_connection()
    cursor.execute("SELECT institution_id, name FROM institution ORDER BY name ASC")
    institutions = cursor.fetchall()
    
    if request.method == "POST":
        try:
            email = request.form.get("email")
            course_name = request.form.get("course_name")
            institution_name = request.form.get("institution_name")
            issue_date = request.form.get("issue_date")

            institution_id = None
            for institution in institutions:
                if institution["name"] == institution_name:
                    institution_id = institution["institution_id"]
                    break

            if institution_id is None:
                return render_template("issue.html", institutions=institutions, error="Please select a valid institution.")

            # Get user ID by email
            cursor.execute("SELECT user_id FROM user WHERE email = %s", (email,))
            user = cursor.fetchone()
            
            if user:
                cursor.execute("""
                    INSERT INTO certificate 
                    (user_id, institution_id, course_name, issue_date, verification_status)
                    VALUES (%s, %s, %s, %s, %s)
                """, (user["user_id"], institution_id, course_name, issue_date, "verified"))
                db.commit()
                return redirect(url_for("success"))
            else:
                return "User not found with that email"
        except Exception as e:
            return f"An error occurred: {str(e)}"
    return render_template("issue.html", institutions=institutions)

@app.route("/verify", methods=["GET", "POST"])
def verify():
    if request.method == "POST":
        try:
            certificate_id = request.form.get("certificate_id")
            db, cursor = get_db_connection()
            cursor.execute("SELECT * FROM certificate WHERE certificate_id = %s", (certificate_id,))
            cert = cursor.fetchone()
            if cert:
                return render_template("verify.html", certificate=cert)
            else:
                return "Certificate not found"
        except Exception as e:
            return f"An error occurred: {str(e)}"
    return render_template("verify.html")

@app.route("/admin/verify-certificate/<int:certificate_id>", methods=["POST"])
def admin_verify_certificate(certificate_id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    
    try:
        verification_status = request.form.get("verification_status", "verified")
        db, cursor = get_db_connection()
        
        cursor.execute("""
            UPDATE certificate 
            SET verification_status = %s
            WHERE certificate_id = %s
        """, (verification_status, certificate_id))
        db.commit()
        
        return redirect(url_for("admin_dashboard"))
    except Exception as e:
        return f"An error occurred: {str(e)}"

@app.route("/success")
def success():
    return render_template("success.html")

@app.route("/mycertificates")
def mycertificates():
    if "user" not in session:
        return redirect(url_for("userlogin"))
    
    try:
        db, cursor = get_db_connection()
        
        # Get user_id
        cursor.execute("SELECT user_id FROM user WHERE name = %s", (session["user"],))
        user = cursor.fetchone()
        
        if not user:
            return "User not found", 404
        
        # Get all certificates for the user
        cursor.execute("""
            SELECT c.certificate_id, c.cert_code, c.certificate_file_path, c.course_name, c.issue_date, c.verification_status, i.name as institution_name
            FROM certificate c
            LEFT JOIN institution i ON c.institution_id = i.institution_id
            WHERE c.user_id = %s
            ORDER BY c.issue_date DESC
        """, (user["user_id"],))
        certificates = cursor.fetchall()

        # Backfill missing cert codes for existing rows so UI never shows None.
        updated = False
        for cert in certificates:
            if not cert.get("cert_code"):
                new_code = generate_unique_cert_code(cursor)
                cursor.execute(
                    "UPDATE certificate SET cert_code = %s WHERE certificate_id = %s",
                    (new_code, cert["certificate_id"])
                )
                cert["cert_code"] = new_code
                updated = True

        if updated:
            db.commit()
        
        return render_template("mycertificates.html", name=session["user"], certificates=certificates)
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

# ====== SKILLS MANAGEMENT ======
@app.route("/myskills")
def myskills():
    if "user" not in session:
        return redirect(url_for("userlogin"))
    
    try:
        # Get fresh connection and cursor
        db = mysql.connector.connect(
            host="localhost",
            port=3306,
            user="root",
            password="root",
            database="skillstamp"
        )
        cursor = db.cursor(dictionary=True)
        
        # Get user_id
        cursor.execute("SELECT user_id FROM user WHERE name = %s", (session["user"],))
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            db.close()
            return "User not found", 404
        
        # Get all skills for the user from user_skill joined with skill
        cursor.execute("""
            SELECT us.user_skill_id, s.skill_id, s.skill_name, us.experience_level, us.years_of_experience
            FROM user_skill us
            JOIN skill s ON us.skill_id = s.skill_id
            WHERE us.user_id = %s 
            ORDER BY us.user_skill_id DESC
        """, (user["user_id"],))
        skills = cursor.fetchall()
        
        cursor.close()
        db.close()
        
        return render_template("myskills.html", name=session["user"], skills=skills)
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

@app.route("/addskill", methods=["GET", "POST"])
def addskill():
    if "user" not in session:
        return redirect(url_for("userlogin"))
    
    if request.method == "POST":
        try:
            skill_name = " ".join(request.form.get("skill_name", "").strip().split())
            category = " ".join(request.form.get("category", "General").strip().split()) or "General"
            proficiency_level = request.form.get("proficiency_level", "intermediate")
            years_of_experience_raw = request.form.get("years_of_experience", "0").strip()
            
            if not skill_name:
                return "Skill name cannot be empty", 400
            
            try:
                years_of_experience = max(0, int(years_of_experience_raw or "0"))
            except ValueError:
                return render_template("addskill.html", name=session["user"], error="Years of experience must be a valid number")

            db, cursor = get_db_connection()
            
            # Get user_id
            cursor.execute("SELECT user_id FROM user WHERE name = %s", (session["user"],))
            user = cursor.fetchone()
            
            if not user:
                return "User not found", 404
            
            cursor.execute(
                "SELECT skill_id, skill_name FROM skill WHERE LOWER(TRIM(skill_name)) = LOWER(TRIM(%s))",
                (skill_name,)
            )
            skill = cursor.fetchone()
            
            if not skill:
                cursor.execute("""
                    INSERT INTO skill (skill_name, category, certification_required)
                    VALUES (%s, %s, 0)
                """, (skill_name, category))
                db.commit()
                cursor.execute("SELECT skill_id, skill_name FROM skill WHERE skill_name = %s", (skill_name,))
                skill = cursor.fetchone()

            if not skill:
                return render_template("addskill.html", name=session["user"], error="Failed to create skill")

            skill_id = skill["skill_id"]

            # Check if user already has this skill (prevent duplicate per user).
            cursor.execute(
                "SELECT user_skill_id FROM user_skill WHERE user_id = %s AND skill_id = %s",
                (user["user_id"], skill_id)
            )
            if cursor.fetchone():
                return render_template("addskill.html", name=session["user"], error=f"You already have the skill '{skill['skill_name']}'")
            
            # Insert into user_skill
            cursor.execute("""
                INSERT INTO user_skill (user_id, skill_id, experience_level, years_of_experience)
                VALUES (%s, %s, %s, %s)
            """, (user["user_id"], skill_id, proficiency_level, years_of_experience))
            db.commit()
            
            return redirect(url_for("myskills"))
        except mysql.connector.IntegrityError as ie:
            return render_template("addskill.html", name=session["user"], error="This skill already exists for your profile")
        except Exception as e:
            return render_template("addskill.html", name=session["user"], error=f"An error occurred: {str(e)}")
    
    return render_template("addskill.html", name=session["user"])

@app.route("/deleteskill/<int:skill_id>", methods=["POST"])
def deleteskill(skill_id):
    if "user" not in session:
        return redirect(url_for("userlogin"))
    
    try:
        db, cursor = get_db_connection()
        
        # Get user_id
        cursor.execute("SELECT user_id FROM user WHERE name = %s", (session["user"],))
        user = cursor.fetchone()
        
        if not user:
            return "User not found", 404
        
        # Verify the user_skill belongs to the user before deleting
        cursor.execute("""
            DELETE FROM user_skill 
            WHERE user_skill_id = %s AND user_id = %s
        """, (skill_id, user["user_id"]))
        db.commit()
        
        return redirect(url_for("myskills"))
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

# ====== JOB MANAGEMENT ======
@app.route("/postjob", methods=["GET", "POST"])
def postjob():
    if "user" not in session:
        return redirect(url_for("recruiter_login"))
    
    db, cursor = get_db_connection()
    
    # Verify user is a recruiter
    cursor.execute("SELECT user_id, role FROM user WHERE name = %s", (session["user"],))
    user = cursor.fetchone()
    
    if not user:
        return "User not found", 404
    
    if user.get("role", "").lower() != "recruiter":
        return "Unauthorized. Only recruiters can post jobs.", 403
    
    if request.method == "POST":
        try:
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            location = request.form.get("location", "").strip()
            job_type = request.form.get("job_type", "Full-time")
            salary_range = request.form.get("salary_range", "").strip()
            required_skills = request.form.get("required_skills", "").strip()
            deadline = request.form.get("deadline", "")
            
            if not title or not description:
                return "Title and description are required", 400
            
            # Insert job posting
            cursor.execute("""
                INSERT INTO job_posting (user_id, title, description, location, job_type, salary_range, required_skills, deadline, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (user["user_id"], title, description, location, job_type, salary_range, required_skills, deadline, "active"))
            db.commit()
            
            return redirect(url_for("recruiter_dashboard"))
        except Exception as e:
            return f"An error occurred: {str(e)}", 500
    
    return render_template("postjob.html", name=session["user"])

@app.route("/recruiter_dashboard")
def recruiter_dashboard():
    if "user" not in session:
        return redirect(url_for("recruiter_login"))
    
    try:
        db, cursor = get_db_connection()
        
        # Get user_id and verify role
        cursor.execute("SELECT user_id, role FROM user WHERE name = %s", (session["user"],))
        user = cursor.fetchone()
        
        if not user:
            return "User not found", 404
        
        if user.get("role", "").lower() != "recruiter":
            return "Unauthorized. This page is for recruiters only.", 403
        
        # Get jobs posted by this recruiter
        cursor.execute("""
            SELECT job_id, title, description, location, job_type, posted_date, deadline, status
            FROM job_posting
            WHERE user_id = %s
            ORDER BY posted_date DESC
        """, (user["user_id"],))
        jobs = cursor.fetchall()
        
        # Get statistics
        cursor.execute("""
            SELECT COUNT(*) as total_jobs FROM job_posting WHERE user_id = %s
        """, (user["user_id"],))
        stats_jobs = cursor.fetchone()
        
        cursor.execute("""
            SELECT COUNT(*) as total_applications 
            FROM job_application ja
            JOIN job_posting jp ON ja.job_id = jp.job_id
            WHERE jp.user_id = %s
        """, (user["user_id"],))
        stats_apps = cursor.fetchone()
        
        cursor.execute("""
            SELECT COUNT(*) as active_jobs FROM job_posting WHERE user_id = %s AND status = 'active'
        """, (user["user_id"],))
        stats_active = cursor.fetchone()
        
        cursor.execute("""
            SELECT COUNT(*) as pending_applications 
            FROM job_application ja
            JOIN job_posting jp ON ja.job_id = jp.job_id
            WHERE jp.user_id = %s AND ja.status = 'pending'
        """, (user["user_id"],))
        stats_pending = cursor.fetchone()
        
        stats = {
            "total_jobs": stats_jobs["total_jobs"] if stats_jobs else 0,
            "total_applications": stats_apps["total_applications"] if stats_apps else 0,
            "active_jobs": stats_active["active_jobs"] if stats_active else 0,
            "pending_applications": stats_pending["pending_applications"] if stats_pending else 0
        }
        
        return render_template("dashboard.html", name=session["user"], role="recruiter", jobs=jobs, stats=stats)
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

# ====== JOB APPLICATIONS ======
@app.route("/jobs")
def jobs():
    """Display all available jobs for users to apply"""
    try:
        # Get fresh connection and cursor
        db = mysql.connector.connect(
            host="localhost",
            port=3306,
            user="root",
            password="root",
            database="skillstamp"
        )
        cursor = db.cursor(dictionary=True)
        
        # Get all active jobs with salary information
        cursor.execute("""
            SELECT jp.job_id, jp.title, jp.description, jp.location, jp.job_type, 
                   jp.posted_date, jp.deadline, jp.salary_range, jp.required_skills, u.name as recruiter_name
            FROM job_posting jp
            JOIN user u ON jp.user_id = u.user_id
            WHERE jp.status = 'active'
            ORDER BY jp.posted_date DESC
        """)
        jobs_list = cursor.fetchall()
        
       
        applied_jobs = []
        if "user" in session:
            cursor.execute("SELECT user_id FROM user WHERE name = %s", (session["user"],))
            user = cursor.fetchone()
            if user:
                cursor.execute("""
                    SELECT job_id FROM job_application WHERE user_id = %s
                """, (user["user_id"],))
                applied = cursor.fetchall()
                applied_jobs = [job["job_id"] for job in applied]
        
        cursor.close()
        db.close()
        
        return render_template("jobs.html", jobs=jobs_list, applied_jobs=applied_jobs, 
                             name=session.get("user", None))
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

@app.route("/applyjob/<int:job_id>", methods=["GET", "POST"])
def applyjob(job_id):
    if "user" not in session:
        return redirect(url_for("userlogin"))
    
    try:
        db, cursor = get_db_connection()
        
        # Get user_id
        cursor.execute("SELECT user_id FROM user WHERE name = %s", (session["user"],))
        user = cursor.fetchone()
        
        if not user:
            return "User not found", 404
        
        # Check if user already applied
        cursor.execute("""
            SELECT application_id FROM job_application WHERE job_id = %s AND user_id = %s
        """, (job_id, user["user_id"]))
        
        if cursor.fetchone():
            return "You have already applied for this job", 400
        
        if request.method == "POST":
            try:
                # Insert application
                cursor.execute("""
                    INSERT INTO job_application (job_id, user_id, status)
                    VALUES (%s, %s, 'pending')
                """, (job_id, user["user_id"]))
                db.commit()
                
                return redirect(url_for("myapplications"))
            except Exception as e:
                return f"An error occurred: {str(e)}", 500
        
        # GET request - show job details
        cursor.execute("""
            SELECT jp.job_id, jp.title, jp.description, jp.location, jp.job_type, 
                   jp.posted_date, jp.deadline, jp.salary_range, jp.required_skills, u.name as recruiter_name
            FROM job_posting jp
            JOIN user u ON jp.user_id = u.user_id
            WHERE jp.job_id = %s AND jp.status = 'active'
        """, (job_id,))
        job = cursor.fetchone()
        
        if not job:
            return "Job not found", 404
        
        return render_template("applyjob.html", name=session["user"], job=job)
    
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

@app.route("/myapplications")
def myapplications():
    if "user" not in session:
        return redirect(url_for("userlogin"))
    
    try:
        # Get fresh connection and cursor
        db = mysql.connector.connect(
            host="localhost",
            port=3306,
            user="root",
            password="root",
            database="skillstamp"
        )
        cursor = db.cursor(dictionary=True)
        
        # Get user_id
        cursor.execute("SELECT user_id FROM user WHERE name = %s", (session["user"],))
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            db.close()
            return "User not found", 404
        
        # Get all applications for this user
        cursor.execute("""
            SELECT ja.application_id, ja.status, ja.applied_date, 
                   jp.job_id, jp.title, jp.location, jp.salary_range, jp.required_skills, u.name as recruiter_name
            FROM job_application ja
            JOIN job_posting jp ON ja.job_id = jp.job_id
            JOIN user u ON jp.user_id = u.user_id
            WHERE ja.user_id = %s
            ORDER BY ja.applied_date DESC
        """, (user["user_id"],))
        applications = cursor.fetchall()
        
        cursor.close()
        db.close()
        
        return render_template("myapplications.html", name=session["user"], applications=applications)
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

@app.route("/jobapplications/<int:job_id>")
def jobapplications(job_id):
    if "user" not in session:
        return redirect(url_for("userlogin"))
    
    try:
        db, cursor = get_db_connection()
        
        # Get recruiter_id
        cursor.execute("SELECT user_id FROM user WHERE name = %s", (session["user"],))
        recruiter = cursor.fetchone()
        
        if not recruiter:
            return "User not found", 404
        
        # Verify job belongs to recruiter
        cursor.execute("""
            SELECT job_id FROM job_posting WHERE job_id = %s AND user_id = %s
        """, (job_id, recruiter["user_id"]))
        
        if not cursor.fetchone():
            return "Unauthorized", 403
        
        # Get all applications for this job with applicant skills and certificates
        cursor.execute("""
            SELECT ja.application_id, ja.status, ja.applied_date,
                   u.user_id, u.name, u.email
            FROM job_application ja
            JOIN user u ON ja.user_id = u.user_id
            WHERE ja.job_id = %s
            ORDER BY ja.applied_date DESC
        """, (job_id,))
        applications = cursor.fetchall()
        
        # For each applicant, get their skills and certificates
        for app in applications:
            cursor.execute("""
                SELECT s.skill_name, us.experience_level FROM user_skill us
                JOIN skill s ON us.skill_id = s.skill_id
                WHERE us.user_id = %s
            """, (app["user_id"],))
            skills_result = cursor.fetchall()
            app["skills"] = skills_result if skills_result else []
            
            cursor.execute("""
                SELECT c.certificate_id, c.course_name, c.institution_id, i.name as institution_name,
                       c.issue_date, c.verification_status
                FROM certificate c
                LEFT JOIN institution i ON c.institution_id = i.institution_id
                WHERE c.user_id = %s
            """, (app["user_id"],))
            certs_result = cursor.fetchall()
            app["certificates"] = certs_result if certs_result else []
        
        # Get job details
        cursor.execute("""
            SELECT title, location, job_type FROM job_posting WHERE job_id = %s
        """, (job_id,))
        job = cursor.fetchone()
        
        return render_template("jobapplications.html", name=session["user"], 
                             job=job, applications=applications, job_id=job_id)
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

@app.route("/recruiter_candidates")
def recruiter_candidates():
    if "user" not in session:
        return redirect(url_for("userlogin"))
    
    try:
        db, cursor = get_db_connection()
        
        # Get recruiter_id
        cursor.execute("SELECT user_id FROM user WHERE name = %s", (session["user"],))
        recruiter = cursor.fetchone()
        
        if not recruiter:
            return "User not found", 404
        
        # Get all job applications for jobs posted by this recruiter with candidate details
        cursor.execute("""
            SELECT DISTINCT u.user_id, u.name, u.email
            FROM job_application ja
            JOIN job_posting jp ON ja.job_id = jp.job_id
            JOIN user u ON ja.user_id = u.user_id
            WHERE jp.user_id = %s
            ORDER BY u.name
        """, (recruiter["user_id"],))
        candidates = cursor.fetchall()
        
        # For each candidate, get their skills and certificates
        for candidate in candidates:
            cursor.execute("""
                SELECT s.skill_name, us.experience_level FROM user_skill us
                JOIN skill s ON us.skill_id = s.skill_id
                WHERE us.user_id = %s
            """, (candidate["user_id"],))
            skills_result = cursor.fetchall()
            candidate["skills"] = skills_result if skills_result else []
            
            cursor.execute("""
                SELECT c.certificate_id, c.course_name, c.institution_id, i.name as institution_name,
                       c.issue_date, c.verification_status
                FROM certificate c
                LEFT JOIN institution i ON c.institution_id = i.institution_id
                WHERE c.user_id = %s
                ORDER BY issue_date DESC
            """, (candidate["user_id"],))
            certs_result = cursor.fetchall()
            candidate["certificates"] = certs_result if certs_result else []
        
        return render_template("recruiter_candidates.html", name=session["user"], 
                             candidates=candidates)
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

@app.route("/updateapplicationstatus/<int:application_id>/<status>", methods=["POST"])
def updateapplicationstatus(application_id, status):
    if "user" not in session:
        return redirect(url_for("userlogin"))
    
    if status not in ["pending", "accepted", "rejected"]:
        return "Invalid status", 400
    
    try:
        db, cursor = get_db_connection()
        
        # Get recruiter_id
        cursor.execute("SELECT user_id FROM user WHERE name = %s", (session["user"],))
        recruiter = cursor.fetchone()
        
        if not recruiter:
            return "User not found", 404
        
        # Verify the application belongs to recruiter's job
        cursor.execute("""
            SELECT ja.application_id FROM job_application ja
            JOIN job_posting jp ON ja.job_id = jp.job_id
            WHERE ja.application_id = %s AND jp.user_id = %s
        """, (application_id, recruiter["user_id"]))
        
        if not cursor.fetchone():
            return "Unauthorized", 403
        
        # Update status
        cursor.execute("""
            UPDATE job_application SET status = %s WHERE application_id = %s
        """, (status, application_id))
        db.commit()
        
        return redirect(request.referrer or url_for("recruiter_dashboard"))
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True)
