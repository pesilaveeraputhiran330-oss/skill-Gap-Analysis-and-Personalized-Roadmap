from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)
import pymysql
import bcrypt
import pandas as pd
import os
import re


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)
app.secret_key = "skillnavigator123"


# =========================================================
# DATABASE CONNECTION
# =========================================================

db = pymysql.connect(
    host="localhost",
    user="root",
    password="root21",
    database="skillnavigator",
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=False
)


# =========================================================
# CSV PATH
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "career_roles_skills.csv")


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def normalize_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).lower()


# =========================================================
# LOGGED USER NAME
# =========================================================

@app.context_processor
def inject_logged_user():

    if "user_id" in session:

        username = session.get("username", "")

        if username:
            return {
                "logged_user_name": username
            }

    return {
        "logged_user_name": "User"
    }


# =========================================================
# GET CAREER ROLES FROM CSV
# =========================================================

def get_career_roles():

    if not os.path.exists(CSV_PATH):
        return []

    try:

        df = pd.read_csv(CSV_PATH)

        if "Career Role" not in df.columns:
            return []

        roles = []

        for role in df["Career Role"].dropna():

            role = str(role).strip()

            if role:
                roles.append(role)

        unique_roles = {}

        for role in roles:
            key = normalize_text(role)

            if key not in unique_roles:
                unique_roles[key] = role

        return sorted(unique_roles.values())

    except Exception as e:

        print("Error reading career roles:", e)

        return []


# =========================================================
# SYNC CAREER SKILLS FROM CSV TO DATABASE
# =========================================================

def sync_career_skills():

    if not os.path.exists(CSV_PATH):
        print("CSV file not found:", CSV_PATH)
        return

    try:

        df = pd.read_csv(CSV_PATH)

        if "Career Role" not in df.columns or "Skill" not in df.columns:
            print("CSV must contain Career Role and Skill columns")
            return

        cursor = db.cursor()

        for _, row in df.iterrows():

            career_role = str(row["Career Role"]).strip()
            skill_name = str(row["Skill"]).strip()

            if not career_role or not skill_name:
                continue

            cursor.execute(
                """
                SELECT id
                FROM career_skills
                WHERE LOWER(TRIM(career_role)) = LOWER(TRIM(%s))
                AND LOWER(TRIM(skill_name)) = LOWER(TRIM(%s))
                LIMIT 1
                """,
                (career_role, skill_name)
            )

            existing = cursor.fetchone()

            if not existing:

                cursor.execute(
                    """
                    INSERT INTO career_skills
                    (career_role, skill_name)
                    VALUES (%s, %s)
                    """,
                    (career_role, skill_name)
                )

        db.commit()

        print("Career skills synced successfully.")

    except Exception as e:

        db.rollback()

        print("Error syncing career skills:", e)


# =========================================================
# CREATE PROFILE TABLE
# =========================================================

def create_profile_table():

    cursor = db.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS profile (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            full_name VARCHAR(150),
            age INT,
            gender VARCHAR(50),
            user_category VARCHAR(100),
            qualification VARCHAR(150),
            skills TEXT,
            career_interest VARCHAR(150) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY unique_user_profile (user_id)
        )
        """
    )

    db.commit()


# =========================================================
# CREATE CAREER PREFERENCES TABLE
# =========================================================

def create_career_preferences_table():

    cursor = db.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS career_preferences (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            career_role VARCHAR(150),
            current_skills TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY unique_user_career (user_id)
        )
        """
    )

    db.commit()


# =========================================================
# CREATE CAREER SKILLS TABLE
# =========================================================

def create_career_skills_table():

    cursor = db.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS career_skills (
            id INT AUTO_INCREMENT PRIMARY KEY,
            career_role VARCHAR(150) NOT NULL,
            skill_name VARCHAR(150) NOT NULL,
            UNIQUE KEY unique_career_skill
            (career_role, skill_name)
        )
        """
    )

    db.commit()


# =========================================================
# CREATE ANALYSIS TABLE
# =========================================================

def create_analysis_table():

    cursor = db.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            career_role VARCHAR(150),
            current_skills TEXT,
            required_skills TEXT,
            matched_skills TEXT,
            missing_skills TEXT,
            match_percentage FLOAT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    db.commit()

    # Check match_percentage column

    cursor.execute(
        """
        SHOW COLUMNS FROM analysis LIKE 'match_percentage'
        """
    )

    column = cursor.fetchone()

    if not column:

        cursor.execute(
            """
            ALTER TABLE analysis
            ADD COLUMN match_percentage FLOAT DEFAULT 0
            """
        )

        db.commit()


# =========================================================
# CREATE ALL TABLES
# =========================================================

def create_all_tables():

    create_profile_table()
    create_career_preferences_table()
    create_career_skills_table()
    create_analysis_table()


# =========================================================
# SAVE ANALYSIS
# =========================================================

def save_analysis(user_id, analysis):

    try:

        cursor = db.cursor()

        required_skills = ", ".join(
            analysis["required_skills"]
        )

        matched_skills = ", ".join(
            analysis["matched_skills"]
        )

        missing_skills = ", ".join(
            analysis["missing_skills"]
        )

        cursor.execute(
            """
            INSERT INTO analysis
            (
                user_id,
                career_role,
                current_skills,
                required_skills,
                matched_skills,
                missing_skills,
                match_percentage
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                analysis["career_role"],
                analysis["current_skills"],
                required_skills,
                matched_skills,
                missing_skills,
                analysis["match_percentage"]
            )
        )

        db.commit()

    except Exception as e:

        db.rollback()

        print("Error saving analysis:", e)


# =========================================================
# CALCULATE SKILL ANALYSIS
# =========================================================

def calculate_skill_analysis(user_id):

    cursor = db.cursor()

    # Get user's career preference

    cursor.execute(
        """
        SELECT career_role, current_skills
        FROM career_preferences
        WHERE user_id = %s
        LIMIT 1
        """,
        (user_id,)
    )

    preference = cursor.fetchone()

    if not preference:
        return None

    career_role = preference["career_role"]
    current_skills_text = preference["current_skills"] or ""

    if not career_role:
        return None

    # Get required skills

    cursor.execute(
        """
        SELECT skill_name
        FROM career_skills
        WHERE LOWER(TRIM(career_role))
        = LOWER(TRIM(%s))
        ORDER BY skill_name
        """,
        (career_role,)
    )

    rows = cursor.fetchall()

    required_skills = [
        row["skill_name"]
        for row in rows
        if row["skill_name"]
    ]

    # Split current skills

    current_skills = [
        skill.strip()
        for skill in re.split(
            r"[,;\n]+",
            current_skills_text
        )
        if skill.strip()
    ]

    # Normalize current skills

    current_skill_keys = {
        normalize_text(skill)
        for skill in current_skills
    }

    matched_skills = []
    missing_skills = []

    for skill in required_skills:

        if normalize_text(skill) in current_skill_keys:

            matched_skills.append(skill)

        else:

            missing_skills.append(skill)

    # Calculate percentage

    if required_skills:

        match_percentage = round(
            (len(matched_skills) / len(required_skills)) * 100,
            2
        )

    else:

        match_percentage = 0

    return {
        "career_role": career_role,
        "current_skills": ", ".join(current_skills),
        "required_skills": required_skills,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "match_percentage": match_percentage
    }


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template("index.html")


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

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

        # Validation

        if not username or not email or not password:

            flash(
                "Please fill all required fields.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if password != confirm_password:

            flash(
                "Passwords do not match.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        email_pattern = r"[^@\s]+@[^@\s]+\.[^@\s]+"

        if not re.match(email_pattern, email):

            flash(
                "Invalid email address.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        try:

            cursor = db.cursor()

            # Check username

            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE username = %s
                LIMIT 1
                """,
                (username,)
            )

            if cursor.fetchone():

                flash(
                    "Username already exists.",
                    "error"
                )

                return redirect(
                    url_for("register")
                )

            # Check email

            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE email = %s
                LIMIT 1
                """,
                (email,)
            )

            if cursor.fetchone():

                flash(
                    "Email already exists.",
                    "error"
                )

                return redirect(
                    url_for("register")
                )

            hashed_password = bcrypt.hashpw(
                password.encode("utf-8"),
                bcrypt.gensalt()
            )

            cursor.execute(
                """
                INSERT INTO users
                (
                    username,
                    email,
                    mobile,
                    password
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    username,
                    email,
                    mobile,
                    hashed_password
                )
            )

            db.commit()

            flash(
                "Registration successful!",
                "success"
            )

            return redirect(
                url_for("login")
            )

        except Exception as e:

            db.rollback()

            print("Registration error:", e)

            flash(
                "Registration failed!",
                "error"
            )

            return redirect(
                url_for("register")
            )

    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        try:

            cursor = db.cursor()

            cursor.execute(
                """
                SELECT *
                FROM users
                WHERE username = %s
                LIMIT 1
                """,
                (username,)
            )

            user = cursor.fetchone()

            if user:

                stored_password = user["password"]

                if isinstance(
                    stored_password,
                    str
                ):
                    stored_password = stored_password.encode(
                        "utf-8"
                    )

                password_valid = bcrypt.checkpw(
                    password.encode("utf-8"),
                    stored_password
                )

                if password_valid:

                    session["user_id"] = user["id"]
                    session["username"] = user["username"]
                    session["email"] = user.get("email", "")
                    session["mobile"] = user.get("mobile", "")

                    return redirect(
                        url_for("dashboard")
                    )

            flash(
                "Invalid username or password.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        except Exception as e:

            print("Login error:", e)

            flash(
                "Login failed.",
                "error"
            )

            return redirect(
                url_for("login")
            )

    return render_template(
        "login.html"
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    try:

        cursor = db.cursor()

        # =====================================================
        # TOTAL USERS WHO COMPLETED PROFILE
        # =====================================================

        cursor.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS profile_count
            FROM profile
            """
        )

        profile_result = cursor.fetchone()

        profile_count = profile_result["profile_count"] or 0


        # =====================================================
        # TOTAL USERS WHO SELECTED CAREER
        # =====================================================

        cursor.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS career_count
            FROM career_preferences
            """
        )

        career_result = cursor.fetchone()

        career_count = career_result["career_count"] or 0


        # =====================================================
        # TOTAL UNIQUE USERS WHO COMPLETED SKILL ANALYSIS
        # =====================================================

        cursor.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS skills_count
            FROM analysis
            """
        )

        skills_result = cursor.fetchone()

        skills_count = skills_result["skills_count"] or 0


        # =====================================================
        # CLOSE CURSOR
        # =====================================================

        cursor.close()


        # =====================================================
        # SEND DATA TO DASHBOARD
        # =====================================================

        return render_template(
            "dashboard.html",

            username=session.get(
                "username",
                "User"
            ),

            profile_count=profile_count,

            career_count=career_count,

            skills_count=skills_count
        )


    except Exception as e:

        print(
            "Dashboard statistics error:",
            e
        )

        return render_template(
            "dashboard.html",

            username=session.get(
                "username",
                "User"
            ),

            profile_count=0,

            career_count=0,

            skills_count=0
        )


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile", methods=["GET", "POST"])
def profile():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    user_id = session["user_id"]

    if request.method == "POST":

        full_name = request.form.get(
            "full_name",
            ""
        ).strip()

        age = request.form.get(
            "age",
            ""
        ).strip()

        gender = request.form.get(
            "gender",
            ""
        ).strip()

        user_category = request.form.get(
            "user_category",
            ""
        ).strip()

        qualification = request.form.get(
            "qualification",
            ""
        ).strip()

        skills = request.form.get(
            "skills",
            ""
        ).strip()

        career_interest = request.form.get(
            "career_interest",
            ""
        ).strip()

        roles = get_career_roles()

        role_keys = {
            normalize_text(role)
            for role in roles
        }

        if normalize_text(career_interest) not in role_keys:

            flash(
                "Please select a valid career interest.",
                "error"
            )

            return redirect(
                url_for("career")
            )

        try:

            cursor = db.cursor()

            cursor.execute(
                """
                SELECT id
                FROM profile
                WHERE user_id = %s
                LIMIT 1
                """,
                (user_id,)
            )

            existing = cursor.fetchone()

            if existing:

                cursor.execute(
                    """
                    UPDATE profile
                    SET
                        full_name = %s,
                        age = %s,
                        gender = %s,
                        user_category = %s,
                        qualification = %s,
                        skills = %s,
                        career_interest = %s
                    WHERE user_id = %s
                    """,
                    (
                        full_name,
                        age if age else None,
                        gender,
                        user_category,
                        qualification,
                        skills,
                        career_interest,
                        user_id
                    )
                )

            else:

                cursor.execute(
                    """
                    INSERT INTO profile
                    (
                        user_id,
                        full_name,
                        age,
                        gender,
                        user_category,
                        qualification,
                        skills,
                        career_interest
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        full_name,
                        age if age else None,
                        gender,
                        user_category,
                        qualification,
                        skills,
                        career_interest
                    )
                )

            db.commit()

            flash(
                "Profile saved successfully.",
                "success"
            )

            return redirect(
                url_for("career")
            )

        except Exception as e:

            db.rollback()

            print("Profile error:", e)

            flash(
                "Profile update failed.",
                "error"
            )

    try:

        cursor = db.cursor()

        cursor.execute(
            """
            SELECT *
            FROM profile
            WHERE user_id = %s
            LIMIT 1
            """,
            (user_id,)
        )

        profile_data = cursor.fetchone()

    except Exception as e:

        print("Profile fetch error:", e)

        profile_data = None

    return render_template(
        "profile.html",
        profile=profile_data,
        career_roles=get_career_roles()
    )


# =========================================================
# CAREER ROLE
# =========================================================

@app.route("/career", methods=["GET", "POST"])
def career():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    user_id = session["user_id"]

    roles = get_career_roles()

    if request.method == "POST":

        career_role = request.form.get(
            "career_role",
            ""
        ).strip()

        current_skills = request.form.get(
            "current_skills",
            ""
        ).strip()

        role_keys = {
            normalize_text(role)
            for role in roles
        }

        if normalize_text(career_role) not in role_keys:

            flash(
                "Please select a valid career role.",
                "error"
            )

            return redirect(
                url_for(
                    "skill_match",
                    show_error=1
                )
            )

        try:

            cursor = db.cursor()

            cursor.execute(
                """
                SELECT id
                FROM career_preferences
                WHERE user_id = %s
                LIMIT 1
                """,
                (user_id,)
            )

            existing = cursor.fetchone()

            if existing:

                cursor.execute(
                    """
                    UPDATE career_preferences
                    SET
                        career_role = %s,
                        current_skills = %s
                    WHERE user_id = %s
                    """,
                    (
                        career_role,
                        current_skills,
                        user_id
                    )
                )

            else:

                cursor.execute(
                    """
                    INSERT INTO career_preferences
                    (
                        user_id,
                        career_role,
                        current_skills
                    )
                    VALUES (%s, %s, %s)
                    """,
                    (
                        user_id,
                        career_role,
                        current_skills
                    )
                )

            db.commit()

            flash(
                "Career preference saved successfully.",
                "success"
            )

            return redirect(
                url_for("skill_match")
            )

        except Exception as e:

            db.rollback()

            print("Career error:", e)

            flash(
                "Career preference update failed.",
                "error"
            )

    try:

        cursor = db.cursor()

        cursor.execute(
            """
            SELECT *
            FROM career_preferences
            WHERE user_id = %s
            LIMIT 1
            """,
            (user_id,)
        )

        career_data = cursor.fetchone()

    except Exception as e:

        print("Career fetch error:", e)

        career_data = None

    return render_template(
        "career.html",
        username=session.get("username", "User"),
        career_roles=roles,
        career=career_data,
        show_error=request.args.get("show_error")
    )


# =========================================================
# SKILL GAP
# =========================================================

@app.route("/skill_gap")
def skill_gap():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    user_id = session["user_id"]

    analysis = calculate_skill_analysis(
        user_id
    )

    if not analysis:

        return redirect(
            url_for(
                "career",
                show_error=1
            )
        )

    save_analysis(
        user_id,
        analysis
    )

    skill_gap_percentage = 100 - analysis["match_percentage"]
    

    return render_template(
        "skill_gap.html",
        analysis=analysis,
        career_role=analysis["career_role"],
        current_skills=analysis["current_skills"],
        required_skills=analysis["required_skills"],
        matched_skills=analysis["matched_skills"],
        missing_skills=analysis["missing_skills"],
        match_percentage=analysis["match_percentage"],
        skill_gap_percentage=skill_gap_percentage
    )


# =========================================================
# SKILL MATCH
# =========================================================

@app.route("/skill-match")
@app.route("/skill_match")
def skill_match():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    user_id = session["user_id"]

    analysis = calculate_skill_analysis(
        user_id
    )

    if not analysis:

        return redirect(
            url_for(
                "career",
                show_error=1
            )
        )

    save_analysis(
        user_id,
        analysis
    )

    return render_template(
        "skill_match.html",
        analysis=analysis,
        career_role=analysis["career_role"],
        current_skills=analysis["current_skills"],
        required_skills=analysis["required_skills"],
        matched_skills=analysis["matched_skills"],
        missing_skills=analysis["missing_skills"],
        match_percentage=analysis["match_percentage"]
    )


# =========================================================
# SKILL ROADMAP DATA
# =========================================================

def get_skill_roadmap(skill):

    roadmap_data = {

        "python": {
            "level": "Beginner to Intermediate",
            "topics": [
                "Python Basics",
                "Variables and Data Types",
                "Functions",
                "OOP Concepts",
                "File Handling",
                "Exception Handling",
                "Libraries"
            ],
            "duration": "2-3 Weeks"
        },

        "sql": {
            "level": "Beginner to Intermediate",
            "topics": [
                "SQL Basics",
                "SELECT Queries",
                "WHERE and ORDER BY",
                "JOINs",
                "GROUP BY",
                "Subqueries",
                "Database Design"
            ],
            "duration": "2 Weeks"
        },

        "mysql": {
            "level": "Beginner to Intermediate",
            "topics": [
                "MySQL Basics",
                "Tables",
                "CRUD Operations",
                "Keys",
                "Joins",
                "Indexes",
                "Database Management"
            ],
            "duration": "2 Weeks"
        },

        "machine learning": {
            "level": "Intermediate",
            "topics": [
                "ML Basics",
                "Supervised Learning",
                "Unsupervised Learning",
                "Regression",
                "Classification",
                "Clustering",
                "Model Evaluation"
            ],
            "duration": "3-4 Weeks"
        },

        "deep learning": {
            "level": "Intermediate to Advanced",
            "topics": [
                "Neural Networks",
                "Activation Functions",
                "Backpropagation",
                "CNN",
                "RNN",
                "Model Training"
            ],
            "duration": "4-5 Weeks"
        },

        "pandas": {
            "level": "Beginner to Intermediate",
            "topics": [
                "Series",
                "DataFrame",
                "Data Cleaning",
                "Filtering",
                "Grouping",
                "Data Analysis"
            ],
            "duration": "1-2 Weeks"
        },

        "numpy": {
            "level": "Beginner to Intermediate",
            "topics": [
                "Arrays",
                "Indexing",
                "Slicing",
                "Mathematical Operations",
                "Statistics"
            ],
            "duration": "1 Week"
        },

        "data visualization": {
            "level": "Intermediate",
            "topics": [
                "Charts",
                "Matplotlib",
                "Seaborn",
                "Data Storytelling",
                "Dashboard Design"
            ],
            "duration": "1-2 Weeks"
        },

        "html": {
            "level": "Beginner",
            "topics": [
                "HTML Basics",
                "Tags",
                "Forms",
                "Tables",
                "Semantic HTML"
            ],
            "duration": "1 Week"
        },

        "css": {
            "level": "Beginner to Intermediate",
            "topics": [
                "Selectors",
                "Box Model",
                "Flexbox",
                "Grid",
                "Responsive Design",
                "Animations"
            ],
            "duration": "1-2 Weeks"
        },

        "javascript": {
            "level": "Beginner to Intermediate",
            "topics": [
                "Variables",
                "Functions",
                "DOM",
                "Events",
                "Arrays",
                "Objects",
                "Fetch API"
            ],
            "duration": "2-3 Weeks"
        },

        "flask": {
            "level": "Intermediate",
            "topics": [
                "Flask Basics",
                "Routes",
                "Templates",
                "Jinja",
                "Forms",
                "Sessions",
                "Database Connectivity"
            ],
            "duration": "2-3 Weeks"
        },

        "java": {
            "level": "Beginner to Intermediate",
            "topics": [
                "Java Basics",
                "OOP",
                "Classes",
                "Inheritance",
                "Exception Handling",
                "Collections"
            ],
            "duration": "3 Weeks"
        },

        "c++": {
            "level": "Beginner to Intermediate",
            "topics": [
                "C++ Basics",
                "OOP",
                "Pointers",
                "STL",
                "Functions",
                "Classes"
            ],
            "duration": "3 Weeks"
        },

        "git": {
            "level": "Beginner",
            "topics": [
                "Git Basics",
                "Repositories",
                "Commit",
                "Branch",
                "Merge",
                "Push and Pull"
            ],
            "duration": "1 Week"
        },

        "github": {
            "level": "Beginner",
            "topics": [
                "Repositories",
                "Branches",
                "Pull Requests",
                "Issues",
                "Collaboration"
            ],
            "duration": "1 Week"
        },

        "docker": {
            "level": "Intermediate",
            "topics": [
                "Containers",
                "Images",
                "Dockerfile",
                "Docker Compose",
                "Container Management"
            ],
            "duration": "2 Weeks"
        },

        "kubernetes": {
            "level": "Advanced",
            "topics": [
                "Pods",
                "Services",
                "Deployments",
                "ConfigMaps",
                "Namespaces",
                "Scaling"
            ],
            "duration": "3-4 Weeks"
        },

        "aws": {
            "level": "Intermediate",
            "topics": [
                "AWS Basics",
                "EC2",
                "S3",
                "IAM",
                "RDS",
                "Cloud Deployment"
            ],
            "duration": "3 Weeks"
        },

        "linux": {
            "level": "Beginner to Intermediate",
            "topics": [
                "Linux Commands",
                "File System",
                "Permissions",
                "Processes",
                "Shell Scripting"
            ],
            "duration": "2 Weeks"
        },

        "power bi": {
            "level": "Beginner to Intermediate",
            "topics": [
                "Power BI Basics",
                "Data Import",
                "Data Cleaning",
                "Visualizations",
                "Dashboards",
                "Reports"
            ],
            "duration": "2 Weeks"
        },

        "excel": {
            "level": "Beginner to Intermediate",
            "topics": [
                "Excel Basics",
                "Formulas",
                "Functions",
                "Pivot Tables",
                "Charts",
                "Data Analysis"
            ],
            "duration": "1-2 Weeks"
        }
    }

    key = normalize_text(skill)

    if key in roadmap_data:

        return roadmap_data[key]

    return {
        "level": "Intermediate",
        "topics": [
            f"Introduction to {skill}",
            f"Basic concepts of {skill}",
            f"Practical usage of {skill}",
            f"Projects using {skill}",
            f"Advanced concepts of {skill}"
        ],
        "duration": "2-3 Weeks"
    }


# =========================================================
# GENERATE PERSONALIZED ROADMAP
# =========================================================

def generate_personalized_roadmap(analysis):

    roadmap = []

    missing_skills = analysis.get(
        "missing_skills",
        []
    )

    # Saved roadmap progress from session
    saved_progress = session.get(
        "roadmap_progress",
        {}
    )

    for index, skill in enumerate(
        missing_skills,
        start=1
    ):

        roadmap_info = get_skill_roadmap(skill)

        # Use skill name as unique key
        skill_key = str(skill).strip().lower()

        completed_topics = saved_progress.get(
            skill_key,
            []
        )

        # Make sure only valid topics are kept
        completed_topics = [
            topic
            for topic in completed_topics
            if topic in roadmap_info["topics"]
        ]

        total_topics = len(
            roadmap_info["topics"]
        )

        completed_count = len(
            completed_topics
        )

        # Calculate percentage
        if total_topics > 0:
            progress = round(
                (completed_count / total_topics) * 100
            )
        else:
            progress = 0

        roadmap.append(
            {
                "step": index,
                "skill": skill,
                "level": roadmap_info["level"],
                "topics": roadmap_info["topics"],
                "duration": roadmap_info["duration"],

                # IMPORTANT
                "completed_topics": completed_topics,
                "completed_count": completed_count,
                "progress": progress
            }
        )

    return roadmap

# =========================================================
# ROADMAP
# =========================================================

@app.route("/roadmap")
def roadmap():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    user_id = session["user_id"]

    analysis = calculate_skill_analysis(
        user_id
    )

    if not analysis:

        return redirect(
            url_for("career", show_error=1)
        )

    roadmap_data = generate_personalized_roadmap(
        analysis
    )

    # Overall learning progress
    total_topics = 0
    completed_topics = 0

    for step in roadmap_data:

        total_topics += len(
            step["topics"]
        )

        completed_topics += len(
            step["completed_topics"]
        )

    if total_topics > 0:

        overall_progress = round(
            (completed_topics / total_topics) * 100
        )

    else:

        overall_progress = 0

    return render_template(
        "roadmap.html",

        analysis=analysis,

        roadmap=roadmap_data,

        career_role=analysis["career_role"],

        current_skills=analysis["current_skills"],

        required_skills=analysis["required_skills"],

        matched_skills=analysis["matched_skills"],

        missing_skills=analysis["missing_skills"],

        total_skills=len(
            analysis["required_skills"]
        ),

        matched_count=len(
            analysis["matched_skills"]
        ),

        missing_count=len(
            analysis["missing_skills"]
        ),

        match_percentage=analysis["match_percentage"],

        # Overall roadmap progress
        total_topics=total_topics,

        completed_topics=completed_topics,

        overall_progress=overall_progress
    )

    # =========================================================
# SAVE ROADMAP TOPIC PROGRESS
# =========================================================

@app.route(
    "/roadmap/progress",
    methods=["POST"]
)
def save_roadmap_progress():

    if "user_id" not in session:

        return {
            "success": False,
            "message": "Login required"
        }, 401

    data = request.get_json(
        silent=True
    ) or {}

    skill = str(
        data.get("skill", "")
    ).strip()

    completed_topics = data.get(
        "completed_topics",
        []
    )

    if not skill:

        return {
            "success": False,
            "message": "Skill is required"
        }, 400

    if not isinstance(
        completed_topics,
        list
    ):

        return {
            "success": False,
            "message": "Invalid topics"
        }, 400

    # Existing session data
    roadmap_progress = session.get(
        "roadmap_progress",
        {}
    )

    skill_key = skill.lower()

    # Save completed topics
    roadmap_progress[
        skill_key
    ] = completed_topics

    session[
        "roadmap_progress"
    ] = roadmap_progress

    session.modified = True

    # Calculate progress
    total_topics = len(
        completed_topics
    )

    # We need actual total from roadmap data
    roadmap_info = get_skill_roadmap(
        skill
    )

    total_available = len(
        roadmap_info["topics"]
    )

    if total_available > 0:

        progress = round(
            (
                total_topics
                /
                total_available
            ) * 100
        )

    else:

        progress = 0

    return {
        "success": True,
        "skill": skill,
        "completed_count": total_topics,
        "total_topics": total_available,
        "progress": progress
    }


# =========================================================
# REPORT
# =========================================================

@app.route("/report")
def report():

    # -----------------------------------------------------
    # LOGIN CHECK
    # -----------------------------------------------------

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    cursor = None

    try:

        cursor = db.cursor(pymysql.cursors.DictCursor)

        # =================================================
        # USER + PROFILE DETAILS
        # =================================================

        cursor.execute(
            """
            SELECT
                u.username,
                p.full_name,
                p.user_category,
                p.qualification
            FROM users u
            LEFT JOIN profile p
                ON u.id = p.user_id
            WHERE u.id = %s
            LIMIT 1
            """,
            (user_id,)
        )

        user = cursor.fetchone()

        if not user:
            cursor.close()
            return redirect(url_for("login"))

        username = user.get("username")

        full_name = user.get("full_name")

        user_category = user.get("user_category")

        qualification = user.get("qualification")


        # =================================================
        # LATEST ANALYSIS
        # =================================================

        cursor.execute(
            """
            SELECT *
            FROM analysis
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
        )

        analysis = cursor.fetchone()


        # -------------------------------------------------
        # NO ANALYSIS FOUND
        # -------------------------------------------------

        if not analysis:

            cursor.close()

            return redirect(
                url_for(
                    "career",
                    show_error=1
                )
            )


        # =================================================
        # CAREER ROLE
        # =================================================

        career_role = analysis.get("career_role")


        # =================================================
        # ANALYSIS DATE
        # =================================================

        analysis_date = analysis.get("created_at")

        if analysis_date:
            analysis_date = analysis_date.strftime("%d-%m-%Y")


        # =================================================
        # REQUIRED SKILLS
        # =================================================

        required_skills_raw = (
            analysis.get("required_skills") or ""
        )


        # =================================================
        # MATCHED SKILLS
        # =================================================

        matched_skills_raw = (
            analysis.get("matched_skills") or ""
        )


        # =================================================
        # MISSING SKILLS
        # =================================================

        missing_skills_raw = (
            analysis.get("missing_skills") or ""
        )


        # =================================================
        # CONVERT CSV -> LIST
        # =================================================

        required_skills = [
            skill.strip()
            for skill in required_skills_raw.split(",")
            if skill.strip()
        ]

        matched_skills = [
            skill.strip()
            for skill in matched_skills_raw.split(",")
            if skill.strip()
        ]

        missing_skills = [
            skill.strip()
            for skill in missing_skills_raw.split(",")
            if skill.strip()
        ]


        # =================================================
        # SKILL COUNTS
        # =================================================

        total_skills = len(required_skills)

        matched_count = len(matched_skills)

        missing_count = len(missing_skills)


                # =================================================
        # LEARNING ROADMAP PROGRESS
        # =================================================

        roadmap_data = generate_personalized_roadmap(
            {
                "missing_skills": missing_skills
            }
        )

        total_topics = 0
        completed_topics = 0

        for step in roadmap_data:

            total_topics += len(
                step["topics"]
            )

            completed_topics += len(
                step["completed_topics"]
            )

        if total_topics > 0:

            overall_progress = round(
                (completed_topics / total_topics) * 100
            )

        else:

            overall_progress = 0


        # =================================================
        # MATCH PERCENTAGE
        # =================================================

        if total_skills > 0:

            match_percentage = round(
                (matched_count / total_skills) * 100
            )

        else:

            match_percentage = 0


        # =================================================
        # CAREER READINESS
        # =================================================

        if match_percentage >= 80:

            readiness = "Excellent"

            match_status = "Excellent Career Alignment"

            alignment_message = (
                "You are strongly aligned with your career path"
            )

            alignment_description = (
                "Your current skills show excellent alignment "
                "with the recommended career path."
            )

            readiness_description = (
                "Excellent progress"
            )


        elif match_percentage >= 60:

            readiness = "Good"

            match_status = "Good Career Alignment"

            alignment_message = (
                "You are on the right track"
            )

            alignment_description = (
                "Your current skills show strong alignment "
                "with your recommended career path."
            )

            readiness_description = (
                "Keep improving"
            )


        elif match_percentage >= 40:

            readiness = "Intermediate"

            match_status = "Moderate Career Alignment"

            alignment_message = (
                "You are making good progress"
            )

            alignment_description = (
                "Your current skills have moderate alignment "
                "with your recommended career path."
            )

            readiness_description = (
                "More improvement needed"
            )


        else:

            readiness = "Beginner"

            match_status = (
                "Career Alignment Needs Improvement"
            )

            alignment_message = (
                "You have skills to develop"
            )

            alignment_description = (
                "Focus on the missing skills to improve "
                "your alignment with the recommended career path."
            )

            readiness_description = (
                "Focus on skill development"
            )


        # =================================================
        # SKILL DESCRIPTIONS
        # =================================================

        if matched_count > 0:

            matched_skills_description = (
                f"{matched_count} skill"
                if matched_count == 1
                else f"{matched_count} skills"
            )

            matched_skills_description += " matched"

        else:

            matched_skills_description = "No matched skills yet"


        if missing_count > 0:

            skills_to_improve_description = (
                "Focus required"
            )

        else:

            skills_to_improve_description = (
                "No major gaps"
            )


        # =================================================
        # CAREER INSIGHT
        # =================================================

        if match_percentage >= 80:

            report_insight = (
                f"Your profile is well aligned with "
                f"{career_role}. Continue strengthening your "
                "existing skills and explore advanced topics."
            )

        elif match_percentage >= 60:

            report_insight = (
                f"You have a good foundation for "
                f"{career_role}. Focus on the remaining "
                "skill gaps to become more career-ready."
            )

        elif match_percentage >= 40:

            report_insight = (
                f"You have started building the skills needed "
                f"for {career_role}. Follow the learning roadmap "
                "to improve your career alignment."
            )

        else:

            report_insight = (
                f"Your current skill alignment with "
                f"{career_role} is still developing. "
                "Prioritize the missing skills and follow "
                "the recommended learning roadmap."
            )


        # =================================================
        # CLOSE CURSOR
        # =================================================

        cursor.close()


        # =================================================
        # REPORT TEMPLATE
        # =================================================

        return render_template(

            "report.html",

            # -----------------------------
            # USER DETAILS
            # -----------------------------

            username=username,

            full_name=full_name,

            user_category=user_category,

            qualification=qualification,


            # -----------------------------
            # CAREER DETAILS
            # -----------------------------

            career_role=career_role,

            analysis_date=analysis_date,


            # -----------------------------
            # RESULT
            # -----------------------------

            match_percentage=match_percentage,

            match_status=match_status,

            alignment_message=alignment_message,

            alignment_description=alignment_description,


            # -----------------------------
            # MATCHED SKILLS
            # -----------------------------

            matched_skills=matched_skills,

            matched_skills_description=(
                matched_skills_description
            ),


            # -----------------------------
            # MISSING SKILLS
            # -----------------------------

            skills_to_improve=missing_count,

            skills_to_improve_description=(
                skills_to_improve_description
            ),

            improvement_skills=missing_skills,


            # -----------------------------
            # READINESS
            # -----------------------------

            readiness=readiness,

            readiness_description=(
                readiness_description
            ),


            # -----------------------------
            # STRENGTHS
            # -----------------------------

            strengths=matched_skills,


            # -----------------------------
            # INSIGHT
            # -----------------------------

            report_insight=report_insight,

            # -----------------------------
            # LEARNING PROGRESS
            # -----------------------------

            total_topics=total_topics,

            completed_topics=completed_topics,

            overall_progress=overall_progress,

        )


    except Exception as e:

        print(
            "REPORT ERROR:",
            repr(e)
        )

        try:
            if cursor:
                cursor.close()
        except:
            pass

        flash(
            "Unable to generate career report.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )

# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    create_all_tables()

    sync_career_skills()

    print(
        "Career roles:",
        len(get_career_roles())
    )

    print(
        "CSV Path:",
        CSV_PATH
    )

    app.run(
        debug=True
    )