
# Lite CRM (Streamlit + SQLite)

A lightweight CRM you can run locally or deploy to Streamlit Cloud. Features:
- Contacts, Companies, Deals, Tasks, Notes
- Simple pipeline view (deals by stage)
- Search, import/export CSV, and demo data
- Single-file app using SQLite (created in the same folder)

## Quickstart

1. Install dependencies (ideally in a virtual environment):
   ```bash
   pip install streamlit pandas
   ```

2. Run the app:
   ```bash
   streamlit run lite_crm.py
   ```

3. The app will create `lite_crm.db` next to the script on first run.

## Deploy (Streamlit Community Cloud)

- Push `lite_crm.py` to a GitHub repo.
- On https://share.streamlit.io , create a new app from your repo.
- Add the following to `requirements.txt` in your repo:
  ```
  streamlit
  pandas
  ```

## Optional Improvements (next steps)
- Use a managed DB (e.g., Supabase/Postgres) and add user auth.
- Add file attachments and activity timelines.
- Add email logging and basic Kanban for deal stages.
- Build REST API endpoints (FastAPI) to integrate with other tools.
