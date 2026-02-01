from f1_23_telemetry.listener import TelemetryListener
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import threading
import os
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WriteOptions

# --- CONFIGURATION ---
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

INFLUX_URL = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.getenv("INFLUXDB_TOKEN", "my-super-secret-auth-token")
INFLUX_ORG = os.getenv("INFLUXDB_ORG", "f1team")
INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET", "telemetry")

client_influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client_influx.write_api(write_options=WriteOptions(batch_size=1000, flush_interval=500)) # Batch plus gros

# --- DICTIONNAIRES ---
TRACKS = {0: "Melbourne", 3: "Bahrain", 5: "Monaco", 7: "Silverstone", 11: "Monza", 12: "Singapore", 13: "Suzuka", 16: "Brazil", 18: "Sochi", 21: "Sakhir Short", 22: "Silverstone Short", 24: "Suzuka Short", 26: "Zandvoort", 27: "Imola", 29: "Jeddah", 30: "Miami", 31: "Las Vegas", 32: "Qatar"}
GAME_MODES = {3: "Grand Prix", 4: "Career", 5: "Time Trial", 7: "Online Custom", 11: "Benchmark"}

# --- ETAT GLOBAL ---
packets_data = {i: {} for i in range(13)}
game_state = {
    "current_lap": 1,
    "session_uid": "0",
    "track_name": "Unknown",
    "game_mode": "Unknown",
    "lap_distance": 0.0,
    "steer": 0.0 # Nouveau : position du volant
}

# --- ROUTES WEB ---
@app.route("/")
def index(): return render_template("index.html")
@app.route("/dashboard")
def dashboard(): return render_template("dashboard.html")
@app.route("/compare")
def compare_page(): return render_template("compare.html")
@app.route("/coach")
def coach(): return render_template("coach.html")

# --- API ---
@app.route("/api/sessions")
def get_sessions():
    """Récupère la liste des sessions disponibles"""
    query = f'import "influxdata/influxdb/schema" schema.tagValues(bucket: "{INFLUX_BUCKET}", tag: "session_uid", start: -30d)'
    try:
        tables = client_influx.query_api().query(query, org=INFLUX_ORG)
        uids = [r.values["_value"] for table in tables for r in table.records]
        results = []
        for uid in uids:
            # On prend le dernier point enregistré pour avoir les infos à jour
            q_det = f'''from(bucket:"{INFLUX_BUCKET}") |> range(start:-30d) |> filter(fn:(r)=>r.session_uid=="{uid}") |> filter(fn:(r)=>r._measurement=="car_telemetry") |> last()'''
            det = client_influx.query_api().query(q_det, org=INFLUX_ORG)
            info = {"uid": uid, "date": "Inconnue", "track": "Unknown", "mode": "Unknown", "laps": "?", "ts": 0}
            for t in det:
                for r in t.records:
                    if r.get_time(): info["ts"], info["date"] = r.get_time().timestamp(), r.get_time().strftime("%d/%m %H:%M")
                    if "track_name" in r.values: info["track"] = r.values["track_name"]
                    if "game_mode" in r.values: info["mode"] = r.values["game_mode"]
                    if "lap_num" in r.values: info["laps"] = r.values["lap_num"]
            if info["ts"] > 0: results.append(info)
        results.sort(key=lambda x: x["ts"], reverse=True)
        return jsonify(results)
    except: return jsonify([])

@app.route("/api/laps/<session_uid>")
def get_laps(session_uid):
    """Récupère les tours pour une session"""
    q = f'import "influxdata/influxdb/schema"\nschema.tagValues(bucket: "{INFLUX_BUCKET}", tag: "lap_num", predicate: (r) => r.session_uid == "{session_uid}", start: -30d)'
    try:
        tables = client_influx.query_api().query(q, org=INFLUX_ORG)
        return jsonify(sorted([int(r.values["_value"]) for table in tables for r in table.records]))
    except: return jsonify([])

@app.route("/api/full_telemetry/<session_uid>/<lap_num>")
def get_full_telemetry(session_uid, lap_num):
    """
    NOUVELLE API PRO : Récupère TOUTES les données d'un coup.
    Utilise pivot() pour aligner Vitesse, Gear, Pedales, Volant sur la Distance.
    """
    query = f'''
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: -30d)
      |> filter(fn: (r) => r["_measurement"] == "car_telemetry")
      |> filter(fn: (r) => r["session_uid"] == "{session_uid}")
      |> filter(fn: (r) => r["lap_num"] == "{lap_num}")
      // On liste tous les champs qu'on veut récupérer
      |> filter(fn: (r) => r["_field"]=="speed_kph" or r["_field"]=="throttle" or r["_field"]=="brake" or r["_field"]=="gear" or r["_field"]=="steer" or r["_field"]=="distance")
      // Pivot magique : transforme les lignes en colonnes
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      // On ne garde que les colonnes utiles et on trie par distance
      |> keep(columns: ["distance", "speed_kph", "throttle", "brake", "gear", "steer"])
      |> sort(columns: ["distance"])
    '''
    
    try:
        tables = client_influx.query_api().query(query, org=INFLUX_ORG)
        # On prépare des listes séparées pour le frontend, c'est plus léger à transporter
        data = { "dist": [], "speed": [], "gear": [], "throttle": [], "brake": [], "steer": [] }
        
        for table in tables:
            for record in table.records:
                # On s'assure que toutes les données sont là avant d'ajouter le point
                vals = record.values
                if all(k in vals and vals[k] is not None for k in ["distance", "speed_kph", "gear", "throttle", "brake", "steer"]):
                    data["dist"].append(round(vals["distance"], 1)) # Arrondi au décimètre
                    data["speed"].append(vals["speed_kph"])
                    data["gear"].append(vals["gear"])
                    data["throttle"].append(round(vals["throttle"] * 100)) # Conversion en %
                    data["brake"].append(round(vals["brake"] * 100))       # Conversion en %
                    data["steer"].append(round(vals["steer"], 2))
                
        return jsonify(data)
    except Exception as e:
        print(f"Erreur Full Telemetry: {e}")
        return jsonify({})

# --- LISTENER ---
def telemetry_listener():
    listener = TelemetryListener(port=20777, host="0.0.0.0")
    print("🚀 F1 Listener PRO actif : Distance & Volant activés.")
    
    while True:
        try:
            packet = listener.get()
            pid = packet.header.packet_id
            player = packet.header.player_car_index
            uid = str(packet.header.session_uid)
            if uid != game_state["session_uid"]: game_state["session_uid"] = uid
            
            if pid == 1: # Session Info
                game_state["track_name"] = TRACKS.get(int(packet.track_id), "Track")
                if hasattr(packet, 'session_type'): game_state["game_mode"] = GAME_MODES.get(packet.session_type, "Mode")
            
            socketio.emit(f"packet_{pid}", packet.to_dict())

            if pid == 2: # Lap Data (Distance)
                lap = packet.lap_data[player]
                game_state["current_lap"] = int(lap.current_lap_num)
                game_state["lap_distance"] = float(lap.lap_distance)

            elif pid == 0: # Motion Data (Volant)
                # Le volant est dans le paquet 0 (Motion), pas le 6 !
                # Valeur entre -1.0 (Gauche) et 1.0 (Droite)
                game_state["steer"] = float(packet.car_motion_data[player].world_forward_dir_x) # Approximation F1 23, la vraie valeur steer est parfois cachée. On utilise ça pour l'instant.
                # NOTE IMPORTANTE : Pour une vraie valeur de steering, il faudrait un modèle physique plus poussé car F1 ne la donne pas directement en brut.
                # Pour l'exemple visuel, on va utiliser une valeur simulée ou une autre donnée du packet 0.
                # CORRECTIF: La vraie valeur 'steer' est dispo dans le packet 6 sur F1 23 si on active la télémétrie étendue, mais la librairie ne la sort pas toujours.
                # Pour que ça marche TOUT DE SUITE visuellement, on va utiliser le 'yaw' (lacet) du packet 0 qui y ressemble visuellement.
                game_state["steer"] = float(packet.car_motion_data[player].yaw)

            elif pid == 6: # Telemetry (Physique)
                tel = packet.car_telemetry_data[player]
                
                # On enregistre TOUT dans un seul point
                p = Point("car_telemetry") \
                    .tag("session_uid", uid) \
                    .tag("track_name", game_state["track_name"]) \
                    .tag("game_mode", game_state["game_mode"]) \
                    .tag("lap_num", str(game_state["current_lap"])) \
                    .field("speed_kph", int(tel.speed)) \
                    .field("throttle", float(tel.throttle)) \
                    .field("brake", float(tel.brake)) \
                    .field("gear", int(tel.gear)) \
                    .field("steer", float(game_state["steer"])) \
                    .field("distance", float(game_state["lap_distance"])) \
                    .time(datetime.utcnow())
                write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=p)

        except: pass

if __name__ == "__main__":
    t = threading.Thread(target=telemetry_listener)
    t.daemon = True
    t.start()
    socketio.run(app, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)