# IntelliBin — Smart Waste Collection System

IoT-based smart waste bin monitoring and optimal collection route planning system. Bins report fill levels via LoRa, a central server logs data and computes optimal collection routes, and an ML model predicts fill patterns to generate collection schedules.

## Architecture

```
[Bin 1: ESP32 + Ultrasonic + MPU6050]  ──LoRa 868MHz──┐
[Bin 2: ESP32 simulated]               ──LoRa 868MHz──┼──▶ [Receiver ESP32] ──Serial──▶ [Flask Server]
[Bin 3: ESP32 simulated]               ──LoRa 868MHz──┘         │                          │
                                                                 │                     ┌────┴────┐
                                                                 ▼                     ▼         ▼
                                                            OLED Display         Route Planner   CSV Log
                                                                                (Leaflet.js)      │
                                                                                                  ▼
                                                                                           ML Predictor
                                                                                        (Collection Schedule)
```

## Project Structure

```
├── transmitter.ino          # Real bin (Bin 1): HC-SR04 ultrasonic + MPU6050 accelerometer
├── trans2.ino               # Simulated bins (Bin 2 & 3): gradual fill + random movement
├── reciver.ino              # LoRa receiver gateway: forwards packets to Serial
└── osrm_trial/
    ├── app.py               # Flask web server: serial listener, route API, Leaflet.js frontend
    ├── path_planner.py       # TSP solver: brute-force (≤8 goals) / nearest-neighbor + 2-opt (>8)
    └── ml/
        ├── simulate_data.py  # Generate realistic multi-day training data
        ├── predictor.py      # Random Forest model: predict fill levels → collection schedule
        └── visualize.py      # Generate standalone HTML report with charts
```

## Hardware

| Component | Role |
|-----------|------|
| Heltec WiFi LoRa 32 (ESP32) x3 | Transmitter (x2) + Receiver (x1) |
| HC-SR04 Ultrasonic Sensor | Measure bin fill distance (Bin 1) |
| MPU6050 Accelerometer | Detect bin movement/tampering (Bin 1) |
| LoRa 868 MHz | Wireless communication between bins and gateway |

## LoRa Packet Format

```
ID:1,STAT:FULL,Mov:0,Percentage:85
```

| Field | Description |
|-------|-------------|
| `ID` | Bin identifier (1–3) |
| `STAT` | `FULL` (≥80%) or `EMPTY` (<80%) |
| `Mov` | Movement detected (1) or not (0) |
| `Percentage` | Fill level 0–100% |

## Setup

### Server (Route Planner + Data Collection)

```bash
cd osrm_trial
python3 -m venv .venv
source .venv/bin/activate       # bash/zsh
# source .venv/bin/activate.fish  # fish shell
pip install flask osmnx networkx pyserial folium scikit-learn numpy
```

### Run

```bash
cd osrm_trial
python3 app.py
```

Opens `http://localhost:8080`. Set serial port via environment variable:

```bash
SERIAL_PORT=/dev/ttyUSB0 python3 app.py
```

## ML Prediction Pipeline

### 1. Generate Training Data

```bash
cd osrm_trial
.venv/bin/python ml/simulate_data.py --days 30 --bins 3
```

Generates `training_data.csv` with realistic fill patterns (residential, commercial, park profiles).

### 2. Run Predictor

```bash
.venv/bin/python ml/predictor.py --data training_data.csv --forecast-hours 24
```

Outputs per-bin MAE and a collection schedule for the next 24 hours.

### 3. Visualize Results

```bash
.venv/bin/python ml/visualize.py --data training_data.csv --out ml/report.html
open ml/report.html
```

Generates a standalone HTML report with:
- Historical fill curves
- Forecast with FULL threshold
- Backtest (actual vs predicted)
- Per-bin MAE comparison
- Predicted collection schedule

## Data Logging

The server logs all bin readings to `bin_log.csv`:

```csv
Timestamp,Bin ID,Percentage,Status,Movement
2025-01-15 08:30:12,1,45,EMPTY,0
2025-01-15 08:30:16,2,82,FULL,0
```

## Route Planning

The web frontend provides:
- Interactive Leaflet.js map with draggable markers
- Real-time route recalculation on the OSM road network
- Optimal visit order via TSP (brute-force or heuristic)
- Live bin status polling from serial data
