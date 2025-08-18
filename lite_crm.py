
import sqlite3
import pandas as pd
import streamlit as st
if not hasattr(st, "rerun"):
    # Backward-compat for older Streamlit
    def _compat_rerun():
        st.experimental_rerun()
    st.rerun = _compat_rerun
from datetime import datetime, date

DB_PATH = "lite_crm.db"

# ---------- DB Utilities ----------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

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

    conn.commit()
    conn.close()

def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def upsert(table, data: dict, id=None):
    conn = get_conn()
    cur = conn.cursor()
    data = {**data, "updated_at": now_iso()}
    if id is None:
        # insert
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        cur.execute(sql, list(data.values()))
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return new_id
    else:
        # update
        set_clause = ", ".join(f"{k}=?" for k in data.keys())
        sql = f"UPDATE {table} SET {set_clause} WHERE id=?"
        cur.execute(sql, list(data.values()) + [id])
        conn.commit()
        conn.close()
        return id

def delete_row(table, id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {table} WHERE id=?", (id,))
    conn.commit()
    conn.close()

def read_df(sql, params=()):
    conn = get_conn()
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df

# ---------- UI Utilities ----------
st.set_page_config(page_title="Lite CRM", page_icon="📇", layout="wide")

def header(title, subtitle=None):
    st.markdown(f"### {title}")
    if subtitle:
        st.caption(subtitle)

def owner_input():
    return st.text_input("Owner (optional)", value=st.session_state.get("owner", ""))

def company_picker(label="Company", key=None):
    companies = read_df("SELECT id, name FROM companies ORDER BY name ASC")
    options = ["-- None --"] + [f"{row['id']} · {row['name']}" for _, row in companies.iterrows()]
    choice = st.selectbox(label, options, key=key)
    if choice == "-- None --":
        return None
    return int(choice.split("·")[0].strip())

def contact_picker(label="Contact", key=None):
    contacts = read_df("SELECT id, first_name, last_name FROM contacts ORDER BY last_name ASC")
    options = ["-- None --"] + [f"{row['id']} · {row['first_name']} {row['last_name']}" for _, row in contacts.iterrows()]
    choice = st.selectbox(label, options, key=key)
    if choice == "-- None --":
        return None
    return int(choice.split("·")[0].strip())

def search_box(placeholder="Search by name, email, or phone...", key="q"):
    return st.text_input("", placeholder=placeholder, key=key)

def render_table(df, use_container_width=True):
    st.dataframe(df, use_container_width=use_container_width)

# ---------- Pages ----------
def dashboard_page():
    header("📈 Dashboard", "Quick stats & upcoming tasks")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Companies", int(read_df("SELECT COUNT(*) as c FROM companies")["c"][0]))
    with col2:
        st.metric("Contacts", int(read_df("SELECT COUNT(*) as c FROM contacts")["c"][0]))
    with col3:
        st.metric("Open Deals", int(read_df("SELECT COUNT(*) as c FROM deals WHERE stage != 'Closed Won' AND stage != 'Closed Lost'")["c"][0]))
    with col4:
        st.metric("Open Tasks", int(read_df("SELECT COUNT(*) as c FROM tasks WHERE status = 'Open'")["c"][0]))

    st.divider()
    st.subheader("📅 Upcoming Tasks (next 14 days)")
    tasks_df = read_df("""
        SELECT id, title, due_date, status, priority, related_type, related_id
        FROM tasks
        WHERE status='Open' AND due_date IS NOT NULL AND due_date <= date('now', '+14 day')
        ORDER BY due_date ASC
    """)
    if tasks_df.empty:
        st.info("No upcoming tasks.")
    else:
        render_table(tasks_df)

    st.subheader("💼 Deals by Stage")
    deals_df = read_df("""
        SELECT stage, COUNT(*) as count, SUM(amount) as pipeline
        FROM deals
        GROUP BY stage
    """)
    if deals_df.empty:
        st.info("No deals yet.")
    else:
        render_table(deals_df)

def companies_page():
    header("🏢 Companies", "Manage accounts")
    with st.expander("➕ Add / Edit Company", expanded=False):
        cid = st.number_input("ID (leave 0 to create new)", value=0, step=1)
        name = st.text_input("Name *")
        domain = st.text_input("Domain")
        phone = st.text_input("Phone")
        website = st.text_input("Website")
        owner = owner_input()

        if st.button("Save Company", type="secondary"):
            if not name.strip():
                st.error("Name is required")
            else:
                data = {"name": name.strip(), "domain": domain.strip(), "phone": phone.strip(), "website": website.strip(), "owner": owner}
                new_id = upsert("companies", data, id=(cid or None))
                st.success(f"Saved company with ID {new_id}")
                st.rerun()

    q = search_box("Search by name or domain...", key="q_companies")
    if q:
        df = read_df("SELECT * FROM companies WHERE name LIKE ? OR domain LIKE ? ORDER BY updated_at DESC", (f"%{q}%", f"%{q}%"))
    else:
        df = read_df("SELECT * FROM companies ORDER BY updated_at DESC LIMIT 500")
    render_table(df)

    with st.expander("🧹 Delete Company"):
        del_id = st.number_input("Company ID to delete", value=0, step=1)
        if st.button("Delete Company", type="secondary"):
            if del_id > 0:
                delete_row("companies", del_id)
                st.warning(f"Deleted company {del_id}")
                st.experimental_rerun()
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
                    df["updated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    df.to_sql("companies", conn, if_exists="append", index=False)
                    conn.close()
                    st.success("Imported companies")
                    st.experimental_rerun()
            except Exception as e:
                st.error(f"Import failed: {e}")
    with c2:
        df = read_df("SELECT * FROM companies")
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
                st.experimental_rerun()

    q = search_box("Search by name, email, or phone...", key="q_contacts")
    if q:
        like = f"%{q}%"
        df = read_df("""
            SELECT c.*, co.name as company_name
            FROM contacts c
            LEFT JOIN companies co ON co.id=c.company_id
            WHERE c.first_name LIKE ? OR c.last_name LIKE ? OR c.email LIKE ? OR c.phone LIKE ?
            ORDER BY c.updated_at DESC
        """, (like, like, like, like))
    else:
        df = read_df("""
            SELECT c.*, co.name as company_name
            FROM contacts c
            LEFT JOIN companies co ON co.id=c.company_id
            ORDER BY c.updated_at DESC LIMIT 500
        """)
    render_table(df)

    with st.expander("🧹 Delete Contact"):
        del_id = st.number_input("Contact ID to delete", value=0, step=1, key="del_contact_id")
        if st.button("Delete Contact", type="secondary", key="del_contact_btn"):
            if del_id > 0:
                delete_row("contacts", del_id)
                st.warning(f"Deleted contact {del_id}")
                st.experimental_rerun()
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
                    df["updated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    df.to_sql("contacts", conn, if_exists="append", index=False)
                    conn.close()
                    st.success("Imported contacts")
                    st.experimental_rerun()
            except Exception as e:
                st.error(f"Import failed: {e}")
    with c2:
        df = read_df("SELECT * FROM contacts")
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
                st.experimental_rerun()

    q = search_box("Search by deal name...", key="q_deals")
    if q:
        df = read_df("""
            SELECT d.*, co.name as company_name,
                   c.first_name || ' ' || c.last_name as contact_name
            FROM deals d
            LEFT JOIN companies co ON co.id=d.company_id
            LEFT JOIN contacts c ON c.id=d.contact_id
            WHERE d.name LIKE ?
            ORDER BY d.updated_at DESC
        """, (f"%{q}%",))
    else:
        df = read_df("""
            SELECT d.*, co.name as company_name,
                   c.first_name || ' ' || c.last_name as contact_name
            FROM deals d
            LEFT JOIN companies co ON co.id=d.company_id
            LEFT JOIN contacts c ON c.id=d.contact_id
            ORDER BY d.updated_at DESC LIMIT 500
        """)
    render_table(df)

    with st.expander("🧹 Delete Deal"):
        del_id = st.number_input("Deal ID to delete", value=0, step=1, key="del_deal_id")
        if st.button("Delete Deal", type="secondary", key="del_deal_btn"):
            if del_id > 0:
                delete_row("deals", del_id)
                st.warning(f"Deleted deal {del_id}")
                st.experimental_rerun()
            else:
                st.error("Enter a valid ID.")

    st.divider()
    st.subheader("Pipeline (by stage)")
    by_stage = read_df("""
        SELECT stage, COUNT(*) as deals, SUM(amount) as amount
        FROM deals
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
    """)
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
                st.experimental_rerun()

    q = search_box("Search by title...", key="q_tasks")
    if q:
        df = read_df("""
            SELECT * FROM tasks
            WHERE title LIKE ? OR description LIKE ?
            ORDER BY updated_at DESC
        """, (f"%{q}%", f"%{q}%"))
    else:
        df = read_df("SELECT * FROM tasks ORDER BY updated_at DESC LIMIT 500")
    render_table(df)

    with st.expander("🧹 Delete Task"):
        del_id = st.number_input("Task ID to delete", value=0, step=1, key="del_task_id")
        if st.button("Delete Task", type="secondary", key="del_task_btn"):
            if del_id > 0:
                delete_row("tasks", del_id)
                st.warning(f"Deleted task {del_id}")
                st.experimental_rerun()
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
                st.experimental_rerun()

    q = search_box("Search notes...", key="q_notes")
    if q:
        df = read_df("""
            SELECT * FROM notes
            WHERE body LIKE ?
            ORDER BY updated_at DESC
        """, (f"%{q}%",))
    else:
        df = read_df("SELECT * FROM notes ORDER BY updated_at DESC LIMIT 500")
    render_table(df)

    with st.expander("🧹 Delete Note"):
        del_id = st.number_input("Note ID to delete", value=0, step=1, key="del_note_id")
        if st.button("Delete Note", type="secondary", key="del_note_btn"):
            if del_id > 0:
                delete_row("notes", del_id)
                st.warning(f"Deleted note {del_id}")
                st.experimental_rerun()
            else:
                st.error("Enter a valid ID.")

def settings_page():
    header("⚙️ Settings", "Owner, demo data, and maintenance")
    st.text_input("Default owner for new records", key="owner", placeholder="e.g., Einstein")

    st.divider()
    st.subheader("Demo data")
    if st.button("Insert sample records"):
        # Add a few records for a quick demo
        company_id = upsert("companies", {"name": "Acme Corp", "domain": "acme.com", "phone": "555-1234", "website": "https://acme.com", "owner": st.session_state.get("owner")})
        contact_id = upsert("contacts", {"first_name": "Ada", "last_name": "Lovelace", "email": "ada@acme.com", "phone": "555-2222", "title": "CTO", "company_id": company_id, "owner": st.session_state.get("owner")})
        upsert("deals", {"name": "Acme – Analytics Project", "company_id": company_id, "contact_id": contact_id, "stage": "Qualified", "amount": 25000, "close_date": date.today().isoformat(), "owner": st.session_state.get("owner")})
        upsert("tasks", {"title": "Follow up with Ada", "description": "Send proposal draft", "due_date": date.today().isoformat(), "status": "Open", "priority": "High", "related_type": "Contact", "related_id": contact_id, "owner": st.session_state.get("owner")})
        upsert("notes", {"body": "Great intro call with Ada. Interested in MMM.", "related_type": "Deal", "related_id": 1, "owner": st.session_state.get("owner")})
        st.success("Inserted sample data!")

    st.subheader("Maintenance")
    if st.button("Reset (delete all local data)"):
        try:
            import os
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            init_db()
            st.warning("Database reset. (Local file removed and recreated.)")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Reset failed: {e}")

# ---------- App ----------
def main():
    init_db()
    st.title("Lite CRM 📇")
    st.caption("Contacts • Companies • Deals • Tasks • Notes (SQLite + Streamlit)")

    pages = {
        "Dashboard": dashboard_page,
        "Companies": companies_page,
        "Contacts": contacts_page,
        "Deals": deals_page,
        "Tasks": tasks_page,
        "Notes": notes_page,
        "Settings": settings_page,
    }
    choice = st.sidebar.radio("Navigate", list(pages.keys()))
    pages[choice]()

    st.sidebar.markdown("---")
    st.sidebar.info("Tip: Set a default Owner in **Settings** so it autofills on new records.")

if __name__ == "__main__":
    main()
