from f1_23_telemetry.listener import TelemetryListener
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Dictionnaire global: { packet_id: dernier_packet_dict }
packets_data = {i: {} for i in range(13)}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/packet/<int:packet_id>")
def show_packet(packet_id):
    """Affiche dynamiquement les données d’un packet"""
    return render_template("packet.html", packet_id=packet_id)

def telemetry_listener():
    listener = TelemetryListener(port=20777, host="0.0.0.0")
    print("En attente de données UDP depuis F1 23...")

    while True:
        try:
            packet = listener.get()
            pid = packet.header.packet_id

            # stocke le dict complet
            packets_data[pid] = packet.to_dict()

            # envoie au front
            socketio.emit(f"packet_{pid}", packets_data[pid])

        except KeyboardInterrupt:
            print("\nArrêt du listener")
            break
        except Exception as e:
            print(f"Erreur: {e}")

def main():
    t = threading.Thread(target=telemetry_listener, daemon=True)
    t.start()
    socketio.run(app, host="0.0.0.0", port=5000)

if __name__ == "__main__":
    main()
