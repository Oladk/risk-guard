FROM python:3.12-slim

WORKDIR /app

# Dépendances d'abord (cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code
COPY . .

# Multi-utilisateur activé par défaut en conteneur (déploiement cloud).
ENV RISK_REQUIRE_AUTH=1
# Base persistée : monter un volume sur /app/data (sinon éphémère).
ENV RISK_DB_PATH=/app/data/risk.db

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health').status==200 else 1)"

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
