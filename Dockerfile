FROM python:3.11-slim

WORKDIR /app

# System deps (optional but useful for pandas performance)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY lite_crm.py ./

# Streamlit configs
ENV PORT=8501
EXPOSE 8501

CMD streamlit run lite_crm.py --server.port=${PORT} --server.address=0.0.0.0