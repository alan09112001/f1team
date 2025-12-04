# 1. Image de base : on utilise une image Python officielle légère (slim)
FROM python:3.11-slim

# 2. Définir l'environnement : le répertoire de travail dans le conteneur
WORKDIR /app

# 3. Installation des dépendances
# On copie d'abord le fichier de dépendances pour tirer parti du cache Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copie du code source
# On copie le reste du projet (listener.py, templates/, static/, etc.)
COPY . .

# 5. Définition des ports
# Le serveur web Flask écoute sur le port 5000 (socketio.run() dans listener.py)
EXPOSE 5000

# 6. Point d'entrée : la commande pour démarrer l'application
# Elle exécute la fonction main() de listener.py
CMD ["python", "listener.py"]