import os
import base64
import hashlib
import hmac
import sqlite3
from datetime import datetime, date
import streamlit as st
import pandas as pd

# ------------------------
# App config
# ------------------------
try:
    st.set_page_config(page_title="Lite CRM", page_icon="📇", layout="wide", initial_sidebar_state="expanded")
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

    # Deals (new)
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

    # Tasks (new)
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
def create_user(name, email, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    pw_hash = hash_password(password)
    try:
        c.execute("INSERT INTO users (name,email,password_hash) VALUES (?,?,?)", (name, email.lower().strip(), pw_hash))
        conn.commit()
    except sqlite3.IntegrityError:
        st.error("User already exists")
        return False
    finally:
        conn.close()
    return True

def login_user(email, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id,name,password_hash FROM users WHERE email=?", (email.lower().strip(),))
    row = c.fetchone()
    conn.close()
    if row and check_password(password, row[2]):
        return {"id": row[0], "name": row[1], "email": email}
    return None

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
# Main (Sidebar nav with fixed items)
# ------------------------
def main():
    st.title("Lite CRM")

    if "user" not in st.session_state:
        st.session_state.user = None

    # Build sidebar first
    st.sidebar.header("Menu")

    if st.session_state.user is None:
        nav = st.sidebar.radio("Navigate", ["Login", "Register"], index=0)
        if nav == "Register":
            st.subheader("Create new account")
            name = st.text_input("Name")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.button("Register"):
                if name and email and password:
                    if create_user(name, email, password):
                        st.success("Account created! Please login.")
                        st.experimental_rerun()
                else:
                    st.error("Please fill all fields.")
        elif nav == "Login":
            st.subheader("Login")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.button("Login"):
                user = login_user(email, password)
                if user:
                    st.session_state.user = user
                    st.success(f"Welcome {user['name']}!")
                    st.experimental_rerun()
                else:
                    st.error("Invalid credentials")
    else:
        # Fixed list — no dropdown — exactly the pages you asked for:
        nav = st.sidebar.radio("Navigate", ["Companies", "Deals", "Contacts", "Tasks", "Logout"], index=0)

        if nav == "Companies":
            companies_page(st.session_state.user)
        elif nav == "Deals":
            deals_page(st.session_state.user)
        elif nav == "Contacts":
            contacts_page(st.session_state.user)
        elif nav == "Tasks":
            tasks_page(st.session_state.user)
        elif nav == "Logout":
            st.session_state.user = None
            st.success("Logged out!")
            st.experimental_rerun()

if __name__ == "__main__":
    main()
