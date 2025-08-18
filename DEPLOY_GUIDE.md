# Lite CRM — Deployment Guide

Below are several reliable hosting options if Streamlit Community Cloud is slow or unreachable.

---

## Option A: Render (Free tier)

1. Create a new **Web Service** on Render.
2. Connect your repo (or upload these files) with `lite_crm.py`, `requirements.txt`, and `render.yaml`.
3. Render auto-detects the Python environment. Use the start command:
   ```
   streamlit run lite_crm.py --server.port=$PORT --server.address=0.0.0.0
   ```
4. Deploy. Your app will be available at a Render URL.

---

## Option B: Hugging Face Spaces (Streamlit)

1. Create a new **Space** → **Streamlit**.
2. Upload `app.py` (duplicate of `lite_crm.py`) and `requirements.txt`.
3. Spaces will auto-build and serve the app.

> If you prefer the filename `lite_crm.py`, set `App file: lite_crm.py` in the Space settings.

---

## Option C: Heroku (Free limited tier / low-cost dynos)

1. Install Heroku CLI and log in.
2. Ensure `Procfile` and `requirements.txt` are present.
3. Push your repo to Heroku:
   ```bash
   heroku create lite-crm-demo
   git push heroku main
   ```
4. Heroku will run the `Procfile` command:
   ```
   web: streamlit run lite_crm.py --server.port=$PORT --server.address=0.0.0.0
   ```

---

## Option D: Docker anywhere (Fly.io, Railway, your VPS)

1. Build and run locally:
   ```bash
   docker build -t lite-crm .
   docker run -p 8501:8501 lite-crm
   ```
2. Deploy the same image to your preferred host (Fly.io, Railway, AWS Lightsail, GCP Cloud Run).

**Cloud Run (example):**
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/lite-crm
gcloud run deploy lite-crm --image gcr.io/PROJECT_ID/lite-crm --platform managed --allow-unauthenticated --region YOUR_REGION --port 8501
```

---

## Option E: Quick temporary sharing (no hosting)

- **Cloudflare Tunnel** (no account required):
  ```bash
  pip install streamlit pandas cloudflared
  streamlit run lite_crm.py
  cloudflared tunnel --url http://localhost:8501
  ```
  Share the public URL printed by `cloudflared`.
  
- **ngrok**:
  ```bash
  streamlit run lite_crm.py
  ngrok http 8501
  ```

---

## Performance & Reliability Tips

- Use `--server.address=0.0.0.0` and the host's `$PORT` to avoid binding errors.
- Avoid storing large CSVs in SQLite; consider Postgres (e.g., Supabase) for multi-user scale.
- Add caching for expensive queries in Streamlit (e.g., `@st.cache_data`).
- Turn off debug logs in production to reduce overhead.
- Prefer regions close to your users (Australia → choose an APAC region when available).

---

## Files included in this package

- `lite_crm.py` — the app
- `app.py` — alias for HF Spaces
- `requirements.txt` — Python deps
- `Dockerfile` — container deploy
- `Procfile` — Heroku
- `render.yaml` — Render
- `DEPLOY_GUIDE.md` — this guide