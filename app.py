import csv
import io
from flask import make_response

from email_validator import validate_email, EmailNotValidError

import phonenumbers
from phonenumbers import NumberParseException

from datetime import date, timedelta

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    make_response
)

from flask_wtf.csrf import CSRFProtect

from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)

from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

import os
import sqlite3
import smtplib

from email.message import EmailMessage


# ==========================================
# LOAD ENVIRONMENT VARIABLES
# ==========================================

load_dotenv()


app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is not configured."
    )

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)

csrf = CSRFProtect(app)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv(
         "FLASK_ENV",
         "development"
    ) . lower() == "production"
)

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "admin_login"

login_manager.session_protection = "strong"

# ==========================================
# EMAIL SETTINGS
# ==========================================

MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_RECEIVER = os.getenv("MAIL_RECEIVER")

print("MAIL_USERNAME:", MAIL_USERNAME)
print("MAIL_RECEIVER:", MAIL_RECEIVER)
print("MAIL_PASSWORD loaded:", bool(MAIL_PASSWORD))

# ==========================================
# DATABASE
# ==========================================

DATABASE = "lena_techs.db"

def whatsapp_number(phone):

    if not phone:
        return ""
    return phone.replace("+", "").replace(" ", "")


def get_db():

    connection = sqlite3.connect(DATABASE)

    connection.row_factory = sqlite3.Row

    return connection

class Admin(UserMixin):

    def __init__(
        self,
        admin_id,
        username,
        password
    ):

        self.id = admin_id

        self.username = username

        self.password = password

@login_manager.user_loader
def load_user(admin_id):

    connection = get_db()

    admin = connection.execute(
        """
        SELECT *
        FROM admins
        WHERE id = ?
        """,
        (admin_id,)
    ).fetchone()

    connection.close()

    if admin:

        return Admin(
            admin["id"],
            admin["username"],
            admin["password"]
        )

    return None

@app.after_request
def add_security_headers(response):

    response.headers["X-Content-Type-Options"] = "nosniff"

    response.headers["X-Frame-Options"] = "SAMEORIGIN"

    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    return response


def create_database():

    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS enquiries (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            email TEXT NOT NULL,

            company TEXT,

            service TEXT,

            message TEXT,

            status TEXT DEFAULT 'New',

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS admins (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL

        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS enquiry_notes (

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enquiry_id INTEGER NOT NULL,
            note TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (enquiry_id) REFERENCES enquiries(id)
        )
    """)

 # Add follow-up fields if they do not already exist

    try:
        connection.execute("""
            ALTER TABLE enquiries
            ADD COLUMN follow_up_date TEXT
        """)
    except sqlite3.OperationalError:
        pass

    try:
        connection.execute("""
            ALTER TABLE enquiries
            ADD COLUMN follow_up_note TEXT
        """)
    except sqlite3.OperationalError:
        pass

    try:
        connection.execute("""
            ALTER TABLE enquiries
            ADD COLUMN phone TEXT
        """)
    except sqlite3.OperationalError:
        pass

    try:
       connection.execute("""
           ALTER TABLE enquiries
           ADD COLUMN priority TEXT DEFAULT 'Medium'
        """)
    except sqlite3.OperationalError:
        pass

    connection.commit()

    connection.close()


# ==========================================
# SEND EMAIL
# ==========================================

def send_email(name, email, phone, company, service, message):

    if not MAIL_USERNAME or not MAIL_PASSWORD or not MAIL_RECEIVER:
        return False

    email_message = EmailMessage()

    email_message["Subject"] = (
        f"New Lena Techs Project Enquiry - {name}"
    )

    email_message["From"] = MAIL_USERNAME

    email_message["To"] = MAIL_RECEIVER

    email_message["Reply-To"] = email

    email_message.set_content(f"""
NEW PROJECT ENQUIRY
===================

Name:
{name}

Email:
{email}

Phone / WhatsApp:
{phone}

Company / Business:
{company}

Service Required:
{service}

Project Description:
{message}

===================
Lena Techs Website
""")


    try:

        with smtplib.SMTP(
            "smtp.gmail.com",
            587
        ) as server:

            server.starttls()

            server.login(
                MAIL_USERNAME,
                MAIL_PASSWORD
            )

            server.send_message(
                email_message
            )

        return True

    except Exception as error:

        print("Email error:", error)

        return False


# ==========================================
# HOME PAGE
# ==========================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# ==========================================
# CONTACT / QUOTATION FORM
# ==========================================

@app.route(
    "/contact",
    methods=["POST"]
)
def contact():

    website = request.form.get("website", "").strip()

    if website:
        flash(
            "Your request could not be submitted.",
            "error"
        )
        return redirect(url_for("home") + "#contact")

    name = request.form.get(
        "name",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip()

    try:
        valid_email = validate_email(email)
        email = valid_email.normalized
    except EmailNotValidError:
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("home") + "#contact")

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    company = request.form.get(
        "company",
        ""
    ).strip()

    if phone:
        try:
            parsed_phone = phonenumbers.parse(
                phone,
                None
            )

            if not phonenumbers.is_valid_number(parsed_phone):
                flash(
                    "Please enter a valid phone number.",
                    "error"
                )
                return redirect(
                    url_for("home") + "#contact"
                )

            phone = phonenumbers.format_number(
                parsed_phone,
                phonenumbers.PhoneNumberFormat.E164
            )

        except NumberParseException:
            flash(
                "Please enter a valid phone number.",
                "error"
            )
            return redirect(
                url_for("home") + "#contact"
            )

    service = request.form.get(
        "service",
        ""
    ).strip()

    message = request.form.get(
        "message",
        ""
    ).strip()


    # -----------------------------
    # BASIC VALIDATION
    # -----------------------------

    if not name or not email or not message:

        flash(
            "Please complete all required fields.",
            "error"
        )

        return redirect(
            url_for("home") + "#contact"
        )


    # -----------------------------
    # SAVE TO DATABASE
    # -----------------------------

    connection = get_db()

    connection.execute(
        """
        INSERT INTO enquiries
        (name, email, phone, company, service, message)

        VALUES (?, ?, ?, ?, ?, ?)
        """,

        (
            name,
            email,
            phone,
            company,
            service,
            message
        )
    )

    connection.commit()

    connection.close()


    # -----------------------------
    # SEND EMAIL
    # -----------------------------

    email_sent = send_email(
        name,
        email,
        phone,
        company,
        service,
        message
    )


    if email_sent:

        flash(
            "Thank you! Your project request has been sent successfully.",
            "success"
        )

    else:

        flash(
            "Your request was received. Email notifications are currently being configured.",
            "success"
        )


    return redirect(
        url_for("home") + "#contact"
    )

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if current_user.is_authenticated:

        return redirect(
            url_for("admin_dashboard")
        )


    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )


        connection = get_db()

        admin = connection.execute(
            """
            SELECT *
            FROM admins
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

        connection.close()


        if admin and check_password_hash(
            admin["password"],
            password
        ):

            user = Admin(
                admin["id"],
                admin["username"],
                admin["password"]
            )

            login_user(user, remember=False)

            return redirect(
                url_for("admin_dashboard")
            )


        flash(
            "Invalid username or password.",
            "error"
        )


    return render_template(
        "admin_login.html"
    )

@app.route("/admin")
@login_required
def admin_dashboard():

    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()

    connection = get_db()

    query = """
        SELECT *
        FROM enquiries
        WHERE 1 = 1
    """

    parameters = []

    # Search
    if search:

        query += """
            AND (
                name LIKE ?
                OR email LIKE ?
                OR company LIKE ?
                OR service LIKE ?
                OR message LIKE ?
            )
        """

        search_value = f"%{search}%"

        parameters.extend([
            search_value,
            search_value,
            search_value,
            search_value,
            search_value
        ])

    # Status filter
    if status_filter:

        query += """
            AND status = ?
        """

        parameters.append(status_filter)

    query += """
        ORDER BY created_at DESC
    """

    enquiries = connection.execute(
        query,
        parameters
    ).fetchall()

    follow_ups = connection.execute(
       """
       SELECT *
       FROM enquiries
       WHERE follow_up_date IS NOT NULL
       AND follow_up_date != ''
       ORDER BY follow_up_date ASC
       """
    ).fetchall()

    total_enquiries = connection.execute(
        """
        SELECT COUNT(*)
        FROM enquiries
        """
    ).fetchone()[0]

    new_enquiries = connection.execute(
        """
        SELECT COUNT(*)
        FROM enquiries
        WHERE status = 'New'
        """
    ).fetchone()[0]

    contacted_enquiries = connection.execute(
        """
        SELECT COUNT(*)
        FROM enquiries
        WHERE status = 'Contacted'
        """
    ).fetchone()[0]

    quoted_enquiries = connection.execute(
        """
        SELECT COUNT(*)
        FROM enquiries
        WHERE status = 'Quoted'
        """
    ).fetchone()[0]

    in_progress_enquiries = connection.execute(
        """
        SELECT COUNT(*)
        FROM enquiries
        WHERE status = 'In Progress'
       """
    ).fetchone()[0]

    completed_enquiries = connection.execute(
       """
       SELECT COUNT(*)
       FROM enquiries
       WHERE status = 'Completed'
       """
    ).fetchone()[0]

    if total_enquiries > 0:
        new_percentage = (new_enquiries * 100) / total_enquiries
        contacted_percentage = (contacted_enquiries * 100) / total_enquiries
        quoted_percentage = (quoted_enquiries * 100) / total_enquiries
        in_progress_percentage = (in_progress_enquiries * 100) / total_enquiries
        completed_percentage = (completed_enquiries * 100) / total_enquiries
    else:
        new_percentage = 0
        contacted_percentage = 0
        quoted_percentage = 0
        in_progress_percentage = 0
        completed_percentage = 0

    connection.close()

    return render_template(
    "admin_dashboard.html",
    enquiries=enquiries,
    follow_ups=follow_ups,

    total_enquiries=total_enquiries,
    new_enquiries=new_enquiries,
    contacted_enquiries=contacted_enquiries,
    quoted_enquiries=quoted_enquiries,
    in_progress_enquiries=in_progress_enquiries,
    completed_enquiries=completed_enquiries,

    new_percentage=new_percentage,
    contacted_percentage=contacted_percentage,
    quoted_percentage=quoted_percentage,
    in_progress_percentage=in_progress_percentage,
    completed_percentage=completed_percentage,

    search=search,
    status_filter=status_filter
)

@app.route("/admin/export-enquiries")
@login_required
def export_enquiries():

    connection = get_db()

    enquiries = connection.execute(
        """
        SELECT
            id,
            name,
            email,
            phone,
            company,
            service,
            message,
            status,
            follow_up_date,
            follow_up_note,
            created_at
        FROM enquiries
        ORDER BY created_at DESC
        """
    ).fetchall()

    connection.close()

    output = io.StringIO()

    writer = csv.writer(output)

    output.write("\ufeff") 

    writer.writerow([
        "ID",
        "Name",
        "Email",
        "Phone",
        "Company",
        "Service",
        "Message",
        "Status",
        "Follow-up Date", 
        "Follow-up Note",
        "Created At"
    ])

    for enquiry in enquiries:

        writer.writerow([
            enquiry["id"],
            enquiry["name"],
            enquiry["email"],
            enquiry["phone"],
            enquiry["company"],
            enquiry["service"],
            enquiry["message"],
            enquiry["status"],
            enquiry["follow_up_date"],
            enquiry["follow_up_note"],
            enquiry["created_at"]
        ])

    response = make_response(
        output.getvalue()
    )

    response.headers["Content-Disposition"] = (
        "attachment; filename=lena_techs_enquiries.csv"
    )

    response.headers["Content-Type"] = (
        "text/csv; charset=utf-8"
    )

    return response

@app.route("/admin/backup-database")
@login_required
def backup_database():

    if not os.path.exists(DATABASE):
        flash(
            "Database file could not be found.",
            "error"
        )
        return redirect(
            url_for("admin_dashboard")
        )

    with open(DATABASE, "rb") as database_file:
        database_data = database_file.read()

    response = make_response(
        database_data
    )

    response.headers["Content-Type"] = (
        "application/octet-stream"
    )

    response.headers["Content-Disposition"] = (
        "attachment; filename=lena_techs_backup.db"
    )

    return response


@app.route("/admin/enquiry/<int:enquiry_id>/status", methods=["POST"])
@login_required
def update_enquiry_status(enquiry_id):

    status = request.form.get("status", "").strip()

    allowed_statuses = [
        "New",
        "Contacted",
        "Quoted",
        "In Progress",
        "Completed"
    ]

    if status not in allowed_statuses:
        flash("Invalid enquiry status.", "admin_error")
        return redirect(url_for("admin_dashboard"))

    connection = get_db()

    connection.execute(
        """
        UPDATE enquiries
        SET status = ?
        WHERE id = ?
        """,
        (status, enquiry_id)
    )

    connection.commit()
    connection.close()

    flash(
        "Enquiry status updated successfully.",
        "admin_success"
    )

    return redirect(url_for("admin_dashboard"))

@app.route(
    "/admin/enquiry/<int:enquiry_id>/priority",
    methods=["POST"]
)
@login_required
def update_enquiry_priority(enquiry_id):

    priority = request.form.get(
        "priority",
        ""
    ).strip()

    allowed_priorities = [
        "High",
        "Medium",
        "Low"
    ]

    if priority not in allowed_priorities:
        flash(
            "Invalid enquiry priority.",
            "admin_error"
        )
        return redirect(
            url_for(
                "enquiry_details",
                enquiry_id=enquiry_id
            )
        )

    connection = get_db()

    enquiry = connection.execute(
        """
        SELECT id
        FROM enquiries
        WHERE id = ?
        """,
        (enquiry_id,)
    ).fetchone()

    if not enquiry:
        connection.close()

        flash(
            "Enquiry not found.",
            "admin_error"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    connection.execute(
        """
        UPDATE enquiries
        SET priority = ?
        WHERE id = ?
        """,
        (
            priority,
            enquiry_id
        )
    )

    connection.commit()
    connection.close()

    flash(
        "Enquiry priority updated successfully.",
        "admin_success"
    )

    return redirect(
        url_for(
            "enquiry_details",
            enquiry_id=enquiry_id
        )
    )

@app.route("/admin/enquiry/<int:enquiry_id>")
@login_required
def enquiry_details(enquiry_id):

    connection = get_db()

    enquiry = connection.execute(
        """
        SELECT *
        FROM enquiries
        WHERE id = ?
        """,
        (enquiry_id,)
    ).fetchone()

    if not enquiry:
        connection.close()

        flash(
            "Enquiry not found.",
            "admin_error"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    notes = connection.execute(
        """
        SELECT *
        FROM enquiry_notes
        WHERE enquiry_id = ?
        ORDER BY created_at DESC
        """,
        (enquiry_id,)
    ).fetchall()

    connection.close()

    return render_template(
        "enquiry_details.html",
        enquiry=enquiry,
        notes=notes,
        current_date=date.today().isoformat(),
        whatsapp_number=whatsapp_number
    )
@app.route(
    "/admin/enquiry/<int:enquiry_id>/notes",
    methods=["POST"]
)
@login_required
def add_enquiry_note(enquiry_id):

    note = request.form.get("note", "").strip()

    if not note:
        flash(
            "Please enter a note before saving.",
            "admin_error"
        )

        return redirect(
            url_for(
                "enquiry_details",
                enquiry_id=enquiry_id
            )
        )

    connection = get_db()

    enquiry = connection.execute(
        """
        SELECT id
        FROM enquiries
        WHERE id = ?
        """,
        (enquiry_id,)
    ).fetchone()

    if not enquiry:
        connection.close()

        flash(
            "Enquiry not found.",
            "admin_error"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    connection.execute(
        """
        INSERT INTO enquiry_notes
        (enquiry_id, note)
        VALUES (?, ?)
        """,
        (enquiry_id, note)
    )

    connection.commit()
    connection.close()

    flash(
        "Internal note saved successfully.",
        "admin_success"
    )

    return redirect(
        url_for(
            "enquiry_details",
            enquiry_id=enquiry_id
        )
    )
@app.route(
    "/admin/enquiry/<int:enquiry_id>/follow-up",
    methods=["POST"]
)
@login_required
def set_follow_up(enquiry_id):

    follow_up_date = request.form.get(
        "follow_up_date",
        ""
    ).strip()

    follow_up_note = request.form.get(
        "follow_up_note",
        ""
    ).strip()

    if not follow_up_date or not follow_up_note:
        flash(
            "Please provide both a follow-up date and reminder.",
            "admin_error"
        )

        return redirect(
            url_for(
                "enquiry_details",
                enquiry_id=enquiry_id
            )
        )

    connection = get_db()

    enquiry = connection.execute(
        """
        SELECT id
        FROM enquiries
        WHERE id = ?
        """,
        (enquiry_id,)
    ).fetchone()

    if not enquiry:
        connection.close()

        flash(
            "Enquiry not found.",
            "admin_error"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    connection.execute(
        """
        UPDATE enquiries
        SET follow_up_date = ?,
            follow_up_note = ?
        WHERE id = ?
        """,
        (
            follow_up_date,
            follow_up_note,
            enquiry_id
        )
    )

    connection.commit()
    connection.close()

    flash(
        "Follow-up scheduled successfully.",
        "admin_success"
    )

    return redirect(
        url_for(
            "enquiry_details",
            enquiry_id=enquiry_id
        )
    )


@app.route(
    "/admin/enquiry/<int:enquiry_id>/reply",
    methods=["POST"]
)
@login_required
def reply_to_client(enquiry_id):

    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()

    if not subject or not message:
        flash(
            "Please enter both a subject and message.",
            "admin_error"
        )

        return redirect(
            url_for(
                "enquiry_details",
                enquiry_id=enquiry_id
            )
        )

    connection = get_db()

    enquiry = connection.execute(
        """
        SELECT *
        FROM enquiries
        WHERE id = ?
        """,
        (enquiry_id,)
    ).fetchone()

    connection.close()

    if not enquiry:
        flash(
            "Enquiry not found.",
            "admin_error"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    if not MAIL_USERNAME or not MAIL_PASSWORD:
        flash(
            "Email service is not configured.",
            "admin_error"
        )

        return redirect(
            url_for(
                "enquiry_details",
                enquiry_id=enquiry_id
            )
        )

    email_message = EmailMessage()

    email_message["Subject"] = subject
    email_message["From"] = MAIL_USERNAME
    email_message["To"] = enquiry["email"]
    email_message["Reply-To"] = MAIL_USERNAME

    email_message.set_content(
        f"""
Hello {enquiry["name"]},

{message}

Kind regards,

Lena Techs
Software Development & Digital Solutions
0796 456 070
lenatechsolution@gmail.com
"""
    )

    try:

        with smtplib.SMTP(
            "smtp.gmail.com",
            587
        ) as server:

            server.starttls()

            server.login(
                MAIL_USERNAME,
                MAIL_PASSWORD
            )

            server.send_message(
                email_message
            )

        flash(
            "Reply sent successfully to the client.",
            "admin_success"
        )

    except Exception as error:

        print("Reply email error:", error)

        flash(
            "Unable to send the reply. Please try again.",
            "error"
        )

    return redirect(
        url_for(
            "enquiry_details",
            enquiry_id=enquiry_id
        )
    )


@app.route("/admin/enquiry/<int:enquiry_id>/delete", methods=["POST"])
@login_required
def delete_enquiry(enquiry_id):

    connection = get_db()

    enquiry = connection.execute(
        """
        SELECT *
        FROM enquiries
        WHERE id = ?
        """,
        (enquiry_id,)
    ).fetchone()

    if not enquiry:
        connection.close()

        flash(
            "Enquiry not found.",
            "admin_error"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    connection.execute(
        """
        DELETE FROM enquiries
        WHERE id = ?
        """,
        (enquiry_id,)
    )

    connection.commit()
    connection.close()

    flash(
        "Enquiry deleted successfully.",
        "admin_success"
    )

    return redirect(
        url_for("admin_dashboard")
    )


@app.route("/admin/logout")
@login_required
def admin_logout():

    logout_user()

    return redirect(
        url_for("admin_login")
    )

@app.errorhandler(404)
def page_not_found(error):

    return render_template(
        "404.html"
    ), 404

@app.errorhandler(500)
def internal_server_error(error):
    return render_template("500.html"), 500

# ==========================================
# RUN APPLICATION
# ==========================================

if __name__ == "__main__":

    create_database()

    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    app.run(
        debug=debug_mode
    )