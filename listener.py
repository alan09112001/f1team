from f1_23_telemetry.listener import TelemetryListener
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

telemetry_data = {
    # Ma voiture
    "speed": 0, "gear": 0, "engine_rpm": 0,
    "throttle": 0.0, "brake": 0.0, "ers_store_energy": 0.0,
    "tyres_wear": [0, 0, 0, 0], "tyres_damage": [0, 0, 0, 0],
    # Voiture devant
    "ahead_speed": 0, "ahead_gear": 0, "ahead_engine_rpm": 0,
    "ahead_throttle": 0.0, "ahead_brake": 0.0, "ahead_ers_store_energy": 0.0,
    "ahead_tyres_wear": [0, 0, 0, 0], "ahead_tyres_damage": [0, 0, 0, 0],
    "ahead_ers_mode": None,
    # Tour et secteurs
    "lap_time": 0.0, "best_lap_time": 0.0,
    "ahead_lap_time": 0.0, "ahead_best_lap_time": 0.0,
    "sectors": [0.0, 0.0, 0.0], "ahead_sectors": [0.0, 0.0, 0.0],
    "improved_sectors": [False, False, False],
    "average_speed": 0.0, "ahead_average_speed": 0.0,
    "current_lap_num": 0
}

last_ahead_ers_mode = None


@app.route("/")
def index():
    return render_template("index.html")


def ms_to_sec(val):
    try:
        return val / 1000.0
    except Exception:
        return 0.0


def safe_getattr(obj, *names, default=0):
    """
    Retourne la première valeur non-None trouvée parmi plusieurs noms d'attributs.
    Permet d'être tolérant sur les variantes de nommage dans les différentes
    librairies/specs (ex: CurrentLapTimeInMS / current_lap_time_in_ms / currentLapTimeInMS).
    """
    for name in names:
        # try attribute style
        if hasattr(obj, name):
            v = getattr(obj, name)
            if v is not None:
                return v
        # try camelCase / different casing by attempting dict-like access
        try:
            v = obj.__getattribute__(name)
            if v is not None:
                return v
        except Exception:
            pass
    return default


def telemetry_listener():
    global last_ahead_ers_mode
    listener = TelemetryListener(port=20777, host="0.0.0.0")
    print("En attente de données... Lance F1 23 et active l'UDP dans les options du jeu !")
    while True:
        try:
            packet = listener.get()
            player_idx = packet.header.player_car_index
            ahead_idx = max(0, player_idx - 1)

            # CarTelemetry (id=6)
            if packet.header.packet_id == 6:
                car = packet.car_telemetry_data[player_idx]
                telemetry_data.update({
                    "speed": safe_getattr(car, "speed", "Speed", default=0),
                    "gear": safe_getattr(car, "gear", "Gear", default=0),
                    "engine_rpm": safe_getattr(car, "engine_rpm", "engineRPM", "EngineRPM", default=0),
                    "throttle": safe_getattr(car, "throttle", "Throttle", default=0.0),
                    "brake": safe_getattr(car, "brake", "Brake", default=0.0)
                })
                ahead = packet.car_telemetry_data[ahead_idx]
                telemetry_data.update({
                    "ahead_speed": safe_getattr(ahead, "speed", "Speed", default=0),
                    "ahead_gear": safe_getattr(ahead, "gear", "Gear", default=0),
                    "ahead_engine_rpm": safe_getattr(ahead, "engine_rpm", "engineRPM", "EngineRPM", default=0),
                    "ahead_throttle": safe_getattr(ahead, "throttle", "Throttle", default=0.0),
                    "ahead_brake": safe_getattr(ahead, "brake", "Brake", default=0.0)
                })

            # CarStatus (id=7)
            if packet.header.packet_id == 7:
                car_status = packet.car_status_data[player_idx]
                ers_store = safe_getattr(car_status, "ers_store_energy", "ersStoreEnergy", default=0)
                telemetry_data["ers_store_energy"] = (ers_store * 100 / 4000000) if isinstance(ers_store, (int, float)) else ers_store
                ahead_status = packet.car_status_data[ahead_idx]
                ahead_ers_store = safe_getattr(ahead_status, "ers_store_energy", "ersStoreEnergy", default=0)
                telemetry_data["ahead_ers_store_energy"] = (ahead_ers_store * 100 / 4000000) if isinstance(ahead_ers_store, (int, float)) else ahead_ers_store

                # ERS IA devant
                current_mode = safe_getattr(ahead_status, "ers_deploy_mode", "ersDeployMode", default=None)
                telemetry_data["ahead_ers_mode"] = current_mode
                if last_ahead_ers_mode is None:
                    last_ahead_ers_mode = current_mode
                elif current_mode != last_ahead_ers_mode:
                    print(f"⚡ Mode ERS IA devant changé ! Nouveau mode : {current_mode}")
                    last_ahead_ers_mode = current_mode

            # CarDamage (id=9)
            if packet.header.packet_id == 9:
                car_damage = packet.car_damage_data[player_idx]
                telemetry_data["tyres_wear"] = safe_getattr(car_damage, "m_tyresWear", "tyresWear", default=telemetry_data["tyres_wear"])
                telemetry_data["tyres_damage"] = safe_getattr(car_damage, "m_tyresDamage", "tyresDamage", default=telemetry_data["tyres_damage"])
                ahead_damage = packet.car_damage_data[ahead_idx]
                telemetry_data["ahead_tyres_wear"] = safe_getattr(ahead_damage, "m_tyresWear", "tyresWear", default=telemetry_data["ahead_tyres_wear"])
                telemetry_data["ahead_tyres_damage"] = safe_getattr(ahead_damage, "m_tyresDamage", "tyresDamage", default=telemetry_data["ahead_tyres_damage"])

            # Envoi SocketIO
            socketio.emit("update", telemetry_data)

        except KeyboardInterrupt:
            print("\nArrêt du listener")
            break
        except Exception as e:
            # On logge l'erreur mais on continue — tolérance aux paquets incomplets
            print(f"Erreur: {e}")


def main():
    t = threading.Thread(target=telemetry_listener, daemon=True)
    t.start()
    socketio.run(app, host="0.0.0.0", port=5000)


if __name__ == "__main__":
    main()
