#!/bin/bash

# 1. Se placer dans le dossier du script
cd "$(dirname "$0")"

echo "🍎 --- Démarrage du script d'installation pour Mac ---"

# --- ÉTAPE A : Vérification et Installation de HOMEBREW ---
if ! command -v brew &> /dev/null; then
    echo "⚠️  Homebrew n'est pas installé."
    echo "☕️ Installation de Homebrew en cours..."
    echo "❗  Le terminal va demander votre mot de passe : Tapez-le (rien ne s'affiche) puis ENTRÉE."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Configuration du chemin (PATH) après installation
    if [[ $(uname -m) == 'arm64' ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    else
        eval "$(/usr/local/bin/brew shellenv)"
    fi
else
    echo "✅ Homebrew est déjà installé."
fi

# --- ÉTAPE B : Vérification et Installation de PYTHON 3 ---
if ! command -v python3 &> /dev/null; then
    echo "🐍 Installation de Python 3..."
    brew install python
else
    echo "✅ Python 3 est déjà installé."
fi

# --- ÉTAPE C : Mise en place du PROJET ---
if [ ! -d "venv" ]; then
    echo "🔨 Création de l'environnement virtuel 'venv'..."
    python3 -m venv venv
fi

source venv/bin/activate

if [ -f "requirements.txt" ]; then
    echo "📦 Vérification des librairies..."
    pip install -r requirements.txt
else
    echo "⚠️  requirements.txt manquant. Installation manuelle..."
    pip install f1-23-telemetry flask-socketio
fi

# --- ÉTAPE D : Détection IP & Pop-up (Version Fiable) ---

echo "📡 Détection de votre adresse IP locale..."

# Astuce de pro : On utilise Python pour trouver l'IP utilisée pour sortir vers le réseau.
# C'est la méthode la plus fiable pour avoir l'IP locale (ex: 192.168.1.15).
MON_IP=$(python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()")

echo "🔔 Affichage des instructions..."

# Le texte de la pop-up
MSG="Pour connecter votre jeu F1 24, configurez la télémétrie ainsi :

1. Allez dans Paramètres > Télémétrie
2. UDP Telemetry : Activé
3. UDP IP Address : $MON_IP
4. Port : 20777
5. Format UDP : F1 23"

# Affichage de la fenêtre (le script se met en pause ici)
osascript -e "display dialog \"$MSG\" with title \"Configuration Requise F1 24\" buttons {\"C'est fait, lancer !\"} default button 1 with icon note"

# --- ÉTAPE E : Lancement ---

echo "🌍 Ouverture du navigateur..."
# On lance le navigateur en arrière-plan
(sleep 2 && open http://127.0.0.1:5000) &

echo "🚀 Lancement du listener..."
python3 listener.py