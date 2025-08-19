import os
import base64
import hashlib
import hmac
import sqlite3
from datetime import date
import streamlit as st
import pandas as pd

# ------------------------
# App config
# ------------------------
try:
    st.set_page_config(
        page_title="Lite CRM",
        page_icon="📇",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass

DB_PATH = "lite_crm.db"

# ------------------------
# Password Hashing Helpers (PBKDF2, no external deps)
# ------------------------
PBKDF_ALG = "sha256"
PBKDF_ITER = 120_000
SALT_BYTES = 16
KEY_LEN = 32

def hash_password(password: str) -> str:
    salt = os.urandom(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(PBKDF_ALG, password.encode("utf-8"), salt, PBKDF_ITER, dklen=KEY_LEN)
    return f"pbkdf2${PBKDF_ALG}${PBKDF_ITER}$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()

def check_password(password: str, stored: str) -> bool:
    try:
        _, alg, iters, salt_b64, dk_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        dk = hashlib.pbkdf2_hmac(alg, password.encode("utf-8"), salt, int(iters), dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False

# ------------------------
# Database Setup
# ------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Users
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Companies
    c.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            industry TEXT,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Contacts
    c.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            company_id INTEGER,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Deals
    c.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            company_id INTEGER,
            contact_id INTEGER,
            stage TEXT DEFAULT 'New',        -- New, Qualified, Proposal, Negotiation, Closed Won, Closed Lost
            amount REAL DEFAULT 0,
            close_date TEXT,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Tasks
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            status TEXT DEFAULT 'Open',      -- Open, In Progress, Done
            priority TEXT DEFAULT 'Medium',  -- Low, Medium, High
            related_type TEXT,               -- Company, Contact, Deal
            related_id INTEGER,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ------------------------
# Auth
# ------------------------
def any_user_exists() -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM users LIMIT 1")
    exists = c.fetchone() is not None
    conn.close()
    return exists

def create_user(name, email, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    pw_hash = hash_password(password)
    try:
        c.execute("INSERT INTO users (name,email,password_hash) VALUES (?,?,?)", (name, email.lower().strip(), pw_hash))
        conn.commit()
    except sqlite3.IntegrityError:
        return False, "User already exists"
    finally:
        conn.close()
    return True, "Account created"

def login_user(email, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id,name,password_hash FROM users WHERE email=?", (email.lower().strip(),))
    row = c.fetchone()
    conn.close()
    if row and check_password(password, row[2]):
        return {"id": row[0], "name": row[1], "email": email}
    return None

def logout_user():
    st.session_state.user = None

# ------------------------
# Inline Login (since there are no dedicated pages)
# ------------------------
def login_panel(show_register_bootstrap: bool = True):
    """Inline panel shown on any CRM page when not logged in."""
    st.subheader("🔒 Login required")
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
        if submitted:
            user = login_user(email, password)
            if user:
                st.session_state.user = user
                st.success(f"Welcome back, {user['name']}!")
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")

    # If no users exist at all, allow bootstrapping the first account here
    if show_register_bootstrap and not any_user_exists():
        st.info("No users found yet. Create the first account:")
        with st.form("bootstrap_register"):
            name = st.text_input("Full name", key="reg_name")
            email2 = st.text_input("Admin email", key="reg_email")
            pw1 = st.text_input("Password", type="password", key="reg_pw1")
            pw2 = st.text_input("Confirm password", type="password", key="reg_pw2")
            ok = st.form_submit_button("Create first account")
            if ok:
                if not name or not email2 or not pw1:
                    st.error("All fields are required.")
                elif pw1 != pw2:
                    st.error("Passwords do not match.")
                else:
                    created, msg = create_user(name, email2, pw1)
                    if created:
                        st.success("Account created. Please log in above.")
                    else:
                        st.error(msg)

# ------------------------
# Pages
# ------------------------
def companies_page(user):
    st.subheader("Companies")
    with st.form("add_company"):
        name = st.text_input("Company name")
        industry = st.text_input("Industry")
        if st.form_submit_button("Save"):
            if not name.strip():
                st.error("Name is required")
            else:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute(
                    "INSERT INTO companies (name,industry,created_by) VALUES (?,?,?)",
                    (name.strip(), industry.strip(), user["id"])
                )
                conn.commit()
                conn.close()
                st.success("Company added!")

    # Show companies
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT id, name, industry, created_by, created_at FROM companies ORDER BY created_at DESC",
        conn
    )
    conn.close()
    st.dataframe(df, use_container_width=True)

def contacts_page(user):
    st.subheader("Contacts")
    with st.form("add_contact"):
        name = st.text_input("Full name")
        email = st.text_input("Email")
        phone = st.text_input("Phone")
        company_id = st.number_input("Company ID (optional)", step=1, min_value=0)
        if st.form_submit_button("Save"):
            if not name.strip():
                st.error("Name is required")
            else:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                cid = int(company_id) if company_id else None
                c.execute(
                    "INSERT INTO contacts (name,email,phone,company_id,created_by) VALUES (?,?,?,?,?)",
                    (name.strip(), email.strip(), phone.strip(), cid, user["id"])
                )
                conn.commit()
                conn.close()
                st.success("Contact added!")

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT c.id, c.name, c.email, c.phone, c.company_id, c.created_at,
               co.name AS company_name
        FROM contacts c
        LEFT JOIN companies co ON co.id = c.company_id
        ORDER BY c.created_at DESC
        """,
        conn
    )
    conn.close()
    st.dataframe(df, use_container_width=True)

def deals_page(user):
    st.subheader("Deals")
    with st.form("add_deal"):
        name = st.text_input("Deal name")
        company_id = st.number_input("Company ID (optional)", step=1, min_value=0)
        contact_id = st.number_input("Contact ID (optional)", step=1, min_value=0)
        stage = st.selectbox("Stage", ["New", "Qualified", "Proposal", "Negotiation", "Closed Won", "Closed Lost"])
        amount = st.number_input("Amount", step=100.0, min_value=0.0)
        close_date = st.date_input("Expected close date", value=date.today())
        if st.form_submit_button("Save"):
            if not name.strip():
                st.error("Deal name is required")
            else:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                coid = int(company_id) if company_id else None
                ct = int(contact_id) if contact_id else None
                c.execute(
                    """
                    INSERT INTO deals (name, company_id, contact_id, stage, amount, close_date, created_by)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (name.strip(), coid, ct, stage, float(amount), close_date.isoformat() if close_date else None, user["id"])
                )
                conn.commit()
                conn.close()
                st.success("Deal added!")

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT d.id, d.name, d.stage, d.amount, d.close_date, d.company_id, d.contact_id, d.created_at
        FROM deals d
        ORDER BY d.created_at DESC
        """,
        conn
    )
    conn.close()
    st.dataframe(df, use_container_width=True)

def tasks_page(user):
    st.subheader("Tasks")
    with st.form("add_task"):
        title = st.text_input("Title")
        description = st.text_area("Description")
        due_date = st.date_input("Due date", value=None)
        status = st.selectbox("Status", ["Open", "In Progress", "Done"])
        priority = st.selectbox("Priority", ["Low", "Medium", "High"])
        related_type = st.selectbox("Related to", ["None", "Company", "Contact", "Deal"])
        related_id = st.number_input("Related ID (if any)", step=1, min_value=0)
        if st.form_submit_button("Save"):
            if not title.strip():
                st.error("Title is required")
            else:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                rt = None if related_type == "None" else related_type
                rid = int(related_id) if related_id else None
                dd = due_date.isoformat() if due_date else None
                c.execute(
                    """
                    INSERT INTO tasks (title, description, due_date, status, priority, related_type, related_id, created_by)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (title.strip(), description.strip(), dd, status, priority, rt, rid, user["id"])
                )
                conn.commit()
                conn.close()
                st.success("Task added!")

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT id, title, status, priority, due_date, related_type, related_id, created_at
        FROM tasks
        ORDER BY created_at DESC
        """,
        conn
    )
    conn.close()
    st.dataframe(df, use_container_width=True)

# ------------------------
# Gate wrapper (always show sidebar; gate content if not logged in)
# ------------------------
def render_page_or_login(page_fn):
    user = st.session_state.get("user")
    if user is None:
        login_panel(show_register_bootstrap=True)
    else:
        page_fn(user)

# ------------------------
# Main (Sidebar is always visible; no Login/Register pages)
# ------------------------
def main():
    st.title("Lite CRM")

    if "user" not in st.session_state:
        st.session_state.user = None  # {"id":..., "name":..., "email":...}

    # Fixed sidebar items (always visible)
    st.sidebar.header("Menu")
    nav = st.sidebar.radio(
        "Navigate",
        ["Companies", "Deals", "Contacts", "Tasks", "Logout"],
        index=0,
    )

    # Router
    if nav == "Companies":
        render_page_or_login(companies_page)
    elif nav == "Deals":
        render_page_or_login(deals_page)
    elif nav == "Contacts":
        render_page_or_login(contacts_page)
    elif nav == "Tasks":
        render_page_or_login(tasks_page)
    elif nav == "Logout":
        if st.session_state.user:
            logout_user()
            st.success("Logged out!")
        else:
            st.info("You are not logged in.")
        st.experimental_rerun()

if __name__ == "__main__":
    main()
