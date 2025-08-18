
    import os
    import sqlite3
    import pandas as pd
    import streamlit as st
    from datetime import datetime, date, timedelta
    import secrets
    import hashlib, hmac, base64, os

    DB_PATH = "lite_crm.db"

    # ---------- Utilities ----------
    def now_iso():
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    def get_conn():
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def column_exists(conn, table, column):
        cur = conn.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cur.fetchall()]
        return column in cols

    def table_exists(conn, table):
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        return cur.fetchone() is not None

    # ---------- Auth helpers ----------
    - def hash_password(password: str) -> bytes:
-     return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
-
- def check_password(password: str, hashed: bytes) -> bool:
-     try:
-         return bcrypt.checkpw(password.encode("utf-8"), hashed)
-     except Exception:
-         return False
+PBKDF_ALG = "sha256"
+PBKDF_ITER = 120_000   # OWASP baseline
+SALT_BYTES = 16
+KEY_LEN = 32
+
+def hash_password(password: str) -> str:
+    salt = os.urandom(SALT_BYTES)
+    dk = hashlib.pbkdf2_hmac(PBKDF_ALG, password.encode("utf-8"), salt, PBKDF_ITER, dklen=KEY_LEN)
+    return f"pbkdf2${PBKDF_ALG}${PBKDF_ITER}$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()
+
+def check_password(password: str, stored: str) -> bool:
+    try:
+        _, alg, iters, salt_b64, dk_b64 = stored.split("$")
+        salt = base64.b64decode(salt_b64)
+        expected = base64.b64decode(dk_b64)
+        dk = hashlib.pbkdf2_hmac(alg, password.encode("utf-8"), salt, int(iters), dklen=len(expected))
+        return hmac.compare_digest(dk, expected)
+    except Exception:
+        return False


    # ---------- DB Init / Migration ----------
    def init_db():
        conn = get_conn()
        cur = conn.cursor()

        # Users
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );""")

        # Workspaces and memberships (RBAC)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_user_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(owner_user_id) REFERENCES users(id) ON DELETE SET NULL
        );""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            workspace_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member', -- 'admin' or 'member'
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, workspace_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
        );""")

        # Invites
        cur.execute("""
        CREATE TABLE IF NOT EXISTS invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            workspace_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member',
            token TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            accepted_at TEXT,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
        );""")

        # Password reset tokens
        cur.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            used_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );""")

        # Core objects
        cur.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            domain TEXT,
            phone TEXT,
            website TEXT,
            owner TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT,
            title TEXT,
            company_id INTEGER,
            owner TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL
        );""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            company_id INTEGER,
            contact_id INTEGER,
            stage TEXT DEFAULT 'New',
            amount REAL DEFAULT 0,
            close_date TEXT,
            owner TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL,
            FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE SET NULL
        );""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            status TEXT DEFAULT 'Open',
            priority TEXT DEFAULT 'Medium',
            related_type TEXT,
            related_id INTEGER,
            owner TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            body TEXT NOT NULL,
            related_type TEXT,
            related_id INTEGER,
            owner TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );""")

        # Ensure multi-tenant scoping columns
        for table in ["companies", "contacts", "deals", "tasks", "notes"]:
            if not column_exists(conn, table, "user_id"):
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;")
                except Exception:
                    pass
            if not column_exists(conn, table, "workspace_id"):
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE;")
                except Exception:
                    pass

        conn.commit()
        conn.close()

    # ---------- Session helpers ----------
    st.set_page_config(page_title="Lite CRM", page_icon="📇", layout="wide")

    if not hasattr(st, "rerun"):
        def _compat_rerun():
            st.experimental_rerun()
        st.rerun = _compat_rerun

    def get_columns(conn, table):
        cur = conn.execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cur.fetchall()]

    def current_user():
        return st.session_state.get("user")

    def current_user_id():
        u = current_user()
        return u["id"] if u else None

    def current_workspace_id():
        return st.session_state.get("workspace_id")

    def current_role():
        return st.session_state.get("role", "member")

    def set_workspace_context(uid):
        # Choose a workspace for the user if not set
        conn = get_conn()
        rows = conn.execute("""
            SELECT m.workspace_id, m.role, w.name
            FROM memberships m
            JOIN workspaces w ON w.id=m.workspace_id
            WHERE m.user_id=?
            ORDER BY w.created_at ASC
        """, (uid,)).fetchall()
        conn.close()
        if not rows:
            return
        wsid, role, _ = rows[0]
        st.session_state["workspace_id"] = wsid
        st.session_state["role"] = role

    # ---------- Data helpers (scoped by workspace) ----------
    def upsert(table, data: dict, id=None):
        uid = current_user_id()
        wsid = current_workspace_id()
        if "user_id" in data:
            pass
        elif uid is not None and "user_id" in get_columns(get_conn(), table):
            data = {**data, "user_id": uid}
        if "workspace_id" in data:
            pass
        elif wsid is not None and "workspace_id" in get_columns(get_conn(), table):
            data = {**data, "workspace_id": wsid}

        conn = get_conn()
        cur = conn.cursor()
        cols = get_columns(conn, table)
        if "updated_at" in cols:
            data = {**data, "updated_at": now_iso()}

        if not id or id == 0:
            cols = ", ".join(data.keys())
            placeholders = ", ".join("?" for _ in data)
            sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
            cur.execute(sql, list(data.values()))
            conn.commit()
            new_id = cur.lastrowid
            conn.close()
            return new_id
        else:
            set_clause = ", ".join(f"{k}=?" for k in data.keys())
            sql = f"UPDATE {table} SET {set_clause} WHERE id=? AND workspace_id=?"
            cur.execute(sql, list(data.values()) + [id, current_workspace_id()])
            conn.commit()
            conn.close()
            return id

    def delete_row(table, id):
        conn = get_conn()
        conn.execute(f"DELETE FROM {table} WHERE id=? AND workspace_id=?", (id, current_workspace_id()))
        conn.commit()
        conn.close()

    def read_df(sql, params=()):
        conn = get_conn()
        df = pd.read_sql_query(sql, conn, params=params)
        conn.close()
        return df

    # ---------- Auth & Invitations ----------
    def accept_invite_if_present(user_email, user_id):
        conn = get_conn()
        row = conn.execute("SELECT id, workspace_id, role FROM invites WHERE email=? AND accepted_at IS NULL ORDER BY created_at DESC", (user_email,)).fetchone()
        if row:
            inv_id, wsid, role = row
            # create membership if missing
            exists = conn.execute("SELECT 1 FROM memberships WHERE user_id=? AND workspace_id=?", (user_id, wsid)).fetchone()
            if not exists:
                conn.execute("INSERT INTO memberships (user_id, workspace_id, role, created_at) VALUES (?,?,?,?)", (user_id, wsid, role, now_iso()))
            conn.execute("UPDATE invites SET accepted_at=? WHERE id=?", (now_iso(), inv_id))
            conn.commit()
        conn.close()

    def show_auth_gate():
        init_db()

        # Query param flows
        qp = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()
        reset_token = qp.get("reset")
        invite_token = qp.get("invite")

        if "user" not in st.session_state:
            st.session_state["user"] = None

        st.title("Lite CRM 📇")
        st.caption("Sign in, create an account, or reset your password.")

        # Handle invite token acceptance upfront (stores invite email in session)
        if invite_token:
            token = invite_token[0] if isinstance(invite_token, list) else invite_token
            conn = get_conn()
            inv = conn.execute("SELECT email, workspace_id, role, created_at FROM invites WHERE token=? AND accepted_at IS NULL", (token,)).fetchone()
            conn.close()
            if inv:
                inv_email, wsid, role, created = inv
                st.info(f"You've been invited to a workspace as **{role}**. Create an account or sign in using **{inv_email}** to accept.")
                st.session_state["pending_invite_email"] = inv_email

        tabs = st.tabs(["Sign in", "Create account", "Forgot password", "Reset password (token)"])

        # --- Sign in ---
        with tabs[0]:
            st.subheader("Welcome back")
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_pw")
            if st.button("Sign in", type="primary", key="login_btn"):
                conn = get_conn()
                row = conn.execute("SELECT id, name, email, password_hash FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
                if not row:
                    st.error("Invalid email or password.")
                else:
                    uid, name, em, pw_hash = row
                    if check_password(password, pw_hash):
                        st.session_state["user"] = {"id": uid, "name": name or em, "email": em}
                        # Set workspace context
                        set_workspace_context(uid)
                        st.success("Signed in successfully.")
                        st.rerun()
                    else:
                        st.error("Invalid email or password.")
                conn.close()

        # --- Create account ---
        with tabs[1]:
            st.subheader("Create a new account")
            name = st.text_input("Full name", key="signup_name")
            email_new = st.text_input("Email", key="signup_email", value=st.session_state.get("pending_invite_email", ""))
            pw1 = st.text_input("Password", type="password", key="signup_pw1")
            pw2 = st.text_input("Confirm password", type="password", key="signup_pw2")
            if st.button("Create account", type="primary", key="signup_btn"):
                if not email_new or not pw1:
                    st.error("Email and password are required.")
                elif pw1 != pw2:
                    st.error("Passwords do not match.")
                else:
                    try:
                        conn = get_conn()
                        conn.execute(
                            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?,?,?,?)",
                            (name.strip() if name else None, email_new.strip().lower(), hash_password(pw1), now_iso()),
                        )
                        conn.commit()
                        row = conn.execute("SELECT id, name, email FROM users WHERE email=?", (email_new.strip().lower(),)).fetchone()
                        uid, nm, em = row

                        # If invited, join that workspace; else create a default workspace
                        inv = conn.execute("SELECT id, workspace_id, role FROM invites WHERE email=? AND accepted_at IS NULL ORDER BY created_at DESC", (em,)).fetchone()
                        if inv:
                            inv_id, wsid, role = inv
                            conn.execute("INSERT OR IGNORE INTO memberships (user_id, workspace_id, role, created_at) VALUES (?,?,?,?)", (uid, wsid, role, now_iso()))
                            conn.execute("UPDATE invites SET accepted_at=? WHERE id=?", (now_iso(), inv_id))
                            st.session_state["workspace_id"] = wsid
                            st.session_state["role"] = role
                        else:
                            # Create default workspace
                            conn.execute("INSERT INTO workspaces (name, owner_user_id, created_at) VALUES (?,?,?)", (f"{nm or em}'s Workspace", uid, now_iso()))
                            wsid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                            conn.execute("INSERT INTO memberships (user_id, workspace_id, role, created_at) VALUES (?,?,?,?)", (uid, wsid, "admin", now_iso()))
                            st.session_state["workspace_id"] = wsid
                            st.session_state["role"] = "admin"

                        conn.commit()
                        conn.close()

                        st.session_state["user"] = {"id": uid, "name": nm or em, "email": em}
                        st.success("Account created. You're signed in.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("That email is already registered. Try signing in.")

        # --- Forgot password (request token) ---
        with tabs[2]:
            st.subheader("Forgot password")
            email_f = st.text_input("Your account email", key="forgot_email")
            if st.button("Generate reset link", key="forgot_btn"):
                conn = get_conn()
                row = conn.execute("SELECT id FROM users WHERE email=?", (email_f.strip().lower(),)).fetchone()
                if not row:
                    st.error("If that email exists, a reset token will be generated.")
                else:
                    uid = row[0]
                    token = secrets.token_urlsafe(24)
                    conn.execute("INSERT INTO password_resets (user_id, token, created_at) VALUES (?,?,?)", (uid, token, now_iso()))
                    conn.commit()
                    conn.close()
                    base = st.request.host or "localhost:8501"
                    link = f"https://{base}?reset={token}"
                    st.success("Reset token created. Since email isn't configured, copy this URL:")
                    st.code(link, language="text")

        # --- Reset password (consume token) ---
        with tabs[3]:
            st.subheader("Reset password via token")
            token_in = ""
            if reset_token:
                token_in = reset_token[0] if isinstance(reset_token, list) else reset_token
                st.info("Token detected in URL; you can submit directly.")
            token = st.text_input("Reset token", value=token_in)
            new1 = st.text_input("New password", type="password", key="newpw1")
            new2 = st.text_input("Confirm new password", type="password", key="newpw2")
            if st.button("Reset password", type="primary", key="reset_btn"):
                if new1 != new2 or not new1:
                    st.error("Passwords must match and be non-empty.")
                else:
                    conn = get_conn()
                    row = conn.execute("SELECT user_id, created_at, used_at FROM password_resets WHERE token=?", (token,)).fetchone()
                    if not row:
                        st.error("Invalid token.")
                    else:
                        uid, created_at, used_at = row
                        # simple expiry: 60 minutes
                        created_dt = datetime.fromisoformat(created_at.replace("Z",""))
                        if used_at is not None:
                            st.error("Token already used.")
                        elif datetime.utcnow() - created_dt > timedelta(minutes=60):
                            st.error("Token expired.")
                        else:
                            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new1), uid))
                            conn.execute("UPDATE password_resets SET used_at=? WHERE token=?", (now_iso(), token))
                            conn.commit()
                            conn.close()
                            st.success("Password updated. Please sign in.")
                            st.rerun()

    # ---------- UI utilities ----------
    def header(title, subtitle=None):
        st.markdown(f"### {title}")
        if subtitle:
            st.caption(subtitle)

    def owner_input():
        return st.text_input("Owner (optional)", value=st.session_state.get("default_owner", ""))

    def company_picker(label="Company", key=None):
        wsid = current_workspace_id()
        companies = read_df("SELECT id, name FROM companies WHERE workspace_id=? ORDER BY name ASC", (wsid,))
        options = ["-- None --"] + [f"{row['id']} · {row['name']}" for _, row in companies.iterrows()]
        choice = st.selectbox(label, options, key=key)
        if choice == "-- None --":
            return None
        return int(choice.split("·")[0].strip())

    def contact_picker(label="Contact", key=None):
        wsid = current_workspace_id()
        contacts = read_df("SELECT id, first_name, last_name FROM contacts WHERE workspace_id=? ORDER BY last_name ASC", (wsid,))
        options = ["-- None --"] + [f"{row['id']} · {row['first_name']} {row['last_name']}" for _, row in contacts.iterrows()]
        choice = st.selectbox(label, options, key=key)
        if choice == "-- None --":
            return None
        return int(choice.split("·")[0].strip())

    def render_table(df, use_container_width=True):
        st.dataframe(df, use_container_width=use_container_width)

    # ---------- Pages ----------
    def dashboard_page():
        header("📈 Dashboard", "Quick stats & upcoming tasks")
        wsid = current_workspace_id()
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Companies", int(read_df("SELECT COUNT(*) as c FROM companies WHERE workspace_id=?", (wsid,))["c"][0]))
        with col2:
            st.metric("Contacts", int(read_df("SELECT COUNT(*) as c FROM contacts WHERE workspace_id=?", (wsid,))["c"][0]))
        with col3:
            st.metric("Open Deals", int(read_df("SELECT COUNT(*) as c FROM deals WHERE workspace_id=? AND stage NOT IN ('Closed Won','Closed Lost')", (wsid,))["c"][0]))
        with col4:
            st.metric("Open Tasks", int(read_df("SELECT COUNT(*) as c FROM tasks WHERE workspace_id=? AND status='Open'", (wsid,))["c"][0]))

        st.divider()
        st.subheader("📅 Upcoming Tasks (next 14 days)")
        tasks_df = read_df("""
            SELECT id, title, due_date, status, priority, related_type, related_id
            FROM tasks
            WHERE workspace_id=? AND status='Open' AND due_date IS NOT NULL AND due_date <= date('now', '+14 day')
            ORDER BY due_date ASC
        """, (wsid,))
        if tasks_df.empty:
            st.info("No upcoming tasks.")
        else:
            render_table(tasks_df)

        st.subheader("💼 Deals by Stage")
        deals_df = read_df("""
            SELECT stage, COUNT(*) as count, SUM(amount) as pipeline
            FROM deals
            WHERE workspace_id=?
            GROUP BY stage
        """, (wsid,))
        if deals_df.empty:
            st.info("No deals yet.")
        else:
            render_table(deals_df)

    def require_admin():
        if current_role() != "admin":
            st.error("Admin only action.")
            return False
        return True

    def companies_page():
        header("🏢 Companies", "Manage accounts")
        with st.expander("➕ Add / Edit Company", expanded=False):
            cid = st.number_input("ID (leave 0 to create new)", value=0, step=1)
            name = st.text_input("Name *")
            domain = st.text_input("Domain")
            phone = st.text_input("Phone")
            website = st.text_input("Website")
            owner = owner_input()

            if st.button("Save Company", type="primary"):
                if not name.strip():
                    st.error("Name is required")
                else:
                    data = {"name": name.strip(), "domain": domain.strip(), "phone": phone.strip(), "website": website.strip(), "owner": owner}
                    new_id = upsert("companies", data, id=(cid or None))
                    st.success(f"Saved company with ID {new_id}")
                    st.rerun()

        q = st.text_input("Search by name or domain...", key="q_companies")
        wsid = current_workspace_id()
        if q:
            df = read_df("SELECT * FROM companies WHERE workspace_id=? AND (name LIKE ? OR domain LIKE ?) ORDER BY updated_at DESC", (wsid, f"%{q}%", f"%{q}%"))
        else:
            df = read_df("SELECT * FROM companies WHERE workspace_id=? ORDER BY updated_at DESC LIMIT 500", (wsid,))
        render_table(df)

        with st.expander("🧹 Delete Company"):
            del_id = st.number_input("Company ID to delete", value=0, step=1)
            if st.button("Delete Company", type="secondary"):
                if not require_admin():
                    pass
                elif del_id > 0:
                    delete_row("companies", del_id)
                    st.warning(f"Deleted company {del_id}")
                    st.rerun()
                else:
                    st.error("Enter a valid ID.")

        st.divider()
        st.subheader("⬇️ Import / ⬆️ Export")
        c1, c2 = st.columns(2)
        with c1:
            uploaded = st.file_uploader("Import companies CSV", type=["csv"], key="imp_comp")
            if uploaded:
                try:
                    df = pd.read_csv(uploaded)
                    required = {"name"}
                    if not required.issubset(df.columns):
                        st.error(f"CSV must include {required}")
                    else:
                        conn = get_conn()
                        df["user_id"] = current_user_id()
                        df["workspace_id"] = current_workspace_id()
                        if "updated_at" in get_columns(conn, "companies"):
                            df["updated_at"] = now_iso()
                        df.to_sql("companies", conn, if_exists="append", index=False)
                        conn.close()
                        st.success("Imported companies")
                        st.rerun()
                except Exception as e:
                    st.error(f"Import failed: {e}")
        with c2:
            df = read_df("SELECT * FROM companies WHERE workspace_id=?", (wsid,))
            st.download_button("Export companies CSV", df.to_csv(index=False), file_name="companies_export.csv")

    def contacts_page():
        header("👤 Contacts", "Manage people")
        with st.expander("➕ Add / Edit Contact", expanded=False):
            cid = st.number_input("ID (leave 0 to create new)", value=0, step=1, key="contact_id_input")
            first = st.text_input("First name *")
            last = st.text_input("Last name *")
            email = st.text_input("Email")
            phone = st.text_input("Phone")
            title = st.text_input("Title")
            company_id = company_picker()
            owner = owner_input()

            if st.button("Save Contact", type="primary"):
                if not first.strip() or not last.strip():
                    st.error("First and last name are required")
                else:
                    data = {"first_name": first.strip(), "last_name": last.strip(), "email": email.strip(), "phone": phone.strip(), "title": title.strip(), "company_id": company_id, "owner": owner}
                    new_id = upsert("contacts", data, id=(cid or None))
                    st.success(f"Saved contact with ID {new_id}")
                    st.rerun()

        q = st.text_input("Search by name, email, or phone...", key="q_contacts")
        wsid = current_workspace_id()
        if q:
            like = f"%{q}%"
            df = read_df("""
                SELECT c.*, co.name as company_name
                FROM contacts c
                LEFT JOIN companies co ON co.id=c.company_id
                WHERE c.workspace_id=? AND (c.first_name LIKE ? OR c.last_name LIKE ? OR c.email LIKE ? OR c.phone LIKE ?)
                ORDER BY c.updated_at DESC
            """, (wsid, like, like, like, like))
        else:
            df = read_df("""
                SELECT c.*, co.name as company_name
                FROM contacts c
                LEFT JOIN companies co ON co.id=c.company_id
                WHERE c.workspace_id=?
                ORDER BY c.updated_at DESC LIMIT 500
            """, (wsid,))
        render_table(df)

        with st.expander("🧹 Delete Contact"):
            del_id = st.number_input("Contact ID to delete", value=0, step=1, key="del_contact_id")
            if st.button("Delete Contact", type="secondary", key="del_contact_btn"):
                if not require_admin():
                    pass
                elif del_id > 0:
                    delete_row("contacts", del_id)
                    st.warning(f"Deleted contact {del_id}")
                    st.rerun()
                else:
                    st.error("Enter a valid ID.")

        st.divider()
        st.subheader("⬇️ Import / ⬆️ Export")
        c1, c2 = st.columns(2)
        with c1:
            uploaded = st.file_uploader("Import contacts CSV", type=["csv"], key="imp_contacts")
            if uploaded:
                try:
                    df = pd.read_csv(uploaded)
                    required = {"first_name", "last_name"}
                    if not required.issubset(df.columns):
                        st.error(f"CSV must include {required}")
                    else:
                        conn = get_conn()
                        df["user_id"] = current_user_id()
                        df["workspace_id"] = current_workspace_id()
                        if "updated_at" in get_columns(conn, "contacts"):
                            df["updated_at"] = now_iso()
                        df.to_sql("contacts", conn, if_exists="append", index=False)
                        conn.close()
                        st.success("Imported contacts")
                        st.rerun()
                except Exception as e:
                    st.error(f"Import failed: {e}")
        with c2:
            df = read_df("SELECT * FROM contacts WHERE workspace_id=?", (wsid,))
            st.download_button("Export contacts CSV", df.to_csv(index=False), file_name="contacts_export.csv")

    def deals_page():
        header("💼 Deals", "Pipeline & opportunities")
        with st.expander("➕ Add / Edit Deal", expanded=False):
            did = st.number_input("ID (leave 0 to create new)", value=0, step=1, key="deal_id_input")
            name = st.text_input("Name *")
            company_id = company_picker()
            contact_id = contact_picker()
            stage = st.selectbox("Stage", ["New", "Qualified", "Proposal", "Negotiation", "Closed Won", "Closed Lost"])
            amount = st.number_input("Amount", min_value=0.0, step=100.0)
            close_date = st.date_input("Expected close date", value=date.today())
            owner = owner_input()

            if st.button("Save Deal", type="primary"):
                if not name.strip():
                    st.error("Deal name is required")
                else:
                    data = {
                        "name": name.strip(),
                        "company_id": company_id,
                        "contact_id": contact_id,
                        "stage": stage,
                        "amount": float(amount),
                        "close_date": close_date.isoformat() if close_date else None,
                        "owner": owner,
                    }
                    new_id = upsert("deals", data, id=(did or None))
                    st.success(f"Saved deal with ID {new_id}")
                    st.rerun()

        q = st.text_input("Search by deal name...", key="q_deals")
        wsid = current_workspace_id()
        if q:
            df = read_df("""
                SELECT d.*, co.name as company_name,
                       c.first_name || ' ' || c.last_name as contact_name
                FROM deals d
                LEFT JOIN companies co ON co.id=d.company_id
                LEFT JOIN contacts c ON c.id=d.contact_id
                WHERE d.workspace_id=? AND d.name LIKE ?
                ORDER BY d.updated_at DESC
            """, (wsid, f"%{q}%",))
        else:
            df = read_df("""
                SELECT d.*, co.name as company_name,
                       c.first_name || ' ' || c.last_name as contact_name
                FROM deals d
                LEFT JOIN companies co ON co.id=d.company_id
                LEFT JOIN contacts c ON c.id=d.contact_id
                WHERE d.workspace_id=?
                ORDER BY d.updated_at DESC LIMIT 500
            """, (wsid,))
        render_table(df)

        with st.expander("🧹 Delete Deal"):
            del_id = st.number_input("Deal ID to delete", value=0, step=1, key="del_deal_id")
            if st.button("Delete Deal", type="secondary", key="del_deal_btn"):
                if not require_admin():
                    pass
                elif del_id > 0:
                    delete_row("deals", del_id)
                    st.warning(f"Deleted deal {del_id}")
                    st.rerun()
                else:
                    st.error("Enter a valid ID.")

        st.divider()
        st.subheader("Pipeline (by stage)")
        by_stage = read_df("""
            SELECT stage, COUNT(*) as deals, SUM(amount) as amount
            FROM deals
            WHERE workspace_id=?
            GROUP BY stage
            ORDER BY
              CASE stage
                WHEN 'New' THEN 1
                WHEN 'Qualified' THEN 2
                WHEN 'Proposal' THEN 3
                WHEN 'Negotiation' THEN 4
                WHEN 'Closed Won' THEN 5
                WHEN 'Closed Lost' THEN 6
                ELSE 7 END
        """, (current_workspace_id(),))
        render_table(by_stage)

    def tasks_page():
        header("📝 Tasks", "Follow-ups & reminders")
        with st.expander("➕ Add / Edit Task", expanded=False):
            tid = st.number_input("ID (leave 0 to create new)", value=0, step=1, key="task_id_input")
            title = st.text_input("Title *")
            description = st.text_area("Description")
            due_date = st.date_input("Due date", value=None)
            status = st.selectbox("Status", ["Open", "In Progress", "Done"])
            priority = st.selectbox("Priority", ["Low", "Medium", "High"])
            related_type = st.selectbox("Related to", ["None", "Company", "Contact", "Deal"])
            related_id = st.number_input("Related ID (if any)", value=0, step=1)
            owner = owner_input()

            if st.button("Save Task", type="primary"):
                if not title.strip():
                    st.error("Task title is required")
                else:
                    rt = None if related_type == "None" else related_type
                    rid = None if related_id == 0 else related_id
                    dd = due_date.isoformat() if due_date else None
                    data = {
                        "title": title.strip(),
                        "description": description.strip(),
                        "due_date": dd,
                        "status": status,
                        "priority": priority,
                        "related_type": rt,
                        "related_id": rid,
                        "owner": owner,
                    }
                    new_id = upsert("tasks", data, id=(tid or None))
                    st.success(f"Saved task with ID {new_id}")
                    st.rerun()

        q = st.text_input("Search by title...", key="q_tasks")
        wsid = current_workspace_id()
        if q:
            df = read_df("""
                SELECT * FROM tasks
                WHERE workspace_id=? AND (title LIKE ? OR description LIKE ?)
                ORDER BY updated_at DESC
            """, (wsid, f"%{q}%", f"%{q}%"))
        else:
            df = read_df("SELECT * FROM tasks WHERE workspace_id=? ORDER BY updated_at DESC LIMIT 500", (wsid,))
        render_table(df)

        with st.expander("🧹 Delete Task"):
            del_id = st.number_input("Task ID to delete", value=0, step=1, key="del_task_id")
            if st.button("Delete Task", type="secondary", key="del_task_btn"):
                if not require_admin():
                    pass
                elif del_id > 0:
                    delete_row("tasks", del_id)
                    st.warning(f"Deleted task {del_id}")
                    st.rerun()
                else:
                    st.error("Enter a valid ID.")

    def notes_page():
        header("🗒️ Notes", "Log interactions")
        with st.expander("➕ Add / Edit Note", expanded=False):
            nid = st.number_input("ID (leave 0 to create new)", value=0, step=1, key="note_id_input")
            body = st.text_area("Note *")
            related_type = st.selectbox("Related to", ["None", "Company", "Contact", "Deal"])
            related_id = st.number_input("Related ID (if any)", value=0, step=1)
            owner = owner_input()

            if st.button("Save Note", type="primary"):
                if not body.strip():
                    st.error("Note is required")
                else:
                    rt = None if related_type == "None" else related_type
                    rid = None if related_id == 0 else related_id
                    data = {"body": body.strip(), "related_type": rt, "related_id": rid, "owner": owner}
                    new_id = upsert("notes", data, id=(nid or None))
                    st.success(f"Saved note with ID {new_id}")
                    st.rerun()

        q = st.text_input("Search notes...", key="q_notes")
        wsid = current_workspace_id()
        if q:
            df = read_df("""
                SELECT * FROM notes
                WHERE workspace_id=? AND body LIKE ?
                ORDER BY updated_at DESC
            """, (wsid, f"%{q}%",))
        else:
            df = read_df("SELECT * FROM notes WHERE workspace_id=? ORDER BY updated_at DESC LIMIT 500", (wsid,))
        render_table(df)

        with st.expander("🧹 Delete Note"):
            del_id = st.number_input("Note ID to delete", value=0, step=1, key="del_note_id")
            if st.button("Delete Note", type="secondary", key="del_note_btn"):
                if not require_admin():
                    pass
                elif del_id > 0:
                    delete_row("notes", del_id)
                    st.warning(f"Deleted note {del_id}")
                    st.rerun()
                else:
                    st.error("Enter a valid ID.")

    def workspace_settings():
        header("👥 Workspace", "Members, invites, and switching")
        uid = current_user_id()

        # Switcher
        conn = get_conn()
        rows = conn.execute("""
            SELECT w.id, w.name, m.role
            FROM memberships m JOIN workspaces w ON w.id=m.workspace_id
            WHERE m.user_id=?
            ORDER BY w.created_at ASC
        """, (uid,)).fetchall()
        conn.close()

        if not rows:
            st.warning("You have no workspaces. Create one below.")
        else:
            names = {row[0]: f"{row[1]} ({row[2]})" for row in rows}
            wsids = list(names.keys())
            current = current_workspace_id() or wsids[0]
            choice = st.selectbox("Active Workspace", options=wsids, format_func=lambda x: names[x], index=wsids.index(current))
            if choice != current_workspace_id():
                st.session_state["workspace_id"] = choice
                # update role in session
                role = [r[2] for r in rows if r[0] == choice][0]
                st.session_state["role"] = role
                st.success(f"Switched to workspace: {names[choice]}")
                st.rerun()

        st.divider()

        # Admin-only actions
        if current_role() == "admin":
            st.subheader("Create workspace")
            ws_name = st.text_input("Workspace name", key="new_ws_name")
            if st.button("Create workspace", key="create_ws"):
                if ws_name.strip():
                    conn = get_conn()
                    conn.execute("INSERT INTO workspaces (name, owner_user_id, created_at) VALUES (?,?,?)", (ws_name.strip(), uid, now_iso()))
                    wsid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    conn.execute("INSERT INTO memberships (user_id, workspace_id, role, created_at) VALUES (?,?,?,?)", (uid, wsid, "admin", now_iso()))
                    conn.commit()
                    conn.close()
                    st.success("Workspace created and you are admin.")
                    st.rerun()
                else:
                    st.error("Name required.")

            st.subheader("Invite member")
            inv_email = st.text_input("Invitee email")
            inv_role = st.selectbox("Role", ["member", "admin"])
            if st.button("Generate invite link"):
                if inv_email and "@" in inv_email:
                    token = secrets.token_urlsafe(20)
                    conn = get_conn()
                    conn.execute("INSERT INTO invites (email, workspace_id, role, token, created_at) VALUES (?,?,?,?,?)",
                                 (inv_email.strip().lower(), current_workspace_id(), inv_role, token, now_iso()))
                    conn.commit()
                    conn.close()
                    base = st.request.host or "localhost:8501"
                    link = f"https://{base}?invite={token}"
                    st.success("Share this invite link:")
                    st.code(link, language="text")
                else:
                    st.error("Enter a valid email.")

            st.subheader("Members")
            conn = get_conn()
            members = read_df("""
                SELECT u.email, u.name, m.role, m.created_at
                FROM memberships m JOIN users u ON u.id=m.user_id
                WHERE m.workspace_id=?
                ORDER BY u.email
            """, (current_workspace_id(),))
            conn.close()
            render_table(members)

    def settings_page():
        header("⚙️ Settings", "Owner, demo data, and maintenance")
        st.text_input("Default owner for new records", key="default_owner", placeholder="e.g., Einstein")

        st.divider()
        st.subheader("Demo data")
        if st.button("Insert sample records"):
            company_id = upsert("companies", {"name": "Acme Corp", "domain": "acme.com", "phone": "555-1234", "website": "https://acme.com", "owner": st.session_state.get("default_owner")})
            contact_id = upsert("contacts", {"first_name": "Ada", "last_name": "Lovelace", "email": "ada@acme.com", "phone": "555-2222", "title": "CTO", "company_id": company_id, "owner": st.session_state.get("default_owner")})
            deal_id = upsert("deals", {"name": "Acme – Analytics Project", "company_id": company_id, "contact_id": contact_id, "stage": "Qualified", "amount": 25000, "close_date": date.today().isoformat(), "owner": st.session_state.get("default_owner")})
            upsert("tasks", {"title": "Follow up with Ada", "description": "Send proposal draft", "due_date": date.today().isoformat(), "status": "Open", "priority": "High", "related_type": "Contact", "related_id": contact_id, "owner": st.session_state.get("default_owner")})
            upsert("notes", {"body": "Great intro call with Ada. Interested in MMM.", "related_type": "Deal", "related_id": deal_id, "owner": st.session_state.get("default_owner")})
            st.success("Inserted sample data!")

        st.subheader("Maintenance (current workspace)")
        if st.button("Reset (delete all data in this workspace)"):
            if current_role() != "admin":
                st.error("Admin only action.")
            else:
                try:
                    conn = get_conn()
                    for table in ["notes", "tasks", "deals", "contacts", "companies"]:
                        conn.execute(f"DELETE FROM {table} WHERE workspace_id=?", (current_workspace_id(),))
                    conn.commit()
                    conn.close()
                    st.warning("Workspace data deleted.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Reset failed: {e}")

    # ---------- App ----------
    def main():
        init_db()

        # If not logged in, show auth
        if not current_user():
            show_auth_gate()
            return

        # Top bar: workspace + user
        colA, colB = st.columns([0.7, 0.3])
        with colA:
            st.title("Lite CRM 📇")
            st.caption("Accounts • Contacts • Deals • Tasks • Notes")
        with colB:
            u = current_user()
            st.write(f"**{u['name']}**  
{u['email']}")
            if st.button("Sign out"):
                st.session_state.clear()
                st.rerun()

        pages = {
            "Dashboard": dashboard_page,
            "Companies": companies_page,
            "Contacts": contacts_page,
            "Deals": deals_page,
            "Tasks": tasks_page,
            "Notes": notes_page,
            "Workspace": workspace_settings,
            "Settings": settings_page,
        }
        choice = st.sidebar.radio("Navigate", list(pages.keys()))
        pages[choice]()

        st.sidebar.markdown("---")
        st.sidebar.info("Tip: Use **Workspace** to invite teammates and switch contexts.")

    if __name__ == "__main__":
        main()
