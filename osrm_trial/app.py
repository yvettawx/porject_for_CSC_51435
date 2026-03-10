"""
Interactive draggable route planner — Flask backend + Leaflet.js frontend.

Run:
    pip3 install flask osmnx networkx pyserial
    python3 app.py
Then open http://localhost:5000
"""

import threading
import webbrowser
import serial  # pyserial, for reading bin status from Arduino (optional)
import networkx as nx
import osmnx as ox
from flask import Flask, jsonify, render_template_string, request
import csv
from datetime import datetime
import os
from path_planner import nearest_node, best_visit_order
# ---------------------------------------------------------------------------
# Default coordinates (Paris)
# ---------------------------------------------------------------------------

DEFAULT_START = (48.8566, 2.3522)
DEFAULT_GOALS = [
    (48.8606, 2.3376),
    (48.8530, 2.3499),
    (48.8490, 2.3620),
]

# Bin state (full + mov)
goal_status = [{"full": False, "mov": 0} for _ in DEFAULT_GOALS]
goal_lock = threading.Lock()
SERIAL_PORT = os.environ.get("SERIAL_PORT", "/dev/ttyUSB0")
BAUD_RATE = 115200

# ---------------------------------------------------------------------------
# Graph cache
# ---------------------------------------------------------------------------

_graph: nx.MultiDiGraph | None = None
_graph_bbox: tuple[float, float, float, float] | None = None  # (north, south, east, west)
_graph_lock = threading.Lock()
PADDING = 0.01
EDGE_THRESHOLD = 0.003

def _bounding_box(points: list[tuple[float, float]], padding: float = PADDING):
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return (
        max(lats) + padding, min(lats) - padding,
        max(lons) + padding, min(lons) - padding
    )

def _points_fit(points: list[tuple[float, float]], bbox: tuple) -> bool:
    north, south, east, west = bbox
    for lat, lon in points:
        if (lat > north - EDGE_THRESHOLD or lat < south + EDGE_THRESHOLD or
            lon > east - EDGE_THRESHOLD or lon < west + EDGE_THRESHOLD):
            return False
    return True

def get_graph(points: list[tuple[float, float]]) -> nx.MultiDiGraph:
    global _graph, _graph_bbox
    with _graph_lock:
        if _graph is None or _graph_bbox is None or not _points_fit(points, _graph_bbox):
            north, south, east, west = _bounding_box(points)
            print(f"Downloading street network for bbox N{north:.4f} S{south:.4f} E{east:.4f} W{west:.4f} …")
            G = ox.graph_from_bbox((west, south, east, north), network_type="drive")
            G = ox.add_edge_speeds(G)
            G = ox.add_edge_travel_times(G)
            print(f"Graph loaded: {len(G.nodes)} nodes, {len(G.edges)} edges")
            _graph = G
            _graph_bbox = (north, south, east, west)
        return _graph

# Routing helpers imported from path_planner:
# nearest_node, best_visit_order

# ---------------------------------------------------------------------------
# Serial listener
# ---------------------------------------------------------------------------

CSV_LOG_FILE = "bin_log.csv"
CSV_COLUMNS = ["Timestamp", "Bin ID", "Percentage", "Status", "Movement"]

def _init_csv():
    if not os.path.exists(CSV_LOG_FILE):
        with open(CSV_LOG_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)

def serial_listener():
    global goal_status
    _init_csv()
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"[SERIAL] Connected to {SERIAL_PORT}")
    except Exception as e:
        print("[SERIAL] Connection error:", e)
        return

    while True:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue
            # Expected format: ID:2,STAT:EMPTY,Mov:0,Percentage:39
            pairs = [item.split(":", 1) for item in line.split(",")]
            if not all(len(p) == 2 for p in pairs):
                print(f"[SERIAL] Malformed line: {line}")
                continue
            parts = dict(pairs)
            if "ID" not in parts or "STAT" not in parts:
                print(f"[SERIAL] Missing required fields: {line}")
                continue
            bin_id = int(parts["ID"]) - 1
            status = parts["STAT"]
            percentage = int(float(parts.get("Percentage", 0)))
            if 0 <= bin_id < len(goal_status):
                with goal_lock:
                    goal_status[bin_id]["full"] = (status == "FULL")
                    goal_status[bin_id]["mov"] = int(parts.get("Mov", 0))
                    print(f"[SERIAL] Updated bin {bin_id+1} → {status}, Mov: {goal_status[bin_id]['mov']}, Percentage: {percentage}%")
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    mov = goal_status[bin_id]["mov"]
                    with open(CSV_LOG_FILE, "a", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerow([timestamp, bin_id + 1, percentage, status, mov])
        except Exception as e:
            print("[SERIAL] Parse error:", e)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Route Planner</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  *{box-sizing:border-box;margin:0;padding:0;}
  body{font-family:system-ui,sans-serif;display:flex;height:100vh;}
  #map{flex:1;}
  #panel{width:260px;padding:16px;background:#1e1e2e;color:#cdd6f4;display:flex;flex-direction:column;gap:12px;overflow-y:auto;}
  #panel h2{font-size:1rem;color:#89b4fa;}
  #info{font-size:0.85rem;line-height:1.6;}
  #info .label{color:#a6e3a1;font-weight:600;}
  #spinner{display:none;align-items:center;gap:8px;color:#f38ba8;font-size:0.8rem;}
  #spinner.active{display:flex;}
  .dot{width:8px;height:8px;border-radius:50%;background:#f38ba8;animation:pulse 1s infinite ease-in-out;}
  .dot:nth-child(2){animation-delay:0.2s;}
  .dot:nth-child(3){animation-delay:0.4s;}
  @keyframes pulse{0%,100%{opacity:.2}50%{opacity:1}}
  #hint{font-size:0.75rem;color:#6c7086;margin-top:auto;}
  #goal-list{display:flex;flex-direction:column;gap:6px;}
  .goal-item{display:flex;align-items:center;gap:8px;font-size:0.85rem;}
</style>
</head>
<body>
<div id="map"></div>
<div id="panel">
  <h2>Route Planner</h2>
  <div id="goal-list"></div>
  <div id="spinner"><div class="dot"></div><div class="dot"></div><div class="dot"></div> Computing…</div>
  <div id="info">Drag any marker to update the route.</div>
  <p id="hint">Blue = Start | Red = Goals | Route road-snapped via OSM.</p>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const DEFAULT_START = {{ start_json | safe }};
const DEFAULT_GOALS = {{ goals_json | safe }};

const map = L.map('map').setView(DEFAULT_START, 14);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors'}).addTo(map);

function blueIcon(label){return L.divIcon({className:'',html:`<div style="background:#3b82f6;color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)">${label}</div>`,iconSize:[28,28],iconAnchor:[14,14]})}
function redIcon(label){return L.divIcon({className:'',html:`<div style="background:#ef4444;color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)">${label}</div>`,iconSize:[28,28],iconAnchor:[14,14]})}

const startMarker = L.marker(DEFAULT_START,{draggable:true,icon:blueIcon('S')}).addTo(map).bindTooltip('Start',{permanent:false});
const goalMarkers = DEFAULT_GOALS.map((pt,i)=>L.marker(pt,{draggable:true,icon:redIcon(i+1)}).addTo(map).bindTooltip(`Goal ${i+1}`,{permanent:false}));

let goalMov = [];

async function fetchStatus(){
    const r = await fetch('/goal_status');
    const status = await r.json();
    status.forEach((v,i)=>{
        goalMarkers[i].setOpacity(v.full?1:0.3);
        goalMov[i] = v.mov;
    });
    renderGoalList();
    fetchRoute();
}

function renderGoalList(){
    const list = document.getElementById('goal-list');
    list.innerHTML = goalMov.map((mov,i)=>`
        <div class="goal-item">
            Goal ${i+1} — Mov: ${mov}
        </div>`).join('');
}

setInterval(fetchStatus,4000);

let routeLine=L.polyline([], {color:'#3b82f6', weight:5, opacity:0.85}).addTo(map);

async function fetchRoute(){
    const spinner = document.getElementById('spinner');
    const info = document.getElementById('info');
    spinner.classList.add('active');

    const start = startMarker.getLatLng();

    // Only include full bins for the route
    const goals = goalMarkers.map((m,i)=>{
        const ll = m.getLatLng();
        return {latlng:[ll.lat,ll.lng], full: m.options.opacity===1};
    }).filter(g=>g.full).map(g=>g.latlng);

    if(goals.length===0){
        routeLine.setLatLngs([]);
        info.innerHTML='<span style="color:#6c7086">No full bins to visit.</span>';
        spinner.classList.remove('active');
        return;
    }

    try{
        const resp = await fetch('/route',{
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({start:[start.lat,start.lng],goals})
        });
        if(!resp.ok){
            const err = await resp.json().catch(()=>({error:resp.statusText}));
            info.innerHTML=`<span style="color:#f38ba8">Error: ${err.error||resp.statusText}</span>`;
            return;
        }
        const data = await resp.json();
        routeLine.setLatLngs(data.path);
        map.fitBounds(routeLine.getBounds(),{padding:[30,30]});

        const orderStr = data.order.map((_,i)=>`<span class="label">Stop ${i+1}</span> → ${data.order[i][0].toFixed(4)}, ${data.order[i][1].toFixed(4)}`).join('<br>');
        info.innerHTML = `<b>Distance:</b> ${data.distance_km.toFixed(2)} km<br><br><b>Visit order:</b><br><span class="label">Start</span> → ${start.lat.toFixed(4)}, ${start.lng.toFixed(4)}<br>` + orderStr;

    }catch(e){
        info.innerHTML=`<span style="color:#f38ba8">Network error: ${e.message}</span>`;
    } finally{
        spinner.classList.remove('active');
    }
}

startMarker.on('dragend',fetchRoute);
goalMarkers.forEach(m=>m.on('dragend',fetchRoute));

renderGoalList();
fetchRoute();
</script>
</body>
</html>
"""

@app.route("/goal_status")
def goal_status_api():
    with goal_lock:
        return jsonify(goal_status)

@app.route("/")
def index():
    import json
    start_json = json.dumps(list(DEFAULT_START))
    goals_json = json.dumps([list(g) for g in DEFAULT_GOALS])
    return render_template_string(HTML, start_json=start_json, goals_json=goals_json)

@app.route("/route", methods=["POST"])
def route():
    data = request.get_json(force=True)
    try:
        start = tuple(data["start"])
        goals = [tuple(g) for g in data["goals"]]
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid payload: {exc}"}), 400

    all_points = [start] + goals
    try:
        G = get_graph(all_points)
        order, dist_m, path_nodes = best_visit_order(G, start, goals)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    path_coords = [[G.nodes[n]["y"], G.nodes[n]["x"]] for n in path_nodes]

    return jsonify({
        "path": path_coords,
        "order": [list(pt) for pt in order],
        "distance_km": round(dist_m / 1000, 3),
    })

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    print(f"Starting Route Planner at http://localhost:{port}  (Ctrl-C to quit)")
    threading.Thread(target=serial_listener, daemon=True).start()
    app.run(debug=False, port=port)