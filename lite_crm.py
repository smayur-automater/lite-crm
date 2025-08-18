import os
import base64
import hashlib
import hmac
import sqlite3
import streamlit as st
import pandas as pd
from datetime import datetime

# ------------------------
# Password Hashing Helpers
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
DB_PATH = "lite_crm.db"

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
    conn.commit()
    conn.close()

init_db()

# ------------------------
# Authentication
# ------------------------
def create_user(name, email, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    pw_hash = hash_password(password)
    try:
        c.execute("INSERT INTO users (name,email,password_hash) VALUES (?,?,?)", (name, email, pw_hash))
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
    c.execute("SELECT id,name,password_hash FROM users WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()
    if row and check_password(password, row[2]):
        return {"id": row[0], "name": row[1], "email": email}
    return None

# ------------------------
# App Pages
# ------------------------
def companies_page(user):
    st.subheader("Companies")
    with st.form("add_company"):
        name = st.text_input("Company name")
        industry = st.text_input("Industry")
        if st.form_submit_button("Save"):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO companies (name,industry,created_by) VALUES (?,?,?)", (name, industry, user["id"]))
            conn.commit()
            conn.close()
            st.success("Company added!")

    # Show companies
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM companies", conn)
    st.dataframe(df)
    conn.close()

def contacts_page(user):
    st.subheader("Contacts")
    with st.form("add_contact"):
        name = st.text_input("Contact name")
        email = st.text_input("Email")
        phone = st.text_input("Phone")
        company_id = st.number_input("Company ID", step=1)
        if st.form_submit_button("Save"):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO contacts (name,email,phone,company_id,created_by) VALUES (?,?,?,?,?)",
                      (name, email, phone, company_id, user["id"]))
            conn.commit()
            conn.close()
            st.success("Contact added!")

    # Show contacts
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM contacts", conn)
    st.dataframe(df)
    conn.close()

# ------------------------
# Main App
# ------------------------
def main():
    st.title("Lite CRM")

    if "user" not in st.session_state:
        st.session_state.user = None

    menu = ["Login", "Register"]
    if st.session_state.user:
        menu = ["Companies", "Contacts", "Logout"]

    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Register":
        st.subheader("Create new account")
        name = st.text_input("Name")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Register"):
            if create_user(name, email, password):
                st.success("Account created! Please login.")
    elif choice == "Login":
        st.subheader("Login")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            user = login_user(email, password)
            if user:
                st.session_state.user = user
                st.success(f"Welcome {user['name']}!")
            else:
                st.error("Invalid credentials")
    elif choice == "Companies":
        companies_page(st.session_state.user)
    elif choice == "Contacts":
        contacts_page(st.session_state.user)
    elif choice == "Logout":
        st.session_state.user = None
        st.success("Logged out!")

if __name__ == "__main__":
    main()
