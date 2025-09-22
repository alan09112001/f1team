from f1_23_telemetry.listener import TelemetryListener
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading
import os

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
    # Tours et secteurs
    "lap_time": "00:00:000", "best_lap_time": "00:00:000",
    "ahead_lap_time": "00:00:000", "ahead_best_lap_time": "00:00:000",
    "sectors": ["00:00:000", "00:00:000", "00:00:000"],
    "ahead_sectors": ["00:00:000", "00:00:000", "00:00:000"],
    "improved_sectors": [False, False, False],
    "average_speed": 0.0, "ahead_average_speed": 0.0,
    # LapData enrichi
    "current_lap_num": 0,
    "current_lap_time_in_ms": "00:00:000",
    "last_lap_time_in_ms": "00:00:000",
    "lap_distance": 0.0,
    "total_distance": 0.0,
    "car_position": 0,
    "grid_position": 0,
    "sector": 0,
    "sector_1_time_in_ms": "00:00:000",
    "sector_2_time_in_ms": "00:00:000",
    "corner_cutting_warnings": 0,
    "penalties": 0,
    "num_pit_stops": 0,
    "pit_status": 0,
    "driver_status": 0,
    "result_status": 0,
    "safety_car_delta": 0.0
}

last_ahead_ers_mode = None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/lapdata")
def lapdata():
    """Page d’affichage des données LapData"""
    return render_template("lapdata.html")


def ms_to_time(val):
    """Convertit des millisecondes en format mm:ss:ms"""
    try:
        val = int(val)
        minutes = int(val // 60000)
        seconds = int((val % 60000) // 1000)
        millis = int(val % 1000)
        return f"{minutes:02}:{seconds:02}:{millis:03}"
    except Exception:
        return "00:00:000"


def safe_getattr(obj, *names, default=0):
    """
    Retourne la première valeur non-None trouvée parmi plusieurs noms d'attributs.
    Permet d'être tolérant sur les variantes de nommage dans les différentes
    librairies/specs (ex: CurrentLapTimeInMS / current_lap_time_in_ms / currentLapTimeInMS).
    """
    for name in names:
        if hasattr(obj, name):
            v = getattr(obj, name)
            if v is not None:
                return v
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

            # Lap Data (id=2)
            if packet.header.packet_id == 2:
                lap = packet.lap_data[player_idx]
                telemetry_data.update({
                    "current_lap_num": safe_getattr(lap, "current_lap_num", "CurrentLapNum", default=0),
                    "current_lap_time_in_ms": ms_to_time(safe_getattr(lap, "current_lap_time_in_ms", "CurrentLapTimeInMS", default=0)),
                    "last_lap_time_in_ms": ms_to_time(safe_getattr(lap, "last_lap_time_in_ms", "LastLapTimeInMS", default=0)),
                    "lap_distance": safe_getattr(lap, "lap_distance", "LapDistance", default=0.0),
                    "total_distance": safe_getattr(lap, "total_distance", "TotalDistance", default=0.0),
                    "car_position": safe_getattr(lap, "car_position", "CarPosition", default=0),
                    "grid_position": safe_getattr(lap, "grid_position", "GridPosition", default=0),
                    "sector": safe_getattr(lap, "sector", "Sector", default=0),
                    "sector_1_time_in_ms": ms_to_time(safe_getattr(lap, "sector_1_time_in_ms", "Sector1TimeInMS", default=0)),
                    "sector_2_time_in_ms": ms_to_time(safe_getattr(lap, "sector_2_time_in_ms", "Sector2TimeInMS", default=0)),
                    "corner_cutting_warnings": safe_getattr(lap, "corner_cutting_warnings", "CornerCuttingWarnings", default=0),
                    "penalties": safe_getattr(lap, "penalties", "Penalties", default=0),
                    "num_pit_stops": safe_getattr(lap, "num_pit_stops", "NumPitStops", default=0),
                    "pit_status": safe_getattr(lap, "pit_status", "PitStatus", default=0),
                    "driver_status": safe_getattr(lap, "driver_status", "DriverStatus", default=0),
                    "result_status": safe_getattr(lap, "result_status", "ResultStatus", default=0),
                    "safety_car_delta": safe_getattr(lap, "safety_car_delta", "SafetyCarDelta", default=0.0),
                })

            # Session Data (id=1)
            if packet.header.packet_id == 1:
                session = packet
                telemetry_data["total_laps"] = safe_getattr(session, "total_laps", "TotalLaps", "num_laps", default=0)

            socketio.emit("update", telemetry_data)

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
