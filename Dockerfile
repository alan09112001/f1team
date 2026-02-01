# Image légère
FROM python:3.9-slim

WORKDIR /app

# Installation des dépendances système basiques
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Installation des libs Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code
COPY . .

# Lancement
CMD ["python", "listener.py"]