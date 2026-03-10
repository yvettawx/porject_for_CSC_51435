# Route Planner & Data Server

Flask web server that combines real-time bin monitoring with interactive route planning on OpenStreetMap.

## Files

| File | Description |
|------|-------------|
| `app.py` | Flask server: serial listener, bin status API, route planner API, Leaflet.js frontend |
| `path_planner.py` | TSP solver: brute-force (≤8 goals), nearest-neighbor + 2-opt (>8 goals) |
| `ml/simulate_data.py` | Generate multi-day simulated training data |
| `ml/predictor.py` | Random Forest prediction model → collection schedule |
| `ml/visualize.py` | Generate standalone HTML report with evaluation charts |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask osmnx networkx pyserial folium scikit-learn numpy
```

## Usage

```bash
python3 app.py
```

Opens `http://localhost:8080`. Configure serial port: `SERIAL_PORT=/dev/ttyUSB0 python3 app.py`

## How it works

1. Downloads the drivable street network for the bounding box using [OSMnx](https://osmnx.readthedocs.io/).
2. Snaps each coordinate to the nearest graph node.
3. Solves TSP: brute-force permutations for ≤8 goals, nearest-neighbor + 2-opt heuristic for larger inputs.
4. Renders the optimal route as a polyline on an interactive Leaflet.js map.
5. Reads bin status from serial (LoRa receiver), logs to CSV, and exposes via `/status` API.
