# Route Planner

An interactive multi-stop route planner built on OpenStreetMap data. Given a start point and multiple goal locations, it finds the shortest road-snapped route visiting all goals (brute-force TSP).

## Files

| File | Description |
|------|-------------|
| `app.py` | Flask web app with a Leaflet.js frontend — drag markers to replan in real time |
| `path_planner.py` | Standalone script that computes and renders the route to a static Folium HTML map |
| `overpass_streets.py` | Utility to query street data around a coordinate via the Overpass API |
| `route_map.html` | Pre-generated example map output |

## Setup

```bash
pip install flask osmnx networkx folium requests
```

## Usage

### Interactive web app

```bash
python app.py
```

Opens `http://localhost:5000` in your browser. Drag the blue **Start** marker or any red **Goal** marker to recalculate the route on the fly.

### Static map script

```bash
python path_planner.py
```

Downloads the street network, computes the optimal visit order, and saves `route_map.html` (opened automatically).

### Street lookup utility

```bash
python overpass_streets.py
```

Queries streets within a radius of a coordinate using the Overpass API and prints results to the terminal.

## How it works

1. Downloads the drivable street network for the bounding box of all points using [OSMnx](https://osmnx.readthedocs.io/).
2. Snaps each coordinate to the nearest graph node.
3. Tries all permutations of the goal points (brute-force TSP) and picks the ordering with the shortest total road distance.
4. Returns the full node path and renders it as a polyline on the map.

> **Note:** Brute-force TSP is only practical for a small number of goals (up to ~8–9). For larger inputs, a heuristic solver would be needed.

## Default coordinates

All scripts default to central Paris, France:

- **Start:** `48.8566, 2.3522` (Notre-Dame area)
- **Goals:** three nearby landmarks

Edit the `DEFAULT_START` / `DEFAULT_GOALS` constants at the top of each file to use different locations.
